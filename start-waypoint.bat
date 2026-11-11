@echo off
rem Waypoint: the FULL app on this PC. Double-click to start; close this window to stop.
setlocal
cd /d "%~dp0"
title Waypoint

if not exist "backend\.venv\Scripts\python.exe" (
  echo First-time setup is not done yet. In a terminal, run:
  echo   cd backend
  echo   python -m venv .venv
  echo   .venv\Scripts\python -m pip install -r requirements.txt
  echo See README.md, "Run the full app on your PC".
  pause
  exit /b 1
)

if not exist "frontend\dist\index.html" (
  echo Building the web app, first run only...
  pushd frontend
  if not exist "node_modules" call npm install
  call npm run build
  popd
  if not exist "frontend\dist\index.html" (
    echo The web app did not build. See the messages above.
    pause
    exit /b 1
  )
)

echo.
echo Waypoint is starting at http://127.0.0.1:8000
echo The page opens in your browser. If it says "cannot connect", wait a few
echo seconds and refresh: the models take a moment to load.
echo Close this window to stop Waypoint.
echo.

start "" http://127.0.0.1:8000
cd backend
.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

echo.
echo Waypoint has stopped.
pause
