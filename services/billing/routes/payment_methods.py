"""Cards on file, charging them, and the autopay run.

Why we charge saved cards ourselves instead of using Paystack Subscriptions for tenant customers: a
Paystack Plan/Subscription charge cannot carry our `subaccount` / `transaction_charge`, so the tenant would
not be settled and OmniDome would not get its commission. `POST /transaction/charge_authorization` does
accept them, so recurring ISP billing is: our invoice schedule -> charge the saved authorization with the
split -> the same `charge.success` handler applies the payment. A failed charge is reported synchronously by
Paystack (there is no charge.failed webhook), so the failure is recorded here and retried by the autopay run.

Card-on-file consent: a card is only saved when the initialize request said `save_payment_method` (the
customer ticked the box); that flag travels in the Paystack metadata and comes back on charge.success.
"""

import logging
import os
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select

from services.billing import calc
from services.billing.access import require_tier
from services.billing.contacts import resolve_customer_email
from services.billing.database import get_session
from services.billing.models import Invoice, PaystackInitialization
from services.billing.models_gateway import GatewayCharge, GatewayDispute, PaymentMethod
from services.billing.routes import gateway as gw
from services.billing.routes.paystack_recurring import _paystack, _secret
from services.common.auth import AuthContext, get_auth_context

logger = logging.getLogger("billing.payment_methods")

router = APIRouter(tags=["Payment methods"])

NON_PAYABLE = ("paid", "voided", "credit_issued", "draft")


def max_attempts() -> int:
    return int(os.getenv("AUTOPAY_MAX_ATTEMPTS", "3"))


def retry_gap() -> timedelta:
    return timedelta(hours=float(os.getenv("AUTOPAY_RETRY_HOURS", "48")))


# ---------------------------------------------------------------------------
# Capture (called from the charge.success webhook transaction)
# ---------------------------------------------------------------------------

def capture_authorization(session, tenant_id, customer_id, data: dict) -> Optional[PaymentMethod]:
    """Save the card from a successful charge when the customer consented and Paystack says it is reusable."""
    meta = data.get("metadata")
    if not isinstance(meta, dict) or not meta.get("save_payment_method"):
        return None
    auth = data.get("authorization") or {}
    code = auth.get("authorization_code")
    if not code or not auth.get("reusable") or (auth.get("channel") or "card") != "card":
        return None
    signature = auth.get("signature") or code
    existing = session.execute(select(PaymentMethod).where(
        PaymentMethod.tenant_id == tenant_id, PaymentMethod.customer_id == customer_id,
        PaymentMethod.signature == signature)).scalar_one_or_none()
    cust = data.get("customer") or {}
    fields = dict(authorization_code=code, paystack_customer_code=cust.get("customer_code"),
                  brand=auth.get("brand"), card_type=auth.get("card_type"), bank=auth.get("bank"), last4=auth.get("last4"),
                  exp_month=_int(auth.get("exp_month")), exp_year=_int(auth.get("exp_year")), reusable=True, status="active")
    if existing is not None:
        for k, v in fields.items():          # a re-used card: refresh the token / expiry, keep default + consent date
            setattr(existing, k, v)
        return existing
    has_default = session.execute(select(PaymentMethod.id).where(
        PaymentMethod.tenant_id == tenant_id, PaymentMethod.customer_id == customer_id,
        PaymentMethod.status == "active", PaymentMethod.is_default.is_(True)).limit(1)).first() is not None
    row = PaymentMethod(tenant_id=tenant_id, customer_id=customer_id, signature=signature,
                        is_default=not has_default, **fields)
    session.add(row)
    return row


def _int(v) -> Optional[int]:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def is_expired(m: PaymentMethod, today: Optional[date] = None) -> bool:
    """A card is valid through the last day of its expiry month."""
    if not m.exp_month or not m.exp_year:
        return False
    today = today or calc.today_sast()
    return (today.year, today.month) > (m.exp_year, m.exp_month)


