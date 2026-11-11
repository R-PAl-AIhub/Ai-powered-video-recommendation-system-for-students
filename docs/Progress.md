# Progress

Back to [[Project Map]]. **This is the single source of truth for where the work
stands.** Update it at every checkpoint: move items between sections, add a line to
the checkpoint log, and rewrite "Resume here".

Last updated: 2026-11-11.

## State in one paragraph

The backend and frontend are complete, tested and browser-checked, with migrations.
Study material beyond videos is built, with its UI. The read-only demo is live on
GitHub Pages, the owner runs the full app on his PC with `start-waypoint.bat`, and
the README is written. What remains is optional (see "Resume here").

## Resume here

**Steps A to D of the owner's decision of 2026-11-11 are done (same day):**

- A. `frontend/deploy-pages.sh` written and run. The demo is live (HTTP 200, assets
  load) at https://r-pal-aihub.github.io/Ai-powered-video-recommendation-system-for-students/
  Pages needed no manual switch-on. To republish after frontend changes:
  `bash frontend/deploy-pages.sh` from Git Bash. Not done: a click-through of the
  live site in a browser (it was browser-checked locally before publishing).
- B. `start-waypoint.bat` in the root: checks `backend\.venv`, builds `frontend\dist`
  if missing, opens http://127.0.0.1:8000, runs uvicorn. **Written but not run**: this
  PC runs short of memory, so the owner's first double-click is its first test.
- C. `README.md` in the root (demo link and limits, PC setup and launcher, settings,
  Docker and Render as optional, republishing the demo). `STATUS.md` removed.
- D. This note updated, committed and pushed.

**Owner's instruction (2026-11-11, newest): finish everything, so that the owner only
has to double-click and sign up. Reflect every change in these notes, and keep
`nextAi.txt` (root) current: it is a copy-paste prompt for another AI to continue.**

### Finishing pass

Do in order. Mark each item done here, with what was verified, before moving on.

1. [~] CI. Checked 2026-11-11: frontend build and evaluation gate pass; on SQLite
   and on PostgreSQL every test passed except one,
   `test_blocked_youtube_degrades_gracefully_and_schedules_a_retry`. Cause: a real
   race. The "stop asking YouTube after 3 refusals in a row" decision was taken by
   the thread that collects results, so fast worker threads could request every
   video first. Fixed: the worker threads now count refusals themselves
   (`_BlockWatch` in `services/pipeline.py`). **Still to confirm: the CI run of the
   commit with this fix is green, and the Docker image job (it only runs when the
   tests pass) builds and publishes.** Read results without a login:
   `curl -s .../actions/runs?per_page=3`, `.../actions/runs/<id>/jobs`, and
   `.../check-runs/<job id>/annotations` (failing tests appear there as
   annotations, thanks to `pytest-github-actions-annotate-failures`; raw logs need
   a login).
2. [x] Unit tests (2026-11-11): `tests/test_jobs.py`, `test_youtube.py`,
   `test_ocr.py`, `test_document_formats.py`. 181 tests pass, lint clean, gate
   25/25, coverage 82% -> 90%. They found one bug, now fixed: a text file saved by
   Windows Notepad as "Unicode" (UTF-16) was refused as unsupported
   (`sniff_kind` in `services/documents.py`). `backend/.coverage` is no longer
   tracked in git.
3. [ ] Run the full app as `start-waypoint.bat` does (fresh `app.db`): sign up,
   make a course, add a playlist and a syllabus, analyse, open the path. Include
   file upload through the screen and topic reorder by drag. Stop the server after.
4. [ ] More real playlists in other subjects, and one non-English playlist.
5. [ ] Click through the live demo in a browser.
6. [ ] Final state: clean `backend/data/app.db` (no test account), docs and
   `nextAi.txt` final, everything pushed.

Cannot be done here (recorded, not faked): YouTube Data API path (no key), YouTube
watch time (not offered by YouTube), Docker run on this PC.

**Older list (superseded by the finishing pass):**

1. The owner double-clicks `start-waypoint.bat` and signs up once (`backend/data/app.db`).
2. The first CI run (`ci.yml`, `7c94784`) was never checked; the PostgreSQL job has
   never run. Not a priority for the owner. Check without `gh`:
   `curl -s https://api.github.com/repos/R-PAl-AIhub/Ai-powered-video-recommendation-system-for-students/actions/runs?per_page=3`
3. "To do, in order" items 5 and 6 below (unit tests, more real playlists).

Earlier plan, kept for the record (all done or replaced by the above):

**Owner's instruction (2026-11-11): finish, then deploy on GitHub or Vercel, whichever
is feasible.** Vercel cannot host the backend (see [[Decisions]]); the plan is a static
demo on GitHub Pages, a Docker image on GHCR and a `render.yaml` for the full stack.

