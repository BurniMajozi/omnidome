"""Background watcher: notices tickets that ran out of time, and asks Jev whether late ones need a supervisor.

Every WATCH_SECONDS:

1. Breaches. An open ticket past its resolution deadline gets ONE `sla_breached` event on its timeline (the
   UPDATE ... RETURNING claims it atomically, so several workers cannot both log it), a
   `support.ticket.sla_breached` bus event (automations and agents can react) and a bell notification.
   Overdue is otherwise a computed state; nothing is changed on the ticket itself.
2. Stage checks. For tenants whose Jev mode is not "off", the worst late/idle tickets that are not already
   escalated are put to Jev ("does this need a supervisor now?", jev_ticket.check_stage), a few per tenant per
   cycle. Depending on the mode and Jev's confidence the ticket is escalated, an escalation is suggested to a
   person, or nothing happens.

One worker at a time runs a cycle (a transaction-level advisory lock held for its duration).
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid

from sqlalchemy import text

from services.common import ticket_events as E
from services.common.db import session_scope
from services.common.event_bus import notify, publish
from services.support import jev_ticket, kpi, lifecycle, notify as support_notify

logger = logging.getLogger("support.watcher")

WATCH_SECONDS = int(os.getenv("TICKET_WATCH_SECONDS", "300"))
LOCK_KEY = 0x5_0_8_009
BREACH_BATCH = 200
STAGE_LIMIT = 30
# A deadline that passed longer ago than this is logged on the ticket but does not ring the bell or fire automations.
FRESH_BREACH_HOURS = 6


async def log_breaches(db) -> int:
    """Record the first breach of each open ticket's deadline. Returns how many were logged."""
    rows = (await db.execute(text("""
        WITH due AS (
            SELECT id FROM tickets
             WHERE status NOT IN ('RESOLVED', 'CLOSED') AND sla_due_at IS NOT NULL AND sla_due_at < now()
               AND breach_logged_at IS NULL ORDER BY sla_due_at LIMIT :n FOR UPDATE SKIP LOCKED)
        UPDATE tickets t SET breach_logged_at = now(), updated_at = now() FROM due WHERE t.id = due.id
        RETURNING t.id, t.tenant_id, t.ticket_no, t.subject, t.priority, t.queue, t.sla_due_at,
                  (t.sla_due_at > now() - make_interval(hours => :fresh)) AS fresh"""),
        {"n": BREACH_BATCH, "fresh": FRESH_BREACH_HOURS})).mappings().all()
    for r in rows:
        ref = f"T-{r['ticket_no']}" if r["ticket_no"] else "A ticket"
        await lifecycle.insert_event(db, r["tenant_id"], r["id"], "sla_breached", actor_type="system",
                                     note=f"Resolution deadline passed ({r['priority']} priority).",
                                     data={"sla_due_at": r["sla_due_at"].isoformat() if r["sla_due_at"] else None})
        if not r["fresh"]:      # a backlog found on first run: on the timeline, but no bell or automation storm
            continue
        await publish(db, r["tenant_id"], E.EVENT_TICKET_BREACHED,
                      {"ticket_id": str(r["id"]), "ticket_ref": f"T-{r['ticket_no']}" if r["ticket_no"] else None,
                       "priority": r["priority"], "queue": r["queue"], "subject": r["subject"]},
                      source="support", subject=("ticket", r["id"]), idempotency_key=f"ticket-breach:{r['id']}")
        await notify(db, r["tenant_id"], f"{ref} is past its deadline", body=(r["subject"] or "")[:200], category="support",
                     severity="critical" if r["priority"] in ("HIGH", "URGENT") else "warning",
                     link=f"/dashboard?section=service&ticket={r['id']}", source="support", subject=("ticket", r["id"]))
    return len(rows)


async def stage_checks() -> int:
    """Put late tickets to Jev for tenants that allow it. Returns how many Jev calls were made."""
    async with session_scope() as db:
        tenants = [r[0] for r in (await db.execute(text("""
            SELECT DISTINCT tenant_id FROM tickets WHERE status NOT IN ('RESOLVED', 'CLOSED', 'ESCALATED')
               AND ((sla_due_at IS NOT NULL AND sla_due_at < now())
                    OR COALESCE(last_activity_at, updated_at, created_at) < now() - interval '2 hours')"""))).all()]
    calls = 0
    for tenant_id in tenants:
        async with session_scope() as db:
            mode = (await support_notify.load_settings(db, tenant_id))["jev_routing_mode"]
            if mode == "off":
                continue
            late = await kpi.late_tickets(db, tenant_id, STAGE_LIMIT)
        for item in late:
            if item["status"] == "ESCALATED":
                continue
            result = await jev_ticket.check_stage(tenant_id, uuid.UUID(item["id"]), mode)
            if result == "unavailable":
                break                       # Jev is off or down for this deployment: do not hammer it ticket by ticket
            if result != "skipped":
                calls += 1
            if calls >= jev_ticket.STAGE_CHECKS_PER_TENANT_PER_CYCLE:
                break
    return calls


async def run_cycle() -> dict:
    async with session_scope() as leader:
        got = (await leader.execute(text("SELECT pg_try_advisory_xact_lock(:k)"), {"k": LOCK_KEY})).scalar()
        if not got:
            return {"skipped": True}
        async with session_scope() as db:
            breaches = await log_breaches(db)
        calls = await stage_checks()
    return {"breaches": breaches, "jev_calls": calls}


async def run_forever() -> None:
    await asyncio.sleep(30)                 # let the service finish starting
    while True:
        try:
            result = await run_cycle()
            if result.get("breaches") or result.get("jev_calls"):
                logger.info("ticket watcher: %s", result)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - a bad cycle must not end the watcher
            logger.exception("ticket watcher cycle failed")
        await asyncio.sleep(WATCH_SECONDS)
