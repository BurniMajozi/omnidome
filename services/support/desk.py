"""Ticket desk API: list/search, create, detail with timeline, comments, assignment, status, routing rules.

Replaces the thin ticket CRUD that used to live in main.py. Every route is tenant-scoped, role-gated
(support/access.py tiers) and writes a timeline entry (`ticket_replies.kind`) for each change so the
desk can show who did what. Tickets raised by the event bus arrive through consumer.py/ticketing.py
and show up here like any other ticket (`source` says where they came from).
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, desc, func, or_, select, text

from services.common import ticket_events as E
from services.common.auth import AuthContext, get_auth_context, get_current_tenant_id
from services.common.event_bus import publish
from services.common.redaction import redact_text
from services.support import custom_rules, finance_bridge, jev_ticket, kpi, lifecycle, notify, streams, ticket_rules, ticketing
from services.support.access import has_tier, require, require_job_access, require_tier
from services.support.database import Ticket, TicketReply, get_session

logger = logging.getLogger("support.desk")
router = APIRouter()

CRM_URL = os.getenv("CRM_SERVICE_URL", "http://crm:8001")

TICKET_STATUSES = {"OPEN", "IN_PROGRESS", "ESCALATED", "ON_HOLD", "PENDING", "RESOLVED", "CLOSED"}
PRIORITIES = set(ticket_rules.PRIORITIES)
MANUAL_SOURCES = {"manual", "email", "call_center", "api"}


# ── helpers ─────────────────────────────────────────────────────────────────

def _iso(v: Optional[datetime]) -> Optional[str]:
    return v.isoformat() if v else None


def _aware(v: Optional[datetime]) -> Optional[datetime]:
    return None if v is None else (v if v.tzinfo else v.replace(tzinfo=timezone.utc))


def sla_state(t: Ticket, now: Optional[datetime] = None) -> Optional[str]:
    """none | ok | due_soon | breached | met | missed for the ticket's resolution SLA."""
    due = _aware(t.sla_due_at)
    if due is None:
        return None
    now = now or datetime.now(timezone.utc)
    if t.status in ticketing.CLOSED_STATUSES:
        done = _aware(t.resolved_at) or _aware(t.updated_at) or now
        return "met" if done <= due else "missed"
    if now > due:
        return "breached"
    return "due_soon" if due - now <= timedelta(hours=2) else "ok"


def ticket_to_dict(t: Ticket) -> dict:
    return {
        "id": str(t.id),
        "ticket_no": t.ticket_no,
        "ticket_ref": f"T-{t.ticket_no}" if t.ticket_no else None,
        "tenant_id": str(t.tenant_id),
        "customer_id": str(t.customer_id) if t.customer_id else None,
        "subject": t.subject,
        "description": t.description,
        "priority": t.priority,
        "status": t.status,
        "category": t.category,
        "assigned_to": str(t.assigned_to) if t.assigned_to else None,
        "external_fno_ref": t.external_fno_ref,
        "is_fcr": bool(t.is_fcr),
        "resolution_notes": t.resolution_notes,
        "resolved_at": _iso(t.resolved_at),
        "created_at": _iso(t.created_at),
        "updated_at": _iso(t.updated_at),
        "source": t.source or "manual",
        "source_ref_type": t.source_ref_type,
        "source_ref_id": t.source_ref_id,
        "source_link": t.source_link,
        "event_type": t.event_type,
        "queue": t.queue,
        "occurrence_count": t.occurrence_count or 1,
        "last_occurrence_at": _iso(t.last_occurrence_at),
        "sla_due_at": _iso(t.sla_due_at),
        "sla_state": sla_state(t),
        "first_response_at": _iso(t.first_response_at),
        "context": t.context or {},
        # time dimension
        "first_assigned_at": _iso(t.first_assigned_at),
        "last_activity_at": _iso(t.last_activity_at),
        "escalated_at": _iso(t.escalated_at),
        "assignment_count": t.assignment_count or 0,
        "modification_count": t.modification_count or 0,
        "transfer_count": t.transfer_count or 0,
        "reopen_count": t.reopen_count or 0,
        "reply_channel": t.reply_channel,
        "overdue": kpi.is_overdue(t.status, _aware(t.sla_due_at)),
        "stale": kpi.is_stale(t.status, t.priority, _aware(t.last_activity_at) or _aware(t.updated_at) or _aware(t.created_at)),
        "hours_to_first_response": kpi.hours_between(t.created_at, t.first_response_at),
        "hours_to_resolve": kpi.hours_between(t.created_at, t.resolved_at),
    }


def reply_to_dict(r: TicketReply) -> dict:
    return {"id": str(r.id), "kind": r.kind or "comment", "author_type": r.author_type,
            "author_id": str(r.author_id) if r.author_id else None, "message": r.message,
            "is_private": bool(r.is_private), "created_at": _iso(r.created_at), "data": r.data or {}}


async def _get_ticket(db, tenant_id: uuid.UUID, ticket_id: uuid.UUID, *, lock: bool = False) -> Ticket:
    stmt = select(Ticket).where(Ticket.id == ticket_id, Ticket.tenant_id == tenant_id)
    if lock:
        stmt = stmt.with_for_update()
    ticket = (await db.execute(stmt)).scalar_one_or_none()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return ticket


