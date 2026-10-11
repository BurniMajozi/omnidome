"""Concrete panel feature gates and atomic monthly write budgets."""
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from sqlalchemy import text
from services.common.platform_pricing import catalog

ALIASES = {"portal-builder": "portal", "journey_engine": "portal", "customer_journey": "portal", "lifecycle": "portal"}
RANK = {"free": 0, "starter": 1, "professional": 2, "enterprise": 3}

DDL = ["""CREATE TABLE IF NOT EXISTS platform_panel_usage (
 tenant_id uuid NOT NULL REFERENCES tenants(id), module text NOT NULL, period date NOT NULL,
 writes integer NOT NULL DEFAULT 0 CHECK(writes>=0), PRIMARY KEY(tenant_id,module,period))"""]

def payment_access(settings, status, now=None):
    now = now or datetime.now(timezone.utc)
    pricing = (settings or {}).get("platform_pricing") or {}
    if status == "suspended": return False
    active = pricing.get("active_quote")
    # Older negotiated agreements and explicit owner provisioning are retained.
    if not active or pricing.get("billing_mode") == "platform_owner": return True
    if Decimal(active.get("recurring_net_zar", active.get("net_zar", "0"))) == 0: return True
    end = pricing.get("period_end")
    if not end: return False
    deadline = datetime.fromisoformat(end) + timedelta(days=catalog()["payment_grace_days"])
    return now < deadline

def blocked_feature(module, tier, path):
    for rule in catalog()["feature_gates"]:
        if rule["module"] == module and re.search(rule["pattern"], path) and RANK.get(tier, 0) < RANK[rule["tier"]]:
            return rule
    return None

async def reserve_write(db, tenant, module, limit):
    period = datetime.now(timezone.utc).date().replace(day=1)
    await db.execute(text("""INSERT INTO platform_panel_usage(tenant_id,module,period)
      VALUES(:t,:m,:p) ON CONFLICT DO NOTHING"""), {"t":str(tenant),"m":module,"p":period})
    row = (await db.execute(text("""UPDATE platform_panel_usage SET writes=writes+1
      WHERE tenant_id=:t AND module=:m AND period=:p AND writes<:limit RETURNING writes"""),
      {"t":str(tenant),"m":module,"p":period,"limit":limit})).first()
    return period if row else None

async def release_write(db, tenant, module, period):
    await db.execute(text("""UPDATE platform_panel_usage SET writes=greatest(0,writes-1)
      WHERE tenant_id=:t AND module=:m AND period=:p"""), {"t":str(tenant),"m":module,"p":period})
