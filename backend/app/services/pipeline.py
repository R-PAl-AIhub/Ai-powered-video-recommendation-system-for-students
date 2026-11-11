"""The processing pipeline for one project.

Stages: playlists → video details and transcripts → documents (text/OCR) →
topics → embeddings → recommendations. Every stage is incremental, so running
the pipeline again only does the work that is new.
"""

from __future__ import annotations

import logging
import re
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Document, Playlist, Project, Topic, Video, VideoChunk, utcnow
from . import documents as documents_service
from .asr import get_transcriber
from .embeddings import get_embedder, to_blob
from .fuzzy import comment_sentiment
from .matching import invalidate_index
from .questions import link_questions
from .recommend import ensure_topic_vectors, playlist_topic_order, rebuild_recommendations
from .topics import ExtractedTopic, extract_topics, headings_from_notes, keyphrase_topics
from .youtube import (
    Transcript,
    TranscriptSegment,
    VideoMeta,
    YouTubeBlocked,
    YouTubeClient,
    YouTubeError,
    get_youtube_client,
)

log = logging.getLogger(__name__)

CHUNK_SECONDS = 75.0
CHUNK_MAX_WORDS = 230
META_DESCRIPTION_CHARS = 600
BLOCK_ABORT_AFTER = 3  # consecutive refused requests before leaving YouTube alone

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
    return isinstance(exc, YouTubeBlocked) or type(exc).__name__ in {
        "IpBlocked",
        "RequestBlocked",
        "PoTokenRequired",
    }


def _fetch_one(
    client: YouTubeClient,
    video_id: int,
    youtube_id: str,
    has_description: bool,
    stop: threading.Event,
    duration_s: int = 0,
) -> _Fetched:
    """Fetch one video's transcript, and its details only if they are needed.

    Each video costs one caption request. The heavier details request (the one
    YouTube's bot detection watches most closely) is made only for videos without
    captions, where the description is the only text there is to match on.
    """
    if stop.is_set():  # YouTube started refusing requests; leave this one for a retry
        return _Fetched(video_id, None, None, "error", blocked=True)
    try:
        transcript = client.fetch_transcript(youtube_id)
    except Exception as exc:
        log.info("transcript failed for %s: %s", youtube_id, type(exc).__name__)
        return _Fetched(video_id, None, None, "error", blocked=_is_block(exc))
    if transcript is None and (transcriber := get_transcriber()) is not None:
        try:  # no captions: listen to the video instead
            transcript = transcriber.transcribe(youtube_id, duration_s)
        except Exception as exc:
            if _is_block(exc):
                return _Fetched(video_id, None, None, "error", blocked=True)
            log.info("speech recognition failed for %s: %s", youtube_id, exc)
    meta = None
    if transcript is None and not has_description:
        try:
            meta = client.fetch_video(youtube_id)
        except Exception as exc:
            if _is_block(exc):
                return _Fetched(video_id, None, None, "error", blocked=True)
            log.info("details unavailable for %s: %s", youtube_id, exc)
    return _Fetched(video_id, meta, transcript, "ok" if transcript else "none")


def transcript_usable(transcript: Transcript) -> bool:
    """Whether the embedding model can read this transcript's language."""
    language = transcript.language.lower()
    return get_embedder().multilingual or language.startswith("en") or language.endswith("→en")


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
    transcript = fetched.transcript
    video.transcript_status = fetched.status
    video.transcript_language = transcript.language if transcript else ""
    if transcript and not transcript_usable(transcript):
        # Captions exist, but in a language the current model cannot read.
        video.transcript_status = "foreign"
        transcript = None
    video.embedded_with = ""
    video.chunks = build_chunks(video, chapters, transcript)


