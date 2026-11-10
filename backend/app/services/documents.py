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
class Extracted:
    text: str
    page_count: int = 1
    ocr_pages: int = 0
    warnings: list[str] = field(default_factory=list)


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
    if ext in TEXT_EXTENSIONS and b"\x00" not in data[:4096]:
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
        for number in range(min(len(pdf), MAX_PDF_PAGES)):
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
        if len(pdf) > MAX_PDF_PAGES:
            result.warnings.append(f"Only the first {MAX_PDF_PAGES} pages were read.")
    finally:
        pdf.close()
    result.text = clean_text("\n\n".join(parts))
    return result


def _extract_docx(data: bytes) -> Extracted:
    import docx

    try:
        document = docx.Document(io.BytesIO(data))
    except Exception as exc:
        raise DocumentError("This Word document could not be opened.") from exc
    parts = [p.text for p in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                parts.append(" | ".join(dict.fromkeys(cells)))  # merged cells repeat
    return Extracted(text=clean_text("\n".join(parts)))


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
    return result
