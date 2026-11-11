"""Reading each supported file type without OCR: type detection, text cleanup,
PDFs with a text layer and bookmarks, Word files, text encodings, web pages."""

from __future__ import annotations

import io

import docx
import pytest
from PIL import Image

from app.services import documents, ocr
from app.services.documents import DocumentError, clean_text, extract, sniff_kind

LONG = "This sentence is long enough to count as real text on a page of a PDF file."


def text_pdf(pages: list[str], bookmarks: list[tuple[str, int]] = ()) -> bytes:
    """A small PDF with a real text layer: one line per page, optional bookmarks
    (title, 0-based page)."""
    objects: dict[int, bytes] = {}
    page_ids = [4 + 2 * i for i in range(len(pages))]
    first_outline = 4 + 2 * len(pages)
    outline_ids = [first_outline + 1 + i for i in range(len(bookmarks))]

    catalog = b"<< /Type /Catalog /Pages 2 0 R"
    if bookmarks:
        catalog += b" /Outlines %d 0 R" % first_outline
    objects[1] = catalog + b" >>"
    kids = b" ".join(b"%d 0 R" % i for i in page_ids)
    objects[2] = b"<< /Type /Pages /Kids [%s] /Count %d >>" % (kids, len(pages))
    objects[3] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"
    for page_id, line in zip(page_ids, pages, strict=True):
        escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream = f"BT /F1 12 Tf 40 780 Td ({escaped}) Tj ET".encode("latin-1")
        objects[page_id] = (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            b"/Resources << /Font << /F1 3 0 R >> >> /Contents %d 0 R >>" % (page_id + 1)
        )
        objects[page_id + 1] = b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream)
    if bookmarks:
        objects[first_outline] = b"<< /Type /Outlines /First %d 0 R /Last %d 0 R /Count %d >>" % (
            outline_ids[0],
            outline_ids[-1],
            len(bookmarks),
        )
        for index, (title, page) in enumerate(bookmarks):
            item = b"<< /Title (%s) /Parent %d 0 R /Dest [%d 0 R /Fit]" % (
                title.encode("latin-1"),
                first_outline,
                page_ids[page],
            )
            if index > 0:
                item += b" /Prev %d 0 R" % outline_ids[index - 1]
            if index < len(bookmarks) - 1:
                item += b" /Next %d 0 R" % outline_ids[index + 1]
            objects[outline_ids[index]] = item + b" >>"

    out = bytearray(b"%PDF-1.4\n")
    offsets = {}
    for number in sorted(objects):
        offsets[number] = len(out)
        out += b"%d 0 obj\n%s\nendobj\n" % (number, objects[number])
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for number in sorted(objects):
        out += b"%010d 00000 n \n" % offsets[number]
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        xref,
    )
    return bytes(out)


def word_file(build) -> bytes:
    document = docx.Document()
    build(document)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def picture(fmt: str) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (40, 30), "white").save(buffer, format=fmt)
    return buffer.getvalue()


# -------------------------------------------------------------- type detection


@pytest.mark.parametrize(
    ("data", "name", "kind"),
    [
        (b"%PDF-1.7 ...", "anything.bin", "pdf"),  # the content decides, not the name
        (b"PK\x03\x04rest", "notes.docx", "docx"),
        (picture("PNG"), "photo.png", "image"),
        (picture("JPEG"), "photo.jpg", "image"),
        (picture("BMP"), "scan.bmp", "image"),
        (picture("TIFF"), "scan.tif", "image"),
        (picture("WEBP"), "scan.webp", "image"),
        (b"Unit 1: Processes", "syllabus.txt", "text"),
        (b"# Notes", "notes.md", "text"),
    ],
)
def test_sniff_kind_recognises_supported_files(data, name, kind):
    assert sniff_kind(data, name) == kind


@pytest.mark.parametrize(
    ("data", "name"),
    [
        (b"PK\x03\x04rest", "archive.zip"),  # a zip that is not a Word file
        (b"MZ\x90\x00", "program.exe"),
        (b"MZ\x90\x00", "renamed.pdf"),  # the name alone is not trusted
        (b"binary\x00data", "data.txt"),
        (b"plain words", "noextension"),
    ],
)
def test_sniff_kind_refuses_everything_else(data, name):
    with pytest.raises(DocumentError, match="Unsupported file"):
        sniff_kind(data, name)


