"""Shared rate limiter for OmniDome services.

Provides a simple in-memory sliding-window rate limiter that can be used
as a FastAPI middleware or dependency.

Usage as middleware (in service main.py):

    from services.common.rate_limiter import RateLimiterMiddleware
    app.add_middleware(RateLimiterMiddleware, max_requests=60, window_seconds=60)

Usage as dependency on specific endpoints:

    from services.common.rate_limiter import RateLimiter

    _auth_limiter = RateLimiter(max_requests=10, window_seconds=60)

    @app.post("/users")
    async def create_user(..., limiter: None = Depends(_auth_limiter.check)):
        ...
"""

from __future__ import annotations

import hashlib
import logging
import time
from collections import defaultdict
from typing import Optional

from fastapi import HTTPException, Request, status

logger = logging.getLogger(__name__)


def identity_key(request: Request) -> str:
    """Stable per-caller limiter key: x-user-id, else hash of the bearer token, else client host.

    Behind a proxy every request shares the proxy's client.host, so keying on the host alone
    makes one caller's flood exhaust the bucket for everybody.
    """
    user = (request.headers.get("x-user-id") or "").strip()
    if user:
        return "u:" + user[:128]
    auth = request.headers.get("authorization") or ""
    if auth.lower().startswith("bearer ") and auth[7:].strip():
        return "t:" + hashlib.sha256(auth[7:].strip().encode()).hexdigest()[:32]
    return "ip:" + (request.client.host if request.client else "unknown")


class RateLimiter:
    """Sliding-window rate limiter keyed by client identifier.

    Args:
        max_requests: Maximum number of requests allowed in the window.
        window_seconds: Size of the sliding window in seconds.
        key_func: Optional callable that extracts a key from a FastAPI request.
                  Defaults to using request.client.host.
    """

    def __init__(
        self,
        max_requests: int = 60,
        window_seconds: float = 60.0,
        key_func: Optional[object] = None,
        max_keys: int = 10000,
    ):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.max_keys = max_keys
        self._key_func = key_func or (lambda r: r.client.host if r.client else "unknown")
        self._requests: dict[str, list[float]] = defaultdict(list)

    def _cleanup(self, key: str, now: float) -> None:
        """Remove timestamps outside the current window."""
        cutoff = now - self.window_seconds
        self._requests[key] = [t for t in self._requests[key] if t > cutoff]

    def _evict(self, now: float) -> None:
        """Bound memory: drop idle keys, then the least recently used ones."""
        cutoff = now - self.window_seconds
        for k in [k for k, v in self._requests.items() if not v or v[-1] <= cutoff]:
            del self._requests[k]
        if len(self._requests) >= self.max_keys:
            # still full of live keys: drop the least recently used 10% so this is not O(n log n) per request
            target = max(1, self.max_keys - max(1, self.max_keys // 10))
            oldest = sorted(self._requests, key=lambda k: self._requests[k][-1])
            for k in oldest[: len(self._requests) - target]:
                del self._requests[k]

    async def check(self, request: Request) -> None:
        """FastAPI dependency that raises HTTP 429 if rate limit exceeded."""
        self.check_key(self._key_func(request))  # type: ignore[operator]

    def check_key(self, key: str) -> None:
        """Same as check() but with an explicit key (for keys derived from the request body)."""
        now = time.monotonic()
        if key not in self._requests and len(self._requests) >= self.max_keys:
            self._evict(now)
        self._cleanup(key, now)

        if len(self._requests[key]) >= self.max_requests:
            logger.warning("Rate limit exceeded for %s (%d req/%ds)", key, self.max_requests, int(self.window_seconds))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded. Please try again later.",
                headers={"Retry-After": str(int(self.window_seconds))},
            )

        self._requests[key].append(now)


class RateLimiterMiddleware:
    """Starlette/FastAPI middleware that applies rate limiting to all requests.

    Args:
        app: The ASGI app (set by Starlette automatically).
        max_requests: Maximum requests per window per client IP.
        window_seconds: Sliding window size in seconds.
        exclude_paths: Set of path prefixes to exclude from rate limiting.
    """

    def __init__(
        self,
        app,
        max_requests: int = 100,
        window_seconds: float = 60.0,
        exclude_paths: Optional[set[str]] = None,
    ):
        self.app = app
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.exclude_paths = exclude_paths or {"/health", "/docs", "/openapi.json", "/redoc"}
        self._requests: dict[str, list[float]] = defaultdict(list)

    def _cleanup(self, key: str, now: float) -> None:
        cutoff = now - self.window_seconds
        self._requests[key] = [t for t in self._requests[key] if t > cutoff]

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if any(path.startswith(p) for p in self.exclude_paths):
            await self.app(scope, receive, send)
            return

        # Extract client IP
        client = scope.get("client")
        key = client[0] if client else "unknown"
        now = time.monotonic()
        self._cleanup(key, now)

        if len(self._requests[key]) >= self.max_requests:
            logger.warning("Middleware rate limit exceeded for %s", key)
            from starlette.responses import JSONResponse
            response = JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Please try again later."},
                headers={"Retry-After": str(int(self.window_seconds))},
            )
            await response(scope, receive, send)
            return

        self._requests[key].append(now)
        await self.app(scope, receive, send)