async def emit(db, tenant_id: uuid.UUID, event_type: str, ticket: Ticket, extra: Optional[dict] = None) -> None:
    """Publish a ticket lifecycle event for automations; never fails the request."""
    try:
        async with db.begin_nested():
            await publish(db, tenant_id, event_type,
                          {"ticket_id": str(ticket.id), "ticket_ref": f"T-{ticket.ticket_no}" if ticket.ticket_no else None,
                           "status": ticket.status, "priority": ticket.priority, "category": ticket.category,
                           "source": ticket.source or "manual", "queue": ticket.queue, **(extra or {})},
                          source="support", subject=("ticket", ticket.id))
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not publish %s: %s", event_type, type(exc).__name__)


async def _enrich_customer(td: dict, tenant_id: uuid.UUID, user_id: Optional[uuid.UUID]) -> dict:
    cid = td.get("customer_id")
    if not cid:
        return td
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            resp = await client.get(f"{CRM_URL}/customers/{cid}",
                                    headers=finance_bridge.signed_headers(tenant_id, user_id, "GET", f"/customers/{cid}"))
        if resp.status_code == 200:
            c = resp.json()
            td["customer_name"] = f"{c.get('first_name', '')} {c.get('last_name', '')}".strip()
            td["customer_phone"] = c.get("phone", "")
            td["customer_address"] = c.get("physical_address", "")
    except Exception:  # noqa: BLE001 - tickets work without customer enrichment
        pass
    return td


async def _verify_customer(tenant_id: uuid.UUID, user_id: Optional[uuid.UUID], customer_id: uuid.UUID) -> None:
    """The customer must exist in the caller's tenant (CRM is tenant-scoped). 422 if unknown,
    503 if it cannot be checked. SUPPORT_VERIFY_CUSTOMER=false disables (local development only)."""
    if os.getenv("SUPPORT_VERIFY_CUSTOMER", "true").strip().lower() in {"0", "false", "no", "off"}:
        return
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{CRM_URL}/customers/{customer_id}",
                                    headers=finance_bridge.signed_headers(tenant_id, user_id, "GET", f"/customers/{customer_id}"))
    except Exception:  # noqa: BLE001
        raise HTTPException(status_code=503, detail="Could not verify the customer; try again")
    if resp.status_code == 404:
        raise HTTPException(status_code=422, detail="Unknown customer for this tenant")
    if resp.status_code != 200:
        raise HTTPException(status_code=503, detail="Could not verify the customer; try again")


async def _verify_assignee(db, tenant_id: uuid.UUID, user_id: uuid.UUID) -> None:
    """An assignee must be an active member of this tenant."""
    ok = (await db.execute(text("SELECT 1 FROM users WHERE id = :u AND tenant_id = :t AND COALESCE(is_active, true)"),
                           {"u": str(user_id), "t": str(tenant_id)})).first()
    if ok is None:
        raise HTTPException(status_code=422, detail="Assignee is not an active member of this tenant")


async def change_status(db, ticket: Ticket, new_status: str, auth: AuthContext, note: str = "") -> bool:
    """Apply a status transition with timeline + lifecycle event. Returns True when something changed."""
    new_status = new_status.upper()
    old = ticket.status
    if new_status == old:
        return False
    now = datetime.now(timezone.utc)
    reopening = old in ticketing.CLOSED_STATUSES and new_status not in ticketing.CLOSED_STATUSES
    closing = new_status in ticketing.CLOSED_STATUSES and old not in ticketing.CLOSED_STATUSES
    if reopening and ticket.dedupe_key:
        clash = (await db.execute(select(Ticket.id).where(
            Ticket.tenant_id == ticket.tenant_id, Ticket.dedupe_key == ticket.dedupe_key,
            Ticket.id != ticket.id, Ticket.status.notin_(ticketing.CLOSED_STATUSES)))).first()
        if clash:
            raise HTTPException(status_code=409, detail="A newer open ticket already tracks this same problem")
    ticket.status = new_status
    if closing:
        # RESOLVED then CLOSED is one resolution: keep the first resolved_at so time-to-resolve is not stretched.
        ticket.resolved_at = ticket.resolved_at or now
        if note:
            ticket.resolution_notes = redact_text(note, 2000)
    elif reopening:
        ticket.resolved_at = None
    await db.flush()
    verb = "Closed" if new_status == "CLOSED" else "Resolved" if new_status == "RESOLVED" else "Reopened" if reopening \
        else f"Status changed to {new_status.replace('_', ' ').title()}"
    await ticketing.add_timeline(db, ticket.id, "status",
                                 f"{verb}" + (f": {redact_text(note, 400)}" if note else "") + f" (was {old.replace('_', ' ').lower()}).",
                                 author_type="agent", author_id=auth.user_id, data={"from": old, "to": new_status})
    event_type = lifecycle.status_event_type(old, new_status)
    await lifecycle.record(db, ticket, event_type, actor_id=auth.user_id, from_value=old, to_value=new_status,
                           note=note or None, visibility="public" if closing and note else "internal")
    if closing and not ticket.is_fcr:
        ticket.is_fcr = lifecycle.first_touch_resolution(ticket.assignment_count, ticket.transfer_count, ticket.reopen_count)
    if closing:
        await emit(db, ticket.tenant_id, E.EVENT_TICKET_CLOSED, ticket)
        await notify.notify_requester(db, ticket, "resolved", detail=note, actor_id=auth.user_id)
        if ticket.resolution_notes:
            jev_ticket.schedule_review(ticket.tenant_id, ticket.id)
    elif reopening:
        await emit(db, ticket.tenant_id, E.EVENT_TICKET_REOPENED, ticket)
    elif new_status == "ESCALATED":
        await emit(db, ticket.tenant_id, E.EVENT_TICKET_ESCALATED, ticket)
    return True


