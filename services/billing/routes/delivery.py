"""POST /delivery/webhook-event: the Communication service reports provider delivery facts here.

Authorised with the shared INTERNAL_SERVICE_KEY (x-internal-key, constant-time compare) -- NOT a user
session -- so the path is public to the entitlement middleware (main.py PUBLIC paths) and checks itself.

AgentMail event -> body.event_type (see delivery.AGENTMAIL_EVENT_MAP):
    message.delivered  -> delivered      message.bounced  -> bounced      message.complained -> complained
    message.rejected   -> rejected       message.received (reply to our mail) -> replied
    (opened is accepted for providers that report it)
``message_id`` is the id Communication returned from /api/v1/mail/send (stored on our ``sent`` row).
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request

from services.billing import delivery
from services.billing.access import internal_key_ok
from services.billing.schemas_invoicing import DeliveryWebhookEvent

logger = logging.getLogger("billing.delivery.webhook")

router = APIRouter(tags=["Document delivery"])

PUBLIC_PATHS = {"/delivery/webhook-event"}


@router.post("/delivery/webhook-event")
async def webhook_event(body: DeliveryWebhookEvent, request: Request):
    if not internal_key_ok(request):
        raise HTTPException(status_code=403, detail="internal service key required")
    result = delivery.record_provider_event(body.tenant_id, body.message_id, body.event_type, body.detail)
    if result["recorded"] and body.event_type in ("bounced", "complained"):
        reason = "bounce" if body.event_type == "bounced" else "complaint"
        d = body.detail or {}
        named = [d["recipient"]] if isinstance(d.get("recipient"), str) else \
            [a for a in (d.get("recipients") or []) if isinstance(a, str)]
        # Only suppress addresses the provider named; with none named, only when the mail had ONE recipient.
        targets = named or (result["recipients"] if len(result["recipients"]) == 1 else [])
        for address in targets:
            await delivery.add_suppression_best_effort(body.tenant_id, address, reason)
    return {"status": "accepted" if result["matched"] else "ignored", "matched": result["matched"],
            "recorded": result["recorded"]}
