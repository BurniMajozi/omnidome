"""The one way any service asks for a ticket.

Two routes lead to a ticket, both through the Postgres event bus and both handled by the support
service's consumer (services/support/consumer.py), so no service carries its own ticket logic:

1. Publish the domain event you already publish (`iot.home.offline`, `finance.payment.failed`, ...).
   The support rule table maps it to a ticket (category, priority, dedupe key, link back).
2. Call `request_ticket(...)` for an explicit "a human should look at this" with no domain event of
   its own. It publishes `ticket.requested`; the payload carries the whole ticket spec.

Both run inside the caller's transaction, so a ticket request exists if and only if the business change
committed. Text is redacted again on the support side before it is stored.
"""

from __future__ import annotations

import uuid
from typing import Any, Optional

from services.common.event_bus import publish

EVENT_TICKET_REQUESTED = "ticket.requested"

# Events raised by the support service itself (orchestrator automations can trigger on these).
EVENT_TICKET_CREATED = "support.ticket.created"
EVENT_TICKET_REPEATED = "support.ticket.repeated"
EVENT_TICKET_CLOSED = "support.ticket.closed"
EVENT_TICKET_REOPENED = "support.ticket.reopened"
EVENT_TICKET_ASSIGNED = "support.ticket.assigned"
EVENT_TICKET_MODIFIED = "support.ticket.modified"        # priority/category/queue changed while being worked
EVENT_TICKET_NOTE = "support.ticket.note_added"
EVENT_TICKET_ESCALATED = "support.ticket.escalated"
EVENT_TICKET_BREACHED = "support.ticket.sla_breached"    # the resolution deadline passed while still open
# Asks the communication service to tell the requester, on the channel the request came in on.
EVENT_CUSTOMER_UPDATE = "support.ticket.customer_update"
# Asks the communication service to also create a task / escalation / schedule item for a ticket.
EVENT_OUTCOME_REQUESTED = "support.ticket.outcome_requested"

# Domain events published by the source services and mapped to tickets by the support rule table.
EVENT_EMAIL_RECEIVED = "email.received"          # published by communication/mail_state.py
EVENT_EMAIL_SEND_FAILED = "email.send_failed"
EVENT_EMAIL_DELIVERY_FAILED = "email.delivery_failed"
EVENT_AGENT_RUN_FAILED = "agents.run.failed"
EVENT_AGENT_NEEDS_HUMAN = "agents.task.needs_human"
EVENT_CALL_MISSED = "callcenter.call.missed"
EVENT_CALLBACK_REQUESTED = "callcenter.callback.requested"
EVENT_PAYMENT_FAILED = "finance.payment.failed"
EVENT_RECONCILIATION_EXCEPTION = "finance.reconciliation.exception"
EVENT_SYSTEM_ERROR = "system.error.raised"
EVENT_JOB_FAILED = "system.job.failed"


async def request_ticket(
    session,
    tenant_id: uuid.UUID | str,
    *,
    source: str,
    title: str,
    description: str = "",
    category: Optional[str] = None,
    priority: Optional[str] = None,
    dedupe_key: str,
    ref: Optional[tuple[str, Any]] = None,
    link: Optional[str] = None,
    customer_id: Optional[uuid.UUID | str] = None,
    context: Optional[dict] = None,
) -> uuid.UUID:
    """Ask the support service for a ticket. Repeats with the same `dedupe_key` while the ticket is
    open add a comment and bump its occurrence counter instead of creating another ticket."""
    payload = {
        "source": source, "title": title, "description": description, "category": category,
        "priority": priority, "dedupe_key": dedupe_key, "link": link,
        "ref_type": ref[0] if ref else None, "ref_id": str(ref[1]) if ref else None,
        "customer_id": str(customer_id) if customer_id else None, "context": context or {},
    }
    return await publish(session, tenant_id, EVENT_TICKET_REQUESTED, payload, source=source[:60],
                         subject=ref)


async def publish_standalone(tenant_id, event_type: str, payload: dict, *, source: str,
                             subject: Optional[tuple[str, Any]] = None, idempotency_key: Optional[str] = None) -> bool:
    """Publish from a code path that has no open async session (e.g. a sync-session service finishing a
    failed charge). Opens its own transaction. Never raises; returns whether the event was recorded."""
    import logging
    from services.common.db import session_scope
    try:
        async with session_scope() as session:
            await publish(session, tenant_id, event_type, payload, source=source[:60], subject=subject,
                          idempotency_key=idempotency_key)
        return True
    except Exception as exc:  # noqa: BLE001
        logging.getLogger("omnidome.ticket_events").warning("could not publish %s: %s", event_type, type(exc).__name__)
        return False
