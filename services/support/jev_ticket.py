"""Jev routing and review for tickets: what the support service does with Jev's opinion.

Jev itself is reached through the orchestrator (agent_orchestrator/jev_ticket.py, which holds the key and the
data-egress switches). Support sends an already-redacted ticket and gets back proposals with probabilities.

Per-tenant mode (`ticket_settings.jev_routing_mode`):

    off      Jev is never asked.
    suggest  (default) Jev's proposals are stored and shown on the ticket; a person clicks Apply.
    auto     a proposal with probability >= APPLY_AT is applied by itself, logged as an event by "jev";
             anything between SUGGEST_AT and APPLY_AT is shown as a suggestion; below SUGGEST_AT is ignored.

Jev can route (queue, category, priority, outcome, assignee), review a ticket at close ("was it properly
resolved?") and judge whether a ticket that sat too long in its stage should be escalated. It never closes,
deletes or reopens anything, never sends anything to the requester, and every decision is a row in
`ticket_jev_decisions` plus an event on the ticket's timeline.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, text

from services.common import ticket_events as E
from services.common.db import session_scope
from services.common.event_bus import notify, publish
from services.support import custom_rules, internal_client, kpi, lifecycle, notify as support_notify, ticket_rules, ticketing
from services.support.database import Ticket

logger = logging.getLogger("support.jev")

APPLY_AT = float(os.getenv("JEV_TICKET_APPLY_AT", "0.90"))
SUGGEST_AT = float(os.getenv("JEV_TRIAGE_MIN_CONFIDENCE", "0.60"))
REVIEW_FLAG_BELOW = float(os.getenv("JEV_TICKET_REVIEW_FLAG_BELOW", "0.40"))
STAGE_RECHECK_HOURS = 6
STAGE_CHECKS_PER_TENANT_PER_CYCLE = 10
ROUTABLE_FIELDS = ("queue", "category", "priority", "outcome", "assignee")

_ALLOWED = {"queue": set(ticket_rules.QUEUES), "category": set(ticket_rules.CATEGORIES),
            "priority": set(ticket_rules.PRIORITIES), "outcome": set(custom_rules.OUTCOMES)}


_background: set = set()


def schedule_review(tenant_id: uuid.UUID, ticket_id: uuid.UUID, delay: float = 3.0) -> None:
    """Review a just-closed ticket in the background, after the request that closed it has committed."""
    async def run() -> None:
        await asyncio.sleep(delay)
        try:
            await review_closed(tenant_id, ticket_id)
        except Exception:  # noqa: BLE001 - a review is advisory
            logger.warning("Jev close review failed for ticket %s", ticket_id, exc_info=True)
    task = asyncio.create_task(run())
    _background.add(task)
    task.add_done_callback(_background.discard)


# ── pure decision logic ─────────────────────────────────────────────────────

def decide(proposal: dict, confidence: dict, mode: str, current: dict, candidates: Optional[set] = None) -> dict:
    """Split Jev's routing proposal into what to apply now, what to show as a suggestion, and what to drop.

    `current` holds the ticket's present queue/category/priority/outcome/assignee; a proposal equal to the
    present value is not a change. Values outside the allowed lists (or an assignee who was not offered) are
    dropped, whatever the probability."""
    out = {"apply": {}, "suggest": {}, "ignored": {}}
    if mode not in ("suggest", "auto"):
        return out
    for key in ROUTABLE_FIELDS:
        if key not in proposal:
            continue
        value, conf = str(proposal[key]), float(confidence.get(key, 0.0))
        if key == "assignee":
            valid = candidates is not None and value in candidates
        else:
            value = value.upper() if key in ("category", "priority") else value.lower()
            valid = value in _ALLOWED[key]
        if not valid or str(current.get(key) or "") == value:
            continue
        if mode == "auto" and conf >= APPLY_AT:
            out["apply"][key] = value
        elif conf >= SUGGEST_AT:
            out["suggest"][key] = value
        else:
            out["ignored"][key] = value
    return out


def review_flagged(resolved_properly: float, resolution_specific: float) -> bool:
    return min(resolved_properly, resolution_specific) < REVIEW_FLAG_BELOW


def stage_disposition(should_escalate: float, mode: str) -> str:
    """apply | suggest | ignore for an escalation judgement."""
    if mode == "off":
        return "ignore"
    if mode == "auto" and should_escalate >= APPLY_AT:
        return "apply"
    return "suggest" if should_escalate >= SUGGEST_AT else "ignore"


# ── Jev through the orchestrator ────────────────────────────────────────────

async def _ask(tenant_id, path: str, body: dict) -> Optional[dict]:
    """Call the orchestrator's Jev ticket endpoint. None when it cannot be reached (never raises)."""
    return await internal_client.post_orchestrator(tenant_id, f"/api/jev/tickets/{path}", body, timeout=40.0)


