"""Study material beyond videos: books, articles, web pages and class notes.

Each piece of material is cut into passages of a paragraph or three, keeping the
page each passage is on and the heading it sits under. Every topic is then
matched against the passages with the same two stages used for videos (meaning
plus wording to shortlist, the cross-encoder to decide), and the best stretch
of each document becomes a *reading*: "Operating Systems: Three Easy Pieces,
pp. 112–118, §Paging". Readings are offered for every topic and are the main
suggestion for a topic no video teaches.

Material never feeds topic extraction or exam weighting: a 300-page book names
far more than the course asks for.
"""

from __future__ import annotations

import ipaddress
import logging
import re
import socket
import threading
from collections import OrderedDict
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit, urlunsplit

import numpy as np
from sqlalchemy import delete
from sqlalchemy.orm import Session

from ..models import Document, DocumentPassage, Project, Reading
from . import documents as documents_service
from .embeddings import from_blob, get_embedder, to_blob
from .matching import score_passages, tidy_snippet
from .recommend import (
    FIRST_STAGE_WEIGHT,
    KEY_TERM_WEIGHT,
    SHORTLIST_FLOOR,
    _key_words,
    _lexical_text,
    acronym_map,
    query_text,
)
from .rerank import get_reranker, query_hash

log = logging.getLogger(__name__)

PASSAGE_KINDS = ("reading", "notes")  # documents the student can be sent to read

TARGET_WORDS = 170  # a passage closes once it reaches this many words...
MAX_WORDS = 260  # ...and never grows past this (the cross-encoder reads ~250 words)
MIN_WORDS = 35  # shorter passages are merged into their neighbour
MAX_PASSAGES_PER_DOCUMENT = 2500

READING_HIT = 0.5  # relevance a passage needs to be recommended
SHORTLIST = 12  # passages per topic read by the cross-encoder
# Lower than for videos: a passage is one view of a topic among several, so its
# embedding score runs lower; on OSTEP's semaphore chapter the reader-writer
# section scored 0.30 here and 1.0 with the cross-encoder.
PASSAGE_SHORTLIST_FLOOR = 0.25
EXTEND_SHARE = 0.75  # neighbouring passages this close to the best one are read too
EXTEND_MAX = 6  # passages added on each side at most
MAX_READINGS = 3  # documents suggested per topic
RECAP_FACTOR = 0.8  # summaries, exercises and reference lists rank below the explanation
_RECAP = re.compile(
    r"\b(summary|conclusions?|recap|review questions|exercises|homework|problems|"
    r"references|bibliography|further reading|see also|notes)\s*$",
    re.I,
)


# ---------------------------------------------------------------------- passages


@dataclass
class _Draft:
    words: list[str]
    page_start: int
    page_end: int
    page_label: str
    heading: str


_NUMBERED_HEADING = re.compile(r"^(?:\d{1,2}(?:\.\d{1,2}){0,3}|[IVX]{1,5}\.|chapter\s+\d+)\s+\S", re.I)
# In PDF text a bare number before a line is usually a page number or a figure
# label, so there a heading must carry a dotted section number: "38.4 RAID Level 0".
_PDF_SECTION = re.compile(r"^(?:\d{1,2}(?:\.\d{1,2}){1,3}\.?|(?:[Cc]hapter|CHAPTER)\s+\d+:?)\s+[A-Z][a-zA-Z ]")


def _heading_line(line: str, *, strict: bool) -> str | None:
    """The heading text if this line is a heading, else None.

    Markdown headings and numbered section titles ("3.2 Paging") always count.
    Outside PDFs (``strict=False``) a short line in title or upper case without
    end punctuation counts too; in PDF text such lines are too often the end of
    a wrapped sentence, a caption or a running head.
    """
    text = line.strip()
    if not text or len(text) > 90:
        return None
    if text.startswith("#"):
        return text.lstrip("#").strip() or None
    words = text.split()
    if strict:  # a section title may be a question: "18.2 Where Are Page Tables Stored?"
        if len(words) > 12 or text[-1] in ".,;:!)" or not _PDF_SECTION.match(text):
            return None
        return text
    if len(words) > 10 or text[-1] in ".,;:!?)" or not text[0].isalnum():
        return None
    if _NUMBERED_HEADING.match(text) and any(c.isalpha() for c in text):
        return text
    letters = [w for w in words if w[:1].isalpha()]
    if not letters:
        return None
    capitalised = sum(1 for w in letters if w[0].isupper()) / len(letters)
    if text.isupper() or (capitalised >= 0.6 and len(words) <= 8):
        return text
    return None


