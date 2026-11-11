"""The learning path: topics, feedback, progress, search and YouTube gap-filling."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..deps import idle_project, owned_project
from ..models import Feedback, Project, Recommendation, Topic, Video, utcnow
from ..schemas import (
    AddVideoIn,
    FeedbackIn,
    PathOut,
    QuestionsOut,
    SearchOut,
    SearchResult,
    ThemeOut,
    TopicIn,
    TopicOrderIn,
    TopicPatch,
    WatchedIn,
    YouTubeResult,
    YouTubeSearchIn,
)
from ..services.matching import Match
from ..services.path import build_path, build_questions, video_out, video_url
from ..services.pipeline import ingest_single_video
from ..services.recommend import (
    playlist_topic_order,
    rebuild_recommendations,
    relearn_threshold,
    search_project,
    unit_title,
)
from ..services.topic_map import build_topic_map
from ..services.youtube import YouTubeError, get_youtube_client, parse_video_id, watch_url

router = APIRouter(prefix="/projects/{project_id}", tags=["learning"])


def _topic(db: Session, project: Project, topic_id: int) -> Topic:
    topic = db.get(Topic, topic_id)
    if topic is None or topic.project_id != project.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Topic not found")
    return topic


def _video(db: Session, project: Project, video_id: int) -> Video:
    video = db.get(Video, video_id)
    if video is None or video.project_id != project.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Video not found")
    return video


def _refresh(db: Session, project: Project) -> PathOut:
    """Recompute recommendations after a change and return the new path."""
    db.flush()
    db.refresh(project)
    rebuild_recommendations(db, project)
    db.commit()
    return build_path(db, project)


@router.get("/path", response_model=PathOut)
def get_path(project: Project = Depends(owned_project), db: Session = Depends(get_db)):
    return build_path(db, project)


@router.get("/topic-map", response_model=list[ThemeOut])
def get_topic_map(project: Project = Depends(owned_project), db: Session = Depends(get_db)):
    """The themes the playlists cover (LDA), with their videos and syllabus topics."""
    playlists = {p.id: p for p in project.playlists}
    names = {t.id: t.name for t in project.topics}
    themes = build_topic_map(db, project)
    videos = {v.id: v for v in db.scalars(select(Video).where(Video.project_id == project.id))}
    return [
        ThemeOut(
            words=theme.words,
            videos=[
                video_out(videos[vid], playlists)
                for vid in sorted(theme.video_ids, key=lambda i: videos[i].playlist_position)
            ][:12],
            topics=[names[tid] for tid in theme.topic_ids],
        )
        for theme in themes
    ]


@router.get("/questions", response_model=QuestionsOut)
def get_questions(project: Project = Depends(owned_project), db: Session = Depends(get_db)):
    """Past exam questions, each linked to its topic and to the video moment that
    explains it."""
    return build_questions(db, project)


# ----------------------------------------------------------------------- topics


@router.post("/topics", response_model=PathOut, status_code=status.HTTP_201_CREATED)
def add_topic(
    body: TopicIn, project: Project = Depends(idle_project), db: Session = Depends(get_db)
):
    topics = list(project.topics)
    if len(topics) >= get_settings().max_topics_per_project:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "This project has reached its topic limit"
        )
    if any(t.name.lower() == body.name.lower() for t in topics):
        raise HTTPException(status.HTTP_409_CONFLICT, "This topic is already in the list")
    index = len(topics)
    unit = body.unit
    if body.after_id is not None:
        anchor = _topic(db, project, body.after_id)
        index = topics.index(anchor) + 1
        unit = unit or anchor.unit
    topic = Topic(project_id=project.id, name=body.name, unit=unit, source="manual")
    topics.insert(index, topic)
    db.add(topic)
    for position, item in enumerate(topics):
        item.position = position
    project.topics_locked = True
    return _refresh(db, project)


@router.patch("/topics/{topic_id}", response_model=PathOut)
def update_topic(
    topic_id: int,
    body: TopicPatch,
    project: Project = Depends(idle_project),
    db: Session = Depends(get_db),
):
    topic = _topic(db, project, topic_id)
    if body.name is not None and body.name != topic.name:
        topic.name = " ".join(body.name.split())
        topic.embedding = None
        project.topics_locked = True
    if body.unit is not None and body.unit != topic.unit:
        topic.unit = " ".join(body.unit.split())
        topic.embedding = None
        project.topics_locked = True
    if body.covered is not None:
        topic.covered = body.covered
    return _refresh(db, project)


@router.delete("/topics/{topic_id}", response_model=PathOut)
def delete_topic(
    topic_id: int, project: Project = Depends(idle_project), db: Session = Depends(get_db)
):
    db.delete(_topic(db, project, topic_id))
    project.topics_locked = True
    return _refresh(db, project)


@router.post("/topics/order/from-playlists", response_model=PathOut)
def order_topics_like_playlists(
    project: Project = Depends(idle_project), db: Session = Depends(get_db)
):
    """Reorder the path the way the student's playlists teach the topics."""
    mined = playlist_topic_order(db, project)
    by_id = {t.id: t for t in project.topics}
    for position, topic_id in enumerate(mined.order):
        by_id[topic_id].position = position
    project.topics_locked = True
    return _refresh(db, project)


