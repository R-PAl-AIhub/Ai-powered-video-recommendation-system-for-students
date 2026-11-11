"""Reading real files: PDFs with and without a text layer, photos, Word files,
OCR spell-correction, and the Google Vision backend."""

from __future__ import annotations

import io

import httpx
import pytest
from PIL import Image, ImageDraw, ImageFont

from app.services import documents, ocr
from app.services.documents import spell_correct, vocabulary_of

from .conftest import register, run_jobs


def _font(size: int):
    try:
        return ImageFont.truetype("arial.ttf", size)
    except OSError:
        try:
            return ImageFont.truetype("DejaVuSans.ttf", size)
        except OSError:
            return ImageFont.load_default(size=size)


def scanned_pdf(lines: list[str]) -> bytes:
    """A PDF whose page is only a picture of text, like a scan."""
    image = Image.new("RGB", (1240, 1754), "white")
    draw = ImageDraw.Draw(image)
    for row, line in enumerate(lines):
        draw.text((110, 120 + row * 58), line, fill="black", font=_font(34))
    buffer = io.BytesIO()
    image.save(buffer, format="PDF")
    return buffer.getvalue()


def test_spell_correct_fixes_ocr_errors_with_course_words():
    vocabulary = vocabulary_of(
        ["A semaphore is an integer variable.", "Every variable is shared by the semaphore."]
    )
    fixed, changed = spell_correct("A semaphore is an integer yariable, shared.", vocabulary)
    assert fixed == "A semaphore is an integer variable, shared."
    assert changed == 1
    # Unknown subject words with no close match are left alone.
    unchanged, changed = spell_correct("Thrashing and Belady anomaly", vocabulary)
    assert unchanged == "Thrashing and Belady anomaly" and changed == 0


def test_google_vision_engine_reads_text_via_the_api():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["key"] == "test-key"
        assert b"DOCUMENT_TEXT_DETECTION" in request.content
        return httpx.Response(200, json={"responses": [{"fullTextAnnotation": {"text": "Semaphores\n"}}]})

    engine = ocr.GoogleVisionEngine("test-key", transport=httpx.MockTransport(handler))
    assert engine.read(Image.new("RGB", (200, 80), "white")) == "Semaphores"


@pytest.fixture
def real_ocr():
    try:
        engine = ocr.RapidOcrEngine()
    except Exception as exc:  # pragma: no cover - only where the model cannot load
        pytest.skip(f"RapidOCR unavailable: {exc}")
    ocr.set_ocr(engine)
    yield engine
    ocr.set_ocr(None)


def test_scanned_pdf_is_read_with_ocr(real_ocr):
    result = documents.extract(scanned_pdf(["Unit 1: Memory", "Paging, Segmentation, Thrashing."]), "scan.pdf")
    assert result.ocr_pages == 1
    assert "Paging" in result.text and "Segmentation" in result.text


def test_scanned_syllabus_upload_builds_topics(client, real_ocr):
    register(client)
    project_id = client.post("/api/projects", json={"name": "Scanned"}).json()["id"]
    pdf = scanned_pdf(["Unit 1: Memory Management", "Paging, Segmentation, Virtual memory."])
    response = client.post(
        f"/api/projects/{project_id}/documents",
        data={"kind": "syllabus"},
        files={"file": ("scan.pdf", pdf, "application/pdf")},
    )
    assert response.status_code == 201
    client.post(f"/api/projects/{project_id}/process")
    run_jobs()
    detail = client.get(f"/api/projects/{project_id}").json()
    assert detail["documents"][0]["ocr_pages"] == 1
    names = {t["name"] for t in client.get(f"/api/projects/{project_id}/path").json()["topics"]}
    assert {"Paging", "Segmentation", "Virtual memory"} <= names
