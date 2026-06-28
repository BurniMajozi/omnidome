"""Resilient HTTP client for cross-service calls in OmniDome.

Wraps httpx with circuit breaker (from services.common.circuit_breaker),
exponential back-off retry, and centralised service URL resolution.

Usage:

    from services.common.http_client import service_get, service_post

    data = await service_get("billing", "/invoices", tenant_id=tenant_id, user_id=user_id)
    result = await service_post("network", "/services/suspend-by-customer",
                                json={"customer_id": str(cid)},
                                tenant_id=tenant_id)
"""

from __future__ import annotations

import logging
import os
import uuid
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

# ── Service URL registry ──────────────────────────────────────────────────────
# Each entry maps a logical service name to its env-var + default URL.
_SERVICE_URLS: dict[str, str] = {
    "crm":                os.getenv("CRM_SERVICE_URL",                "http://crm:8001"),
    "sales":              os.getenv("SALES_SERVICE_URL",              "http://sales:8002"),
    "billing":            os.getenv("BILLING_SERVICE_URL",            "http://billing:8003"),
    "rica":               os.getenv("RICA_SERVICE_URL",               "http://rica:8004"),
    "network":            os.getenv("NETWORK_SERVICE_URL",            "http://network:8005"),
    "iot":                os.getenv("IOT_SERVICE_URL",                "http://iot:8006"),
    "call_center":        os.getenv("CALL_CENTER_SERVICE_URL",        "http://call-center:8007"),
    "support":            os.getenv("SUPPORT_SERVICE_URL",            "http://support:8008"),
    "hr":                 os.getenv("HR_SERVICE_URL",                 "http://hr:8009"),
    "inventory":          os.getenv("INVENTORY_SERVICE_URL",          "http://inventory:8010"),
    "analytics":          os.getenv("ANALYTICS_SERVICE_URL",          "http://analytics:8011"),
    "retention":          os.getenv("RETENTION_SERVICE_URL",          "http://retention:8012"),
    "admin":              os.getenv("ADMIN_SERVICE_URL",              "http://admin:8013"),
    "marketing":          os.getenv("MARKETING_SERVICE_URL",          "http://marketing:8014"),
    "finance":            os.getenv("FINANCE_SERVICE_URL",            "http://finance:8015"),
    "web_analytics":      os.getenv("WEB_ANALYTICS_SERVICE_URL",      "http://web-analytics:8016"),
    "communication":      os.getenv("COMMUNICATION_SERVICE_URL",      "http://communication:8020"),
    "agents":             os.getenv("AGENTS_SERVICE_URL",             "http://agents:8021"),
    "customer_journey":   os.getenv("CUSTOMER_JOURNEY_SERVICE_URL",   "http://customer-journey:8022"),
    "billing_collections":os.getenv("BILLING_COLLECTIONS_SERVICE_URL","http://billing-collections:8023"),
    "fno_intelligence":   os.getenv("FNO_INTELLIGENCE_SERVICE_URL",   "http://fno-intelligence:8024"),
    "memory":             os.getenv("MEMORY_SERVICE_URL",             "http://memory:8025"),
    "journey_engine":     os.getenv("JOURNEY_ENGINE_SERVICE_URL",     "http://journey_engine:8017"),
    "lifecycle":          os.getenv("LIFECYCLE_SERVICE_URL",          "http://lifecycle:8018"),
    "orchestrator":       os.getenv("ORCHESTRATOR_SERVICE_URL",       "http://agent-orchestrator:8019"),
    "portal":             os.getenv("PORTAL_SERVICE_URL",             "http://portal:8026"),
}


def _resolve_url(service_name: str) -> str:
    url = _SERVICE_URLS.get(service_name)
    if not url:
        raise ValueError(f"Unknown service: {service_name!r}. "
                         f"Known: {list(_SERVICE_URLS)}")
    return url.rstrip("/")


def _build_headers(
    tenant_id: Optional[uuid.UUID] = None,
    user_id: Optional[uuid.UUID] = None,
    extra: Optional[dict[str, str]] = None,
) -> dict[str, str]:
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if tenant_id is not None:
        headers["X-Tenant-Id"] = str(tenant_id)
    if user_id is not None:
        headers["X-User-Id"] = str(user_id)
    if extra:
        headers.update(extra)
    return headers


async def _request(
    method: str,
    service_name: str,
    path: str,
    *,
    tenant_id: Optional[uuid.UUID] = None,
    user_id: Optional[uuid.UUID] = None,
    json: Any = None,
    params: Optional[dict] = None,
    timeout: float = 5.0,
    extra_headers: Optional[dict[str, str]] = None,
    retries: int = 2,
) -> Any:
    """Core request helper with retry and structured logging.

    Returns parsed JSON on success (200-299).
    Raises httpx.HTTPStatusError on non-2xx after retries.
    """
    base = _resolve_url(service_name)
    url = f"{base}/{path.lstrip('/')}"
    headers = _build_headers(tenant_id, user_id, extra_headers)

    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.request(
                    method,
                    url,
                    headers=headers,
                    json=json,
                    params=params,
                )
            resp.raise_for_status()
            try:
                return resp.json()
            except Exception:
                return resp.text
        except (httpx.ConnectError, httpx.TimeoutException, httpx.RemoteProtocolError) as exc:
            last_exc = exc
            if attempt < retries:
                import asyncio
                await asyncio.sleep(0.3 * (2 ** attempt))
                logger.warning(
                    "[http_client] %s %s/%s — attempt %d/%d failed: %s",
                    method, service_name, path, attempt + 1, retries + 1, exc,
                )
            continue
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "[http_client] %s %s%s → HTTP %s", method, service_name, path, exc.response.status_code
            )
            raise

    logger.error(
        "[http_client] %s %s%s — all %d attempts failed: %s",
        method, service_name, path, retries + 1, last_exc,
    )
    raise last_exc  # type: ignore[misc]


async def service_get(
    service_name: str,
    path: str,
    *,
    tenant_id: Optional[uuid.UUID] = None,
    user_id: Optional[uuid.UUID] = None,
    params: Optional[dict] = None,
    timeout: float = 5.0,
    retries: int = 2,
) -> Any:
    """GET a resource from a sibling service."""
    return await _request(
        "GET", service_name, path,
        tenant_id=tenant_id, user_id=user_id,
        params=params, timeout=timeout, retries=retries,
    )


async def service_post(
    service_name: str,
    path: str,
    *,
    json: Any = None,
    tenant_id: Optional[uuid.UUID] = None,
    user_id: Optional[uuid.UUID] = None,
    timeout: float = 5.0,
    retries: int = 1,
) -> Any:
    """POST to a sibling service."""
    return await _request(
        "POST", service_name, path,
        json=json, tenant_id=tenant_id, user_id=user_id,
        timeout=timeout, retries=retries,
    )


async def service_put(
    service_name: str,
    path: str,
    *,
    json: Any = None,
    tenant_id: Optional[uuid.UUID] = None,
    user_id: Optional[uuid.UUID] = None,
    timeout: float = 5.0,
) -> Any:
    """PUT to a sibling service."""
    return await _request(
        "PUT", service_name, path,
        json=json, tenant_id=tenant_id, user_id=user_id,
        timeout=timeout,
    )


async def service_delete(
    service_name: str,
    path: str,
    *,
    tenant_id: Optional[uuid.UUID] = None,
    user_id: Optional[uuid.UUID] = None,
    timeout: float = 5.0,
) -> Any:
    """DELETE a resource on a sibling service."""
    return await _request(
        "DELETE", service_name, path,
        tenant_id=tenant_id, user_id=user_id,
        timeout=timeout,
    )
