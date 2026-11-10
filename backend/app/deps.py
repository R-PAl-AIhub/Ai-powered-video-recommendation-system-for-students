"""FastAPI dependencies: authentication, ownership and CSRF origin checks."""

from __future__ import annotations

from urllib.parse import urlparse

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .models import Job, Project, User
from .security import COOKIE_NAME, read_token

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def verify_origin(request: Request) -> None:
    """Reject cross-site state-changing requests.

    The session cookie is SameSite=Lax already; this is a second line of defence:
    when a browser sends an Origin header on an unsafe method, it must be this
    site (or an explicitly allowed origin).
    """
    if request.method in SAFE_METHODS:
        return
    origin = request.headers.get("origin")
    if not origin:
        return  # non-browser client (curl, server-to-server)
    if origin in get_settings().cors_origin_list:
        return
    origin_host = urlparse(origin).netloc.lower()
    request_host = (request.headers.get("x-forwarded-host") or request.headers.get("host") or "").lower()
    if origin_host and origin_host == request_host.split(",")[0].strip():
        return
    raise HTTPException(status.HTTP_403_FORBIDDEN, "Cross-site request blocked")


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        header = request.headers.get("authorization", "")
        if header.lower().startswith("bearer "):
            token = header[7:].strip()
    user_id = read_token(token) if token else None
    user = db.get(User, user_id) if user_id is not None else None
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Please sign in")
    return user


def owned_project(
    project_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> Project:
    project = db.get(Project, project_id)
    # 404 (not 403) for other people's projects, so ids cannot be probed.
    if project is None or project.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    return project


def idle_project(
    project: Project = Depends(owned_project), db: Session = Depends(get_db)
) -> Project:
    """A project the caller owns that has no analysis running. Changing sources,
    topics or feedback mid-run would race with the pipeline."""
    busy = db.scalar(
        select(Job.id).where(Job.project_id == project.id, Job.status.in_(("queued", "running")))
    )
    if busy is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "The analysis is still running. Try again when it has finished.",
        )
    return project


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
