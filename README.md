# Waypoint

AI video recommendations for students. Give Waypoint your syllabus and the YouTube
playlists you study from, and it builds an ordered study path: the right video, and
the right minutes in it, for each topic. It also marks the topics your playlists do
not cover, shows which topics matter most in past papers, links past questions to the
moment a video answers them, and suggests pages from your books and notes.

## Live demo (read-only)

**https://r-pal-aihub.github.io/Ai-powered-video-recommendation-system-for-students/**

Press **Sign in** (the form is filled in for you). The demo shows a real Operating
Systems course: the path, the player, gaps, questions, search and study material.

The demo has no server behind it. It shows saved results, so you cannot add
playlists, upload files, run a new analysis or keep changes. For that, run the full
app on your PC.

## Run the full app on your PC (Windows)

### First-time setup

You need [Python](https://www.python.org/downloads/) 3.12 or newer and
[Node.js](https://nodejs.org/) 20 or newer. Then, in a terminal in the project folder:

```bat
cd backend
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
cd ..\frontend
npm install
```

### Every time

Double-click **`start-waypoint.bat`**.

- Your browser opens http://127.0.0.1:8000. If it says it cannot connect, wait a few
  seconds and refresh.
- The first start builds the web app. The first analysis downloads the AI
  models (a few hundred MB), so it needs the internet once.
- Create an account the first time (**Sign up**). The account and all your courses
  stay on your PC, in `backend/data/app.db`.
- To stop Waypoint, close the black window. It uses a lot of memory while it runs.

After you change the frontend code, delete the `frontend\dist` folder; the next start
builds it again.

### Settings (optional)

Waypoint works with no settings. To change one, copy `.env.example` to `backend/.env`
and edit it there. For a PC, remove the `ENVIRONMENT=production` line. Useful ones:

| Setting | What it does |
|---|---|
| `YOUTUBE_API_KEY` | Uses the official YouTube Data API (likes, dates, comment sentiment) |
| `GOOGLE_VISION_API_KEY` | Better reading of handwritten notes |
| `ASR_ENABLED=true` | Speech recognition for videos without captions (needs ffmpeg; slow) |
| `RERANKER_MODEL=` (empty) | Less memory, slightly lower matching quality |

## Other ways to run it (optional)

- **Docker**: copy `.env.example` to `.env`, set `SECRET_KEY`, then
  `docker compose up --build`. This starts PostgreSQL, the API and a separate worker,
  at http://localhost:8000.
- **Render**: `render.yaml` is a blueprint for the full stack. Use the standard plan:
  512 MB is too little memory for the models unless `RERANKER_MODEL` is empty.

Vercel and GitHub Pages cannot host the full app, because it needs a long-running
Python server. That is why only the demo is online.

## Update the online demo

From Git Bash, in the project folder:

```bash
bash frontend/deploy-pages.sh
```

It builds the demo and pushes it to the `gh-pages` branch. The demo's data is
`frontend/src/demo-data.json`, made by `backend/evaluation/export_demo.py`.

## For developers

- Code: `backend/` (Python, FastAPI) and `frontend/` (React, Vite, three.js).
- Notes: [`docs/`](docs/) is an Obsidian vault in plain Markdown. Start with
  [`docs/Project Map.md`](docs/Project%20Map.md), then
  [`docs/Progress.md`](docs/Progress.md) for the current state and next step.
- Tests: in `backend`, `.venv\Scripts\python -m pytest`. Frontend check:
  `npm run build` in `frontend`.
