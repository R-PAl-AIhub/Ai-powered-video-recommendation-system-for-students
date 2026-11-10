"""Projects and their sources (playlists, documents), plus processing jobs."""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..deps import current_user, idle_project, owned_project
from ..models import Document, Playlist, Project, User, Video, utcnow
from ..schemas import (
    DocumentKind,
    DocumentOut,
    DocumentTextIn,
    JobOut,
    PlaylistIn,
    PlaylistOut,
    ProcessIn,
    ProjectDetail,
    ProjectIn,
    ProjectPatch,
    ProjectSummary,
)
from ..services import jobs
from ..services.documents import ALLOWED_EXTENSIONS, DocumentError, clean_text, sniff_kind
from ..services.matching import invalidate_index
from ..services.path import document_out, job_out, project_detail, project_summary
from ..services.recommend import rebuild_recommendations
from ..services.youtube import parse_playlist_id

router = APIRouter(prefix="/projects", tags=["projects"])


def _touch_sources(project: Project) -> None:
    project.sources_changed_at = utcnow()


@router.get("", response_model=list[ProjectSummary])
def list_projects(user: User = Depends(current_user), db: Session = Depends(get_db)):
    projects = db.scalars(
        select(Project).where(Project.user_id == user.id).order_by(Project.created_at.desc())
    ).all()
    return [project_summary(db, p) for p in projects]


@router.post("", response_model=ProjectDetail, status_code=status.HTTP_201_CREATED)
def create_project(
    body: ProjectIn, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    project = Project(
        user_id=user.id, name=body.name, subject=body.subject, description=body.description
    )
    db.add(project)
    db.commit()
    return project_detail(db, project)


@router.get("/{project_id}", response_model=ProjectDetail)
def get_project(project: Project = Depends(owned_project), db: Session = Depends(get_db)):
    return project_detail(db, project)


@router.patch("/{project_id}", response_model=ProjectDetail)
def update_project(
    body: ProjectPatch, project: Project = Depends(idle_project), db: Session = Depends(get_db)
):
    if body.name is not None:
        project.name = " ".join(body.name.split())
    if body.subject is not None and body.subject != project.subject:
        project.subject = " ".join(body.subject.split())
        for topic in project.topics:  # the subject steers topic vectors
            topic.embedding = None
    if body.description is not None:
        project.description = body.description
    db.commit()
    return project_detail(db, project)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project: Project = Depends(owned_project), db: Session = Depends(get_db)):
    upload_dir = get_settings().upload_dir
    for document in project.documents:
        if document.storage_name:
            (upload_dir / document.storage_name).unlink(missing_ok=True)
    invalidate_index(project.id)
    db.delete(project)
    db.commit()


# -------------------------------------------------------------------- playlists


@router.post(
    "/{project_id}/playlists", response_model=PlaylistOut, status_code=status.HTTP_201_CREATED
)
def add_playlist(
    body: PlaylistIn, project: Project = Depends(idle_project), db: Session = Depends(get_db)
):
    settings = get_settings()
    playlist_id = parse_playlist_id(body.url)
    if playlist_id is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "That does not look like a YouTube playlist link. Open the playlist on YouTube and "
            "copy its address (it contains “list=”).",
        )
    if any(p.youtube_id == playlist_id for p in project.playlists):
        raise HTTPException(status.HTTP_409_CONFLICT, "This playlist is already in the project")
    if len(project.playlists) >= settings.max_playlists_per_project:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"A project can hold up to {settings.max_playlists_per_project} playlists",
        )
    playlist = Playlist(
        project_id=project.id,
        youtube_id=playlist_id,
        url=f"https://www.youtube.com/playlist?list={playlist_id}",
        position=max((p.position for p in project.playlists), default=-1) + 1,
    )
    db.add(playlist)
    _touch_sources(project)
    db.commit()
    return PlaylistOut.model_validate(playlist)


