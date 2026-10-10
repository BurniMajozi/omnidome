"""Best-effort write-through to the knowledge layer for BI Studio work product.

When a deck / brand kit / research run is created, changed, published or deleted we tell tenant_memory to
refresh that one card (POST /api/v1/knowledge/admin/upsert-source) so agents can find it within seconds
instead of waiting for the periodic sweep. This must NEVER fail or slow the user's save:

  * `notify()` only schedules a background task and returns immediately; it never raises.
  * The task waits a moment so the request's transaction has committed (the memory service re-reads the row
    itself), then POSTs; one retry, then it logs and the sweep catches up.
  * Not configured (no TENANT_MEMORY_SERVICE_URL) or switched off (KNOWLEDGE_WRITE_THROUGH=false): no-op.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Optional

import httpx

logger = logging.getLogger("fno_intelligence.bi_artifact_events")

PATH = "/api/v1/knowledge/admin/upsert-source"
COMMIT_DELAY_S = float(os.getenv("KNOWLEDGE_WRITE_THROUGH_DELAY_S", "1.5"))
RETRY_DELAY_S = float(os.getenv("KNOWLEDGE_WRITE_THROUGH_RETRY_S", "6"))
TIMEOUT_S = float(os.getenv("KNOWLEDGE_WRITE_THROUGH_TIMEOUT_S", "20"))
KINDS = frozenset({"bi_deck", "bi_brand_kit", "research", "competitor", "campaign_analysis"})

_tasks: set = set()       # strong references so fire-and-forget tasks are not garbage collected mid-flight


def enabled() -> bool:
    if os.getenv("KNOWLEDGE_WRITE_THROUGH", "true").strip().lower() in {"0", "false", "no", "off"}:
        return False
    return bool(os.getenv("TENANT_MEMORY_SERVICE_URL", "").strip())


def _identity_headers(auth: Any) -> dict:
    headers = {"X-Tenant-Id": str(auth.tenant_id), "X-User-Id": str(auth.user_id)}
    if getattr(auth, "roles", None):
        headers["X-Roles"] = ",".join(sorted({str(r) for r in auth.roles}))
    return headers


async def _post(headers: dict, body: dict) -> int:
    """Seam for tests. Returns the HTTP status."""
    base = os.getenv("TENANT_MEMORY_SERVICE_URL", "").rstrip("/")
    async with httpx.AsyncClient(timeout=TIMEOUT_S) as c:
        r = await c.post(f"{base}{PATH}", json=body, headers=headers)
    return r.status_code


async def _send(headers: dict, body: dict, delay: float, retry_delay: float) -> bool:
    for attempt, wait in enumerate((delay, retry_delay)):
        await asyncio.sleep(wait)
        try:
            status = await _post(headers, body)
        except Exception as exc:  # noqa: BLE001 - the layer being down must not matter to the user
            logger.warning("knowledge write-through %s:%s failed (%s): %s", body["source_type"], body["source_id"], type(exc).__name__, exc)
            continue
        if status in (200, 201, 202):
            return True
        if status in (400, 403, 404, 429, 503) and attempt == 1:
            logger.info("knowledge write-through %s:%s not applied (HTTP %s); the sweep will catch up", body["source_type"], body["source_id"], status)
        if status in (400, 403):      # will not succeed on retry
            return False
    return False


def notify(auth: Any, source_type: str, source_id: Any, *, deleted: bool = False) -> Optional[asyncio.Task]:
    """Schedule a card refresh (or tombstone when `deleted`). Never raises; returns the task or None."""
    try:
        if source_type not in KINDS or not enabled() or auth is None:
            return None
        body = {"source_type": source_type, "source_id": str(source_id), "deleted": bool(deleted)}
        task = asyncio.get_running_loop().create_task(_send(_identity_headers(auth), body, COMMIT_DELAY_S, RETRY_DELAY_S))
        _tasks.add(task)
        task.add_done_callback(_tasks.discard)
        return task
    except Exception as exc:  # noqa: BLE001
        logger.warning("knowledge write-through not scheduled: %s", exc)
        return None


def notify_system(tenant_id: Any, user_id: Any, source_type: str, source_id: Any, *, deleted: bool = False) -> Optional[asyncio.Task]:
    """Same, for background pipelines that have no request identity: acts as the 'service' role for the row's creator."""
    from types import SimpleNamespace
    ident = SimpleNamespace(tenant_id=tenant_id, user_id=user_id or "00000000-0000-0000-0000-000000000000", roles=["service"])
    return notify(ident, source_type, source_id, deleted=deleted)
