"""Durable platform usage ledger and entitlement outbox. ISP invoices stay separate."""
from __future__ import annotations

import calendar
import json
import math
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import text
from services.common.platform_pricing import catalog

DDL = [
    """CREATE TABLE IF NOT EXISTS platform_cost_events (
      id uuid PRIMARY KEY, tenant_id uuid NOT NULL REFERENCES tenants(id), operation_id uuid NOT NULL,
      category text NOT NULL, provider text NOT NULL, quantity numeric NOT NULL CHECK(quantity>=0),
      unit text NOT NULL, amount numeric CHECK(amount>=0), currency text NOT NULL,
      source text NOT NULL CHECK(source IN ('actual','estimated','allocated','unknown')),
      metadata jsonb NOT NULL DEFAULT '{}', created_at timestamptz NOT NULL DEFAULT now(),
      CHECK((source='unknown' AND amount IS NULL) OR (source!='unknown' AND amount IS NOT NULL)))""",
    "CREATE INDEX IF NOT EXISTS ix_platform_cost_tenant_time ON platform_cost_events(tenant_id,created_at)",
    """CREATE TABLE IF NOT EXISTS platform_usage_operations (
      id uuid PRIMARY KEY, tenant_id uuid NOT NULL REFERENCES tenants(id), kind text NOT NULL,
      policy jsonb NOT NULL, credits integer NOT NULL DEFAULT 0 CHECK(credits>=0),
      status text NOT NULL, started_at timestamptz NOT NULL DEFAULT now(), completed_at timestamptz)""",
    """CREATE TABLE IF NOT EXISTS platform_usage_entitlements (
      tenant_id uuid PRIMARY KEY REFERENCES tenants(id), generation text NOT NULL, policy jsonb NOT NULL,
      source text NOT NULL, revision integer NOT NULL, starts_at timestamptz NOT NULL,
      expires_at timestamptz, actor_id uuid, reason text, updated_at timestamptz NOT NULL DEFAULT now())""",
    """CREATE TABLE IF NOT EXISTS platform_usage_outbox (
      id text PRIMARY KEY, tenant_id uuid NOT NULL REFERENCES tenants(id), generation text NOT NULL,
      action text NOT NULL, payload jsonb NOT NULL, status text NOT NULL DEFAULT 'pending',
      attempts integer NOT NULL DEFAULT 0, error_code text, available_at timestamptz NOT NULL DEFAULT now(),
      created_at timestamptz NOT NULL DEFAULT now(), completed_at timestamptz)""",
    """CREATE TABLE IF NOT EXISTS platform_usage_policy_versions (
      id uuid PRIMARY KEY, tenant_id uuid NOT NULL REFERENCES tenants(id), policy jsonb NOT NULL,
      actor_id uuid NOT NULL, reason text NOT NULL, expires_at timestamptz NOT NULL,
      created_at timestamptz NOT NULL DEFAULT now())""",
    """CREATE OR REPLACE FUNCTION platform_cost_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN RAISE EXCEPTION 'Platform cost events are immutable; append a separate correction record'; END; $$""",
    "DROP TRIGGER IF EXISTS platform_cost_immutable_trigger ON platform_cost_events",
    """CREATE TRIGGER platform_cost_immutable_trigger BEFORE UPDATE OR DELETE ON platform_cost_events
      FOR EACH ROW EXECUTE FUNCTION platform_cost_immutable()""",
    """CREATE OR REPLACE FUNCTION platform_policy_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN RAISE EXCEPTION 'Usage policy versions are immutable; append a new version'; END; $$""",
    "DROP TRIGGER IF EXISTS platform_policy_immutable_trigger ON platform_usage_policy_versions",
    """CREATE TRIGGER platform_policy_immutable_trigger BEFORE UPDATE OR DELETE ON platform_usage_policy_versions
      FOR EACH ROW EXECUTE FUNCTION platform_policy_immutable()""",
]


async def ensure_schema(conn):
    for statement in DDL:
        await conn.execute(text(statement))


def add_months(value: datetime, count: int) -> datetime:
    month = value.month - 1 + count
    year = value.year + month // 12
    month = month % 12 + 1
    return value.replace(year=year, month=month, day=min(value.day, calendar.monthrange(year, month)[1]))


def policy_for_quote(priced):
    if priced.get("usage_policy"):
        return dict(priced["usage_policy"])
    # Old saved invoices acquire no new commercial allowance implicitly.
    return {**catalog()["usage_policy"], "monthly_credits": 0, "legacy": True}


