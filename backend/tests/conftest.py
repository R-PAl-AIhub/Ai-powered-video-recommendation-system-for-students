"""Shared test setup: an isolated database, a fake YouTube, and no model downloads."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

# Settings are read when the app is imported, so the environment comes first.
_WORKDIR = Path(tempfile.mkdtemp(prefix="recommender-tests-"))
os.environ.update(
    ENVIRONMENT="test",
    # CI runs the suite a second time on PostgreSQL by setting TEST_DATABASE_URL.
    DATABASE_URL=os.environ.get("TEST_DATABASE_URL")
    or f"sqlite:///{(_WORKDIR / 'test.db').as_posix()}",
    DATA_DIR=str(_WORKDIR),
    EMBEDDING_BACKEND="hash",  # deterministic, lexical, instant
    RERANKER_MODEL="",
    RUN_WORKER="false",  # tests run jobs inline
    OCR_BACKEND="none",
    ASR_ENABLED="false",  # tests that listen install a fake transcriber
    YOUTUBE_REQUEST_INTERVAL="0",
    SECRET_KEY="test-secret-key-that-is-long-enough-0123456789",
    AUTH_RATE_LIMIT_PER_MINUTE="1000",
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.routers import auth  # noqa: E402
from app.services import jobs, matching, recommend  # noqa: E402
from app.services.youtube import set_youtube_client  # noqa: E402
from evaluation import os_course  # noqa: E402
from evaluation.harness import LabelledYouTube  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_state():
    """Every test starts with empty tables, empty caches and a fake YouTube."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    matching._cache.clear()
    recommend._passages.clear()
    auth.limiter.reset()
    fake = LabelledYouTube(os_course.PLAYLISTS)
    set_youtube_client(fake)
    yield fake
    set_youtube_client(None)


@pytest.fixture
def youtube(fresh_state) -> LabelledYouTube:
    return fresh_state


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session


def register(client: TestClient, email: str = "student@example.com", name: str = "Student"):
    response = client.post(
        "/api/auth/register", json={"email": email, "name": name, "password": "correct-horse-9"}
    )
    assert response.status_code == 201, response.text
    return response.json()


def run_jobs() -> int:
    """Run every queued job, as the background worker would."""
    ran = 0
    with SessionLocal() as session:
        while (job := jobs.claim_next(session)) is not None:
            jobs.execute(session, job)
            ran += 1
    return ran


def make_course(client: TestClient) -> int:
    """Create a project holding the labelled OS course and process it."""
    project = client.post(
        "/api/projects", json={"name": "Operating Systems", "subject": "Operating Systems"}
    ).json()
    project_id = project["id"]
    for playlist in os_course.PLAYLISTS:
        url = f"https://www.youtube.com/playlist?list={playlist.youtube_id}"
        assert client.post(f"/api/projects/{project_id}/playlists", json={"url": url}).status_code == 201
    for kind, text in (
        ("syllabus", os_course.SYLLABUS),
        ("exam", os_course.EXAM),
        ("notes", os_course.NOTES),
    ):
        response = client.post(
            f"/api/projects/{project_id}/documents/text", json={"kind": kind, "text": text}
        )
        assert response.status_code == 201, response.text
    assert client.post(f"/api/projects/{project_id}/process").status_code == 202
    assert run_jobs() >= 1  # a second run listens, when a transcriber is installed
    return project_id


@pytest.fixture
def course(client) -> int:
    register(client)
    return make_course(client)


def topic_by_name(path: dict, name: str) -> dict:
    return next(t for t in path["topics"] if t["name"] == name)
