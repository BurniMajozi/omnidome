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
