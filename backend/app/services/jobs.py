"""A durable, database-backed job queue.

Jobs live in the ``jobs`` table, so they survive restarts and can be processed by
any number of worker processes. A worker claims a job with a guarded UPDATE (and
``FOR UPDATE SKIP LOCKED`` on PostgreSQL), heartbeats while it works, and a job
whose worker died is put back on the queue up to ``MAX_ATTEMPTS`` times.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import timedelta

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import SessionLocal
from ..models import Job, Project, utcnow
from ..observability import JOB_DURATION, JOBS_TOTAL
from .pipeline import run_pipeline

log = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
ACTIVE = ("queued", "running")
RETRY_DELAYS_MINUTES = (30, 120, 360)  # waits before each automatic retry after a YouTube block


def enqueue(db: Session, project: Project, options: dict | None = None) -> Job:
    """Queue processing for a project. Returns the already-active job if there is one."""
    active = db.scalar(
        select(Job).where(Job.project_id == project.id, Job.status.in_(ACTIVE)).order_by(Job.id)
    )
    if active:
        return active
    # A manual run replaces any automatic retry that was waiting.
    db.execute(delete(Job).where(Job.project_id == project.id, Job.status == "scheduled"))
    job = Job(project_id=project.id, options=options or {}, message="Waiting to start")
    db.add(job)
    db.commit()
    return job


def latest_job(db: Session, project_id: int) -> Job | None:
    """The most recent job that has run or is running (not a waiting retry)."""
    return db.scalar(
        select(Job)
        .where(Job.project_id == project_id, Job.status != "scheduled")
        .order_by(Job.id.desc())
    )


def next_retry(db: Session, project_id: int) -> Job | None:
    return db.scalar(
        select(Job).where(Job.project_id == project_id, Job.status == "scheduled").order_by(Job.id)
    )


def schedule_retry(db: Session, job: Job) -> Job | None:
    """After YouTube refused some requests, plan another run for later.

    Delays grow (30 min, 2 h, 6 h) and then stop, so a long block does not
    turn into endless retries.
    """
    retries = int(job.options.get("auto_retry", 0))
    if retries >= len(RETRY_DELAYS_MINUTES):
        return None
    retry = Job(
        project_id=job.project_id,
        status="scheduled",
        stage="scheduled",
        run_after=utcnow() + timedelta(minutes=RETRY_DELAYS_MINUTES[retries]),
        options={"auto_retry": retries + 1},
        message="Waiting to retry videos YouTube refused",
    )
    db.add(retry)
    return retry


def queue_listening(db: Session, job: Job) -> Job:
    """After the path was built from the captions, queue a run that listens to
    the videos left without words. It starts as soon as the worker is free."""
    follow_up = Job(
        project_id=job.project_id,
        options={"listen": True, "auto_retry": int(job.options.get("auto_retry", 0))},
        message="Waiting to listen to videos without captions",
    )
    db.add(follow_up)
    return follow_up


def promote_due(db: Session) -> int:
    """Move scheduled retries whose time has come onto the queue."""
    due = db.scalars(
        select(Job).where(Job.status == "scheduled", Job.run_after <= utcnow())
    ).all()
    promoted = 0
    for job in due:
        busy = db.scalar(
            select(Job.id).where(Job.project_id == job.project_id, Job.status.in_(ACTIVE))
        )
        if busy is None:
            job.status, job.stage, job.message = "queued", "queued", "Retrying"
            promoted += 1
    db.commit()
    return promoted


def claim_next(db: Session) -> Job | None:
    """Atomically take the oldest queued job."""
    candidate = db.scalar(
        select(Job.id)
        .where(Job.status == "queued")
        .order_by(Job.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if candidate is None:
        db.rollback()
        return None
    now = utcnow()
    claimed = db.execute(
        update(Job)
        .where(Job.id == candidate, Job.status == "queued")
        .values(
            status="running",
            started_at=now,
            heartbeat_at=now,
            attempts=Job.attempts + 1,
            stage="starting",
            message="Starting",
            error="",
        )
    )
    db.commit()
    if claimed.rowcount != 1:  # another worker won the race
        return None
    return db.get(Job, candidate)


def recover_interrupted(db: Session, *, everything: bool = False) -> int:
    """Re-queue jobs whose worker stopped heartbeating (or all running jobs, when
    this process is known to be the only worker)."""
    query = select(Job).where(Job.status == "running")
    if not everything:
        cutoff = utcnow() - timedelta(minutes=get_settings().job_stale_minutes)
        query = query.where(Job.heartbeat_at < cutoff)
    recovered = 0
    for job in db.scalars(query):
        if job.attempts >= MAX_ATTEMPTS:
            job.status = "failed"
            job.error = "Processing was interrupted several times. Please run the analysis again."
            job.finished_at = utcnow()
        else:
            job.status, job.stage, job.message = "queued", "queued", "Waiting to resume"
        recovered += 1
    db.commit()
    return recovered


def execute(db: Session, job: Job) -> None:
    """Run one claimed job to completion, recording progress on the job row."""
    started = time.monotonic()
    last_write = 0.0

    def report(stage: str, progress: float, message: str) -> None:
        nonlocal last_write
        now = time.monotonic()
        if stage == job.stage and now - last_write < 0.4:
            return
        last_write = now
        job.stage, job.progress, job.message = stage, round(progress, 4), message[:500]
        job.heartbeat_at = utcnow()
        db.commit()

    try:
        project = db.get(Project, job.project_id)
        if project is None:
            raise RuntimeError("project no longer exists")
        result = run_pipeline(db, project, report, job.options)
        job.status, job.stage, job.progress = "done", "done", 1.0
        job.message = "Your learning path is ready"
        job.warnings = result.warnings
        if result.to_listen:
            queue_listening(db, job)
        elif result.blocked_videos:
            schedule_retry(db, job)
    except Exception as exc:
        log.exception("job %s failed", job.id)
        db.rollback()
        job_id = job.id
        db.expire_all()
        job = db.get(Job, job_id)
        if job is None:  # the project (and its jobs) was deleted mid-run
            return
        job.status = "failed"
        job.error = f"Processing failed: {type(exc).__name__}: {str(exc)[:300]}"
    job.finished_at = utcnow()
    db.commit()
    JOBS_TOTAL.labels(status=job.status).inc()
    JOB_DURATION.observe(time.monotonic() - started)


class Worker(threading.Thread):
    """Polls the queue and runs jobs one at a time."""

    def __init__(self, poll_seconds: float = 1.0):
        super().__init__(name="job-worker", daemon=True)
        self._stop_event = threading.Event()
        self._poll = poll_seconds

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        log.info("job worker started")
        last_recovery = time.monotonic()
        while not self._stop_event.is_set():
            ran = False
            try:
                with SessionLocal() as db:
                    job = claim_next(db)
                    if job is not None:
                        ran = True
                        execute(db, job)
                    elif time.monotonic() - last_recovery > 60:
                        last_recovery = time.monotonic()
                        recover_interrupted(db)
                        promote_due(db)
            except Exception:
                log.exception("job worker loop error")
            if not ran:
                self._stop_event.wait(self._poll)
        log.info("job worker stopped")
