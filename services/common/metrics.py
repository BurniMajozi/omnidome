"""Prometheus metrics middleware for OmniDome services.

Usage in any service main.py:

    from services.common.metrics import setup_metrics
    setup_metrics(app, service_name="crm")

This adds:
    - GET /metrics — Prometheus-compatible metrics endpoint
    - Automatic request counting (by method, path, status)
    - Automatic request latency histogram
    - Active request gauge

All metrics are labeled with service_name for multi-service dashboards.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from fastapi import FastAPI, Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

# In-memory metrics storage (per-process, suitable for single-instance deployments)
# For multi-process, use prometheus-client with multiprocess mode
_request_count: dict[str, int] = {}
_request_latency: dict[str, list[float]] = {}
_active_requests: dict[str, int] = {}
_service_name: str = "unknown"


def setup_metrics(app: FastAPI, service_name: str = "unknown") -> None:
    """Attach Prometheus metrics middleware and endpoint to a FastAPI app."""
    global _service_name
    _service_name = service_name

    @app.middleware("http")
    async def metrics_middleware(request: Request, call_next):
        if request.url.path == "/metrics":
            return await call_next(request)

        key = f"{request.method}:{request.url.path}"
        _active_requests[key] = _active_requests.get(key, 0) + 1
        start = time.perf_counter()

        try:
            response = await call_next(request)
            return response
        finally:
            latency = time.perf_counter() - start
            _active_requests[key] = max(0, _active_requests.get(key, 1) - 1)
            _request_count[key] = _request_count.get(key, 0) + 1
            if key not in _request_latency:
                _request_latency[key] = []
            _request_latency[key].append(latency)
            # Keep only last 1000 latency samples per endpoint
            if len(_request_latency[key]) > 1000:
                _request_latency[key] = _request_latency[key][-1000:]

    @app.get("/metrics", include_in_schema=False)
    async def metrics_endpoint():
        lines = []
        svc = _service_name

        # Request count
        lines.append(f"# HELP omnidome_requests_total Total HTTP requests")
        lines.append(f"# TYPE omnidome_requests_total counter")
        for key, count in sorted(_request_count.items()):
            method, path = key.split(":", 1)
            lines.append(f'omnidome_requests_total{{service="{svc}",method="{method}",path="{path}"}} {count}')

        # Active requests
        lines.append(f"# HELP omnidome_active_requests Currently active HTTP requests")
        lines.append(f"# TYPE omnidome_active_requests gauge")
        for key, count in sorted(_active_requests.items()):
            method, path = key.split(":", 1)
            lines.append(f'omnidome_active_requests{{service="{svc}",method="{method}",path="{path}"}} {count}')

        # Latency histogram (p50, p95, p99)
        lines.append(f"# HELP omnidome_request_latency_seconds Request latency")
        lines.append(f"# TYPE omnidome_request_latency_seconds summary")
        for key, latencies in sorted(_request_latency.items()):
            if not latencies:
                continue
            method, path = key.split(":", 1)
            sorted_lat = sorted(latencies)
            n = len(sorted_lat)
            p50 = sorted_lat[int(n * 0.5)]
            p95 = sorted_lat[int(n * 0.95)]
            p99 = sorted_lat[int(n * 0.99)]
            total = sum(sorted_lat)
            lines.append(f'omnidome_request_latency_seconds{{service="{svc}",method="{method}",path="{path}",quantile="0.5"}} {p50:.4f}')
            lines.append(f'omnidome_request_latency_seconds{{service="{svc}",method="{method}",path="{path}",quantile="0.95"}} {p95:.4f}')
            lines.append(f'omnidome_request_latency_seconds{{service="{svc}",method="{method}",path="{path}",quantile="0.99"}} {p99:.4f}')
            lines.append(f'omnidome_request_latency_seconds_sum{{service="{svc}",method="{method}",path="{path}"}} {total:.4f}')
            lines.append(f'omnidome_request_latency_seconds_count{{service="{svc}",method="{method}",path="{path}"}} {n}')

        return Response(
            content="\n".join(lines) + "\n",
            media_type="text/plain; version=0.0.4",
        )

    logger.info("Prometheus metrics enabled for %s at /metrics", svc)