@router.put("/topics/order", response_model=PathOut)
def reorder_topics(
    body: TopicOrderIn, project: Project = Depends(idle_project), db: Session = Depends(get_db)
):
    """Set the order of the path. Ids not listed keep their relative order at the end."""
    by_id = {t.id: t for t in project.topics}
    if len(set(body.ids)) != len(body.ids) or any(i not in by_id for i in body.ids):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Unknown or repeated topic id")
    listed = set(body.ids)
    ordered = [by_id[i] for i in body.ids] + [t for t in project.topics if t.id not in listed]
    for position, topic in enumerate(ordered):
        topic.position = position
    project.topics_locked = True
    return _refresh(db, project)


# --------------------------------------------------------------------- feedback


@router.post("/feedback", response_model=PathOut)
def give_feedback(
    body: FeedbackIn, project: Project = Depends(idle_project), db: Session = Depends(get_db)
):
    """Record the student's judgement of a recommendation and re-plan the path.

    correct          pin this video to the topic
    wrong_topic      never suggest this video for this topic again
    irrelevant       remove this video from the whole project
    already_covered  the student already knows this topic; drop it from the path
    """
    topic = _topic(db, project, body.topic_id)
    video = _video(db, project, body.video_id)
    feedback = db.scalar(
        select(Feedback).where(Feedback.topic_id == topic.id, Feedback.video_id == video.id)
    )
    recommendation = db.scalar(
        select(Recommendation).where(
            Recommendation.topic_id == topic.id, Recommendation.video_id == video.id
        )
    )
    relevance = recommendation.relevance if recommendation else 0.0
    if feedback is None:
        feedback = Feedback(
            project_id=project.id, topic_id=topic.id, video_id=video.id, relevance=relevance
        )
        db.add(feedback)
    elif recommendation is not None:
        feedback.relevance = relevance
    was_covered = feedback.kind == "already_covered"
    feedback.kind = body.kind
    if body.kind == "already_covered":
        topic.covered = True
    elif was_covered:
        topic.covered = False
    db.flush()
    relearn_threshold(db, project)
    return _refresh(db, project)


@router.delete("/feedback", response_model=PathOut)
def undo_feedback(
    topic_id: int = Query(...),
    video_id: int = Query(...),
    project: Project = Depends(idle_project),
    db: Session = Depends(get_db),
):
    feedback = db.scalar(
        select(Feedback).where(
            Feedback.project_id == project.id,
            Feedback.topic_id == topic_id,
            Feedback.video_id == video_id,
        )
    )
    if feedback is not None:
        if feedback.kind == "already_covered":
            _topic(db, project, topic_id).covered = False
        db.delete(feedback)
        db.flush()
        relearn_threshold(db, project)
    return _refresh(db, project)


