# Progress

Back to [[Project Map]]. **This is the single source of truth for where the work
stands.** Update it at every checkpoint: move items between sections, add a line to
the checkpoint log, and rewrite "Resume here".

Last updated: 2026-11-12.

## State in one paragraph

The backend and frontend are complete, tested and browser-checked, with migrations.
Study material beyond videos is built, with its UI. The read-only demo is live on
GitHub Pages, the owner runs the full app on his PC with `start-waypoint.bat`, and
the README is written. The repository is public again and the demo is back online
(2026-11-12). The app now has three ways to get a video's words when YouTube refuses
captions (listen, paste, retry). Since 2026-11-12 afternoon listening is ON by default
(owner: "I want the transcript anyhow"): the path is built from captions first, then
a second job listens to every video left without words and updates the path.
**The finishing pass is complete (2026-11-12): every item is done, and the owner
only has to double-click `start-waypoint.bat` and sign up.** See "Finishing pass"
for what was verified and "Known problems" for the weak points that are left.

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

### Repository visibility (resolved 2026-11-12)

The repository was private for some hours on 2026-11-12, which switched GitHub
Pages off (demo 404) and hid CI from plain `curl`. The owner made it public again at
about 09:55. Pages stays off after that until something is pushed to `gh-pages`:
`bash frontend/deploy-pages.sh` brought the demo back (HTTP 200 a minute later).
If the demo is ever 404 again, check `"private"` and `"has_pages"` in
`curl -s https://api.github.com/repos/R-PAl-AIhub/Ai-powered-video-recommendation-system-for-students`.

### Finishing pass

Do in order. Mark each item done here, with what was verified, before moving on.

1. [x] CI (2026-11-11). The run of `ed24d3c` is green in every job: lint and tests
   on SQLite, tests on PostgreSQL (first time ever), evaluation gate, frontend
   build, and the Docker image built and published to
   `ghcr.io/r-pal-aihub/waypoint`. The only failure before was a real race: the
   "stop asking YouTube after 3 refusals in a row" decision was taken by the thread
   that collects results, so fast worker threads could request every video first.
   Fixed with `_BlockWatch` in `services/pipeline.py`. Read CI without a login:
   `curl -s .../actions/runs?per_page=3`, `.../actions/runs/<id>/jobs`,
   `.../check-runs/<job id>/annotations` (failing tests show as annotations).
   Not done: nobody has *run* the published image (no Docker on this PC).
2. [x] Unit tests (2026-11-11): `tests/test_jobs.py`, `test_youtube.py`,
   `test_ocr.py`, `test_document_formats.py`. 181 tests pass, lint clean, gate
   25/25, coverage 82% -> 90%. They found one bug, now fixed: a text file saved by
   Windows Notepad as "Unicode" (UTF-16) was refused as unsupported
   (`sniff_kind` in `services/documents.py`). `backend/.coverage` is no longer
   tracked in git.
3. [x] Full app in the browser (2026-11-11), on a throwaway database, now deleted.
   Worked: landing page, sign-up, new course, add a real playlist, upload a file
   through the screen (a Notepad "Unicode" file), paste a past paper, build and
   update the path, Path tab with study ranges, player (opens at the start second,
   stops at the end second), "Wrong topic" and Undo, Focus, Questions, Search
   (found and not found), Topics reorder by drag (saved to the server).
   `start-waypoint.bat` itself was run: the server answered on
   http://127.0.0.1:8000 and created an empty `backend/data/app.db`. The server
   was stopped afterwards. Screenshots time out in this browser, so the look was
   not checked by eye, only the content and behaviour.
   Found and fixed: a past question with no direct answer now points to where its
   topic is taught (`link_questions` in `services/questions.py`); real OS course
   unchanged (6 of 8 answered). The fallback has its own tests since 2026-11-12
   (`tests/test_question_fallback.py`: answered where the topic is taught, left
   unanswered when the topic is a gap, a direct answer is kept).