def _line_key(line: str) -> str:
    """A line with its digits removed, so "4 PAGING: INTRODUCTION" and
    "6 PAGING: INTRODUCTION" compare equal."""
    return re.sub(r"[\d\s]+", " ", line.lower()).strip()


def _running_lines(units: list[documents_service.Unit]) -> set[str]:
    """Lines printed on many pages (running heads, footers, copyright lines)."""
    pages = [u for u in units if u.page]
    if len(pages) < 4:
        return set()
    counts: dict[str, int] = {}
    for unit in pages:
        for key in {_line_key(line) for line in unit.text.split("\n")}:
            if 3 <= len(key) <= 120:
                counts[key] = counts.get(key, 0) + 1
    floor = max(3, int(0.3 * len(pages)))
    return {key for key, count in counts.items() if count >= floor}


def build_passages(units: list[documents_service.Unit], *, pdf: bool) -> list[DocumentPassage]:
    """Cut a document's units (pages or sections) into passages.

    A passage never spans two headings. PDF pages flow into each other, because
    paragraphs continue over page breaks; sections of other formats do not.
    """
    drafts: list[_Draft] = []
    current: _Draft | None = None
    running = _running_lines(units) if pdf else set()

    def flush() -> None:
        nonlocal current
        if current and current.words:
            drafts.append(current)
        current = None

    heading = ""
    for unit in units:
        if unit.heading and unit.heading != heading:
            flush()
            heading = unit.heading
        for line in unit.text.split("\n"):
            if running and _line_key(line) in running:
                continue  # a running head or footer, repeated on most pages
            found = _heading_line(line, strict=pdf)
            if found and (not pdf or not unit.heading):
                flush()
                heading = found[:300]
                continue
            words = line.split()
            while words:
                if current is None:
                    current = _Draft([], unit.page, unit.page, unit.page_label, heading)
                room = MAX_WORDS - len(current.words)
                current.words.extend(words[:room])
                current.page_end = unit.page
                words = words[room:]
                if len(current.words) >= MAX_WORDS or (
                    len(current.words) >= TARGET_WORDS and line.rstrip().endswith((".", "?", "!", ":"))
                ):
                    flush()
        if not pdf:
            flush()
    flush()

    # Fold passages that are too short to match anything into a neighbour under
    # the same heading.
    merged: list[_Draft] = []
    for draft in drafts:
        previous = merged[-1] if merged else None
        if (
            previous is not None
            and previous.heading == draft.heading
            and (len(draft.words) < MIN_WORDS or len(previous.words) < MIN_WORDS)
            and len(previous.words) + len(draft.words) <= MAX_WORDS + MIN_WORDS
        ):
            previous.words.extend(draft.words)
            previous.page_end = draft.page_end or previous.page_end
        else:
            merged.append(draft)

    return [
        DocumentPassage(
            idx=number,
            page_start=draft.page_start,
            page_end=draft.page_end,
            page_label=draft.page_label,
            heading=draft.heading,
            text=" ".join(draft.words),
        )
        for number, draft in enumerate(merged[:MAX_PASSAGES_PER_DOCUMENT])
    ]


def set_passages(document: Document, extracted: documents_service.Extracted | None) -> None:
    """(Re)build a document's passages, from its layout when it was just read or
    from its stored text otherwise (pasted text, documents read before passages
    existed)."""
    if document.kind not in PASSAGE_KINDS:
        document.passages = []
        return
    units = extracted.units if extracted and extracted.units else [documents_service.Unit(document.text)]
    pdf = any(unit.page for unit in units)
    document.passages = build_passages(units, pdf=pdf)


def prepare_passages(db: Session, project: Project) -> None:
    """Give every ready study document passages, and embed the ones that need it."""
    embedder = get_embedder()
    for document in project.documents:
        if document.kind in PASSAGE_KINDS and document.status == "ready" and not document.passages:
            set_passages(document, None)
    db.flush()
    pending = [
        passage
        for document in project.documents
        if document.kind in PASSAGE_KINDS and document.status == "ready"
        for passage in document.passages
        if passage.embedding is None or passage.embedded_with != embedder.name
    ]
    for start in range(0, len(pending), 256):
        part = pending[start : start + 256]
        vectors = embedder.embed_passages([_passage_text(p.heading, p.text) for p in part])
        for passage, vector in zip(part, vectors, strict=True):
            passage.embedding = to_blob(vector)
            passage.embedded_with = embedder.name
    db.flush()


