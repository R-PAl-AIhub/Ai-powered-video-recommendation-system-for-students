"""Turn uploaded files (PDF, DOCX, text, images) into plain text.

PDF pages with a text layer are read directly; pages without one (scans) are
rendered and sent through OCR.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

from .ocr import get_ocr

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
TEXT_EXTENSIONS = {".txt", ".md", ".text"}
ALLOWED_EXTENSIONS = {".pdf", ".docx", *IMAGE_EXTENSIONS, *TEXT_EXTENSIONS}

MAX_PDF_PAGES = 300
MIN_PAGE_TEXT = 40  # fewer characters than this on a page => treat it as a scan
MAX_TEXT_CHARS = 1_500_000


class DocumentError(Exception):
    """The file could not be read; the message is safe to show to the student."""


@dataclass
class Unit:
    """A piece of a document as it was laid out: a PDF page, or a section under a
    heading. Study material is cut into passages along these, so a passage can
    say which page it is on."""

    text: str
    page: int = 0  # 1-based PDF page; 0 = the format has no pages
    page_label: str = ""  # the number printed on the page, when the PDF defines one
    heading: str = ""


@dataclass
class Extracted:
    text: str
    page_count: int = 1
    ocr_pages: int = 0
    warnings: list[str] = field(default_factory=list)
    units: list[Unit] = field(default_factory=list)


def sniff_kind(data: bytes, filename: str) -> str:
    """Decide the real file type from its leading bytes, not just its name."""
    ext = Path(filename).suffix.lower()
    if data.startswith(b"%PDF-"):
        return "pdf"
    if data.startswith(b"PK\x03\x04") and ext == ".docx":
        return "docx"
    if (
        data.startswith(b"\x89PNG")
        or data.startswith(b"\xff\xd8\xff")
        or data[:4] in (b"II*\x00", b"MM\x00*")
        or data.startswith(b"BM")
        or (data.startswith(b"RIFF") and data[8:12] == b"WEBP")
    ):
        return "image"
    if ext in TEXT_EXTENSIONS and (
        # UTF-16 text (Windows Notepad's "Unicode") is full of zero bytes; its
        # byte-order mark tells it apart from a binary file.
        data[:2] in (b"\xff\xfe", b"\xfe\xff") or b"\x00" not in data[:4096]
    ):
        return "text"
    raise DocumentError(
        "Unsupported file. Upload a PDF, a Word document (.docx), a text file, "
        "or a photo/scan (PNG, JPG, WEBP, TIFF)."
    )


def clean_text(text: str) -> str:
    """Light cleanup shared by every extractor."""
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    text = text.replace("­", "")  # soft hyphen
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)  # re-join words hyphenated at line ends
    text = re.sub(r"[ \t ]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()[:MAX_TEXT_CHARS]


_WORD = re.compile(r"[A-Za-z][A-Za-z'-]*")


def spell_correct(text: str, vocabulary: dict[str, int]) -> tuple[str, int]:
    """Fix OCR misreadings against the course's own vocabulary.

    A word is changed only when it is unknown, at least five letters long, and
    one known word (seen at least twice) is a clear close match, so subject terms
    are never "corrected" into ordinary English. Returns the text and how many
    words were changed.
    """
    import difflib

    known = [w for w, n in vocabulary.items() if n >= 2 and len(w) >= 4]
    by_length: dict[int, list[str]] = {}
    for word in known:
        by_length.setdefault(len(word), []).append(word)
    cache: dict[str, str | None] = {}
    changed = 0

    def fix(match: re.Match) -> str:
        nonlocal changed
        word = match.group(0)
        lower = word.lower()
        if len(lower) < 5 or lower in vocabulary:
            return word
        if lower not in cache:
            pool = [w for n in range(len(lower) - 1, len(lower) + 2) for w in by_length.get(n, [])]
            close = difflib.get_close_matches(lower, pool, n=2, cutoff=0.84)
            # Ambiguous (two equally good candidates) or nothing close: leave it.
            if len(close) == 1 or (
                len(close) == 2
                and difflib.SequenceMatcher(None, lower, close[0]).ratio()
                > difflib.SequenceMatcher(None, lower, close[1]).ratio() + 0.04
            ):
                cache[lower] = close[0]
            else:
                cache[lower] = None
        replacement = cache[lower]
        if replacement is None:
            return word
        changed += 1
        if word.isupper():
            return replacement.upper()
        if word[:1].isupper():
            return replacement.capitalize()
        return replacement

    return _WORD.sub(fix, text), changed


def vocabulary_of(texts: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for text in texts:
        for word in _WORD.findall(text):
            lower = word.lower()
            counts[lower] = counts.get(lower, 0) + 1
    return counts


def _ocr_image(image: Image.Image, result: Extracted, label: str) -> str:
    engine = get_ocr()
    if engine is None:
        result.warnings.append(
            f"{label} looks like a scan, but no OCR engine is available on this server."
        )
        return ""
    result.ocr_pages += 1
    return engine.read(image)


def _extract_pdf(data: bytes) -> Extracted:
    import pypdfium2 as pdfium

    try:
        pdf = pdfium.PdfDocument(data)
    except Exception as exc:
        raise DocumentError("This PDF could not be opened (it may be corrupt or encrypted).") from exc

    result = Extracted(text="", page_count=len(pdf))
    parts: list[str] = []
    try:
        headings = _pdf_outline(pdf)
        current_heading = ""
        for number in range(min(len(pdf), MAX_PDF_PAGES)):
            current_heading = headings.get(number, current_heading)
            page = pdf[number]
            textpage = page.get_textpage()
            text = textpage.get_text_range() or ""
            textpage.close()
            if len(text.strip()) < MIN_PAGE_TEXT:
                bitmap = page.render(scale=2.0)
                image = bitmap.to_pil()
                bitmap.close()
                ocr_text = _ocr_image(image, result, f"Page {number + 1}")
                if len(ocr_text.strip()) > len(text.strip()):
                    text = ocr_text
            page.close()
            parts.append(text)
            try:
                label = (pdf.get_page_label(number) or "").strip()[:40]
            except Exception:
                label = ""
            result.units.append(
                Unit(
                    text=clean_text(text),
                    page=number + 1,
                    page_label=label if label != str(number + 1) else "",
                    heading=current_heading,
                )
            )
        if len(pdf) > MAX_PDF_PAGES:
            result.warnings.append(f"Only the first {MAX_PDF_PAGES} pages were read.")
    finally:
        pdf.close()
    result.text = clean_text("\n\n".join(parts))
    return result


def _pdf_outline(pdf) -> dict[int, str]:
    """The deepest bookmark title starting on each page (0-based), from the PDF's
    table of contents. Empty when the PDF has none."""
    found: dict[int, tuple[int, str]] = {}
    try:
        for bookmark in pdf.get_toc(max_depth=4):
            dest = bookmark.get_dest()
            index = dest.get_index() if dest is not None else None
            title = " ".join((bookmark.get_title() or "").split())[:300]
            if index is None or index < 0 or not title:
                continue
            level = getattr(bookmark, "level", 0)
            if index not in found or level >= found[index][0]:
                found[index] = (level, title)
    except Exception:  # a damaged outline is not worth failing the document for
        return {}
    return {index: title for index, (_, title) in found.items()}


def _extract_docx(data: bytes) -> Extracted:
    import docx

    try:
        document = docx.Document(io.BytesIO(data))
    except Exception as exc:
        raise DocumentError("This Word document could not be opened.") from exc
    parts = [p.text for p in document.paragraphs]
    # Sections follow Word's own heading styles ("Heading 1", "Title", ...).
    units: list[Unit] = []
    heading, body = "", []
    for paragraph in document.paragraphs:
        style = (paragraph.style.name if paragraph.style is not None else "").lower()
        if (style.startswith("heading") or style == "title") and paragraph.text.strip():
            if body:
                units.append(Unit(text=clean_text("\n".join(body)), heading=heading))
            heading, body = " ".join(paragraph.text.split())[:300], []
        else:
            body.append(paragraph.text)
    if body:
        units.append(Unit(text=clean_text("\n".join(body)), heading=heading))
    for table in document.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                parts.append(" | ".join(dict.fromkeys(cells)))  # merged cells repeat
    return Extracted(text=clean_text("\n".join(parts)), units=units)


def _extract_image(data: bytes) -> Extracted:
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except Exception as exc:
        raise DocumentError("This image could not be opened.") from exc
    result = Extracted(text="")
    result.text = clean_text(_ocr_image(image, result, "This image"))
    return result


def _extract_text(data: bytes) -> Extracted:
    for encoding in ("utf-8-sig", "utf-16", "cp1252"):
        try:
            return Extracted(text=clean_text(data.decode(encoding)))
        except UnicodeError:
            continue
    return Extracted(text=clean_text(data.decode("utf-8", errors="replace")))


def extract(data: bytes, filename: str) -> Extracted:
    """Extract text from a file's bytes. Raises DocumentError for unreadable files."""
    kind = sniff_kind(data, filename)
    extractor = {
        "pdf": _extract_pdf,
        "docx": _extract_docx,
        "image": _extract_image,
        "text": _extract_text,
    }[kind]
    result = extractor(data)
    if not result.text and not result.warnings:
        result.warnings.append("No readable text was found in this file.")
    if not result.units and result.text:
        result.units = [Unit(text=result.text)]
    return result