def _payload(t: Ticket, resolution: Optional[str] = None) -> dict:
    return {"ref": f"T-{t.ticket_no}" if t.ticket_no else None, "subject": (t.subject or "")[:300],
            "description": (t.description or "")[:2500] or None, "resolution": (resolution or t.resolution_notes or "")[:2500] or None,
            "source": t.source, "category": t.category, "priority": t.priority, "queue": t.queue, "status": t.status,
            "event_type": t.event_type, "occurrence_count": t.occurrence_count}


async def _candidates(db, tenant_id) -> list[dict]:
    """Members who have worked tickets in the last 90 days, as opaque ids with workload numbers."""
    rows = (await db.execute(text("""
        SELECT u.id::text AS id,
               count(*) FILTER (WHERE t.status NOT IN ('RESOLVED', 'CLOSED')) AS open,
               count(*) FILTER (WHERE t.resolved_at > now() - interval '30 days') AS resolved_30d
          FROM tickets t JOIN users u ON u.id = t.assigned_to AND u.tenant_id = t.tenant_id AND COALESCE(u.is_active, true)
         WHERE t.tenant_id = :t AND t.assigned_to IS NOT NULL AND t.created_at > now() - interval '90 days'
         GROUP BY u.id ORDER BY resolved_30d DESC, open ASC LIMIT 25"""), {"t": str(tenant_id)})).mappings().all()
    people = [dict(r) | {"top_categories": []} for r in rows]
    if people:
        cats = (await db.execute(text("""
            SELECT id, category FROM (
                SELECT assigned_to::text AS id, category,
                       row_number() OVER (PARTITION BY assigned_to ORDER BY count(*) DESC, category) AS rn
                  FROM tickets WHERE tenant_id = :t AND category IS NOT NULL AND created_at > now() - interval '90 days'
                       AND assigned_to = ANY(CAST(:ids AS uuid[])) GROUP BY assigned_to, category) x WHERE rn <= 3"""),
            {"t": str(tenant_id), "ids": [p["id"] for p in people]})).all()
        by_id = {p["id"]: p for p in people}
        for pid, cat in cats:
            by_id[pid]["top_categories"].append(cat)
    return people


# ── recording ───────────────────────────────────────────────────────────────

async def _save_decision(db, tenant_id, ticket_id, stage: str, proposal: dict, confidence: dict, disposition: str,
                         reason: str, evaluated: bool, decided_by=None) -> uuid.UUID:
    decision_id = uuid.uuid4()
    await db.execute(text("""
        INSERT INTO ticket_jev_decisions (id, tenant_id, ticket_id, stage, proposal, confidence, disposition, reason,
                                          evaluated_by_jev, decided_by, decided_at)
        VALUES (:id, :t, :ticket, :stage, CAST(:proposal AS jsonb), CAST(:confidence AS jsonb), :disposition, :reason,
                :evaluated, :by, CASE WHEN CAST(:decided AS boolean) THEN now() ELSE NULL END)"""),
        {"id": decision_id, "t": str(tenant_id), "ticket": ticket_id, "stage": stage, "proposal": json.dumps(proposal),
         "confidence": json.dumps(confidence), "disposition": disposition, "reason": reason[:400], "evaluated": evaluated,
         "by": decided_by, "decided": disposition in ("applied", "dismissed")})
    return decision_id