# ── request models ──────────────────────────────────────────────────────────

class TicketCreate(BaseModel):
    customer_id: Optional[uuid.UUID] = None
    subject: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=5000)
    category: str = "GENERAL"
    priority: str = "NORMAL"
    source: str = "manual"
    queue: Optional[str] = None
    assigned_to: Optional[uuid.UUID] = None
    source_ref_type: Optional[str] = Field(default=None, max_length=60)
    source_ref_id: Optional[str] = Field(default=None, max_length=120)
    # Where the requester can be reached: the channel the request came in on and its address/thread id.
    reply_channel: Optional[str] = Field(default=None, max_length=30)
    reply_ref: Optional[str] = Field(default=None, max_length=200)


class TicketUpdate(BaseModel):
    status: Optional[str] = None
    priority: Optional[str] = None
    category: Optional[str] = None
    queue: Optional[str] = None
    note: str = Field(default="", max_length=2000)


# Back-compat name used by older callers/tests.
TicketStatusUpdate = TicketUpdate


class CommentCreate(BaseModel):
    message: str = Field(min_length=1, max_length=5000)
    is_private: bool = False


class AssignRequest(BaseModel):
    assigned_to: Optional[uuid.UUID] = None   # null = unassign
    queue: Optional[str] = None


class RuleOverride(BaseModel):
    enabled: Optional[bool] = None
    category: Optional[str] = None
    priority: Optional[str] = None
    queue: Optional[str] = None
    assigned_to: Optional[uuid.UUID] = None
    outcome: Optional[str] = None
    reset: bool = False


def _norm_choice(value: Optional[str], allowed, label: str) -> Optional[str]:
    if value is None or value == "":
        return None
    v = value.strip().upper() if allowed is not ticket_rules.QUEUES else value.strip().lower()
    if v not in allowed:
        raise HTTPException(status_code=422, detail=f"{label} must be one of {sorted(allowed)}")
    return v


# ── list / search / summary ─────────────────────────────────────────────────

def _filters(tenant_id: uuid.UUID, auth_user: Optional[uuid.UUID], *, status_: Optional[str], priority: Optional[str],
             category: Optional[str], source: Optional[str], queue: Optional[str], assigned: Optional[str],
             customer_id: Optional[uuid.UUID], q: Optional[str], sla: Optional[str], open_only: bool):
    conds = [Ticket.tenant_id == tenant_id]
    if status_:
        wanted = [s.strip().upper() for s in status_.split(",") if s.strip()]
        conds.append(Ticket.status.in_(wanted))
    if open_only:
        conds.append(Ticket.status.notin_(ticketing.CLOSED_STATUSES))
    if priority:
        conds.append(Ticket.priority == priority.upper())
    if category:
        conds.append(Ticket.category == category.upper())
    if source:
        conds.append(func.coalesce(Ticket.source, "manual") == source.lower())
    if queue:
        conds.append(Ticket.queue == queue.lower())
    if customer_id:
        conds.append(Ticket.customer_id == customer_id)
    if assigned == "unassigned":
        conds.append(Ticket.assigned_to.is_(None))
    elif assigned == "me" and auth_user:
        conds.append(Ticket.assigned_to == auth_user)
    elif assigned:
        try:
            conds.append(Ticket.assigned_to == uuid.UUID(assigned))
        except ValueError:
            raise HTTPException(status_code=422, detail="assigned must be me, unassigned or a user id")
    if sla == "breached":
        conds += [Ticket.status.notin_(ticketing.CLOSED_STATUSES), Ticket.sla_due_at < func.now()]
    if q:
        like = f"%{q.strip()[:100]}%"
        clauses = [Ticket.subject.ilike(like), Ticket.description.ilike(like)]
        digits = q.strip().lstrip("#").upper().removeprefix("T-")
        if digits.isdigit():
            clauses.append(Ticket.ticket_no == int(digits))
        conds.append(or_(*clauses))
    return and_(*conds)


@router.get("/tickets/meta")
async def ticket_meta(auth: AuthContext = Depends(get_auth_context)):
    return {"statuses": sorted(TICKET_STATUSES), "priorities": list(ticket_rules.PRIORITIES),
            "categories": list(ticket_rules.CATEGORIES), "queues": list(ticket_rules.QUEUES),
            "sources": list(ticket_rules.SOURCES), "sla_hours": ticketing.SLA_HOURS,
            "user_id": str(auth.user_id)}


