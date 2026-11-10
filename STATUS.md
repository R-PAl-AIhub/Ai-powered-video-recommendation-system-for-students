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

The **backend is written and runs end to end**. **Tests, the frontend, Docker, CI/CD
and the README are not started.** Work stopped in the middle of tuning how the two
matching stages are combined (details under "Resume here").

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
| Matching | `app/services/embeddings.py`, `matching.py`, `rerank.py`, `recommend.py`, `fuzzy.py`, `sequencing.py` | Works; second stage still being tuned. |
| Pipeline and jobs | `app/services/pipeline.py`, `app/services/jobs.py`, `app/worker.py` | Pipeline verified end to end. Job queue written, not yet tested. |
| Observability | `app/observability.py` | Written, not yet tested. |
| Evaluation | `evaluation/` | Working (see below). |

## Measured results

Synthetic labelled course (`python -m evaluation.run`):

- Embeddings only (before the reranker was added): top-1 accuracy 25/25, gaps 3/3.
- Lexical fallback (`--backend hash`): 25/25, gaps 3/3. This still passes.
- **With the reranker as currently combined: 23/25 and two false gaps. The gate
  fails.** This is the open problem.

Real playlist (Neso Academy "Operating System", 77 videos, cached in
`backend/data/live-os.db`, not in git):

- Units 1 to 4 of a real syllabus match sensibly with correct timestamps.
- Units 5 to 7 are correctly reported as gaps: that free playlist has no deadlock,
  memory or storage lectures, only 40 to 78 second promo clips, which are now
  excluded by `MIN_VIDEO_SECONDS=120`.

## Resume here

**Done since the first checkpoint.** The second stage now reads the title chunk plus
the top three transcript chunks, is calibrated to a 0.8 to 4.9 logit window, and
leads the relevance (`relevance = s2 * (1 - 0.15 * (1 - s1))`). Results:

- Synthetic gate passes: 24/25, gaps 3/3, timestamps 3/3.
- Real playlist: Units 3 and 4 essentially all correct; look-alikes rejected;
  searches correct, including honest "Video not found".

**Still wrong on the real playlist, with the intended fix for each.**

1. *The abbreviation "OS".* "Structure of an OS" picks "Basics of OS (I/O
   Structure)" instead of "Structures of Operating System"; "OS Services" scores
   only 0.51. Fix: expand acronyms in the topic text used for both stages, by
   matching an all-caps token against the initials of the project subject and unit
   titles ("OS" from "Operating Systems") and against "Name (ABBR)" definitions.
2. *"Process states" loses to the next video.* `_title_tokens()` in `recommend.py`
   stems by truncating to six characters, so "states" and "State" do not match.
   Fix: strip plural endings before truncating, and raise `TITLE_BONUS` to 0.08.
3. *Generic names rejected by the cross-encoder.* "Processes", "Processes:
   Definition", "Types of threads" become gaps. Run
   `python -m evaluation.rerank_study --models Xenova/ms-marco-MiniLM-L-6-v2 --detail`
   to see which labelled positives fail under each phrasing before choosing a fix.

**Background: why the second stage was changed.** The first version combined the
embedding score (stage 1) and cross-encoder score (stage 2) as a geometric mean and
read one transcript chunk per video, which wrongly rejected true matches.

**Evidence.** `python -m evaluation.rerank_study` on 60 labelled real pairs:

| Model | Passages per video | AUC | Best accuracy |
|---|---|---|---|
| `Xenova/ms-marco-MiniLM-L-6-v2` | 3 | 0.991 | 0.967 at logit 2.84 |
| `Xenova/ms-marco-MiniLM-L-12-v2` | 3 | 0.990 | 0.967 (3x slower) |
| `jinaai/jina-reranker-v1-turbo-en` | 3 | 0.967 | 0.933 |

With three passages: positives have p10 = 3.42 and median 7.19; negatives have a
maximum of 2.72. Rephrasing the query did not help.

After any change, re-run `python -m evaluation.run --backend fastembed` (must pass)
and `python -m evaluation.live --name os ... --raw` (works offline from the cache).

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
