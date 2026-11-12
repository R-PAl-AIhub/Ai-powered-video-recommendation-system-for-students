"""When YouTube refuses caption requests and speech recognition is on, the videos
are listened to instead (``_fetch`` in ``app/services/pipeline.py``), and the
caption service is left alone once it is clearly refusing."""

from __future__ import annotations

from app.services.asr import set_transcriber
from app.services.pipeline import BLOCK_ABORT_AFTER
from app.services.youtube import Transcript, TranscriptSegment
from tests.conftest import make_course, register
from tests.test_api import path_of, primary_id


class FakeWhisper:
    """Hears exactly what the labelled video says; ``deaf`` ids yield nothing."""

    name = "fake"

    def __init__(self, youtube, deaf: frozenset[str] = frozenset()):
        self.youtube, self.deaf, self.heard = youtube, deaf, []

    def transcribe(self, video_id, duration_s=0, hint=""):
        self.heard.append(video_id)
        sentences = self.youtube.videos[video_id][1].sentences
        if video_id in self.deaf or not sentences:
            return None
        segments = [TranscriptSegment(i * 30.0, 30.0, s) for i, s in enumerate(sentences)]
        return Transcript(language="en", is_generated=True, segments=segments)


def _job(client, project_id: int) -> dict:
    return client.get(f"/api/projects/{project_id}/job").json()


def test_blocked_captions_are_replaced_by_listening(client, youtube):
    # Every video that has something to hear is refused its captions.
    youtube.blocked = {vid for vid, (_, video) in youtube.videos.items() if video.sentences}
    whisper = FakeWhisper(youtube)
    set_transcriber(whisper)
    try:
        register(client)
        project_id = make_course(client)
    finally:
        set_transcriber(None)

    job = _job(client, project_id)
    assert job["status"] == "done"
    # Only the one video with nothing to hear is left for a retry: once captions
    # are being refused, nobody can tell whether it has any.
    limited = [w for w in job["warnings"] if "temporarily limiting" in w]
    assert len(limited) == 1 and "so 1 video is matched on title only" in limited[0]
    assert set(whisper.heard) >= youtube.blocked
    # Transcripts, not just titles, drive the match.
    path = path_of(client, project_id)
    assert primary_id(path, "Banker's algorithm") == "osBankers08"
    # Once YouTube is clearly refusing, captions are not asked for any more.
    asked = [c for c in youtube.calls if c[0] == "transcript"]
    assert BLOCK_ABORT_AFTER <= len(asked) < len(youtube.videos)


def test_a_blocked_video_that_cannot_be_heard_is_retried_later(client, youtube):
    youtube.blocked = set(youtube.videos)
    whisper = FakeWhisper(youtube, deaf=frozenset({"osBankers08"}))
    set_transcriber(whisper)
    try:
        register(client)
        project_id = make_course(client)
    finally:
        set_transcriber(None)

    job = _job(client, project_id)
    assert job["status"] == "done"
    assert any("temporarily limiting" in warning for warning in job["warnings"])
    assert job["retry_at"] is not None


def test_listening_is_not_used_when_captions_work(client, youtube):
    whisper = FakeWhisper(youtube)
    set_transcriber(whisper)
    try:
        register(client)
        make_course(client)
    finally:
        set_transcriber(None)
    with_captions = {vid for vid, (_, video) in youtube.videos.items() if video.sentences}
    assert not set(whisper.heard) & with_captions


def _english_only(monkeypatch):
    """Make the (multilingual) test embedder behave like the default English model."""
    from app.services import pipeline

    monkeypatch.setattr(
        pipeline,
        "transcript_usable",
        lambda t: t.language.startswith("en") or t.language.endswith("→en"),
    )


def _hindi_captions(youtube, video_id: str):
    """YouTube now sends this video's captions in Hindi."""
    real = youtube.fetch_transcript

    def fetch(requested: str):
        transcript = real(requested)
        if requested == video_id and transcript is not None:
            transcript.language = "hi"
        return transcript

    youtube.fetch_transcript = fetch


def _status(client, project_id: int, youtube_id: str) -> str:
    path = path_of(client, project_id)
    for topic in path["topics"]:
        for pick in [topic["primary"], *topic["alternates"]]:
            if pick and pick["video"]["youtube_id"] == youtube_id:
                return pick["video"]["transcript_status"]
    waiting = client.get(f"/api/projects/{project_id}/videos/untranscribed").json()
    return next(v["transcript_status"] for v in waiting if v["youtube_id"] == youtube_id)


def test_captions_in_an_unreadable_language_are_listened_to(client, youtube, monkeypatch):
    _english_only(monkeypatch)
    _hindi_captions(youtube, "osBankers08")

    class Translating(FakeWhisper):
        def transcribe(self, video_id, duration_s=0, hint=""):
            heard = super().transcribe(video_id, duration_s, hint)
            if heard is not None:
                heard.language = "hi→en"  # Whisper translates as it listens
            return heard

    whisper = Translating(youtube)
    set_transcriber(whisper)
    try:
        register(client)
        project_id = make_course(client)
    finally:
        set_transcriber(None)
    assert "osBankers08" in whisper.heard
    assert _status(client, project_id, "osBankers08") == "ok"
    assert primary_id(path_of(client, project_id), "Banker's algorithm") == "osBankers08"