async def apply_fields(db, ticket: Ticket, fields: dict, *, actor_id=None, actor_type: str = "jev") -> list[str]:
    """Apply routing fields to a locked ORM ticket and log each as a lifecycle event. Returns what changed."""
    changed: list[str] = []
    note = "Routed by Jev." if actor_type == "jev" else "Jev's suggestion applied."
    if "priority" in fields and fields["priority"] != ticket.priority:
        old = ticket.priority
        ticket.priority = fields["priority"]
        ticket.sla_due_at = ticketing.sla_due(ticket.priority, ticket.created_at)
        await lifecycle.record(db, ticket, "modified", actor_id=actor_id, actor_type=actor_type, from_value=old,
                               to_value=ticket.priority, note=note, data={"field": "priority"})
        changed.append("priority")
    if "category" in fields and fields["category"] != ticket.category:
        old = ticket.category
        ticket.category = fields["category"]
        await lifecycle.record(db, ticket, "modified", actor_id=actor_id, actor_type=actor_type, from_value=old,
                               to_value=ticket.category, note=note, data={"field": "category"})
        changed.append("category")
    if "queue" in fields and fields["queue"] != ticket.queue:
        old = ticket.queue
        ticket.queue = fields["queue"]
        await lifecycle.record(db, ticket, "transferred", actor_id=actor_id, actor_type=actor_type, from_value=old,
                               to_value=ticket.queue, note=note, data={"field": "queue"})
        changed.append("queue")
    if "assignee" in fields and str(ticket.assigned_to or "") != fields["assignee"]:
        old = ticket.assigned_to
        ticket.assigned_to = uuid.UUID(fields["assignee"])
        if ticket.status == "OPEN":
            ticket.status = "IN_PROGRESS"
        await lifecycle.record(db, ticket, "reassigned" if old else "assigned", actor_id=actor_id, actor_type=actor_type,
                               from_value=str(old) if old else None, to_value=fields["assignee"], note=note)
        changed.append("assignee")
    if "outcome" in fields and fields["outcome"] != "ticket":
        await publish(db, ticket.tenant_id, E.EVENT_OUTCOME_REQUESTED,
                      {"ticket_id": str(ticket.id), "outcome": fields["outcome"], "title": ticket.subject,
                       "description": (ticket.description or "")[:1000], "priority": ticket.priority, "queue": ticket.queue,
                       "category": ticket.category, "assigned_to": str(ticket.assigned_to) if ticket.assigned_to else None},
                      source="support", subject=("ticket", ticket.id),
                      idempotency_key=f"ticket-outcome:{ticket.id}:{fields['outcome']}")
        changed.append("outcome")
    return changed


async def escalate(db, ticket: Ticket, *, actor_id=None, actor_type: str = "jev", note: str = "") -> bool:
    """Move an open ticket to ESCALATED (idempotent) and log it."""
    if ticket.status in ticketing.CLOSED_STATUSES or ticket.status == "ESCALATED":
        return False
    old = ticket.status
    ticket.status = "ESCALATED"
    await ticketing.add_timeline(db, ticket.id, "status", f"Escalated{': ' + note if note else ''} (was {old.replace('_', ' ').lower()}).",
                                 author_type="agent" if actor_type != "jev" else "system", author_id=actor_id,
                                 data={"from": old, "to": "ESCALATED"})
    await lifecycle.record(db, ticket, "escalated", actor_id=actor_id, actor_type=actor_type, from_value=old,
                           to_value="ESCALATED", note=note or None)
    try:
        async with db.begin_nested():
            await publish(db, ticket.tenant_id, E.EVENT_TICKET_ESCALATED,
                          {"ticket_id": str(ticket.id), "status": ticket.status, "priority": ticket.priority,
                           "queue": ticket.queue, "by": actor_type}, source="support", subject=("ticket", ticket.id))
    except Exception:  # noqa: BLE001
        logger.warning("could not publish escalation for ticket %s", ticket.id)
    return True