@router.get("/tickets/summary")
async def ticket_summary(auth: AuthContext = Depends(get_auth_context), db=Depends(get_session)):
    """Counts for the desk header and view chips, aggregated in SQL (polled every 30 s per open desk)."""
    p = {"t": str(auth.tenant_id), "me": str(auth.user_id)}
    totals = (await db.execute(text("""
        SELECT count(*) AS total,
               count(*) FILTER (WHERE status NOT IN ('CLOSED','RESOLVED')) AS open,
               count(*) FILTER (WHERE status IN ('CLOSED','RESOLVED')) AS closed,
               count(*) FILTER (WHERE status NOT IN ('CLOSED','RESOLVED') AND assigned_to IS NULL) AS unassigned,
               count(*) FILTER (WHERE status NOT IN ('CLOSED','RESOLVED') AND assigned_to = CAST(:me AS uuid)) AS mine,
               count(*) FILTER (WHERE status NOT IN ('CLOSED','RESOLVED') AND sla_due_at IS NOT NULL AND sla_due_at < now()) AS breached,
               avg(extract(epoch FROM (resolved_at - created_at)) / 3600.0)
                   FILTER (WHERE resolved_at IS NOT NULL AND resolved_at >= created_at) AS avg_hours,
               avg(extract(epoch FROM (first_response_at - created_at)) / 3600.0)
                   FILTER (WHERE first_response_at IS NOT NULL AND first_response_at >= created_at) AS avg_response_hours,
               count(*) FILTER (WHERE """ + kpi.STALE_SQL + """) AS stale
          FROM tickets WHERE tenant_id = CAST(:t AS uuid)"""), p)).mappings().one()

    async def grouped(column: str, only_open: bool) -> dict:
        rows = (await db.execute(text(
            f"SELECT COALESCE({column}, 'manual') AS k, count(*) AS n FROM tickets WHERE tenant_id = CAST(:t AS uuid)"
            + (" AND status NOT IN ('CLOSED','RESOLVED')" if only_open else "") + " GROUP BY 1 ORDER BY 1"), p)).all()
        return {k: n for k, n in rows}

    avg = totals["avg_hours"]
    return {
        "total": totals["total"], "open": totals["open"], "closed": totals["closed"], "unassigned": totals["unassigned"],
        "mine": totals["mine"], "breached": totals["breached"],
        "by_status": await grouped("status", False), "open_by_priority": await grouped("priority", True),
        "open_by_source": await grouped("source", True),
        "avg_resolution_hours": round(float(avg), 1) if avg is not None else None,
        "avg_response_hours": round(float(totals["avg_response_hours"]), 1) if totals["avg_response_hours"] is not None else None,
        "stale": totals["stale"],
    }


@router.get("/tickets/search")
async def search_tickets(
    status: Optional[str] = None, priority: Optional[str] = None, category: Optional[str] = None,
    source: Optional[str] = None, queue: Optional[str] = None, assigned: Optional[str] = None,
    customer_id: Optional[uuid.UUID] = None, q: Optional[str] = None, sla: Optional[str] = None,
    open_only: bool = False, sort: str = Query("newest", pattern="^(newest|oldest|priority|sla|updated)$"),
    limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
    auth: AuthContext = Depends(get_auth_context), db=Depends(get_session),
):
    where = _filters(auth.tenant_id, auth.user_id, status_=status, priority=priority, category=category, source=source,
                     queue=queue, assigned=assigned, customer_id=customer_id, q=q, sla=sla, open_only=open_only)
    prio_rank = func.array_position(text("ARRAY['URGENT','HIGH','NORMAL','LOW']::text[]"), Ticket.priority)
    order = {"newest": [desc(Ticket.created_at)], "oldest": [Ticket.created_at],
             "updated": [desc(func.coalesce(Ticket.updated_at, Ticket.created_at))],
             "priority": [prio_rank, desc(Ticket.created_at)],
             "sla": [Ticket.sla_due_at.asc().nulls_last(), desc(Ticket.created_at)]}[sort]
    total = (await db.execute(select(func.count(Ticket.id)).where(where))).scalar() or 0
    rows = (await db.execute(select(Ticket).where(where).order_by(*order).limit(limit).offset(offset))).scalars().all()
    return {"items": [ticket_to_dict(t) for t in rows], "total": total, "limit": limit, "offset": offset}


@router.get("/tickets/assignees")
async def ticket_assignees(auth: AuthContext = Depends(require_tier("technician")), db=Depends(get_session)):
    """Active members of this tenant who can be assigned a ticket (id and display name only)."""
    rows = (await db.execute(text(
        """SELECT id, COALESCE(NULLIF(full_name, ''), split_part(email, '@', 1)) AS name FROM users
            WHERE tenant_id = :t AND COALESCE(is_active, true) ORDER BY 2 LIMIT 200"""), {"t": str(auth.tenant_id)})).mappings().all()
    return [{"id": str(r["id"]), "name": r["name"]} for r in rows]


@router.get("/tickets/kpis")
async def ticket_kpis(days: int = Query(30, ge=1, le=kpi.MAX_DAYS), assignee: Optional[uuid.UUID] = None,
                      auth: AuthContext = Depends(get_auth_context), db=Depends(get_session)):
    """Time to respond / assign / resolve, first-touch resolution, SLA and time in stage for tickets opened in the window."""
    return await kpi.compute(db, auth.tenant_id, days, assignee)


@router.get("/tickets/late")
async def late_tickets(limit: int = Query(25, ge=1, le=200), auth: AuthContext = Depends(get_auth_context),
                       db=Depends(get_session)):
    """Open tickets that are past their deadline or have had no activity for too long, worst first."""
    return {"items": await kpi.late_tickets(db, auth.tenant_id, limit)}