# ---------------------------------------------------------------- text cleanup


def test_clean_text_normalises_what_extractors_produce():
    raw = "Dead-\r\nlock   avoid­ance\x00\tis key.  \r\n\r\n\r\n\r\n  Next   line \rEnd"
    assert clean_text(raw) == "Deadlock avoidance is key.\n\nNext line\nEnd"
    assert len(clean_text("x" * (documents.MAX_TEXT_CHARS + 50))) == documents.MAX_TEXT_CHARS


def test_spell_correct_keeps_the_case_of_the_word_and_leaves_ambiguous_ones():
    vocabulary = {"semaphore": 4, "scheduling": 3, "cat": 9}
    fixed, changed = documents.spell_correct("SEMAPH0RE and Schedulmg, cat", {**vocabulary})
    assert fixed == "SEMAPH0RE and Scheduling, cat"  # a digit splits the word: left alone
    assert changed == 1
    fixed, changed = documents.spell_correct("SEMAPHORF Semaphorf semaphorf", vocabulary)
    assert fixed == "SEMAPHORE Semaphore semaphore" and changed == 3
    # Two equally close known words: do not guess.
    fixed, changed = documents.spell_correct("pagimg", {"paging": 2, "pacing": 2})
    assert fixed == "pagimg" and changed == 0


# ------------------------------------------------------------------------ PDFs


def test_pdf_with_a_text_layer_is_read_page_by_page_without_ocr():
    result = extract(text_pdf([f"Page one. {LONG}", f"Page two. {LONG}"]), "book.pdf")
    assert result.page_count == 2 and result.ocr_pages == 0 and result.warnings == []
    assert [unit.page for unit in result.units] == [1, 2]
    assert result.units[0].text.startswith("Page one.")
    assert "Page two." in result.text


def test_pdf_bookmarks_become_the_heading_of_the_pages_they_cover():
    pdf = text_pdf(
        [f"Intro. {LONG}", f"Locks. {LONG}", f"More locks. {LONG}", f"Paging. {LONG}"],
        bookmarks=[("Chapter 28 Locks", 1), ("Chapter 18 Paging", 3)],
    )
    result = extract(pdf, "ostep.pdf")
    assert [unit.heading for unit in result.units] == [
        "",
        "Chapter 28 Locks",
        "Chapter 28 Locks",  # a chapter runs until the next bookmark
        "Chapter 18 Paging",
    ]


def test_scanned_page_without_an_ocr_engine_gives_a_warning_not_an_error():
    ocr.set_ocr(None)
    result = extract(text_pdf(["x"]), "scan.pdf")
    assert result.ocr_pages == 0
    assert any("Page 1 looks like a scan" in warning for warning in result.warnings)


def test_scanned_page_uses_the_ocr_engine_when_it_reads_more():
    class Engine:
        name = "fake"

        def read(self, image):
            return "Banker algorithm keeps the system in a safe state at all times."

    ocr.set_ocr(Engine())
    try:
        result = extract(text_pdf(["x"]), "scan.pdf")
    finally:
        ocr.set_ocr(None)
    assert result.ocr_pages == 1 and result.text.startswith("Banker algorithm")


def test_broken_pdf_is_reported_to_the_student():
    with pytest.raises(DocumentError, match="could not be opened"):
        extract(b"%PDF-1.4 this is not really a pdf", "broken.pdf")


def test_long_pdf_is_cut_off_with_a_warning(monkeypatch):
    monkeypatch.setattr(documents, "MAX_PDF_PAGES", 2)
    result = extract(text_pdf([f"One. {LONG}", f"Two. {LONG}", f"Three. {LONG}"]), "long.pdf")
    assert len(result.units) == 2 and result.page_count == 3
    assert result.warnings == ["Only the first 2 pages were read."]


# ------------------------------------------------------------------ Word files


