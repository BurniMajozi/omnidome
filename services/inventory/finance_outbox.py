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
                row.status = "failed"
                row.last_error = str(exc)[:1000]
                row.next_attempt_at = now + timedelta(seconds=min(3600, 30 * 2 ** min(row.attempts, 7)))
                failed += 1
            else:
                row.status = "sent"
                row.last_error = None
                row.next_attempt_at = None
                delivered += 1
        await db.commit()
    return {"sent": delivered, "failed": failed}
