"""Match topics against video content.

Every video is a set of text chunks: one "meta" chunk (title, chapters,
description) and one chunk per ~75 s of transcript. A topic is scored against
every chunk with a hybrid of semantic similarity (embeddings) and lexical overlap
(TF-IDF), then chunk scores are rolled up into one relevance value per video,
together with the timestamp where the topic starts.
"""

from __future__ import annotations

import re
import threading
from collections import OrderedDict
from dataclasses import dataclass

import numpy as np
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Video, VideoChunk
from .embeddings import Embedder, from_blob

LEX_FULL = 0.30  # TF-IDF cosine regarded as a complete lexical match
LEX_BOOST = 0.35  # how far a lexical match can lift a weak semantic score
HOT_FRACTION = 0.75  # chunks within this fraction of the best chunk count as "on topic"
HOT_FLOOR = 0.35
OUTRO_SECONDS = 60  # an end this close to the video's end means "to the end"
INTRO_SECONDS = 90  # a topic that starts this early is treated as starting at 0:00
BEST_CHUNK_WEIGHT = 0.7  # share of the single best transcript chunk in a video's score
AGREEMENT_BONUS = 0.3  # lift when both the transcript and the title match
TITLE_ONLY_FACTOR = 0.85  # discount for videos matched without a transcript


@dataclass(frozen=True)
class VideoInfo:
    id: int
    title: str
    playlist_id: int | None
    playlist_position: int
    channel: str
    duration_s: int
    view_count: int | None
    like_count: int | None
    comment_count: int | None
    published_at: object | None  # datetime
    comment_sentiment: float | None
    has_transcript: bool
    english: bool  # False when the transcript is in another language (not translated)


@dataclass
class ProjectIndex:
    videos: list[VideoInfo]
    spans: list[tuple[int, int]]  # rows [start, end) of each video; row `start` is the meta chunk
    starts: np.ndarray
    ends: np.ndarray
    texts: list[str]
    chunk_ids: list[int]
    matrix: np.ndarray
    vectorizer: object | None
    tfidf: object | None

    @property
    def empty(self) -> bool:
        return not self.videos


@dataclass
class Match:
    video_id: int
    relevance: float
    start_s: float = 0.0
    end_s: float = 0.0  # where the topic ends; 0 means the end of the video
    coverage_s: float = 0.0
    snippet: str = ""
    via: str = "transcript"  # transcript | title


def _fit_tfidf(texts: list[str]):
    from sklearn.feature_extraction.text import TfidfVectorizer

    if len(texts) < 2:
        return None, None
    vectorizer = TfidfVectorizer(
        ngram_range=(1, 2),
        sublinear_tf=True,
        stop_words="english",
        max_features=60000,
        norm="l2",
        dtype=np.float32,
    )
    try:
        return vectorizer, vectorizer.fit_transform(texts)
    except ValueError:  # every document is empty or only stop words
        return None, None


def hybrid_scores(
    embedder: Embedder,
    query_vectors: np.ndarray,
    query_texts: list[str],
    passage_matrix: np.ndarray,
    vectorizer,
    tfidf,
) -> np.ndarray:
    """Relevance in 0..1 for every (query, passage) pair."""
    low, high = embedder.calibration
    semantic = np.clip((query_vectors @ passage_matrix.T - low) / (high - low), 0.0, 1.0)
    if vectorizer is not None and tfidf is not None:
        lexical = (vectorizer.transform(query_texts) @ tfidf.T).toarray()
        lexical = np.clip(lexical / LEX_FULL, 0.0, 1.0)
        semantic = semantic + LEX_BOOST * lexical * (1.0 - semantic)
    return semantic.astype(np.float32)


def score_passages(
    embedder: Embedder,
    query_vectors: np.ndarray,
    query_texts: list[str],
    passage_vectors: np.ndarray,
    passage_texts: list[str],
) -> np.ndarray:
    """Hybrid scores against an ad-hoc set of passages (exam questions, notes)."""
    if len(passage_texts) == 0 or len(query_texts) == 0:
        return np.zeros((len(query_texts), len(passage_texts)), dtype=np.float32)
    vectorizer, tfidf = _fit_tfidf(passage_texts)
    return hybrid_scores(embedder, query_vectors, query_texts, passage_vectors, vectorizer, tfidf)


# ------------------------------------------------------------------ project index

_cache: OrderedDict[int, tuple[tuple, ProjectIndex]] = OrderedDict()
_cache_lock = threading.Lock()
_CACHE_SIZE = 8


def _signature(db: Session, project_id: int, embedder: Embedder) -> tuple:
    count, newest = db.execute(
        select(func.count(VideoChunk.id), func.max(VideoChunk.id))
        .join(Video, Video.id == VideoChunk.video_id)
        .where(
            Video.project_id == project_id,
            Video.embedded_with == embedder.name,
            VideoChunk.embedding.is_not(None),
        )
    ).one()
    return (count, newest, embedder.name, get_settings().min_video_seconds)