class SettingsUpdate(BaseModel):
    notify_enabled: Optional[bool] = None
    notify_on_assigned: Optional[bool] = None
    notify_on_modified: Optional[bool] = None
    notify_on_note: Optional[bool] = None
    notify_on_resolved: Optional[bool] = None
    jev_routing_mode: Optional[str] = None
    jev_review_on_close: Optional[bool] = None


@router.get("/tickets/settings")
async def get_ticket_settings(auth: AuthContext = Depends(get_auth_context), db=Depends(get_session)):
    return {**await notify.load_settings(db, auth.tenant_id), "jev_modes": list(notify.JEV_MODES),
            "deliverable_channels": sorted(notify.DELIVERABLE_CHANNELS), "can_edit": await has_tier(auth, db, "manager")}


@router.put("/tickets/settings")
async def put_ticket_settings(payload: SettingsUpdate, auth: AuthContext = Depends(require_tier("manager")),
                              db=Depends(get_session)):
    """Who is told what about a ticket, and how far Jev may route on its own."""
    changes = payload.model_dump(exclude_none=True)
    if "jev_routing_mode" in changes and changes["jev_routing_mode"] not in notify.JEV_MODES:
        raise HTTPException(status_code=422, detail=f"jev_routing_mode must be one of {list(notify.JEV_MODES)}")
    merged = {**await notify.load_settings(db, auth.tenant_id), **changes}
    await db.execute(text("""
        INSERT INTO ticket_settings (tenant_id, notify_enabled, notify_on_assigned, notify_on_modified, notify_on_note,
                                     notify_on_resolved, jev_routing_mode, jev_review_on_close, updated_by, updated_at)
        VALUES (:t, :notify_enabled, :notify_on_assigned, :notify_on_modified, :notify_on_note, :notify_on_resolved,
                :jev_routing_mode, :jev_review_on_close, :by, now())
        ON CONFLICT (tenant_id) DO UPDATE SET notify_enabled = EXCLUDED.notify_enabled,
            notify_on_assigned = EXCLUDED.notify_on_assigned, notify_on_modified = EXCLUDED.notify_on_modified,
            notify_on_note = EXCLUDED.notify_on_note, notify_on_resolved = EXCLUDED.notify_on_resolved,
            jev_routing_mode = EXCLUDED.jev_routing_mode, jev_review_on_close = EXCLUDED.jev_review_on_close,
            updated_by = EXCLUDED.updated_by, updated_at = now()"""),
        {"t": str(auth.tenant_id), "by": auth.user_id, **{k: merged[k] for k in notify.DEFAULT_SETTINGS}})
    return merged


@router.get("/tickets")
async def list_tickets(
    status: Optional[str] = None, priority: Optional[str] = None, category: Optional[str] = None,
    source: Optional[str] = None, queue: Optional[str] = None, assigned: Optional[str] = None,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id), auth: AuthContext = Depends(get_auth_context),
    db=Depends(get_session),
):
    """List support tickets (newest first). The mobile technician app reads this as a plain array."""
    where = _filters(tenant_id, auth.user_id, status_=status, priority=priority, category=category, source=source,
                     queue=queue, assigned=assigned, customer_id=None, q=None, sla=None, open_only=False)
    tickets = (await db.execute(select(Ticket).where(where).order_by(desc(Ticket.created_at)).limit(500))).scalars().all()
    dicts = [ticket_to_dict(t) for t in tickets]
    return list(await asyncio.gather(*[_enrich_customer(d, tenant_id, auth.user_id) for d in dicts]))


@router.get("/tickets/{ticket_id}")
async def get_ticket(ticket_id: uuid.UUID, auth: AuthContext = Depends(get_auth_context), db=Depends(get_session)):
    """A ticket with its customer details and full timeline."""
    ticket = await _get_ticket(db, auth.tenant_id, ticket_id)
    replies = (await db.execute(select(TicketReply).where(TicketReply.ticket_id == ticket.id)
                                .order_by(TicketReply.created_at))).scalars().all()
    td = await _enrich_customer(ticket_to_dict(ticket), auth.tenant_id, auth.user_id)
    td["timeline"] = [reply_to_dict(r) for r in replies]
    td["events"] = await ticket_events(db, ticket.tenant_id, ticket.id)
    td["jev"] = await jev_decisions(db, ticket.tenant_id, ticket.id)
    return td


async def ticket_events(db, tenant_id: uuid.UUID, ticket_id: uuid.UUID) -> list[dict]:
    rows = (await db.execute(text("""
        SELECT e.id::text AS id, e.event_type, e.actor_id::text AS actor_id, e.actor_type, e.from_value, e.to_value,
               e.note, e.visibility, e.channel, e.data, e.created_at,
               COALESCE(NULLIF(u.full_name, ''), split_part(u.email, '@', 1)) AS actor_name
          FROM ticket_events e LEFT JOIN users u ON u.id = e.actor_id
         WHERE e.tenant_id = :t AND e.ticket_id = :id ORDER BY e.created_at, e.id"""),
        {"t": str(tenant_id), "id": ticket_id})).mappings().all()
    return [{**dict(r), "created_at": _iso(r["created_at"]), "data": r["data"] or {}} for r in rows]