4. [x] More real playlists (2026-11-12). A database-systems playlist in English
   and a 15-lecture playlist taught in Hindi (`PLjgyGylma3IFNC7sNZOSbwGQPK_MYtCFW`,
   Gate Smashers, normalization), both judged against the transcripts, not the
   titles; see [[Matching Pipeline]], "Results". The owner's meaning of
   "non-English": the teacher may speak any language and the transcript may be in
   any language; the transcript is what gets matched.
   Hindi playlist: YouTube refused every caption download from this PC (HTTP 429,
   by every tool), so 10 lectures use the English captions copied from "Show
   transcript" in the owner's Chrome (`backend/data/hi-captions/`, not in git) and
   5 lectures (26, 35, 36, 37, 38) were heard by Whisper `small` on this PC and
   translated to English (91 minutes of audio in 36 minutes). Result: 15 of 21
   topics matched, all 15 on a lecture that teaches the topic, 4 of them starting
   late; 6 gaps, 5 right and 1 wrong ("Need for normalization"). Three errors
   found by the check were fixed with tests: the "sure first stage" rule, the
   sound-alike correction of heard title terms ("closer" to "closure"), and the
   full title bonus for a title that names the whole topic. The other two real
   courses are unchanged by the fixes. Cache: `backend/data/live-hi-dbms.db`,
   output: `backend/data/live-hi-dbms.log` (not in git). To repeat:
   `PYTHONIOENCODING=utf-8 .venv/Scripts/python -m evaluation.live --name hi-dbms
   --subject "Database Management Systems" --playlist <link>
   --syllabus evaluation/samples/dbms_normalization_syllabus.txt
   --transcripts data/hi-captions --raw` in `backend/`.
   Not possible and not built: calling YouTube's transcript-panel service from a
   script (it has to pose as a browser; refused here as bot-check circumvention,
   and it is not something to ship).
5. [x] Live demo clicked through in a browser (2026-11-12), on the real address
   after it came back: a deep link to `/signin` loads (GitHub's 404 fallback, the
   one expected console message), demo sign-in, course list (36/58 matched, 22
   gaps), Path with study ranges and "Also read", the player (opens at second 637
   for a 10:37 start), the read-only message on "Wrong topic", Focus, Questions (6
   of 8), Topics, Sources, Search (found, and not found for what the playlist
   lacks). Not checked: phone width (the window could not be resized) and the look
   by eye. The same build was also clicked through locally before that.
6. [x] Final state (2026-11-12, about 16:35): `backend/data/app.db` has 0 users
   and 0 courses (no test account); no server and no Python process is left
   running; the working tree is clean and pushed. CI is green in every job (lint
   and tests on SQLite, tests on PostgreSQL, evaluation gate, frontend build,
   Docker image) for `78ec77b`, the last commit that changes code; the commit
   after it changes these notes and `nextAi.txt` only. The demo answers HTTP 200.
   What the owner does: double-click `start-waypoint.bat` and sign up.

