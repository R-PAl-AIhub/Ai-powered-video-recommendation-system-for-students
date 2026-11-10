"""Assemble API views (learning path, project summaries) from the database."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..models import Document, Feedback, Job, Playlist, Project, Recommendation, Topic, Video
from ..schemas import (
    DocumentOut,
    JobOut,
    PathOut,
    PathStats,
    PlaylistOut,
    ProjectDetail,
    ProjectSummary,
    RecommendationOut,
    TopicOut,
    VideoOut,
)
from .youtube import watch_url


def video_out(video: Video, playlists: dict[int, Playlist]) -> VideoOut:
    playlist = playlists.get(video.playlist_id) if video.playlist_id else None
    return VideoOut(
        id=video.id,
        youtube_id=video.youtube_id,
        title=video.title,
        channel=video.channel,
        duration_s=video.duration_s,
        view_count=video.view_count,
        like_count=video.like_count,
        thumbnail_url=video.thumbnail_url,
        playlist_id=video.playlist_id,
        playlist_title=playlist.title if playlist else "",
        playlist_position=video.playlist_position,
        transcript_status=video.transcript_status,
        transcript_language=video.transcript_language,
        source=video.source,
        watched=video.watched_at is not None,
    )


def video_url(video: Video, start_s: float, playlists: dict[int, Playlist]) -> str:
    playlist = playlists.get(video.playlist_id) if video.playlist_id else None
    return watch_url(video.youtube_id, start_s, playlist.youtube_id if playlist else None)


def build_path(db: Session, project: Project) -> PathOut:
    playlists = {p.id: p for p in project.playlists}
    topics = db.scalars(
        select(Topic)
        .where(Topic.project_id == project.id)
        .order_by(Topic.position, Topic.id)
        .options(selectinload(Topic.recommendations).joinedload(Recommendation.video))
    ).all()
    feedback = {
        (f.topic_id, f.video_id): f.kind
        for f in db.scalars(select(Feedback).where(Feedback.project_id == project.id))
    }

    out: list[TopicOut] = []
    path_videos: dict[int, Video] = {}
    matched = gaps = covered = 0
    for topic in topics:
        recommendations = [
            RecommendationOut(
                video=video_out(r.video, playlists),
                rank=r.rank,
                relevance=r.relevance,
                quality=r.quality,
                score=r.score,
                start_s=r.start_s,
                coverage_s=r.coverage_s,
                snippet=r.snippet,
                reasons=list(r.reasons or []),
                url=video_url(r.video, r.start_s, playlists),
                feedback=feedback.get((topic.id, r.video_id)),
            )
            for r in topic.recommendations
        ]
        primary = recommendations[0] if recommendations and not topic.covered else None
        if topic.covered:
            status = "covered"
            covered += 1
        elif primary:
            status = "matched"
            matched += 1
            path_videos[primary.video.id] = topic.recommendations[0].video
        else:
            status = "gap"
            gaps += 1
        out.append(
            TopicOut(
                id=topic.id,
                name=topic.name,
                unit=topic.unit,
                position=topic.position,
                source=topic.source,
                status=status,
                exam_hits=topic.exam_hits,
                exam_weight=topic.exam_weight,
                in_notes=topic.in_notes,
                notes_snippet=topic.notes_snippet,
                primary=primary,
                alternates=recommendations[1:] if primary else [],
            )
        )

    total = sum(v.duration_s for v in path_videos.values())
    remaining = sum(v.duration_s for v in path_videos.values() if v.watched_at is None)
    return PathOut(
        project_id=project.id,
        relevance_threshold=project.relevance_threshold,
        stats=PathStats(
            topics=len(topics),
            matched=matched,
            gaps=gaps,
            covered=covered,
            videos=len(path_videos),
            watched=sum(1 for v in path_videos.values() if v.watched_at is not None),
            total_seconds=total,
            remaining_seconds=remaining,
        ),
        topics=out,
    )


def _counts(db: Session, project: Project) -> dict[str, int]:
    topics = db.scalar(select(func.count(Topic.id)).where(Topic.project_id == project.id)) or 0
    covered = (
        db.scalar(
            select(func.count(Topic.id)).where(Topic.project_id == project.id, Topic.covered)
        )
        or 0
    )
    matched = (
        db.scalar(
            select(func.count(Recommendation.id))
            .join(Topic, Topic.id == Recommendation.topic_id)
            .where(
                Recommendation.project_id == project.id,
                Recommendation.rank == 0,
                Topic.covered.is_(False),
            )
        )
        or 0
    )
    videos = db.scalar(select(func.count(Video.id)).where(Video.project_id == project.id)) or 0
    watched = (
        db.scalar(
            select(func.count(Video.id)).where(
                Video.project_id == project.id, Video.watched_at.is_not(None)
            )
        )
        or 0
    )
    return {
        "topics": topics,
        "matched": matched,
        "covered": covered,
        "gaps": max(topics - matched - covered, 0),
        "videos": videos,
        "watched": watched,
    }


def _job_out(db: Session, project_id: int) -> JobOut | None:
    job = db.scalar(select(Job).where(Job.project_id == project_id).order_by(Job.id.desc()))
    return JobOut.model_validate(job) if job else None


def project_summary(db: Session, project: Project) -> ProjectSummary:
    return ProjectSummary(
        id=project.id,
        name=project.name,
        subject=project.subject,
        description=project.description,
        created_at=project.created_at,
        processed_at=project.processed_at,
        job=_job_out(db, project.id),
        **_counts(db, project),
    )


def document_out(document: Document) -> DocumentOut:
    return DocumentOut(
        id=document.id,
        kind=document.kind,
        filename=document.filename,
        size_bytes=document.size_bytes,
        status=document.status,
        error=document.error,
        page_count=document.page_count,
        ocr_pages=document.ocr_pages,
        characters=len(document.text),
        preview=document.text[:400],
    )


def project_detail(db: Session, project: Project) -> ProjectDetail:
    per_playlist = dict(
        db.execute(
            select(Video.playlist_id, func.count(Video.id))
            .where(Video.project_id == project.id)
            .group_by(Video.playlist_id)
        ).all()
    )
    stale = project.processed_at is None or (
        project.sources_changed_at is not None and project.sources_changed_at > project.processed_at
    )
    has_sources = bool(project.playlists or project.documents)
    return ProjectDetail(
        id=project.id,
        name=project.name,
        subject=project.subject,
        description=project.description,
        created_at=project.created_at,
        processed_at=project.processed_at,
        relevance_threshold=project.relevance_threshold,
        topics_locked=project.topics_locked,
        stale=stale and has_sources,
        job=_job_out(db, project.id),
        playlists=[
            PlaylistOut(
                id=p.id,
                youtube_id=p.youtube_id,
                url=p.url,
                title=p.title,
                channel=p.channel,
                status=p.status,
                error=p.error,
                video_count=per_playlist.get(p.id, 0),
            )
            for p in project.playlists
        ],
        documents=[document_out(d) for d in project.documents],
        **_counts(db, project),
    )