def _passage_text(heading: str, text: str) -> str:
    return f"{heading}. {text}" if heading else text


# ----------------------------------------------------------------------- matching

_rerank_cache: OrderedDict[tuple[str, str, int], float] = OrderedDict()
_rerank_lock = threading.Lock()
_RERANK_CACHE_SIZE = 50_000


def _raw_scores(model: str, query: str, items: list[tuple[int, str]], score) -> dict[int, float]:
    """Cross-encoder scores per passage id, remembered so re-matching after a
    topic edit only reads the passages that are new to that wording."""
    digest = query_hash(query)
    known: dict[int, float] = {}
    missing: list[tuple[int, str]] = []
    with _rerank_lock:
        for passage_id, text in items:
            key = (model, digest, passage_id)
            if key in _rerank_cache:
                _rerank_cache.move_to_end(key)
                known[passage_id] = _rerank_cache[key]
            else:
                missing.append((passage_id, text))
    if missing:
        fresh = score(query, [text for _, text in missing])
        with _rerank_lock:
            for (passage_id, _), value in zip(missing, fresh, strict=True):
                known[passage_id] = value
                _rerank_cache[(model, digest, passage_id)] = value
            while len(_rerank_cache) > _RERANK_CACHE_SIZE:
                _rerank_cache.popitem(last=False)
    return known


@dataclass
class _Hit:
    row: int  # position in the passage list
    relevance: float


def _relevance(
    query: str,
    first: np.ndarray,
    passages: list[DocumentPassage],
    texts: list[str],
) -> list[_Hit]:
    """Second-stage relevance for one topic's shortlist."""
    floor = PASSAGE_SHORTLIST_FLOOR if get_reranker() is not None else SHORTLIST_FLOOR
    order = [int(i) for i in np.argsort(-first)[:SHORTLIST] if first[i] >= floor]
    if not order:
        return []
    reranker = get_reranker()
    if reranker is None:
        values = {row: float(first[row]) for row in order}
    else:
        raw = _raw_scores(
            reranker.name,
            query,
            [(passages[row].id, texts[row]) for row in order],
            reranker.raw_scores,
        )
        values = {
            row: reranker.calibrate(raw[passages[row].id])
            * (1.0 - FIRST_STAGE_WEIGHT * (1.0 - float(first[row])))
            for row in order
        }
    # A passage that never uses the topic's distinctive words is a look-alike
    # (a CPU-scheduling page for "disk scheduling"); same rule as for videos.
    # Stems, so "readers" is found in "reader-writer locks".
    words = [w[:-2] if w.endswith("es") and len(w) > 5 else w[:-1] if w.endswith("s") and len(w) > 4 else w for w in _key_words(query)]
    hits = []
    for row, value in values.items():
        if words:
            text = texts[row].lower()
            missing = sum(1 for w in words if w not in text)
            value *= 1.0 - KEY_TERM_WEIGHT * missing / len(words)
        if _RECAP.search(passages[row].heading):
            # A chapter summary names every topic of the chapter in a few lines and
            # so matches each of them well, but it explains none of them.
            value *= RECAP_FACTOR
        hits.append(_Hit(row, value))
    return hits


def _stretch(
    best: DocumentPassage, first: np.ndarray, position: dict[int, int]
) -> list[DocumentPassage]:
    """The best passage plus the neighbours that continue it: those whose
    first-stage score is close to the best one's. A topic is often explained over
    several consecutive passages, even several sections ("RAID level 0", "RAID
    level 1", ... for "RAID levels"), and the student should read them all."""
    siblings = best.document.passages  # ordered by idx
    at = next(i for i, p in enumerate(siblings) if p.id == best.id)
    bar = EXTEND_SHARE * float(first[position[best.id]])

    def close(i: int) -> bool:
        row = position.get(siblings[i].id)
        return row is not None and float(first[row]) >= bar

    low = at
    while low > 0 and at - low < EXTEND_MAX and close(low - 1):
        low -= 1
    high = at
    while high + 1 < len(siblings) and high - at < EXTEND_MAX and close(high + 1):
        high += 1
    return siblings[low : high + 1]


