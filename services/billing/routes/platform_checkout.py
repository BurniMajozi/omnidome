"""Paystack broker for platform tenant invoices; never uses ISP customer accounts."""
import os
import uuid
from urllib.parse import urlparse
import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text
from services.common.auth import AuthContext, get_auth_context
from services.common.db import get_async_session, session_scope
from services.common import rbac, platform_commerce as commerce

router = APIRouter(prefix="/platform-checkout", tags=["Platform checkout"])
PUBLIC_PATHS = {"/platform-checkout/initialize", "/platform-checkout/verify", "/platform-checkout/cancel"}
# These bypass the ISP Billing panel entitlement only. Each route requires verified
# identity, authoritative organisation-admin RBAC and tenant ownership below.


class OrderId(BaseModel):
    model_config = ConfigDict(extra="forbid")
    order_id: uuid.UUID


async def authorize(ctx, db):
    await rbac._load_rbac(ctx, db)
    if "platform_admin" in ctx.roles or "platform.admin" in ctx.permissions: return
    member = (await db.execute(text("SELECT 1 FROM users WHERE id=:u AND tenant_id=:t AND is_active"), {"u": str(ctx.user_id), "t": str(ctx.tenant_id)})).first()
    if not member or not ({"owner", "org_admin"} & set(ctx.roles)):
        raise HTTPException(403, "Organisation Admin or Platform Owner required")


async def provider(method, path, body=None):
    key = os.getenv("PAYSTACK_SECRET_KEY", "")
    if not key: raise HTTPException(503, "Paystack is not configured; your invoice is saved")
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.request(method, "https://api.paystack.co" + path,
                headers={"Authorization": "Bearer " + key}, json=body)
    except httpx.HTTPError: raise HTTPException(503, "Paystack is unavailable; retry the saved invoice")
    try: result = response.json()
    except ValueError: raise HTTPException(502, "Invalid payment provider response")
    if response.status_code >= 400 or result.get("status") is not True:
        raise HTTPException(502, "Payment provider rejected the request")
    return result.get("data") or {}


async def load_order(db, ctx, ident):
    await authorize(ctx, db)
    await commerce.tenant_lock(db, ctx.tenant_id)
    row = (await db.execute(text("SELECT * FROM platform_orders WHERE id=:id AND tenant_id=:t FOR UPDATE"), {"id": str(ident), "t": str(ctx.tenant_id)})).mappings().first()
    if not row: raise HTTPException(404, "Invoice not found")
    return dict(row)


