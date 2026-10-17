"""Signed service-to-service calls from the support service (the same identity scheme as finance_bridge)."""

from __future__ import annotations

import logging
import os
import uuid
from typing import Optional

import httpx

from services.support import finance_bridge

logger = logging.getLogger("support.internal")


def orchestrator_url() -> str:
    return (os.getenv("ORCHESTRATOR_URL") or os.getenv("AGENT_ORCHESTRATOR_URL") or "http://agent-orchestrator:8021").rstrip("/")


async def post_orchestrator(tenant_id: uuid.UUID, path: str, body: dict, *, timeout: float = 30.0) -> Optional[dict]:
    """POST `body` to the orchestrator as the support service. The JSON answer, or None on any failure (logged)."""
    try:
        headers = finance_bridge.signed_headers(tenant_id, None, "POST", path)
    except Exception as exc:  # noqa: BLE001 - IdentityConfigError etc.
        logger.warning("cannot sign orchestrator call: %s", type(exc).__name__)
        return None
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(f"{orchestrator_url()}{path}", json=body, headers=headers)
    except httpx.HTTPError as exc:
        logger.warning("orchestrator call %s failed: %s", path, type(exc).__name__)
        return None
    if resp.status_code != 200:
        logger.warning("orchestrator call %s returned HTTP %s", path, resp.status_code)
        return None
    try:
        return resp.json()
    except ValueError:
        return None