async def jev_decisions(db, tenant_id: uuid.UUID, ticket_id: uuid.UUID) -> list[dict]:
    rows = (await db.execute(text("""
        SELECT id::text AS id, stage, proposal, confidence, disposition, reason, evaluated_by_jev, created_at, decided_at
          FROM ticket_jev_decisions WHERE tenant_id = :t AND ticket_id = :id ORDER BY created_at DESC LIMIT 10"""),
        {"t": str(tenant_id), "id": ticket_id})).mappings().all()
    return [{**dict(r), "created_at": _iso(r["created_at"]), "decided_at": _iso(r["decided_at"])} for r in rows]


@router.post("/tickets/{ticket_id}/jev/route")
async def ask_jev_to_route(ticket_id: uuid.UUID, auth: AuthContext = Depends(require_tier("technician")), db=Depends(get_session)):
    """Ask Jev to route this ticket now (even when the workspace mode is off). The answer is applied or suggested
    according to the workspace's Jev mode; with the mode off it is always a suggestion."""
    await _get_ticket(db, auth.tenant_id, ticket_id)
    return await jev_ticket.route_ticket(auth.tenant_id, ticket_id, force=True, actor_id=auth.user_id)


@router.post("/tickets/{ticket_id}/jev/{decision_id}/apply")
async def apply_jev_suggestion(ticket_id: uuid.UUID, decision_id: uuid.UUID,
                               auth: AuthContext = Depends(require_tier("technician")), db=Depends(get_session)):
    """Accept one of Jev's stored suggestions: it is applied as the person who clicked."""
    ticket = await _get_ticket(db, auth.tenant_id, ticket_id, lock=True)
    await require_job_access(auth, db, ticket.assigned_to)
    try:
        changed = await jev_ticket.apply_suggestion(db, auth.tenant_id, ticket, decision_id, auth.user_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="Suggestion not found")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    await db.flush()
    td = ticket_to_dict(ticket)
    await streams.notify_ticket_update(str(auth.tenant_id), td)
    return {"changed": changed, "ticket": td}


@router.post("/tickets/{ticket_id}/jev/{decision_id}/dismiss")
async def dismiss_jev_suggestion(ticket_id: uuid.UUID, decision_id: uuid.UUID,
                                 auth: AuthContext = Depends(require_tier("technician")), db=Depends(get_session)):
    await _get_ticket(db, auth.tenant_id, ticket_id)
    if not await jev_ticket.dismiss_suggestion(db, auth.tenant_id, ticket_id, decision_id, auth.user_id):
        raise HTTPException(status_code=404, detail="No open suggestion with that id")
    return {"dismissed": True}


@router.get("/tickets/{ticket_id}/events")
async def get_ticket_events(ticket_id: uuid.UUID, auth: AuthContext = Depends(get_auth_context), db=Depends(get_session)):
    """The ticket's lifecycle log: who did what and when, oldest first."""
    ticket = await _get_ticket(db, auth.tenant_id, ticket_id)
    return {"items": await ticket_events(db, ticket.tenant_id, ticket.id)}


# ── create / update ─────────────────────────────────────────────────────────

@router.post("/tickets", status_code=status.HTTP_201_CREATED)
async def create_ticket(payload: TicketCreate, auth: AuthContext = Depends(require_tier("technician")),
                        db=Depends(get_session)):
    """Open a ticket by hand (support agent and up). The customer, when given, must belong to the tenant."""
    tid = auth.tenant_id
    category = _norm_choice(payload.category, ticket_rules.CATEGORIES, "category") or "GENERAL"
    priority = _norm_choice(payload.priority, PRIORITIES, "priority") or "NORMAL"
    source = (payload.source or "manual").strip().lower()
    if source not in MANUAL_SOURCES:
        raise HTTPException(status_code=422, detail=f"source must be one of {sorted(MANUAL_SOURCES)}")
    queue = _norm_choice(payload.queue, ticket_rules.QUEUES, "queue")
    if payload.customer_id:
        await _verify_customer(tid, auth.user_id, payload.customer_id)
    if payload.assigned_to:
        await _verify_assignee(db, tid, payload.assigned_to)
        if payload.assigned_to != auth.user_id:
            await require(auth, db, "manager")
    now = datetime.now(timezone.utc)
    t = Ticket(tenant_id=tid, customer_id=payload.customer_id, subject=payload.subject.strip(),
               description=payload.description, category=category, priority=priority, status="OPEN", source=source,
               queue=queue, assigned_to=payload.assigned_to, created_by=auth.user_id, occurrence_count=1,
               last_occurrence_at=now, sla_due_at=ticketing.sla_due(priority, now),
               source_ref_type=payload.source_ref_type, source_ref_id=payload.source_ref_id,
               reply_channel=(payload.reply_channel or notify.channel_for_source(source) or None),
               reply_ref=payload.reply_ref, last_activity_at=now)
    db.add(t)
    await db.flush()
    await db.refresh(t)
    await ticketing.add_timeline(db, t.id, "event", "Ticket opened.", author_type="agent", author_id=auth.user_id,
                                 data={"source": source})
    await lifecycle.record(db, t, "created", actor_id=auth.user_id, to_value="OPEN", channel=t.reply_channel,
                           data={"source": source, "priority": priority, "category": category, "queue": queue})
    if payload.assigned_to:
        await lifecycle.record(db, t, "assigned", actor_id=auth.user_id, to_value=str(payload.assigned_to),
                               data={"at_creation": True})
    await emit(db, tid, E.EVENT_TICKET_CREATED, t, {"created_by": str(auth.user_id)})
    td = ticket_to_dict(t)
    await streams.notify_new_ticket(str(tid), td)
    return td