@router.post("/initialize")
async def initialize(body: OrderId, ctx: AuthContext = Depends(get_auth_context), db=Depends(get_async_session)):
    order = await load_order(db, ctx, body.order_id)
    current = commerce.state(await commerce.tenant_lock(db, ctx.tenant_id))
    if order["paid_at"]: raise HTTPException(409, "Invoice already paid")
    if current.get("revision") != order["revision"]: raise HTTPException(409, "Selection changed; pay the latest invoice")
    if order["quote"]["amount_cents"] <= 0: raise HTTPException(409, "Free selections do not require checkout")
    if order["checkout_url"]: return {"authorization_url": order["checkout_url"], "reference": order["reference"]}
    email = (await db.execute(text("SELECT email FROM users WHERE id=:u AND is_active"), {"u": str(ctx.user_id)})).scalar_one_or_none()
    if not email: raise HTTPException(409, "An active billing administrator with an email is required")
    args = {"email": email, "amount": order["quote"]["amount_cents"], "currency": "ZAR", "reference": order["reference"],
            "metadata": {"platform_order_id": str(order["id"]), "tenant_id": str(ctx.tenant_id)}}
    site = os.getenv("APP_PUBLIC_URL", "http://localhost:3000").rstrip("/")
    if urlparse(site).scheme not in {"http", "https"}: raise HTTPException(503, "Invalid application URL")
    args["callback_url"] = site + "/checkout?order=" + str(order["id"])
    if order["intent"] == "subscription":
        sub = (await db.execute(text("SELECT * FROM platform_subscriptions WHERE tenant_id=:t AND status IN ('active','pending','past_due') ORDER BY updated_at DESC LIMIT 1 FOR UPDATE"), {"t": str(ctx.tenant_id)})).mappings().first()
        if sub and sub["status"] in {"active", "pending", "past_due"} and sub["order_id"] != order["id"]:
            raise HTTPException(409, "Cancel the existing platform subscription before starting another")
        plan_code = order.get("plan_code")
        if not plan_code:
            plan = await provider("POST", "/plan", {"name": "OminiDome " + order["reference"], "amount": args["amount"], "currency": "ZAR",
                "interval": "annually" if order["quote"]["period"] == "annually" else "monthly"})
            plan_code = plan.get("plan_code")
            if not isinstance(plan_code, str) or not plan_code.startswith("PLN_"): raise HTTPException(502, "Invalid subscription plan response")
        args["plan"] = plan_code
        await db.execute(text("UPDATE platform_orders SET plan_code=:p WHERE id=:id"), {"p": plan_code, "id": str(order["id"])})
        import json
        await db.execute(text("""INSERT INTO platform_subscriptions(tenant_id,order_id,plan_code,status,quote,revision)
          VALUES(:t,:id,:p,'pending',CAST(:q AS jsonb),:r) ON CONFLICT(order_id) DO UPDATE SET
          order_id=excluded.order_id,plan_code=excluded.plan_code,subscription_code=NULL,email_token=NULL,status='pending',quote=excluded.quote,revision=excluded.revision"""),
          {"t": str(ctx.tenant_id), "id": str(order["id"]), "p": plan_code, "q": json.dumps(order["quote"]), "r": order["revision"]})
    result = await provider("POST", "/transaction/initialize", args)
    url = result.get("authorization_url", "")
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "checkout.paystack.com" or result.get("reference") != order["reference"]:
        raise HTTPException(502, "Invalid payment checkout response")
    await db.execute(text("UPDATE platform_orders SET checkout_url=:url,status='checkout' WHERE id=:id"), {"url": url, "id": str(order["id"])})
    return {"authorization_url": url, "reference": order["reference"]}


@router.post("/verify")
async def verify(body: OrderId, ctx: AuthContext = Depends(get_auth_context), db=Depends(get_async_session)):
    order = await load_order(db, ctx, body.order_id)
    if order["paid_at"]: return {"status": order["status"], "duplicate": True}
    result = await provider("GET", "/transaction/verify/" + order["reference"])
    return await commerce.paid(db, order, result)


@router.post("/cancel")
async def cancel(body: OrderId, ctx: AuthContext = Depends(get_auth_context), db=Depends(get_async_session)):
    order = await load_order(db, ctx, body.order_id)
    sub = (await db.execute(text("SELECT * FROM platform_subscriptions WHERE tenant_id=:t AND order_id=:id FOR UPDATE"), {"t": str(ctx.tenant_id), "id": str(order["id"])})).mappings().first()
    if not sub: raise HTTPException(404, "Subscription not found")
    if sub["status"] == "cancelled": return {"status": "cancelled"}
    if sub["subscription_code"] and sub["email_token"]:
        await provider("POST", "/subscription/disable", {"code": sub["subscription_code"], "token": sub["email_token"]})
    elif sub["status"] != "pending":
        raise HTTPException(409, "Subscription is awaiting provider confirmation")
    if sub["status"] == "pending":
        tenant = await commerce.tenant_lock(db, ctx.tenant_id)
        current = commerce.state(tenant)
        import json
        settings = {**(tenant["settings"] or {}), "platform_pricing": {**current, "revision": int(current.get("revision", 0)) + 1}}
        await db.execute(text("UPDATE tenants SET settings=CAST(:s AS jsonb) WHERE id=:t"), {"s": json.dumps(settings), "t": str(ctx.tenant_id)})
        await db.execute(text("UPDATE platform_orders SET status='cancelled' WHERE id=:id"), {"id": str(order["id"])})
    await db.execute(text("UPDATE platform_subscriptions SET status='cancelled',updated_at=now() WHERE order_id=:id"), {"id": str(order["id"])})
    return {"status": "cancelled"}


