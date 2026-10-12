"""OmniDome organisation trials; never ISP customer subscription trials."""
import json
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
from sqlalchemy import text
from services.common import platform_commerce as commerce
from services.common.platform_pricing import Selection, catalog, quote


def is_due(settings, now=None):
    trial = (settings or {}).get("platform_trial") or {}
    return trial.get("status") == "active" and datetime.fromisoformat(trial["ends_at"]) <= (now or datetime.now(timezone.utc))


async def start(db, tenant, actor, now=None, *, awaiting_owner=False):
    row = await commerce.tenant_lock(db, tenant)
    settings = row["settings"] or {}
    trial = settings.get("platform_trial")
    if trial:
        await expire(db, tenant, now=now)
        fresh = await commerce.tenant_lock(db,tenant)
        return (fresh["settings"] or {})["platform_trial"]
    current = commerce.state(row)
    active = current.get("active_quote")
    if current.get("billing_mode") == "payment" or (active and active["amount_cents"] > 0):
        raise HTTPException(409, "An existing paid or negotiated plan cannot be replaced by a trial")
    if (await db.execute(text("SELECT 1 FROM platform_orders WHERE tenant_id=:t AND paid_at IS NOT NULL AND quote->>'amount_cents' <> '0' LIMIT 1"), {"t":str(tenant)})).first():
        raise HTTPException(409, "This organisation has already used a paid plan")
    now = now or datetime.now(timezone.utc)
    end = now + timedelta(days=14)
    from services.common.platform_invoice import tax_policy
    selection = Selection(modules={m["id"]:"professional" for m in catalog()["modules"]}, seats=3)
    priced = quote(selection, await tax_policy(db))
    priced.update(name="OmniDome Professional trial", seats=3, seat_price="0.00", amount_cents=0,
                  total_zar="0.00", net_zar="0.00", vat_zar="0.00", monthly_net_zar="0.00", monthly_display_zar="0.00", lines=[])
    priced["usage_policy"]["monthly_credits"] = 50
    revision = int(current.get("revision",0)) + 1
    trial = {"status":"pending" if awaiting_owner else "active", "starts_at":now.isoformat(), "ends_at":end.isoformat(), "days":14,
             "credits":50, "seats":3, "fallback":"free", "started_by":str(actor)}
    await commerce.provision(db, tenant, priced, actor)
    from services.common.platform_usage import activate
    await activate(db, tenant, priced, "trial:"+str(tenant), revision, source="trial", actor=actor, now=now)
    await db.execute(text("UPDATE platform_usage_entitlements SET expires_at=:end WHERE tenant_id=:t"), {"end":end,"t":str(tenant)})
    settings = {**settings,"platform_trial":trial,"platform_pricing":{**current,"selection":priced["selection"],"quote":priced,
        "active_quote":priced,"revision":revision,"billing_mode":"trial","provisioned":True}}
    await db.execute(text("UPDATE tenants SET settings=CAST(:s AS jsonb) WHERE id=:t"), {"s":json.dumps(settings),"t":str(tenant)})
    return trial


async def activate_owner(db, tenant, owner):
    """Called only by the verified invitation acceptance transaction."""
    row = await commerce.tenant_lock(db,tenant)
    settings = row["settings"] or {}
    trial = settings.get("platform_trial") or {}
    if trial.get("status") != "pending": return
    current = commerce.state(row)
    if current.get("billing_mode") != "trial":
        settings["platform_trial"] = {**trial,"status":"upgraded"}
    else:
        now=datetime.now(timezone.utc); end=now+timedelta(days=14)
        settings["platform_trial"] = {**trial,"status":"active","starts_at":now.isoformat(),"ends_at":end.isoformat(),"started_by":str(owner)}
        from services.common.platform_usage import activate
        await activate(db,tenant,current["active_quote"],"trial:"+str(tenant),current["revision"],source="trial",actor=owner,now=now)
        await db.execute(text("UPDATE platform_usage_entitlements SET expires_at=:e WHERE tenant_id=:t"),{"e":end,"t":str(tenant)})
    await db.execute(text("UPDATE tenants SET settings=CAST(:s AS jsonb) WHERE id=:t"),{"s":json.dumps(settings),"t":str(tenant)})


async def expire(db, tenant, now=None):
    candidate = (await db.execute(text("SELECT settings FROM tenants WHERE id=:t"), {"t":str(tenant)})).scalar_one_or_none()
    if not is_due(candidate, now): return False
    row = await commerce.tenant_lock(db, tenant)
    settings = row["settings"] or {}
    if not is_due(settings, now): return False
    current = commerce.state(row)
    trial = settings["platform_trial"]
    if current.get("billing_mode") != "trial":
        settings["platform_trial"] = {**trial,"status":"upgraded"}
    else:
        from services.common.platform_invoice import tax_policy
        priced = quote(Selection(bundle="starter"), await tax_policy(db))
        # Keep an already-issued upgrade invoice payable at its frozen price.
        revision = int(current.get("revision",0))
        # Retain members, invitations and data. Extra users retain Admin access;
        # business panels require the selected Free seat until more seats are bought.
        await commerce.provision(db, tenant, priced, None, retain_members=True)
        owner = (await db.execute(text("SELECT id FROM users WHERE tenant_id=:t AND is_active=true ORDER BY is_owner DESC,created_at,id LIMIT 1"), {"t":str(tenant)})).scalar_one_or_none()
        settings["platform_trial"] = {**trial,"status":"expired","free_user_id":str(owner) if owner else None}
        settings["platform_pricing"] = {**current,"active_quote":priced,"quote":priced,"selection":priced["selection"],
            "revision":revision,"billing_mode":"free","provisioned":True}
        from services.common.platform_usage import activate
        await activate(db, tenant, priced, "trial-free:"+str(tenant), revision, source="trial_expiry", now=now)
    await db.execute(text("UPDATE tenants SET settings=CAST(:s AS jsonb) WHERE id=:t"), {"s":json.dumps(settings),"t":str(tenant)})
    return True


async def sweep(db):
    tenants = (await db.execute(text("SELECT id FROM tenants WHERE settings->'platform_trial'->>'status'='active' AND (settings->'platform_trial'->>'ends_at')::timestamptz<=now() ORDER BY id LIMIT 100"))).scalars().all()
    for tenant in tenants:
        await expire(db,tenant)


async def seat_allowed(db, tenant, user):
    row = (await db.execute(text("SELECT settings FROM tenants WHERE id=:t"), {"t":str(tenant)})).scalar_one_or_none() or {}
    trial = row.get("platform_trial") or {}
    pricing = row.get("platform_pricing") or {}
    if trial.get("status") == "expired" and pricing.get("billing_mode") == "free":
        return trial.get("free_user_id") == str(user)
    return True