# ── routing ─────────────────────────────────────────────────────────────────

async def route_ticket(tenant_id: uuid.UUID, ticket_id: uuid.UUID, *, force: bool = False,
                       actor_id: Optional[uuid.UUID] = None) -> dict:
    """Ask Jev to route a ticket and apply/suggest/ignore the answer per the tenant's mode.
    `force` (a person pressed "Ask Jev") runs even when the mode is off and always stores a suggestion."""
    async with session_scope() as db:
        mode = (await support_notify.load_settings(db, tenant_id))["jev_routing_mode"]
        if mode == "off" and not force:
            return {"status": "off"}
        ticket = (await db.execute(select(Ticket).where(Ticket.id == ticket_id, Ticket.tenant_id == tenant_id))).scalar_one_or_none()
        if ticket is None or ticket.status in ticketing.CLOSED_STATUSES:
            return {"status": "skipped"}
        body = {"ticket": _payload(ticket), "candidates": await _candidates(db, tenant_id)}
    answer = await _ask(tenant_id, "route", body)
    if not answer or not answer.get("evaluated_by_jev"):
        reason = (answer or {}).get("reason") or "The orchestrator could not be reached"
        logger.info("Jev did not route ticket %s: %s", ticket_id, reason)
        return {"status": "unavailable", "reason": reason}
    mode_used = "suggest" if (force and mode == "off") else mode
    async with session_scope() as db:
        ticket = (await db.execute(select(Ticket).where(Ticket.id == ticket_id, Ticket.tenant_id == tenant_id)
                                   .with_for_update())).scalar_one_or_none()
        if ticket is None or ticket.status in ticketing.CLOSED_STATUSES:
            return {"status": "skipped"}
        offered = {c["id"] for c in body["candidates"]}
        current = {"queue": ticket.queue, "category": ticket.category, "priority": ticket.priority,
                   "outcome": "ticket", "assignee": str(ticket.assigned_to) if ticket.assigned_to else None}
        verdict = decide(answer.get("proposal") or {}, answer.get("confidence") or {}, mode_used, current, offered)
        applied = await apply_fields(db, ticket, verdict["apply"]) if verdict["apply"] else []
        proposal, confidence = answer.get("proposal") or {}, answer.get("confidence") or {}
        if applied:
            await lifecycle.insert_event(db, tenant_id, ticket.id, "jev_applied", actor_type="jev",
                                         to_value=", ".join(applied), data={"fields": verdict["apply"], "confidence": confidence})
        decision_id = None
        if verdict["suggest"] or applied:
            disposition = "applied" if applied and not verdict["suggest"] else "suggested"
            decision_id = await _save_decision(db, tenant_id, ticket.id, "route",
                                               {**verdict["apply"], **verdict["suggest"]}, confidence, disposition,
                                               answer.get("reason") or "", True)
            if verdict["suggest"]:
                await lifecycle.insert_event(db, tenant_id, ticket.id, "jev_suggested", actor_type="jev",
                                             to_value=", ".join(verdict["suggest"]),
                                             data={"fields": verdict["suggest"], "confidence": confidence, "decision_id": str(decision_id)})
        elif proposal:
            await _save_decision(db, tenant_id, ticket.id, "route", proposal, confidence, "ignored",
                                 "Nothing differed from the current routing, or confidence was too low", True)
    return {"status": "routed", "applied": verdict["apply"], "suggested": verdict["suggest"],
            "decision_id": str(decision_id) if decision_id else None}


