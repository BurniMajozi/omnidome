"""Paystack recurring billing — Plans & Subscriptions.

Complements routes/paystack.py (one-off charges) with recurring billing:

  - A BillingPlan is mirrored to a Paystack Plan (POST /plan) -> PLN_xxx, stored
    on billing_plans.paystack_plan_code.
  - A customer is subscribed to that plan (POST /subscription) -> SUB_xxx, stored
    on our subscriptions row alongside the customer code + email token.

Creating a Paystack subscription requires the customer's saved `authorization`
(a card token from a prior successful charge via routes/paystack.py). Renewals
then arrive as `charge.success` / `invoice.*` webhooks (handled in paystack.py).

Amounts are in ZAR cents. No key configured -> deterministic mock codes so the
flow is exercisable offline.
"""

import logging
import os
from decimal import Decimal
from typing import Optional

import uuid
import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from services.common.auth import AuthContext, get_auth_context
from services.billing.database import get_session
from services.billing.models import BillingPlan, Subscription

logger = logging.getLogger("billing.paystack.recurring")

router = APIRouter(prefix="/payments/paystack", tags=["Paystack Recurring"])

PAYSTACK_BASE = "https://api.paystack.co"

# billing_cycle -> Paystack plan interval
_INTERVAL_MAP = {
    "MONTHLY": "monthly",
    "WEEKLY": "weekly",
    "ANNUAL": "annually",
    "ANNUALLY": "annually",
    "YEARLY": "annually",
    "DAILY": "daily",
    "QUARTERLY": "quarterly",
    "BIANNUAL": "biannually",
}


def _secret() -> str:
    return os.getenv("PAYSTACK_SECRET_KEY", "")


def _headers() -> dict:
    return {"Authorization": f"Bearer {_secret()}", "Content-Type": "application/json"}


async def _paystack(method: str, path: str, json_body: Optional[dict] = None) -> dict:
    """Thin Paystack call. Returns the parsed body; raises HTTPException(502) on transport error."""
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.request(method, f"{PAYSTACK_BASE}{path}", json=json_body, headers=_headers())
    except httpx.HTTPError as exc:
        logger.error("Paystack %s %s failed: %s", method, path, exc)
        raise HTTPException(status_code=502, detail="Payment gateway unreachable") from exc
    body = resp.json() if resp.content else {}
    body["_http_status"] = resp.status_code
    return body


class PaystackPlanSync(BaseModel):
    interval: Optional[str] = None  # override BillingPlan.billing_cycle if set


class PaystackSubscribeRequest(BaseModel):
    subscription_id: Optional[uuid.UUID] = None  # our subscriptions row to link
    customer_code: str                            # CUS_xxx (Paystack customer)
    plan_code: str                                # PLN_xxx (Paystack plan)
    authorization_code: Optional[str] = None      # AUTH_xxx from a prior charge
    start_date: Optional[str] = None              # ISO8601; optional


class DisableSubscriptionRequest(BaseModel):
    email_token: str


# ---------------------------------------------------------------------------
# POST /payments/paystack/plans/{plan_id}/sync  — mirror a BillingPlan to Paystack
# ---------------------------------------------------------------------------

@router.post("/plans/{plan_id}/sync")
async def sync_plan_to_paystack(
    plan_id: uuid.UUID,
    body: PaystackPlanSync,
    ctx: AuthContext = Depends(get_auth_context),
):
    with get_session() as session:
        plan = session.execute(
            select(BillingPlan).where(BillingPlan.id == plan_id, BillingPlan.tenant_id == ctx.tenant_id)
        ).scalar_one_or_none()
        if not plan:
            raise HTTPException(status_code=404, detail="Billing plan not found")
        name = plan.name
        amount_cents = int(Decimal(str(plan.price)) * 100)
        currency = plan.currency or "ZAR"
        cycle = (body.interval or plan.billing_cycle or "MONTHLY").upper()

    interval = _INTERVAL_MAP.get(cycle, "monthly")

    if not _secret():
        code = "PLN_MOCK_" + str(plan_id)[:8]
        logger.warning("PAYSTACK_SECRET_KEY not set; mock plan %s", code)
    else:
        res = await _paystack("POST", "/plan", {
            "name": name, "amount": amount_cents, "interval": interval, "currency": currency,
        })
        if not res.get("status"):
            raise HTTPException(status_code=502, detail=res.get("message", "Paystack plan create failed"))
        code = res.get("data", {}).get("plan_code")

    with get_session() as session:
        plan = session.execute(
            select(BillingPlan).where(BillingPlan.id == plan_id, BillingPlan.tenant_id == ctx.tenant_id)
        ).scalar_one_or_none()
        plan.paystack_plan_code = code
        session.commit()

    return {"plan_id": str(plan_id), "paystack_plan_code": code, "interval": interval, "amount_zar": amount_cents / 100}