def credit_charge(policy, kind, tokens=0, eligible=True):
    if not eligible:
        return 0
    if kind not in policy["rates"]:
        raise ValueError("Unknown commercial operation kind")
    return max(policy["rates"][kind], math.ceil(max(0, tokens) / policy["token_block"]))


async def append_cost(db, *, tenant, operation, category, provider, quantity, unit,
                      amount=None, currency="USD", source="unknown", event_id=None, metadata=None):
    quantity = Decimal(str(quantity))
    amount = Decimal(str(amount)) if amount is not None else None
    if not quantity.is_finite() or quantity < 0 or (amount is not None and (not amount.is_finite() or amount < 0)):
        raise ValueError("Invalid cost quantity or amount")
    if (source == "unknown") != (amount is None):
        raise ValueError("Unknown cost must remain null")
    if source not in {"actual", "estimated", "allocated", "unknown"}:
        raise ValueError("Invalid cost source")
    safe_metadata = {k: v for k, v in (metadata or {}).items() if k in {"model", "outcome", "attempt", "purpose", "receipt_id"}}
    await db.execute(text("""INSERT INTO platform_cost_events
      (id,tenant_id,operation_id,category,provider,quantity,unit,amount,currency,source,metadata)
      VALUES(:id,:t,:op,:cat,:provider,:q,:unit,:amount,:currency,:source,CAST(:meta AS jsonb))
      ON CONFLICT(id) DO NOTHING"""),
      {"id": str(event_id or uuid.uuid4()), "t": str(tenant), "op": str(operation), "cat": category,
       "provider": provider, "q": quantity, "unit": unit, "amount": amount, "currency": currency,
       "source": source, "meta": json.dumps(safe_metadata)})


async def activate(db, tenant, priced, generation, revision, *, source, actor=None, reason=None, now=None):
    """Only authoritative provisioning calls this, in the payment/admin transaction."""
    now = now or datetime.now(timezone.utc)
    policy = policy_for_quote(priced)
    expires = add_months(now, 12 if priced["period"] == "annually" else 1)
    # An owner override is bounded to the invoice's service period, not perpetual.
    await db.execute(text("""INSERT INTO platform_usage_entitlements
      (tenant_id,generation,policy,source,revision,starts_at,expires_at,actor_id,reason)
      VALUES(:t,:g,CAST(:p AS jsonb),:s,:r,:start,:end,:actor,:reason)
      ON CONFLICT(tenant_id) DO UPDATE SET generation=excluded.generation,policy=excluded.policy,
        source=excluded.source,revision=excluded.revision,starts_at=excluded.starts_at,
        expires_at=excluded.expires_at,actor_id=excluded.actor_id,reason=excluded.reason,updated_at=now()"""),
      {"t": str(tenant), "g": generation, "p": json.dumps(policy), "s": source, "r": revision,
       "start": now, "end": expires, "actor": str(actor) if actor else None, "reason": reason})
    # Reconciliation is durable even while the Autumn runtime is unavailable.
    await db.execute(text("""INSERT INTO platform_usage_outbox(id,tenant_id,generation,action,payload)
      VALUES(:id,:t,:g,'reconcile','{}') ON CONFLICT(id) DO NOTHING"""),
      {"id": f"activate:{tenant}:{generation}", "t": str(tenant), "g": generation})


async def start_operation(db, tenant, operation, kind):
    active = (await db.execute(text("SELECT policy,expires_at FROM platform_usage_entitlements WHERE tenant_id=:t"), {"t": str(tenant)})).mappings().first()
    policy = dict(active["policy"]) if active else {**catalog()["usage_policy"], "monthly_credits": 0, "legacy": True}
    if active and active["expires_at"] <= datetime.now(timezone.utc):
        policy["monthly_credits"] = 0
    await db.execute(text("""INSERT INTO platform_usage_operations(id,tenant_id,kind,policy,status)
      VALUES(:id,:t,:kind,CAST(:p AS jsonb),'running')"""),
      {"id": str(operation), "t": str(tenant), "kind": kind, "p": json.dumps(policy)})
    return policy


async def finish_operation(db, tenant, operation, policy, kind, *, tokens, eligible, status):
    credits = credit_charge(policy, kind, tokens, eligible)
    result = await db.execute(text("""UPDATE platform_usage_operations SET credits=:c,kind=:kind,status=:s,completed_at=now()
      WHERE id=:id AND tenant_id=:t AND status='running' RETURNING id"""),
      {"c": credits, "kind": kind, "s": status, "id": str(operation), "t": str(tenant)})
    if not result.first():
        return
    # Shadow usage stays local. It never debits real credits or charges Paystack.