async def apply_suggestion(db, tenant_id: uuid.UUID, ticket: Ticket, decision_id: uuid.UUID, user_id: uuid.UUID) -> list[str]:
    """A person accepted a stored suggestion: apply it as that person."""
    row = (await db.execute(text("""
        SELECT proposal, disposition FROM ticket_jev_decisions
         WHERE id = :id AND tenant_id = :t AND ticket_id = :ticket FOR UPDATE"""),
        {"id": decision_id, "t": str(tenant_id), "ticket": ticket.id})).mappings().first()
    if row is None:
        raise LookupError("Suggestion not found")
    if row["disposition"] != "suggested":
        raise ValueError("This suggestion was already decided")
    proposal = row["proposal"] or {}
    if proposal.get("status") == "ESCALATED":
        changed = ["status"] if await escalate(db, ticket, actor_id=user_id, actor_type="agent", note="Jev's suggestion accepted.") else []
    else:
        if "assignee" in proposal:
            ok = (await db.execute(text("SELECT 1 FROM users WHERE id = :u AND tenant_id = :t AND COALESCE(is_active, true)"),
                                   {"u": proposal["assignee"], "t": str(tenant_id)})).first()
            if ok is None:
                proposal = {k: v for k, v in proposal.items() if k != "assignee"}
        fields = {k: v for k, v in proposal.items() if k in ROUTABLE_FIELDS and
                  (k == "assignee" or str(v) in _ALLOWED[k] or str(v).upper() in _ALLOWED[k] or str(v).lower() in _ALLOWED[k])}
        changed = await apply_fields(db, ticket, fields, actor_id=user_id, actor_type="agent")
    await db.execute(text("UPDATE ticket_jev_decisions SET disposition = 'applied', decided_by = :u, decided_at = now() WHERE id = :id"),
                     {"u": user_id, "id": decision_id})
    return changed


