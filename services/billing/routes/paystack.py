"""Paystack integration — initialize, verify, webhook."""

import hashlib
import hmac
import logging
import os
from decimal import Decimal
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Header, Request, status

from services.common.auth import AuthContext, get_auth_context
from services.billing.database import get_session
from services.billing.models import Invoice, Payment
from services.billing.schemas import (
    PaymentRead,
    PaystackInitializeRequest,
    PaystackInitializeResponse,
    PaystackVerifyResponse,
)

logger = logging.getLogger("billing.paystack")

router = APIRouter(prefix="/payments/paystack", tags=["Paystack"])

PAYSTACK_BASE = "https://api.paystack.co"
PAYSTACK_SECRET = os.getenv("PAYSTACK_SECRET_KEY", "")
PAYSTACK_WEBHOOK_SECRET = os.getenv("PAYSTACK_WEBHOOK_SECRET", PAYSTACK_SECRET)


def _paystack_headers() -> dict:
    return {
        "Authorization": f"Bearer {PAYSTACK_SECRET}",
        "Content-Type": "application/json",
    }


# ---------------------------------------------------------------------------
# POST /payments/paystack/initialize
# ---------------------------------------------------------------------------

@router.post("/initialize", response_model=PaystackInitializeResponse)
async def initialize_paystack(
    body: PaystackInitializeRequest,
    ctx: AuthContext = Depends(get_auth_context),
):
    with get_session() as session:
        inv = (
            session.query(Invoice)
            .filter(Invoice.id == body.invoice_id, Invoice.tenant_id == ctx.tenant_id)
            .first()
        )
        if not inv:
            raise HTTPException(status_code=404, detail="Invoice not found")
        if inv.status in ("paid", "voided"):
            raise HTTPException(status_code=400, detail=f"Invoice is already {inv.status}")

    # Amount in kobo (ZAR cents)
    amount_zar = body.amount_zar or (inv.total_zar - inv.amount_paid_zar)
    amount_kobo = int(amount_zar * 100)

    payload = {
        "email": body.email,
        "amount": amount_kobo,
        "currency": "ZAR",
        "metadata": {
            "invoice_id": str(inv.id),
            "tenant_id": str(ctx.tenant_id),
            "customer_id": str(inv.customer_id),
        },
    }
    if body.callback_url:
        payload["callback_url"] = body.callback_url

    if not PAYSTACK_SECRET:
        # Dev mode — return mock response
        logger.warning("PAYSTACK_SECRET not set; returning mock initialization")
        return PaystackInitializeResponse(
            authorization_url="https://checkout.paystack.com/mock",
            access_code="MOCK_ACCESS",
            reference="MOCK_REF_" + str(inv.id)[:8],
        )

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            f"{PAYSTACK_BASE}/transaction/initialize",
            json=payload,
            headers=_paystack_headers(),
        )
        if resp.status_code != 200:
            logger.error("Paystack init failed: %s", resp.text)
            raise HTTPException(status_code=502, detail="Payment gateway error")

        data = resp.json().get("data", {})
        return PaystackInitializeResponse(
            authorization_url=data.get("authorization_url", ""),
            access_code=data.get("access_code", ""),
            reference=data.get("reference", ""),
        )


# ---------------------------------------------------------------------------
# POST /payments/paystack/verify/{reference}
# ---------------------------------------------------------------------------

@router.post("/verify/{reference}", response_model=PaystackVerifyResponse)
async def verify_paystack(
    reference: str,
    ctx: AuthContext = Depends(get_auth_context),
):
    if not PAYSTACK_SECRET:
        return PaystackVerifyResponse(
            reference=reference, status="mock_success", amount_zar=Decimal("0.00")
        )

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            f"{PAYSTACK_BASE}/transaction/verify/{reference}",
            headers=_paystack_headers(),
        )
        if resp.status_code != 200:
            logger.error("Paystack verify failed: %s", resp.text)
            raise HTTPException(status_code=502, detail="Payment gateway error")

        data = resp.json().get("data", {})
        amount_zar = Decimal(str(data.get("amount", 0))) / 100
        return PaystackVerifyResponse(
            reference=data.get("reference", reference),
            status=data.get("status", "unknown"),
            amount_zar=amount_zar,
            paid_at=data.get("paid_at"),
            channel=data.get("channel"),
        )