def match_readings(db: Session, project: Project) -> int:
    """Rebuild every topic's readings. Returns how many were stored."""
    db.execute(delete(Reading).where(Reading.project_id == project.id))
    embedder = get_embedder()
    documents = [
        d for d in project.documents if d.kind in PASSAGE_KINDS and d.status == "ready"
    ]
    passages = [
        p
        for d in documents
        for p in d.passages
        if p.embedding is not None and p.embedded_with == embedder.name
    ]
    topics = [
        t
        for t in project.topics
        if not t.covered and t.embedding is not None and t.embedded_with == embedder.name
    ]
    if not passages or not topics:
        db.flush()
        return 0

    acronyms = acronym_map(project)
    queries = [query_text(t, acronyms) for t in topics]
    texts = [_passage_text(p.heading, p.text) for p in passages]
    first = score_passages(
        embedder,
        np.vstack([from_blob(t.embedding) for t in topics]),
        [_lexical_text(q, t) for q, t in zip(queries, topics, strict=True)],
        np.vstack([from_blob(p.embedding) for p in passages]),
        texts,
    )
    # Neighbours of a passage in its own document, for extending a stretch.
    position = {p.id: row for row, p in enumerate(passages)}

    stored = 0
    for topic_row, topic in enumerate(topics):
        hits = [
            h
            for h in _relevance(queries[topic_row], first[topic_row], passages, texts)
            if h.relevance >= READING_HIT
        ]
        best_per_document: dict[int, _Hit] = {}
        for hit in sorted(hits, key=lambda h: -h.relevance):
            best_per_document.setdefault(passages[hit.row].document_id, hit)
        chosen = sorted(best_per_document.values(), key=lambda h: -h.relevance)[:MAX_READINGS]
        for rank, hit in enumerate(chosen):
            best = passages[hit.row]
            stretch = _stretch(best, first[topic_row], position)
            pages = [p.page_start for p in stretch if p.page_start] + [
                p.page_end for p in stretch if p.page_end
            ]
            db.add(
                Reading(
                    project_id=project.id,
                    topic_id=topic.id,
                    document_id=best.document_id,
                    rank=rank,
                    relevance=round(hit.relevance, 4),
                    first_idx=stretch[0].idx,
                    last_idx=stretch[-1].idx,
                    page_start=min(pages) if pages else 0,
                    page_end=max(pages) if pages else 0,
                    page_label=stretch[0].page_label,
                    heading=best.heading,
                    snippet=tidy_snippet(best.text, 280),
                )
            )
            stored += 1
    db.flush()
    return stored


# ---------------------------------------------------------------------- web pages

MAX_PAGE_BYTES = 8 * 1024 * 1024
FETCH_TIMEOUT = 20.0
MAX_REDIRECTS = 5
USER_AGENT = "Waypoint-study-reader/1.0 (reads pages a student added to their course)"


class UnsafeURL(documents_service.DocumentError):
    """The address is not a public web page this server may fetch."""


def normalise_url(url: str) -> str:
    url = url.strip()
    scheme = re.match(r"^([a-z][a-z0-9+.-]*):(?!\d)", url, re.I)
    if "://" not in url and not scheme:  # "example.org/page" or "example.org:8080/page"
        url = "https://" + url
    parts = urlsplit(url)
    try:
        parts.port  # noqa: B018 — raises on a malformed port
    except ValueError:
        raise UnsafeURL("That web address is not valid.") from None
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise UnsafeURL("Enter a web address starting with http:// or https://.")
    if parts.username or parts.password:
        raise UnsafeURL("Web addresses with a user name or password are not accepted.")
    return urlunsplit((parts.scheme, parts.netloc, parts.path or "/", parts.query, ""))


def public_address(host: str, port: int) -> str:
    """Resolve a host name and return one of its addresses, refusing hosts that
    point anywhere but the public internet (this machine, the private network,
    cloud metadata services). Guards the server against being used to reach
    internal systems (server-side request forgery)."""
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except (socket.gaierror, UnicodeError) as exc:
        raise UnsafeURL("That web address could not be found.") from exc
    addresses = []
    for info in infos:
        address = ipaddress.ip_address(info[4][0].split("%")[0])
        if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
            address = address.ipv4_mapped
        if not address.is_global or address.is_multicast:
            raise UnsafeURL("Only public web pages can be added.")
        addresses.append(str(address))
    if not addresses:
        raise UnsafeURL("That web address could not be found.")
    return addresses[0]


