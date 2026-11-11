"""The job queue: queueing, claiming, retries after a YouTube block, recovery of
interrupted jobs, and failure handling."""

from __future__ import annotations

from datetime import timedelta

from app.models import Job, Project, User, utcnow
from app.services import jobs
from app.services.pipeline import PipelineResult


def make_project(db, email: str = "owner@example.com") -> Project:
    user = User(email=email, name="Owner", password_hash="x")
    db.add(user)
    db.flush()
    project = Project(user_id=user.id, name="Course")
    db.add(project)
    db.commit()
    return project


def test_enqueue_returns_the_active_job_instead_of_a_second_one(db):
    project = make_project(db)
    first = jobs.enqueue(db, project, {"force": True})
    again = jobs.enqueue(db, project)
    assert again.id == first.id
    assert first.status == "queued" and first.options == {"force": True}
    assert db.query(Job).count() == 1


def test_manual_run_replaces_a_waiting_retry(db):
    project = make_project(db)
    done = Job(project_id=project.id, status="done", options={})
    db.add(done)
    db.commit()
    assert jobs.schedule_retry(db, done) is not None
    db.commit()
    assert jobs.next_retry(db, project.id) is not None

    manual = jobs.enqueue(db, project)
    assert jobs.next_retry(db, project.id) is None
    assert manual.status == "queued"
    # latest_job ignores waiting retries and returns the newest real job.
    assert jobs.latest_job(db, project.id).id == manual.id


def test_retry_delays_grow_and_then_stop(db):
    project = make_project(db)
    waits = []
    for retries in range(len(jobs.RETRY_DELAYS_MINUTES)):
        job = Job(project_id=project.id, status="done", options={"auto_retry": retries})
        db.add(job)
        db.commit()
        before = utcnow().replace(tzinfo=None)
        retry = jobs.schedule_retry(db, job)
        db.commit()
        assert retry.status == "scheduled"
        assert retry.options == {"auto_retry": retries + 1}
        minutes = (retry.run_after.replace(tzinfo=None) - before).total_seconds() / 60
        waits.append(round(minutes))
    assert waits == list(jobs.RETRY_DELAYS_MINUTES)

    exhausted = Job(
        project_id=project.id, status="done", options={"auto_retry": len(jobs.RETRY_DELAYS_MINUTES)}
    )
    db.add(exhausted)
    db.commit()
    assert jobs.schedule_retry(db, exhausted) is None


def test_promote_due_queues_only_retries_whose_time_has_come(db):
    idle = make_project(db, "idle@example.com")
    busy = make_project(db, "busy@example.com")
    later = make_project(db, "later@example.com")
    past, future = utcnow() - timedelta(minutes=1), utcnow() + timedelta(hours=1)
    db.add_all(
        [
            Job(project_id=idle.id, status="scheduled", run_after=past, options={}),
            Job(project_id=busy.id, status="running", options={}),
            Job(project_id=busy.id, status="scheduled", run_after=past, options={}),
            Job(project_id=later.id, status="scheduled", run_after=future, options={}),
        ]
    )
    db.commit()

    assert jobs.promote_due(db) == 1
    assert jobs.next_retry(db, idle.id) is None  # promoted
    assert jobs.latest_job(db, idle.id).status == "queued"
    assert jobs.next_retry(db, busy.id) is not None  # its project is still working
    assert jobs.next_retry(db, later.id) is not None  # not due yet


def test_claim_next_takes_the_oldest_job_once(db):
    first = jobs.enqueue(db, make_project(db, "a@example.com"))
    second = jobs.enqueue(db, make_project(db, "b@example.com"))

    claimed = jobs.claim_next(db)
    assert claimed.id == first.id
    db.refresh(claimed)  # this session queued the job; a worker's own session loads it fresh
    assert claimed.status == "running" and claimed.attempts == 1
    assert claimed.started_at is not None and claimed.heartbeat_at is not None

    assert jobs.claim_next(db).id == second.id
    assert jobs.claim_next(db) is None