async def dismiss_suggestion(db, tenant_id: uuid.UUID, ticket_id: uuid.UUID, decision_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    res = await db.execute(text("""
        UPDATE ticket_jev_decisions SET disposition = 'dismissed', decided_by = :u, decided_at = now()
         WHERE id = :id AND tenant_id = :t AND ticket_id = :ticket AND disposition = 'suggested' RETURNING id"""),
        {"u": user_id, "id": decision_id, "t": str(tenant_id), "ticket": ticket_id})
    return res.first() is not None


# ── review at close ─────────────────────────────────────────────────────────

async def review_closed(tenant_id: uuid.UUID, ticket_id: uuid.UUID) -> dict:
    """Ask Jev whether a just-closed ticket was properly resolved; flag it for a person when it was not."""
    async with session_scope() as db:
        if not (await support_notify.load_settings(db, tenant_id))["jev_review_on_close"]:
            return {"status": "off"}
        ticket = (await db.execute(select(Ticket).where(Ticket.id == ticket_id, Ticket.tenant_id == tenant_id))).scalar_one_or_none()
        if ticket is None or ticket.status not in ticketing.CLOSED_STATUSES or not (ticket.resolution_notes or "").strip():
            return {"status": "skipped", "reason": "No resolution note to review"}
        body = {"ticket": _payload(ticket)}
    answer = await _ask(tenant_id, "review", body)
    if not answer or not answer.get("evaluated_by_jev"):
        return {"status": "unavailable", "reason": (answer or {}).get("reason") or "The orchestrator could not be reached"}
    proper, specific = float(answer.get("resolved_properly", 0.0)), float(answer.get("resolution_specific", 0.0))
    flagged = review_flagged(proper, specific)
    confidence = {"resolved_properly": proper, "resolution_specific": specific}
    async with session_scope() as db:
        ticket = (await db.execute(select(Ticket).where(Ticket.id == ticket_id, Ticket.tenant_id == tenant_id))).scalar_one_or_none()
        if ticket is None:
            return {"status": "skipped"}
        reason = ("The resolution may not fully address the problem or is too vague to be useful later."
                  if flagged else "The resolution addresses the problem.")
        await _save_decision(db, tenant_id, ticket.id, "review", {"flagged": flagged}, confidence,
                             "flagged" if flagged else "passed", reason, True)
        await lifecycle.insert_event(db, tenant_id, ticket.id, "jev_review", actor_type="jev",
                                     to_value="flagged" if flagged else "passed", note=reason, data=confidence)
        if flagged:
            ref = f"T-{ticket.ticket_no}" if ticket.ticket_no else "A ticket"
            await notify(db, tenant_id, f"{ref} may not be properly resolved", body=ticket.subject[:200], category="support",
                         severity="warning", link=f"/dashboard?section=service&ticket={ticket.id}", source="support",
                         subject=("ticket", ticket.id))
    return {"status": "flagged" if flagged else "passed", **confidence}


# ── stage checks (called by the watcher) ────────────────────────────────────

async def check_stage(tenant_id: uuid.UUID, ticket_id: uuid.UUID, mode: str) -> str:
    """Ask Jev whether a late or idle ticket needs a supervisor now. Returns the disposition taken."""
    async with session_scope() as db:
        t = (await db.execute(select(Ticket).where(Ticket.id == ticket_id, Ticket.tenant_id == tenant_id))).scalar_one_or_none()
        if t is None or t.status in ticketing.CLOSED_STATUSES or t.status == "ESCALATED":
            return "skipped"
        recent = (await db.execute(text("""
            SELECT 1 FROM ticket_jev_decisions WHERE ticket_id = :id AND stage = 'stage'
               AND created_at > now() - make_interval(hours => :h) LIMIT 1"""), {"id": ticket_id, "h": STAGE_RECHECK_HOURS})).first()
        if recent:
            return "skipped"
        now = datetime.now(timezone.utc)
        due = kpi._aware(t.sla_due_at)
        timing = {"hours_open": kpi.hours_between(t.created_at, now) or 0.0,
                  "hours_since_activity": kpi.hours_between(t.last_activity_at or t.updated_at or t.created_at, now) or 0.0,
                  "hours_past_deadline": round((now - due).total_seconds() / 3600.0, 2) if due and now > due else 0.0,
                  "times_reassigned": max(0, (t.assignment_count or 0) - 1), "escalated_already": False}
        body = {"ticket": _payload(t), "timing": timing}
    answer = await _ask(tenant_id, "stage", body)
    if not answer or not answer.get("evaluated_by_jev"):
        return "unavailable"
    p = float(answer.get("should_escalate", 0.0))
    action = stage_disposition(p, mode)
    async with session_scope() as db:
        t = (await db.execute(select(Ticket).where(Ticket.id == ticket_id, Ticket.tenant_id == tenant_id).with_for_update())).scalar_one_or_none()
        if t is None:
            return "skipped"
        confidence = {"should_escalate": p}
        reason = f"Open {timing['hours_open']}h, idle {timing['hours_since_activity']}h, {timing['hours_past_deadline']}h past its deadline."
        if action == "apply" and await escalate(db, t, actor_type="jev", note=reason):
            await _save_decision(db, tenant_id, t.id, "stage", {"status": "ESCALATED"}, confidence, "applied", reason, True)
            await lifecycle.insert_event(db, tenant_id, t.id, "jev_applied", actor_type="jev", to_value="ESCALATED", data=confidence)
        elif action == "suggest":
            decision_id = await _save_decision(db, tenant_id, t.id, "stage", {"status": "ESCALATED"}, confidence, "suggested", reason, True)
            await lifecycle.insert_event(db, tenant_id, t.id, "jev_suggested", actor_type="jev", to_value="ESCALATED", note=reason,
                                         data={**confidence, "decision_id": str(decision_id)})
        else:
            await _save_decision(db, tenant_id, t.id, "stage", {"status": "ESCALATED"}, confidence, "ignored", reason, True)
    return action
