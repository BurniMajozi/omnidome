"""Paystack integration - initialize, verify, webhook.

Money-safety rules enforced here:
  * initialize: amount <= outstanding, Decimal -> cents with ROUND_HALF_UP, the customer's email comes
    from their record (never the client), callback_url must be on BILLING_CALLBACK_ALLOWED_HOSTS
    (default: host of APP_PUBLIC_URL), no mock reference unless BILLING_ALLOW_MOCK_PAYSTACK=true,
    and every checkout gets a unique reference stored in billing_paystack_initializations.
  * webhook: HMAC-SHA512 signature; each event is applied once (billing_webhook_events, unique key,
    inserted in the SAME transaction as the payment); currency must be ZAR; the amount must match the
    initialization; payments that cannot be applied to the invoice (voided/credited/over the balance)
    become unallocated customer credits, never a silent drop and never a paid VOIDED invoice;
    reinstatement runs after commit.
"""

import hashlib
import hmac
import json
import logging
import os
import uuid
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.exc import IntegrityError

from services.common.auth import AuthContext, get_auth_context
from services.common.http_client import service_post
from services.billing import finance_posting as fp, invoicing
from services.billing.access import require_tier
from services.billing.contacts import resolve_customer_email
from services.billing.database import get_session
from services.billing.models import (
    BillingWebhookEvent, CustomerCredit, Invoice, PaystackInitialization, Subscription,
)
from services.billing.schemas import (
    PaystackInitializeRequest,
    PaystackInitializeResponse,
    PaystackVerifyResponse,
)

logger = logging.getLogger("billing.paystack")

router = APIRouter(prefix="/payments/paystack", tags=["Paystack"])

PAYSTACK_BASE = "https://api.paystack.co"
PAYSTACK_SECRET = os.getenv("PAYSTACK_SECRET_KEY", "")
PAYSTACK_WEBHOOK_SECRET = os.getenv("PAYSTACK_WEBHOOK_SECRET", PAYSTACK_SECRET)
NON_PAYABLE = ("paid", "voided", "credit_issued")


def _paystack_headers() -> dict:
    return {
        "Authorization": f"Bearer {PAYSTACK_SECRET}",
        "Content-Type": "application/json",
    }


