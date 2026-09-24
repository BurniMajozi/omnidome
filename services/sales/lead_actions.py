"""Lead action side-effects that talk to other services (SPEC-lead-actions.md).

The action endpoints in main.py record the request on the lead's timeline and
publish an event; the sales EventConsumer below does the slow/remote part
(AgentMail, Marketing) with retries, so the endpoint never waits on or loses it.
"""

from __future__ import annotations

import html
import logging
import os
import uuid
from typing import Any

import httpx
from sqlalchemy import select

from services.common import agentmail
from services.common.event_bus import MAX_ATTEMPTS, EventConsumer, notify
from services.sales.database import get_session
from services.sales.lead_service import Actor, full_name, record_activity
from services.sales.models import Lead, LeadActivity

logger = logging.getLogger("sales.lead_actions")

OUTBOUND_QUEUE = "Outbound queue"
AUTOMATION = Actor(name="Sales automation")
SYSTEM_USER_ID = "00000000-0000-0000-0000-000000000000"


# ── Pure helpers ────────────────────────────────────────────────────────────

def email_html(body: str) -> str:
    """Plain text from the compose box → safe HTML (escaped, line breaks kept)."""
    return html.escape(body or "").replace("\n", "<br>")


def lead_audience_member(lead: Any) -> dict:
    """A lead in Marketing's business-audience shape (lib/audiences.ts AudienceBusiness)."""
    return {
        "name": full_name(lead),
        "category": (lead.source or "").replace("_", " ").title() or None,
        "address": lead.address,
        "phone": lead.phone,
        "email": lead.email,
        "website": None,
        "lat": None,
        "lng": None,
    }


def campaign_audience(campaign_id: str, campaign_name: str, members: list[dict]) -> dict:
    """One audience per campaign holding every lead sent to it. Marketing upserts
    on (rules.source, rules.source_id), so re-sending the full list is idempotent."""
    return {
        "name": f"Sales leads · {campaign_name}",
        "description": f"{len(members)} leads sent from Sales to the campaign '{campaign_name}'",
        "member_count": len(members),
        "rules": {
            "type": "businesses",
            "platform": "custom",
            "source": "sales_campaign",
            "source_id": campaign_id,
            "source_name": campaign_name,
            "businesses": members,
        },
    }


# ── Event handlers (at-least-once; idempotent) ──────────────────────────────

async def handle_email_requested(event: dict) -> None:
    p = event["payload"]
    tenant_id = uuid.UUID(event["tenant_id"])
    lead_id = uuid.UUID(p["lead_id"])
    async with get_session() as db:
        already = (await db.execute(
            select(LeadActivity.id).where(
                LeadActivity.lead_id == lead_id, LeadActivity.kind == "email_sent",
                LeadActivity.details["event_id"].astext == event["id"],
            )
        )).first()
    if already:
        return
    try:
        message_id = await agentmail.send_email(p["to"], p["subject"], email_html(p.get("body", "")))
    except Exception as exc:
        if event.get("attempt", 1) >= MAX_ATTEMPTS:
            async with get_session() as db:
                await record_activity(db, tenant_id, lead_id, "email_failed",
                                      f"Email not sent: {p['subject']}",
                                      {"event_id": event["id"], "to": p["to"], "error": str(exc)[:300]}, AUTOMATION)
        raise
    async with get_session() as db:
        await record_activity(db, tenant_id, lead_id, "email_sent", f"Email sent: {p['subject']}",
                              {"event_id": event["id"], "to": p["to"], "message_id": message_id,
                               "subject": p["subject"]}, AUTOMATION)


async def handle_campaign_requested(event: dict) -> None:
    p = event["payload"]
    tenant_id = uuid.UUID(event["tenant_id"])
    campaign_id, campaign_name = p["campaign_id"], p.get("campaign_name") or "Campaign"
    async with get_session() as db:
        leads = (await db.execute(
            select(Lead).distinct().join(LeadActivity, LeadActivity.lead_id == Lead.id).where(
                Lead.tenant_id == tenant_id, LeadActivity.kind == "campaign_requested",
                LeadActivity.details["campaign_id"].astext == campaign_id,
            )
        )).scalars().all()
    body = campaign_audience(campaign_id, campaign_name, [lead_audience_member(lead) for lead in leads])
    base = os.getenv("MARKETING_SERVICE_URL", "http://marketing:8007").rstrip("/")
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(f"{base}/segments", json=body, headers={
            "X-Tenant-Id": str(tenant_id), "X-User-Id": SYSTEM_USER_ID})
    if resp.status_code >= 400:
        raise RuntimeError(f"Marketing {resp.status_code}: {resp.text[:300]}")
    async with get_session() as db:
        await record_activity(
            db, tenant_id, uuid.UUID(p["lead_id"]), "campaign_added",
            f"In Marketing audience '{body['name']}' ({body['member_count']} leads)",
            {"event_id": event["id"], "campaign_id": campaign_id}, AUTOMATION)
        await notify(db, tenant_id, f"{p.get('reference') or 'Lead'} added to {campaign_name}",
                     body=f"Marketing audience '{body['name']}' now has {body['member_count']} leads.",
                     category="marketing", source="sales", subject=("lead", p["lead_id"]))


consumer = EventConsumer("sales", {
    "sales.lead.email_requested": handle_email_requested,
    "sales.lead.campaign_requested": handle_campaign_requested,
})