def test_word_file_is_split_at_headings_and_tables_are_read():
    def build(document):
        document.add_paragraph("Operating Systems", style="Title")
        document.add_paragraph("Course overview paragraph.")
        document.add_heading("Unit 1: Processes", level=1)
        document.add_paragraph("Process states and the process control block.")
        document.add_heading("Unit 2: Memory", level=2)
        document.add_paragraph("Paging and segmentation.")
        table = document.add_table(rows=2, cols=2)
        table.cell(0, 0).text, table.cell(0, 1).text = "Week", "Topic"
        table.cell(1, 0).text, table.cell(1, 1).text = "1", "Scheduling"

    result = extract(word_file(build), "syllabus.docx")
    assert [(unit.heading, unit.text) for unit in result.units] == [
        ("Operating Systems", "Course overview paragraph."),
        ("Unit 1: Processes", "Process states and the process control block."),
        ("Unit 2: Memory", "Paging and segmentation."),
    ]
    assert "Week | Topic" in result.text and "1 | Scheduling" in result.text
    assert all(unit.page == 0 for unit in result.units)


def test_broken_word_file_is_reported_to_the_student():
    with pytest.raises(DocumentError, match="Word document could not be opened"):
        extract(b"PK\x03\x04 not a real archive", "broken.docx")


# ------------------------------------------------------------- images and text


def test_image_without_an_ocr_engine_gives_a_warning():
    ocr.set_ocr(None)
    result = extract(picture("PNG"), "notes.png")
    assert result.text == "" and result.units == []
    assert any("This image looks like a scan" in warning for warning in result.warnings)


def test_broken_image_is_reported_to_the_student():
    with pytest.raises(DocumentError, match="image could not be opened"):
        extract(b"\x89PNG\r\n\x1a\n truncated", "broken.png")


@pytest.mark.parametrize(
    "data",
    [
        "Résumé of Unit 1 — naïve paging".encode(),
        "﻿Résumé of Unit 1 — naïve paging".encode(),  # UTF-8 with a byte-order mark
        "Résumé of Unit 1 — naïve paging".encode("utf-16"),
        "Résumé of Unit 1 — naïve paging".encode("cp1252"),  # old Windows Notepad
    ],
)
def test_text_files_are_decoded_in_the_common_encodings(data):
    result = extract(data, "notes.txt")
    assert result.text == "Résumé of Unit 1 — naïve paging"
    assert [unit.text for unit in result.units] == [result.text]  # one unit for the whole file


def test_empty_file_says_that_nothing_was_found():
    result = extract(b"   \n  ", "empty.txt")
    assert result.text == "" and result.warnings == ["No readable text was found in this file."]


# ------------------------------------------------------------------- web pages


def test_web_page_keeps_the_article_and_drops_navigation():
    page = """
    <html><head><title>  Semaphore
      (programming) - Wiki </title><style>p { color: red }</style></head>
    <body>
      <nav><ul><li>Home<li>About</ul></nav>
      <div role="banner">Site banner that should never be read by anybody.</div>
      <p>This sidebar paragraph sits outside the article and must be dropped.</p>
      <main>
        <h1>Semaphore</h1>
        <p>A semaphore is a variable used to control access<br>to a common resource.</p>
        <button>Edit</button>
        <span>Edit</span>
        <h2>Semantics <small>and</small> implementation</h2>
        <p>Counting semaphores are equipped with two operations: wait and signal.</p>
        <aside><p>An aside that is not part of the explanation at all, skipped.</p></aside>
        <script>var tracking = "A semaphore script that must not be read as text.";</script>
      </main>
      <footer><p>Footer text that is long enough to look like a real paragraph.</p></footer>
    </body></html>
    """
    title, result = documents.extract_html(page)
    assert title == "Semaphore (programming) - Wiki"
    assert [unit.heading for unit in result.units] == [
        "Semaphore",
        "Semantics and implementation",
    ]
    assert result.units[0].text == (
        "A semaphore is a variable used to control access\nto a common resource."
    )
    for dropped in ("sidebar", "banner", "Footer", "aside", "tracking", "Home", "Edit"):
        assert dropped not in result.text


def test_web_page_without_main_keeps_every_section_and_reports_an_empty_page():
    title, result = documents.extract_html(
        "<h2>Deadlock</h2><p>Four conditions must hold for a deadlock to occur.</p>"
        "<h3>Prevention</h3><div>Break at least one of the four conditions.</div>"
    )
    assert title == ""
    assert [unit.heading for unit in result.units] == ["Deadlock", "Prevention"]

    _, empty = documents.extract_html("<html><body><nav>Menu</nav></body></html>")
    assert empty.text == "" and empty.warnings == ["No readable text was found on this web page."]