def to_cents(amount: Decimal) -> int:
    """ZAR amount -> integer cents, rounded half up (never truncated)."""
    return int((Decimal(str(amount)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def allow_mock() -> bool:
    return os.getenv("BILLING_ALLOW_MOCK_PAYSTACK", "false").strip().lower() == "true"


def allowed_callback_hosts() -> set:
    raw = os.getenv("BILLING_CALLBACK_ALLOWED_HOSTS", "")
    hosts = {h.strip().lower() for h in raw.split(",") if h.strip()}
    if not hosts:
        host = urlparse(os.getenv("APP_PUBLIC_URL", "")).hostname
        if host:
            hosts.add(host.lower())
    return hosts


def callback_allowed(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    return parsed.scheme in ("http", "https") and bool(parsed.hostname) and parsed.hostname.lower() in allowed_callback_hosts()


# ---------------------------------------------------------------------------
# POST /payments/paystack/initialize
# ---------------------------------------------------------------------------

@router.post("/initialize", response_model=PaystackInitializeResponse,
             dependencies=[Depends(require_tier("admin"))])
async def initialize_paystack(
    body: PaystackInitializeRequest,
    ctx: AuthContext = Depends(get_auth_context),
):
    if not PAYSTACK_SECRET and not allow_mock():
        raise HTTPException(status_code=503, detail="Paystack not configured")
    if body.callback_url and not callback_allowed(body.callback_url):
        raise HTTPException(status_code=400, detail="callback_url host is not allowed")

    with get_session() as session:
        inv = (
            session.query(Invoice)
            .filter(Invoice.id == body.invoice_id, Invoice.tenant_id == ctx.tenant_id)
            .first()
        )
        if not inv:
            raise HTTPException(status_code=404, detail="Invoice not found")
        if inv.status in NON_PAYABLE or inv.credit_note_of is not None:
            raise HTTPException(status_code=400, detail=f"Invoice is already {inv.status}")
        outstanding = inv.total_zar - inv.amount_paid_zar
        amount_zar = Decimal(str(body.amount_zar)) if body.amount_zar is not None else outstanding
        if amount_zar <= 0 or amount_zar > outstanding:
            raise HTTPException(status_code=400, detail=f"Amount must be between 0.01 and the outstanding R{outstanding}")
        invoice_id, customer_id = inv.id, inv.customer_id
        billing_account_id = inv.billing_account_id

    amount_cents = to_cents(amount_zar)
    reference = f"OD-{uuid.uuid4().hex}"

    if not PAYSTACK_SECRET:  # BILLING_ALLOW_MOCK_PAYSTACK=true (development only)
        logger.warning("PAYSTACK_SECRET_KEY not set; BILLING_ALLOW_MOCK_PAYSTACK returns a mock checkout")
        return PaystackInitializeResponse(
            authorization_url="https://checkout.paystack.com/mock", access_code="MOCK_ACCESS", reference=reference)

    email = await resolve_customer_email(ctx.tenant_id, customer_id, billing_account_id)
    if not email:
        raise HTTPException(status_code=422, detail="Customer has no email on file")

    payload = {
        "email": email,
        "amount": amount_cents,
        "currency": "ZAR",
        "reference": reference,
        "metadata": {
            "invoice_id": str(invoice_id),
            "tenant_id": str(ctx.tenant_id),
            "customer_id": str(customer_id),
        },
    }
    if body.callback_url:
        payload["callback_url"] = body.callback_url

    with get_session() as session:
        session.add(PaystackInitialization(
            tenant_id=ctx.tenant_id, invoice_id=invoice_id, customer_id=customer_id,
            reference=reference, amount_cents=amount_cents, currency="ZAR", status="pending"))

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(f"{PAYSTACK_BASE}/transaction/initialize", json=payload, headers=_paystack_headers())
    if resp.status_code != 200:
        logger.error("Paystack init failed: HTTP %s", resp.status_code)
        with get_session() as session:
            session.query(PaystackInitialization).filter(PaystackInitialization.reference == reference).delete()
        raise HTTPException(status_code=502, detail="Payment gateway error")

    data = resp.json().get("data", {})
    return PaystackInitializeResponse(
        authorization_url=data.get("authorization_url", ""),
        access_code=data.get("access_code", ""),
        reference=data.get("reference", reference),
    )


# ---------------------------------------------------------------------------
# POST /payments/paystack/verify/{reference}
# ---------------------------------------------------------------------------

@router.post("/verify/{reference}", response_model=PaystackVerifyResponse,
             dependencies=[Depends(require_tier("reader"))])
async def verify_paystack(
    reference: str,
    ctx: AuthContext = Depends(get_auth_context),
):
    if not PAYSTACK_SECRET:
        if not allow_mock():
            raise HTTPException(status_code=503, detail="Paystack not configured")
        return PaystackVerifyResponse(reference=reference, status="mock_success", amount_zar=Decimal("0.00"))

    # Only references we initialized for this tenant may be verified.
    with get_session() as session:
        known = session.query(PaystackInitialization.id).filter(
            PaystackInitialization.reference == reference, PaystackInitialization.tenant_id == ctx.tenant_id).first()
    if known is None:
        raise HTTPException(status_code=404, detail="Unknown reference")

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(f"{PAYSTACK_BASE}/transaction/verify/{reference}", headers=_paystack_headers())
    if resp.status_code != 200:
        logger.error("Paystack verify failed: HTTP %s", resp.status_code)
        raise HTTPException(status_code=502, detail="Payment gateway error")

    data = resp.json().get("data", {})
    return PaystackVerifyResponse(
        reference=data.get("reference", reference),
        status=data.get("status", "unknown"),
        amount_zar=Decimal(str(data.get("amount", 0))) / 100,
        paid_at=data.get("paid_at"),
        channel=data.get("channel"),
    )


# ---------------------------------------------------------------------------
# POST /payments/paystack/webhook - Paystack webhook handler
# ---------------------------------------------------------------------------

def _verify_webhook_signature(body: bytes, signature: Optional[str]) -> bool:
    """Verify HMAC SHA-512 signature from Paystack. No secret or no signature
    means not verified: the webhook is public, and an unverified
    charge.success would mark any invoice paid."""
    if not PAYSTACK_WEBHOOK_SECRET or not signature:
        return False
    expected = hmac.new(
        PAYSTACK_WEBHOOK_SECRET.encode(), body, hashlib.sha512
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def event_key(event: str, data: dict, raw: bytes) -> str:
    ident = data.get("id") or data.get("reference") or hashlib.sha256(raw).hexdigest()
    return f"{event}:{ident}"[:200]


@router.post("/webhook", status_code=200)
async def paystack_webhook(
    request: Request,
    x_paystack_signature: Optional[str] = Header(None),
):
    """Handle Paystack webhook callbacks.

    This endpoint is public (bypasses entitlement guard via public_paths config).
    """
    raw_body = await request.body()

    if not PAYSTACK_WEBHOOK_SECRET:
        logger.error("Paystack webhook secret not configured - rejecting webhook")
        raise HTTPException(status_code=503, detail="Webhook secret not configured")
    if not _verify_webhook_signature(raw_body, x_paystack_signature):
        raise HTTPException(status_code=401, detail="Invalid or missing signature")

    try:
        payload = json.loads(raw_body)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    event = payload.get("event", "")
    data = payload.get("data", {}) or {}

    logger.info("Paystack webhook: event=%s ref=%s", event, data.get("reference"))
    outcome = "accepted"

    if event == "charge.success":
        outcome = await _handle_charge_success(data, event_key(event, data, raw_body))
    elif event in ("subscription.disable", "subscription.not_renew"):
        _handle_subscription_status(data, "cancelled")
    elif event == "subscription.create":
        logger.info("Subscription created: %s", data.get("subscription_code"))
    elif event == "invoice.payment_failed":
        _handle_subscription_status(data.get("subscription", data), "past_due")
    elif event in ("transfer.success", "transfer.failed", "transfer.reversed"):
        # Payroll payouts (services/hr) initiate transfers on this same Paystack
        # account; record the terminal state here for visibility.
        logger.info("Transfer %s: %s", event.split(".")[1], data.get("reference"))

    return {"status": outcome}


def _handle_subscription_status(data: dict, new_status: str) -> None:
    """Reflect a Paystack subscription lifecycle event on our subscriptions row."""
    code = data.get("subscription_code") or (data.get("subscription") or {}).get("subscription_code")
    if not code:
        logger.info("subscription webhook without subscription_code; ignored")
        return
    with get_session() as session:
        sub = (
            session.query(Subscription)
            .filter(Subscription.paystack_subscription_code == code)
            .first()
        )
        if sub:
            sub.status = new_status
            logger.info("Subscription %s -> %s", code, new_status)


def classify_charge(inv: Invoice, amount: Decimal, init_cents: Optional[int], amount_cents: int,
                    currency: str) -> tuple[str, Decimal, Decimal]:
    """Decide what to do with a verified charge. Pure (unit tested).

    Returns (action, apply_amount, extra) where action is one of
      'reject_currency'  - not ZAR: nothing recorded (alert),
      'unallocated'      - hold the whole amount as customer credit (voided/credited invoice,
                           or amount differs from the initialization),
      'apply'            - apply `apply_amount` to the invoice, `extra` (>=0) is held as credit.
    """
    if (currency or "").upper() != "ZAR":
        return "reject_currency", Decimal("0"), Decimal("0")
    if inv.status in NON_PAYABLE and inv.status != "paid" or inv.credit_note_of is not None:
        return "unallocated", Decimal("0"), amount
    if init_cents is not None and init_cents != amount_cents:
        return "unallocated", Decimal("0"), amount
    outstanding = inv.total_zar - inv.amount_paid_zar
    if outstanding <= 0:  # already paid in full: the whole charge is an overpayment
        return "unallocated", Decimal("0"), amount
    if amount > outstanding:
        return "apply", outstanding, amount - outstanding
    return "apply", amount, Decimal("0")


async def _handle_charge_success(data: dict, key: str) -> str:
    """Process a successful charge exactly once. Returns 'accepted' | 'duplicate' | 'ignored' | 'rejected'."""
    reference = data.get("reference", "") or ""
    amount_cents = int(data.get("amount", 0) or 0)
    amount = (Decimal(amount_cents) / 100).quantize(Decimal("0.01"))
    currency = str(data.get("currency") or "")
    metadata = data.get("metadata") or {}
    if not isinstance(metadata, dict):
        metadata = {}

    entries: list = []
    reinstate = None
    tenant_for_delivery = None
    with get_session() as session:
        # Dedupe: the event row is written in this transaction, so a failure rolls it back and
        # Paystack's retry is processed normally; a committed duplicate is a no-op.
        try:
            with session.begin_nested():
                session.add(BillingWebhookEvent(provider="paystack", event_key=key, event_type="charge.success",
                                                reference=reference or None))
                session.flush()
        except IntegrityError:
            logger.info("Webhook: duplicate event %s ignored", key)
            return "duplicate"

        init = None
        if reference:
            init = session.query(PaystackInitialization).filter(PaystackInitialization.reference == reference).first()
        try:
            if init is not None:
                tenant_id, invoice_id = init.tenant_id, init.invoice_id
            else:
                tenant_id, invoice_id = uuid.UUID(str(metadata["tenant_id"])), uuid.UUID(str(metadata["invoice_id"]))
        except (KeyError, ValueError):
            logger.warning("Webhook charge.success missing/invalid invoice/tenant metadata (ref %s)", reference)
            return "ignored"

        inv = (
            session.query(Invoice)
            .filter(Invoice.id == invoice_id, Invoice.tenant_id == tenant_id)
            .with_for_update()
            .first()
        )
        if not inv:
            logger.error("Webhook: invoice %s not found for charge %s (R%s received)", invoice_id, reference, amount)
            return "ignored"
        tenant_for_delivery = tenant_id

        action, apply_amt, extra = classify_charge(inv, amount, init.amount_cents if init else None, amount_cents, currency)
        if action == "reject_currency":
            logger.error("ALERT: Paystack charge %s in currency %r (not ZAR) NOT recorded", reference, currency)
            return "rejected"

        if action == "apply" and apply_amt > 0:
            _, entries = invoicing.apply_payment(session, inv, apply_amt, "card", reference=reference or None,
                                                 paystack_ref=reference or None)
            logger.info("Payment recorded: invoice=%s amount=R%.2f status=%s", inv.number, apply_amt, inv.status)
            if inv.status == "paid":
                reinstate = inv.customer_id
        if extra > 0:
            kind = "overpayment" if action == "apply" else "unallocated_payment"
            why = {
                "overpayment": "charge exceeded the invoice balance",
                "unallocated_payment": f"charge could not be applied to invoice {inv.number} (status {inv.status}"
                                       f"{'; amount differs from initialization' if init is not None and init.amount_cents != amount_cents else ''})",
            }[kind]
            logger.error("ALERT: R%s held as unallocated credit for customer %s: %s", extra, inv.customer_id, why)
            credit = CustomerCredit(
                id=uuid.uuid4(), tenant_id=tenant_id, customer_id=inv.customer_id, invoice_id=inv.id,
                amount_zar=extra, kind=kind, reference=reference or None, reason=why)
            session.add(credit)
            session.flush()
            ce = fp.payment_entry(credit.id, reference or str(credit.id)[:8], fp.sast_today(), extra, "card")
            if fp.enqueue(session, tenant_id, ce) is not None:
                entries.append(ce)
        if init is not None:
            init.status = "completed"
    # Everything below runs after the commit.
    if tenant_for_delivery is not None:
        await fp.deliver_after_commit(tenant_for_delivery, entries)
        if reinstate is not None:
            await _trigger_auto_reinstate(tenant_for_delivery, reinstate)
    return "accepted"


async def _trigger_auto_reinstate(tenant_id, customer_id) -> None:
    """Notify Network service to reinstate customer service after payment."""
    try:
        await service_post(
            "network",
            "/services/reinstate-by-customer",
            json={"customer_id": str(customer_id)},
            tenant_id=tenant_id,
            user_id=uuid.UUID(fp.service_user_id()),
            timeout=5.0,
        )
        logger.info("Auto-reinstate OK for customer %s", customer_id)
    except Exception as exc:
        logger.error("Auto-reinstate failed for customer %s: %s", customer_id, exc)
