"""Ticket creation with dedupe: the database half of the shared ticket mechanism.

`raise_ticket` is the only function that turns a TicketSpec (from ticket_rules.resolve, or a manual
create) into a row. Guarantees:

* one OPEN ticket per (tenant, dedupe_key), enforced by a partial unique index, so two consumers racing
  on the same key cannot both create it;
* a repeat bumps `occurrence_count`/`last_occurrence_at`, adds a system comment (capped so a hot loop
  cannot flood the timeline: the first few repeats, then every 10th) and raises priority as it recurs;
* a closed ticket is never silently reopened by a repeat: the problem is back, so a new ticket opens and
  links to the previous one in its context;
* every free-text field is redacted again here, whatever the source.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import text

from services.common import ticket_events as E
from services.common.event_bus import notify, publish
from services.common.redaction import redact_data, redact_text
from services.support import lifecycle
from services.support.ticket_rules import TicketSpec, escalated_priority

SLA_HOURS = {"URGENT": 4, "HIGH": 8, "NORMAL": 24, "LOW": 72}
OPEN_STATUSES = ("OPEN", "IN_PROGRESS", "ESCALATED", "ON_HOLD", "PENDING", "REOPENED")
CLOSED_STATUSES = ("RESOLVED", "CLOSED")

# Repeat comments: always for repeats 2..REPEAT_COMMENT_HEAD, then every REPEAT_COMMENT_EVERY-th.
REPEAT_COMMENT_HEAD = 5
REPEAT_COMMENT_EVERY = 10


@dataclass
class RaiseResult:
    ticket_id: uuid.UUID
    created: bool
    occurrence_count: int
    commented: bool = False
    skipped: bool = False


def sla_due(priority: str, created: Optional[datetime] = None) -> datetime:
    return (created or datetime.now(timezone.utc)) + timedelta(hours=SLA_HOURS.get(priority, 24))


def reply_route(spec: TicketSpec) -> tuple[Optional[str], Optional[str]]:
    """(channel, address/thread) the requester can be reached on, from what the source told us."""
    from services.support.notify import channel_for_source
    channel = channel_for_source(spec.source)
    if channel == "email" and spec.ref_type == "email_thread" and spec.ref_id:
        return "email", spec.ref_id
    return channel, None


def should_comment_on_repeat(occurrences: int) -> bool:
    return 2 <= occurrences <= REPEAT_COMMENT_HEAD or occurrences % REPEAT_COMMENT_EVERY == 0


async def add_timeline(db, ticket_id: uuid.UUID, kind: str, message: str, *, author_type: str = "system",
                       author_id: Optional[uuid.UUID] = None, is_private: bool = True,
                       data: Optional[dict] = None) -> None:
    import json
    await db.execute(text("""
        INSERT INTO ticket_replies (id, ticket_id, author_id, author_type, message, is_private, kind, data)
        VALUES (:id, :ticket_id, :author_id, :author_type, :message, :is_private, :kind, CAST(:data AS jsonb))"""),
        {"id": uuid.uuid4(), "ticket_id": ticket_id, "author_id": author_id, "author_type": author_type,
         "message": message, "is_private": is_private, "kind": kind, "data": json.dumps(data or {}, default=str)})


async def _find_open(db, tenant_id: uuid.UUID, key: str):
    return (await db.execute(text(
        """SELECT id, priority, occurrence_count, status FROM tickets
            WHERE tenant_id = :t AND dedupe_key = :k AND status NOT IN ('CLOSED', 'RESOLVED')
            ORDER BY created_at DESC LIMIT 1 FOR UPDATE"""),
        {"t": str(tenant_id), "k": key})).mappings().first()


async def _bump(db, tenant_id: uuid.UUID, existing, spec: TicketSpec) -> RaiseResult:
    count = int(existing["occurrence_count"] or 1) + 1
    new_priority = escalated_priority(existing["priority"] or spec.priority, count)
    await db.execute(text("""
        UPDATE tickets SET occurrence_count = :n, last_occurrence_at = now(), updated_at = now(),
               priority = :p, sla_due_at = CASE WHEN :p <> priority THEN :sla ELSE sla_due_at END
         WHERE id = :id"""),
        {"n": count, "p": new_priority, "sla": sla_due(new_priority), "id": existing["id"]})
    commented = False
    if spec.repeat_comment and should_comment_on_repeat(count):
        suffix = f" (occurrence {count})" if count > 1 else ""
        await add_timeline(db, existing["id"], "event", f"{spec.repeat_comment}{suffix}",
                           data={"event_type": spec.event_type, "event_id": spec.event_id, "occurrence": count})
        commented = True
    await lifecycle.insert_event(db, tenant_id, existing["id"], "repeated", actor_type="system", to_value=str(count),
                                 data={"event_type": spec.event_type, "occurrence": count})
    if new_priority != existing["priority"]:
        await add_timeline(db, existing["id"], "status", f"Priority raised to {new_priority} after {count} occurrences.",
                           data={"priority": new_priority})
        await lifecycle.insert_event(db, tenant_id, existing["id"], "modified", actor_type="system",
                                     from_value=existing["priority"], to_value=new_priority,
                                     note=f"Raised after {count} occurrences.", data={"field": "priority", "automatic": True})
        await db.execute(text("UPDATE tickets SET modification_count = modification_count + 1, last_activity_at = now() WHERE id = :id"),
                         {"id": existing["id"]})
    await publish(db, tenant_id, E.EVENT_TICKET_REPEATED,
                  {"ticket_id": str(existing["id"]), "occurrences": count, "source": spec.source, "priority": new_priority},
                  source="support", subject=("ticket", existing["id"]),
                  idempotency_key=f"ticket-repeat:{existing['id']}:{count}")
    return RaiseResult(existing["id"], False, count, commented)


async def raise_ticket(db, tenant_id: uuid.UUID, spec: TicketSpec) -> RaiseResult:
    """Create the ticket for `spec`, or fold it into the open ticket with the same dedupe key."""
    import json

    spec.subject = redact_text(spec.subject, 200) or "(no subject)"
    spec.description = redact_text(spec.description, 2000)
    spec.repeat_comment = redact_text(spec.repeat_comment, 400)
    spec.context = redact_data(spec.context or {})

    existing = await _find_open(db, tenant_id, spec.dedupe_key)
    if spec.comment_only:
        if existing is None:
            return RaiseResult(uuid.UUID(int=0), False, 0, skipped=True)
        await add_timeline(db, existing["id"], "event", spec.repeat_comment or "Related event received.",
                           data={"event_type": spec.event_type, "event_id": spec.event_id})
        await db.execute(text("UPDATE tickets SET updated_at = now() WHERE id = :id"), {"id": existing["id"]})
        return RaiseResult(existing["id"], False, int(existing["occurrence_count"] or 1), True)
    if existing is not None:
        return await _bump(db, tenant_id, existing, spec)

    previous = (await db.execute(text(
        """SELECT id FROM tickets WHERE tenant_id = :t AND dedupe_key = :k AND status IN ('CLOSED', 'RESOLVED')
            ORDER BY created_at DESC LIMIT 1"""), {"t": str(tenant_id), "k": spec.dedupe_key})).scalar()
    context = dict(spec.context)
    if previous:
        context["previous_ticket_id"] = str(previous)

    ticket_id = uuid.uuid4()
    reply_channel, reply_ref = reply_route(spec)
    row = (await db.execute(text("""
        INSERT INTO tickets (id, tenant_id, customer_id, subject, description, priority, status, category, assigned_to,
                             source, source_ref_type, source_ref_id, source_link, event_type, dedupe_key,
                             occurrence_count, last_occurrence_at, queue, sla_due_at, context, created_at, updated_at,
                             reply_channel, reply_ref, last_activity_at, assignment_count, first_assigned_at)
        VALUES (:id, :tenant, :customer, :subject, :description, :priority, 'OPEN', :category, :assigned_to,
                :source, :ref_type, :ref_id, :link, :event_type, :dedupe_key,
                1, now(), :queue, :sla, CAST(:context AS jsonb), now(), now(),
                :reply_channel, :reply_ref, now(), :assignments, CASE WHEN CAST(:assigned_to AS uuid) IS NULL THEN NULL ELSE now() END)
        ON CONFLICT (tenant_id, dedupe_key)
            WHERE dedupe_key IS NOT NULL AND status NOT IN ('CLOSED', 'RESOLVED')
        DO NOTHING
        RETURNING id"""),
        {"id": ticket_id, "tenant": str(tenant_id), "customer": spec.customer_id, "subject": spec.subject,
         "description": spec.description, "priority": spec.priority, "category": spec.category,
         "assigned_to": spec.assigned_to, "source": spec.source, "ref_type": spec.ref_type, "ref_id": spec.ref_id,
         "link": spec.link, "event_type": spec.event_type, "dedupe_key": spec.dedupe_key, "queue": spec.queue,
         "sla": sla_due(spec.priority), "context": json.dumps(context, default=str),
         "reply_channel": reply_channel, "reply_ref": reply_ref, "assignments": 1 if spec.assigned_to else 0})).first()
    if row is None:      # lost a race to another consumer: it is an open ticket now, so this is a repeat
        existing = await _find_open(db, tenant_id, spec.dedupe_key)
        if existing is not None:
            return await _bump(db, tenant_id, existing, spec)
        raise RuntimeError("ticket insert conflicted but no open ticket found")

    await add_timeline(db, ticket_id, "event", f"Ticket opened from {spec.source.replace('_', ' ')}.",
                       data={"event_type": spec.event_type, "event_id": spec.event_id, "ref_type": spec.ref_type,
                             "ref_id": spec.ref_id})
    await lifecycle.insert_event(db, tenant_id, ticket_id, "created", actor_type="system", to_value="OPEN",
                                 channel=reply_channel, data={"source": spec.source, "event_type": spec.event_type,
                                                              "priority": spec.priority, "category": spec.category,
                                                              "queue": spec.queue})
    if spec.assigned_to:
        await add_timeline(db, ticket_id, "assignment", "Assigned by the tenant's routing rule.",
                           data={"assigned_to": str(spec.assigned_to)})
        await lifecycle.insert_event(db, tenant_id, ticket_id, "assigned", actor_type="system", to_value=str(spec.assigned_to),
                                     data={"by": "routing_rule"})
    await publish(db, tenant_id, E.EVENT_TICKET_CREATED,
                  {"ticket_id": str(ticket_id), "source": spec.source, "category": spec.category,
                   "priority": spec.priority, "queue": spec.queue, "subject": spec.subject,
                   "ref_type": spec.ref_type, "ref_id": spec.ref_id},
                  source="support", subject=("ticket", ticket_id), idempotency_key=f"ticket-created:{ticket_id}")
    if spec.priority in {"HIGH", "URGENT"}:
        await notify(db, tenant_id, f"New {spec.priority.lower()} ticket: {spec.subject}"[:200],
                     body=spec.description[:300] or None, category="support",
                     severity="critical" if spec.priority == "URGENT" else "warning",
                     link=f"/dashboard?section=service&ticket={ticket_id}", source="support", subject=("ticket", ticket_id))
    return RaiseResult(ticket_id, True, 1)
