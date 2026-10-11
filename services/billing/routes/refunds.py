"""Refunds: pay back money we hold for a customer (billing_customer_credits) through Paystack.

Source of a refund is always a customer credit: a credit note on a paid invoice (`refund_required`), an
overpayment, or an unallocated payment. To refund a paid invoice, issue the credit note first (existing flow);
the clerk then refunds the resulting credit here. That keeps invoice, ledger and refund in step and makes it
impossible to refund more than we hold.

Paystack side: POST /refund {transaction, amount} against the original charge (never more than that charge's
unrefunded amount), then `refund.pending/processing/processed/failed` webhooks move the state. EFT payments
have no Paystack transaction, so those are recorded as `manual` refunds (the clerk paid the customer from the
tenant's own bank) with a bank reference.

Money flow note: Paystack pays the refund out of OmniDome's balance, but the tenant was already settled. A
processed Paystack refund therefore also opens a billing_gateway_liabilities row (the tenant owes it back);
manual refunds do not (the tenant paid them itself). OmniDome's commission is kept on refunds.
"""

import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from services.billing import finance_posting as fp
from services.billing.access import require_tier
from services.billing.database import get_session
from services.billing.models import BillingWebhookEvent, CustomerCredit, Payment
from services.billing.models_gateway import GatewayLiability, GatewayRefund
from services.billing.routes.paystack_recurring import _paystack, _secret
from services.common.auth import AuthContext, get_auth_context

logger = logging.getLogger("billing.refunds")

router = APIRouter(prefix="/refunds", tags=["Refunds"])

REFUNDABLE_KINDS = ("refund_required", "overpayment", "unallocated_payment")
ACTIVE = ("pending", "processing", "processed")      # statuses that count against the credit / the charge
STATUS_MAP = {"pending": "pending", "processing": "processing", "processed": "processed", "failed": "failed",
              "needs-attention": "failed", "reversed": "failed"}


def _cents(value) -> int:
    return int((Decimal(str(value)) * 100).to_integral_value())


def committed_cents(session, *, credit_id=None, reference=None) -> int:
    q = select(func.coalesce(func.sum(GatewayRefund.amount_cents), 0)).where(GatewayRefund.status.in_(ACTIVE))
    q = q.where(GatewayRefund.credit_id == credit_id) if credit_id is not None else q.where(GatewayRefund.transaction_reference == reference)
    return int(session.execute(q).scalar_one())


def candidate_charges(session, credit: CustomerCredit) -> list[tuple[str, int]]:
    """[(paystack_reference, refundable_cents)] for the card charges this credit's money came from, newest first."""
    refs: list[tuple[str, int]] = []
    if credit.kind in ("overpayment", "unallocated_payment") and credit.reference:
        # these credits are created straight from a Paystack charge, so the reference IS the transaction
        total = _cents(credit.amount_zar)
        refs.append((credit.reference, total))
    elif credit.invoice_id is not None:
        for p in session.execute(select(Payment).where(
                Payment.tenant_id == credit.tenant_id, Payment.invoice_id == credit.invoice_id,
                Payment.paystack_ref.is_not(None)).order_by(Payment.created_at.desc())).scalars():
            if str(p.status) in ("completed", "PaymentStatus.completed"):
                refs.append((p.paystack_ref, _cents(p.amount_zar)))
    return [(r, max(0, c - committed_cents(session, reference=r))) for r, c in refs]


def remaining_cents(session, credit: CustomerCredit) -> int:
    return max(0, _cents(credit.amount_zar) - committed_cents(session, credit_id=credit.id))


def public(r: GatewayRefund) -> dict:
    return {"id": str(r.id), "credit_id": str(r.credit_id), "invoice_id": str(r.invoice_id) if r.invoice_id else None,
            "method": r.method, "amount_zar": r.amount_cents / 100, "status": r.status, "reason": r.reason,
            "failure_reason": r.failure_reason, "created_at": r.created_at.isoformat() if r.created_at else None,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None}


class RefundRequest(BaseModel):
    credit_id: uuid.UUID
    amount_zar: Optional[Decimal] = Field(None, gt=0, max_digits=12, decimal_places=2)
    reason: Optional[str] = Field(None, max_length=300)
    method: str = Field("paystack", pattern="^(paystack|manual)$")
    manual_reference: Optional[str] = Field(None, max_length=100, description="Bank reference of the EFT paid out (manual only)")