@router.delete("/{project_id}/playlists/{playlist_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_playlist(
    playlist_id: int, project: Project = Depends(idle_project), db: Session = Depends(get_db)
):
    playlist = db.get(Playlist, playlist_id)
    if playlist is None or playlist.project_id != project.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Playlist not found")
    for video in db.scalars(select(Video).where(Video.playlist_id == playlist.id)):
        db.delete(video)
    db.delete(playlist)
    _touch_sources(project)
    db.flush()
    db.refresh(project)
    invalidate_index(project.id)
    rebuild_recommendations(db, project)
    db.commit()


# -------------------------------------------------------------------- documents


def _check_document_quota(project: Project) -> None:
    limit = get_settings().max_documents_per_project
    if len(project.documents) >= limit:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"A project can hold up to {limit} documents"
        )


@router.post(
    "/{project_id}/documents", response_model=DocumentOut, status_code=status.HTTP_201_CREATED
)
async def upload_document(
    request: Request,
    file: UploadFile,
    kind: DocumentKind = Form(...),
    project: Project = Depends(idle_project),
    db: Session = Depends(get_db),
):
    settings = get_settings()
    _check_document_quota(project)
    too_large = HTTPException(
        status.HTTP_413_CONTENT_TOO_LARGE,
        f"Files can be up to {settings.max_upload_mb} MB",
    )
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > settings.max_upload_bytes + 4096:
        raise too_large

    data = bytearray()
    while chunk := await file.read(1024 * 1024):
        data.extend(chunk)
        if len(data) > settings.max_upload_bytes:
            raise too_large
    if not data:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "The file is empty")

    filename = Path(file.filename or "upload").name[:200] or "upload"
    extension = Path(filename).suffix.lower()
    try:
        if extension not in ALLOWED_EXTENSIONS:
            raise DocumentError(
                "Unsupported file. Upload a PDF, a Word document (.docx), a text file, "
                "or a photo/scan (PNG, JPG, WEBP, TIFF)."
            )
        sniff_kind(bytes(data[:4096]), filename)
    except DocumentError as exc:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, str(exc)) from None

    storage_name = f"{uuid.uuid4().hex}{extension}"
    (settings.upload_dir / storage_name).write_bytes(data)
    document = Document(
        project_id=project.id,
        kind=kind,
        filename=filename,
        content_type=(file.content_type or "")[:120],
        size_bytes=len(data),
        storage_name=storage_name,
    )
    db.add(document)
    _touch_sources(project)
    db.commit()
    return document_out(document)


@router.post(
    "/{project_id}/documents/text", response_model=DocumentOut, status_code=status.HTTP_201_CREATED
)
def add_text_document(
    body: DocumentTextIn, project: Project = Depends(idle_project), db: Session = Depends(get_db)
):
    """Paste a syllabus (or notes / questions) as plain text instead of uploading a file."""
    _check_document_quota(project)
    text = clean_text(body.text)
    title = " ".join(body.title.split()) or f"Pasted {body.kind}"
    document = Document(
        project_id=project.id,
        kind=body.kind,
        filename=title,
        content_type="text/plain",
        size_bytes=len(text.encode("utf-8")),
        status="ready",
        text=text,
        page_count=1,
    )
    db.add(document)
    _touch_sources(project)
    db.commit()
    return document_out(document)


@router.delete("/{project_id}/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_document(
    document_id: int, project: Project = Depends(idle_project), db: Session = Depends(get_db)
):
    document = db.get(Document, document_id)
    if document is None or document.project_id != project.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    if document.storage_name:
        (get_settings().upload_dir / document.storage_name).unlink(missing_ok=True)
    db.delete(document)
    _touch_sources(project)
    db.commit()


# ------------------------------------------------------------------- processing


@router.post("/{project_id}/process", response_model=JobOut, status_code=status.HTTP_202_ACCEPTED)
def process_project(
    body: ProcessIn | None = None,
    project: Project = Depends(owned_project),
    db: Session = Depends(get_db),
):
    if not project.playlists and not project.documents and not project.topics:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Add a playlist and a syllabus first, then run the analysis.",
        )
    job = jobs.enqueue(db, project, {"reextract": bool(body and body.reextract)})
    return JobOut.model_validate(job)


@router.get("/{project_id}/job", response_model=JobOut | None)
def get_job(project: Project = Depends(owned_project), db: Session = Depends(get_db)):
    return job_out(db, project.id)
