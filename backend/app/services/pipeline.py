"""The processing pipeline for one project.

Stages: playlists → video details and transcripts → documents (text/OCR) →
topics → embeddings → recommendations. Every stage is incremental, so running
the pipeline again only does the work that is new.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Document, Playlist, Project, Topic, Video, VideoChunk, utcnow
from . import documents as documents_service
from .embeddings import get_embedder, to_blob
from .matching import invalidate_index
from .recommend import ensure_topic_vectors, rebuild_recommendations
from .topics import extract_topics
from .youtube import (
    Transcript,
    TranscriptSegment,
    VideoMeta,
    YouTubeClient,
    YouTubeError,
    get_youtube_client,
)

log = logging.getLogger(__name__)

CHUNK_SECONDS = 75.0
CHUNK_MAX_WORDS = 230
META_DESCRIPTION_CHARS = 600
BLOCK_ABORT_AFTER = 6  # consecutive blocked transcript requests before giving up

Progress = Callable[[str, float, str], None]  # (stage, progress 0..1, message)

_NOISE = re.compile(r"\[[^\]]{0,30}\]|\([^)]{0,3}\)|>>+")
_PROMO = re.compile(
    r"https?://|www\.|subscribe|follow\s+(us|me)|instagram|facebook|twitter|telegram|whatsapp|"
    r"linkedin|playstore|app\s*store|download\s+(the|our)\s+app|contribute|donat|"
    r"copyright|all rights reserved|music\s*:|#\w+",
    re.IGNORECASE,
)


# -------------------------------------------------------------------- chunking


def chunk_transcript(segments: list[TranscriptSegment]) -> list[tuple[float, float, str]]:
    """Group caption segments into windows of about CHUNK_SECONDS."""
    chunks: list[tuple[float, float, str]] = []
    words: list[str] = []
    window_start: float | None = None
    last_end = 0.0
    for segment in segments:
        text = _NOISE.sub(" ", segment.text.replace("\n", " ")).strip()
        if not text:
            continue
        if window_start is None:
            window_start = segment.start
        words.extend(text.split())
        last_end = max(last_end, segment.start + segment.duration)
        if segment.start - window_start >= CHUNK_SECONDS or len(words) >= CHUNK_MAX_WORDS:
            chunks.append((window_start, last_end, " ".join(words)))
            words, window_start = [], None
    if words and window_start is not None:
        if chunks and len(words) < 25:  # fold a short tail into the previous window
            start, _, text = chunks[-1]
            chunks[-1] = (start, last_end, f"{text} {' '.join(words)}")
        else:
            chunks.append((window_start, last_end, " ".join(words)))
    # Auto-captions overlap; make each window end where the next begins.
    return [
        (start, chunks[i + 1][0] if i + 1 < len(chunks) else end, text)
        for i, (start, end, text) in enumerate(chunks)
    ]


def clean_description(description: str) -> str:
    """Keep the descriptive part of a YouTube description; drop links and promo lines."""
    kept: list[str] = []
    for line in description.splitlines():
        line = line.strip()
        if not line or _PROMO.search(line) or re.match(r"^\d{1,2}:\d{2}", line):
            continue
        kept.append(line)
        if sum(len(k) for k in kept) > META_DESCRIPTION_CHARS:
            break
    return " ".join(kept)[:META_DESCRIPTION_CHARS]


def meta_text(title: str, chapters: list[str], description: str) -> str:
    parts = [title.strip()]
    if chapters:
        parts.append("Chapters: " + "; ".join(chapters[:40]))
    cleaned = clean_description(description)
    if cleaned:
        parts.append(cleaned)
    return ". ".join(p for p in parts if p)


def build_chunks(video: Video, chapters: list[str], transcript: Transcript | None) -> list[VideoChunk]:
    chunks = [
        VideoChunk(
            idx=0,
            kind="meta",
            start_s=0.0,
            end_s=float(video.duration_s),
            text=meta_text(video.title, chapters, video.description) or video.youtube_id,
        )
    ]
    if transcript:
        for number, (start, end, text) in enumerate(chunk_transcript(transcript.segments), 1):
            chunks.append(
                VideoChunk(idx=number, kind="transcript", start_s=start, end_s=end, text=text)
            )
    return chunks


# ---------------------------------------------------------------------- stages


@dataclass
class _Fetched:
    video_id: int
    meta: VideoMeta | None
    transcript: Transcript | None
    status: str  # ok | none | error
    blocked: bool = False


def _is_block(exc: Exception) -> bool:
    return type(exc).__name__ in {"IpBlocked", "RequestBlocked", "PoTokenRequired"}


def _fetch_one(client: YouTubeClient, video_id: int, youtube_id: str, need_details: bool) -> _Fetched:
    meta = None
    if need_details:
        try:
            meta = client.fetch_video(youtube_id)
        except Exception as exc:  # details are optional; the playlist entry is enough
            log.info("details unavailable for %s: %s", youtube_id, exc)
    try:
        transcript = client.fetch_transcript(youtube_id)
        return _Fetched(video_id, meta, transcript, "ok" if transcript else "none")
    except Exception as exc:
        log.info("transcript failed for %s: %s", youtube_id, type(exc).__name__)
        return _Fetched(video_id, meta, None, "error", blocked=_is_block(exc))


def sync_playlists(
    db: Session, project: Project, client: YouTubeClient, report: Progress, warnings: list[str]
) -> None:
    settings = get_settings()
    playlists = list(project.playlists)
    for number, playlist in enumerate(playlists):
        report("playlists", number / max(len(playlists), 1), f"Reading playlist {number + 1} of {len(playlists)}")
        try:
            meta = client.fetch_playlist(playlist.youtube_id, settings.max_videos_per_playlist)
        except YouTubeError as exc:
            playlist.status, playlist.error = "error", str(exc)
            warnings.append(f"Playlist could not be read: {exc}")
            db.commit()
            continue
        playlist.title, playlist.channel = meta.title, meta.channel
        playlist.status, playlist.error = "ready", ""
        existing = {
            v.youtube_id: v
            for v in db.scalars(select(Video).where(Video.project_id == project.id))
        }
        for item in meta.videos:
            video = existing.get(item.youtube_id)
            if video is None:
                video = Video(project_id=project.id, youtube_id=item.youtube_id, source="playlist")
                db.add(video)
                existing[item.youtube_id] = video
                video.playlist_id = playlist.id
            elif video.playlist_id is None:
                video.playlist_id = playlist.id
            if video.playlist_id == playlist.id:
                video.playlist_position = item.position
            video.title = item.title or video.title
            video.channel = item.channel or video.channel or meta.channel
            video.duration_s = item.duration_s or video.duration_s
            video.thumbnail_url = item.thumbnail_url or video.thumbnail_url
            if item.view_count is not None:
                video.view_count = item.view_count
            if item.description:
                video.description = item.description
            if item.like_count is not None:
                video.like_count = item.like_count
                video.comment_count = item.comment_count
                video.published_at = item.published_at
        if len(meta.videos) >= settings.max_videos_per_playlist:
            warnings.append(
                f"“{meta.title}” is long; only its first {settings.max_videos_per_playlist} videos were used."
            )
        db.commit()


def apply_fetched(db: Session, video: Video, fetched: _Fetched) -> None:
    """Store fetched details/transcript on a video and (re)build its chunks."""
    chapters: list[str] = []
    if fetched.meta:
        meta = fetched.meta
        video.title = meta.title or video.title
        video.description = meta.description or video.description
        video.channel = meta.channel or video.channel
        video.duration_s = meta.duration_s or video.duration_s
        video.view_count = meta.view_count if meta.view_count is not None else video.view_count
        video.like_count = meta.like_count
        video.comment_count = meta.comment_count
        video.published_at = meta.published_at
        video.thumbnail_url = meta.thumbnail_url or video.thumbnail_url
        chapters = meta.chapters
    video.transcript_status = fetched.status
    video.transcript_language = fetched.transcript.language if fetched.transcript else ""
    video.embedded_with = ""
    video.chunks = build_chunks(video, chapters, fetched.transcript)


def fetch_videos(
    db: Session, project: Project, client: YouTubeClient, report: Progress, warnings: list[str]
) -> None:
    pending = list(
        db.scalars(
            select(Video).where(
                Video.project_id == project.id, Video.transcript_status.in_(("pending", "error"))
            )
        )
    )
    if not pending:
        return
    by_id = {video.id: video for video in pending}
    done = 0
    consecutive_blocks = 0
    aborted = False
    with ThreadPoolExecutor(max_workers=get_settings().transcript_workers) as pool:
        futures = [
            pool.submit(
                _fetch_one,
                client,
                video.id,
                video.youtube_id,
                not video.description and video.like_count is None,
            )
            for video in pending
        ]
        try:
            for future in as_completed(futures):
                fetched = future.result()
                apply_fetched(db, by_id[fetched.video_id], fetched)
                done += 1
                consecutive_blocks = consecutive_blocks + 1 if fetched.blocked else 0
                if done % 5 == 0 or done == len(pending):
                    db.commit()
                report("transcripts", done / len(pending), f"Fetched {done} of {len(pending)} videos")
                if consecutive_blocks >= BLOCK_ABORT_AFTER:
                    aborted = True
                    break
        finally:
            for future in futures:
                future.cancel()
    db.commit()

    statuses = [v.transcript_status for v in pending]
    if aborted or statuses.count("error"):
        warnings.append(
            f"YouTube refused transcript requests for {statuses.count('error') + statuses.count('pending')} "
            "videos (rate limit or blocked network). They are matched on title and description "
            "for now; run the analysis again later to retry."
        )
    missing = statuses.count("none")
    if missing:
        warnings.append(
            f"{missing} video{'s have' if missing != 1 else ' has'} no captions and "
            f"{'were' if missing != 1 else 'was'} matched on title and description only."
        )
    # Videos skipped by an abort still need a meta chunk so they can be matched.
    for video in pending:
        if not video.chunks:
            video.chunks = build_chunks(video, [], None)
    db.commit()


def read_documents(db: Session, project: Project, report: Progress, warnings: list[str]) -> None:
    settings = get_settings()
    pending = [d for d in project.documents if d.status == "pending"]
    for number, document in enumerate(pending):
        report("documents", number / len(pending), f"Reading {document.filename}")
        path = settings.upload_dir / document.storage_name
        try:
            extracted = documents_service.extract(path.read_bytes(), document.filename)
        except documents_service.DocumentError as exc:
            document.status, document.error = "error", str(exc)
            warnings.append(f"{document.filename}: {exc}")
        except OSError:
            document.status, document.error = "error", "The uploaded file is no longer available."
            warnings.append(f"{document.filename}: the uploaded file is no longer available.")
        else:
            document.text = extracted.text
            document.page_count = extracted.page_count
            document.ocr_pages = extracted.ocr_pages
            document.status = "ready" if extracted.text else "error"
            document.error = "" if extracted.text else "; ".join(extracted.warnings)
            warnings.extend(f"{document.filename}: {w}" for w in extracted.warnings)
            # The text now lives in the database; the upload itself is not kept.
            path.unlink(missing_ok=True)
            document.storage_name = ""
        db.commit()


def _topic_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def sync_topics(db: Session, project: Project, warnings: list[str], *, reextract: bool) -> None:
    """Extract topics from the documents, keeping rows (and their feedback) for
    topics that are still present."""
    if project.topics_locked and not reextract:
        return
    ready = [d for d in project.documents if d.status == "ready" and d.text.strip()]
    extracted, source = extract_topics(
        [d.text for d in ready if d.kind == "syllabus"],
        [d.text for d in ready if d.kind == "notes"],
        [d.text for d in ready if d.kind == "exam"],
        limit=get_settings().max_topics_per_project,
    )
    if not extracted:
        if not project.topics:
            warnings.append(
                "No topics could be found. Upload a syllabus, or add topics by hand on the Topics tab."
            )
        return
    if source != "syllabus":
        warnings.append(
            f"No syllabus topics were found, so topics were taken from your {source} instead."
        )
    existing = {_topic_key(t.name): t for t in project.topics}
    kept: list[Topic] = []
    for position, item in enumerate(extracted):
        topic = existing.pop(_topic_key(item.name), None)
        if topic is None:
            topic = Topic(project_id=project.id, name=item.name, source=source)
            topic.unit = item.unit
            project.topics.append(topic)
        elif topic.unit != item.unit:
            topic.unit = item.unit
            topic.embedding = None
        topic.position = position
        kept.append(topic)
    for stale in existing.values():
        if stale.source == "manual":  # never drop topics the student typed in
            stale.position = len(kept)
            kept.append(stale)
        else:
            project.topics.remove(stale)
    project.topics_locked = False
    db.commit()


def embed_videos(db: Session, project: Project, report: Progress) -> None:
    embedder = get_embedder()
    videos = list(
        db.scalars(
            select(Video).where(Video.project_id == project.id, Video.embedded_with != embedder.name)
        )
    )
    chunks = [chunk for video in videos for chunk in video.chunks]
    if not chunks:
        return
    batch = 256
    for start in range(0, len(chunks), batch):
        part = chunks[start : start + batch]
        vectors = embedder.embed_passages([c.text for c in part])
        for chunk, vector in zip(part, vectors, strict=True):
            chunk.embedding = to_blob(vector)
        db.commit()
        done = min(start + batch, len(chunks))
        report("embedding", done / len(chunks), f"Analysed {done} of {len(chunks)} video segments")
    for video in videos:
        video.embedded_with = embedder.name
    db.commit()
    invalidate_index(project.id)


# -------------------------------------------------------------------- pipeline

STAGE_SPANS = {
    "playlists": (0.00, 0.08),
    "transcripts": (0.08, 0.50),
    "documents": (0.50, 0.62),
    "topics": (0.62, 0.66),
    "embedding": (0.66, 0.94),
    "matching": (0.94, 1.00),
}


def run_pipeline(
    db: Session,
    project: Project,
    report: Callable[[str, float, str], None],
    options: dict | None = None,
) -> list[str]:
    """Run every stage for a project. Returns warnings to show the student."""
    options = options or {}
    warnings: list[str] = []
    client = get_youtube_client()

    def stage_report(stage: str, fraction: float, message: str) -> None:
        low, high = STAGE_SPANS[stage]
        report(stage, low + (high - low) * max(0.0, min(1.0, fraction)), message)

    stage_report("playlists", 0, "Reading playlists")
    sync_playlists(db, project, client, stage_report, warnings)

    stage_report("transcripts", 0, "Fetching video details and transcripts")
    fetch_videos(db, project, client, stage_report, warnings)

    stage_report("documents", 0, "Reading your documents")
    read_documents(db, project, stage_report, warnings)

    stage_report("topics", 0, "Finding topics")
    sync_topics(db, project, warnings, reextract=bool(options.get("reextract")))

    stage_report("embedding", 0, "Analysing video content")
    embed_videos(db, project, stage_report)

    stage_report("matching", 0, "Matching topics to videos")
    ensure_topic_vectors(db, project, get_embedder(), force=True)
    rebuild_recommendations(db, project)
    project.processed_at = utcnow()
    db.commit()

    if not db.scalar(select(Video.id).where(Video.project_id == project.id).limit(1)):
        warnings.append("No videos were found. Add a YouTube playlist to get recommendations.")
    return list(dict.fromkeys(warnings))


def ingest_single_video(db: Session, project: Project, youtube_id: str) -> Video:
    """Add one video (e.g. picked from a YouTube search) to the project's pool."""
    client = get_youtube_client()
    video = db.scalar(
        select(Video).where(Video.project_id == project.id, Video.youtube_id == youtube_id)
    )
    if video is None:
        video = Video(project_id=project.id, youtube_id=youtube_id, source="search")
        db.add(video)
        db.flush()
    if video.transcript_status in ("pending", "error"):
        fetched = _fetch_one(client, video.id, youtube_id, need_details=True)
        if fetched.meta is None and not video.title:
            raise YouTubeError("That video could not be loaded from YouTube.")
        apply_fetched(db, video, fetched)
        db.flush()
    embedder = get_embedder()
    if video.embedded_with != embedder.name:
        vectors = embedder.embed_passages([c.text for c in video.chunks])
        for chunk, vector in zip(video.chunks, vectors, strict=True):
            chunk.embedding = to_blob(vector)
        video.embedded_with = embedder.name
    db.flush()
    invalidate_index(project.id)
    return video


__all__ = [
    "Playlist",
    "Document",
    "build_chunks",
    "chunk_transcript",
    "ingest_single_video",
    "meta_text",
    "run_pipeline",
]