# ---------------------------------------------------------------------- web pages

_SKIP_TAGS = frozenset(
    ["script", "style", "noscript", "template", "svg", "nav", "footer", "header", "aside", "form", "button", "iframe", "select", "figure"]
)
_HEADING_TAGS = frozenset(["h1", "h2", "h3", "h4"])
_BLOCK_TAGS = frozenset(
    ["p", "div", "li", "br", "tr", "section", "article", "main", "pre", "blockquote", "dd", "dt", "table", "ul", "ol", "h5", "h6"]
)
_VOID_TAGS = frozenset(
    ["area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"]
)


def extract_html(markup: str) -> tuple[str, Extracted]:
    """Readable text of a web page, cut into sections at its headings.

    Navigation, headers, footers, scripts and forms are dropped. When the page
    marks its content with <main> or <article>, only that part is kept, which
    removes the sidebars of most article and wiki pages. Returns the page title
    and the extracted text.
    """
    from html.parser import HTMLParser

    class Reader(HTMLParser):
        def __init__(self) -> None:
            super().__init__(convert_charrefs=True)
            self.title = ""
            self.in_title = False
            # The element being skipped (nav, script, ...) and how deeply that same
            # tag is nested inside itself. Only its own tag name is counted, so
            # unclosed <li> or <p> inside it cannot leave the reader stuck.
            self.skip_tag = ""
            self.skip = 0
            self.main_depth = 0  # depth inside <main>/<article>
            self.saw_main = False
            self.heading: list[str] | None = None
            # (heading, lines, inside main) per section, in page order
            self.sections: list[tuple[str, list[str], bool]] = [("", [], False)]
            self.line: list[str] = []

        def _flush_line(self) -> None:
            text = " ".join("".join(self.line).split())
            self.line = []
            if text:
                self.sections[-1][1].append(text)

        def handle_starttag(self, tag, attrs):
            if tag in _VOID_TAGS:
                if tag == "br":
                    self._flush_line()
                return
            if tag == "title":
                self.in_title = True
            if self.skip:
                if tag == self.skip_tag:
                    self.skip += 1
                return
            role = dict(attrs).get("role", "") or ""
            if tag in _SKIP_TAGS or role in ("navigation", "banner", "contentinfo", "complementary"):
                self.skip_tag, self.skip = tag, 1
                return
            if tag in ("main", "article"):
                self.main_depth += 1
                self.saw_main = True
            if tag in _HEADING_TAGS:
                self._flush_line()
                self.heading = []
            elif tag in _BLOCK_TAGS:
                self._flush_line()

        def handle_endtag(self, tag):
            if tag in _VOID_TAGS:
                return
            if tag == "title":
                self.in_title = False
            if self.skip:
                if tag == self.skip_tag:
                    self.skip -= 1
                return
            if tag in ("main", "article") and self.main_depth:
                self.main_depth -= 1
            if tag in _HEADING_TAGS and self.heading is not None:
                heading = " ".join("".join(self.heading).split())[:300]
                self.heading = None
                if heading:
                    self.sections.append((heading, [], self.main_depth > 0))
            elif tag in _BLOCK_TAGS:
                self._flush_line()

        def handle_data(self, data):
            if self.in_title:
                self.title += data
                return
            if self.skip:
                return
            if self.heading is not None:
                self.heading.append(data)
            else:
                if not self.sections[-1][1] and not self.line:
                    # First text of a section: record whether it is in the main content.
                    heading, lines, _ = self.sections[-1]
                    self.sections[-1] = (heading, lines, self.main_depth > 0)
                self.line.append(data)

    reader = Reader()
    try:
        reader.feed(markup)
        reader.close()
    except Exception as exc:  # html.parser is lenient; this is a last resort
        raise DocumentError("This web page could not be read.") from exc
    reader._flush_line()

    sections = [s for s in reader.sections if s[1]]
    if reader.saw_main and any(inside for _, _, inside in sections):
        sections = [s for s in sections if s[2]]
    units = []
    for heading, lines, _ in sections:
        # Drop stray short lines (buttons, captions, "Edit" links) between paragraphs.
        kept = [line for line in lines if len(line) >= 30 or line.endswith((".", ":", "?"))]
        text = clean_text("\n".join(kept))
        if text:
            units.append(Unit(text=text, heading=heading))
    title = " ".join(reader.title.split())[:200]
    result = Extracted(text=clean_text("\n\n".join(u.text for u in units)), units=units)
    if not result.text:
        result.warnings.append("No readable text was found on this web page.")
    return title, result