async def handle_event(event, data):
    """Called only after the existing Paystack webhook HMAC has been checked."""
    reference = str(data.get("reference") or "")
    plan = data.get("plan") or {}
    plan_code = plan.get("plan_code") if isinstance(plan, dict) else plan
    if not isinstance(plan_code, str) or not plan_code.startswith("PLN_"):
        plan_code = (data.get("plan_object") or {}).get("plan_code") if isinstance(data.get("plan_object"), dict) else None
    if not isinstance(plan_code, str) or not plan_code.startswith("PLN_"): plan_code = None
    subscription = data.get("subscription") or data
    code = subscription.get("subscription_code") if isinstance(subscription, dict) else None
    if not isinstance(code, str) or not code.startswith("SUB_"): code = None
    if not reference.startswith("ODP-") and not plan_code and not code: return None
    async with session_scope() as db:
        row = None
        if reference.startswith("ODP-"):
            row = (await db.execute(text("SELECT * FROM platform_orders WHERE reference=:r"), {"r": reference})).mappings().first()
            if not row: return "ignored_platform_reference"
        sub = None
        if plan_code or code:
            sub = (await db.execute(text("SELECT * FROM platform_subscriptions WHERE plan_code=:p OR subscription_code=:c"), {"p": plan_code, "c": code})).mappings().first()
        if event == "charge.success" and row:
            return (await commerce.paid(db, dict(row), data))["status"]
        if not sub: return None
        await commerce.tenant_lock(db, sub["tenant_id"])
        if event == "subscription.create":
            # An abandoned pending checkout can complete late. Disable its
            # provider subscription rather than resurrect recurring billing.
            if sub["status"] == "cancelled" and data.get("subscription_code") and data.get("email_token"):
                await provider("POST", "/subscription/disable", {"code": data["subscription_code"], "token": data["email_token"]})
            await db.execute(text("UPDATE platform_subscriptions SET subscription_code=:c,email_token=:token,updated_at=now() WHERE order_id=:id"),
                             {"c": data.get("subscription_code"), "token": data.get("email_token"), "id": str(sub["order_id"])})
        elif event in {"subscription.disable", "subscription.not_renew", "invoice.payment_failed"}:
            await db.execute(text("UPDATE platform_subscriptions SET status=:s,updated_at=now() WHERE order_id=:id"),
                             {"s": "past_due" if event == "invoice.payment_failed" else "cancelled", "id": str(sub["order_id"])})
        elif event == "charge.success":
            # Renewal references are provider generated. Freeze a separate invoice
            # per charge, keeping its original commercial revision for stale checks.
            if not reference or len(reference) > 200: raise HTTPException(409, "Invalid renewal reference")
            original = (await db.execute(text("SELECT actor_id FROM platform_orders WHERE id=:id"), {"id": str(sub["order_id"])})).scalar_one()
            import json
            await db.execute(text("""INSERT INTO platform_orders(id,tenant_id,actor_id,idempotency_key,reference,intent,quote,revision,plan_code)
              VALUES(:id,:t,:actor,:key,:ref,'renewal',CAST(:q AS jsonb),:rev,:plan) ON CONFLICT(reference) DO NOTHING"""),
              {"id": str(uuid.uuid4()), "t": str(sub["tenant_id"]), "actor": str(original), "key": str(uuid.uuid4()), "ref": reference,
               "q": json.dumps(sub["quote"]), "rev": sub["revision"], "plan": sub["plan_code"]})
            renewal = (await db.execute(text("SELECT * FROM platform_orders WHERE reference=:r"), {"r": reference})).mappings().one()
            if renewal["tenant_id"] != sub["tenant_id"]: raise HTTPException(409, "Renewal reference mismatch")
            return (await commerce.paid(db, dict(renewal), data, force_review=sub["status"] == "cancelled"))["status"]
        return "accepted_platform_event"