# ---------------------------------------------------------------------------
# POST /payments/paystack/subscriptions  — subscribe a customer to a plan
# ---------------------------------------------------------------------------

@router.post("/subscriptions")
async def create_subscription(
    body: PaystackSubscribeRequest,
    ctx: AuthContext = Depends(get_auth_context),
):
    payload = {"customer": body.customer_code, "plan": body.plan_code}
    if body.authorization_code:
        payload["authorization"] = body.authorization_code
    if body.start_date:
        payload["start_date"] = body.start_date

    if not _secret():
        sub_code = "SUB_MOCK_" + body.customer_code[-6:]
        email_token = "mock_token"
        logger.warning("PAYSTACK_SECRET_KEY not set; mock subscription %s", sub_code)
    else:
        res = await _paystack("POST", "/subscription", payload)
        if not res.get("status"):
            raise HTTPException(status_code=502, detail=res.get("message", "Paystack subscription failed"))
        data = res.get("data", {})
        sub_code = data.get("subscription_code")
        email_token = data.get("email_token")

    linked = None
    if body.subscription_id:
        with get_session() as session:
            sub = session.execute(
                select(Subscription).where(
                    Subscription.id == body.subscription_id, Subscription.tenant_id == ctx.tenant_id
                )
            ).scalar_one_or_none()
            if sub:
                sub.paystack_subscription_code = sub_code
                sub.paystack_customer_code = body.customer_code
                sub.paystack_email_token = email_token
                session.commit()
                linked = str(sub.id)

    return {
        "paystack_subscription_code": sub_code,
        "email_token": email_token,
        "linked_subscription_id": linked,
    }


# ---------------------------------------------------------------------------
# GET /payments/paystack/subscriptions/{code}  — fetch status
# ---------------------------------------------------------------------------

@router.get("/subscriptions/{code}")
async def get_subscription(code: str, ctx: AuthContext = Depends(get_auth_context)):
    if not _secret():
        return {"subscription_code": code, "status": "active", "mock": True}
    res = await _paystack("GET", f"/subscription/{code}")
    if not res.get("status"):
        raise HTTPException(status_code=404, detail=res.get("message", "Subscription not found"))
    d = res.get("data", {})
    return {
        "subscription_code": d.get("subscription_code", code),
        "status": d.get("status"),
        "next_payment_date": d.get("next_payment_date"),
        "amount": (d.get("amount") or 0) / 100,
    }


# ---------------------------------------------------------------------------
# POST /payments/paystack/subscriptions/{code}/disable
# ---------------------------------------------------------------------------

@router.post("/subscriptions/{code}/disable")
async def disable_subscription(
    code: str,
    body: DisableSubscriptionRequest,
    ctx: AuthContext = Depends(get_auth_context),
):
    if _secret():
        res = await _paystack("POST", "/subscription/disable", {"code": code, "token": body.email_token})
        if not res.get("status"):
            raise HTTPException(status_code=502, detail=res.get("message", "Disable failed"))

    # Reflect on our linked row, if any.
    with get_session() as session:
        sub = session.execute(
            select(Subscription).where(
                Subscription.paystack_subscription_code == code, Subscription.tenant_id == ctx.tenant_id
            )
        ).scalar_one_or_none()
        if sub:
            sub.status = "cancelled"
            session.commit()

    return {"subscription_code": code, "status": "disabled"}