@router.put("/tickets/{ticket_id}")
async def update_ticket(ticket_id: uuid.UUID, payload: TicketUpdate, auth: AuthContext = Depends(require_tier("technician")),
                        db=Depends(get_session)):
    """Change status (close/reopen), priority, category or queue. Technicians: their own / unassigned jobs."""
    if not any([payload.status, payload.priority, payload.category, payload.queue]):
        raise HTTPException(status_code=422, detail="Nothing to change")
    ticket = await _get_ticket(db, auth.tenant_id, ticket_id, lock=True)
    await require_job_access(auth, db, ticket.assigned_to)
    new_status = (payload.status or "").strip().upper() or None
    if new_status == "REOPENED":
        new_status = "OPEN"
    if new_status and new_status not in TICKET_STATUSES:
        raise HTTPException(status_code=422, detail=f"status must be one of {sorted(TICKET_STATUSES)}")
    priority = _norm_choice(payload.priority, PRIORITIES, "priority")
    category = _norm_choice(payload.category, ticket_rules.CATEGORIES, "category")
    queue = _norm_choice(payload.queue, ticket_rules.QUEUES, "queue")
    changes = []
    modified = []          # (field, old, new): customer-visible fields only feed the requester notification
    transferred = None
    if priority and priority != ticket.priority:
        changes.append(f"priority {ticket.priority} → {priority}")
        modified.append(("priority", ticket.priority, priority))
        ticket.priority = priority
        ticket.sla_due_at = ticketing.sla_due(priority, _aware(ticket.created_at))
    if category and category != ticket.category:
        changes.append(f"category {ticket.category or 'none'} → {category}")
        modified.append(("category", ticket.category, category))
        ticket.category = category
    if queue and queue != ticket.queue:
        changes.append(f"queue {ticket.queue or 'none'} → {queue}")
        transferred = (ticket.queue, queue)
        ticket.queue = queue
    if changes:
        await db.flush()
        await ticketing.add_timeline(db, ticket.id, "status", "Updated: " + ", ".join(changes) + ".",
                                     author_type="agent", author_id=auth.user_id, data={"changes": changes})
        note = payload.note or None
        for field, old, new in modified:
            await lifecycle.record(db, ticket, "modified", actor_id=auth.user_id,
                                   from_value=old, to_value=new, note=note, data={"field": field})
            note = None
        if transferred:
            await lifecycle.record(db, ticket, "transferred", actor_id=auth.user_id, from_value=transferred[0],
                                   to_value=transferred[1], note=note, data={"field": "queue"})
        await emit(db, auth.tenant_id, E.EVENT_TICKET_MODIFIED, ticket, {"changes": changes})
        if any(f == "priority" for f, _, _ in modified):
            await notify.notify_requester(db, ticket, "modified", actor_id=auth.user_id,
                                          detail=f"Its priority is now {ticket.priority.title()}.")
    if new_status:
        await change_status(db, ticket, new_status, auth, payload.note)
    await db.flush()
    td = ticket_to_dict(ticket)
    await streams.notify_ticket_update(str(auth.tenant_id), td)
    return td


@router.post("/tickets/{ticket_id}/comments", status_code=status.HTTP_201_CREATED)
async def add_comment(ticket_id: uuid.UUID, payload: CommentCreate, auth: AuthContext = Depends(require_tier("technician")),
                      db=Depends(get_session)):
    """Add a comment (internal note when is_private). The first public comment records the first response."""
    ticket = await _get_ticket(db, auth.tenant_id, ticket_id, lock=True)
    message = redact_text(payload.message, 5000)
    reply = TicketReply(ticket_id=ticket.id, author_id=auth.user_id, author_type="agent", message=message,
                        is_private=payload.is_private, kind="comment")
    db.add(reply)
    ticket.updated_at = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(reply)
    public = not payload.is_private
    await lifecycle.record(db, ticket, "reply_sent" if public else "note_added", actor_id=auth.user_id, note=message,
                           visibility="public" if public else "internal", data={"reply_id": str(reply.id)})
    await emit(db, auth.tenant_id, E.EVENT_TICKET_NOTE, ticket, {"visibility": "public" if public else "internal"})
    if public:
        await notify.notify_requester(db, ticket, "note", detail=message, actor_id=auth.user_id)
    await streams.notify_ticket_update(str(auth.tenant_id), ticket_to_dict(ticket))
    return reply_to_dict(reply)


