"""Durable inventory finance delivery. Only reads committed rows in its own session.

enqueue never performs I/O. deliver can be called after a receipt commit or by a
scheduler/retry endpoint. Finance's source/source_id uniqueness closes the crash
window between remote success and the local sent-status commit.
"""
from datetime import datetime, timedelta, timezone
import os
import uuid

from sqlalchemy import or_, select

from services.common.http_client import _request
from services.inventory.database import InventoryFinanceOutbox, _get_session_factory
from services.inventory.purchasing_helpers import journal_payload


PERMANENT_AFTER = 5


async def post_entry(tenant_id, user_id, payload):
    key = os.getenv("INTERNAL_SERVICE_KEY", "")
    if not key:
        raise RuntimeError("INTERNAL_SERVICE_KEY is required for inventory finance delivery")
    actor = user_id or uuid.UUID(os.getenv("INVENTORY_SERVICE_USER_ID", "00000000-0000-0000-0000-000000000010"))
    await _request("POST", "finance", "/journal-entries", tenant_id=tenant_id, user_id=actor,
                   extra_headers={"x-internal-key": key}, json=payload)


def enqueue(db, gr, tenant_id, accepted_value):
    if accepted_value <= 0:
        return
    payload = journal_payload(gr, accepted_value)
    db.add(InventoryFinanceOutbox(
        tenant_id=tenant_id, source=payload["source"], source_id=payload["source_id"],
        payload=payload, status="pending", attempts=0,
    ))


def enqueue_payload(db, tenant_id, payload, value):
    """Queue any journal in the caller's transaction (no I/O). Zero-value movements post nothing."""
    if value <= 0:
        return False
    db.add(InventoryFinanceOutbox(tenant_id=tenant_id, source=payload["source"], source_id=payload["source_id"],
                                  payload=payload, status="pending", attempts=0))
    return True


async def deliver_quietly(tenant_id, user_id=None):
    """After the caller's transaction commits: try to deliver, never fail the stock operation (rows stay queued for retry)."""
    try:
        await deliver(tenant_id, user_id)
    except Exception:  # noqa: BLE001
        import logging
        logging.getLogger("inventory.finance").warning("finance delivery deferred for tenant %s", tenant_id, exc_info=True)


async def retry_loop(interval_seconds: int = 60):
    """Background: keep retrying queued journals for every tenant until finance accepts them."""
    import asyncio
    import logging
    log = logging.getLogger("inventory.finance")
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            now = datetime.now(timezone.utc)
            async with _get_session_factory()() as db:
                tenants = (await db.execute(select(InventoryFinanceOutbox.tenant_id).where(
                    InventoryFinanceOutbox.status.in_(("pending", "failed")),
                    or_(InventoryFinanceOutbox.next_attempt_at.is_(None), InventoryFinanceOutbox.next_attempt_at <= now)).distinct().limit(50))).scalars().all()
            for t in tenants:
                await deliver(t)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            log.warning("finance retry loop error", exc_info=True)


async def deliver(tenant_id, user_id=None, *, force=False, limit=100, session_factory=None):
    factory = session_factory or _get_session_factory()
    delivered = failed = 0
    now = datetime.now(timezone.utc)
    async with factory() as db:
        stmt = select(InventoryFinanceOutbox).where(
            InventoryFinanceOutbox.tenant_id == tenant_id,
            InventoryFinanceOutbox.status.in_(("pending", "failed")),
        )
        if not force:
            stmt = stmt.where(or_(InventoryFinanceOutbox.next_attempt_at.is_(None),
                                  InventoryFinanceOutbox.next_attempt_at <= now))
        rows = (await db.execute(stmt.order_by(InventoryFinanceOutbox.created_at)
                                .limit(max(1, min(limit, 500))).with_for_update(skip_locked=True))).scalars().all()
        for row in rows:
            row.attempts += 1
            try:
                await post_entry(row.tenant_id, user_id, row.payload)
            except Exception as exc:
                code = getattr(getattr(exc, "response", None), "status_code", None)
                # A client error that is not a timeout/rate limit (module not enabled, tenant gone, bad payload) will not fix itself:
                # after a few tries park the row as "rejected" for a human instead of retrying it for ever.
                permanent = code is not None and 400 <= code < 500 and code not in (408, 429) and row.attempts >= PERMANENT_AFTER
                row.status = "rejected" if permanent else "failed"
                row.last_error = str(exc)[:1000]
                row.next_attempt_at = None if permanent else now + timedelta(seconds=min(3600, 30 * 2 ** min(row.attempts, 7)))
                failed += 1
            else:
                row.status = "sent"
                row.last_error = None
                row.next_attempt_at = None
                delivered += 1
        await db.commit()
    return {"sent": delivered, "failed": failed}
