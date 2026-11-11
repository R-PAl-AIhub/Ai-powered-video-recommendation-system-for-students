# Progress

Back to [[Project Map]]. **This is the single source of truth for where the work
stands.** Update it at every checkpoint: move items between sections, add a line to
the checkpoint log, and rewrite "Resume here".

Last updated: 2026-11-11.

## State in one paragraph

The backend is complete and tested. The frontend is fully written and builds, but
has not yet been opened in a browser. Deployment files, CI/CD, database migrations
and the README are not started.

## Resume here

**Next action: close every gap in [[Requirements Checklist]]** (owner, 2026-11-11:
the idea document is the sole source of truth; every point must be built). Then
Deployment (to-do item 3). Work in this order, updating the checklist row, this
note and committing after each:

1. ~~**Study ranges**~~ (done 2026-11-11). Was: each recommendation gets an end
   second as well as a start: add `end_s` to `Recommendation` (and `Question`) via
   a new Alembic revision; compute it in `locate()` in `services/matching.py` (end
   of the run of on-topic chunks); show "Study 12:34 to 18:02" in `PathRow`,
   `QuestionCard` and search results; pass `end` to the YouTube embed in
   `embedUrl()` so the player stops there.
2. ~~**Short summary per video**~~ (done) in `PathRow` (the snippet already in the API).
3. ~~**Relabel "I know this" to "Already in my playlist"**~~ (done) (the document's wording).
4. ~~**Fuzzy ranking**~~ (done 2026-11-11). Was: add recency (`published_at`) and comment volume
   (`comment_count`) to `services/fuzzy.py`; comment sentiment from Data API
   `commentThreads` when `YOUTUBE_API_KEY` is set. Watch time is not available
   from YouTube (record as not possible).
5. ~~**Notes and exam topics**~~ (done 2026-11-11). Was: add topics found only in notes or exams, placed after
   the most similar syllabus topic, `source="notes"` / `"exam"`.
6. ~~**OCR end to end on real files**~~ (done 2026-11-11). Was: upload an image-only PDF, a PNG photo of
   notes and a DOCX to the demo project; confirm `ocr_pages > 0` and topics react.
   Add spell-check after OCR (correct out-of-vocabulary words against the course
   vocabulary). Add a Google Vision backend (`OCR_BACKEND=google`, API key) for
   handwriting.
7. ~~**Topic transitions mined from playlist order**~~ (done 2026-11-11). Was:, and a sequencing bonus when one
   pick's end leads into the next pick's start.
8. **Optional ASR** (faster-whisper) for videos without captions, paced, off by
   default.
9. **LDA topic map** of the playlists (sklearn), shown as a coverage view.

The demo server: see the steps below; `data/demo.db` has the real playlist. Migrations are done. The steps below are
kept as the recipe for running the demo; step 1's manual `ALTER TABLE` is no longer
needed, because startup now upgrades old databases automatically.

1. The old demo database fails at startup because it predates a column
   (`jobs.run_after`). Make a fresh one instead of copying `live-os.db` as is:
   copy it, then add the missing column, or simply start with a new database.
   The quickest working recipe:

   ```bash
   cd backend
   cp data/live-os.db data/demo.db
   .venv/Scripts/python -c "import sqlite3; c=sqlite3.connect('data/demo.db'); c.execute('ALTER TABLE jobs ADD COLUMN run_after DATETIME'); c.commit()"
   ```

   Then set a password for its one user and add an exam paper (a script that did
   this is described in the checkpoint log entry for 2026-11-11), and start:

   ```bash
   DATABASE_URL=sqlite:///./data/demo.db DATA_DIR=./data .venv/Scripts/python -m uvicorn app.main:app --port 8000
   ```

   The backend serves `frontend/dist` at `http://127.0.0.1:8000/` (run
   `npm run build` in `frontend/` first).
2. Browser check, **done 2026-11-11**: landing page, sign in, course list, all six
   workspace tabs, the player, feedback and undo, search (found and not found), at
   1440 wide and at 390 wide (phone emulation), in both themes. Not covered: topic
   drag-reorder by hand (the API behind it is tested), file upload through the UI
   (the API is tested), and visual review of the light theme inside the app by
   screenshot (screenshots time out in this environment; layout was checked with
   DOM measurements). Demo account: `demo@example.com` / `demo-password-1` in
   `data/demo.db`.
3. Check the browser console for Content-Security-Policy violations; the policy is
   in `backend/app/observability.py`.
4. Fix what is found, rebuild, commit.

## Done

- **Backend**: API, accounts and security, YouTube access with pacing and automatic
  retry, document reading with OCR, topic extraction, two-stage matching, fuzzy
  quality, path sequencing, feedback learning, most-important-topics score,
  question-and-answer linking, job queue and worker, metrics and health checks.
  See [[Backend]] and [[Matching Pipeline]].
- **Quality**: 34 API tests (78% coverage), lint clean, offline evaluation gate
  passing (25/25 topics, 3/3 gaps), verified on a real 77-video playlist.
  See [[Evaluation and Testing]].
- **Frontend**: design tokens, typed API client, UI primitives, 3D hero scene,
  landing page, sign in and up, course list, workspace with six tabs, player.
  Type-check and build pass. See [[Frontend]].
- **Project notes**: this vault.

## To do, in order

1. ~~Browser check of the frontend~~ (done 2026-11-11).
2. ~~Alembic migrations~~ (done 2026-11-11). `app/migrate.py` is the only schema
   path, run at API and worker startup (`MIGRATE_ON_START`, default true) or by
   `python -m app.migrate`. Initial revision `0001` covers all 12 tables. Databases
   made before migrations are adopted: missing tables created, missing columns added
   as nullable, then stamped. 4 tests in `tests/test_migrations.py`. **Adding a
   column from now on:** change the model, then
   `alembic revision --autogenerate -m "..."` in `backend/`, review the file, commit.
2a. ~~3D look across the whole site~~ (done 2026-11-11): pointer tilt with depth
   layers on cards, a perspective floor behind every signed-in page, a coverflow on
   the landing questions row, and the 3D scene beside the sign-in form. See
   [[Frontend]].
3. **Deployment**: `Dockerfile` (build the frontend, install the backend, bake both
   models in with `MODEL_DIR` set at build time, install `libgl1` and
   `libglib2.0-0` for OpenCV/RapidOCR, set `FRONTEND_DIST` explicitly because the
   path differs in the image), `docker-compose.yml` (API with `RUN_WORKER=false`, a
   separate worker service, PostgreSQL), `render.yaml`, `.env.example`. Pick one
   Python version (check onnxruntime and rapidocr wheels exist for it). Note: with
   `RUN_WORKER=true` every API process starts a worker, and on SQLite
   `recover_interrupted(everything=True)` would re-queue another process's job, so
   multi-process deployments must use a separate worker.
4. **CI/CD** in `.github/workflows/`: lint, tests on SQLite and on a PostgreSQL
   service (never run before; expect real bugs), the evaluation gate with the model
   directory cached, frontend build, Docker build and publish to GHCR
   (`permissions: packages: write`).
5. **Unit tests** for `documents.py`, `ocr.py`, `jobs.py`, `youtube.py`.
6. **Real-world checks still owed**: more real playlists in other subjects, and
   non-English playlists, once YouTube stops rate-limiting this machine. Then decide
   on a multilingual default model and a shared transcript cache across projects.
7. **README** for users and deployers, replacing the root `STATUS.md` pointer.

## Known problems

- YouTube was blocking this machine on 2026-11-10 after one burst of requests.
  Pacing was added afterwards; whether the block has lifted is untested.
- Multi-language support is implemented but unverified on real videos.
- The YouTube Data API backend is written but has never run against the real API
  (no key was available).
- PostgreSQL has never been run.
- On the real playlist, "Concept of Operating Systems" picks video 2 rather than
  video 1. Left as is.

## Checkpoint log

Newest first. Each line is a pushed commit on `main`.

| Date | Commit | What changed |
|---|---|---|
| 2026-11-11 | (this commit) | Topic order mined from the playlists (auto when no syllabus; button in Topics); content-chaining bonus in sequencing. 47 tests pass; gate 25/25. |
| 2026-11-11 | (this commit) | OCR verified on real files (scanned PDF, handwriting-style photo, Word); spell-check of OCR text against course vocabulary; Google Vision backend for handwriting. 45 tests pass. |
| 2026-11-11 | (this commit) | Topics found only in notes or past papers are added after the closest syllabus topic; better note-heading detection. Tests pass; gate 25/25. |
| 2026-11-11 | (this commit) | Fuzzy ranking now uses upload age, comment volume and comment sentiment (Data API, migration 0003). 40 tests pass; gate 25/25. |
| 2026-11-11 | (this commit) | Study ranges (start and end second, migration 0002, player stops at the end), transcript summary on each path entry, "Already in my playlist" label. 39 tests pass; frontend builds. |
| 2026-11-11 | (this commit) | 3D look across the whole site (`src/depth.tsx`): card tilt with depth layers, perspective floor, landing coverflow, 3D scene on sign-in. Verified in the browser: floor renders; tilt activates with layers applied under a motion-allowed setting. Found the owner's Windows has animation effects off, so motion stays still there by design. |
| 2026-11-11 | `5071257` | Alembic migrations: initial revision, startup upgrade, adoption of pre-migration databases, 4 tests. 38 tests pass, lint clean. |
| 2026-11-11 | `cb5ad50` | Browser check finished: Focus, Search, Topics, Sources tabs; phone width 390 with emulation; light theme. Fixed the landing nav overflowing on phones (a "hidden" class lost to the button's own inline-flex). |
| 2026-11-11 | `1c57648` | Browser check of the signed-in app. Added an undo bar for feedback: "Wrong topic", "Irrelevant" and "I know this" change the row completely, so there was no way back. Verified in the browser: wrong topic swaps in the next video, undo restores it. Removed a redundant iframe attribute. Found that a video with only a mis-labelled Turkish caption track produced garbage snippets in the cached data; the current pipeline already marks such captions as unreadable (`foreign`), confirmed by re-running on the demo data. |
| 2026-11-11 | `d60991b` | Browser check started (Chrome DevTools tools; the Claude-in-Chrome extension was disconnected). Landing page renders, the 3D scene works, no console errors besides the expected 401 from `/api/auth/me` when signed out. Fixed: in the light theme the 3D slabs were pale grey and washed out, so they now use a dark "screen" colour (`--screen`) in both themes; the hero headline now fits on two lines. |
| 2026-11-11 | `6b5f065` | Project notes vault in `docs/`. Demo database made from the real cache: 8 past questions, 6 answered, and the 2 unanswered are the ones the playlist truly lacks. Server start failed on the old database schema; recorded above. |
| 2026-11-10 | `18eb0f3` | Frontend: 3D landing page and the full app. Builds; not yet seen in a browser. |
| 2026-11-10 | `a1ad279` | Frontend scaffold: tokens, API client, UI primitives. |
| 2026-11-10 | `a9f02b1` | Questions and answers, topic importance, YouTube pacing and retry, language handling, 34 API tests. |
| 2026-11-10 | `5deb23b` | Topic wording (definitions, abbreviations), title matching, raw reranker cache. Real playlist: 38/38 coverable topics. |
| 2026-11-10 | `ae74a10` | Cross-encoder made the main relevance signal after a study on 60 labelled real pairs. |
| 2026-11-10 | `e53d782` | First status file. |
| 2026-11-10 | `82b9e95` | Backend first checkpoint. |

## How to make a checkpoint

```bash
git add -A
git commit -m "Short summary" -m "What changed and what was verified."
git push origin main
```

Before committing: run the tests and the evaluation gate if backend code changed,
`npm run build` if frontend code changed, and update this note.

## Related

[[Goal and Requirements]], [[Decisions]]
