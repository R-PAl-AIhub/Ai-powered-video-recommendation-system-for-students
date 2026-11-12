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
| `services/pasted.py` | A transcript the student copied from YouTube's "Show transcript" and pasted in: times, text, language from the script |
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
  (kinds: `syllabus`, `exam`, `notes`, `reading`; `reading` is study material that is
  recommended per topic but never creates topics)
- `POST /projects/{id}/documents/url` `{url}`: a web page or a PDF on the web as study
  material. The address is checked at once (public internet only); the page is read at
  the next analysis. Topics in `GET /path` carry `readings` (document, pages, heading,
  snippet, deep link) and `stats.gaps_with_reading`.
- `POST /projects/{id}/process`, `GET /projects/{id}/job`
- `GET /projects/{id}/path`, `GET /projects/{id}/questions`, `GET /projects/{id}/search?q=`
- `POST|DELETE /projects/{id}/feedback`, `PUT /projects/{id}/videos/{vid}/watched`
- `GET /projects/{id}/videos/untranscribed` (videos matched on the title only),
  `PUT /projects/{id}/videos/{vid}/transcript` `{text}` (use a pasted transcript; returns the new path)
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
| `ASR_ENABLED` | `true` | Listen to videos (faster-whisper, on this machine; needs ffmpeg) when they have no captions, when YouTube refuses the caption request, or when the captions are in a language the model cannot read. Without ffmpeg it switches itself off with one log line. Set `false` on a server with little memory (the `small` model needs about 1 GB) |
| `ASR_MAX_MINUTES` | `180` | Longer videos are not listened to |
| `ASR_MODEL` | `small` | Whisper size: `tiny`, `base`, `small`, `medium`. `tiny` mis-hears terms in Hindi lectures ("first round of form" for "first normal form"); `small` gets them right and is slower |
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
- **Where a video's words come from, in order** (`_fetch` in `services/pipeline.py`):
  1. YouTube captions (one request per video).
  2. If YouTube refuses that request, or there are no captions, or they are in a
     language the model cannot read: the video is listened to (the default since
     2026-11-12; `ASR_ENABLED=false` turns it off). Listening is slow, so it is a
     run of its own: the first run reads captions only and builds the path, then
     `queue_listening` in `services/jobs.py` queues a second job with
     `options["listen"]`, which listens and rebuilds the path. The screen shows
     the path meanwhile, with the job's progress line. A video in which nothing
     is heard (no speech, or longer than `ASR_MAX_MINUTES`) gets the status
     `silent` and is not listened to again. A single video added from a search is
     not listened to inside the web request; the next analysis does it.
     The audio comes from a different YouTube service than captions, so a
     caption block does not stop it (seen on 2026-11-12: captions answered HTTP 429
     all day, audio downloaded normally). After three refusals in a row captions
     are not asked for again in that run; the rest go straight to listening.
  3. A transcript pasted by the student (`PUT .../videos/{vid}/transcript`). It is
     stored as `ok` and never fetched again.
  4. Otherwise the title and description, with an automatic retry later.
  Not built, on purpose: calling YouTube's transcript-panel service from the
  server. It answers a browser, but a script must pose as one, and that is
  working around YouTube's bot check.
- Audio for listening is downloaded into `DATA_DIR/tmp` and deleted after each video.
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
