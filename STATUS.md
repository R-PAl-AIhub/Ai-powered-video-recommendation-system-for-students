# Build status and resume point

Last updated: 2026-11-10. This file records exactly where the build stopped so it
can be resumed. Delete it once the project is finished and the README replaces it.

## What this project is

A web app that takes a student's YouTube playlists, exam syllabus, teacher's notes
and past papers, and produces an ordered list of videos covering the syllabus, with
gaps flagged, topic search, and a feedback loop. The idea document (`idea.docx`)
and four link lists (`AI Agent Skills*.docx`) are in the project root and are
git-ignored on purpose (the repository is public).

## State in one line

The **backend is written and runs end to end, and matching quality is tuned and
measured**. **Tests, the frontend, Docker, CI/CD and the README are not started.**

## Done

All under `backend/`:

| Area | Files | Status |
|---|---|---|
| Config, database, models | `app/config.py`, `app/db.py`, `app/models.py` | Written. SQLite by default, PostgreSQL via `DATABASE_URL`. |
| Accounts and security | `app/security.py`, `app/deps.py`, `app/routers/auth.py` | Written, not yet tested. Cookie sessions, bcrypt, rate limit, origin check. |
| API | `app/routers/projects.py`, `app/routers/learning.py`, `app/schemas.py`, `app/main.py` | 22 routes register. Not yet exercised over HTTP. |
| YouTube access | `app/services/youtube.py` | yt-dlp path verified live. Data API path is written but untested (no API key). |
| Documents and OCR | `app/services/documents.py`, `app/services/ocr.py` | Written, not yet tested. |
| Topic extraction | `app/services/topics.py` | Verified on four syllabus formats by hand. |
| Matching | `app/services/embeddings.py`, `matching.py`, `rerank.py`, `recommend.py`, `fuzzy.py`, `sequencing.py` | Tuned and measured (see below). |
| Pipeline and jobs | `app/services/pipeline.py`, `app/services/jobs.py`, `app/worker.py` | Pipeline verified end to end. Job queue written, not yet tested. |
| Observability | `app/observability.py` | Written, not yet tested. |
| Evaluation | `evaluation/` | Working (see below). |

## Measured results

Synthetic labelled course (`python -m evaluation.run`):

- Real models (`--backend fastembed`): top-1 accuracy 25/25, gaps 3/3. Passes.
- Lexical fallback (`--backend hash`): 23/25, gaps 3/3. Passes (threshold 0.9).

Real playlist (Neso Academy "Operating System", 77 videos, cached in
`backend/data/live-os.db`, not in git) against `evaluation/samples/os_syllabus.txt`:

- Units 1 to 4: all 38 topics matched, nearly all to exactly the right lecture,
  with timestamps inside multi-topic videos.
- Units 5 to 7: 20 topics correctly reported as gaps. That free playlist has no
  deadlock, memory or storage lectures, only 40 to 78 second promo clips, which
  are excluded by `MIN_VIDEO_SECONDS=120`.
- Topic searches return the right videos or an honest "Video not found".

## Matching: settled

The matching pipeline is tuned and should not need more work before the rest is
built. How it works, with the evidence:

1. **Stage 1, embeddings + TF-IDF** shortlists six videos per topic.
2. **Stage 2, a cross-encoder** (`Xenova/ms-marco-MiniLM-L-6-v2`) reads the topic
   against each shortlisted video's title chunk and top three transcript chunks and
   sets the relevance: `relevance = s2 * (1 - 0.15 * (1 - s1))`.
3. **Topic wording** (`query_text()` in `recommend.py`): "X: Definition" is matched
   as "X"; abbreviations are spelled out from the course subject ("OS").
4. **Tie-breakers**: title match bonus, slight penalty for worked-problem videos,
   and the path-level continuity bonuses.

`python -m evaluation.rerank_study` on 60 labelled real pairs:

| Model | Passages per video | AUC | Best accuracy |
|---|---|---|---|
| `Xenova/ms-marco-MiniLM-L-6-v2` | 3 | 0.991 | 0.967 at logit 2.84 |
| `Xenova/ms-marco-MiniLM-L-12-v2` | 3 | 0.990 | 0.967 (3x slower) |
| `jinaai/jina-reranker-v1-turbo-en` | 3 | 0.967 | 0.933 |

Known small imperfections, left as they are: on the synthetic course one timestamp
is a chunk late ("Structure of an OS"); on the real playlist "Concept of Operating
Systems" picks video #2 rather than #1.

