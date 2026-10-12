"""Tenant usage views and Platform Owner policy/cost management."""
import json
import asyncio
import logging
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from services.common.auth import AuthContext, get_auth_context
from services.common.db import get_async_session, session_scope
from services.common.platform_pricing import catalog
from services.common.platform_usage import add_months, autumn_sync_enabled, queue_optional_sync
from services.common import platform_commerce
from services.admin import iam
from services.common.provider_pricing import draft_rate_card

router = APIRouter(tags=["Platform usage"])


async def sweep_abandoned(db):
    await db.execute(text("UPDATE platform_usage_operations SET status='abandoned',completed_at=now() WHERE status='running' AND started_at<now()-interval '2 hours'"))


async def usage_sweep_loop():
    while True:
        await asyncio.sleep(60)
        try:
            async with session_scope() as db:
                await sweep_abandoned(db)
                from services.common.platform_trials import sweep
                await sweep(db)
            from services.admin.platform_onboarding import deliver_notices
            await deliver_notices()
        except Exception:
            logging.getLogger("admin").warning("Usage cleanup failed; retrying next minute")


async def member_scope(ctx, tenant, db):
    if ctx.is_platform_admin or await iam.has_permission(ctx,"platform.admin",db) or await iam.has_role(ctx,"platform_admin",db):
        return
    if str(ctx.tenant_id) != str(tenant):
        raise HTTPException(403, "Tenant scope mismatch")
    user = (await db.execute(text("SELECT 1 FROM users WHERE id=:u AND tenant_id=:t AND is_active=true"), {"u": str(ctx.user_id), "t": str(tenant)})).first()
    if not user:
        raise HTTPException(403, "Active tenant membership required")