7. [x] Listening by default (owner, 2026-11-12 14:40: "if there is no transcript
   download the audio and extract the transcript out of it, I want the transcript
   anyhow"; everything local, on his PC). Built: `ASR_ENABLED` defaults to `true`,
   `ASR_MODEL` to `small`, `ASR_MAX_MINUTES` to 180; the first job reads captions
   and builds the path, then `queue_listening` (`services/jobs.py`) queues a second
   job that listens (`options["listen"]`) and rebuilds the path; status `silent`
   for a video with nothing to hear, so it is not listened to again; without
   ffmpeg the app switches listening off and logs one line; a video added from a
   search is not listened to inside the web request. Verified: 208 tests pass
   (4 new in `tests/test_listen_when_blocked.py`), lint clean, gate PASS (25/25),
   `npm run build` passes, and on this PC the default settings give
   `faster-whisper:small` (ffmpeg found). **Seen in the real app (2026-11-12, about 15:00)** on a throwaway copy of the
   demo database with default settings: "Update the path" finished in 12 seconds
   with the path ready and the note "9 videos did not give captions that can be
   read. They are listened to next..."; a second job started by itself; the Path
   screen stayed usable (29 playable rows) under the line "Listening to videos
   without captions: 1 of 9 done"; the first real video was heard (9 left became
   8). The server was then stopped and the copy deleted; the other 8 were not
   waited for.
   Added afterwards (owner: "the user shouldn't decide what to listen or what
   not"; least discomfort): the screens no longer ask for a pasted transcript
   when the app will listen by itself (`listening` flag per video; quiet note on
   the Path row, "Nothing for you to do" on Sources). Whisper gets the title and
   subject as a spelling hint. 210 tests pass, lint clean, gate PASS, frontend
   builds. The quiet wording was seen in a browser (2026-11-12, about
   16:20, with the Chrome DevTools tools because the Claude in Chrome extension
   had disconnected) on a throwaway copy of the demo database: Sources says "9
   videos without captions. The app listens to them by itself (about as long as
   the videos) and then updates the path. Nothing for you to do."; three Path
   rows say "Matched on its title for now. The app is listening to this video
   and will update the path by itself."; no "Paste its transcript" link is
   shown; 29 rows stay playable. Read as page text, not by eye. Server stopped,
   copy deleted.
   The owner also pointed to `github.com/lifesized/youtube-transcriber`: it uses
   the same order (captions, then Whisper on the machine). Nothing was copied
   from it (separate Node app, AGPL-3.0, its quick path is a cloud service); see
   [[Decisions]].

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
- A playlist taught in Hindi was run and judged (finishing pass item 4). Captions
  translated by YouTube and a multilingual embedding model are still unverified on
  real videos.
- Study ranges can start late inside the right lecture, and "Need for
  normalization" is a wrong gap on the Hindi playlist (see [[Matching Pipeline]]).
- YouTube refuses caption downloads from this PC (HTTP 429, 2026-11-11 evening to at
  least 2026-11-12 midday). Listening and pasting work around it.
- The YouTube Data API backend is written but has never run against the real API
  (no key was available).
- PostgreSQL has run only in CI (all tests pass there); never on this PC.
- "Three-schema architecture" on the database playlist picks a look-alike title (see [[Matching Pipeline]]).
- On the real playlist, "Concept of Operating Systems" picks video 2 rather than
  video 1. Left as is.

## Checkpoint log

Newest first. Each line is a pushed commit on `main`.

| Date | Commit | What changed |
|---|---|---|
| 2026-11-12 | (this commit) | Finishing pass closed: quiet wording seen in a browser (item 7 done); CI green in every job for `78ec77b`; `app.db` empty, nothing left running (item 6 done). Notes only. |
| 2026-11-12 | `78ec77b` | Hindi playlist finished and judged against its transcripts (item 4 done): 15 of 21 topics matched, all on a lecture that teaches the topic, 4 starting late; 5 right gaps, 1 wrong. Two more fixes from it: a title term heard as a sound-alike word is put back ("closer" to "closure", `restore_title_terms`), and a title that names the whole topic gets the full title bonus (1NF now points to its own lecture). 218 tests pass, lint clean, gate 25/25, the other two real courses unchanged. |
| 2026-11-12 | `96bfbc6` | From judging the Hindi playlist against its transcripts: the reranker may not overrule a nearly certain first stage that the transcript backs ("Insertion deletion and update anomalies" was a gap although lecture 24 teaches it); Whisper gets the title and subject as a spelling hint ("closure" had come out as "closer"). Quieter screens: no request to paste when the app listens by itself. Two-step listening seen working in the real app with a real video. 210 tests pass, lint clean, gate 25/25, the three cached real courses differ only in the intended topic, frontend builds. Demo republished. |
| 2026-11-12 | `66a65e5` | Listening is the default (owner's instruction): captions first and the path, then a second job listens to the videos left without words and updates the path; status `silent`; switches itself off without ffmpeg; `ASR_MODEL=small`, `ASR_MAX_MINUTES=180`; "Nothing could be heard" wording in the paste box. 208 tests pass, lint clean, gate 25/25, frontend builds. Not yet seen in the real app with a real video. Demo republished. |
| 2026-11-12 | `505c0c0` | Words for a video when YouTube refuses captions: listen (`_fetch` in `services/pipeline.py`, also for captions in an unreadable language), or a transcript pasted by the student (`services/pasted.py`, `PUT /videos/{vid}/transcript`, `GET /videos/untranscribed`, "Paste its transcript" on the Path and Sources screens), `--transcripts` in `evaluation/live.py`, audio kept in `DATA_DIR/tmp`. Verified at 14:20 to 14:40: 204 tests pass, lint clean, evaluation gate PASS (25/25, gaps 3/3), `npm run build` passes. Paste box checked in Chrome on a throwaway copy of the demo database (deleted afterwards, server stopped): the Path row of a caption-less video opens the box, a pasted transcript is accepted (HTTP 200), the row then shows a quote from the pasted words and loses the paste link, the Sources list goes from 9 to 8 videos, no console errors. Demo republished after the repository became public again; live demo clicked through; CI green for `e8c1b7e`. |
| 2026-11-12 | (this commit) | Demo build clicked through locally (the online address is still 404); the suggested `youtube-caption-extractor` library also gets HTTP 429 from YouTube; local final state checked (empty `app.db`, no server running). No code changed. |
| 2026-11-12 | (this commit) | Tests for the question fallback (191 tests pass, lint clean, gate 25/25). Non-English run retried: YouTube still refuses caption downloads (HTTP 429), and the Hindi candidate turned out to have English captions. Found the online demo answering 404 because the repository is no longer public; left for the owner to decide. |
| 2026-11-11 | (this commit) | Browser pass of the full app finished; `start-waypoint.bat` run and working; unanswered past questions fall back to where their topic is taught. Non-English run blocked by YouTube rate limiting. |
| 2026-11-11 | (this commit) | Transcript evidence rules in matching (contents read-outs are not teaching; a topic discussed by name counts under any title), found on a real database-systems playlist checked against its transcripts; 188 tests, gate 25/25, real OS course unchanged. CI of `ed24d3c` fully green, including PostgreSQL and the Docker image. Full app verified in the browser up to a finished analysis. |
| 2026-11-11 | `ed24d3c` | Race in stopping after a YouTube block fixed (the one CI failure); unit tests for jobs, youtube, ocr, documents; UTF-16 text files accepted. |
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
