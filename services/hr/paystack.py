"""Paystack Transfers integration for HR payroll (outbound payouts).

This is the *outbound* direction (paying money OUT to employees), distinct
from services/billing/routes/paystack.py which handles *inbound* collections
(charging customers). Two Paystack primitives are used:

  1. Transfer Recipient  (POST /transferrecipient)  -> RCP_xxx code
  2. Transfer            (POST /transfer)            -> TRF_xxx code + status

Amounts are sent in the currency's minor unit (ZAR cents). Business-level
Paystack failures (e.g. insufficient balance on a test account) are returned
as structured results, not raised — the caller records them on the payslip.
Genuine transport errors raise PaystackError.
"""

import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger("hr.paystack")

PAYSTACK_BASE = "https://api.paystack.co"
# South-African bank accounts use the "basa" recipient type on Paystack.
DEFAULT_RECIPIENT_TYPE = "basa"


def _secret() -> str:
    return os.getenv("PAYSTACK_SECRET_KEY", "")


def is_configured() -> bool:
    return bool(_secret())


def _headers() -> dict:
    return {"Authorization": f"Bearer {_secret()}", "Content-Type": "application/json"}


class PaystackError(Exception):
    """Raised on transport/gateway failures (not on Paystack business errors)."""


async def create_transfer_recipient(
    name: str,
    account_number: str,
    bank_code: str,
    currency: str = "ZAR",
) -> dict:
    """Create (or reuse) a Paystack transfer recipient.

    Returns {"ok": bool, "recipient_code": str|None, "message": str}.
    In dev with no key configured, returns a deterministic mock code so the
    payroll flow is exercisable end-to-end offline.
    """
    if not is_configured():
        mock = "RCP_MOCK_" + (account_number or "0")[-6:]
        logger.warning("PAYSTACK_SECRET_KEY not set; returning mock recipient %s", mock)
        return {"ok": True, "recipient_code": mock, "message": "mock (no key configured)"}

    payload = {
        "type": DEFAULT_RECIPIENT_TYPE,
        "name": name,
        "account_number": account_number,
        "bank_code": bank_code,
        "currency": currency,
    }
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                f"{PAYSTACK_BASE}/transferrecipient", json=payload, headers=_headers()
            )
    except httpx.HTTPError as exc:
        raise PaystackError(f"transfer recipient request failed: {exc}") from exc

    body = resp.json() if resp.content else {}
    if resp.status_code in (200, 201) and body.get("status"):
        data = body.get("data", {})
        return {
            "ok": True,
            "recipient_code": data.get("recipient_code"),
            "message": body.get("message", "recipient created"),
        }
    return {
        "ok": False,
        "recipient_code": None,
        "message": body.get("message", f"paystack error ({resp.status_code})"),
    }


async def initiate_transfer(
    amount_zar: float,
    recipient_code: str,
    reason: str,
    reference: Optional[str] = None,
) -> dict:
    """Initiate a Paystack transfer to a recipient.

    Returns {"ok": bool, "transfer_code": str|None, "status": str, "reference": str|None,
             "message": str}. `status` mirrors Paystack ("pending"/"success"/"otp"/...).
    A business failure (e.g. insufficient balance) returns ok=False with the
    Paystack message rather than raising, so the caller can mark the payslip FAILED.
    """
    if not is_configured():
        ref = reference or "mock"
        logger.warning("PAYSTACK_SECRET_KEY not set; simulating transfer %s", ref)
        return {
            "ok": True,
            "transfer_code": "TRF_MOCK_" + ref[-8:],
            "status": "success",
            "reference": ref,
            "message": "mock (no key configured)",
        }

    payload = {
        "source": "balance",
        "amount": int(round(amount_zar * 100)),  # ZAR -> cents
        "recipient": recipient_code,
        "reason": reason,
    }
    if reference:
        payload["reference"] = reference
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                f"{PAYSTACK_BASE}/transfer", json=payload, headers=_headers()
            )
    except httpx.HTTPError as exc:
        raise PaystackError(f"transfer request failed: {exc}") from exc

    body = resp.json() if resp.content else {}
    if resp.status_code in (200, 201) and body.get("status"):
        data = body.get("data", {})
        return {
            "ok": True,
            "transfer_code": data.get("transfer_code"),
            "status": data.get("status", "pending"),
            "reference": data.get("reference", reference),
            "message": body.get("message", "transfer queued"),
        }
    return {
        "ok": False,
        "transfer_code": None,
        "status": "failed",
        "reference": reference,
        "message": body.get("message", f"paystack error ({resp.status_code})"),
    }


# ---------------------------------------------------------------------------
# Funded payouts through billing (the default). Paystack transfers are paid out of OmniDome's own balance, so
# payroll only goes out of the tenant's pre-funded payout wallet (services/billing/routes/payouts.py), which also
# applies OmniDome's fee and sends one bulk transfer instead of one request per employee.
# ---------------------------------------------------------------------------

def payout_mode() -> str:
    """'funded' (default: pay from the tenant's payout wallet via billing) or 'direct' (legacy: one transfer per
    payslip straight from the platform balance, no funding check and no fee: development only)."""
    return "direct" if os.getenv("PAYROLL_PAYOUT_MODE", "funded").strip().lower() == "direct" else "funded"


class InsufficientFunding(Exception):
    """The tenant's payout wallet cannot cover the run plus the fee. `detail` carries required / balance / shortfall."""

    def __init__(self, detail):
        super().__init__("payout wallet is short")
        self.detail = detail


def _billing_headers() -> dict:
    key = os.getenv("INTERNAL_SERVICE_KEY", "")
    if not key:
        raise PaystackError("INTERNAL_SERVICE_KEY is not configured: cannot reach billing payouts")
    return {"x-internal-key": key, "Content-Type": "application/json"}


def _billing_url() -> str:
    return os.getenv("BILLING_SERVICE_URL", "http://billing:8003").rstrip("/")


async def funded_batch(tenant_id, user_id, source_id: str, items: list, kind: str = "payroll") -> dict:
    """Create + execute a payout batch in billing. items: [{item_ref, recipient_code, amount_zar(str), reason, reference}]."""
    body = {"tenant_id": str(tenant_id), "kind": kind, "source_id": source_id,
            "requested_by": str(user_id) if user_id else None, "items": items}
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(f"{_billing_url()}/payouts/internal/batches", json=body, headers=_billing_headers())
    except httpx.HTTPError as exc:
        raise PaystackError(f"payout request failed: {exc}") from exc
    data = resp.json() if resp.content else {}
    if resp.status_code == 402:
        raise InsufficientFunding(data.get("detail"))
    if resp.status_code in (409, 422, 503):
        detail = data.get("detail")
        raise PaystackError(str(detail.get("message") if isinstance(detail, dict) else detail))
    if resp.status_code != 200:
        raise PaystackError(f"billing payouts returned HTTP {resp.status_code}")
    return data


async def funded_status(tenant_id, source_id: str, kind: str = "payroll", reconcile: bool = True) -> dict:
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.get(f"{_billing_url()}/payouts/internal/by-source", headers=_billing_headers(),
                                    params={"tenant_id": str(tenant_id), "kind": kind, "source_id": source_id,
                                            "reconcile": str(reconcile).lower()})
    except httpx.HTTPError as exc:
        raise PaystackError(f"payout status request failed: {exc}") from exc
    if resp.status_code != 200:
        raise PaystackError(f"billing payouts returned HTTP {resp.status_code}")
    return resp.json()
