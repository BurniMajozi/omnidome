"""
Resilient HTTP client with circuit breaker + retry for cross-service calls.

Usage:
    from services.common.http_client import service_call

    result = await service_call("billing", "GET", "/api/invoices", params={"customer_id": "..."})
"""

import asyncio
import logging
import time
from typing import Any, Dict, Optional

import httpx

from services.common.circuit_breaker import cb_registry, CircuitBreakerOpen

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_BACKOFF = 0.5  # seconds, doubled each retry
RETRYABLE_STATUS = {502, 503, 504}


async def service_call(
    service: str,
    method: str,
    path: str,
    *,
    base_url: Optional[str] = None,
    params: Optional[Dict[str, Any]] = None,
    json_body: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    tenant_id: Optional[str] = None,
    user_id: Optional[str] = None,
    timeout: float = 10.0,
) -> Any:
    """Make a resilient cross-service HTTP call with circuit breaker + retry.

    Returns parsed JSON response body.
    Raises httpx.HTTPStatusError on 4xx responses (client errors).
    Raises CircuitBreakerOpen if the circuit breaker is open.
    Raises httpx.HTTPStatusError(502) after all retries exhausted.
    """
    from services.common.config import settings

    SERVICE_URLS = {
        "crm": settings.crm_service_url,
        "billing": settings.billing_service_url,
        "network": settings.network_service_url,
        "retention": settings.retention_service_url,
        "support": settings.support_service_url,
        "analytics": settings.analytics_service_url,
        "sales": settings.sales_service_url,
        "finance": settings.finance_service_url,
        "call_center": settings.call_center_service_url,
        "communication": settings.communication_service_url,
    }

    url = base_url or SERVICE_URLS.get(service, "")
    if not url:
        raise ValueError(f"Unknown service: {service}")
    full_url = f"{url}{path}"

    hdrs = dict(headers or {})
    if tenant_id:
        hdrs["X-Tenant-Id"] = str(tenant_id)
    if user_id:
        hdrs["X-User-Id"] = str(user_id)

    cb = cb_registry.get(service)

    last_exc = None
    for attempt in range(MAX_RETRIES):
        try:
            async with cb:
                t0 = time.monotonic()
                async with httpx.AsyncClient(timeout=timeout) as client:
                    if method.upper() == "GET":
                        resp = await client.get(full_url, params=params, headers=hdrs)
                    elif method.upper() == "POST":
                        resp = await client.post(full_url, json=json_body, headers=hdrs)
                    elif method.upper() == "PUT":
                        resp = await client.put(full_url, json=json_body, headers=hdrs)
                    elif method.upper() == "PATCH":
                        resp = await client.patch(full_url, json=json_body, headers=hdrs)
                    else:
                        raise ValueError(f"Unsupported HTTP method: {method}")

                duration = time.monotonic() - t0
                logger.debug("service_call %s %s → %s (%.2fs)", service, path, resp.status_code, duration)

                if resp.status_code in RETRYABLE_STATUS and attempt < MAX_RETRIES - 1:
                    wait = RETRY_BACKOFF * (2 ** attempt)
                    logger.warning("service_call %s %s retryable %d, waiting %.1fs", service, path, resp.status_code, wait)
                    await asyncio.sleep(wait)
                    continue

                resp.raise_for_status()
                return resp.json()

        except CircuitBreakerOpen:
            raise
        except httpx.HTTPStatusError as exc:
            last_exc = exc
            if exc.response.status_code in RETRYABLE_STATUS and attempt < MAX_RETRIES - 1:
                wait = RETRY_BACKOFF * (2 ** attempt)
                logger.warning("service_call %s %s retryable %d, waiting %.1fs", service, path, exc.response.status_code, wait)
                await asyncio.sleep(wait)
                continue
            raise
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            last_exc = exc
            if attempt < MAX_RETRIES - 1:
                wait = RETRY_BACKOFF * (2 ** attempt)
                logger.warning("service_call %s %s error %s, retry %.1fs", service, path, type(exc).__name__, wait)
                await asyncio.sleep(wait)
                continue
            raise

    raise last_exc or httpx.HTTPStatusError("All retries exhausted", request=None, response=None)