def test_recover_interrupted_requeues_stale_jobs_and_gives_up_after_max_attempts(db):
    project_a = make_project(db, "a@example.com")
    project_b = make_project(db, "b@example.com")
    project_c = make_project(db, "c@example.com")
    stale = utcnow() - timedelta(hours=2)
    retryable = Job(
        project_id=project_a.id, status="running", attempts=1, heartbeat_at=stale, options={}
    )
    exhausted = Job(
        project_id=project_b.id,
        status="running",
        attempts=jobs.MAX_ATTEMPTS,
        heartbeat_at=stale,
        options={},
    )
    alive = Job(
        project_id=project_c.id, status="running", attempts=1, heartbeat_at=utcnow(), options={}
    )
    db.add_all([retryable, exhausted, alive])
    db.commit()

    assert jobs.recover_interrupted(db) == 2
    assert retryable.status == "queued" and retryable.message == "Waiting to resume"
    assert exhausted.status == "failed" and "interrupted" in exhausted.error
    assert exhausted.finished_at is not None
    assert alive.status == "running"  # still heartbeating: another worker owns it

    # A single-worker process takes back every running job at startup.
    assert jobs.recover_interrupted(db, everything=True) == 1
    assert alive.status == "queued"


def test_execute_records_success_and_plans_a_retry_when_videos_were_blocked(db, monkeypatch):
    project = make_project(db)
    seen = {}

    def fake_pipeline(session, proj, report, options):
        seen["project"], seen["options"] = proj.id, options
        report("transcripts", 0.5, "Reading captions")
        return PipelineResult(warnings=["3 videos had no captions"], blocked_videos=2)

    monkeypatch.setattr(jobs, "run_pipeline", fake_pipeline)
    jobs.enqueue(db, project, {"force": True})
    job = jobs.claim_next(db)
    jobs.execute(db, job)

    assert seen == {"project": project.id, "options": {"force": True}}
    assert job.status == "done" and job.progress == 1.0
    assert job.warnings == ["3 videos had no captions"]
    assert job.finished_at is not None
    retry = jobs.next_retry(db, project.id)
    assert retry is not None and retry.options == {"auto_retry": 1}


def test_execute_without_blocked_videos_plans_no_retry(db, monkeypatch):
    project = make_project(db)
    monkeypatch.setattr(jobs, "run_pipeline", lambda *args: PipelineResult())
    jobs.enqueue(db, project)
    jobs.execute(db, jobs.claim_next(db))
    assert jobs.next_retry(db, project.id) is None


def test_execute_marks_the_job_failed_with_a_readable_error(db, monkeypatch):
    project = make_project(db)

    def broken(*args):
        raise ValueError("captions exploded")

    monkeypatch.setattr(jobs, "run_pipeline", broken)
    jobs.enqueue(db, project)
    job = jobs.claim_next(db)
    jobs.execute(db, job)

    stored = jobs.latest_job(db, project.id)
    assert stored.status == "failed"
    assert stored.error == "Processing failed: ValueError: captions exploded"
    assert stored.finished_at is not None


def test_execute_survives_the_project_being_deleted_mid_run(db, monkeypatch):
    project = make_project(db)
    project_id = project.id

    def delete_then_fail(session, proj, report, options):
        session.delete(proj)
        session.commit()
        raise RuntimeError("gone")

    monkeypatch.setattr(jobs, "run_pipeline", delete_then_fail)
    jobs.enqueue(db, project)
    jobs.execute(db, jobs.claim_next(db))  # must not raise
    assert jobs.latest_job(db, project_id) is None


def test_worker_thread_runs_a_queued_job_and_stops(db, monkeypatch):
    project = make_project(db)
    monkeypatch.setattr(jobs, "run_pipeline", lambda *args: PipelineResult())
    job_id = jobs.enqueue(db, project).id

    worker = jobs.Worker(poll_seconds=0.05)
    worker.start()
    try:
        for _ in range(100):
            db.expire_all()
            if db.get(Job, job_id).status == "done":
                break
            worker.join(0.05)
    finally:
        worker.stop()
        worker.join(5)
    assert not worker.is_alive()
    db.expire_all()
    assert db.get(Job, job_id).status == "done"
