"""The ticket's time dimension: every change is one row in `ticket_events` (who, when, from -> to, note).

`record()` is the only writer. It also keeps the denormalised counters and timestamps on the ticket in step
(first response, first assignment, assignments, modifications, transfers, reopens, last activity), so the
desk can show them without scanning the log and `kpi.py` can compute time to respond / resolve and
first-touch resolution from plain columns.

Event types (ticket_events.event_type):

    created        the ticket opened                            to_value = status
    assigned       given to a person for the first time         to_value = user id
    reassigned     moved from one person to another             from_value / to_value = user ids
    unassigned     released                                     from_value = user id
    transferred    moved to another queue                       from_value / to_value = queue
    modified       priority or category changed                 from_value / to_value = old / new, data.field
    status_changed any other status move                        from_value / to_value = status
    note_added     an internal or customer-visible note         note = the text
    reply_sent     a customer-visible reply by a person         note = the text
    customer_notified  the requester was told something         channel, data.trigger, data.delivery
    escalated      status moved to ESCALATED
    resolved       RESOLVED
    closed         CLOSED
    reopened       back from RESOLVED/CLOSED
    sla_breached   the resolution deadline passed while open (written once, by the watcher)
    repeated       the same problem arrived again (folded into this ticket)
    jev_suggested  Jev proposed routing or an escalation; a person decides
    jev_applied    Jev's routing was applied
    jev_review     Jev reviewed a closed ticket

Callers pass the ticket's own transaction (`db`); nothing here commits.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import text

from services.common.redaction import redact_text

EVENT_TYPES = frozenset({
    "created", "assigned", "reassigned", "unassigned", "transferred", "modified", "status_changed", "note_added",
    "reply_sent", "customer_notified", "escalated", "resolved", "closed", "reopened", "sla_breached", "repeated",
    "jev_suggested", "jev_applied", "jev_review",
})

# Events where a person demonstrably picked the ticket up: the first of these is the "first response".
RESPONSE_EVENTS = frozenset({"assigned", "reassigned", "reply_sent"})
# Events that are the system or the requester talking, never an agent working the ticket.
PASSIVE_EVENTS = frozenset({"created", "repeated", "sla_breached", "customer_notified", "jev_suggested", "jev_review"})


def now() -> datetime:
    return datetime.now(timezone.utc)


def status_event_type(old: str, new: str) -> str:
    """The event type for a status move."""
    closed = ("RESOLVED", "CLOSED")
    if old in closed and new not in closed:
        return "reopened"
    if new == "RESOLVED":
        return "resolved"
    if new == "CLOSED":
        return "closed"
    if new == "ESCALATED":
        return "escalated"
    return "status_changed"


async def insert_event(db, tenant_id, ticket_id, event_type: str, *, actor_id=None, actor_type: str = "system",
                       from_value: Optional[str] = None, to_value: Optional[str] = None, note: Optional[str] = None,
                       visibility: str = "internal", channel: Optional[str] = None, data: Optional[dict] = None,
                       at: Optional[datetime] = None) -> uuid.UUID:
    """Insert one event row and nothing else (use `record` to also update the ticket)."""
    if event_type not in EVENT_TYPES:
        raise ValueError(f"unknown ticket event type {event_type!r}")
    event_id = uuid.uuid4()
    await db.execute(text("""
        INSERT INTO ticket_events (id, tenant_id, ticket_id, event_type, actor_id, actor_type, from_value, to_value,
                                   note, visibility, channel, data, created_at)
        VALUES (:id, :tenant, :ticket, :type, :actor, :actor_type, :from_value, :to_value, :note, :visibility,
                :channel, CAST(:data AS jsonb), COALESCE(:at, now()))"""),
        {"id": event_id, "tenant": str(tenant_id), "ticket": ticket_id, "type": event_type,
         "actor": actor_id, "actor_type": actor_type, "from_value": str(from_value)[:200] if from_value else None,
         "to_value": str(to_value)[:200] if to_value else None, "note": redact_text(note, 5000) if note else None,
         "visibility": "public" if visibility == "public" else "internal", "channel": channel,
         "data": json.dumps(data or {}, default=str), "at": at})
    return event_id


async def record(db, ticket, event_type: str, *, actor_id=None, actor_type: str = "agent",
                 from_value: Optional[str] = None, to_value: Optional[str] = None, note: Optional[str] = None,
                 visibility: str = "internal", channel: Optional[str] = None, data: Optional[dict] = None) -> uuid.UUID:
    """Log an event for an ORM `Ticket` and update its counters and timestamps."""
    at = now()
    event_id = await insert_event(db, ticket.tenant_id, ticket.id, event_type, actor_id=actor_id, actor_type=actor_type,
                                  from_value=from_value, to_value=to_value, note=note, visibility=visibility,
                                  channel=channel, data=data, at=at)
    if event_type not in PASSIVE_EVENTS:
        ticket.last_activity_at = at
    if event_type in ("assigned", "reassigned"):
        ticket.assignment_count = (ticket.assignment_count or 0) + 1
        if ticket.first_assigned_at is None:
            ticket.first_assigned_at = at
    elif event_type == "modified":
        ticket.modification_count = (ticket.modification_count or 0) + 1
    elif event_type == "transferred":
        ticket.transfer_count = (ticket.transfer_count or 0) + 1
    elif event_type == "reopened":
        ticket.reopen_count = (ticket.reopen_count or 0) + 1
        ticket.escalated_at = None
        ticket.breach_logged_at = None
    elif event_type == "escalated":
        ticket.escalated_at = at
    counts_as_response = actor_type == "agent" and (
        (event_type in RESPONSE_EVENTS and not (event_type == "reply_sent" and visibility != "public"))
        or (event_type == "status_changed" and to_value == "IN_PROGRESS"))
    if counts_as_response and ticket.first_response_at is None:
        ticket.first_response_at = at
    return event_id


def first_touch_resolution(assignment_count: int, transfer_count: int, reopen_count: int) -> bool:
    """True when one person resolved it: at most one assignment, never moved to another queue, never reopened."""
    return (assignment_count or 0) <= 1 and (transfer_count or 0) == 0 and (reopen_count or 0) == 0