def public(m: PaymentMethod) -> dict:
    """What the API returns. Never the authorization code."""
    return {"id": str(m.id), "customer_id": str(m.customer_id), "brand": m.brand, "card_type": m.card_type, "bank": m.bank,
            "last4": m.last4, "exp_month": m.exp_month, "exp_year": m.exp_year, "is_default": m.is_default,
            "status": "expired" if m.status == "active" and is_expired(m) else m.status}


def usable_method(session, tenant_id, customer_id, method_id=None) -> Optional[PaymentMethod]:
    q = select(PaymentMethod).where(PaymentMethod.tenant_id == tenant_id, PaymentMethod.customer_id == customer_id,
                                    PaymentMethod.status == "active", PaymentMethod.reusable.is_(True))
    q = q.where(PaymentMethod.id == method_id) if method_id else q.order_by(PaymentMethod.is_default.desc(), PaymentMethod.created_at.desc())
    for m in session.execute(q).scalars():
        if not is_expired(m):
            return m
    return None


def invoice_is_disputed(session, tenant_id, invoice_id) -> bool:
    return session.execute(select(GatewayDispute.id).where(
        GatewayDispute.tenant_id == tenant_id, GatewayDispute.invoice_id == invoice_id,
        GatewayDispute.status.notin_(("resolved", "archived"))).limit(1)).first() is not None


# ---------------------------------------------------------------------------
# Charge a saved card
# ---------------------------------------------------------------------------

async def charge_saved_method(tenant_id, user_id, invoice_id, *, method_id=None, amount_zar: Optional[Decimal] = None,
                              kind: str = "autopay") -> dict:
    """Charge the customer's saved card for an invoice. Returns {"status": "succeeded"|"failed"|"pending", ...}.
    Raises HTTPException for conditions the caller must fix (no gateway, no card, invoice not payable)."""
    from services.billing.routes import paystack as ps   # late import: paystack imports this package
    if not _secret():
        raise HTTPException(status_code=503, detail="Paystack not configured")
    with get_session() as session:
        inv = session.execute(select(Invoice).where(Invoice.id == invoice_id, Invoice.tenant_id == tenant_id)).scalar_one_or_none()
        if inv is None:
            raise HTTPException(status_code=404, detail="Invoice not found")
        if inv.status in NON_PAYABLE or inv.credit_note_of is not None:
            raise HTTPException(status_code=400, detail=f"Invoice is already {inv.status}")
        if invoice_is_disputed(session, tenant_id, invoice_id):
            raise HTTPException(status_code=409, detail="Invoice has an open dispute")
        outstanding = inv.total_zar - inv.amount_paid_zar
        amount = Decimal(str(amount_zar)) if amount_zar is not None else outstanding
        if amount <= 0 or amount > outstanding:
            raise HTTPException(status_code=400, detail=f"Amount must be between 0.01 and the outstanding R{outstanding}")
        method = usable_method(session, tenant_id, inv.customer_id, method_id)
        if method is None:
            raise HTTPException(status_code=409, detail="No usable saved card for this customer")
        customer_id, billing_account_id = inv.customer_id, inv.billing_account_id
        auth_code, method_pk = method.authorization_code, method.id
        attempt = 1 + int(session.execute(select(func.count()).select_from(GatewayCharge).where(
            GatewayCharge.tenant_id == tenant_id, GatewayCharge.invoice_id == invoice_id, GatewayCharge.kind == kind)).scalar_one())

    email = await resolve_customer_email(tenant_id, customer_id, billing_account_id)
    if not email:
        raise HTTPException(status_code=422, detail="Customer has no email on file")
    cents = ps.to_cents(amount)
    reference = f"OD-{uuid.uuid4().hex}"
    payload = {"email": email, "amount": cents, "currency": "ZAR", "reference": reference, "authorization_code": auth_code,
               "metadata": {"invoice_id": str(invoice_id), "tenant_id": str(tenant_id), "customer_id": str(customer_id), "kind": kind}}
    with get_session() as session:
        split = gw.split_for_charge(session, tenant_id, cents, reference, invoice_id=invoice_id, kind=kind)
        if split:
            payload.update(split)
            row = session.execute(select(GatewayCharge).where(GatewayCharge.reference == reference)).scalar_one()
            row.payment_method_id, row.attempt = method_pk, attempt
        session.add(PaystackInitialization(tenant_id=tenant_id, invoice_id=invoice_id, customer_id=customer_id,
                                           reference=reference, amount_cents=cents, currency="ZAR", status="pending"))

    res = await _paystack("POST", "/transaction/charge_authorization", payload)
    data = res.get("data") or {}
    status = data.get("status")
    if res.get("_http_status", 200) >= 500 or (not res.get("status") and status is None):
        # unknown outcome (gateway error): leave the rows; the webhook (or the next run's reconciliation) decides
        logger.error("charge_authorization gateway error ref=%s http=%s", reference, res.get("_http_status"))
        return {"status": "pending", "reference": reference, "attempt": attempt}
    if status == "success":
        data.setdefault("reference", reference)
        data["metadata"] = data.get("metadata") if isinstance(data.get("metadata"), dict) else payload["metadata"]
        outcome = await ps._handle_charge_success(data, ps.event_key("charge.success", data, b""))   # same dedupe key as the webhook
        return {"status": "succeeded", "reference": reference, "attempt": attempt, "outcome": outcome}
    if status in ("failed", "abandoned", "reversed") or not res.get("status"):
        reason = (data.get("gateway_response") or res.get("message") or "declined")[:200]
        with get_session() as session:
            session.query(GatewayCharge).filter(GatewayCharge.reference == reference).update(
                {"status": "failed", "failure_reason": reason})
            session.query(PaystackInitialization).filter(PaystackInitialization.reference == reference).update({"status": "failed"})
        logger.warning("saved-card charge failed ref=%s attempt=%s reason=%s", reference, attempt, reason)
        return {"status": "failed", "reference": reference, "attempt": attempt, "reason": reason}
    return {"status": "pending", "reference": reference, "attempt": attempt, "paystack_status": status}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

