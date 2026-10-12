"""Sanitised platform billing facts on the transactional outbox."""
import hashlib
import json
from sqlalchemy import text
from services.common.event_bus import publish

PREFIX = "platform.billing."
SOURCE = "platform_billing"
EVENTS = frozenset(PREFIX + name for name in (
    "credits.low", "credits.exhausted", "credits.topped_up",
    "subscription.payment_failed", "plan.activated", "payment.review",
))

async def emit(db, tenant, name, payload, key, subject):
    event = PREFIX + name
    if event not in EVENTS:
        raise ValueError("Unknown platform billing event")
    return await publish(db, tenant, event, payload, source=SOURCE,
                         idempotency_key="platform-billing:" + key, subject=subject)

async def credits_checkpoint(db, tenant):
    """Once per billing period and severity; only published paid metering alerts."""
    from services.common import platform_credits as credits, platform_commerce as commerce
    if not (await credits.policy(db))["enabled"]:
        return
    await commerce.tenant_lock(db, tenant)
    active = (await db.execute(text("SELECT * FROM platform_usage_entitlements WHERE tenant_id=:t"), {"t": str(tenant)})).mappings().first()
    start, end, allowance = credits.window(active)
    used = int((await db.execute(text("SELECT coalesce(sum(credits),0) FROM platform_usage_operations WHERE tenant_id=:t AND started_at>=:start AND started_at<:end"), {"t": str(tenant), "start": start, "end": end})).scalar_one())
    reserved = int((await db.execute(text("SELECT coalesce(sum(reserved_credits),0) FROM platform_usage_operations WHERE tenant_id=:t AND status='running'"), {"t": str(tenant)})).scalar_one())
    purchased = await credits.balance(db, tenant)
    available = max(0, max(0, allowance-used)+purchased-reserved)
    # Purchased credits are part of spendable capacity, not a second included allowance.
    prepaid_capacity = int((await db.execute(text("""SELECT
        coalesce(sum(credits) FILTER(WHERE created_at<:start),0)+
        coalesce(sum(credits) FILTER(WHERE created_at>=:start AND credits>0),0)
        FROM platform_credit_entries WHERE tenant_id=:t"""), {"t":str(tenant),"start":start})).scalar_one())
    capacity = allowance+max(0,prepaid_capacity)
    threshold = max(10, (capacity+4)//5)
    name = "credits.exhausted" if available == 0 else "credits.low" if available <= threshold else None
    if name:
        await emit(db, tenant, name, {"available": available, "allocated": allowance,
            "used": used, "purchased_remaining": purchased, "reserved": reserved,
            "threshold": threshold,"capacity":capacity, "period_start": start.isoformat(), "period_end": end.isoformat()},
            f"{name}:{start.isoformat()}", ("tenant", tenant))

async def payment_failed(db, subscription, data):
    # Exclude authorisation data, card details, email tokens and customer records.
    identity = {key: data.get(key) for key in ("id", "reference", "invoice_code", "due_date", "period_start", "period_end", "created_at") if data.get(key) is not None}
    if not identity:
        tenant = (await db.execute(text("SELECT settings FROM tenants WHERE id=:t"), {"t": str(subscription["tenant_id"])})).scalar_one()
        identity = {"period_end": (tenant or {}).get("platform_pricing", {}).get("period_end")}
    fingerprint = hashlib.sha256(json.dumps(identity, sort_keys=True, default=str).encode()).hexdigest()
    await emit(db, subscription["tenant_id"], "subscription.payment_failed",
        {"order_id": str(subscription["order_id"]), "status": "past_due", "provider": "paystack"},
        f"payment-failed:{subscription['order_id']}:{fingerprint}", ("platform_order", subscription["order_id"]))
