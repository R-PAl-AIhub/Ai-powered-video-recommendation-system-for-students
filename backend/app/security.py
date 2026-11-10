"""Password hashing, session tokens and a small rate limiter."""

from __future__ import annotations

import base64
import hashlib
import threading
import time
from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from .config import get_settings

ALGORITHM = "HS256"
COOKIE_NAME = "session"


def _prehash(password: str) -> bytes:
    # bcrypt only reads 72 bytes; hashing first keeps long passphrases fully significant.
    return base64.b64encode(hashlib.sha256(password.encode("utf-8")).digest())


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_prehash(password), bcrypt.gensalt(rounds=12)).decode("ascii")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_prehash(password), hashed.encode("ascii"))
    except ValueError:
        return False


def create_token(user_id: int) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_minutes),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def read_token(token: str) -> int | None:
    """The user id carried by a valid token, else None."""
    try:
        payload = jwt.decode(token, get_settings().secret_key, algorithms=[ALGORITHM])
        return int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None


class RateLimiter:
    """Sliding-window limiter, per key, in process memory.

    Good for one instance; behind several instances each keeps its own count, so
    put a shared limiter (reverse proxy or Redis) in front for strict limits.
    """

    def __init__(self, limit: int, window_seconds: float = 60.0):
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] > self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                return False
            hits.append(now)
            if len(self._hits) > 20000:  # bound memory under key churn
                for stale in [k for k, v in self._hits.items() if not v or now - v[-1] > self.window]:
                    del self._hits[stale]
            return True

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()
