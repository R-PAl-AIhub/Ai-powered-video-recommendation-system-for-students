# Backend

Back to [[Project Map]]. Python 3.12+ (developed on 3.14), FastAPI, SQLAlchemy.

## Files (`backend/app/`)

| File | Purpose |
|---|---|
| `main.py` | App factory, health and metrics endpoints, serves `frontend/dist` |
| `config.py` | All settings, from environment variables or `.env` |
| `db.py`, `models.py` | Engine, sessions, tables |
| `security.py`, `deps.py` | Password hashing, session tokens, rate limiter, ownership and origin checks |
| `schemas.py` | Request and response models |
| `observability.py` | Logging, request ids, Prometheus metrics, security headers |
| `worker.py` | Standalone job worker |
| `routers/auth.py` | Register, sign in, sign out, delete account |
| `routers/projects.py` | Projects, playlists, documents, start analysis, job status |
| `routers/learning.py` | Path, questions, topics, feedback, watched, search, YouTube search, add video |
| `services/youtube.py` | Playlists, captions, search; yt-dlp or the Data API; request pacing |
| `services/documents.py`, `ocr.py` | PDF, DOCX, text, images; OCR for scans |
| `services/topics.py` | Syllabus parsing, exam question splitting, notes chunking |
| `services/embeddings.py`, `rerank.py` | The two models, with fallbacks |
| `services/matching.py`, `recommend.py`, `fuzzy.py`, `sequencing.py` | See [[Matching Pipeline]] |
| `services/questions.py` | Links past questions to topics and video moments |
| `services/pipeline.py`, `jobs.py` | The analysis pipeline and its queue |
| `services/path.py` | Builds API responses from the database |

## Endpoints (all under `/api`)

- `POST /auth/register`, `POST /auth/login`, `POST /auth/logout`, `GET /auth/me`, `DELETE /auth/me`
- `GET|POST /projects`, `GET|PATCH|DELETE /projects/{id}`
- `POST /projects/{id}/playlists`, `DELETE /projects/{id}/playlists/{pid}`
- `POST /projects/{id}/documents` (file), `POST /projects/{id}/documents/text`, `DELETE /projects/{id}/documents/{did}`
- `POST /projects/{id}/process`, `GET /projects/{id}/job`
- `GET /projects/{id}/path`, `GET /projects/{id}/questions`, `GET /projects/{id}/search?q=`
- `POST|DELETE /projects/{id}/feedback`, `PUT /projects/{id}/videos/{vid}/watched`
- `POST /projects/{id}/topics`, `PATCH|DELETE /projects/{id}/topics/{tid}`, `PUT /projects/{id}/topics/order`
- `POST /projects/{id}/youtube/search`, `POST /projects/{id}/videos`
- Outside `/api`: `/healthz`, `/readyz`, `/metrics`. Interactive docs at `/api/docs` (not in production).

## Settings that matter (`config.py`)

| Variable | Default | Meaning |
|---|---|---|
| `ENVIRONMENT` | `development` | `production` requires a strong `SECRET_KEY` and hides the docs |
| `SECRET_KEY` | dev value | Signs session tokens; 32+ random characters in production |
| `DATABASE_URL` | `sqlite:///./data/app.db` | PostgreSQL URLs are accepted as given by hosts |
| `YOUTUBE_API_KEY` | unset | Use the official Data API for metadata |
| `YOUTUBE_PROXY` | unset | Proxy for YouTube requests |
| `YOUTUBE_REQUEST_INTERVAL` | `1.0` | Seconds between YouTube requests |
| `EMBEDDING_BACKEND` | `fastembed` | `hash` is a dependency-free lexical fallback |
| `EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` | A multilingual model reads non-English captions |
| `RERANKER_MODEL` | `Xenova/ms-marco-MiniLM-L-6-v2` | Empty string disables stage 2 |
| `RUN_WORKER` | `true` | Run the job worker inside the API process |
| `MIGRATE_ON_START` | `true` | Apply database migrations at startup |
| `OCR_BACKEND` | `auto` | `google`, `rapidocr`, `tesseract` or `none`; `auto` prefers Google Vision when keyed |
| `GOOGLE_VISION_API_KEY` | unset | Google Vision OCR, which reads handwriting |
| `ASR_ENABLED` | `false` | Transcribe videos without captions (faster-whisper; needs ffmpeg) |
| `ASR_MODEL` | `base` | Whisper size: `tiny`, `base`, `small`, `medium` |
| `MIN_VIDEO_SECONDS` | `120` | Shorter clips are never recommended |

## Run it

```bash
cd backend
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements-dev.txt   # Windows; use .venv/bin on Linux/macOS
.venv/Scripts/python -m uvicorn app.main:app --reload         # http://127.0.0.1:8000
```

With `frontend/dist` built, the same server serves the app at `/`.

## Things to know

- **YouTube blocks bursts.** One unthrottled run of about 300 requests in a minute
  got this machine blocked for hours ("Sign in to confirm you're not a bot"). Hence
  the pacing, the one-request-per-video design, stop-after-three-refusals, and
  scheduled retries. Do not remove them.
- **Schema changes go through Alembic.** `app/migrate.py` runs `upgrade head` at
  startup (or `python -m app.migrate` in a deploy step with `MIGRATE_ON_START=false`).
  To change the schema: edit `models.py`, run
  `.venv/Scripts/python -m alembic revision --autogenerate -m "what changed"` in
  `backend/`, review the new file in `alembic/versions/`, commit it. Databases from
  before migrations existed are adopted automatically. Tests still build tables with
  `create_all` for speed; `tests/test_migrations.py` checks the migrations match the
  models.
- New FastAPI nests included routers lazily, so `app.routes` does not list the API
  routes; use `app.openapi()["paths"]`.

## Related

[[Architecture]], [[Evaluation and Testing]]
