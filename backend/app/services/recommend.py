"""Build the learning path: topic vectors, candidate ranking, sequencing, search,
and learning from feedback."""

from __future__ import annotations

import re
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from itertools import pairwise

import numpy as np
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..models import Document, Feedback, Project, Recommendation, RerankScore, Topic
from .embeddings import Embedder, from_blob, get_embedder, to_blob
from .fuzzy import QualityInputs, final_score, quality_score
from .matching import (
    Match,
    ProjectIndex,
    get_index,
    hybrid_scores,
    locate,
    other_runs,
    score_passages,
    stretch_seconds,
    tidy_snippet,
    video_relevance,
)
from .rerank import get_reranker, query_hash
from .sequencing import Candidate, choose_path
from .topics import and_parts, chunk_paragraphs, is_generic, split_questions

DEFAULT_THRESHOLD = 0.5
THRESHOLD_RANGE = (-0.12, 0.20)  # how far feedback may move the threshold from the default
CANDIDATES_PER_TOPIC = 6
MAX_ALTERNATES = 3
EXAM_HIT = 0.5  # a past question at or above this score counts as "about" the topic
NOTES_HIT = 0.4  # lower than for videos: a mention in the notes is enough to flag a topic
NOTES_PASSAGE_WORDS = 25  # about a sentence or two
CLOSEST_FLOOR = 0.25
SHORTLIST_SIZE = 6  # videos per topic passed to the cross-encoder
SHORTLIST_FLOOR = 0.35  # embedding relevance needed to be shortlisted
RERANK_PASSAGES = 3  # transcript chunks per video read by the cross-encoder
FIRST_STAGE_WEIGHT = 0.15  # how much a weak embedding score trims the final relevance
TITLE_BONUS = 0.08  # tie-breaker for a video whose title names the topic
KEY_TERM_WEIGHT = 0.3  # most a topic's missing words can lower a video's relevance
OUTLINE_REFERENCES = 3  # "chapter 7 ... chapter 8 ... chapter 9" in one passage = a contents list
OUTLINE_PENALTY = 0.5  # relevance kept when a topic is only named in a contents list
NAMED_FLOOR = 0.6  # relevance of a video that discusses a topic by name
PRACTICE_PENALTY = 0.05  # worked-problem videos rank just below the concept lecture
CONTEXT_WEIGHT = 0.15  # share of the unit-qualified wording in a topic vector
NOTES_WEIGHT = 0.15  # share of the teacher's notes passage, when one matches

_UNIT_LABEL_ONLY = re.compile(
    r"^(unit|module|chapter|section|part|week|block)\s+\S+$", re.IGNORECASE
)


def unit_title(unit: str) -> str:
    """"Unit 3: Deadlocks" -> "Deadlocks"; "Module I" -> ""."""
    if ": " in unit:
        return unit.split(": ", 1)[1].strip()
    return "" if _UNIT_LABEL_ONLY.match(unit.strip()) else unit.strip()


_ACRONYM = re.compile(r"\b[A-Z]{2,6}\b")
_DEFINED_ACRONYM = re.compile(r"([A-Z][A-Za-z' -]{3,60}?)\s*\(([A-Z]{2,6})\)")
_MINOR_WORDS = {"of", "and", "the", "in", "for", "to", "a", "an", "on", "with"}


def acronym_map(project: Project) -> dict[str, str]:
    """Abbreviations that can be spelled out: the initials of the course subject
    ("OS" for "Operating Systems") and any "Full Name (ABBR)" a topic defines."""
    table: dict[str, str] = {}
    words = [w for w in re.findall(r"[A-Za-z]+", project.subject) if w.lower() not in _MINOR_WORDS]
    for size in range(2, 6):
        for start in range(len(words) - size + 1):
            window = words[start : start + size]
            table.setdefault("".join(w[0] for w in window).upper(), " ".join(window))
    for topic in project.topics:
        for full, short in _DEFINED_ACRONYM.findall(topic.name):
            table[short] = full.strip()
    return table


def query_text(topic: Topic, acronyms: dict[str, str]) -> str:
    """The wording used to match a topic, which can differ from its display name.

    * "Processes: Definition" is matched as "Processes": a generic sub-item asks
      for the introduction to its heading, and "definition" itself matches nothing.
    * Known abbreviations are spelled out ("Structure of an OS" -> "... Operating
      Systems"), because lecturers title videos with the full words.
    """
    name = topic.name
    if ": " in name:
        head, tail = name.split(": ", 1)
        if is_generic(tail):
            name = head

    def expand(match: re.Match) -> str:
        full = acronyms.get(match.group(0))
        if not full or full.lower() in name.lower():  # already spelled out in the name
            return match.group(0)
        return full

    return _ACRONYM.sub(expand, name)


def _lexical_text(text: str, topic: Topic) -> str:
    return f"{text} {unit_title(topic.unit)}".strip()


def _context_text(text: str, topic: Topic) -> str:
    """The topic with its unit, e.g. "Threads, Processes and Scheduling".

    The course subject is deliberately left out: every video in a course matches
    its subject, so adding it makes topics that no video covers look covered.
    """
    parts = [text, unit_title(topic.unit)]
    return ", ".join(dict.fromkeys(p for p in parts if p))


