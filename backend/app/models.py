"""SQLAlchemy models.

A *project* is one course. It owns playlists (the video pool), documents
(syllabus / exam papers / notes), the extracted topics, and the recommendations
that link topics to videos.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    projects: Mapped[list[Project]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    subject: Mapped[str] = mapped_column(String(160), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    # Relevance a video needs to count as covering a topic. Starts at the default and
    # is re-learned from the student's feedback.
    relevance_threshold: Mapped[float] = mapped_column(Float, default=0.5)
    # True once the student edits topics by hand; re-processing then keeps them.
    topics_locked: Mapped[bool] = mapped_column(Boolean, default=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Bumped whenever a playlist or document is added or removed; newer than
    # processed_at means the learning path is out of date.
    sources_changed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    user: Mapped[User] = relationship(back_populates="projects")
    playlists: Mapped[list[Playlist]] = relationship(
        back_populates="project", cascade="all, delete-orphan", order_by="Playlist.position"
    )
    videos: Mapped[list[Video]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    documents: Mapped[list[Document]] = relationship(
        back_populates="project", cascade="all, delete-orphan", order_by="Document.id"
    )
    topics: Mapped[list[Topic]] = relationship(
        back_populates="project", cascade="all, delete-orphan", order_by="Topic.position"
    )
    jobs: Mapped[list[Job]] = relationship(back_populates="project", cascade="all, delete-orphan")
    feedback: Mapped[list[Feedback]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class Playlist(Base):
    __tablename__ = "playlists"
    __table_args__ = (UniqueConstraint("project_id", "youtube_id", name="uq_playlist_project"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    youtube_id: Mapped[str] = mapped_column(String(64))
    url: Mapped[str] = mapped_column(String(500))
    title: Mapped[str] = mapped_column(String(300), default="")
    channel: Mapped[str] = mapped_column(String(200), default="")
    position: Mapped[int] = mapped_column(Integer, default=0)  # student's priority order
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|ready|error
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    project: Mapped[Project] = relationship(back_populates="playlists")
    videos: Mapped[list[Video]] = relationship(back_populates="playlist")


class Video(Base):
    __tablename__ = "videos"
    __table_args__ = (UniqueConstraint("project_id", "youtube_id", name="uq_video_project"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    playlist_id: Mapped[int | None] = mapped_column(
        ForeignKey("playlists.id", ondelete="SET NULL"), nullable=True, index=True
    )
    youtube_id: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(500), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    channel: Mapped[str] = mapped_column(String(200), default="")
    duration_s: Mapped[int] = mapped_column(Integer, default=0)
    view_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    like_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    comment_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    thumbnail_url: Mapped[str] = mapped_column(String(500), default="")
    playlist_position: Mapped[int] = mapped_column(Integer, default=0)
    source: Mapped[str] = mapped_column(String(20), default="playlist")  # playlist|search
    # pending|ok|none|error — "none" means YouTube has no captions for this video.
    transcript_status: Mapped[str] = mapped_column(String(20), default="pending")
    transcript_language: Mapped[str] = mapped_column(String(40), default="")
    embedded_with: Mapped[str] = mapped_column(String(120), default="")  # embedder name
    watched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    project: Mapped[Project] = relationship(back_populates="videos")
    playlist: Mapped[Playlist | None] = relationship(back_populates="videos")
    chunks: Mapped[list[VideoChunk]] = relationship(
        back_populates="video", cascade="all, delete-orphan", order_by="VideoChunk.idx"
    )


class VideoChunk(Base):
    """A window of a video's text. idx 0 is always the title/description chunk."""

    __tablename__ = "video_chunks"
    __table_args__ = (Index("ix_chunk_video_idx", "video_id", "idx"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"), index=True)
    idx: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(12), default="transcript")  # meta|transcript
    start_s: Mapped[float] = mapped_column(Float, default=0.0)
    end_s: Mapped[float] = mapped_column(Float, default=0.0)
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)

    video: Mapped[Video] = relationship(back_populates="chunks")


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(12))  # syllabus|exam|notes
    filename: Mapped[str] = mapped_column(String(300))
    content_type: Mapped[str] = mapped_column(String(120), default="")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    storage_name: Mapped[str] = mapped_column(String(80), default="")  # "" for pasted text
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|ready|error
    error: Mapped[str] = mapped_column(Text, default="")
    text: Mapped[str] = mapped_column(Text, default="")
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    ocr_pages: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    project: Mapped[Project] = relationship(back_populates="documents")


