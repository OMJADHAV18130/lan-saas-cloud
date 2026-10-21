"""Very small in-process sliding-window rate limiter.

Purpose: slow down brute-force attempts against /api/auth/*.

Limitations (documented deliberately - this is a lab build):
  * state is per-process, so with multiple Uvicorn workers the effective
    limit is multiplied by the number of workers;
  * it is memory only and resets on restart.
For a hardened deployment put a reverse proxy (nginx `limit_req`) or Redis in
front of the controller instead.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from typing import Callable

from fastapi import Request

from app.core.errors import RateLimited


class SlidingWindowLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str, limit: int, window_seconds: int) -> None:
        now = time.monotonic()
        cutoff = now - window_seconds
        with self._lock:
            bucket = self._hits[key]
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= limit:
                retry_after = max(1, int(window_seconds - (now - bucket[0])))
                raise RateLimited(
                    "Too many requests. Please try again later.",
                    details=[{"retry_after_seconds": retry_after}],
                )
            bucket.append(now)

    def reset(self, key: str | None = None) -> None:
        with self._lock:
            if key is None:
                self._hits.clear()
            else:
                self._hits.pop(key, None)


limiter = SlidingWindowLimiter()


def client_ip(request: Request) -> str:
    """Best-effort client address (X-Forwarded-For aware)."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def auth_rate_limit(scope: str) -> Callable[[Request], None]:
    """Dependency factory: `Depends(auth_rate_limit("login"))`."""
    from app.core.config import get_settings

    def _dependency(request: Request) -> None:
        settings = get_settings()
        if settings.environment == "test":  # pragma: no cover
            return
        key = f"{scope}:{client_ip(request)}"
        limiter.check(key, settings.auth_rate_limit_attempts,
                      settings.auth_rate_limit_window_seconds)

    return _dependency
