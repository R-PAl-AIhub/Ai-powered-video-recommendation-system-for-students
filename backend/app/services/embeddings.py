"""Text embeddings.

``fastembed`` runs a small sentence-embedding model on ONNX Runtime (no PyTorch).
``hash`` is a dependency-free lexical fallback used in tests and on hosts where
the model cannot be downloaded; matching still works, with less semantic reach.

Each embedder carries a ``calibration`` pair that maps its raw cosine similarity
onto a 0..1 relevance scale, so the rest of the system is model-agnostic.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Protocol

import numpy as np

from ..config import get_settings

log = logging.getLogger(__name__)

BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


class Embedder(Protocol):
    name: str
    dim: int
    calibration: tuple[float, float]  # cosine at relevance 0 and at relevance 1

    def embed_passages(
        self, texts: list[str], on_progress: Callable[[int], None] | None = None
    ) -> np.ndarray: ...

    def embed_queries(self, texts: list[str]) -> np.ndarray: ...


def _normalize(matrix: np.ndarray) -> np.ndarray:
    matrix = np.asarray(matrix, dtype=np.float32)
    if matrix.ndim == 1:
        matrix = matrix.reshape(1, -1)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms


class FastEmbedEmbedder:
    def __init__(self, model_name: str, cache_dir: str):
        from fastembed import TextEmbedding

        self._model = TextEmbedding(model_name=model_name, cache_dir=cache_dir)
        self._lock = threading.Lock()
        self._is_bge_en = "bge" in model_name.lower() and "-en" in model_name.lower()
        self.name = f"fastembed:{model_name}"
        self.dim = int(self._model.embedding_size)
        # Measured with evaluation/run.py and on real lecture playlists: for BGE,
        # same-subject but off-topic passages sit around 0.55-0.62 cosine, topics
        # with no matching video peak near 0.60, and on-topic passages score
        # 0.72-0.89. Other models get a generic window; re-measure before relying on it.
        self.calibration = (0.60, 0.85) if self._is_bge_en else (0.25, 0.65)

    def embed_passages(self, texts, on_progress=None):
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        out: list[np.ndarray] = []
        batch = 32
        for start in range(0, len(texts), batch):
            with self._lock:
                out.extend(self._model.embed(texts[start : start + batch], batch_size=batch))
            if on_progress:
                on_progress(min(start + batch, len(texts)))
        return _normalize(np.vstack(out))

    def embed_queries(self, texts):
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        prepared = [BGE_QUERY_PREFIX + t for t in texts] if self._is_bge_en else list(texts)
        with self._lock:
            vectors = list(self._model.embed(prepared, batch_size=32))
        return _normalize(np.vstack(vectors))


class HashEmbedder:
    """Hashed bag-of-words/bigrams vectors: deterministic, instant, lexical only."""

    name = "hash:v1"
    dim = 2048
    calibration = (0.03, 0.42)

    def __init__(self) -> None:
        from sklearn.feature_extraction.text import HashingVectorizer

        self._vectorizer = HashingVectorizer(
            n_features=self.dim,
            ngram_range=(1, 2),
            norm="l2",
            alternate_sign=False,
            stop_words="english",
            lowercase=True,
        )

    def _embed(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        return _normalize(self._vectorizer.transform(texts).toarray())

    def embed_passages(self, texts, on_progress=None):
        vectors = self._embed(texts)
        if on_progress:
            on_progress(len(texts))
        return vectors

    def embed_queries(self, texts):
        return self._embed(texts)


_embedder: Embedder | None = None
_lock = threading.Lock()


def get_embedder() -> Embedder:
    """The process-wide embedder. Falls back to the hash embedder if the model
    cannot be loaded, so a missing download never takes the service down."""
    global _embedder
    if _embedder is None:
        with _lock:
            if _embedder is None:
                settings = get_settings()
                if settings.embedding_backend == "fastembed":
                    try:
                        _embedder = FastEmbedEmbedder(
                            settings.embedding_model, str(settings.model_cache_dir)
                        )
                    except Exception as exc:
                        log.error("Embedding model unavailable (%s); using hash fallback", exc)
                        _embedder = HashEmbedder()
                else:
                    _embedder = HashEmbedder()
                log.info("Embedder: %s", _embedder.name)
    return _embedder


def set_embedder(embedder: Embedder | None) -> None:
    global _embedder
    _embedder = embedder


def to_blob(vector: np.ndarray) -> bytes:
    return np.asarray(vector, dtype=np.float32).tobytes()


def from_blob(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32)