**Owner's decision (2026-11-11, latest, overrides the steps below where they differ):**
keep the whole app (Docker, CI, render.yaml stay in the repo), but put ONLY the demo
online (GitHub Pages, read-only), and give the owner the FULL app on his own PC.
No CI/CD is needed for publishing: build and push the demo from this machine.
Done already: `build:pages` script in `frontend/package.json`; `frontend/dist-pages/`
in `.gitignore`. To do, in order:

A. `frontend/deploy-pages.sh` (run from Git Bash): `cd frontend`,
   `MSYS_NO_PATHCONV=1 VITE_DEMO=1 PAGES_BASE=/Ai-powered-video-recommendation-system-for-students/ npm run build:pages`,
   copy `dist-pages/index.html` to `dist-pages/404.html`, create empty
   `dist-pages/.nojekyll`, then in `dist-pages`: `git init -b gh-pages`, add, commit,
   `git push --force <origin url> gh-pages`. Run it, then open
   https://r-pal-aihub.github.io/Ai-powered-video-recommendation-system-for-students/
   If it stays 404 after a few minutes: GitHub Settings > Pages > Deploy from branch
   `gh-pages`, folder `/` (ask the owner, or use his logged-in browser).
B. `start-waypoint.bat` in the project root (owner's full local app, double-click):
   `cd /d "%~dp0"`; if `frontend\dist\index.html` is missing run `npm run build` in
   `frontend`; `start "" http://127.0.0.1:8000`; then in `backend`:
   `.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`.
   Uses `backend/data/app.db` (sign up once). Do not leave the server running after
   testing: this PC runs short of memory.
C. README.md in the root: live demo link (read-only), how to run the full app on
   the PC (`start-waypoint.bat`, first-time setup: `python -m venv .venv`,
   `pip install -r requirements.txt`, `npm install`), Docker/Render as optional.
D. Update this note and commit and push after each step. Leave `ci.yml` as is (its
   first run was never checked; not a priority for the owner).

**Next action, in order:**

1. ~~Study material backend~~ (done 2026-11-11, `services/readings.py`, migration 0005).
2. ~~Study material UI~~ (done 2026-11-11; builds. Visual check happens on the
   static demo in step 5, which carries sample readings; the machine was too short
   of memory to run the model server for a browser check).
3. ~~Deployment files~~ (done 2026-11-11): `Dockerfile` (Node build stage, Python
   3.13 runtime, models baked into `/opt/models`, non-root, health check),
   `.dockerignore`, `docker-compose.yml` (PostgreSQL, API with `RUN_WORKER=false`,
   separate worker sharing the `/data` volume), `render.yaml` (standard plan for the
   models' memory), `.env.example`. No Docker on this machine: the image is first
   built by CI (step 4).
4. ~~CI~~ (pushed 2026-11-11, `7c94784`, `.github/workflows/ci.yml`: lint, tests on
   SQLite and PostgreSQL via `TEST_DATABASE_URL`, evaluation gate, frontend build,
   Docker image to `ghcr.io/r-pal-aihub/waypoint`). **Result of the first run not yet
   checked.** Check it without `gh`:
   `curl -s https://api.github.com/repos/R-PAl-AIhub/Ai-powered-video-recommendation-system-for-students/actions/runs?per_page=3`
   (then `.../actions/runs/<id>/jobs` for failing steps). The PostgreSQL job has never
   run before; expect real bugs there and fix them.
5. **GitHub Pages demo: code done and browser-checked locally, NOT yet published.**
   Done: `VITE_DEMO=1` build answers from `frontend/src/demo-data.json` (made by
   `backend/evaluation/export_demo.py` from a copy of `data/demo.db` with OSTEP and
   Wikipedia readings; no real name or e-mail in it), `src/demo.ts`, `IS_DEMO` in
   `api.ts`, prefilled sign-in with a demo notice in `Auth.tsx`, router `basename`
   from `BASE_URL`, `base` from `PAGES_BASE` in `vite.config.ts`. Checked at 1440 and
   390 wide: sign-in, course list, Path (readings on gaps, "pp. 11–12, § 31.5
   Reader-Writer Locks"), Sources, read-only message on edits, no console errors.
   **Remaining, in order:**
   a. Add `"build:pages": "tsc --noEmit && vite build --outDir dist-pages"` to
      `frontend/package.json`, and `frontend/dist-pages/` to `.gitignore`.
   b. After building, copy `dist-pages/index.html` to `dist-pages/404.html` (deep
      links on Pages) and add an empty `dist-pages/.nojekyll`.
   c. Write `.github/workflows/pages.yml`: on push to main (paths `frontend/**`),
      `npm ci`, then `VITE_DEMO=1 PAGES_BASE=/${{ github.event.repository.name }}/
      npm run build:pages`, the step b copies, then force-push `dist-pages` to the
      `gh-pages` branch with `GITHUB_TOKEN` (`permissions: contents: write`).
   d. Push, then check https://r-pal-aihub.github.io/Ai-powered-video-recommendation-system-for-students/
      If it stays 404, Pages must be switched on once in the repository settings
      (Settings > Pages > Deploy from branch `gh-pages`, folder `/`); ask the owner
      or use their logged-in browser.
   Local build tip on Windows Git Bash: prefix `MSYS_NO_PATHCONV=1`, or the base
   path gets rewritten into a Windows path.
6. README: live demo link and what it cannot do (read-only, no server), `docker
   compose up`, the Render blueprint (standard plan; 512 MB is too small for the
   models unless `RERANKER_MODEL` is empty), configuration from `.env.example`.
   It replaces the root `STATUS.md` pointer.

Earlier: **study material beyond videos** (owner, 2026-11-11): let the student add books, articles, web pages and notes as study sources, and recommend the right pages or sections per topic alongside the videos, especially for gaps. Every buildable gap in [[Requirements Checklist]] is closed (2026-11-11). Previously: **close every gap in [[Requirements Checklist]]** (owner, 2026-11-11:
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
8. ~~**Optional ASR**~~ (done 2026-11-11). Was: (faster-whisper) for videos without captions, paced, off by
   default.
9. ~~**LDA topic map**~~ (done 2026-11-11). Was: of the playlists (sklearn), shown as a coverage view.

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
7. ~~README~~ (done 2026-11-11).

## Known problems

- YouTube was blocking this machine on 2026-11-10 after one burst of requests.
  Pacing was added afterwards; whether the block has lifted is untested.
- Multi-language support is implemented but unverified on real videos.
- The YouTube Data API backend is written but has never run against the real API
  (no key was available).
- PostgreSQL has run only in CI (all tests pass there); never on this PC.
- On the real playlist, "Concept of Operating Systems" picks video 2 rather than
  video 1. Left as is.

## Checkpoint log

Newest first. Each line is a pushed commit on `main`.

| Date | Commit | What changed |
|---|---|---|
| 2026-11-11 | (this commit) | Finishing pass 1 and 2: fixed the race in stopping after a YouTube block (the one CI failure, same on SQLite and PostgreSQL); unit tests for jobs, youtube, ocr, documents (181 tests, 90% coverage); UTF-16 text files now accepted. |
| 2026-11-11 | `6c692ff` | CI reports failing tests as annotations (readable without a login). |
| 2026-11-11 | `a1cf310` | `nextAi.txt` handoff prompt; finishing-pass plan in this note. |
| 2026-11-11 | (this commit) | Demo published to GitHub Pages with `frontend/deploy-pages.sh` (live, HTTP 200); `start-waypoint.bat` for the full app on the owner's PC (not yet run); `README.md` replaces `STATUS.md`. |
| 2026-11-11 | (this commit) | Static demo mode for GitHub Pages (`VITE_DEMO=1`, real course snapshot with readings, export script); checked in the browser locally. Not yet published; see "Resume here" step 5. |
| 2026-11-11 | `7c94784` | CI workflow (lint, SQLite and PostgreSQL tests, evaluation gate, frontend build, image to GHCR); first run not yet checked. |
| 2026-11-11 | `ca18315` | Deployment files: Dockerfile, docker-compose (PostgreSQL + API + worker), render.yaml, .env.example; Vercel ruled out (recorded in [[Decisions]]). Not yet built: no Docker here; CI builds it next. |
| 2026-11-11 | `2a2eb3c` | Study material UI: Sources tab section (web page or online PDF, upload, paste); "Also read" on path rows; readings as the main suggestion on gap rows; gap stat counts gaps the reading explains. Frontend builds. |
| 2026-11-11 | `3b88844` | Study material beyond videos (backend): `reading` documents (files, pasted text, web pages via `POST /documents/url` with SSRF protection), passages with PDF pages and section headings, readings per topic matched like videos (migration 0005). Real check with OSTEP chapters and Wikipedia: 11 of 12 readings on the right section, 8 fill video gaps. 74 tests pass; gate passes. |
| 2026-11-11 | (this commit) | Topics taught across several stretches: part series, repeated teaching, and set cover of a topic's parts across playlists, with uncovered parts listed (migration 0004). Six worst-case tests; gate checks zero unneeded splits. 55 tests pass. |
| 2026-11-11 | (this commit) | Whole-video picks say "study the whole video". Browser-checked on the restarted server: ranges in Path, Questions and Search; player opens at the start second; topic map, new label and order button present. |
| 2026-11-11 | (this commit) | Study ranges tuned on the real playlist (whole video when the title names only this topic; strict start, tolerant end); key-term check fixes "disk scheduling" matching a CPU lecture; ASR also retries caption-less videos; demo data rebuilt; docs brought up to date. 49 tests pass; gate 25/25. |
| 2026-11-11 | (this commit) | LDA topic map of the playlists (Focus tab), with matching syllabus topics and themes beyond the syllabus. Every buildable checklist item is done. 49 tests pass. |
| 2026-11-11 | (this commit) | Optional speech recognition (faster-whisper, ffmpeg decode) for caption-less videos; verified on a real lecture. YouTube no longer blocks this machine. 48 tests pass. |
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
