"""Honest provider-error mapping for the Zernio integration.

Rules (item 4 of the integration brief: "never fabricate success"):
  * Zernio 4xx (bad input, missing add-on, account not connected, validation) is the
    *provider rejecting the request*. The tenant gets HTTP 422 and the provider's own
    message so the UI can show something actionable.
  * Zernio 401/403-on-our-key, 5xx and transport errors are *our* problem or an outage:
    HTTP 502 with a generic message and a reference id (details stay in server logs).
  * Zernio 429 is passed on as 429 with Retry-After.
Nothing here ever includes request headers, the API key or tokens.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Any, Dict, Optional

from fastapi import HTTPException

from services.marketing.zernio_client import ZernioError, ZernioRateLimitError

logger = logging.getLogger("marketing.zernio")

_SECRETISH = re.compile(r"(?i)(bearer\s+[a-z0-9._\-]+|sk_[a-z0-9_]{8,}|eyJ[a-zA-Z0-9_\-]{20,}\.[a-zA-Z0-9_\-]+\.[a-zA-Z0-9_\-]+)")


def parse_provider_message(exc: ZernioError) -> Dict[str, Any]:
    """Best-effort {message, code, details} from a Zernio error body."""
    raw = exc.message or ""
    message, code, details = raw, None, None
    try:
        body = json.loads(raw)
        if isinstance(body, dict):
            err = body.get("error")
            if isinstance(err, dict):
                message = err.get("message") or err.get("error") or message
                code = err.get("code")
            elif isinstance(err, str):
                message = body.get("message") or err
                code = body.get("code")
            else:
                message = body.get("message") or message
                code = body.get("code")
            details = body.get("details")
            if body.get("param"):  # the offending request field, when the provider names it
                details = {**(details if isinstance(details, dict) else {}), "param": body["param"]}
    except (ValueError, TypeError):
        pass
    message = _SECRETISH.sub("[redacted]", str(message))[:500]
    return {"message": message, "code": code, "details": details if isinstance(details, (dict, list)) else None}


def provider_error(context: str, exc: BaseException) -> HTTPException:
    """Map any exception from a Zernio call to the HTTPException the tenant should see."""
    ref = uuid.uuid4().hex[:12]
    if isinstance(exc, ZernioRateLimitError):
        logger.warning("zernio rate limited [%s] %s", ref, context)
        return HTTPException(
            status_code=429,
            detail={"error": "provider_rate_limited", "message": "The provider is rate limiting requests; retry shortly.", "ref": ref},
            headers={"Retry-After": str(exc.seconds_until_reset())},
        )
    if isinstance(exc, ZernioError):
        parsed = parse_provider_message(exc)
        # 401/403 from Zernio on the *platform* key (not a tenant add-on gate) is our config problem.
        if exc.status in (401,) or exc.status >= 500:
            logger.error("zernio upstream failure [%s] %s: %s %s", ref, context, exc.status, parsed["message"])
            return HTTPException(status_code=502, detail={
                "error": "provider_unavailable",
                "message": "The provider could not complete the request. Try again, or contact support with the reference.",
                "ref": ref,
            })
        logger.info("zernio rejected [%s] %s: %s %s", ref, context, exc.status, parsed["message"])
        return HTTPException(status_code=422, detail={
            "error": "provider_rejected",
            "message": parsed["message"] or "The provider rejected the request.",
            "provider_status": exc.status,
            "provider_code": parsed["code"],
            "details": parsed["details"],
            "ref": ref,
        })
    logger.error("zernio transport error [%s] %s: %s", ref, context, type(exc).__name__)
    return HTTPException(status_code=502, detail={
        "error": "provider_unavailable",
        "message": "The provider could not be reached. Try again shortly.",
        "ref": ref,
    })


def not_configured() -> HTTPException:
    return HTTPException(status_code=503, detail={
        "error": "provider_not_configured",
        "message": "Social/ads provider is not configured on this deployment (ZERNIO_API_KEY missing).",
    })


def safe_text(value: Optional[str], limit: int = 500) -> str:
    return _SECRETISH.sub("[redacted]", value or "")[:limit]