Reranker scores are cached raw in the `rerank_scores` table and calibrated on read.

After any matching change, re-run `python -m evaluation.run --backend fastembed`
(must pass) and `python -m evaluation.live --name os ... --raw` (works offline from
the cache).

## Resume here

Start at item 0 of the list below. Nothing is half-finished.

## Not started, in order

0. **Most important topics and a question-and-answer section** (requested by the
   user on 2026-11-10). Interpretation chosen:
   - *Most important topics*: rank topics by an importance score built from
     `Topic.exam_hits` / `exam_weight` (how often past papers ask about them) and
     `Topic.in_notes`, expose it on the API and show it as its own section.
   - *Question and answer section*: store each past-paper question (new `questions`
     table, filled in the pipeline from `split_questions()`), link it to its best
     topic and to the video moment that answers it (reuse `search_project()` logic),
     and return the transcript excerpt as the answer context. Endpoint
     `GET /api/projects/{id}/questions`, grouped by topic.

1. **YouTube robustness.** After one full-playlist run YouTube blocked this machine
   ("Sign in to confirm you're not a bot") for both yt-dlp and the transcript
   library. The first run sent about 300 requests in a minute. Needed: throttling
   with jitter and fewer workers, fetch per-video details only when a video has no
   captions, a shared transcript cache table across projects, stop on block with a
   scheduled automatic retry, proxy documentation.
2. **Multiple languages** (explicit requirement). Could not be verified because of
   the block. Plan: prefer English captions, then YouTube's translation to English,
   then original-language captions with a multilingual embedding model; only run the
   English reranker on English text. A Turkish-only caption track is currently fed
   to the English model, which is wrong. Evaluate
   `paraphrase-multilingual-MiniLM-L12-v2` (128-token limit, needs smaller chunks).
3. **Backend tests** (`backend/tests/`): unit tests for each service, API tests using
   `evaluation.harness.LabelledYouTube`, security tests.
4. **Alembic migrations** for PostgreSQL.
5. **Frontend** (`frontend/`): React, Vite, TypeScript, Tailwind, with a 3D scene
   (React Three Fiber) and motion. Load the taste design skill first. Must not look
   generic. Pages: sign in, projects, sources, topics, learning path with player,
   search, feedback.
6. **Deployment**: Dockerfile, docker-compose (API, worker, PostgreSQL),
   `render.yaml`, `.env.example`.
7. **CI/CD** (`.github/workflows/`): lint, tests on SQLite and PostgreSQL, the
   evaluation gate, frontend build, Docker build and publish.
8. **README** and a final end-to-end check in a browser.

## How to run what exists

```bash
cd backend
python -m venv .venv
.venv/Scripts/python -m pip install fastapi "uvicorn[standard]" "sqlalchemy>=2" alembic \
  pydantic-settings pyjwt bcrypt python-multipart httpx numpy scikit-learn pypdfium2 \
  python-docx pillow yt-dlp youtube-transcript-api "psycopg[binary]" fastembed \
  rapidocr-onnxruntime prometheus-client email-validator pytest ruff

.venv/Scripts/python -m evaluation.run --backend hash        # offline quality gate
.venv/Scripts/python -m evaluation.run --backend fastembed   # with the real models
.venv/Scripts/python -m uvicorn app.main:app --reload        # API on :8000, docs at /api/docs
```

There is no `requirements.txt` yet; the list above is what is installed. Python
3.14 on Windows was used.

## Decisions already made, with reasons

- **FastAPI**, not Flask or Django: async, validation and OpenAPI built in.
- **Session cookie** (httpOnly, SameSite=Lax) rather than a token in localStorage.
- **Similarity calibration for BGE is 0.60 to 0.85 cosine**, measured: off-topic text
  in the same subject scores 0.55 to 0.62, true matches 0.72 to 0.89.
- **The course subject is not blended into topic vectors.** It made topics with no
  video look covered.
- **Relevance passes through linearly to the ranking score.** A rule-based fuzzy
  combination flattened real differences and the continuity bonus then picked worse
  videos. Fuzzy logic is still used for the metadata quality score.
- **Path ordering is solved as a whole** (Viterbi), with bonuses for staying in the
  same video, playlist or channel.

## Local state that is not in git

- `backend/.venv/`: the virtual environment.
- `backend/data/models/`: downloaded embedding and reranker models.
- `backend/data/live-os.db` and `live-os.backup.db`: cached real-playlist run.
  Keep these; they allow tuning without contacting YouTube.