@router.get("/tenants/{tenant}/usage")
async def usage(tenant: uuid.UUID, ctx: AuthContext = Depends(get_auth_context), db=Depends(get_async_session)):
    await member_scope(ctx, tenant, db)
    from services.common.platform_trials import expire
    await expire(db,tenant)
    # Recover abandoned measurement work without inventing credits or provider costs.
    await db.execute(text("UPDATE platform_usage_operations SET status='abandoned',completed_at=now() WHERE tenant_id=:t AND status='running' AND started_at<now()-interval '2 hours'"), {"t":str(tenant)})
    active = (await db.execute(text("SELECT * FROM platform_usage_entitlements WHERE tenant_id=:t"), {"t": str(tenant)})).mappings().first()
    now = datetime.now(timezone.utc)
    policy = dict(active["policy"]) if active else {**catalog()["usage_policy"], "monthly_credits": 0, "legacy": True}
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end = add_months(start, 1)
    if active:
        anchor = active["starts_at"]
        index = max(0, (now.year-anchor.year)*12+now.month-anchor.month)
        if add_months(anchor,index) > now:
            index = max(0,index-1)
        start = add_months(anchor,index)
        end = add_months(anchor,index+1) if policy.get("permanent_free") else min(add_months(anchor,index+1), active["expires_at"])
        if not policy.get("permanent_free") and active["expires_at"] <= now:
            policy["monthly_credits"] = 0
    summary = (await db.execute(text("""SELECT coalesce(sum(credits),0) AS used,
      count(*) FILTER (WHERE status='running') AS running FROM platform_usage_operations
      WHERE tenant_id=:t AND started_at>=:start AND started_at<:end"""), {"t": str(tenant), "start": start, "end": end})).mappings().one()
    recent = (await db.execute(text("SELECT id,panel,kind,credits,status,started_at,completed_at FROM platform_usage_operations WHERE tenant_id=:t ORDER BY started_at DESC LIMIT 20"), {"t": str(tenant)})).mappings().all()
    from services.common import platform_credits
    credit_policy = await platform_credits.policy(db)
    purchased = await platform_credits.balance(db,tenant)
    reserved = int((await db.execute(text("SELECT coalesce(sum(reserved_credits),0) FROM platform_usage_operations WHERE tenant_id=:t AND status='running'"), {"t":str(tenant)})).scalar_one())
    by_panel = (await db.execute(text("""SELECT panel,count(*) AS operations,coalesce(sum(credits),0) AS credits,
      count(*) FILTER(WHERE status='running') AS running FROM platform_usage_operations
      WHERE tenant_id=:t AND started_at>=:start AND started_at<:end GROUP BY panel ORDER BY sum(credits) DESC,panel"""), {"t":str(tenant),"start":start,"end":end})).mappings().all()
    sync = (await db.execute(text("SELECT status,error_code,attempts FROM platform_usage_outbox WHERE tenant_id=:t AND action='reconcile' ORDER BY created_at DESC LIMIT 1"), {"t": str(tenant)})).mappings().first()
    trial = (await db.execute(text("SELECT settings->'platform_trial' FROM tenants WHERE id=:t"),{"t":str(tenant)})).scalar_one_or_none()
    return {"policy": policy, "period_start": start, "period_end": end, "used": summary["used"],
            "remaining": max(0, policy["monthly_credits"]-int(summary["used"])), "running": summary["running"],
            "source": active["source"] if active else "legacy", "sync": dict(sync) if sync else None,
            "recent": [dict(row) for row in recent], "charges_enabled": credit_policy["enabled"] or bool(trial),
            "credit_wallet":{"purchased_remaining":purchased,"reserved":reserved,
                "available":max(0,max(0,policy["monthly_credits"]-int(summary["used"]))+purchased-reserved),
                "topup_policy":credit_policy},"by_panel":[dict(row) for row in by_panel],
            "entitlement_authority": "postgres", "autumn_sync_enabled": autumn_sync_enabled(),
            "panel_usage": [dict(row) for row in (await db.execute(text("""SELECT m.key AS module,tm.config,
              coalesce(u.writes,0) AS used FROM tenant_modules tm JOIN modules m ON m.id=tm.module_id
              LEFT JOIN platform_panel_usage u ON u.tenant_id=tm.tenant_id AND u.module=m.key AND u.period=date_trunc('month',now() AT TIME ZONE 'UTC')::date
              WHERE tm.tenant_id=:t AND tm.status IN ('ENABLED','TRIAL') AND tm.config ? 'writes_per_month' ORDER BY m.key"""), {"t":str(tenant)})).mappings().all()]}


@router.get("/tenants/{tenant}/usage/logs")
async def usage_logs(tenant: uuid.UUID, panel: str | None = Query(None,max_length=60), limit: int = Query(25,ge=1,le=100), offset: int = Query(0,ge=0,le=100000),
                     ctx: AuthContext = Depends(get_auth_context), db=Depends(get_async_session)):
    from services.admin.pricing import check_scope
    await check_scope(ctx,tenant,db)
    params = {"t":str(tenant),"panel":panel,"limit":limit,"offset":offset}
    where = "tenant_id=:t AND (CAST(:panel AS text) IS NULL OR panel=:panel)"
    total = (await db.execute(text("SELECT count(*) FROM platform_usage_operations WHERE "+where),params)).scalar_one()
    rows = (await db.execute(text("SELECT id,panel,kind,status,credits,measured_credits,reserved_credits,started_at,completed_at FROM platform_usage_operations WHERE "+where+" ORDER BY started_at DESC,id DESC LIMIT :limit OFFSET :offset"),params)).mappings().all()
    return {"total":total,"limit":limit,"offset":offset,"rows":[dict(row) for row in rows]}


class CreditPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = False
    price_per_credit_zar: str | None = Field(None,pattern=r"^\d{1,4}(\.\d{1,2})?$")
    operation_credit_limit: int = Field(100,ge=50,le=1000)


@router.get("/pricing/credits")
async def credit_policy_read(ctx: AuthContext = Depends(get_auth_context),db=Depends(get_async_session)):
    await iam.require_platform_admin(ctx,db)
    from services.common.platform_credits import policy
    return await policy(db)


