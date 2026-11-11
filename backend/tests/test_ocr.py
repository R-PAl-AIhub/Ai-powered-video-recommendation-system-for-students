"""OCR helpers and engine selection, without loading a real OCR model."""

from __future__ import annotations

import sys
import types

import httpx
import pytest
from PIL import Image

from app.config import get_settings
from app.services import ocr


@pytest.fixture(autouse=True)
def restore_engine():
    """Engine selection is cached per process; put the test default back after."""
    yield
    ocr.set_ocr(None)


def box(left: float, top: float, width: float = 80, height: float = 20) -> list[list[float]]:
    return [
        [left, top],
        [left + width, top],
        [left + width, top + height],
        [left, top + height],
    ]


# ------------------------------------------------------------------ image prep


def test_prepare_image_converts_to_rgb_and_shrinks_large_scans():
    huge = Image.new("L", (4400, 1100), 255)
    prepared = ocr.prepare_image(huge)
    assert prepared.mode == "RGB"
    assert prepared.size == (ocr.MAX_SIDE, ocr.MAX_SIDE // 4)

    small = Image.new("RGB", (640, 480), "white")
    assert ocr.prepare_image(small).size == (640, 480)


def test_prepare_image_applies_the_camera_rotation():
    photo = Image.new("RGB", (400, 200), "white")
    exif = photo.getexif()
    exif[0x0112] = 6  # orientation: the phone was held upright
    photo.info["exif"] = exif.tobytes()
    photo.getexif()[0x0112] = 6
    assert ocr.prepare_image(photo).size == (200, 400)


# --------------------------------------------------------------- reading order


def test_lines_from_boxes_rebuilds_reading_order():
    detected = [
        (box(300, 102), "Management"),  # same line as "Memory", found first
        (box(40, 160), "Paging"),
        (box(40, 100), "Memory"),
        (box(200, 164), "and"),
        (box(300, 158), "Segmentation"),
        (box(40, 230), "   "),  # blank detections are ignored
        (box(40, 300), None),
    ]
    assert ocr.lines_from_boxes(detected) == "Memory Management\nPaging and Segmentation"
    assert ocr.lines_from_boxes([]) == ""


# --------------------------------------------------------------------- engines


def test_rapidocr_engine_orders_its_results_and_handles_an_empty_page(monkeypatch):
    class FakeRapid:
        result = None

        def __call__(self, array):
            assert array.shape == (80, 200, 3)
            return self.result, 0.01

    monkeypatch.setitem(
        sys.modules, "rapidocr_onnxruntime", types.SimpleNamespace(RapidOCR=FakeRapid)
    )
    engine = ocr.RapidOcrEngine()
    page = Image.new("RGB", (200, 80), "white")

    assert engine.read(page) == ""
    FakeRapid.result = [(box(120, 10), "locks", 0.98), (box(10, 12), "Spin", 0.97)]
    assert engine.read(page) == "Spin locks"


def test_tesseract_engine_returns_trimmed_text(monkeypatch):
    fake = types.SimpleNamespace(image_to_string=lambda image: "  Deadlock avoidance\n\n")
    monkeypatch.setitem(sys.modules, "pytesseract", fake)
    assert ocr.TesseractEngine().read(Image.new("RGB", (60, 40), "white")) == "Deadlock avoidance"


def test_google_vision_reports_api_errors_and_empty_pages():
    def vision(payload: dict, status: int = 200) -> ocr.GoogleVisionEngine:
        transport = httpx.MockTransport(lambda request: httpx.Response(status, json=payload))
        return ocr.GoogleVisionEngine("test-key", transport=transport)

    page = Image.new("RGB", (60, 40), "white")
    assert vision({"responses": [{}]}).read(page) == ""
    with pytest.raises(RuntimeError, match="Quota exceeded"):
        vision({"responses": [{"error": {"message": "Quota exceeded"}}]}).read(page)
    with pytest.raises(httpx.HTTPStatusError):
        vision({"error": "forbidden"}, status=403).read(page)


# ------------------------------------------------------------ engine selection


def fake_rapid(monkeypatch, *, works: bool = True) -> None:
    def build(self):
        if not works:
            raise RuntimeError("model files missing")

    monkeypatch.setattr(ocr.RapidOcrEngine, "__init__", build)


def test_build_none_disables_ocr():
    assert ocr._build("none") is None


def test_build_auto_prefers_google_vision_when_a_key_is_set(monkeypatch):
    fake_rapid(monkeypatch)
    assert isinstance(ocr._build("auto"), ocr.RapidOcrEngine)
    monkeypatch.setattr(get_settings(), "google_vision_api_key", "a-key")
    assert isinstance(ocr._build("auto"), ocr.GoogleVisionEngine)
    assert isinstance(ocr._build("google"), ocr.GoogleVisionEngine)
    # An explicit choice wins over the key.
    assert isinstance(ocr._build("rapidocr"), ocr.RapidOcrEngine)


def test_build_google_without_a_key_gives_no_engine(monkeypatch):
    fake_rapid(monkeypatch)
    assert ocr._build("google") is None


def test_build_falls_back_to_tesseract_only_when_it_is_installed(monkeypatch):
    fake_rapid(monkeypatch, works=False)
    monkeypatch.setattr(ocr.shutil, "which", lambda name: None)
    assert ocr._build("auto") is None
    assert ocr._build("rapidocr") is None

    monkeypatch.setattr(ocr.shutil, "which", lambda name: "/usr/bin/tesseract")
    monkeypatch.setitem(sys.modules, "pytesseract", types.SimpleNamespace())
    assert isinstance(ocr._build("auto"), ocr.TesseractEngine)
    assert isinstance(ocr._build("tesseract"), ocr.TesseractEngine)
    # The binary without the Python package is not enough.
    monkeypatch.setitem(sys.modules, "pytesseract", None)
    assert ocr._build("tesseract") is None


def test_get_ocr_builds_once_and_can_be_overridden(monkeypatch):
    built: list[str] = []

    class Engine:
        name = "fake"

        def read(self, image):
            return "text"

    def build(backend):
        built.append(backend)
        return Engine()

    monkeypatch.setattr(ocr, "_build", build)
    monkeypatch.setattr(ocr, "_resolved", False)
    first = ocr.get_ocr()
    assert ocr.get_ocr() is first and built == ["none"]  # the test setting, asked once

    replacement = Engine()
    ocr.set_ocr(replacement)
    assert ocr.get_ocr() is replacement and built == ["none"]