def _unit(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return (matrix / norms).astype(np.float32)


# ------------------------------------------------- exam / notes passages (cached)

_passages: OrderedDict[tuple[int, str], tuple[list[str], np.ndarray]] = OrderedDict()
_passages_lock = threading.Lock()


def _document_passages(document: Document, embedder: Embedder) -> tuple[list[str], np.ndarray]:
    key = (document.id, embedder.name)
    with _passages_lock:
        if key in _passages:
            _passages.move_to_end(key)
            return _passages[key]
    # Notes are cut into short passages: a topic is usually a paragraph or two, and
    # a long passage about several topics matches none of them strongly.
    texts = (
        split_questions(document.text)
        if document.kind == "exam"
        else chunk_paragraphs(document.text, target_words=NOTES_PASSAGE_WORDS)
    )
    value = (texts, embedder.embed_passages(texts))
    with _passages_lock:
        _passages[key] = value
        while len(_passages) > 64:
            _passages.popitem(last=False)
    return value


def _collect(project: Project, kind: str, embedder: Embedder) -> tuple[list[str], np.ndarray]:
    texts: list[str] = []
    vectors: list[np.ndarray] = []
    for document in project.documents:
        if document.kind == kind and document.status == "ready" and document.text.strip():
            doc_texts, doc_vectors = _document_passages(document, embedder)
            if doc_texts:
                texts.extend(doc_texts)
                vectors.append(doc_vectors)
    matrix = np.vstack(vectors) if vectors else np.zeros((0, embedder.dim), dtype=np.float32)
    return texts, matrix


def ensure_topic_vectors(
    db: Session, project: Project, embedder: Embedder, *, force: bool = False
) -> None:
    """Embed topics that need it and refresh their exam/notes signals.

    A topic vector is mostly the topic name, steered slightly by its unit and,
    when the teacher's notes discuss it, by the notes' own wording.
    """
    pending = [
        t for t in project.topics if force or t.embedding is None or t.embedded_with != embedder.name
    ]
    if not pending:
        return

    acronyms = acronym_map(project)
    texts = [query_text(t, acronyms) for t in pending]
    names = embedder.embed_queries(texts)
    contexts = embedder.embed_queries(
        [_context_text(text, t) for text, t in zip(texts, pending, strict=True)]
    )
    vectors = _unit((1 - CONTEXT_WEIGHT) * names + CONTEXT_WEIGHT * contexts)
    lexical = [_lexical_text(text, t) for text, t in zip(texts, pending, strict=True)]

    exam_texts, exam_vectors = _collect(project, "exam", embedder)
    exam_scores = score_passages(embedder, vectors, lexical, exam_vectors, exam_texts)
    notes_texts, notes_vectors = _collect(project, "notes", embedder)
    notes_scores = score_passages(embedder, vectors, lexical, notes_vectors, notes_texts)

    for row, topic in enumerate(pending):
        topic.exam_hits = int((exam_scores[row] >= EXAM_HIT).sum()) if exam_texts else 0
        topic.in_notes, topic.notes_snippet = False, ""
        vector = vectors[row]
        if notes_texts:
            best = int(np.argmax(notes_scores[row]))
            if notes_scores[row, best] >= NOTES_HIT:
                topic.in_notes = True
                topic.notes_snippet = tidy_snippet(notes_texts[best], 320)
                blended = (1 - NOTES_WEIGHT) * vector + NOTES_WEIGHT * notes_vectors[best]
                vector = _unit(blended.reshape(1, -1))[0]
        topic.embedding = to_blob(vector)
        topic.embedded_with = embedder.name

    most = max((t.exam_hits for t in project.topics), default=0)
    for topic in project.topics:
        topic.exam_weight = round(topic.exam_hits / most, 3) if most else 0.0
    db.flush()


# ----------------------------------------------------------------------- feedback


@dataclass
class FeedbackState:
    blocked_pairs: set[tuple[int, int]] = field(default_factory=set)  # (topic, video)
    blocked_videos: set[int] = field(default_factory=set)
    pinned: dict[int, int] = field(default_factory=dict)  # topic -> video


def load_feedback(db: Session, project_id: int) -> FeedbackState:
    state = FeedbackState()
    for item in db.scalars(select(Feedback).where(Feedback.project_id == project_id)):
        if item.kind == "wrong_topic":
            state.blocked_pairs.add((item.topic_id, item.video_id))
        elif item.kind == "irrelevant":
            state.blocked_videos.add(item.video_id)
        elif item.kind == "correct":
            state.pinned[item.topic_id] = item.video_id
    return state


def learn_threshold(
    positives: list[float], negatives: list[float], base: float = DEFAULT_THRESHOLD
) -> float:
    """Pick the relevance threshold that best separates the student's judgements.

    Each rejected video scoring at or above the threshold, and each confirmed
    video scoring below it, costs 1. Moving away from the default costs a little
    too, so a single click nudges the threshold instead of swinging it.
    """
    low, high = base + THRESHOLD_RANGE[0], base + THRESHOLD_RANGE[1]
    options = {base}
    options.update(min(high, max(low, n + 0.01)) for n in negatives)
    options.update(min(high, max(low, p - 0.01)) for p in positives)

    def cost(threshold: float) -> float:
        errors = sum(n >= threshold for n in negatives) + sum(p < threshold for p in positives)
        return errors + 3.0 * abs(threshold - base)

    return round(min(sorted(options, key=lambda t: abs(t - base)), key=cost), 3)


def relearn_threshold(db: Session, project: Project) -> float:
    rows = db.scalars(select(Feedback).where(Feedback.project_id == project.id)).all()
    positives = [f.relevance for f in rows if f.kind == "correct" and f.relevance > 0]
    negatives = [f.relevance for f in rows if f.kind in ("wrong_topic", "irrelevant")]
    project.relevance_threshold = learn_threshold(positives, negatives)
    return project.relevance_threshold


# ------------------------------------------------------------------ second stage

_TITLE_STOP = frozenset(
    ["the", "and", "for", "with", "from", "into", "about", "what", "how", "why", "introduction", "intro", "part", "lecture", "lec", "chapter", "unit", "video", "tutorial", "explained", "explanation", "basics", "basic", "concept", "concepts", "example", "examples", "solved", "problem", "problems", "full", "course", "complete", "operating", "algorithm", "algorithms", "method", "methods", "technique", "techniques"]
)


_PRACTICE_TITLE = re.compile(
    r"\b(solved|problems?|numericals?|examples?|practice|questions?|pyqs?|quiz|exercise|"
    r"gate\s+\d{4}|previous\s+year)\b",
    re.IGNORECASE,
)


def _stem(word: str) -> str:
    """Crude stem: drop a plural ending, then keep the first six letters, so
    "states"/"State" and "scheduling"/"scheduler" compare equal."""
    if len(word) > 4 and word.endswith("es") and not word.endswith("ses"):
        word = word[:-2] if word.endswith(("ches", "shes", "xes")) else word[:-1]
    elif len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        word = word[:-1]
    return word[:6]


def _title_tokens(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return {_stem(w) for w in words if len(w) >= 3 and w not in _TITLE_STOP}


def title_affinity(topic_name: str, video_title: str) -> float:
    """How closely a video title names the topic (0..1, Jaccard over word stems)."""
    topic, title = _title_tokens(topic_name), _title_tokens(video_title)
    if not topic or not title:
        return 0.0
    return len(topic & title) / len(topic | title)


def rerank_relevance(
    db: Session | None,
    project_id: int,
    index: ProjectIndex,
    queries: list[tuple[int | None, str]],
    scores: np.ndarray,
    relevance: np.ndarray,
    must_include: dict[int, set[int]] | None = None,
) -> np.ndarray:
    """Re-score each query's best videos with the cross-encoder.

    For every query the top videos by embedding relevance are shortlisted, and the
    cross-encoder reads the query against each one's title/description chunk and
    best transcript chunks. The cross-encoder score becomes the relevance, trimmed
    slightly when the embedding stage was lukewarm: on labelled real pairs it
    separates true matches from look-alikes far better than the embeddings do, so
    it leads and the embeddings only shortlist. Videos outside the shortlist score
    0. Scores are cached per (topic, chunk) when a session and topic ids are given.

    Returns the input relevance unchanged when no reranker is configured.
    """
    reranker = get_reranker()
    if reranker is None:
        return relevance

    cache: dict[tuple[int, int], RerankScore] = {}
    if db is not None:
        cache = {
            (row.topic_id, row.chunk_id): row
            for row in db.scalars(select(RerankScore).where(RerankScore.project_id == project_id))
        }

    out = np.zeros_like(relevance)
    for row, (topic_id, text) in enumerate(queries):
        order = np.argsort(-relevance[row])[:SHORTLIST_SIZE]
        columns = [int(c) for c in order if relevance[row, c] >= SHORTLIST_FLOOR]
        for column in (must_include or {}).get(row, ()):
            if column not in columns:
                columns.append(column)
        if not columns:
            continue

        # The chunks to read for each shortlisted video: its meta chunk, and its
        # best few transcript chunks according to the first stage. Reading only
        # the single best chunk wrongly rejected real matches; three is where
        # accuracy levels off (see evaluation/rerank_study.py).
        chunk_rows: list[list[int]] = []
        for column in columns:
            start, end = index.spans[column]
            rows = [start]
            if end - start > 1:
                best = np.argsort(-scores[row, start + 1 : end])[:RERANK_PASSAGES]
                rows.extend(start + 1 + int(offset) for offset in best)
            chunk_rows.append(rows)

        digest = query_hash(text)
        known: dict[int, float] = {}
        missing: list[int] = []
        for chunk_row in dict.fromkeys(r for rows in chunk_rows for r in rows):
            cached = cache.get((topic_id, index.chunk_ids[chunk_row])) if topic_id else None
            if cached and cached.query_hash == digest and cached.model == reranker.name:
                known[chunk_row] = cached.score
            else:
                missing.append(chunk_row)
        if missing:
            fresh = reranker.raw_scores(text, [index.texts[r] for r in missing])
            for chunk_row, value in zip(missing, fresh, strict=True):
                known[chunk_row] = value
                if db is None or topic_id is None:
                    continue
                key = (topic_id, index.chunk_ids[chunk_row])
                cached = cache.get(key)
                if cached is None:
                    cached = RerankScore(project_id=project_id, topic_id=topic_id, chunk_id=key[1])
                    db.add(cached)
                    cache[key] = cached
                cached.query_hash, cached.model, cached.score = digest, reranker.name, value

        for column, rows in zip(columns, chunk_rows, strict=True):
            first = float(relevance[row, column])
            if not index.videos[column].english:
                # The cross-encoder only reads English; a transcript in another
                # language keeps its (multilingual) embedding relevance.
                out[row, column] = first
                continue
            second = reranker.calibrate(max(known[r] for r in rows))
            out[row, column] = second * (1.0 - FIRST_STAGE_WEIGHT * (1.0 - first))
    return out


_KEY_STOP = frozenset(
    ["and", "the", "for", "with", "from", "into", "about", "over", "under", "than", "then", "that", "this", "those", "these", "what", "when", "where", "which", "their", "there", "have", "been", "were", "will", "would", "could", "should", "also", "each", "such", "using", "used", "other", "more", "most", "some", "many", "much", "very", "only", "just"]
)


def _key_words(text: str) -> list[str]:
    words = re.findall(r"[a-z][a-z0-9]{2,}", text.lower())
    return [w for w in dict.fromkeys(words) if w not in _KEY_STOP and w not in _TITLE_STOP]


def apply_key_terms(index: ProjectIndex, queries: list[str], relevance: np.ndarray) -> np.ndarray:
    """Lower the relevance of videos that never mention a topic's distinctive words.

    Meaning-based matching can rate "disk scheduling" close to a lecture on CPU
    scheduling; if the word "disk" appears nowhere in that video, it is not the
    lecture to recommend. Relevance drops in proportion to the share of the
    topic's words that are missing (prefix match, so plurals count).
    """
    adjusted = relevance.copy()
    vocabulary: dict[int, str] = {}
    for row, query in enumerate(queries):
        words = _key_words(query)
        if not words:
            continue
        for column in np.flatnonzero(relevance[row] > 0):
            column = int(column)
            if column not in vocabulary:
                start, end = index.spans[column]
                vocabulary[column] = " ".join(index.texts[start:end]).lower()
            text = vocabulary[column]
            missing = sum(1 for w in words if w not in text)
            if missing:
                adjusted[row, column] *= 1.0 - KEY_TERM_WEIGHT * missing / len(words)
    return adjusted


_NUMBER_WORDS = "one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen"
_OUTLINE_REFERENCE = re.compile(
    rf"\b(?:chapter|unit|module|lecture|section)\s+(?:number\s+)?(?:\d+|{_NUMBER_WORDS})\b"
    r"|\b(?:first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|\d+(?:st|nd|rd|th))"
    r"\s+(?:chapter|unit|module)\b",
    re.IGNORECASE,
)


def is_outline(text: str) -> bool:
    """A passage that walks through the course contents ("in chapter 7 we will
    see normalization, in chapter 8 storage ..."). It names many topics and
    teaches none of them."""
    return len(_OUTLINE_REFERENCE.findall(text)) >= OUTLINE_REFERENCES


def _phrase_pattern(text: str) -> re.Pattern | None:
    """Matches the topic's words in order, whatever their endings: "functional
    dependencies" also finds "functional dependency"."""
    words = _key_words(text)
    if not words:
        return None
    return re.compile(r"\W+".join(rf"\b{re.escape(_stem(w))}\w*" for w in words))


def apply_transcript_evidence(
    index: ProjectIndex, queries: list[str], relevance: np.ndarray
) -> np.ndarray:
    """Correct the relevance with what the transcript literally says.

    * A video that names the topic only while listing the course contents does
      not teach it: its relevance is cut, so the topic stays a gap instead of
      pointing at a syllabus read-out.
    * A video that names a topic of two or more words in two passages in a row
      (over a minute of the lecture) is discussing it, whatever the video is
      called. The reranker
      scores one long passage at a time and can underrate a topic taught as part
      of a broader lecture ("data independence" inside "View of Data"), so such
      a video gets at least ``NAMED_FLOOR``.

    Only the spoken words are used here, never the title.
    """
    adjusted = relevance.copy()
    lowered: dict[int, str] = {}
    outline: dict[int, bool] = {}
    for row, query in enumerate(queries):
        pattern = _phrase_pattern(query)
        if pattern is None:
            continue
        several_words = len(_key_words(query)) >= 2
        # Every video is looked at, including those the reranker scored 0: it is
        # exactly the underrated ones that the second rule is for.
        for column, (start, end) in enumerate(index.spans):
            listing = 0
            teaching: list[int] = []
            for chunk in range(start + 1, end):  # transcript passages; start is the title
                if chunk not in lowered:
                    lowered[chunk] = index.texts[chunk].lower()
                if not pattern.search(lowered[chunk]):
                    continue
                if chunk not in outline:
                    outline[chunk] = is_outline(lowered[chunk])
                if outline[chunk]:
                    listing += 1
                else:
                    teaching.append(chunk)
            if listing and not teaching:
                adjusted[row, column] *= OUTLINE_PENALTY
            elif several_words and any(b - a == 1 for a, b in pairwise(teaching)):
                # Named in two passages in a row: the lecture stays on the topic.
                # (Scattered mentions are not enough: an overview of operating
                # system structures says "virtual memory" three times in passing.)
                adjusted[row, column] = max(adjusted[row, column], NAMED_FLOOR)
    return adjusted


def _rank_score(
    text: str,
    index: ProjectIndex,
    relevance: np.ndarray,
    quality: list[float],
    row: int,
    column: int,
) -> float:
    base = final_score(float(relevance[row, column]), quality[column])
    title = index.videos[column].title
    score = base + TITLE_BONUS * title_affinity(text, title)
    # Between equally relevant videos, teach the concept before the worked problems.
    if _PRACTICE_TITLE.search(title) and not _PRACTICE_TITLE.search(text):
        score -= PRACTICE_PENALTY
    return score


# ------------------------------------------------------------------ segments

ASPECT_MATCH = 0.6  # a notes passage or past question this close to a topic is one of its parts
ASPECT_HIT = 0.5  # a stretch covers a part when one of its chunks is this close (calibrated)
MAX_ASPECTS = 4
MAX_SEGMENTS = 4
SERIES_FLOOR = 0.3  # first-stage relevance a series fragment needs
REPEAT_MIN_CHUNKS = 2  # a second stretch in the same video must be this long (not a recap)
DUPLICATE = 0.95  # stretches this similar teach the same thing; the second is an alternate
_PART_MARKER = re.compile(
    r"\b(?:part|pt\.?|section)\s*[-:#]?\s*(?:\d+|[ivx]+|one|two|three|four)\b|\(\s*\d+\s*\)\s*$"
    r"|\b(?:continued|contd)\b",
    re.IGNORECASE,
)


@dataclass
class Aspect:
    label: str
    vector: np.ndarray


def _key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def topic_aspects(
    project: Project,
    embedder: Embedder,
    topics: list[Topic],
    texts: dict[int, str],
    vectors: np.ndarray,
) -> list[list[Aspect]]:
    """The parts each topic should cover: its "X and Y" halves, and the past
    questions and notes passages most clearly about it."""
    aspects: list[list[Aspect]] = [[] for _ in topics]
    names = {_key(t.name) for t in topics}
    halves = [[part for part in and_parts(t.name) if _key(part) not in names] for t in topics]
    flat = [part for parts in halves for part in parts]
    if flat:
        embedded = iter(embedder.embed_queries(flat))
        for row, parts in enumerate(halves):
            aspects[row] = [Aspect(part, next(embedded)) for part in parts]
    lexical = [_lexical_text(texts[t.id], t) for t in topics]
    for kind in ("exam", "notes"):
        passages, passage_vectors = _collect(project, kind, embedder)
        if not passages:
            continue
        scores = score_passages(embedder, vectors, lexical, passage_vectors, passages)
        for row in range(len(topics)):
            for i in np.argsort(-scores[row])[:2]:
                if scores[row, i] >= ASPECT_MATCH and len(aspects[row]) < MAX_ASPECTS:
                    aspects[row].append(Aspect(tidy_snippet(passages[i], 70), passage_vectors[i]))
    return aspects


def _series_stem(title: str) -> str | None:
    if not _PART_MARKER.search(title):
        return None
    return _key(_PART_MARKER.sub(" ", title))


def _whole_rows(index: ProjectIndex, column: int) -> tuple[int, int]:
    start, end = index.spans[column]
    return (start + 1, end - 1) if end - start > 1 else (start, start)


def _mean(index: ProjectIndex, rows: tuple[int, int]) -> np.ndarray:
    vector = index.matrix[rows[0] : rows[1] + 1].mean(axis=0)
    return vector / (np.linalg.norm(vector) + 1e-9)


def plan_segments(
    index: ProjectIndex,
    embedder: Embedder,
    row: int,
    column: int,
    primary_rows: tuple[int, int],
    chunk_scores: np.ndarray,
    relevance: np.ndarray,
    first_stage: np.ndarray,
    threshold: float,
    aspects: list[Aspect],
    blocked: set[int],
) -> tuple[list[dict], list[str]]:
    """Every stretch of video needed to cover a topic, in watching order.

    Starts from the chosen stretch and adds, MAX_SEGMENTS in all at most:
    the other parts of a "Part 1 / Part 2" series around the chosen video; a
    second substantial stretch where the same video teaches the topic again; and
    the fewest stretches from any playlist that cover the parts (halves, past
    questions, notes passages) still missing. Returns the segments and the
    labels of parts no video covers.
    """
    low, high = embedder.calibration

    def covered_by(rows: tuple[int, int]) -> set[int]:
        block = index.matrix[rows[0] : rows[1] + 1]
        return {
            i
            for i, aspect in enumerate(aspects)
            if (float((block @ aspect.vector).max()) - low) / (high - low) >= ASPECT_HIT
        }

    primary = index.videos[column]
    # (column, rows, whole video?, parts it adds)
    plan: list[tuple[int, tuple[int, int], bool, list[str]]] = [(column, primary_rows, False, [])]
    covered = covered_by(primary_rows)

    # A topic split across a "Part 1 / Part 2" series: take the series in order.
    stem = _series_stem(primary.title)
    if stem and primary.playlist_id is not None:
        by_place = {(v.playlist_id, v.playlist_position): c for c, v in enumerate(index.videos)}
        series = [column]
        for step in (-1, 1):
            position = primary.playlist_position + step
            while len(series) < MAX_SEGMENTS and (primary.playlist_id, position) in by_place:
                c = by_place[(primary.playlist_id, position)]
                other = index.videos[c]
                if (
                    _series_stem(other.title) != stem
                    or not other.has_transcript
                    or other.id in blocked
                    or first_stage[row, c] < SERIES_FLOOR
                ):
                    break
                series.append(c)
                position += step
        if len(series) > 1:
            series.sort(key=lambda c: index.videos[c].playlist_position)
            plan = [(c, _whole_rows(index, c), True, []) for c in series]
            for c in series:
                covered |= covered_by(_whole_rows(index, c))

    # The same video teaching the topic again, away from the chosen stretch.
    if len(plan) == 1:
        for rows in other_runs(index, column, chunk_scores, primary_rows):
            if rows[1] - rows[0] + 1 >= REPEAT_MIN_CHUNKS and len(plan) < MAX_SEGMENTS:
                plan.append((column, rows, False, []))
                covered |= covered_by(rows)

    # Parts still missing: the fewest stretches, from any playlist, that cover them.
    uncovered = set(range(len(aspects))) - covered
    used = {item[0] for item in plan}
    candidates: list[tuple[int, tuple[int, int], set[int]]] = []
    if uncovered:
        for c in np.flatnonzero(relevance[row] >= threshold):
            c = int(c)
            video = index.videos[c]
            if c in used or video.id in blocked or not video.has_transcript or video.short:
                continue
            match = locate(index, c, chunk_scores, float(relevance[row, c]))
            rows = (match.first_row, match.last_row)
            candidates.append((c, rows, covered_by(rows)))
    while uncovered and len(plan) < MAX_SEGMENTS and candidates:
        best = max(
            candidates,
            key=lambda item: (
                len(item[2] & uncovered),
                index.videos[item[0]].playlist_id == primary.playlist_id,
                float(relevance[row, item[0]]),
            ),
        )
        gained = best[2] & uncovered
        if not gained:
            break
        candidates.remove(best)
        if any(float(_mean(index, best[1]) @ _mean(index, r)) >= DUPLICATE for _, r, _, _ in plan):
            continue  # the same material again: an alternate, not a missing part
        plan.append((best[0], best[1], False, [aspects[i].label for i in sorted(gained)]))
        uncovered -= gained

    # Watching order: a series as is; otherwise the chosen video's stretches by
    # time, then the stretches from other videos.
    if not plan[0][2]:
        own = sorted((item for item in plan if item[0] == column), key=lambda item: item[1][0])
        plan = own + [item for item in plan if item[0] != column]
    segments = []
    for c, rows, whole, covers in plan:
        start_s, end_s = (0.0, 0.0) if whole else stretch_seconds(index, c, *rows)
        segments.append(
            {"video_id": index.videos[c].id, "start_s": start_s, "end_s": end_s, "covers": covers}
        )
    return segments, [aspects[i].label for i in sorted(uncovered)]


# ---------------------------------------------------------------- recommendations


def _stretch_vector(index: ProjectIndex, column: int, chunk_scores: np.ndarray):
    """Embedding of the chunk that best teaches the topic in this video."""
    start, end = index.spans[column]
    if end - start <= 1:
        return index.matrix[start]
    return index.matrix[start + 1 + int(np.argmax(chunk_scores[start + 1 : end]))]


@dataclass
class PlaylistOrder:
    order: list[int]  # topic ids in the order the playlists teach them
    transitions: list[tuple[str, str, int]]  # (topic, next topic, times seen)


def playlist_topic_order(db: Session, project: Project) -> PlaylistOrder:
    """The topic order the student's playlists follow, mined from the videos.

    Each video is labelled with the topic it teaches best; walking every playlist
    in its own order then gives "topic Y follows topic X" transitions, as in
    sequential-pattern mining over a teacher's curriculum. Topics are ordered by
    where they first appear in the student's playlists (earlier playlists first);
    topics no video teaches keep their place after the topic before them.
    """
    embedder = get_embedder()
    ensure_topic_vectors(db, project, embedder)
    topics = list(project.topics)
    index = get_index(db, project.id, embedder)
    if not topics or index.empty:
        return PlaylistOrder([t.id for t in topics], [])
    acronyms = acronym_map(project)
    texts = [query_text(t, acronyms) for t in topics]
    scores = hybrid_scores(
        embedder,
        np.vstack([from_blob(t.embedding) for t in topics]),
        [_lexical_text(text, t) for text, t in zip(texts, topics, strict=True)],
        index.matrix,
        index.vectorizer,
        index.tfidf,
    )
    relevance = video_relevance(index, scores)
    rank = {p.id: r for r, p in enumerate(project.playlists)}
    threshold = project.relevance_threshold

    # Where each topic is first taught: (playlist rank, position in that playlist).
    first_seen: dict[int, tuple[int, int]] = {}
    for row, topic in enumerate(topics):
        hits = [
            (rank.get(index.videos[c].playlist_id, len(rank)), index.videos[c].playlist_position)
            for c in np.flatnonzero(relevance[row] >= threshold)
        ]
        if hits:
            first_seen[topic.id] = min(hits)

    # Transitions along each playlist, between the topics videos teach best.
    counts: dict[tuple[int, int], int] = {}
    by_playlist: dict[object, list[tuple[int, int]]] = {}
    for column, video in enumerate(index.videos):
        best = int(np.argmax(relevance[:, column]))
        if relevance[best, column] >= threshold and video.playlist_id is not None:
            by_playlist.setdefault(video.playlist_id, []).append((video.playlist_position, best))
    for sequence in by_playlist.values():
        sequence.sort()
        for (_, a), (_, b) in zip(sequence, sequence[1:], strict=False):
            if a != b:
                counts[(a, b)] = counts.get((a, b), 0) + 1
    transitions = sorted(
        ((topics[a].name, topics[b].name, n) for (a, b), n in counts.items()),
        key=lambda item: -item[2],
    )

    # Sort taught topics by first appearance; untaught ones follow their predecessor.
    order: list[int] = []
    taught = sorted(first_seen, key=lambda tid: (first_seen[tid], [t.id for t in topics].index(tid)))
    order = list(taught)
    for position, topic in enumerate(topics):
        if topic.id in first_seen:
            continue
        previous = next((t.id for t in reversed(topics[:position]) if t.id in order), None)
        order.insert(order.index(previous) + 1 if previous is not None else 0, topic.id)
    return PlaylistOrder(order, transitions[:20])


def _age_years(published) -> float | None:
    if published is None:
        return None
    from datetime import UTC, datetime

    if published.tzinfo is None:  # SQLite returns naive datetimes
        published = published.replace(tzinfo=UTC)
    return max(0.0, (datetime.now(UTC) - published).days / 365.25)


def _reasons(match: Match, has_transcript: bool) -> list[str]:
    if not has_transcript:
        return ["No captions on this video, so it was matched on its title and description"]
    if match.via == "title":
        return ["The title and description match this topic"]
    minutes = match.coverage_s / 60
    if minutes >= 1.5:
        return [f"Spends about {round(minutes)} min on this topic"]
    return ["Covers this topic in the transcript"]


def rebuild_recommendations(db: Session, project: Project) -> dict[str, int]:
    """Recompute every recommendation for a project. Fast (in-memory maths only),
    so it runs inline after feedback or topic edits."""
    embedder = get_embedder()
    ensure_topic_vectors(db, project, embedder)
    topics = list(project.topics)
    db.execute(delete(Recommendation).where(Recommendation.project_id == project.id))
    index = get_index(db, project.id, embedder)
    stats = {"topics": len(topics), "matched": 0, "gaps": 0, "covered": 0}
    if not topics or index.empty:
        stats["covered"] = sum(t.covered for t in topics)
        stats["gaps"] = len(topics) - stats["covered"]
        db.flush()
        return stats

    vectors = np.vstack([from_blob(t.embedding) for t in topics])
    acronyms = acronym_map(project)
    texts = {t.id: query_text(t, acronyms) for t in topics}
    scores = hybrid_scores(
        embedder,
        vectors,
        [_lexical_text(texts[t.id], t) for t in topics],
        index.matrix,
        index.vectorizer,
        index.tfidf,
    )
    feedback = load_feedback(db, project.id)
    column_of = {video.id: column for column, video in enumerate(index.videos)}
    pinned_columns = {
        row: {column_of[feedback.pinned[topic.id]]}
        for row, topic in enumerate(topics)
        if feedback.pinned.get(topic.id) in column_of
    }
    relevance = rerank_relevance(
        db,
        project.id,
        index,
        [(t.id, texts[t.id]) for t in topics],
        scores,
        video_relevance(index, scores),
        pinned_columns,
    )
    relevance = apply_key_terms(index, [texts[t.id] for t in topics], relevance)
    relevance = apply_transcript_evidence(index, [texts[t.id] for t in topics], relevance)

    def naming_tokens(text: str) -> list[set[str]]:
        """Ways a title can name a topic: its full wording, or for "Head: item" just
        the item. Bracketed abbreviations such as "(PCB)" are optional."""
        plain = re.sub(r"\([^)]*\)", " ", text)
        forms = [_title_tokens(plain)]
        if ": " in plain:
            forms.append(_title_tokens(plain.split(": ", 1)[1]))
        return [f for f in forms if f]

    tokens = {t.id: naming_tokens(texts[t.id]) for t in topics}

    def dedicated_to(topic_id: int, title: str) -> bool:
        """The title names this topic and no other (parent or child topics aside)."""
        named = _title_tokens(title)
        mine = next((form for form in tokens[topic_id] if form <= named), None)
        if mine is None:
            return False
        return not any(
            other <= named and not (other <= mine or mine <= other)
            for tid, forms in tokens.items()
            if tid != topic_id
            for other in forms[:1]  # another topic's full wording
        )
    threshold = project.relevance_threshold
    playlist_rank = {playlist.id: rank for rank, playlist in enumerate(project.playlists)}
    quality = [
        quality_score(
            QualityInputs(
                v.duration_s,
                v.view_count,
                v.like_count,
                v.has_transcript,
                age_years=_age_years(v.published_at),
                comment_count=v.comment_count,
                comment_sentiment=v.comment_sentiment,
            )
        )
        for v in index.videos
    ]

    options: list[list[tuple[Candidate, int]]] = []
    for row, topic in enumerate(topics):
        if topic.covered:
            options.append([])
            continue
        ranked = sorted(
            (
                (_rank_score(texts[topic.id], index, relevance, quality, row, int(column)), int(column))
                for column in np.flatnonzero(relevance[row] >= threshold)
                if index.videos[column].id not in feedback.blocked_videos
                and (topic.id, index.videos[column].id) not in feedback.blocked_pairs
                and not index.videos[column].short  # short clips only continue a series
            ),
            reverse=True,
        )[:CANDIDATES_PER_TOPIC]
        pinned_video = feedback.pinned.get(topic.id)
        pinned_column = column_of.get(pinned_video) if pinned_video is not None else None
        if pinned_column is not None and all(column != pinned_column for _, column in ranked):
            score = _rank_score(texts[topic.id], index, relevance, quality, row, pinned_column)
            ranked.insert(0, (score, pinned_column))
        entries = []
        for score, column in ranked:
            video = index.videos[column]
            entries.append(
                (
                    Candidate(
                        video_id=video.id,
                        score=score,
                        playlist_id=video.playlist_id,
                        playlist_rank=playlist_rank.get(video.playlist_id, len(playlist_rank)),
                        playlist_position=video.playlist_position,
                        channel=video.channel,
                        pinned=video.id == pinned_video,
                        vector=_stretch_vector(index, column, scores[row]),
                    ),
                    column,
                )
            )
        options.append(entries)

    chosen = choose_path([[candidate for candidate, _ in entries] for entries in options])

    first_stage = video_relevance(index, scores)
    aspect_lists = topic_aspects(project, embedder, topics, texts, vectors)
    previous: Candidate | None = None
    for row, topic in enumerate(topics):
        entries = options[row]
        pick = chosen[row]
        if topic.covered:
            stats["covered"] += 1
            continue
        if pick is None:
            stats["gaps"] += 1
            continue
        stats["matched"] += 1
        ordered = [entries[pick]] + [e for i, e in enumerate(entries) if i != pick]
        for rank, (candidate, column) in enumerate(ordered[: MAX_ALTERNATES + 1]):
            video = index.videos[column]
            match = locate(index, column, scores[row], float(relevance[row, column]))
            if dedicated_to(topic.id, video.title):
                # The video is about this topic: study all of it.
                match.start_s, match.end_s = 0.0, 0.0
            segments: list[dict] = []
            uncovered: list[str] = []
            if rank == 0:
                rows = (match.first_row, match.last_row)
                if match.start_s == 0 and match.end_s == 0:
                    rows = _whole_rows(index, column)
                segments, uncovered = plan_segments(
                    index, embedder, row, column, rows, scores[row], relevance,
                    first_stage, threshold, aspect_lists[row], feedback.blocked_videos,
                )
                if len(segments) > 1 and segments[0]["video_id"] == video.id:
                    match.start_s = segments[0]["start_s"]
                    match.end_s = segments[0]["end_s"]
            reasons = _reasons(match, video.has_transcript)
            if len(segments) > 1:
                used = len({s["video_id"] for s in segments})
                across = f" across {used} videos" if used > 1 else ""
                reasons.insert(0, f"Taught in {len(segments)} parts{across}")
            if candidate.pinned:
                reasons.insert(0, "You confirmed this video for the topic")
            if rank == 0 and previous is not None:
                if previous.video_id == candidate.video_id:
                    reasons.append("Continues the video you are already watching")
                elif previous.playlist_id is not None and previous.playlist_id == candidate.playlist_id:
                    reasons.append("Keeps you in the same playlist")
            elif rank > 0 and candidate.playlist_id != ordered[0][0].playlist_id:
                reasons.append("A different perspective from another playlist")
            db.add(
                Recommendation(
                    project_id=project.id,
                    topic_id=topic.id,
                    video_id=video.id,
                    rank=rank,
                    relevance=round(match.relevance, 4),
                    quality=round(quality[column], 4),
                    score=round(candidate.score, 4),
                    start_s=match.start_s,
                    end_s=match.end_s,
                    coverage_s=match.coverage_s,
                    snippet=match.snippet,
                    reasons=reasons,
                    segments=segments if len(segments) > 1 else [],
                    uncovered=uncovered,
                )
            )
        previous = entries[pick][0]
    db.flush()
    return stats


# ------------------------------------------------------------------------- search


@dataclass
class SearchOutcome:
    found: bool
    matches: list[Match]
    closest: list[Match]  # weak matches shown only when nothing clears the threshold


def _sequence(index: ProjectIndex, matches: list[Match]) -> list[Match]:
    """Order results for watching: best playlist first, playlist order within it."""
    info = {video.id: video for video in index.videos}
    best_in_group: dict[object, float] = {}
    for match in matches:
        group = info[match.video_id].playlist_id or f"v{match.video_id}"
        best_in_group[group] = max(best_in_group.get(group, 0.0), match.relevance)

    def key(match: Match):
        video = info[match.video_id]
        group = video.playlist_id or f"v{match.video_id}"
        return (-best_in_group[group], str(group), video.playlist_position)

    return sorted(matches, key=key)


def search_project(db: Session, project: Project, query: str, limit: int = 8) -> SearchOutcome:
    embedder = get_embedder()
    index = get_index(db, project.id, embedder)
    if index.empty:
        return SearchOutcome(found=False, matches=[], closest=[])
    scores = hybrid_scores(
        embedder,
        embedder.embed_queries([query]),
        [query],
        index.matrix,
        index.vectorizer,
        index.tfidf,
    )
    relevance = rerank_relevance(
        None, project.id, index, [(None, query)], scores, video_relevance(index, scores)
    )[0]
    blocked = load_feedback(db, project.id).blocked_videos
    order = [int(c) for c in np.argsort(-relevance) if index.videos[int(c)].id not in blocked]

    matches = [
        locate(index, column, scores[0], float(relevance[column]))
        for column in order
        if relevance[column] >= project.relevance_threshold
    ][:limit]
    if matches:
        return SearchOutcome(found=True, matches=_sequence(index, matches), closest=[])
    closest = [
        locate(index, column, scores[0], float(relevance[column]))
        for column in order[:3]
        if relevance[column] >= CLOSEST_FLOOR
    ]
    return SearchOutcome(found=False, matches=[], closest=closest)
