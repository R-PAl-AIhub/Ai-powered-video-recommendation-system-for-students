"""Application settings, read from environment variables (and an optional .env file)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_SECRET = "dev-only-secret-change-me-before-deploying"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: Literal["development", "production", "test"] = "development"

    # --- security ---
    secret_key: str = DEV_SECRET
    access_token_minutes: int = 60 * 24 * 7
    cors_origins: str = ""  # comma-separated list; empty = same-origin only
    auth_rate_limit_per_minute: int = 20

    # --- storage ---
    database_url: str = "sqlite:///./data/app.db"
    data_dir: Path = Path("./data")
    frontend_dist: Path | None = None  # built SPA to serve; auto-detected when unset

    # --- YouTube ---
    youtube_api_key: str | None = None  # optional: use the official Data API for metadata
    youtube_proxy: str | None = None  # optional: http(s) proxy for YouTube requests
    max_playlists_per_project: int = 10
    max_videos_per_playlist: int = 300
    # YouTube blocks clients that send bursts of requests, so requests are spaced
    # out (seconds between any two, with jitter) and few run in parallel.
    youtube_request_interval: float = 1.0
    transcript_workers: int = 2
    transcript_languages: str = "en,en-US,en-GB,en-IN"

    # --- analysis ---
    embedding_backend: Literal["fastembed", "hash"] = "fastembed"
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    # Cross-encoder that re-scores shortlisted videos; "" disables the second stage.
    reranker_model: str = "Xenova/ms-marco-MiniLM-L-6-v2"
    model_dir: Path | None = None  # where model files are cached
    min_video_seconds: int = 120  # shorter clips (trailers, Shorts) are never recommended
    ocr_backend: Literal["auto", "rapidocr", "tesseract", "none"] = "auto"
    max_upload_mb: int = 25
    max_documents_per_project: int = 40
    max_topics_per_project: int = 250

    # Apply database migrations at startup. Turn off when a deploy step runs
    # `python -m app.migrate` once before the processes start.
    migrate_on_start: bool = True

    # --- background worker ---
    # Run the job worker inside the API process. Fine for one process; with several
    # API processes set this to false and run `python -m app.worker` separately.
    run_worker: bool = True
    job_stale_minutes: int = 15

    @model_validator(mode="after")
    def _validate(self) -> Settings:
        url = self.database_url
        # Hosted Postgres providers hand out postgres:// URLs; SQLAlchemy wants a driver.
        if url.startswith("postgres://"):
            url = "postgresql+psycopg://" + url[len("postgres://") :]
        elif url.startswith("postgresql://"):
            url = "postgresql+psycopg://" + url[len("postgresql://") :]
        self.database_url = url

        weak_secret = self.secret_key == DEV_SECRET or len(self.secret_key) < 32
        if self.environment == "production" and weak_secret:
            raise ValueError(
                "SECRET_KEY must be set to a random value of at least 32 characters "
                "when ENVIRONMENT=production"
            )
        return self

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def upload_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def model_cache_dir(self) -> Path:
        # The Docker image bakes the model into MODEL_DIR so cold starts need no download.
        return self.model_dir or self.data_dir / "models"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def transcript_language_list(self) -> list[str]:
        return [x.strip() for x in self.transcript_languages.split(",") if x.strip()]

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    settings.model_cache_dir.mkdir(parents=True, exist_ok=True)
    return settings
