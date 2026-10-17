"""Tell the requester what is happening to their ticket, on the channel they used to reach us.

The support service never talks to a mail or messaging provider. It publishes `support.ticket.customer_update`
on the event bus and the communication service (which owns the mailboxes) delivers it. What gets said is
fixed wording filled with a few facts (reference, subject, new status/priority, the public note), never
free-form agent text and never anything internal: private notes, queue names, assignee names and categories
are not included. A tenant can switch notifications off, or any one trigger, at `/tickets/settings`.

Channels with a delivery path: email. Any other input channel (a missed call, an agent task, a system
event) is recorded as "no outbound path" on the timeline so the desk can see the requester was not told.
A ticket with no requester channel at all (opened by hand) has nobody to tell and records nothing.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import text

from services.common import ticket_events as E
from services.common.event_bus import publish
from services.common.redaction import redact_text
from services.support import lifecycle

DELIVERABLE_CHANNELS = frozenset({"email"})
TRIGGERS = ("assigned", "modified", "note", "resolved")
TRIGGER_COLUMN = {"assigned": "notify_on_assigned", "modified": "notify_on_modified", "note": "notify_on_note",
                  "resolved": "notify_on_resolved"}
# One message per trigger per ticket in this window, so a burst of edits is one notification.
THROTTLE_MINUTES = 10

DEFAULT_SETTINGS = {
    "notify_enabled": True, "notify_on_assigned": True, "notify_on_modified": True, "notify_on_note": True,
    "notify_on_resolved": True, "jev_routing_mode": "suggest", "jev_review_on_close": True,
}
JEV_MODES = ("off", "suggest", "auto")

# Where a ticket's source says the requester can be reached. Only email has a return address today.
SOURCE_CHANNEL = {"email": "email", "call_center": "call", "agent_task": "agent", "finance": "finance",
                  "iot": "system", "system_error": "system"}


def channel_for_source(source: Optional[str]) -> Optional[str]:
    return SOURCE_CHANNEL.get((source or "").lower())


async def load_settings(db, tenant_id) -> dict:
    row = (await db.execute(text("""
        SELECT notify_enabled, notify_on_assigned, notify_on_modified, notify_on_note, notify_on_resolved,
               jev_routing_mode, jev_review_on_close FROM ticket_settings WHERE tenant_id = :t"""),
        {"t": str(tenant_id)})).mappings().first()
    return {**DEFAULT_SETTINGS, **(dict(row) if row else {})}


def render(trigger: str, *, ref: str, subject: str, detail: str = "") -> tuple[str, str]:
    """(subject line, plain-text body) for one notification."""
    subject = " ".join((subject or "your request").split())[:120]
    heading = f"Re: {subject} [{ref}]"
    detail = redact_text(detail, 1200) if detail else ""
    if trigger == "assigned":
        body = f"Your request {ref} ({subject}) has been picked up and is now being worked on."
    elif trigger == "modified":
        body = f"Your request {ref} ({subject}) was updated. {detail}".strip()
    elif trigger == "note":
        body = f"There is an update on your request {ref} ({subject}):\n\n{detail}".strip()
    elif trigger == "resolved":
        body = f"Your request {ref} ({subject}) has been resolved." + (f"\n\n{detail}" if detail else "") \
            + "\n\nIf the problem is still there, reply to this message and we will reopen it."
    else:
        raise ValueError(f"unknown notification trigger {trigger!r}")
    return heading, body


async def notify_requester(db, ticket, trigger: str, detail: str = "", *, actor_id=None) -> Optional[str]:
    """Queue one notification for `ticket`'s requester. Returns the delivery state ('queued' or 'no_outbound_path',
    both recorded on the timeline), 'no_channel' when the ticket has no requester to tell (nothing recorded), or
    None when nothing was due (switched off, throttled)."""
    if trigger not in TRIGGERS:
        raise ValueError(f"unknown notification trigger {trigger!r}")
    settings = await load_settings(db, ticket.tenant_id)
    if not settings["notify_enabled"] or not settings[TRIGGER_COLUMN[trigger]]:
        return None
    recent = (await db.execute(text("""
        SELECT 1 FROM ticket_events WHERE ticket_id = :id AND event_type = 'customer_notified'
           AND data->>'trigger' = :trigger AND created_at > now() - make_interval(mins => :mins) LIMIT 1"""),
        {"id": ticket.id, "trigger": trigger, "mins": THROTTLE_MINUTES})).first()
    if recent:
        return None

    ref = f"T-{ticket.ticket_no}" if ticket.ticket_no else str(ticket.id)[:8]
    channel = ticket.reply_channel or channel_for_source(ticket.source)
    if not channel:
        return "no_channel"
    subject_line, body = render(trigger, ref=ref, subject=ticket.subject, detail=detail)
    delivery = "queued" if channel in DELIVERABLE_CHANNELS and ticket.reply_ref else "no_outbound_path"
    event_id = await lifecycle.record(
        db, ticket, "customer_notified", actor_id=actor_id, actor_type="system", channel=channel,
        visibility="public", note=body, data={"trigger": trigger, "delivery": delivery})
    if delivery == "queued":
        await publish(db, ticket.tenant_id, E.EVENT_CUSTOMER_UPDATE,
                      {"ticket_id": str(ticket.id), "ticket_ref": ref, "channel": channel, "reply_ref": ticket.reply_ref,
                       "customer_id": str(ticket.customer_id) if ticket.customer_id else None,
                       "trigger": trigger, "subject": subject_line, "body": body, "event_id": str(event_id)},
                      source="support", subject=("ticket", ticket.id),
                      idempotency_key=f"ticket-notify:{ticket.id}:{event_id}")
    return delivery
