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

import logging
import time
from collections import defaultdict
from typing import Optional

from fastapi import HTTPException, Request, status

logger = logging.getLogger(__name__)


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
    ):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._key_func = key_func or (lambda r: r.client.host if r.client else "unknown")
        self._requests: dict[str, list[float]] = defaultdict(list)

    def _cleanup(self, key: str, now: float) -> None:
        """Remove timestamps outside the current window."""
        cutoff = now - self.window_seconds
        self._requests[key] = [t for t in self._requests[key] if t > cutoff]

    async def check(self, request: Request) -> None:
        """FastAPI dependency that raises HTTP 429 if rate limit exceeded."""
        key = self._key_func(request)  # type: ignore[operator]
        now = time.monotonic()
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