class Topic(Base):
    __tablename__ = "topics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    unit: Mapped[str] = mapped_column(String(300), default="")
    name: Mapped[str] = mapped_column(String(300))
    position: Mapped[int] = mapped_column(Integer, default=0)  # global order in the path
    source: Mapped[str] = mapped_column(String(12), default="syllabus")  # syllabus|notes|exam|manual
    exam_hits: Mapped[int] = mapped_column(Integer, default=0)  # past questions on this topic
    exam_weight: Mapped[float] = mapped_column(Float, default=0.0)  # 0..1, relative frequency
    in_notes: Mapped[bool] = mapped_column(Boolean, default=False)
    notes_snippet: Mapped[str] = mapped_column(Text, default="")
    covered: Mapped[bool] = mapped_column(Boolean, default=False)  # student already knows it
    embedding: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    embedded_with: Mapped[str] = mapped_column(String(120), default="")

    project: Mapped[Project] = relationship(back_populates="topics")
    recommendations: Mapped[list[Recommendation]] = relationship(
        back_populates="topic", cascade="all, delete-orphan", order_by="Recommendation.rank"
    )


class Recommendation(Base):
    """A video suggested for a topic. rank 0 is the pick placed in the learning path."""

    __tablename__ = "recommendations"
    __table_args__ = (UniqueConstraint("topic_id", "video_id", name="uq_rec_topic_video"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id", ondelete="CASCADE"), index=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"), index=True)
    rank: Mapped[int] = mapped_column(Integer, default=0)
    relevance: Mapped[float] = mapped_column(Float, default=0.0)  # content match, 0..1
    quality: Mapped[float] = mapped_column(Float, default=0.0)  # metadata quality, 0..1
    score: Mapped[float] = mapped_column(Float, default=0.0)  # fuzzy-combined, 0..1
    start_s: Mapped[float] = mapped_column(Float, default=0.0)  # where the topic starts
    end_s: Mapped[float] = mapped_column(Float, default=0.0)  # where it ends; 0 = end of video
    coverage_s: Mapped[float] = mapped_column(Float, default=0.0)  # seconds spent on it
    snippet: Mapped[str] = mapped_column(Text, default="")
    reasons: Mapped[list[Any]] = mapped_column(JSON, default=list)

    topic: Mapped[Topic] = relationship(back_populates="recommendations")
    video: Mapped[Video] = relationship()


class Question(Base):
    """A question from a past exam paper, linked to the topic it is about and to
    the moment in a video that answers it."""

    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer, default=0)  # order within the paper
    text: Mapped[str] = mapped_column(Text)
    topic_id: Mapped[int | None] = mapped_column(
        ForeignKey("topics.id", ondelete="SET NULL"), nullable=True, index=True
    )
    video_id: Mapped[int | None] = mapped_column(
        ForeignKey("videos.id", ondelete="SET NULL"), nullable=True
    )
    relevance: Mapped[float] = mapped_column(Float, default=0.0)
    start_s: Mapped[float] = mapped_column(Float, default=0.0)
    end_s: Mapped[float] = mapped_column(Float, default=0.0)
    snippet: Mapped[str] = mapped_column(Text, default="")

    document: Mapped[Document] = relationship()
    topic: Mapped[Topic | None] = relationship()
    video: Mapped[Video | None] = relationship()


class RerankScore(Base):
    """Cached cross-encoder score for a (topic wording, video chunk) pair, so the
    path can be re-planned after feedback without running the model again."""

    __tablename__ = "rerank_scores"
    __table_args__ = (UniqueConstraint("topic_id", "chunk_id", name="uq_rerank_topic_chunk"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id", ondelete="CASCADE"), index=True)
    chunk_id: Mapped[int] = mapped_column(
        ForeignKey("video_chunks.id", ondelete="CASCADE"), index=True
    )
    query_hash: Mapped[str] = mapped_column(String(16))
    model: Mapped[str] = mapped_column(String(120))
    score: Mapped[float] = mapped_column(Float)


class Feedback(Base):
    __tablename__ = "feedback"
    __table_args__ = (UniqueConstraint("topic_id", "video_id", name="uq_feedback_topic_video"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id", ondelete="CASCADE"), index=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"), index=True)
    # correct | wrong_topic | irrelevant | already_covered
    kind: Mapped[str] = mapped_column(String(20))
    relevance: Mapped[float] = mapped_column(Float, default=0.0)  # relevance when judged
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    project: Mapped[Project] = relationship(back_populates="feedback")


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (Index("ix_job_status", "status", "id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(20), default="process")
    options: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    # queued | running | done | failed | scheduled (an automatic retry waiting for run_after)
    status: Mapped[str] = mapped_column(String(12), default="queued")
    run_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    stage: Mapped[str] = mapped_column(String(40), default="queued")
    progress: Mapped[float] = mapped_column(Float, default=0.0)  # 0..1
    message: Mapped[str] = mapped_column(String(500), default="")
    error: Mapped[str] = mapped_column(Text, default="")
    warnings: Mapped[list[Any]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped[Project] = relationship(back_populates="jobs")