# ---------------------------------------------------------------------------
# POST /payments/paystack/webhook — Paystack webhook handler
# ---------------------------------------------------------------------------

def _verify_webhook_signature(body: bytes, signature: str) -> bool:
    """Verify HMAC SHA-512 signature from Paystack."""
    if not PAYSTACK_WEBHOOK_SECRET:
        return True  # skip in dev
    expected = hmac.new(
        PAYSTACK_WEBHOOK_SECRET.encode(), body, hashlib.sha512
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


@router.post("/webhook", status_code=200)
async def paystack_webhook(
    request: Request,
    x_paystack_signature: Optional[str] = Header(None),
):
    """Handle Paystack webhook callbacks.

    This endpoint is public (bypasses entitlement guard via public_paths config).
    """
    raw_body = await request.body()

    if x_paystack_signature and not _verify_webhook_signature(raw_body, x_paystack_signature):
        raise HTTPException(status_code=400, detail="Invalid signature")

    import json
    payload = json.loads(raw_body)
    event = payload.get("event", "")
    data = payload.get("data", {})

    logger.info("Paystack webhook: event=%s ref=%s", event, data.get("reference"))

    if event == "charge.success":
        await _handle_charge_success(data)
    elif event == "transfer.success":
        logger.info("Transfer success: %s", data.get("reference"))
    # Add more event handlers as needed

    return {"status": "accepted"}


async def _handle_charge_success(data: dict) -> None:
    """Process a successful charge — record payment and update invoice."""
    metadata = data.get("metadata", {})
    invoice_id_raw = metadata.get("invoice_id")
    tenant_id_raw = metadata.get("tenant_id")
    if not invoice_id_raw or not tenant_id_raw:
        logger.warning("Webhook charge.success missing invoice/tenant metadata")
        return

    import uuid as _uuid
    invoice_id = _uuid.UUID(invoice_id_raw)
    tenant_id = _uuid.UUID(tenant_id_raw)
    amount_zar = Decimal(str(data.get("amount", 0))) / 100
    reference = data.get("reference", "")

    with get_session() as session:
        inv = (
            session.query(Invoice)
            .filter(Invoice.id == invoice_id, Invoice.tenant_id == tenant_id)
            .first()
        )
        if not inv:
            logger.warning("Webhook: invoice %s not found", invoice_id)
            return

        payment = Payment(
            tenant_id=tenant_id,
            invoice_id=inv.id,
            customer_id=inv.customer_id,
            amount_zar=amount_zar,
            method="card",
            reference=reference,
            paystack_ref=reference,
            status="completed",
        )
        session.add(payment)

        inv.amount_paid_zar += amount_zar
        if inv.amount_paid_zar >= inv.total_zar:
            inv.status = "paid"
        elif inv.amount_paid_zar > 0:
            inv.status = "partially_paid"

        session.flush()
        logger.info(
            "Payment recorded: invoice=%s amount=R%.2f status=%s",
            inv.number, amount_zar, inv.status,
        )

        # If fully paid and was overdue, trigger reinstatement
        if inv.status == "paid":
            _trigger_auto_reinstate(tenant_id, inv.customer_id)


def _trigger_auto_reinstate(tenant_id, customer_id) -> None:
    """Notify Network service to reinstate customer service after payment."""
    network_url = os.getenv("NETWORK_SERVICE_URL", "http://network:8005")
    try:
        with httpx.Client(timeout=5.0) as client:
            client.post(
                f"{network_url}/services/reinstate-by-customer",
                json={"customer_id": str(customer_id)},
                headers={
                    "X-User-Id": "00000000-0000-0000-0000-000000000000",
                    "X-Tenant-Id": str(tenant_id),
                },
            )
    except Exception as exc:
        logger.error("Auto-reinstate failed for customer %s: %s", customer_id, exc)
