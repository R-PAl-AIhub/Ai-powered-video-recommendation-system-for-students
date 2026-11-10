"""Request and response models."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

DocumentKind = Literal["syllabus", "exam", "notes"]
FeedbackKind = Literal["correct", "wrong_topic", "irrelevant", "already_covered"]


class Model(BaseModel):
    model_config = ConfigDict(from_attributes=True)


def _clean(value: str) -> str:
    return " ".join(value.split())


# ------------------------------------------------------------------------- auth


class RegisterIn(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=8, max_length=200)

    _strip = field_validator("name")(_clean)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


class UserOut(Model):
    id: int
    email: str
    name: str


# --------------------------------------------------------------------- projects


class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    subject: str = Field(default="", max_length=160)
    description: str = Field(default="", max_length=2000)

    _strip = field_validator("name", "subject")(_clean)


class ProjectPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    subject: str | None = Field(default=None, max_length=160)
    description: str | None = Field(default=None, max_length=2000)


class PlaylistIn(BaseModel):
    url: str = Field(min_length=2, max_length=500)


class PlaylistOut(Model):
    id: int
    youtube_id: str
    url: str
    title: str
    channel: str
    status: str
    error: str
    video_count: int = 0


class DocumentTextIn(BaseModel):
    kind: DocumentKind
    title: str = Field(default="", max_length=200)
    text: str = Field(min_length=10, max_length=400_000)


class DocumentOut(Model):
    id: int
    kind: str
    filename: str
    size_bytes: int
    status: str
    error: str
    page_count: int
    ocr_pages: int
    characters: int = 0
    preview: str = ""


class JobOut(Model):
    id: int
    status: str
    stage: str
    progress: float
    message: str
    error: str
    warnings: list[str]
    created_at: datetime
    finished_at: datetime | None


class ProcessIn(BaseModel):
    reextract: bool = False  # discard hand-edited topics and extract them again


class ProjectSummary(Model):
    id: int
    name: str
    subject: str
    description: str
    created_at: datetime
    processed_at: datetime | None
    topics: int = 0
    matched: int = 0
    gaps: int = 0
    covered: int = 0
    videos: int = 0
    watched: int = 0
    job: JobOut | None = None


class ProjectDetail(ProjectSummary):
    relevance_threshold: float
    topics_locked: bool
    stale: bool  # sources changed since the last analysis
    playlists: list[PlaylistOut]
    documents: list[DocumentOut]


# ---------------------------------------------------------------- learning path


class VideoOut(Model):
    id: int
    youtube_id: str
    title: str
    channel: str
    duration_s: int
    view_count: int | None
    like_count: int | None
    thumbnail_url: str
    playlist_id: int | None
    playlist_title: str = ""
    playlist_position: int
    transcript_status: str
    transcript_language: str
    source: str
    watched: bool = False


class RecommendationOut(BaseModel):
    video: VideoOut
    rank: int
    relevance: float
    quality: float
    score: float
    start_s: float
    coverage_s: float
    snippet: str
    reasons: list[str]
    url: str
    feedback: FeedbackKind | None = None


class TopicOut(BaseModel):
    id: int
    name: str
    unit: str
    position: int
    source: str
    status: Literal["matched", "gap", "covered"]
    exam_hits: int
    exam_weight: float
    in_notes: bool
    notes_snippet: str
    primary: RecommendationOut | None = None
    alternates: list[RecommendationOut] = []


class PathStats(BaseModel):
    topics: int
    matched: int
    gaps: int
    covered: int
    videos: int
    watched: int
    total_seconds: int
    remaining_seconds: int


class PathOut(BaseModel):
    project_id: int
    relevance_threshold: float
    stats: PathStats
    topics: list[TopicOut]


class TopicIn(BaseModel):
    name: str = Field(min_length=2, max_length=300)
    unit: str = Field(default="", max_length=300)
    after_id: int | None = None  # insert after this topic; None appends

    _strip = field_validator("name", "unit")(_clean)


class TopicPatch(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=300)
    unit: str | None = Field(default=None, max_length=300)
    covered: bool | None = None


class TopicOrderIn(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=1000)


class FeedbackIn(BaseModel):
    topic_id: int
    video_id: int
    kind: FeedbackKind


class WatchedIn(BaseModel):
    watched: bool


class SearchResult(BaseModel):
    video: VideoOut
    relevance: float
    start_s: float
    coverage_s: float
    snippet: str
    url: str


class SearchOut(BaseModel):
    query: str
    found: bool
    message: str
    results: list[SearchResult]
    closest: list[SearchResult]


class YouTubeSearchIn(BaseModel):
    query: str = Field(default="", max_length=200)
    topic_id: int | None = None


class YouTubeResult(BaseModel):
    youtube_id: str
    title: str
    channel: str
    duration_s: int
    view_count: int | None
    thumbnail_url: str
    url: str
    in_project: bool


class AddVideoIn(BaseModel):
    video: str = Field(min_length=5, max_length=500)  # YouTube URL or id
    topic_id: int | None = None  # pin the video to this topic
