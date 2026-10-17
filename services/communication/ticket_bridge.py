"""Communication-service side of the ticket desk: delivers what support asks for over the event bus.

Support never talks to a mail provider or creates chat items itself. It publishes two events and this module
(the communication service owns mailboxes, channels, tasks, escalations and the schedule) acts on them:

`support.ticket.customer_update`
    Tell the requester about their ticket by email, in the thread the request came in on. The wording is
    fixed templates written by support (see support/notify.py); this module only checks and sends. It refuses
    credential-shaped text, only replies to a real inbound sender (never an auto-responder), and sends at most
    once per event even if the bus redelivers it. A failure raises, so the bus retries with back-off.

`support.ticket.outcome_requested`
    Create the task, escalation or schedule item that goes with a ticket, in the tenant's "Tickets" channel
    (created on first use, visible to everyone in the workspace). Created once per (ticket, outcome).
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Optional

from sqlalchemy import select, text

from services.common import email_safety as ES
from services.common import ticket_events as E
from services.common.event_bus import EventConsumer
from services.communication.database import get_session
from services.communication.models import AgentEmail, Channel, Escalation, ScheduleEvent, Task

logger = logging.getLogger("communication.ticket_bridge")

CONSUMER_NAME = "communication_tickets"
TICKETS_CHANNEL = "Tickets"
# Hours until a task is due / a follow-up is booked, by ticket priority.
DUE_HOURS = {"URGENT": 4, "HIGH": 8, "NORMAL": 24, "LOW": 72}
FOLLOW_UP_HOURS = {"URGENT": 1, "HIGH": 2, "NORMAL": 8, "LOW": 24}
_AUTO_SENDER = re.compile(r"(?i)(no-?reply|mailer-daemon|postmaster|do-?not-?reply|auto[- ]?reply)")


def _uuid(value) -> Optional[uuid.UUID]:
    try:
        return uuid.UUID(str(value)) if value else None
    except (ValueError, TypeError):
        return None


# ── customer updates ────────────────────────────────────────────────────────

async def _resolve_thread(session, tenant_id: uuid.UUID, ref: str) -> Optional[dict]:
    """The email_threads row a ticket's reply_ref points at (its id, or its thread key)."""
    by_id = _uuid(ref)
    row = (await session.execute(text("""
        SELECT id::text AS id, mailbox_id::text AS mailbox_id, thread_key, provider_thread_id, subject FROM email_threads
         WHERE tenant_id = CAST(:t AS uuid) AND (id = CAST(:id AS uuid) OR thread_key = :ref) LIMIT 1"""),
        {"t": str(tenant_id), "id": str(by_id) if by_id else None, "ref": ref})).mappings().first()
    return dict(row) if row else None


async def _last_inbound(session, tenant_id: uuid.UUID, thread: dict) -> Optional[AgentEmail]:
    from services.communication.routes.mail_threads import _thread_emails
    emails = await _thread_emails(session, SimpleNamespace(tenant_id=tenant_id), thread)
    return next((e for e in reversed(emails) if e.direction == "inbound"), None)


async def _already_sent(session, tenant_id: uuid.UUID, event_id: str) -> bool:
    rows = (await session.execute(select(AgentEmail.id).where(
        AgentEmail.tenant_id == tenant_id, AgentEmail.direction == "outbound",
        AgentEmail.headers["ticket_update_event"].astext == event_id).limit(1))).first()
    return rows is not None


async def deliver_customer_update(event: dict) -> None:
    from services.communication.routes import mail as M
    p = event.get("payload") or {}
    if p.get("channel") != "email" or not p.get("reply_ref"):
        return
    tenant_id = uuid.UUID(event["tenant_id"])
    body, subject = str(p.get("body") or "").strip(), str(p.get("subject") or "").strip()[:300]
    if not body:
        return
    if ES.contains_secret(body):
        logger.warning("ticket update %s refused: text looks like a credential", p.get("ticket_ref"))
        return
    update_id = str(p.get("event_id") or event["id"])
    async with get_session() as session:
        if await _already_sent(session, tenant_id, update_id):
            return
        thread = await _resolve_thread(session, tenant_id, str(p["reply_ref"]))
        if thread is None:
            logger.info("ticket update %s: thread %s not found", p.get("ticket_ref"), p["reply_ref"])
            return
        last_in = await _last_inbound(session, tenant_id, thread)
    if last_in is None or _AUTO_SENDER.search(last_in.sender or ""):
        return
    target = M._clean_addrs([M._reply_target(last_in.sender)], "sender")
    rec = await M._deliver_and_store(
        tenant_id, last_in.mailbox_id, target, [], [], subject or M._reply_subject(last_in.subject), body, None,
        last_in.message_id,
        extra_headers={"ticket_update_event": update_id, "ticket_ref": str(p.get("ticket_ref") or ""),
                       "ticket_trigger": str(p.get("trigger") or "")},
        thread_id=(last_in.headers or {}).get("thread_id") or thread.get("provider_thread_id"),
        actor={"action": "ticket_update_sent", "id": None, "kind": "system",
               "detail": {"ticket": p.get("ticket_ref"), "trigger": p.get("trigger")}})
    if rec.status != "sent":
        raise RuntimeError("the mail provider did not accept the ticket update")


