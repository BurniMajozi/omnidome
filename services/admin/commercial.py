"""Tenant usage views and Platform Owner policy/cost management."""
import json
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from services.common.auth import AuthContext, get_auth_context
from services.common.db import get_async_session
from services.common.platform_pricing import catalog
from services.common.platform_usage import add_months, autumn_sync_enabled, queue_optional_sync
from services.common import platform_commerce
from services.admin import iam
from services.common.provider_pricing import draft_rate_card

router = APIRouter(tags=["Platform usage"])


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
        end = min(add_months(anchor,index+1), active["expires_at"])
        if active["expires_at"] <= now:
            policy["monthly_credits"] = 0
    summary = (await db.execute(text("""SELECT coalesce(sum(credits),0) AS used,
      count(*) FILTER (WHERE status='running') AS running FROM platform_usage_operations
      WHERE tenant_id=:t AND started_at>=:start AND started_at<:end"""), {"t": str(tenant), "start": start, "end": end})).mappings().one()
    recent = (await db.execute(text("SELECT id,kind,credits,status,started_at,completed_at FROM platform_usage_operations WHERE tenant_id=:t ORDER BY started_at DESC LIMIT 20"), {"t": str(tenant)})).mappings().all()
    sync = (await db.execute(text("SELECT status,error_code,attempts FROM platform_usage_outbox WHERE tenant_id=:t AND action='reconcile' ORDER BY created_at DESC LIMIT 1"), {"t": str(tenant)})).mappings().first()
    return {"policy": policy, "period_start": start, "period_end": end, "used": summary["used"],
            "remaining": max(0, policy["monthly_credits"]-int(summary["used"])), "running": summary["running"],
            "source": active["source"] if active else "legacy", "sync": dict(sync) if sync else None,
            "recent": [dict(row) for row in recent], "charges_enabled": False,
            "entitlement_authority": "postgres", "autumn_sync_enabled": autumn_sync_enabled()}


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
    if active["expires_at"] <= now:
        raise HTTPException(409, "Renew or explicitly provision the plan before changing its allowance")
    policy = {**active["policy"], "monthly_credits": body.monthly_credits}
    ident = uuid.uuid4()
    await db.execute(text("""INSERT INTO platform_usage_policy_versions(id,tenant_id,policy,actor_id,reason,expires_at)
      VALUES(:id,:t,CAST(:p AS jsonb),:actor,:reason,:expiry)"""),
      {"id": str(ident), "t": str(tenant), "p": json.dumps(policy), "actor": str(ctx.user_id), "reason": body.reason, "expiry": body.expires_at})
    # Override can expire earlier than paid access but cannot extend a paid grant.
    expiry = min(body.expires_at, active["expires_at"])
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
