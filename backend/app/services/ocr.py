"""Optical character recognition for scanned pages and photos of notes.

``auto`` prefers RapidOCR (ONNX models, no system packages) and falls back to
Tesseract when its binary is installed. Both return plain text in reading order.
"""

from __future__ import annotations

import logging
import shutil
import threading
from typing import Protocol

from PIL import Image, ImageOps

from ..config import get_settings

log = logging.getLogger(__name__)

MAX_SIDE = 2200  # px; larger scans are downscaled before recognition


class OcrEngine(Protocol):
    name: str

    def read(self, image: Image.Image) -> str: ...


def prepare_image(image: Image.Image) -> Image.Image:
    """Normalise orientation, colour mode and size."""
    image = ImageOps.exif_transpose(image)
    if image.mode != "RGB":
        image = image.convert("RGB")
    longest = max(image.size)
    if longest > MAX_SIDE:
        scale = MAX_SIDE / longest
        image = image.resize((int(image.width * scale), int(image.height * scale)))
    return image


def lines_from_boxes(items: list[tuple[list[list[float]], str]]) -> str:
    """Rebuild reading order from detected text boxes: group boxes into lines by
    vertical overlap, then order each line left to right."""
    boxes = []
    for points, text in items:
        text = (text or "").strip()
        if not text:
            continue
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        boxes.append((min(ys), max(ys), min(xs), text))
    boxes.sort(key=lambda b: (b[0] + b[1]) / 2)

    lines: list[list[tuple[float, float, float, str]]] = []
    for box in boxes:
        centre = (box[0] + box[1]) / 2
        if lines:
            last = lines[-1]
            top = min(b[0] for b in last)
            bottom = max(b[1] for b in last)
            if top <= centre <= bottom:
                last.append(box)
                continue
        lines.append([box])
    return "\n".join(" ".join(b[3] for b in sorted(line, key=lambda b: b[2])) for line in lines)


class RapidOcrEngine:
    name = "rapidocr"

    def __init__(self) -> None:
        from rapidocr_onnxruntime import RapidOCR

        self._engine = RapidOCR()
        self._lock = threading.Lock()  # the ONNX sessions are not re-entrant

    def read(self, image: Image.Image) -> str:
        import numpy as np

        array = np.asarray(prepare_image(image))
        with self._lock:
            result, _elapsed = self._engine(array)
        if not result:
            return ""
        return lines_from_boxes([(item[0], item[1]) for item in result])


class TesseractEngine:
    name = "tesseract"

    def read(self, image: Image.Image) -> str:
        import pytesseract

        return pytesseract.image_to_string(prepare_image(image)).strip()


_engine: OcrEngine | None = None
_resolved = False
_lock = threading.Lock()


def _build(backend: str) -> OcrEngine | None:
    if backend == "none":
        return None
    if backend in ("auto", "rapidocr"):
        try:
            return RapidOcrEngine()
        except Exception as exc:
            log.warning("RapidOCR unavailable: %s", exc)
            if backend == "rapidocr":
                return None
    if shutil.which("tesseract"):
        try:
            import pytesseract  # noqa: F401

            return TesseractEngine()
        except ImportError:
            log.warning("tesseract binary found but pytesseract is not installed")
    return None


def get_ocr() -> OcrEngine | None:
    """The configured OCR engine, or None when OCR is unavailable."""
    global _engine, _resolved
    if not _resolved:
        with _lock:
            if not _resolved:
                _engine = _build(get_settings().ocr_backend)
                _resolved = True
                log.info("OCR engine: %s", _engine.name if _engine else "none")
    return _engine


def set_ocr(engine: OcrEngine | None) -> None:
    """Override the engine (used by tests)."""
    global _engine, _resolved
    _engine, _resolved = engine, True