def finalize_processed(session, refund: GatewayRefund) -> Optional[dict]:
    """Refund money has left: close the credit when fully refunded, open the tenant liability (Paystack refunds)
    and return the ledger entry to enqueue. Idempotent: calling it twice changes nothing the second time."""
    credit = session.execute(select(CustomerCredit).where(CustomerCredit.id == refund.credit_id).with_for_update()).scalar_one_or_none()
    if credit is not None and credit.status == "open" and committed_cents(session, credit_id=credit.id) >= _cents(credit.amount_zar):
        credit.status = "refunded"
    if refund.method == "paystack":
        exists = session.execute(select(GatewayLiability.id).where(
            GatewayLiability.tenant_id == refund.tenant_id, GatewayLiability.kind == "refund",
            GatewayLiability.source_id == str(refund.id))).first()
        if not exists:
            session.add(GatewayLiability(tenant_id=refund.tenant_id, kind="refund", source_id=str(refund.id),
                                         amount_cents=refund.amount_cents, note=f"Refund of invoice {refund.invoice_id}"))
    entry = fp.refund_entry(refund.id, refund.transaction_reference or "manual", fp.sast_today(), Decimal(refund.amount_cents) / 100)
    return entry if fp.enqueue(session, refund.tenant_id, entry) is not None else None


@router.get("/credits", dependencies=[Depends(require_tier("reader"))])
async def refundable_credits(ctx: AuthContext = Depends(get_auth_context)):
    """Open customer credits that can be refunded, with how much is left and whether Paystack can pay it."""
    with get_session() as session:
        rows = session.execute(select(CustomerCredit).where(
            CustomerCredit.tenant_id == ctx.tenant_id, CustomerCredit.status == "open",
            CustomerCredit.kind.in_(REFUNDABLE_KINDS)).order_by(CustomerCredit.created_at.desc()).limit(200)).scalars().all()
        out = []
        for c in rows:
            left = remaining_cents(session, c)
            if left <= 0:
                continue
            best = max((a for _, a in candidate_charges(session, c)), default=0)
            out.append({"id": str(c.id), "customer_id": str(c.customer_id), "invoice_id": str(c.invoice_id) if c.invoice_id else None,
                        "kind": c.kind, "reason": c.reason, "amount_zar": float(c.amount_zar), "remaining_zar": left / 100,
                        "paystack_refundable_zar": min(best, left) / 100,
                        "created_at": c.created_at.isoformat() if c.created_at else None})
        return {"credits": out}


@router.get("", dependencies=[Depends(require_tier("reader"))])
async def list_refunds(credit_id: Optional[uuid.UUID] = None, invoice_id: Optional[uuid.UUID] = None,
                       ctx: AuthContext = Depends(get_auth_context)):
    with get_session() as session:
        q = select(GatewayRefund).where(GatewayRefund.tenant_id == ctx.tenant_id)
        if credit_id:
            q = q.where(GatewayRefund.credit_id == credit_id)
        if invoice_id:
            q = q.where(GatewayRefund.invoice_id == invoice_id)
        return {"refunds": [public(r) for r in session.execute(q.order_by(GatewayRefund.created_at.desc()).limit(200)).scalars()]}


