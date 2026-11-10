"""Application entry point: API, background worker and the built single-page app."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text

from . import __version__
from .config import get_settings
from .db import SessionLocal, init_db
from .deps import verify_origin
from .observability import RequestContextMiddleware, configure_logging
from .routers import auth, learning, projects
from .services import jobs

log = logging.getLogger(__name__)


def _frontend_dir() -> Path | None:
    settings = get_settings()
    candidates = [settings.frontend_dist] if settings.frontend_dist else []
    candidates.append(Path(__file__).resolve().parents[2] / "frontend" / "dist")
    for candidate in candidates:
        if candidate and (candidate / "index.html").is_file():
            return candidate
    return None


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.environment == "production")
    if settings.is_sqlite:
        init_db()  # PostgreSQL schemas are managed by Alembic migrations
    worker = None
    if settings.run_worker:
        with SessionLocal() as db:
            # With SQLite this process is the only worker, so any job still marked
            # "running" was cut off by a restart and can resume immediately.
            recovered = jobs.recover_interrupted(db, everything=settings.is_sqlite)
            if recovered:
                log.info("recovered %d interrupted job(s)", recovered)
        worker = jobs.Worker()
        worker.start()
    yield
    if worker is not None:
        worker.stop()
        worker.join(timeout=5)


def create_app() -> FastAPI:
    settings = get_settings()
    production = settings.environment == "production"
    app = FastAPI(
        title="Syllabus-driven video recommendations",
        version=__version__,
        lifespan=lifespan,
        docs_url=None if production else "/api/docs",
        redoc_url=None,
        openapi_url=None if production else "/api/openapi.json",
    )
    app.add_middleware(RequestContextMiddleware, hsts=production)
    if settings.cors_origin_list:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origin_list,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    api = APIRouter(prefix="/api", dependencies=[Depends(verify_origin)])
    api.include_router(auth.router)
    api.include_router(projects.router)
    api.include_router(learning.router)
    app.include_router(api)

    @app.get("/healthz", include_in_schema=False)
    def healthz():
        """Liveness: the process is up."""
        return {"status": "ok", "version": __version__}

    @app.get("/readyz", include_in_schema=False)
    def readyz():
        """Readiness: the database answers."""
        try:
            with SessionLocal() as db:
                db.execute(text("SELECT 1"))
        except Exception:
            log.exception("readiness check failed")
            return JSONResponse({"status": "unavailable"}, status_code=503)
        return {"status": "ready"}

    @app.get("/metrics", include_in_schema=False)
    def metrics():
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        log.exception("unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse({"detail": "Something went wrong on our side."}, status_code=500)

    frontend = _frontend_dir()
    if frontend is not None:
        app.mount("/assets", StaticFiles(directory=frontend / "assets"), name="assets")
        root = frontend.resolve()

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            if path.startswith("api/"):
                raise HTTPException(404, "Not found")
            target = (root / path).resolve()
            if path and target.is_file() and root in target.parents:
                return FileResponse(target)
            # Client-side routes all load the app shell; it must never be cached,
            # or a deploy would leave browsers pointing at old asset names.
            return FileResponse(root / "index.html", headers={"Cache-Control": "no-cache"})

    return app


app = create_app()