@router.put("/videos/{video_id}/watched", status_code=status.HTTP_204_NO_CONTENT)
def set_watched(
    video_id: int,
    body: WatchedIn,
    project: Project = Depends(owned_project),
    db: Session = Depends(get_db),
):
    video = _video(db, project, video_id)
    video.watched_at = utcnow() if body.watched else None
    db.commit()


# ----------------------------------------------------------------------- search


def _result(db: Session, project: Project, match: Match, playlists: dict) -> SearchResult:
    video = db.get(Video, match.video_id)
    return SearchResult(
        video=video_out(video, playlists),
        relevance=round(match.relevance, 4),
        start_s=match.start_s,
        end_s=match.end_s,
        coverage_s=match.coverage_s,
        snippet=match.snippet,
        url=video_url(video, match.start_s, playlists),
    )


@router.get("/search", response_model=SearchOut)
def search(
    q: str = Query(..., min_length=2, max_length=200),
    project: Project = Depends(owned_project),
    db: Session = Depends(get_db),
):
    """Find videos in the project's playlists for a topic the student types in."""
    query = " ".join(q.split())
    outcome = search_project(db, project, query)
    playlists = {p.id: p for p in project.playlists}
    if outcome.found:
        count = len(outcome.matches)
        message = f"{count} video{'s' if count != 1 else ''} found for “{query}”"
    else:
        message = f"Video not found for “{query}”"
    return SearchOut(
        query=query,
        found=outcome.found,
        message=message,
        results=[_result(db, project, m, playlists) for m in outcome.matches],
        closest=[_result(db, project, m, playlists) for m in outcome.closest],
    )


@router.post("/youtube/search", response_model=list[YouTubeResult])
def youtube_search(
    body: YouTubeSearchIn, project: Project = Depends(owned_project), db: Session = Depends(get_db)
):
    """Search all of YouTube, for topics the student's playlists do not cover."""
    query = " ".join(body.query.split())
    if body.topic_id is not None:
        topic = _topic(db, project, body.topic_id)
        parts = [topic.name, unit_title(topic.unit), project.subject]
        query = " ".join(dict.fromkeys(p for p in parts if p))
    if len(query) < 2:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Enter something to search for")
    try:
        found = get_youtube_client().search(f"{query} lecture", limit=8)
    except YouTubeError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"YouTube search failed: {exc}") from None
    existing = set(db.scalars(select(Video.youtube_id).where(Video.project_id == project.id)))
    return [
        YouTubeResult(
            youtube_id=v.youtube_id,
            title=v.title,
            channel=v.channel,
            duration_s=v.duration_s,
            view_count=v.view_count,
            thumbnail_url=v.thumbnail_url,
            url=watch_url(v.youtube_id),
            in_project=v.youtube_id in existing,
        )
        for v in found
        if v.duration_s == 0 or v.duration_s >= 90  # skip Shorts
    ]


@router.post("/videos", response_model=PathOut, status_code=status.HTTP_201_CREATED)
def add_video(
    body: AddVideoIn, project: Project = Depends(idle_project), db: Session = Depends(get_db)
):
    """Add a single video to the project, optionally pinning it to a topic."""
    youtube_id = parse_video_id(body.video)
    if youtube_id is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "That does not look like a YouTube video link"
        )
    topic = _topic(db, project, body.topic_id) if body.topic_id is not None else None
    try:
        video = ingest_single_video(db, project, youtube_id)
    except YouTubeError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from None
    if topic is not None:
        feedback = db.scalar(
            select(Feedback).where(Feedback.topic_id == topic.id, Feedback.video_id == video.id)
        )
        if feedback is None:
            feedback = Feedback(project_id=project.id, topic_id=topic.id, video_id=video.id)
            db.add(feedback)
        feedback.kind = "correct"
        topic.covered = False
    return _refresh(db, project)