@router.post("/tickets/{ticket_id}/assign")
async def assign_ticket(ticket_id: uuid.UUID, payload: AssignRequest, auth: AuthContext = Depends(require_tier("technician")),
                        db=Depends(get_session)):
    """Assign to a member (or null to unassign). Taking or releasing your own job needs technician;
    assigning someone else, or moving someone else's job, needs manager."""
    ticket = await _get_ticket(db, auth.tenant_id, ticket_id, lock=True)
    target = payload.assigned_to
    if target not in (None, auth.user_id) or (ticket.assigned_to not in (None, auth.user_id)):
        await require(auth, db, "manager")
    if target:
        await _verify_assignee(db, auth.tenant_id, target)
    queue = _norm_choice(payload.queue, ticket_rules.QUEUES, "queue")
    previous = ticket.assigned_to
    previous_queue = ticket.queue
    previous_status = ticket.status
    ticket.assigned_to = target
    if queue:
        ticket.queue = queue
    if target and ticket.status == "OPEN":
        ticket.status = "IN_PROGRESS"
    await db.flush()
    if target is None:
        await lifecycle.record(db, ticket, "unassigned", actor_id=auth.user_id, from_value=str(previous) if previous else None)
    elif target != previous:
        await lifecycle.record(db, ticket, "reassigned" if previous else "assigned", actor_id=auth.user_id,
                               from_value=str(previous) if previous else None, to_value=str(target))
    if queue and queue != previous_queue:
        await lifecycle.record(db, ticket, "transferred", actor_id=auth.user_id, from_value=previous_queue, to_value=queue,
                               data={"field": "queue"})
    if ticket.status != previous_status:
        await lifecycle.record(db, ticket, "status_changed", actor_id=auth.user_id, from_value=previous_status,
                               to_value=ticket.status, data={"by": "assignment"})
    if target and target != previous:
        await notify.notify_requester(db, ticket, "assigned", actor_id=auth.user_id)
    who = "nobody" if target is None else "themselves" if target == auth.user_id else "a teammate"
    await ticketing.add_timeline(db, ticket.id, "assignment", f"Assigned to {who}." if target else "Unassigned.",
                                 author_type="agent", author_id=auth.user_id,
                                 data={"from": str(previous) if previous else None, "to": str(target) if target else None,
                                       "queue": ticket.queue})
    await emit(db, auth.tenant_id, E.EVENT_TICKET_ASSIGNED, ticket,
               {"assigned_to": str(target) if target else None})
    td = ticket_to_dict(ticket)
    await streams.notify_ticket_update(str(auth.tenant_id), td)
    return td


# ── routing rules (per tenant) ──────────────────────────────────────────────

@router.get("/ticket-rules")
async def list_rules(auth: AuthContext = Depends(get_auth_context), db=Depends(get_session)):
    """Every event -> ticket rule with the tenant's effective settings (defaults + overrides)."""
    from services.support.consumer import load_overrides
    overrides = await load_overrides(db, auth.tenant_id)
    out = []
    for rule in ticket_rules.RULES.values():
        eff = ticket_rules.effective_rule(rule, overrides.get(rule.key))
        eff["assigned_to"] = str(eff["assigned_to"]) if eff["assigned_to"] else None
        eff["defaults"] = {"enabled": rule.enabled, "category": rule.category, "priority": rule.priority,
                           "queue": rule.queue, "outcome": "ticket"}
        out.append(eff)
    return {"rules": out, "noise": list(ticket_rules.NOISE_PATTERNS), "outcomes": list(custom_rules.OUTCOMES),
            "outcome_labels": custom_rules.OUTCOME_LABELS}


@router.put("/ticket-rules/{rule_key}")
async def put_rule(rule_key: str, payload: RuleOverride, auth: AuthContext = Depends(require_tier("manager")),
                   db=Depends(get_session)):
    """Override a rule for this tenant (enable/disable, category, priority, queue, default assignee) or reset it."""
    if rule_key not in ticket_rules.RULES:
        raise HTTPException(status_code=404, detail="Unknown rule")
    if payload.reset:
        await db.execute(text("DELETE FROM ticket_rule_overrides WHERE tenant_id = :t AND rule_key = :k"),
                         {"t": str(auth.tenant_id), "k": rule_key})
    else:
        category = _norm_choice(payload.category, ticket_rules.CATEGORIES, "category")
        priority = _norm_choice(payload.priority, PRIORITIES, "priority")
        queue = _norm_choice(payload.queue, ticket_rules.QUEUES, "queue")
        outcome = (payload.outcome or "").strip().lower() or None
        if outcome and outcome not in custom_rules.OUTCOMES:
            raise HTTPException(status_code=422, detail=f"outcome must be one of {list(custom_rules.OUTCOMES)}")
        if payload.assigned_to:
            await _verify_assignee(db, auth.tenant_id, payload.assigned_to)
        await db.execute(text("""
            INSERT INTO ticket_rule_overrides (tenant_id, rule_key, enabled, category, priority, queue, assigned_to, outcome,
                                               updated_by, updated_at)
            VALUES (:t, :k, :enabled, :category, :priority, :queue, :assignee, :outcome, :by, now())
            ON CONFLICT (tenant_id, rule_key) DO UPDATE SET enabled = EXCLUDED.enabled, category = EXCLUDED.category,
                priority = EXCLUDED.priority, queue = EXCLUDED.queue, assigned_to = EXCLUDED.assigned_to,
                outcome = EXCLUDED.outcome, updated_by = EXCLUDED.updated_by, updated_at = now()"""),
            {"t": str(auth.tenant_id), "k": rule_key, "enabled": payload.enabled, "category": category,
             "priority": priority, "queue": queue, "assignee": payload.assigned_to, "outcome": outcome, "by": auth.user_id})
    from services.support.consumer import load_overrides
    overrides = await load_overrides(db, auth.tenant_id)
    eff = ticket_rules.effective_rule(ticket_rules.RULES[rule_key], overrides.get(rule_key))
    eff["assigned_to"] = str(eff["assigned_to"]) if eff["assigned_to"] else None
    return eff
