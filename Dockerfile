# Waypoint: one image for the API (which also serves the web app) and the worker.
#
#   docker build -t waypoint .
#   docker run -p 8000:8000 -e SECRET_KEY=$(openssl rand -hex 32) -v waypoint-data:/data waypoint
#
# The embedding model and the reranker are downloaded at build time into
# /opt/models, so a new container starts without fetching anything.

# ---------------------------------------------------------------- web app build
FROM node:22-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ------------------------------------------------------------------ runtime
FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    ENVIRONMENT=production \
    DATA_DIR=/data \
    MODEL_DIR=/opt/models \
    FRONTEND_DIST=/app/frontend/dist \
    PORT=8000

# libgl1 and libglib2.0-0: OpenCV, used by RapidOCR. ffmpeg: speech recognition
# for videos without captions (only used when ASR_ENABLED=true). curl: health check.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 ffmpeg curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install -r requirements.txt

COPY backend/ ./
COPY --from=web /web/dist /app/frontend/dist

# Bake the models into the image. Development settings for this step only:
# production refuses to start without a SECRET_KEY, which a build must not hold.
RUN ENVIRONMENT=development DATA_DIR=/tmp/build-data python -c "\
from app.services.embeddings import get_embedder; \
from app.services.rerank import get_reranker; \
e = get_embedder(); r = get_reranker(); \
print('embedder:', e.name, '| reranker:', r.name if r else None); \
assert r is not None, 'reranker failed to load'" \
    && rm -rf /tmp/build-data

RUN useradd --create-home --uid 10001 waypoint \
    && mkdir -p /data \
    && chown -R waypoint:waypoint /data /opt/models
USER waypoint
VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PORT}/healthz" || exit 1

# The worker runs inside this process unless RUN_WORKER=false; then start a
# second container with `python -m app.worker` (see docker-compose.yml).
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