# ── task / escalation / schedule items ──────────────────────────────────────

async def _service_user(session, tenant_id: uuid.UUID, preferred: Optional[uuid.UUID]) -> Optional[uuid.UUID]:
    """Who the created items are attributed to: the ticket's assignee, else the workspace's first active member."""
    if preferred:
        ok = (await session.execute(text("SELECT 1 FROM users WHERE id = :u AND tenant_id = :t AND COALESCE(is_active, true)"),
                                    {"u": str(preferred), "t": str(tenant_id)})).first()
        if ok:
            return preferred
    row = (await session.execute(text("""
        SELECT id FROM users WHERE tenant_id = :t AND COALESCE(is_active, true) ORDER BY created_at, id LIMIT 1"""),
        {"t": str(tenant_id)})).first()
    return row[0] if row else None


async def _tickets_channel(session, tenant_id: uuid.UUID, owner: uuid.UUID) -> Channel:
    ch = (await session.execute(select(Channel).where(
        Channel.tenant_id == tenant_id, Channel.name == TICKETS_CHANNEL, Channel.is_private == False  # noqa: E712
    ).order_by(Channel.created_at).limit(1))).scalar_one_or_none()
    if ch is None:
        ch = Channel(tenant_id=tenant_id, name=TICKETS_CHANNEL, is_private=False, created_by=owner,
                     description="Tasks, escalations and follow-ups raised from tickets")
        session.add(ch)
        await session.flush()
    return ch


async def create_outcome(event: dict) -> Optional[str]:
    """Create the item for a `support.ticket.outcome_requested` event. Returns what was created, or None."""
    p = event.get("payload") or {}
    outcome = p.get("outcome")
    if outcome not in ("task", "escalation", "schedule"):
        return None
    tenant_id = uuid.UUID(event["tenant_id"])
    ticket_id = str(p.get("ticket_id") or "")
    if not ticket_id:
        return None
    priority = str(p.get("priority") or "NORMAL").upper()
    title = f"Ticket: {str(p.get('title') or 'follow up')}"[:200]
    detail = f"{str(p.get('description') or '')[:900]}\n\nticket:{ticket_id}".strip()
    assignee = _uuid(p.get("assigned_to"))
    async with get_session() as session:
        actor = await _service_user(session, tenant_id, assignee)
        if actor is None:
            logger.warning("ticket %s: no active member to attribute the %s to", ticket_id, outcome)
            return None
        channel = await _tickets_channel(session, tenant_id, actor)
        now = datetime.now(timezone.utc)
        if outcome == "escalation":
            if (await session.execute(select(Escalation.id).where(
                    Escalation.tenant_id == tenant_id, Escalation.ticket_id == ticket_id).limit(1))).first():
                return None
            session.add(Escalation(tenant_id=tenant_id, channel_id=channel.id, ticket_id=ticket_id, reason=detail,
                                   assigned_to=assignee, created_by=actor))
        elif outcome == "task":
            if (await session.execute(select(Task.id).where(
                    Task.tenant_id == tenant_id, Task.description.like(f"%ticket:{ticket_id}")).limit(1))).first():
                return None
            session.add(Task(tenant_id=tenant_id, channel_id=channel.id, user_id=actor, title=title, description=detail,
                             assignee_id=assignee, due_date=now + timedelta(hours=DUE_HOURS.get(priority, 24)), created_by=actor))
        else:
            if (await session.execute(select(ScheduleEvent.id).where(
                    ScheduleEvent.tenant_id == tenant_id, ScheduleEvent.notes.like(f"%ticket:{ticket_id}")).limit(1))).first():
                return None
            start = now + timedelta(hours=FOLLOW_UP_HOURS.get(priority, 8))
            session.add(ScheduleEvent(tenant_id=tenant_id, channel_id=channel.id, user_id=assignee or actor, title=title,
                                      type="follow_up", start_time=start, end_time=start + timedelta(minutes=30),
                                      notes=detail, status="upcoming", created_by=actor))
    return outcome


# ── consumer ────────────────────────────────────────────────────────────────

async def _handle(event: dict) -> None:
    if event["type"] == E.EVENT_CUSTOMER_UPDATE:
        await deliver_customer_update(event)
    elif event["type"] == E.EVENT_OUTCOME_REQUESTED:
        created = await create_outcome(event)
        if created:
            logger.info("ticket %s -> %s created", (event.get("payload") or {}).get("ticket_id"), created)


consumer = EventConsumer(CONSUMER_NAME, {E.EVENT_CUSTOMER_UPDATE: _handle, E.EVENT_OUTCOME_REQUESTED: _handle})
