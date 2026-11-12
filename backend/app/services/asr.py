"""Speech recognition for videos that have no captions (optional).

Off by default (``ASR_ENABLED=false``): it downloads each caption-less video's
audio, which is slow on CPU and is the kind of request YouTube rate-limits, so
requests go through the same pacing as everything else. Speech in other
languages is translated to English by Whisper unless the embedding model is
multilingual.
"""

from __future__ import annotations

import logging
import tempfile
import threading
from pathlib import Path
from typing import Protocol

from ..config import get_settings
from .youtube import Transcript, TranscriptSegment, pace

log = logging.getLogger(__name__)


class Transcriber(Protocol):
    name: str

    def transcribe(self, video_id: str, duration_s: int = 0) -> Transcript | None: ...


def _decode(path: Path):
    """Audio file to 16 kHz mono float samples, via ffmpeg.

    faster-whisper's own decoder depends on a specific PyAV version; ffmpeg is
    sturdier and is needed in the deployment image anyway.
    """
    import shutil
    import subprocess

    import numpy as np

    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("ffmpeg is required for speech recognition")
    raw = subprocess.run(
        [ffmpeg, "-nostdin", "-loglevel", "error", "-i", str(path), "-f", "s16le",
         "-ac", "1", "-ar", "16000", "-"],
        capture_output=True,
        check=True,
    ).stdout
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


class WhisperTranscriber:
    def __init__(self, model_name: str, cache_dir: str):
        self.name = f"faster-whisper:{model_name}"
        self._model_name = model_name
        self._cache_dir = cache_dir
        self._model = None
        self._lock = threading.Lock()

    def _load(self):
        if self._model is None:
            from faster_whisper import WhisperModel

            self._model = WhisperModel(
                self._model_name, device="cpu", compute_type="int8", download_root=self._cache_dir
            )
        return self._model

    def _download_audio(self, video_id: str, folder: str) -> Path | None:
        import yt_dlp

        settings = get_settings()
        options = {
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "format": "bestaudio[filesize<60M]/bestaudio",
            "outtmpl": str(Path(folder) / "%(id)s.%(ext)s"),
            "socket_timeout": 30,
        }
        if settings.youtube_proxy:
            options["proxy"] = settings.youtube_proxy
        pace()
        with yt_dlp.YoutubeDL(options) as ydl:
            ydl.download([f"https://www.youtube.com/watch?v={video_id}"])
        return next(Path(folder).glob(f"{video_id}.*"), None)

    def transcribe(self, video_id: str, duration_s: int = 0) -> Transcript | None:
        from .embeddings import get_embedder

        settings = get_settings()
        if duration_s and duration_s > settings.asr_max_minutes * 60:
            return None
        # The audio is kept inside the app's own data folder, and removed afterwards.
        scratch = Path(settings.data_dir) / "tmp"
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="asr-", dir=scratch) as folder:
            audio = self._download_audio(video_id, folder)
            if audio is None:
                return None
            translate = not get_embedder().multilingual
            with self._lock:  # one transcription at a time; it is CPU-bound
                segments, info = self._load().transcribe(
                    _decode(audio), task="translate" if translate else "transcribe", vad_filter=True
                )
                parts = [
                    TranscriptSegment(start=s.start, duration=s.end - s.start, text=s.text.strip())
                    for s in segments
                    if s.text.strip()
                ]
        if not parts:
            return None
        language = info.language or ""
        if translate and language and not language.startswith("en"):
            language = f"{language}→en"
        # Plain language codes ("hi→en"), so the pipeline treats it like captions.
        return Transcript(language=language or "en", is_generated=True, segments=parts)


_override: Transcriber | None = None
_transcriber: Transcriber | None = None
_lock = threading.Lock()


def get_transcriber() -> Transcriber | None:
    if _override is not None:
        return _override
    settings = get_settings()
    if not settings.asr_enabled:
        return None
    global _transcriber
    with _lock:
        if _transcriber is None:
            _transcriber = WhisperTranscriber(settings.asr_model, str(settings.model_cache_dir))
    return _transcriber


def set_transcriber(transcriber: Transcriber | None) -> None:
    """Override the transcriber (used by tests)."""
    global _override
    _override = transcriber