def test_unreadable_captions_without_listening_are_marked_foreign(client, youtube, monkeypatch):
    _english_only(monkeypatch)
    _hindi_captions(youtube, "osBankers08")
    register(client)
    project_id = make_course(client)
    assert _status(client, project_id, "osBankers08") == "foreign"
    warnings = client.get(f"/api/projects/{project_id}/job").json()["warnings"]
    assert any("only have captions in hi" in warning for warning in warnings)


# ----------------------------------------------- listening is the default, in two runs


def _process(client, project_id: int) -> None:
    assert client.post(f"/api/projects/{project_id}/process").status_code == 202


def _run_one_job() -> None:
    from app.db import SessionLocal
    from app.services import jobs

    with SessionLocal() as session:
        job = jobs.claim_next(session)
        assert job is not None
        jobs.execute(session, job)


def _without_captions(youtube) -> set[str]:
    return {vid for vid, (_, video) in youtube.videos.items() if not video.sentences}


class Audible(FakeWhisper):
    """Also hears the videos that have no captions at all."""

    def transcribe(self, video_id, duration_s=0, hint=""):
        if self.youtube.videos[video_id][1].sentences:
            return super().transcribe(video_id, duration_s, hint)
        self.heard.append(video_id)
        segments = [TranscriptSegment(0.0, 30.0, "Welcome to this lecture of the course.")]
        return Transcript(language="en", is_generated=True, segments=segments)


def test_listening_is_on_unless_switched_off():
    from app.config import Settings

    assert Settings.model_fields["asr_enabled"].default is True
    assert Settings.model_fields["asr_model"].default == "small"


def test_the_path_is_built_first_and_listening_follows(client, youtube):
    from tests.conftest import run_jobs

    quiet = _without_captions(youtube)
    assert quiet
    register(client)
    project_id = make_course(client)  # listening is off here: those stay "none"
    whisper = Audible(youtube)
    set_transcriber(whisper)
    try:
        _process(client, project_id)
        _run_one_job()
        # The first run only reads captions, says what comes next, and queues it.
        assert whisper.heard == []
        waiting = _job(client, project_id)
        assert waiting["status"] == "queued"
        assert "listen" in waiting["message"]
        assert path_of(client, project_id)["topics"]  # the path is already there
        # The second run listens to exactly the videos without captions.
        assert run_jobs() == 1
    finally:
        set_transcriber(None)
    assert set(whisper.heard) == quiet
    assert _job(client, project_id)["status"] == "done"
    left = client.get(f"/api/projects/{project_id}/videos/untranscribed").json()
    assert not {video["youtube_id"] for video in left} & quiet


def test_a_video_with_nothing_to_hear_is_not_listened_to_twice(client, youtube):
    from tests.conftest import run_jobs

    quiet = _without_captions(youtube)
    whisper = FakeWhisper(youtube)  # hears nothing in a video without sentences
    set_transcriber(whisper)
    try:
        register(client)
        project_id = make_course(client)
        assert sorted(whisper.heard) == sorted(quiet)
        warnings = _job(client, project_id)["warnings"]
        assert any("Nothing could be heard" in warning for warning in warnings)
        left = client.get(f"/api/projects/{project_id}/videos/untranscribed").json()
        assert {v["youtube_id"]: v["transcript_status"] for v in left} == dict.fromkeys(
            quiet, "silent"
        )
        # Updating the path again neither listens again nor queues a listening run.
        _process(client, project_id)
        assert run_jobs() == 1
        assert sorted(whisper.heard) == sorted(quiet)
    finally:
        set_transcriber(None)


def test_without_ffmpeg_the_app_still_works(monkeypatch):
    import shutil

    from app.config import get_settings
    from app.services import asr

    monkeypatch.setattr(get_settings(), "asr_enabled", True)
    monkeypatch.setattr(asr, "_available", None)
    monkeypatch.setattr(shutil, "which", lambda name: None)
    assert asr.get_transcriber() is None


def test_whisper_is_told_the_title_and_subject(client, youtube):
    """The title and subject steer the spelling of terms ("closure", not "closer")."""
    hints: dict[str, str] = {}

    class Noting(FakeWhisper):
        def transcribe(self, video_id, duration_s=0, hint=""):
            hints[video_id] = hint
            return super().transcribe(video_id, duration_s, hint)

    set_transcriber(Noting(youtube))
    try:
        register(client)
        make_course(client)
    finally:
        set_transcriber(None)
    assert hints
    for video_id, hint in hints.items():
        assert youtube.videos[video_id][1].title in hint
        assert "Operating Systems" in hint


def test_videos_the_app_will_listen_to_are_flagged(client, youtube):
    """The screens use the flag to say "nothing for you to do" instead of asking
    the student to paste a transcript."""
    register(client)
    project_id = make_course(client)  # listening is off: nothing is flagged
    url = f"/api/projects/{project_id}/videos/untranscribed"
    waiting = client.get(url).json()
    assert waiting and not any(video["listening"] for video in waiting)
    set_transcriber(FakeWhisper(youtube))
    try:
        assert all(video["listening"] for video in client.get(url).json())
    finally:
        set_transcriber(None)