def fetch_videos(
    db: Session, project: Project, client: YouTubeClient, report: Progress, warnings: list[str]
) -> int:
    """Fetch transcripts for videos that still need one. Returns how many videos
    could not be fetched because YouTube refused the requests."""
    wanted = ["pending", "error"]
    if get_embedder().multilingual:
        wanted.append("foreign")  # a multilingual model can use these after all
    pending = list(
        db.scalars(
            select(Video).where(
                Video.project_id == project.id, Video.transcript_status.in_(wanted)
            )
        )
    )
    if not pending:
        return 0
    by_id = {video.id: video for video in pending}
    done = 0
    consecutive_blocks = 0
    stop = threading.Event()
    with ThreadPoolExecutor(max_workers=get_settings().transcript_workers) as pool:
        futures = [
            pool.submit(
                _fetch_one,
                client,
                video.id,
                video.youtube_id,
                bool(video.description),
                stop,
                video.duration_s,
            )
            for video in pending
        ]
        for future in as_completed(futures):
            fetched = future.result()
            apply_fetched(db, by_id[fetched.video_id], fetched)
            done += 1
            consecutive_blocks = consecutive_blocks + 1 if fetched.blocked else 0
            if consecutive_blocks >= BLOCK_ABORT_AFTER:
                stop.set()  # remaining videos return immediately, untouched by YouTube
            if done % 5 == 0 or done == len(pending):
                db.commit()
            report("transcripts", done / len(pending), f"Fetched {done} of {len(pending)} videos")
    db.commit()

    statuses = [v.transcript_status for v in pending]
    blocked = statuses.count("error")
    if blocked:
        warnings.append(
            f"YouTube is temporarily limiting requests, so {blocked} "
            f"video{'s are' if blocked != 1 else ' is'} matched on title only for now. "
            "The analysis will retry them automatically."
        )
    foreign = sorted({v.transcript_language for v in pending if v.transcript_status == "foreign"})
    if foreign:
        warnings.append(
            f"{statuses.count('foreign')} video(s) only have captions in {', '.join(foreign)}, "
            "which the current English model cannot read; they are matched on title and "
            "description. Set EMBEDDING_MODEL to a multilingual model to use those captions."
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
    return blocked


def course_vocabulary(db: Session, project: Project) -> dict[str, int]:
    """Words used in this course: transcripts, titles and documents already read."""
    texts = list(
        db.scalars(
            select(VideoChunk.text)
            .join(Video, Video.id == VideoChunk.video_id)
            .where(Video.project_id == project.id)
        )
    )
    texts += [d.text for d in project.documents if d.status == "ready" and d.text]
    return documents_service.vocabulary_of(texts)


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
            text = extracted.text
            if extracted.ocr_pages and text:
                # OCR misreads letters; correct them against this course's own words.
                text, fixed = documents_service.spell_correct(text, course_vocabulary(db, project))
                if fixed:
                    log.info("corrected %d OCR words in %s", fixed, document.filename)
            document.text = text
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


# Words that make an exam phrase an instruction rather than a concept.
_EXAM_NOISE = frozenset(
    ["explain", "describe", "discuss", "define", "write", "short", "notes", "note", "suitable", "example", "examples", "neat", "diagram", "diagrams", "figure", "calculate", "compute", "find", "compare", "comparison", "differentiate", "difference", "following", "given", "marks", "mark", "answer", "question", "questions", "briefly", "detail", "details", "justify", "state", "list", "illustrate", "consider", "show", "prove", "derive", "what", "which", "why", "how"]
)
NEW_TOPIC_MAX_RELEVANCE = 0.45  # a candidate this close to a syllabus topic is not new


def add_supplementary_topics(
    items: list[tuple[ExtractedTopic, str]], notes_texts: list[str], exam_texts: list[str]
) -> list[tuple[ExtractedTopic, str]]:
    """Add topics the teacher's notes or the past papers cover but the syllabus
    does not name, each placed right after the syllabus topic it is closest to.

    Notes contribute their headings; past papers contribute phrases asked in at
    least two questions. A candidate already covered by a syllabus topic (by
    meaning, not only by wording) is skipped.
    """
    candidates: list[tuple[str, str]] = []
    notes = "\n\n".join(notes_texts)
    if notes.strip():
        candidates += [(t.name, "notes") for t in headings_from_notes(notes, limit=40)]
    exams = "\n\n".join(exam_texts)
    if exams.strip():
        for topic in keyphrase_topics(exams, limit=25):
            words = set(topic.name.lower().split())
            if not words & _EXAM_NOISE:
                candidates.append((topic.name, "exam"))
    if not candidates or not items:
        return items

    embedder = get_embedder()
    low, high = embedder.calibration
    syllabus = embedder.embed_queries([item.name for item, _ in items])
    fresh = embedder.embed_queries([name for name, _ in candidates])
    relevance = (fresh @ syllabus.T - low) / (high - low)

    known = {_topic_key(item.name) for item, _ in items}
    after: dict[int, list[tuple[ExtractedTopic, str]]] = {}
    for row, (name, origin) in enumerate(candidates):
        if _topic_key(name) in known or float(relevance[row].max()) >= NEW_TOPIC_MAX_RELEVANCE:
            continue
        known.add(_topic_key(name))
        anchor = int(relevance[row].argmax()) if float(relevance[row].max()) > 0 else len(items) - 1
        unit = items[anchor][0].unit
        after.setdefault(anchor, []).append((ExtractedTopic(unit=unit, name=name), origin))

    merged: list[tuple[ExtractedTopic, str]] = []
    for index, item in enumerate(items):
        merged.append(item)
        merged.extend(after.get(index, []))
    return merged


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
    items = [(item, source) for item in extracted]
    if source == "syllabus":
        items = add_supplementary_topics(
            items,
            [d.text for d in ready if d.kind == "notes"],
            [d.text for d in ready if d.kind == "exam"],
        )
    existing = {_topic_key(t.name): t for t in project.topics}
    kept: list[Topic] = []
    for position, (item, item_source) in enumerate(items):
        topic = existing.pop(_topic_key(item.name), None)
        if topic is None:
            topic = Topic(project_id=project.id, name=item.name, source=item_source)
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


def score_comments(db: Session, project: Project, client: YouTubeClient) -> None:
    """Viewer sentiment for each video, from its top comments (one request each).

    Only clients that can read comments cheaply offer ``fetch_comments`` (the
    official Data API); without one, ranking simply has one signal fewer.
    """
    fetch = getattr(client, "fetch_comments", None)
    if fetch is None:
        return
    for video in db.scalars(
        select(Video).where(Video.project_id == project.id, Video.comment_sentiment.is_(None))
    ):
        try:
            video.comment_sentiment = comment_sentiment(fetch(video.youtube_id))
        except Exception as exc:  # a ranking nicety; never fail the analysis for it
            log.info("comments unavailable for %s: %s", video.youtube_id, exc)
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


@dataclass
class PipelineResult:
    warnings: list[str] = field(default_factory=list)  # shown to the student
    blocked_videos: int = 0  # videos YouTube refused; worth retrying later


def run_pipeline(
    db: Session,
    project: Project,
    report: Callable[[str, float, str], None],
    options: dict | None = None,
) -> PipelineResult:
    """Run every stage for a project."""
    options = options or {}
    warnings: list[str] = []
    client = get_youtube_client()

    def stage_report(stage: str, fraction: float, message: str) -> None:
        low, high = STAGE_SPANS[stage]
        report(stage, low + (high - low) * max(0.0, min(1.0, fraction)), message)

    stage_report("playlists", 0, "Reading playlists")
    sync_playlists(db, project, client, stage_report, warnings)

    stage_report("transcripts", 0, "Fetching video transcripts")
    blocked = fetch_videos(db, project, client, stage_report, warnings)

    score_comments(db, project, client)

    stage_report("documents", 0, "Reading your documents")
    read_documents(db, project, stage_report, warnings)

    stage_report("topics", 0, "Finding topics")
    sync_topics(db, project, warnings, reextract=bool(options.get("reextract")))

    stage_report("embedding", 0, "Analysing video content")
    embed_videos(db, project, stage_report)

    stage_report("matching", 0, "Matching topics to videos")
    ensure_topic_vectors(db, project, get_embedder(), force=True)
    if project.topics and not project.topics_locked and all(
        t.source in ("notes", "exam") for t in project.topics
    ):
        # No syllabus to give the order: follow the order the playlists teach in.
        positions = {tid: i for i, tid in enumerate(playlist_topic_order(db, project).order)}
        for topic in project.topics:
            topic.position = positions.get(topic.id, topic.position)
        db.flush()
        db.refresh(project)
    rebuild_recommendations(db, project)
    stage_report("matching", 0.6, "Linking past exam questions to videos")
    link_questions(db, project)
    project.processed_at = utcnow()
    db.commit()

    if not db.scalar(select(Video.id).where(Video.project_id == project.id).limit(1)):
        warnings.append("No videos were found. Add a YouTube playlist to get recommendations.")
    return PipelineResult(warnings=list(dict.fromkeys(warnings)), blocked_videos=blocked)


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
        try:
            meta = client.fetch_video(youtube_id)  # a lone video has no playlist entry
        except YouTubeBlocked:
            raise
        except YouTubeError as exc:
            raise YouTubeError("That video could not be loaded from YouTube.") from exc
        fetched = _fetch_one(client, video.id, youtube_id, True, threading.Event())
        fetched.meta = meta
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