class ChargeSavedRequest(BaseModel):
    invoice_id: uuid.UUID
    payment_method_id: Optional[uuid.UUID] = None
    amount_zar: Optional[Decimal] = None


@router.get("/payment-methods", dependencies=[Depends(require_tier("reader"))])
async def list_methods(customer_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context)):
    with get_session() as session:
        rows = session.execute(select(PaymentMethod).where(
            PaymentMethod.tenant_id == ctx.tenant_id, PaymentMethod.customer_id == customer_id,
            PaymentMethod.status == "active").order_by(PaymentMethod.is_default.desc())).scalars().all()
        return {"methods": [public(m) for m in rows]}


@router.post("/payment-methods/{method_id}/default", dependencies=[Depends(require_tier("clerk"))])
async def make_default(method_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context)):
    with get_session() as session:
        m = session.execute(select(PaymentMethod).where(PaymentMethod.id == method_id, PaymentMethod.tenant_id == ctx.tenant_id,
                                                        PaymentMethod.status == "active")).scalar_one_or_none()
        if m is None:
            raise HTTPException(status_code=404, detail="Payment method not found")
        session.query(PaymentMethod).filter(PaymentMethod.tenant_id == ctx.tenant_id, PaymentMethod.customer_id == m.customer_id,
                                            PaymentMethod.id != m.id).update({"is_default": False})
        m.is_default = True
        return public(m)


