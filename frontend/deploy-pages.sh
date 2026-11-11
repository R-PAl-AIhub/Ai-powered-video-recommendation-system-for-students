#!/usr/bin/env bash
# Publishes the read-only demo to GitHub Pages (branch gh-pages).
# Run from Git Bash:  bash frontend/deploy-pages.sh
set -euo pipefail

cd "$(dirname "$0")"

REPO_NAME="Ai-powered-video-recommendation-system-for-students"
ORIGIN_URL="$(git -C .. remote get-url origin)"

# MSYS_NO_PATHCONV stops Git Bash rewriting the base path into a Windows path.
MSYS_NO_PATHCONV=1 VITE_DEMO=1 PAGES_BASE="/${REPO_NAME}/" npm run build:pages

cp dist-pages/index.html dist-pages/404.html   # deep links on Pages
: > dist-pages/.nojekyll                        # serve files as they are

cd dist-pages
rm -rf .git
git init -q -b gh-pages
git add -A
git commit -q -m "Publish demo ($(git -C ../.. rev-parse --short HEAD))"
git push --force "$ORIGIN_URL" gh-pages
rm -rf .git

echo "Published: https://r-pal-aihub.github.io/${REPO_NAME}/"