def _download(url: str, address: str) -> tuple[int, dict[str, str], bytes]:
    """One GET to ``url``, connecting to the already-checked ``address`` so a
    second DNS answer cannot redirect the request (DNS rebinding)."""
    import httpx

    parts = urlsplit(url)
    host = parts.hostname or ""
    literal = f"[{address}]" if ":" in address else address
    netloc = literal + (f":{parts.port}" if parts.port else "")
    target = urlunsplit((parts.scheme, netloc, parts.path or "/", parts.query, ""))
    headers = {
        "Host": parts.netloc.rsplit("@", 1)[-1],
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/pdf,text/plain;q=0.9,*/*;q=0.1",
        "Accept-Language": "en;q=1.0, *;q=0.5",
    }
    extensions = {"sni_hostname": host} if parts.scheme == "https" else {}
    with (
        httpx.Client(timeout=FETCH_TIMEOUT, follow_redirects=False) as client,
        client.stream("GET", target, headers=headers, extensions=extensions) as response,
    ):
        declared = response.headers.get("content-length", "")
        if declared.isdigit() and int(declared) > MAX_PAGE_BYTES:
            raise documents_service.DocumentError("That web page is too large to read.")
        body = bytearray()
        for chunk in response.iter_bytes():
            body.extend(chunk)
            if len(body) > MAX_PAGE_BYTES:
                raise documents_service.DocumentError("That web page is too large to read.")
        return response.status_code, dict(response.headers), bytes(body)


def _decode(body: bytes, content_type: str) -> str:
    match = re.search(r"charset=([\w-]+)", content_type, re.I) or re.search(
        rb"<meta[^>]+charset=[\"']?([\w-]+)", body[:4096], re.I
    )
    charset = match.group(1) if match else "utf-8"
    if isinstance(charset, bytes):
        charset = charset.decode("ascii", "ignore")
    try:
        return body.decode(charset, errors="replace")
    except LookupError:
        return body.decode("utf-8", errors="replace")


def fetch_page(url: str) -> tuple[str, documents_service.Extracted]:
    """Download a web page (or a PDF on the web) and extract it. Returns a title
    and the extracted text. Raises DocumentError with a message for the student."""
    import httpx

    url = normalise_url(url)
    for _ in range(MAX_REDIRECTS + 1):
        parts = urlsplit(url)
        port = parts.port or (443 if parts.scheme == "https" else 80)
        address = public_address(parts.hostname or "", port)
        try:
            status, headers, body = _download(url, address)
        except httpx.HTTPError as exc:
            raise documents_service.DocumentError("That web page could not be reached.") from exc
        headers = {k.lower(): v for k, v in headers.items()}
        if status in (301, 302, 303, 307, 308) and headers.get("location"):
            url = normalise_url(urljoin(url, headers["location"]))
            continue  # every hop is checked again
        if status >= 400:
            raise documents_service.DocumentError(
                f"The web page answered with an error ({status}). Check the address."
            )
        content_type = headers.get("content-type", "").lower()
        name = (parts.path.rstrip("/").rsplit("/", 1)[-1] or parts.hostname or "page")[:200]
        if "pdf" in content_type or body.startswith(b"%PDF-"):
            return name, documents_service.extract(body, name if name.endswith(".pdf") else f"{name}.pdf")
        if "html" in content_type or body.lstrip()[:15].lower().startswith((b"<!doctype", b"<html")):
            title, extracted = documents_service.extract_html(_decode(body, content_type))
            return title or name, extracted
        if content_type.startswith("text/"):
            text = documents_service.clean_text(_decode(body, content_type))
            return name, documents_service.Extracted(text=text, units=[documents_service.Unit(text)])
        raise documents_service.DocumentError(
            "That address is not a web page, PDF or text file this app can read."
        )
    raise documents_service.DocumentError("That web page redirects too many times.")


def reading_url(document: Document, reading: Reading) -> str:
    """A link that opens the material at the right place, when there is one: the
    page of a PDF on the web, or the passage itself on a web page (text fragment)."""
    if not document.source_url:
        return ""
    if reading.page_start and document.content_type == "application/pdf":
        return f"{document.source_url}#page={reading.page_start}"
    if reading.heading:
        from urllib.parse import quote

        return f"{document.source_url}#:~:text={quote(reading.heading[:80], safe='')}"
    return document.source_url


__all__ = [
    "PASSAGE_KINDS",
    "UnsafeURL",
    "build_passages",
    "fetch_page",
    "match_readings",
    "normalise_url",
    "prepare_passages",
    "public_address",
    "reading_url",
    "set_passages",
]
