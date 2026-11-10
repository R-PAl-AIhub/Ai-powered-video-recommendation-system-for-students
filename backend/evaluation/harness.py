"""Run the real pipeline over a labelled course and score the result."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.models import Document, Playlist, Project, User
from app.services.pipeline import run_pipeline
from app.services.youtube import (
    PlaylistMeta,
    Transcript,
    TranscriptSegment,
    VideoMeta,
    YouTubeError,
    set_youtube_client,
    thumbnail_for,
)

from . import os_course
from .os_course import SENTENCE_SECONDS, LabelledPlaylist, LabelledVideo

# Where (seconds) a topic begins inside a video that covers several topics.
EXPECTED_STARTS = {
    "Structure of an OS": 150,
    "Semaphores": 150,
    "Deadlock prevention": 200,
    "Page replacement algorithms": 200,
}
START_TOLERANCE = 100.0


class LabelledYouTube:
    """A YouTube client backed by labelled playlists instead of the network."""

    def __init__(self, playlists: list[LabelledPlaylist]):
        self.playlists = {p.youtube_id: p for p in playlists}
        self.videos: dict[str, tuple[LabelledPlaylist, LabelledVideo]] = {
            v.youtube_id: (p, v) for p in playlists for v in p.videos
        }
        self.search_results: list[VideoMeta] = []
        self.blocked: set[str] = set()  # video ids whose transcript request is refused
        self.calls: list[tuple[str, str]] = []

    def _meta(self, playlist: LabelledPlaylist, video: LabelledVideo, *, full: bool) -> VideoMeta:
        return VideoMeta(
            youtube_id=video.youtube_id,
            title=video.title,
            description=video.description if full else "",
            channel=playlist.channel,
            duration_s=video.seconds,
            view_count=video.views,
            like_count=video.likes if full else None,
            thumbnail_url=thumbnail_for(video.youtube_id),
        )

    def fetch_playlist(self, playlist_id: str, limit: int) -> PlaylistMeta:
        self.calls.append(("playlist", playlist_id))
        playlist = self.playlists.get(playlist_id)
        if playlist is None:
            raise YouTubeError("The playlist does not exist")
        videos = []
        for position, video in enumerate(playlist.videos[:limit]):
            meta = self._meta(playlist, video, full=False)
            meta.position = position
            videos.append(meta)
        return PlaylistMeta(playlist_id, playlist.title, playlist.channel, videos)

    def fetch_video(self, video_id: str) -> VideoMeta:
        self.calls.append(("video", video_id))
        if video_id not in self.videos:
            raise YouTubeError("Video unavailable")
        return self._meta(*self.videos[video_id], full=True)

    def fetch_transcript(self, video_id: str) -> Transcript | None:
        self.calls.append(("transcript", video_id))
        if video_id in self.blocked:
            raise type("IpBlocked", (Exception,), {})("blocked")
        sentences = self.videos[video_id][1].sentences
        if not sentences:
            return None
        return Transcript(
            language="en",
            is_generated=False,
            segments=[
                TranscriptSegment(i * SENTENCE_SECONDS, SENTENCE_SECONDS, sentence)
                for i, sentence in enumerate(sentences)
            ],
        )

    def search(self, query: str, limit: int = 8) -> list[VideoMeta]:
        self.calls.append(("search", query))
        return self.search_results[:limit]


def build_course_project(db: Session, user: User | None = None) -> Project:
    """Create a project holding the labelled OS course (sources only, unprocessed)."""
    if user is None:
        user = User(email="eval@example.com", name="Eval", password_hash="x")
        db.add(user)
        db.flush()
    project = Project(user_id=user.id, name="Operating Systems", subject="Operating Systems")
    db.add(project)
    db.flush()
    for position, playlist in enumerate(os_course.PLAYLISTS):
        db.add(
            Playlist(
                project_id=project.id,
                youtube_id=playlist.youtube_id,
                url=f"https://www.youtube.com/playlist?list={playlist.youtube_id}",
                position=position,
            )
        )
    for kind, name, text in (
        ("syllabus", "syllabus.txt", os_course.SYLLABUS),
        ("exam", "exam-2023.txt", os_course.EXAM),
        ("notes", "unit-3-notes.txt", os_course.NOTES),
    ):
        db.add(
            Document(
                project_id=project.id,
                kind=kind,
                filename=name,
                status="ready",
                text=text,
                size_bytes=len(text),
                page_count=1,
            )
        )
    db.commit()
    db.refresh(project)
    return project


@dataclass
class Report:
    backend: str
    topics: int = 0
    answerable: int = 0
    top1_correct: int = 0
    reciprocal_rank_sum: float = 0.0
    labelled_gaps: int = 0
    predicted_gaps: int = 0
    true_gaps: int = 0
    starts_checked: int = 0
    starts_correct: int = 0
    unlabelled: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    exam_topics: list[str] = field(default_factory=list)  # "name×hits", most asked first
    notes_topics: list[str] = field(default_factory=list)

    @property
    def top1_accuracy(self) -> float:
        return self.top1_correct / self.answerable if self.answerable else 0.0

    @property
    def mrr(self) -> float:
        return self.reciprocal_rank_sum / self.answerable if self.answerable else 0.0

    @property
    def gap_precision(self) -> float:
        return self.true_gaps / self.predicted_gaps if self.predicted_gaps else 1.0

    @property
    def gap_recall(self) -> float:
        return self.true_gaps / self.labelled_gaps if self.labelled_gaps else 1.0

    @property
    def start_accuracy(self) -> float:
        return self.starts_correct / self.starts_checked if self.starts_checked else 1.0

    def summary(self) -> str:
        lines = [
            f"backend            {self.backend}",
            f"topics             {self.topics}",
            f"top-1 accuracy     {self.top1_accuracy:.3f}  ({self.top1_correct}/{self.answerable})",
            f"mean recip. rank   {self.mrr:.3f}",
            f"gap precision      {self.gap_precision:.3f}  ({self.true_gaps}/{self.predicted_gaps})",
            f"gap recall         {self.gap_recall:.3f}  ({self.true_gaps}/{self.labelled_gaps})",
            f"timestamp accuracy {self.start_accuracy:.3f}  ({self.starts_correct}/{self.starts_checked})",
            f"asked in the exam  {', '.join(self.exam_topics) or '-'}",
            f"found in the notes {', '.join(self.notes_topics) or '-'}",
        ]
        lines += [f"  miss: {error}" for error in self.errors]
        lines += [f"  unlabelled topic: {name}" for name in self.unlabelled]
        return "\n".join(lines)


def evaluate(db: Session, backend_name: str) -> Report:
    """Process the labelled course end to end and compare with the expected answers."""
    set_youtube_client(LabelledYouTube(os_course.PLAYLISTS))
    try:
        project = build_course_project(db)
        run_pipeline(db, project, lambda *_: None)
        db.refresh(project)
        report = Report(backend=backend_name, topics=len(project.topics))
        asked = sorted((t for t in project.topics if t.exam_hits), key=lambda t: -t.exam_hits)
        report.exam_topics = [f"{t.name}×{t.exam_hits}" for t in asked]
        report.notes_topics = [t.name for t in project.topics if t.in_notes]
        for topic in project.topics:
            expected = os_course.EXPECTED.get(topic.name)
            if expected is None:
                report.unlabelled.append(topic.name)
                continue
            ranked = [r.video.youtube_id for r in topic.recommendations]
            if not expected:
                report.labelled_gaps += 1
                if not ranked:
                    report.true_gaps += 1
                    report.predicted_gaps += 1
                else:
                    report.predicted_gaps += 0
                    report.errors.append(f"{topic.name!r} should be a gap, got {ranked[0]}")
                continue
            report.answerable += 1
            if not ranked:
                report.predicted_gaps += 1
                report.errors.append(f"{topic.name!r} was flagged as a gap, expected {sorted(expected)}")
                continue
            if ranked[0] in expected:
                report.top1_correct += 1
            else:
                report.errors.append(f"{topic.name!r} -> {ranked[0]}, expected {sorted(expected)}")
            for rank, video_id in enumerate(ranked, 1):
                if video_id in expected:
                    report.reciprocal_rank_sum += 1.0 / rank
                    break
            if topic.name in EXPECTED_STARTS and ranked[0] in expected:
                report.starts_checked += 1
                start = topic.recommendations[0].start_s
                if abs(start - EXPECTED_STARTS[topic.name]) <= START_TOLERANCE:
                    report.starts_correct += 1
                else:
                    report.errors.append(
                        f"{topic.name!r} starts at {start:.0f}s, expected ~{EXPECTED_STARTS[topic.name]}s"
                    )
        return report
    finally:
        set_youtube_client(None)
