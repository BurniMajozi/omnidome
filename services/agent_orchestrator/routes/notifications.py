"""Notifications feed (header bell) — SPEC-event-bus.md.

Rows are written by any service through services.common.event_bus.notify().
A notification with no recipient is for the whole tenant.
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text

from services.common.auth import AuthContext, get_auth_context
from services.common.db import session_scope

router = APIRouter()

_VISIBLE = "tenant_id = :t AND (recipient_id IS NULL OR recipient_id = :u)"


def _row_json(r) -> dict:
    return {
        "id": str(r["id"]), "category": r["category"], "severity": r["severity"],
        "title": r["title"], "body": r["body"], "link": r["link"], "source": r["source"],
        "subject_type": r["subject_type"], "subject_id": r["subject_id"],
        "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        "read_at": r["read_at"].isoformat() if r["read_at"] else None,
    }


def _scope(ctx: AuthContext) -> dict:
    return {"t": str(ctx.tenant_id), "u": str(ctx.user_id) if ctx.user_id else None}


@router.get("")
async def list_notifications(
    unread_only: bool = False,
    limit: int = Query(30, ge=1, le=100),
    ctx: AuthContext = Depends(get_auth_context),
):
    unread = " AND read_at IS NULL" if unread_only else ""
    async with session_scope() as s:
        rows = (await s.execute(
            text(f"SELECT * FROM notifications WHERE {_VISIBLE}{unread} ORDER BY created_at DESC LIMIT :n"),
            {**_scope(ctx), "n": limit},
        )).mappings().all()
        unread_count = (await s.execute(
            text(f"SELECT count(*) FROM notifications WHERE {_VISIBLE} AND read_at IS NULL"), _scope(ctx),
        )).scalar()
    return {"data": [_row_json(r) for r in rows], "unread": unread_count}


@router.get("/unread-count")
async def unread_count(ctx: AuthContext = Depends(get_auth_context)):
    async with session_scope() as s:
        count = (await s.execute(
            text(f"SELECT count(*) FROM notifications WHERE {_VISIBLE} AND read_at IS NULL"), _scope(ctx),
        )).scalar()
    return {"count": count}


@router.post("/read-all")
async def read_all(ctx: AuthContext = Depends(get_auth_context)):
    async with session_scope() as s:
        result = await s.execute(
            text(f"UPDATE notifications SET read_at = now() WHERE {_VISIBLE} AND read_at IS NULL"), _scope(ctx),
        )
    return {"updated": result.rowcount}


@router.post("/{notification_id}/read")
async def read_one(notification_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context)):
    async with session_scope() as s:
        row = (await s.execute(
            text(f"""
                UPDATE notifications SET read_at = coalesce(read_at, now())
                 WHERE id = :id AND {_VISIBLE}
                RETURNING *
            """),
            {**_scope(ctx), "id": notification_id},
        )).mappings().first()
    if not row:
        raise HTTPException(404, "Notification not found")
    return _row_json(row)


# ── Event deliveries (operations view) ──────────────────────────────────────

events_router = APIRouter()


@events_router.get("/deliveries")
async def list_deliveries(
    status: Optional[str] = Query("dead", pattern="^(pending|processing|delivered|dead)$"),
    limit: int = Query(50, ge=1, le=200),
    ctx: AuthContext = Depends(get_auth_context),
):
    async with session_scope() as s:
        rows = (await s.execute(
            text("""
                SELECT d.id, d.consumer, d.status, d.attempts, d.next_attempt_at, d.last_error,
                       d.delivered_at, e.id AS event_id, e.event_type, e.source,
                       e.subject_type, e.subject_id, e.created_at
                  FROM event_deliveries d JOIN domain_events e ON e.id = d.event_id
                 WHERE e.tenant_id = :t AND d.status = :status
                 ORDER BY e.created_at DESC LIMIT :n
            """),
            {"t": str(ctx.tenant_id), "status": status, "n": limit},
        )).mappings().all()
    return {"data": [
        {k: (v.isoformat() if hasattr(v, "isoformat") else (str(v) if isinstance(v, uuid.UUID) else v))
         for k, v in r.items()}
        for r in rows
    ]}


@events_router.post("/deliveries/{delivery_id}/retry")
async def retry_delivery(delivery_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context)):
    async with session_scope() as s:
        row = (await s.execute(
            text("""
                UPDATE event_deliveries d
                   SET status = 'pending', attempts = 0, next_attempt_at = now(), last_error = NULL
                  FROM domain_events e
                 WHERE d.id = :id AND d.event_id = e.id AND e.tenant_id = :t AND d.status = 'dead'
                RETURNING d.id
            """),
            {"id": delivery_id, "t": str(ctx.tenant_id)},
        )).first()
    if not row:
        raise HTTPException(404, "No dead delivery with that id")
    return {"id": str(delivery_id), "status": "pending"}