@router.put("/pricing/credits")
async def credit_policy_update(body: CreditPolicy,ctx: AuthContext = Depends(get_auth_context),db=Depends(get_async_session)):
    from decimal import Decimal
    await iam.require_platform_admin(ctx,db)
    if body.enabled and (not body.price_per_credit_zar or not Decimal('0.01')<=Decimal(body.price_per_credit_zar)<=50):
        raise HTTPException(422,"Publish a credit price between R0.01 and R50")
    await db.execute(text("""INSERT INTO platform_credit_policy(singleton,policy,actor_id) VALUES(true,CAST(:p AS jsonb),:a)
      ON CONFLICT(singleton) DO UPDATE SET policy=excluded.policy,actor_id=excluded.actor_id,updated_at=now()"""), {"p":body.model_dump_json(),"a":str(ctx.user_id)})
    await iam.audit(db,ctx,"pricing.credits.publish","supplier",ctx.user_id,None,body.model_dump())
    return body


class CreditPurchase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    amount_zar: str = Field(pattern=r"^\d{1,6}(\.\d{1,2})?$")
    idempotency_key: uuid.UUID


@router.post("/tenants/{tenant}/usage/topups",status_code=201)
async def topup_order(tenant: uuid.UUID,body: CreditPurchase,ctx: AuthContext = Depends(get_auth_context),db=Depends(get_async_session)):
    from services.admin.pricing import check_scope,public_order
    from services.common.platform_credits import create_order
    await check_scope(ctx,tenant,db)
    order = await create_order(db,tenant,ctx.user_id,body.amount_zar,body.idempotency_key)
    await iam.audit(db,ctx,"tenant.credits.order","platform_order",order["id"],tenant,{"amount_zar":body.amount_zar})
    return public_order(order)