def get_index(db: Session, project_id: int, embedder: Embedder) -> ProjectIndex:
    """The chunk index for a project, rebuilt only when its chunks change."""
    signature = _signature(db, project_id, embedder)
    with _cache_lock:
        cached = _cache.get(project_id)
        if cached and cached[0] == signature:
            _cache.move_to_end(project_id)
            return cached[1]

    rows = db.execute(
        select(VideoChunk, Video)
        .join(Video, Video.id == VideoChunk.video_id)
        .where(
            Video.project_id == project_id,
            Video.embedded_with == embedder.name,
            VideoChunk.embedding.is_not(None),
        )
        .order_by(Video.id, VideoChunk.idx)
    ).all()

    videos: list[VideoInfo] = []
    spans: list[tuple[int, int]] = []
    starts: list[float] = []
    ends: list[float] = []
    texts: list[str] = []
    chunk_ids: list[int] = []
    vectors: list[np.ndarray] = []
    current_id = None
    minimum = get_settings().min_video_seconds
    for chunk, video in rows:
        if 0 < video.duration_s < minimum:
            continue  # trailers and Shorts cannot cover a syllabus topic
        if video.id != current_id:
            if current_id is not None:
                spans[-1] = (spans[-1][0], len(texts))
            current_id = video.id
            videos.append(
                VideoInfo(
                    id=video.id,
                    title=video.title,
                    playlist_id=video.playlist_id,
                    playlist_position=video.playlist_position,
                    channel=video.channel,
                    duration_s=video.duration_s,
                    view_count=video.view_count,
                    like_count=video.like_count,
                    comment_count=video.comment_count,
                    published_at=video.published_at,
                    comment_sentiment=video.comment_sentiment,
                    has_transcript=video.transcript_status == "ok",
                    english=video.transcript_status != "ok"
                    or video.transcript_language.lower().startswith("en")
                    or video.transcript_language.lower().endswith("→en"),
                )
            )
            spans.append((len(texts), len(texts)))
        starts.append(chunk.start_s)
        ends.append(chunk.end_s)
        texts.append(chunk.text)
        chunk_ids.append(chunk.id)
        vectors.append(from_blob(chunk.embedding))
    if spans:
        spans[-1] = (spans[-1][0], len(texts))

    matrix = np.vstack(vectors) if vectors else np.zeros((0, embedder.dim), dtype=np.float32)
    vectorizer, tfidf = _fit_tfidf(texts)
    index = ProjectIndex(
        videos=videos,
        spans=spans,
        starts=np.asarray(starts, dtype=np.float32),
        ends=np.asarray(ends, dtype=np.float32),
        texts=texts,
        chunk_ids=chunk_ids,
        matrix=matrix,
        vectorizer=vectorizer,
        tfidf=tfidf,
    )
    with _cache_lock:
        _cache[project_id] = (signature, index)
        _cache.move_to_end(project_id)
        while len(_cache) > _CACHE_SIZE:
            _cache.popitem(last=False)
    return index


def invalidate_index(project_id: int) -> None:
    with _cache_lock:
        _cache.pop(project_id, None)


# -------------------------------------------------------------------- aggregation


def video_relevance(index: ProjectIndex, scores: np.ndarray) -> np.ndarray:
    """Roll chunk scores (queries x chunks) up to video relevance (queries x videos).

    The transcript score is mostly the best chunk, plus the mean of the best
    three, so a video that dwells on a topic beats one that mentions it once. The
    stronger of transcript and title/description sets the relevance; the weaker
    one can only add to it (a topic that is one section of a longer lecture must
    not be penalised because the title is about something else).
    """
    relevance = np.zeros((scores.shape[0], len(index.videos)), dtype=np.float32)
    for column, (start, end) in enumerate(index.spans):
        meta = scores[:, start]
        if end - start > 1:
            transcript = scores[:, start + 1 : end]
            top = -np.sort(-transcript, axis=1)[:, :3]
            content = BEST_CHUNK_WEIGHT * top[:, 0] + (1 - BEST_CHUNK_WEIGHT) * top.mean(axis=1)
            stronger = np.maximum(content, meta)
            weaker = np.minimum(content, meta)
            relevance[:, column] = stronger + AGREEMENT_BONUS * weaker * (1.0 - stronger)
        else:
            relevance[:, column] = TITLE_ONLY_FACTOR * meta  # no transcript to confirm it
    return relevance


def tidy_snippet(text: str, limit: int = 240) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return cut.rstrip(",;:") + "…"


def study_end(index: ProjectIndex, column: int, last_row: int) -> float:
    """End of the on-topic stretch, or 0 when it runs to (nearly) the end of the video."""
    end = float(index.ends[last_row])
    duration = index.videos[column].duration_s
    if duration and end >= duration - OUTRO_SECONDS:
        return 0.0
    return end


def locate(index: ProjectIndex, column: int, chunk_scores: np.ndarray, relevance: float) -> Match:
    """Find where in the video the topic is covered, and a snippet to show."""
    start, end = index.spans[column]
    video = index.videos[column]
    meta_score = float(chunk_scores[start])
    if end - start <= 1:
        return Match(
            video_id=video.id,
            relevance=relevance,
            snippet=tidy_snippet(index.texts[start]),
            via="title",
        )
    transcript = chunk_scores[start + 1 : end]
    best = int(np.argmax(transcript))
    best_score = float(transcript[best])
    hot = transcript >= max(HOT_FRACTION * best_score, HOT_FLOOR)
    run_start = best
    while run_start > 0 and hot[run_start - 1]:
        run_start -= 1
    run_end = best
    while run_end + 1 < len(hot) and hot[run_end + 1]:
        run_end += 1
    row = start + 1
    start_s = float(index.starts[row + run_start])
    if start_s <= INTRO_SECONDS:
        start_s = 0.0
    coverage = float(np.sum((index.ends[row:end] - index.starts[row:end])[hot]))
    via = "transcript" if best_score >= 0.8 * meta_score else "title"
    return Match(
        video_id=video.id,
        relevance=relevance,
        start_s=start_s,
        end_s=study_end(index, column, row + run_end),
        coverage_s=coverage,
        snippet=tidy_snippet(index.texts[row + best]),
        via=via,
    )
