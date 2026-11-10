"""Second-stage relevance: a cross-encoder re-scores the embedding shortlist.

Embeddings compare a topic and a passage as two separate vectors, which is fast
but cannot tell near-identical wordings apart ("disk scheduling algorithms" vs a
lecture on CPU "scheduling algorithms"). A cross-encoder reads the topic and the
passage together and separates such cases cleanly, at a cost of ~20 ms per pair,
so it is only run on the few candidates the embeddings shortlist.

The reranker is optional: set RERANKER_MODEL to an empty string to disable it
(for example on a host with very little memory). Matching then uses embeddings
alone.
"""

from __future__ import annotations

import hashlib
import logging
import threading
from typing import Protocol

import numpy as np

from ..config import get_settings

log = logging.getLogger(__name__)

PASSAGE_CHARS = 1200  # ~250 tokens; the model reads at most 512 tokens per pair


class Reranker(Protocol):
    name: str

    def raw_scores(self, query: str, passages: list[str]) -> list[float]:
        """The model's own score for each passage. This is what gets cached, so a
        later change of calibration applies to cached scores too."""
        ...

    def calibrate(self, raw: float) -> float:
        """Map a raw score to a relevance in 0..1."""
        ...


class FastEmbedReranker:
    def __init__(self, model_name: str, cache_dir: str):
        from fastembed.rerank.cross_encoder import TextCrossEncoder

        self._model = TextCrossEncoder(model_name=model_name, cache_dir=cache_dir)
        self._lock = threading.Lock()
        self.name = f"fastembed:{model_name}"
        # Logit window mapped to 0..1, set so the best separating logit (2.84)
        # lands on 0.5. Measured with evaluation/rerank_study.py on 60 labelled
        # pairs from a real lecture playlist, taking the best of four passages per
        # video: look-alike pairs peak at 2.72, genuine matches have a 10th
        # percentile of 3.42 and a median of 7.2 (AUC 0.99). Other models use a
        # different output scale and must be measured before use.
        self._low, self._high = 0.8, 4.9
        if "ms-marco" not in model_name.lower():
            log.warning("reranker %s is uncalibrated; scores may be too strict or lax", model_name)

    def raw_scores(self, query: str, passages: list[str]) -> list[float]:
        if not passages:
            return []
        with self._lock:
            logits = self._model.rerank(query, [p[:PASSAGE_CHARS] for p in passages], batch_size=16)
            return [float(value) for value in logits]

    def calibrate(self, raw: float) -> float:
        return float(np.clip((raw - self._low) / (self._high - self._low), 0.0, 1.0))


def query_hash(text: str) -> str:
    """Identifies the wording a cached score was computed for."""
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


_reranker: Reranker | None = None
_resolved = False
_lock = threading.Lock()


def get_reranker() -> Reranker | None:
    """The configured reranker, or None when disabled or unavailable."""
    global _reranker, _resolved
    if not _resolved:
        with _lock:
            if not _resolved:
                settings = get_settings()
                if settings.reranker_model and settings.embedding_backend == "fastembed":
                    try:
                        _reranker = FastEmbedReranker(
                            settings.reranker_model, str(settings.model_cache_dir)
                        )
                    except Exception as exc:
                        log.error("Reranker unavailable (%s); matching uses embeddings only", exc)
                _resolved = True
                log.info("Reranker: %s", _reranker.name if _reranker else "none")
    return _reranker


def set_reranker(reranker: Reranker | None) -> None:
    """Override the reranker (used by tests)."""
    global _reranker, _resolved
    _reranker, _resolved = reranker, True