class DeliveryControl(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: str = Field(pattern=r"^(prepaid|auto_recharge)$")
    recharge_zar: int = Field(50,ge=50,le=100000)
    monthly_cap_zar: int = Field(500,ge=50,le=1000000)


class DeliveryControls(BaseModel):
    model_config = ConfigDict(extra="forbid")
    voice: DeliveryControl
    email: DeliveryControl


@router.get("/tenants/{tenant}/usage/delivery-controls")
async def delivery_controls_read(tenant: uuid.UUID,ctx: AuthContext = Depends(get_auth_context),db=Depends(get_async_session)):
    from services.admin.pricing import check_scope
    await check_scope(ctx,tenant,db)
    row = await platform_commerce.tenant_lock(db,tenant)
    saved = (row["settings"] or {}).get("platform_delivery_controls") or {}
    return {"preferences":{name:saved.get(name) or DeliveryControl(mode="prepaid").model_dump() for name in ("voice","email")},
        "capabilities":{name:{"prepaid_enforced":False,"auto_recharge_active":False,"reason":"Provider capacity metering and reusable-card recharge are not connected yet. These are saved preferences; no automatic charges are authorized."} for name in ("voice","email")}}


@router.put("/tenants/{tenant}/usage/delivery-controls")
async def delivery_controls_update(tenant: uuid.UUID,body: DeliveryControls,ctx: AuthContext = Depends(get_auth_context),db=Depends(get_async_session)):
    from services.admin.pricing import check_scope
    await check_scope(ctx,tenant,db)
    for control in (body.voice,body.email):
        if control.recharge_zar>control.monthly_cap_zar: raise HTTPException(422,"Recharge amount must not exceed the monthly cap")
    row = await platform_commerce.tenant_lock(db,tenant)
    settings = {**(row["settings"] or {}),"platform_delivery_controls":body.model_dump()}
    await db.execute(text("UPDATE tenants SET settings=CAST(:s AS jsonb) WHERE id=:t"),{"s":json.dumps(settings),"t":str(tenant)})
    await iam.audit(db,ctx,"tenant.delivery.preferences","tenant",tenant,tenant,body.model_dump())
    return await delivery_controls_read(tenant,ctx,db)


class PolicyOverride(BaseModel):
    model_config = ConfigDict(extra="forbid")
    monthly_credits: int = Field(ge=0, le=100000000)
    reason: str = Field(min_length=5, max_length=500)
    expires_at: datetime


@router.put("/tenants/{tenant}/usage/policy")
async def override(tenant: uuid.UUID, body: PolicyOverride, ctx: AuthContext = Depends(get_auth_context), db=Depends(get_async_session)):
    await iam.require_platform_admin(ctx, db)
    await platform_commerce.tenant_lock(db, tenant)
    now = datetime.now(timezone.utc)
    if body.expires_at.tzinfo is None or not now < body.expires_at <= add_months(now,12):
        raise HTTPException(422, "Choose an expiry in the next 12 months with a timezone")
    active = (await db.execute(text("SELECT * FROM platform_usage_entitlements WHERE tenant_id=:t FOR UPDATE"), {"t": str(tenant)})).mappings().first()
    if not active:
        raise HTTPException(409, "Provision a catalogue plan first")
    permanent_free = active["policy"].get("permanent_free",False)
    if not permanent_free and active["expires_at"] <= now:
        raise HTTPException(409, "Renew or explicitly provision the plan before changing its allowance")
    policy = {**active["policy"], "monthly_credits": body.monthly_credits}
    policy.pop("permanent_free",None)
    ident = uuid.uuid4()
    await db.execute(text("""INSERT INTO platform_usage_policy_versions(id,tenant_id,policy,actor_id,reason,expires_at)
      VALUES(:id,:t,CAST(:p AS jsonb),:actor,:reason,:expiry)"""),
      {"id": str(ident), "t": str(tenant), "p": json.dumps(policy), "actor": str(ctx.user_id), "reason": body.reason, "expiry": body.expires_at})
    # Override can expire earlier than paid access but cannot extend a paid grant.
    expiry = body.expires_at if permanent_free else min(body.expires_at, active["expires_at"])
    await db.execute(text("""UPDATE platform_usage_entitlements SET policy=CAST(:p AS jsonb),generation=:g,
      source='platform_owner',actor_id=:actor,reason=:reason,expires_at=:expiry,updated_at=now() WHERE tenant_id=:t"""),
      {"p": json.dumps(policy), "g": "policy:"+str(ident), "actor": str(ctx.user_id), "reason": body.reason, "expiry": expiry, "t": str(tenant)})
    await queue_optional_sync(db, tenant, "policy:"+str(ident), "policy:"+str(ident))
    await iam.audit(db,ctx,"tenant.usage_policy.override","tenant",tenant,tenant,{"version":str(ident),"reason":body.reason,"monthly_credits":body.monthly_credits})
    return {"version": ident, "policy": policy, "expires_at": expiry, "charges_enabled": False}


@router.get("/tenants/{tenant}/usage/costs")
async def costs(tenant: uuid.UUID, ctx: AuthContext = Depends(get_auth_context), db=Depends(get_async_session)):
    await iam.require_platform_admin(ctx, db)
    await platform_commerce.tenant_lock(db,tenant)
    rows = (await db.execute(text("""SELECT category,provider,currency,source,count(*) AS events,
      sum(quantity) AS quantity,unit,sum(amount) AS amount FROM platform_cost_events
      WHERE tenant_id=:t AND created_at>=now()-interval '30 days'
      AND NOT EXISTS(SELECT 1 FROM platform_provider_cost_allocations a
        JOIN platform_provider_allocation_voids v ON v.allocation_id=a.id WHERE a.cost_event_id=platform_cost_events.id)
      GROUP BY category,provider,currency,source,unit ORDER BY category,provider"""), {"t": str(tenant)})).mappings().all()
    return {"window_days":30,"costs":[dict(row) for row in rows],"margin_available":False,
            "margin_reason":"Provider, hosting, support and FX reconciliation must be complete before reporting margin.",
            "draft_rate_card":draft_rate_card()}
