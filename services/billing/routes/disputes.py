"""Paystack disputes (chargebacks): record the charge.dispute.* webhooks and list them for the tenant.

This is step one of dispute handling: nothing is lost silently any more. Each event upserts a billing_disputes
row matched to the original charge (so tenant + invoice are known), open disputes freeze dunning/autopay for
the invoice, and platform ops is alerted because the evidence deadline is short and an unanswered dispute is
lost automatically. The evidence workflow (POST /dispute/{id}/evidence, uploads, accept/decline) and the
finance posting (hold / chargeback expense / receivable from the tenant) come with the reconciliation step.
Commission on a charge that is later lost is NOT refunded to the tenant (the processing happened).
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from services.billing.access import require_tier
from services.billing.database import get_session
from services.billing.models import BillingWebhookEvent, PaystackInitialization
from services.billing.models_gateway import GatewayCharge, GatewayDispute
from services.billing.routes import gateway as gw
from services.common.auth import AuthContext, get_auth_context

logger = logging.getLogger("billing.disputes")

router = APIRouter(prefix="/disputes", tags=["Disputes"])

CLOSED = ("resolved", "archived")


def _dt(value) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def event_key(event: str, data: dict) -> str:
    # remind events repeat for the same dispute, so the status/updated time is part of the key
    return f"{event}:{data.get('id')}:{data.get('status')}:{data.get('updatedAt') or data.get('updated_at') or ''}"[:200]


async def handle_event(event: str, data: dict) -> str:
    """charge.dispute.create | .remind | .resolve. Returns 'accepted' | 'duplicate' | 'ignored'."""
    dispute_id = str(data.get("id") or "")
    if not dispute_id:
        logger.warning("dispute webhook without id (%s)", event)
        return "ignored"
    txn = data.get("transaction") or {}
    reference = txn.get("reference") or data.get("transaction_reference")
    alert = None
    with get_session() as session:
        try:
            with session.begin_nested():
                session.add(BillingWebhookEvent(provider="paystack", event_key=event_key(event, data), event_type=event,
                                                reference=reference or None))
                session.flush()
        except IntegrityError:
            return "duplicate"

        tenant_id = invoice_id = customer_id = None
        if reference:
            charge = session.execute(select(GatewayCharge).where(GatewayCharge.reference == reference)).scalar_one_or_none()
            if charge is not None:
                tenant_id, invoice_id = charge.tenant_id, charge.invoice_id
            init = session.execute(select(PaystackInitialization).where(PaystackInitialization.reference == reference)).scalar_one_or_none()
            if init is not None:
                tenant_id, invoice_id, customer_id = init.tenant_id, init.invoice_id, init.customer_id

        row = session.execute(select(GatewayDispute).where(GatewayDispute.paystack_dispute_id == dispute_id)).scalar_one_or_none()
        if row is None:
            row = GatewayDispute(paystack_dispute_id=dispute_id, status="unknown")
            session.add(row)
        row.tenant_id = row.tenant_id or tenant_id
        row.invoice_id = row.invoice_id or invoice_id
        row.customer_id = row.customer_id or customer_id
        row.reference = reference or row.reference
        row.amount_cents = int(data.get("refund_amount") or txn.get("amount") or row.amount_cents or 0)
        row.status = str(data.get("status") or row.status)
        row.category = data.get("category") or row.category
        row.resolution = data.get("resolution") or row.resolution
        row.due_at = _dt(data.get("dueAt") or data.get("due_at")) or row.due_at
        row.last_event = event
        if row.tenant_id is None:
            logger.error("ALERT: Paystack dispute %s on %s matches no charge of ours", dispute_id, reference)
        if event.endswith(".create") or (event.endswith(".remind") and row.status not in CLOSED) or event.endswith(".resolve"):
            alert = (event, dispute_id, reference, row.amount_cents, row.status, row.due_at, row.tenant_id)
        session.flush()
    if alert:
        ev, did, ref, cents, status, due, tenant = alert
        await gw._alert_ops(
            f"Paystack dispute {ev.rsplit('.', 1)[-1]}: R{cents / 100:.2f}",
            f"<p>Dispute <b>{did}</b> on transaction {ref or '(unknown)'} for R{cents / 100:.2f}, status <b>{status}</b>"
            f"{', respond by ' + due.strftime('%Y-%m-%d %H:%M UTC') if due else ''}. Tenant: {tenant or 'unmatched'}.</p>")
    return "accepted"


def public(d: GatewayDispute) -> dict:
    return {"id": str(d.id), "dispute_id": d.paystack_dispute_id, "reference": d.reference,
            "invoice_id": str(d.invoice_id) if d.invoice_id else None, "amount_zar": d.amount_cents / 100,
            "status": d.status, "category": d.category, "resolution": d.resolution,
            "due_at": d.due_at.isoformat() if d.due_at else None, "open": d.status not in CLOSED,
            "updated_at": d.updated_at.isoformat() if d.updated_at else None}


@router.get("", dependencies=[Depends(require_tier("reader"))])
async def list_disputes(ctx: AuthContext = Depends(get_auth_context)):
    with get_session() as session:
        rows = session.execute(select(GatewayDispute).where(GatewayDispute.tenant_id == ctx.tenant_id)
                               .order_by(GatewayDispute.created_at.desc()).limit(200)).scalars().all()
        items = [public(d) for d in rows]
    due = sorted(i["due_at"] for i in items if i["open"] and i["due_at"])
    return {"disputes": items, "open": sum(1 for i in items if i["open"]), "next_due_at": due[0] if due else None}
