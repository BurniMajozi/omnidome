import asyncio
import logging
import os
import time
from collections import deque
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from starlette.responses import Response

from services.common.auth import AuthContext, get_auth_context
from services.common.db import get_async_engine

logger = logging.getLogger("gateway")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())


SERVICE_ROUTES = {
    "/api/crm": ("crm", os.getenv("CRM_SERVICE_URL", "http://crm:8001")),
    "/api/sales": ("sales", os.getenv("SALES_SERVICE_URL", "http://sales:8002")),
    "/api/billing": ("billing", os.getenv("BILLING_SERVICE_URL", "http://billing:8003")),
    "/api/finance": ("finance", os.getenv("FINANCE_SERVICE_URL", "http://finance:8015")),
    "/api/rica": ("rica", os.getenv("RICA_SERVICE_URL", "http://rica:8004")),
    "/api/network": ("network", os.getenv("NETWORK_SERVICE_URL", "http://network:8005")),
    "/api/iot": ("iot", os.getenv("IOT_SERVICE_URL", "http://iot:8006")),
    "/api/call-center": ("call_center", os.getenv("CALL_CENTER_SERVICE_URL", "http://call_center:8007")),
    "/api/support": ("support", os.getenv("SUPPORT_SERVICE_URL", "http://support:8008")),
    "/api/hr": ("hr", os.getenv("HR_SERVICE_URL", "http://hr:8009")),
    "/api/inventory": ("inventory", os.getenv("INVENTORY_SERVICE_URL", "http://inventory:8010")),
    "/api/analytics": ("analytics", os.getenv("ANALYTICS_SERVICE_URL", "http://analytics:8011")),
    "/api/retention": ("retention", os.getenv("RETENTION_SERVICE_URL", "http://retention:8012")),
    "/api/admin": ("admin", os.getenv("ADMIN_SERVICE_URL", "http://admin:8013")),
    "/api/voice": ("voice", os.getenv("TWILIO_VOICE_FUNCTIONS_URL", "")),
    "/api/sms": ("sms", os.getenv("TWILIO_SMS_FUNCTIONS_URL", "")),
}


class RateLimiter:
    def __init__(self) -> None:
        self.window_seconds = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))
        self.default_limit = int(os.getenv("RATE_LIMIT_DEFAULT", "120"))
        self.module_limits = {
            module: int(os.getenv(f"RATE_LIMIT_{module.upper()}", self.default_limit))
            for module, _ in SERVICE_ROUTES.values()
        }
        self._requests: dict[tuple[str, str], deque[float]] = {}
        self._lock = asyncio.Lock()

    async def allow(self, tenant_id: Optional[str], module: str) -> bool:
        key = (tenant_id or "anonymous", module)
        limit = self.module_limits.get(module, self.default_limit)
        now = time.monotonic()
        async with self._lock:
            bucket = self._requests.setdefault(key, deque())
            while bucket and now - bucket[0] > self.window_seconds:
                bucket.popleft()
            if len(bucket) >= limit:
                return False
            bucket.append(now)
        return True


rate_limiter = RateLimiter()


app = FastAPI(title="OmniDome Gateway", version="1.0.0")

cors_origins = ["http://localhost:3000"]
extra_origins = os.getenv("CORS_ORIGINS")
if extra_origins:
    cors_origins.extend([origin.strip() for origin in extra_origins.split(",") if origin.strip()])

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_logger(request: Request, call_next):
    start = time.perf_counter()
    ctx: Optional[AuthContext] = None
    try:
        ctx = await get_auth_context(request)
    except HTTPException:
        ctx = None
    response = await call_next(request)
    latency_ms = (time.perf_counter() - start) * 1000
    logger.info(
        "method=%s path=%s tenant_id=%s user_id=%s status=%s latency_ms=%.2f",
        request.method,
        request.url.path,
        getattr(ctx, "tenant_id", None),
        getattr(ctx, "user_id", None),
        response.status_code,
        latency_ms,
    )
    return response


def _resolve_route(path: str) -> Optional[tuple[str, str, str]]:
    for prefix, (module, base_url) in SERVICE_ROUTES.items():
        if path.startswith(prefix):
            suffix = path[len(prefix):] or "/"
            if not suffix.startswith("/"):
                suffix = "/" + suffix
            return module, base_url.rstrip("/"), suffix
    return None


def _filtered_headers(request: Request) -> dict:
    headers = dict(request.headers)
    headers.pop("host", None)
    headers.pop("content-length", None)
    forwarded_for = headers.get("x-forwarded-for")
    client_host = request.client.host if request.client else ""
    headers["x-forwarded-for"] = f"{forwarded_for}, {client_host}" if forwarded_for else client_host
    headers["x-forwarded-host"] = request.headers.get("host", "")
    headers["x-forwarded-proto"] = request.url.scheme
    return headers


@app.get("/health")
async def health():
    results = {}
    async with httpx.AsyncClient(timeout=3.0) as client:
        tasks = []
        for prefix, (_, base_url) in SERVICE_ROUTES.items():
            tasks.append((prefix, client.get(f"{base_url.rstrip('/')}/health")))
        responses = await asyncio.gather(*(task for _, task in tasks), return_exceptions=True)
        for (prefix, _), resp in zip(tasks, responses):
            if isinstance(resp, Exception):
                results[prefix] = {"status": "down", "error": str(resp)}
            else:
                results[prefix] = {"status": "up" if resp.status_code == 200 else "degraded"}
    overall = "ok" if all(item["status"] == "up" for item in results.values()) else "degraded"
    return {"status": overall, "services": results}


@app.get("/api/supabase/health")
async def supabase_health():
    engine = get_async_engine()
    try:
        async with engine.connect() as conn:
            await conn.execute(text("select 1"))
        return {"status": "ok"}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Supabase unavailable: {exc}") from exc


@app.api_route("/{full_path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy(full_path: str, request: Request):
    route = _resolve_route("/" + full_path if not full_path.startswith("/") else full_path)
    if not route:
        raise HTTPException(status_code=404, detail="Unknown route")

    module, base_url, suffix = route
    if not base_url:
        raise HTTPException(
            status_code=503,
            detail=f"Upstream for {module} not configured",
        )
    ctx: Optional[AuthContext] = None
    try:
        ctx = await get_auth_context(request)
    except HTTPException:
        ctx = None

    if request.method.upper() != "OPTIONS":
        tenant_id = getattr(ctx, "tenant_id", None)
        allowed = await rate_limiter.allow(str(tenant_id) if tenant_id else None, module)
        if not allowed:
            raise HTTPException(status_code=429, detail="Rate limit exceeded")

    url = f"{base_url}{suffix}"
    headers = _filtered_headers(request)
    body = await request.body()

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.request(
                request.method,
                url,
                params=request.query_params,
                content=body,
                headers=headers,
            )
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"Upstream unavailable: {exc}") from exc

    response_headers = {
        key: value
        for key, value in resp.headers.items()
        if key.lower() not in {"content-length", "transfer-encoding", "connection"}
    }
    return Response(content=resp.content, status_code=resp.status_code, headers=response_headers)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
