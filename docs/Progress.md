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

**Next action: look at the frontend in a browser and fix what is wrong.**

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
2. Check, in both themes and at phone width. **Done so far** (desktop, 1440 wide):
   landing hero (light), sign in, course list, Path tab, Questions tab, the player
   (opens the right embed at the right second), feedback and undo (dark). **Still to
   check:** Sources, Focus, Search and Topics tabs (including drag-reorder), phone
   width (about 390 wide), light theme inside the app. Demo account:
   `demo@example.com` / `demo-password-1` in `data/demo.db`.
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

1. **Browser check of the frontend** (see "Resume here").
2. **Alembic migrations.** Needed for PostgreSQL and for upgrading existing SQLite
   databases (the demo database failure above is exactly this problem).
3. **Deployment**: `Dockerfile` (build the frontend, install the backend, bake the
   model files in, install `libgl1` for OCR), `docker-compose.yml` (API, worker,
   PostgreSQL), `render.yaml`, `.env.example`.
4. **CI/CD** in `.github/workflows/`: lint, tests on SQLite and PostgreSQL, the
   evaluation gate, frontend build, Docker build and publish to GHCR.
5. **Unit tests** for `documents.py`, `ocr.py`, `jobs.py`, `youtube.py`.
6. **Real-world checks still owed**: more real playlists in other subjects, and
   non-English playlists, once YouTube stops rate-limiting this machine. Then decide
   on a multilingual default model and a shared transcript cache across projects.
7. **README** for users and deployers, replacing the root `STATUS.md` pointer.

## Known problems

- An existing SQLite database from an older version fails at startup (no migrations).
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
| 2026-11-11 | (this commit) | Browser check of the signed-in app. Added an undo bar for feedback: "Wrong topic", "Irrelevant" and "I know this" change the row completely, so there was no way back. Verified in the browser: wrong topic swaps in the next video, undo restores it. Removed a redundant iframe attribute. Found that a video with only a mis-labelled Turkish caption track produced garbage snippets in the cached data; the current pipeline already marks such captions as unreadable (`foreign`), confirmed by re-running on the demo data. |
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
