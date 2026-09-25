"""Event-triggered workflows (SPEC-lead-automations.md).

Any service (or the portal/website, through POST /api/events) publishes an
event on the bus. The orchestrator's EventConsumer receives every event and
runs each active workflow of that tenant whose `trigger_event` matches, with
input {"event": {...}} and run trigger "event". The three cards on Sales → AI
Lead Warming are installed as ordinary workflows from LEAD_WARMING_TEMPLATES.

Automations draft customer messages; they never send them. A person reviews the
draft on the lead's timeline and sends it (Send email in the lead menu).
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from services.agent_orchestrator.models import Workflow, WorkflowRun
from services.agent_orchestrator.workflow_engine import run_workflow
from services.common.db import session_scope
from services.common.event_bus import EventConsumer, notify

logger = logging.getLogger(__name__)

SYSTEM_USER = "00000000-0000-0000-0000-000000000000"

_DRAFT_RULES = (
    "Reply with the message text only: no code block, no subject line, no placeholders in brackets. "
    "Plain, friendly South African English, at most 90 words, signed 'The OmniDome team'."
)


def _template(key: str, name: str, trigger_event: str, description: str, lead_body: dict, prompt: str) -> dict:
    return {
        "key": key,
        "name": name,
        "trigger_event": trigger_event,
        "description": description,
        "definition": {
            "nodes": [
                {"id": "trigger", "type": "trigger", "name": name, "config": {"event": trigger_event}},
                {"id": "lead", "type": "http_request", "name": "Find or create the lead and move its stage",
                 "config": {"service": "sales", "method": "POST", "path": "/automation/lead-events",
                            "body": {"event_type": "{{input.event.type}}", "event_id": "{{input.event.id}}",
                                     "contact": "{{input.event.payload.contact}}", **lead_body}}},
                {"id": "draft", "type": "agent_invoke", "name": "OmniAssist drafts the warm-up message",
                 "config": {"agent_type": "assistant", "message": f"{prompt} {_DRAFT_RULES}"}},
                {"id": "save", "type": "http_request", "name": "Save the draft on the lead for review",
                 "config": {"service": "sales", "method": "POST", "path": "/leads/{{steps.lead.body.id}}/notes",
                            "body": {"kind": "ai_draft", "body": "{{steps.draft.content}}"}}},
                {"id": "end", "type": "end", "name": "Done", "config": {}},
            ],
            "edges": [
                {"from": "trigger", "to": "lead"}, {"from": "lead", "to": "draft"},
                {"from": "draft", "to": "save"}, {"from": "save", "to": "end"},
            ],
        },
    }


LEAD_WARMING_TEMPLATES = [
    _template(
        "abandoned_basket", "Abandoned basket → warm-up", "portal.cart.abandoned",
        "Customer left a package in the portal basket for more than 2 hours. Lead moves New → Contacted "
        "and OmniAssist drafts a recovery message with voucher FIBERWARM15 and a free installation waiver.",
        {"source": "PORTAL_WEBSITE", "target_status": "CONTACTED",
         "note": "Left {{input.event.payload.cart_summary}} in the basket"},
        "Write a short recovery message to {{input.event.payload.contact.first_name}}, who left "
        "{{input.event.payload.cart_summary}} in their OmniDome basket without paying. Offer voucher "
        "FIBERWARM15 for 15% off and a free installation waiver, and invite them to complete the order.",
    ),
    _template(
        "quote_request", "Quote request → proposal", "portal.quote.requested",
        "Customer asked for pricing on the website calculator or by email. Lead goes onto the pipeline "
        "board in Proposal (deal at the quoted value) and OmniAssist drafts the quote cover note.",
        {"source": "PORTAL_WEBSITE", "target_stage": "Proposal",
         "value_zar": "{{input.event.payload.quote_total_zar}}",
         "note": "Quote requested: {{input.event.payload.quote_summary}}"},
        "Write a short cover note to {{input.event.payload.contact.first_name}} for the quote they requested "
        "({{input.event.payload.quote_summary}}, R {{input.event.payload.quote_total_zar}} per month). Thank "
        "them, summarise the package in one sentence and offer a follow-up call this week.",
    ),
    _template(
        "registration_inactive", "Registration inactive → check-in", "portal.registration.inactive",
        "User registered on the self-service portal but took no action for more than 24 hours. Lead moves "
        "to Qualified and the concierge drafts a friendly check-in offering an address coverage check.",
        {"source": "PORTAL_WEBSITE", "target_status": "QUALIFIED",
         "note": "Registered {{input.event.payload.registered_at}} with no activity since"},
        "Write a friendly check-in to {{input.event.payload.contact.first_name}}, who registered on the "
        "OmniDome self-service portal but has not done anything yet. Offer to check fibre coverage at "
        "their address and explain it takes one minute.",
    ),
]


# ── Consumer ────────────────────────────────────────────────────────────────

async def handle_event(event: dict) -> None:
    """Run the tenant's active workflows for this event type (once per event)."""
    tenant_id = uuid.UUID(event["tenant_id"])
    async with session_scope() as s:
        workflows = (await s.execute(select(Workflow).where(
            Workflow.tenant_id == tenant_id, Workflow.status == "active",
            Workflow.trigger_event == event["type"]))).scalars().all()
        if not workflows:
            return
        already = set((await s.execute(select(WorkflowRun.workflow_id).where(
            WorkflowRun.tenant_id == tenant_id, WorkflowRun.trigger == "event",
            WorkflowRun.input["event"]["id"].astext == event["id"]))).scalars().all())
        todo = [(w.id, w.name) for w in workflows if w.id not in already]

    for workflow_id, name in todo:
        result = await run_workflow(workflow_id=workflow_id, tenant_id=str(tenant_id), user_id=SYSTEM_USER,
                                    input_data={"event": event}, trigger="event")
        logger.info("event %s ran workflow %s: %s", event["type"], name, result.get("status"))
        if result.get("status") == "failed":
            async with session_scope() as s:
                await notify(s, tenant_id, f"Automation '{name}' stopped",
                             body=str(result.get("error") or "A step failed")[:500], category="automation",
                             severity="warning", source="orchestrator", subject=("workflow_run", result.get("run_id")))


