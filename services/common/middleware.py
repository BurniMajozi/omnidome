"""OmniDome shared production middleware — CORS, error handling, logging, graceful shutdown."""

import asyncio
import logging
import os
import signal
import time
import traceback
from contextlib import asynccontextmanager
from typing import Callable

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("omnidome.middleware")


def get_cors_origins() -> list[str]:
    """Parse CORS origins from environment."""
    default_origins = ["http://localhost:3000", "http://localhost:3001"]
    extra = os.getenv("CORS_ORIGINS", "")
    if extra:
        default_origins.extend([o.strip() for o in extra.split(",") if o.strip()])
    return default_origins


def add_cors_middleware(app: FastAPI) -> None:
    """Add CORS middleware with environment-configured origins."""
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_cors_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log all requests with timing."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start = time.monotonic()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception("Unhandled exception in %s %s", request.method, request.url.path)
            raise
        duration = (time.monotonic() - start) * 1000
        logger.info(
            "%s %s %d %.1fms",
            request.method,
            request.url.path,
            response.status_code,
            duration,
        )
        return response


def add_request_logging(app: FastAPI) -> None:
    """Add request logging middleware."""
    app.add_middleware(RequestLoggingMiddleware)


def add_exception_handlers(app: FastAPI) -> None:
    """Add global exception handlers for consistent error responses."""

    @app.exception_handler(404)
    async def not_found_handler(request: Request, exc):
        return Response(
            content='{"detail": "Not found"}',
            status_code=404,
            media_type="application/json",
        )

    @app.exception_handler(500)
    async def internal_error_handler(request: Request, exc):
        logger.error("Internal server error: %s %s\n%s", request.method, request.url.path, traceback.format_exc())
        return Response(
            content='{"detail": "Internal server error"}',
            status_code=500,
            media_type="application/json",
        )


def configure_production(app: FastAPI) -> None:
    """Apply all production middleware: CORS, logging, error handling."""
    add_cors_middleware(app)
    add_request_logging(app)
    add_exception_handlers(app)
