"""Logging, request ids and Prometheus metrics."""

from __future__ import annotations

import contextvars
import json
import logging
import time
import uuid

from prometheus_client import Counter, Histogram
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")

REQUESTS = Counter("http_requests_total", "HTTP requests", ["method", "route", "status"])
LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency",
    ["method", "route"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30),
)
JOBS_TOTAL = Counter("pipeline_jobs_total", "Finished pipeline jobs", ["status"])
JOB_DURATION = Histogram(
    "pipeline_job_duration_seconds",
    "Pipeline job duration",
    buckets=(1, 5, 15, 30, 60, 120, 300, 600, 1800),
)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_var.get(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(production: bool) -> None:
    handler = logging.StreamHandler()
    if production:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(logging.INFO)
    for noisy in ("httpx", "httpcore", "yt_dlp", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def _route_template(request: Request) -> str:
    """The route pattern (/api/projects/{project_id}), so metrics stay low-cardinality."""
    route = request.scope.get("route")  # set by the router once a route has matched
    template = getattr(route, "path_format", None) or getattr(route, "path", None)
    if not template:
        return "unmatched"
    if template == "/{path:path}":
        return "spa"
    return template


SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Content-Security-Policy": (
        "default-src 'self'; "
        "img-src 'self' data: blob: https://i.ytimg.com https://img.youtube.com; "
        "frame-src https://www.youtube-nocookie.com https://www.youtube.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' data: https://fonts.gstatic.com; "
        "script-src 'self' 'wasm-unsafe-eval'; "
        "worker-src 'self' blob:; "
        "connect-src 'self' data: blob:; "
        "object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
    ),
}


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assigns a request id, records metrics, and adds security headers."""

    def __init__(self, app, *, hsts: bool = False):
        super().__init__(app)
        self._hsts = hsts

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("x-request-id", "")[:64] or uuid.uuid4().hex[:16]
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers["X-Request-ID"] = request_id
            for name, value in SECURITY_HEADERS.items():
                response.headers.setdefault(name, value)
            if self._hsts:
                response.headers.setdefault(
                    "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
                )
            return response
        finally:
            route = _route_template(request)
            if route not in ("/metrics", "/healthz"):
                REQUESTS.labels(request.method, route, str(status)).inc()
                LATENCY.labels(request.method, route).observe(time.perf_counter() - started)
            request_id_var.reset(token)