consumer = EventConsumer("orchestrator", {"*": handle_event})


# ── Lead warming templates: install + status ────────────────────────────────

async def install_lead_warming(tenant_id: uuid.UUID) -> None:
    """Create any missing template workflow (idempotent by name), active."""
    async with session_scope() as s:
        existing = set((await s.execute(select(Workflow.name).where(
            Workflow.tenant_id == tenant_id,
            Workflow.name.in_([t["name"] for t in LEAD_WARMING_TEMPLATES])))).scalars().all())
        for t in LEAD_WARMING_TEMPLATES:
            if t["name"] not in existing:
                s.add(Workflow(tenant_id=tenant_id, name=t["name"], description=t["description"],
                               definition=t["definition"], status="active", trigger_event=t["trigger_event"]))


async def lead_warming_status(tenant_id: uuid.UUID) -> list[dict]:
    since = datetime.now(timezone.utc) - timedelta(days=7)
    out = []
    async with session_scope() as s:
        for t in LEAD_WARMING_TEMPLATES:
            wf = (await s.execute(select(Workflow).where(
                Workflow.tenant_id == tenant_id, Workflow.name == t["name"]))).scalars().first()
            item = {"key": t["key"], "name": t["name"], "trigger_event": t["trigger_event"],
                    "description": t["description"], "installed": wf is not None,
                    "workflow_id": str(wf.id) if wf else None, "status": wf.status if wf else None,
                    "runs_7d": 0, "succeeded_7d": 0, "last_run": None}
            if wf:
                counts = (await s.execute(select(WorkflowRun.status, func.count()).where(
                    WorkflowRun.workflow_id == wf.id, WorkflowRun.started_at >= since)
                    .group_by(WorkflowRun.status))).all()
                item["runs_7d"] = sum(n for _, n in counts)
                item["succeeded_7d"] = sum(n for st, n in counts if st == "succeeded")
                last = (await s.execute(select(WorkflowRun).where(WorkflowRun.workflow_id == wf.id)
                                        .order_by(WorkflowRun.started_at.desc()).limit(1))).scalars().first()
                if last:
                    lead_id = (((last.output or {}).get("lead") or {}).get("body") or {}).get("id")
                    item["last_run"] = {"id": str(last.id), "status": last.status, "error": last.error,
                                        "started_at": last.started_at.isoformat() if last.started_at else None,
                                        "lead_id": lead_id}
            out.append(item)
    return out
