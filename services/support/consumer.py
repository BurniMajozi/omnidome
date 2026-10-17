"""Support service's event-bus consumer: every mapped event becomes (or joins) a ticket.

Two kinds of rule feed it: the built-in table (ticket_rules.py, tuned per tenant through overrides) and the
rules a tenant added themselves (custom_rules.py). Built-in event types are subscribed by name; custom
patterns are subscribed when a rule is saved (automation_api.py) and when the service starts.

Delivery is at-least-once, so the handler is idempotent twice over: the ticket dedupe key folds a
redelivered event into the same open ticket, and the event id is recorded on the timeline entry.
Noise, disabled rules and unmapped events return without touching the database beyond reading the
tenant's rules.

When a ticket is created and its rule asks for more than a ticket (a task, an escalation or a schedule
item) a `support.ticket.outcome_requested` event is published in the same transaction; the communication
service creates the item. Jev routing then runs after the commit (see jev_ticket.py) and never blocks or
fails the delivery.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Awaitable, Callable, Optional

from sqlalchemy import text

from services.common import ticket_events as E
from services.common.db import session_scope
from services.common.event_bus import EventConsumer, ensure_schema, publish
from services.support import automation_api, custom_rules, ticket_rules, ticketing

logger = logging.getLogger("support.consumer")

CONSUMER_NAME = "support_tickets"

# Set by main.py so a new ticket reaches live technician streams (SSE).
_notifier: Optional[Callable[[str, str, dict], Awaitable[None]]] = None
# Set by main.py: called with (tenant_id, ticket_id) after a ticket commits, to ask Jev to route it.
_router: Optional[Callable[[uuid.UUID, uuid.UUID], Awaitable[None]]] = None
_background: set = set()


def set_notifier(fn: Optional[Callable[[str, str, dict], Awaitable[None]]]) -> None:
    global _notifier
    _notifier = fn


def set_router(fn: Optional[Callable[[uuid.UUID, uuid.UUID], Awaitable[None]]]) -> None:
    global _router
    _router = fn


async def load_overrides(db, tenant_id: uuid.UUID) -> dict[str, dict]:
    rows = (await db.execute(text(
        """SELECT rule_key, enabled, category, priority, queue, assigned_to, outcome
             FROM ticket_rule_overrides WHERE tenant_id = :t"""), {"t": str(tenant_id)})).mappings().all()
    return {r["rule_key"]: dict(r) for r in rows}


async def request_outcome(db, tenant_id: uuid.UUID, ticket_id: uuid.UUID, spec: ticket_rules.TicketSpec) -> None:
    """Ask the communication service for the task / escalation / schedule item that goes with a new ticket."""
    if spec.outcome == "ticket":
        return
    await publish(db, tenant_id, E.EVENT_OUTCOME_REQUESTED,
                  {"ticket_id": str(ticket_id), "outcome": spec.outcome, "title": spec.subject,
                   "description": spec.description[:1000], "priority": spec.priority, "queue": spec.queue,
                   "category": spec.category, "assigned_to": str(spec.assigned_to) if spec.assigned_to else None},
                  source="support", subject=("ticket", ticket_id),
                  idempotency_key=f"ticket-outcome:{ticket_id}:{spec.outcome}")


async def handle_event(event: dict) -> None:
    tenant_id = uuid.UUID(event["tenant_id"])
    etype = event.get("type")
    builtin = etype in ticket_rules.RULES
    async with session_scope() as db:
        if builtin:
            spec = ticket_rules.resolve(event, await load_overrides(db, tenant_id))
        else:
            spec = custom_rules.resolve_custom(await automation_api.load_rules(db, tenant_id), event)
        if spec is None:
            return
        result = await ticketing.raise_ticket(db, tenant_id, spec)
        if result.created:
            await request_outcome(db, tenant_id, result.ticket_id, spec)
        logger.info("event %s -> ticket %s (%s, occurrence %s)", etype, result.ticket_id,
                    "created" if result.created else "skipped" if result.skipped else "joined", result.occurrence_count)
    if _notifier is not None and not result.skipped:
        try:
            await _notifier(str(tenant_id), "new_ticket" if result.created else "ticket_update",
                            {"id": str(result.ticket_id), "occurrence_count": result.occurrence_count})
        except Exception:  # noqa: BLE001 - a dead SSE stream must not fail the delivery
            logger.debug("ticket notifier failed", exc_info=True)
    if result.created and _router is not None:
        task = asyncio.create_task(_route_quietly(tenant_id, result.ticket_id))
        _background.add(task)
        task.add_done_callback(_background.discard)


async def _route_quietly(tenant_id: uuid.UUID, ticket_id: uuid.UUID) -> None:
    try:
        await _router(tenant_id, ticket_id)
    except Exception:  # noqa: BLE001 - routing is a suggestion layer; the ticket already exists
        logger.warning("Jev routing failed for ticket %s", ticket_id, exc_info=True)


class SupportConsumer(EventConsumer):
    """Subscribes to the built-in event types plus every pattern a tenant's custom rule listens for.

    Custom patterns are not known at import time, so the handler map has a catch-all ("*") that the bus never
    subscribes to (that would deliver every event in the platform): it only receives events whose pattern has a
    subscription row, which `automation_api` writes when a rule is saved."""

    async def ensure_subscriptions(self) -> None:
        async with session_scope() as session:
            await ensure_schema(session)
            patterns = {p for p in self.handlers if p != "*"} | await automation_api.active_patterns(session)
            for pattern in patterns:
                await session.execute(
                    text("INSERT INTO event_subscriptions (consumer, event_pattern) VALUES (:c, :p) ON CONFLICT DO NOTHING"),
                    {"c": self.name, "p": pattern})


consumer = SupportConsumer(CONSUMER_NAME, {**{pattern: handle_event for pattern in ticket_rules.SUBSCRIPTIONS}, "*": handle_event})