@router.post("", dependencies=[Depends(require_tier("admin"))])
async def create_refund(body: RefundRequest, ctx: AuthContext = Depends(get_auth_context)):
    if body.method == "manual" and not body.manual_reference:
        raise HTTPException(status_code=422, detail="manual_reference (the bank reference of the payout) is required")
    if body.method == "paystack" and not _secret():
        raise HTTPException(status_code=503, detail="Paystack not configured")

    with get_session() as session:
        credit = session.execute(select(CustomerCredit).where(
            CustomerCredit.id == body.credit_id, CustomerCredit.tenant_id == ctx.tenant_id).with_for_update()).scalar_one_or_none()
        if credit is None:
            raise HTTPException(status_code=404, detail="Credit not found")
        if credit.status != "open" or credit.kind not in REFUNDABLE_KINDS:
            raise HTTPException(status_code=409, detail="This credit cannot be refunded")
        left = remaining_cents(session, credit)
        cents = _cents(body.amount_zar) if body.amount_zar is not None else left
        if cents <= 0 or cents > left:
            raise HTTPException(status_code=400, detail=f"Amount must be between 0.01 and R{left / 100:.2f}")
        reference = None
        if body.method == "paystack":
            fits = [r for r, avail in candidate_charges(session, credit) if avail >= cents]
            if not fits:
                raise HTTPException(status_code=422, detail="No single card payment can cover this amount; refund a smaller amount, "
                                                            "or pay it back by EFT and record it as a manual refund")
            reference = fits[0]
        refund = GatewayRefund(tenant_id=ctx.tenant_id, credit_id=credit.id, invoice_id=credit.invoice_id, customer_id=credit.customer_id,
                               method=body.method, transaction_reference=reference or body.manual_reference, amount_cents=cents,
                               status="processed" if body.method == "manual" else "pending", reason=body.reason, requested_by=ctx.user_id)
        session.add(refund)
        session.flush()
        refund_id, entries = refund.id, []
        if body.method == "manual":
            entry = finalize_processed(session, refund)
            entries = [entry] if entry else []
    if body.method == "manual":
        await fp.deliver_after_commit(ctx.tenant_id, entries)
        with get_session() as session:
            return public(session.get(GatewayRefund, refund_id))

    res = await _paystack("POST", "/refund", {"transaction": reference, "amount": cents, "currency": "ZAR",
                                              "customer_note": (body.reason or "Refund")[:200], "merchant_note": f"credit {body.credit_id}"})
    data = res.get("data") or {}
    if res.get("_http_status", 200) >= 500:
        # outcome unknown: keep the pending row (it counts against the charge); the refund.* webhook decides
        logger.error("Paystack refund gateway error refund=%s", refund_id)
        raise HTTPException(status_code=502, detail="Payment gateway error; the refund is recorded as pending")
    entries = []
    with get_session() as session:
        refund = session.get(GatewayRefund, refund_id)
        if not res.get("status"):
            refund.status, refund.failure_reason = "failed", (res.get("message") or "Paystack rejected the refund")[:300]
        else:
            refund.paystack_refund_id = str(data.get("id") or "") or None
            refund.status = STATUS_MAP.get(str(data.get("status") or "pending").lower(), "pending")
            if refund.status == "processed":
                entry = finalize_processed(session, refund)
                entries = [entry] if entry else []
        out = public(refund)
    await fp.deliver_after_commit(ctx.tenant_id, entries)
    if out["status"] == "failed":
        raise HTTPException(status_code=502, detail=out["failure_reason"])
    return out


async def handle_event(event: str, data: dict) -> str:
    """refund.pending | refund.processing | refund.processed | refund.failed. Returns 'accepted'|'duplicate'|'ignored'."""
    new_status = STATUS_MAP.get(event.split(".", 1)[1].lower()) or STATUS_MAP.get(str(data.get("status") or "").lower())
    reference = data.get("transaction_reference") or (data.get("transaction") or {}).get("reference")
    rid = str(data.get("id") or "")
    key = f"{event}:{rid or reference}:{data.get('status')}:{data.get('updatedAt') or data.get('updated_at') or ''}"[:200]
    entries, tenant = [], None
    with get_session() as session:
        try:
            with session.begin_nested():
                session.add(BillingWebhookEvent(provider="paystack", event_key=key, event_type=event, reference=reference or None))
                session.flush()
        except IntegrityError:
            return "duplicate"
        q = select(GatewayRefund).where(GatewayRefund.method == "paystack")
        refund = None
        if rid:
            refund = session.execute(q.where(GatewayRefund.paystack_refund_id == rid)).scalars().first()
        if refund is None and reference:
            refund = session.execute(q.where(GatewayRefund.transaction_reference == reference,
                                             GatewayRefund.status.in_(("pending", "processing"))).order_by(GatewayRefund.created_at.desc())).scalars().first()
        if refund is None or new_status is None:
            logger.warning("refund webhook %s ref=%s matches no refund of ours", event, reference)
            return "ignored"
        if refund.status in ("processed", "failed"):
            return "duplicate"                                  # final already; a late/out-of-order event changes nothing
        if rid and not refund.paystack_refund_id:
            refund.paystack_refund_id = rid
        refund.status = new_status
        if new_status == "failed":
            refund.failure_reason = str(data.get("failure_reason") or data.get("message") or "Refund failed at the bank")[:300]
        tenant = refund.tenant_id
        if new_status == "processed":
            entry = finalize_processed(session, refund)
            entries = [entry] if entry else []
    if tenant is not None:
        await fp.deliver_after_commit(tenant, entries)
    return "accepted"