@router.delete("/payment-methods/{method_id}", dependencies=[Depends(require_tier("clerk"))])
async def remove_method(method_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context)):
    """Stop using the card and tell Paystack to deactivate the authorization (best effort)."""
    with get_session() as session:
        m = session.execute(select(PaymentMethod).where(PaymentMethod.id == method_id, PaymentMethod.tenant_id == ctx.tenant_id,
                                                        PaymentMethod.status == "active")).scalar_one_or_none()
        if m is None:
            raise HTTPException(status_code=404, detail="Payment method not found")
        code = m.authorization_code
        m.status, m.is_default = "removed", False
    if _secret():
        res = await _paystack("POST", "/customer/authorization/deactivate", {"authorization_code": code})
        if not res.get("status"):
            logger.warning("Paystack authorization deactivate failed for method %s", method_id)
    return {"id": str(method_id), "status": "removed"}


@router.post("/payments/charge-saved", dependencies=[Depends(require_tier("admin"))])
async def charge_saved(body: ChargeSavedRequest, ctx: AuthContext = Depends(get_auth_context)):
    return await charge_saved_method(ctx.tenant_id, ctx.user_id, body.invoice_id, method_id=body.payment_method_id,
                                     amount_zar=body.amount_zar, kind="manual")


@router.post("/payments/autopay/run", dependencies=[Depends(require_tier("admin"))])
async def run_autopay_endpoint(limit: int = 100, ctx: AuthContext = Depends(get_auth_context)):
    return await run_autopay(ctx.tenant_id, ctx.user_id, limit=min(max(limit, 1), 500))


async def run_autopay(tenant_id, user_id, *, limit: int = 100, today: Optional[date] = None, now: Optional[datetime] = None) -> dict:
    """Charge the default saved card for every due invoice of customers who have one.

    Skips: not yet due, disputed, no usable card, an attempt still pending (<2h), the retry gap not elapsed, and
    invoices that already used `AUTOPAY_MAX_ATTEMPTS` failed attempts (dunning takes over from there)."""
    today = today or calc.today_sast()
    now = now or datetime.now(timezone.utc)
    summary = {"charged": 0, "failed": 0, "pending": 0, "skipped": 0, "details": []}
    with get_session() as session:
        invoices = session.execute(select(Invoice.id, Invoice.customer_id).where(
            Invoice.tenant_id == tenant_id, Invoice.status.in_(("sent", "overdue", "partially_paid")),
            Invoice.credit_note_of.is_(None), Invoice.due_date <= today).order_by(Invoice.due_date).limit(limit * 3)).all()
        plan = []
        for inv_id, cust_id in invoices:
            if len(plan) >= limit:
                break
            why = None
            if invoice_is_disputed(session, tenant_id, inv_id):
                why = "disputed"
            elif usable_method(session, tenant_id, cust_id) is None:
                why = "no_card"
            else:
                tries = session.execute(select(GatewayCharge.status, GatewayCharge.created_at).where(
                    GatewayCharge.tenant_id == tenant_id, GatewayCharge.invoice_id == inv_id,
                    GatewayCharge.kind == "autopay").order_by(GatewayCharge.created_at.desc())).all()
                failed = [t for t in tries if t[0] == "failed"]
                last = tries[0] if tries else None
                if len(failed) >= max_attempts():
                    why = "attempts_exhausted"
                elif last and last[0] == "initialized" and _aware(last[1]) > now - timedelta(hours=2):
                    why = "pending"
                elif last and last[0] == "failed" and _aware(last[1]) > now - retry_gap():
                    why = "retry_later"
            if why:
                summary["skipped"] += 1
            else:
                plan.append(inv_id)
    for inv_id in plan:
        try:
            r = await charge_saved_method(tenant_id, user_id, inv_id, kind="autopay")
        except HTTPException as exc:
            summary["skipped"] += 1
            summary["details"].append({"invoice_id": str(inv_id), "error": exc.detail})
            continue
        key = {"succeeded": "charged", "failed": "failed"}.get(r["status"], "pending")
        summary[key] += 1
        summary["details"].append({"invoice_id": str(inv_id), "status": r["status"], "attempt": r.get("attempt"), "reason": r.get("reason")})
    return summary


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
