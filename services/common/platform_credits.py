"""Prepaid platform credits, separate from plan-change money credits and ISP billing."""
import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from fastapi import HTTPException
from sqlalchemy import text
from services.common import platform_commerce as commerce

DEFAULT_POLICY = {"enabled": False, "price_per_credit_zar": None, "minimum_zar": "50.00", "operation_credit_limit": 100}
DDL = [
    """CREATE TABLE IF NOT EXISTS platform_credit_policy (
      singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton), policy jsonb NOT NULL,
      actor_id uuid, updated_at timestamptz NOT NULL DEFAULT now())""",
    """CREATE TABLE IF NOT EXISTS platform_credit_entries (
      id uuid PRIMARY KEY, tenant_id uuid NOT NULL REFERENCES tenants(id),
      order_id uuid UNIQUE REFERENCES platform_orders(id), operation_id uuid UNIQUE,
      credits integer NOT NULL CHECK(credits<>0), created_at timestamptz NOT NULL DEFAULT now(),
      CHECK((credits>0 AND order_id IS NOT NULL AND operation_id IS NULL)
        OR (credits<0 AND operation_id IS NOT NULL AND order_id IS NULL)))""",
    "CREATE INDEX IF NOT EXISTS ix_credit_entries_tenant ON platform_credit_entries(tenant_id,created_at)",
    "ALTER TABLE platform_usage_operations ADD COLUMN IF NOT EXISTS panel text NOT NULL DEFAULT 'unattributed'",
    "ALTER TABLE platform_usage_operations ADD COLUMN IF NOT EXISTS reserved_credits integer NOT NULL DEFAULT 0",
    "ALTER TABLE platform_usage_operations ADD COLUMN IF NOT EXISTS measured_credits integer NOT NULL DEFAULT 0",
    """CREATE OR REPLACE FUNCTION platform_credit_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN RAISE EXCEPTION 'Credit ledger is append-only'; END; $$""",
    "DROP TRIGGER IF EXISTS platform_credit_immutable_trigger ON platform_credit_entries",
    "CREATE TRIGGER platform_credit_immutable_trigger BEFORE UPDATE OR DELETE ON platform_credit_entries FOR EACH ROW EXECUTE FUNCTION platform_credit_immutable()",
]

async def policy(db):
    saved = (await db.execute(text("SELECT policy FROM platform_credit_policy WHERE singleton=true"))).scalar_one_or_none()
    return {**DEFAULT_POLICY, **(saved or {})}

async def balance(db, tenant):
    return int((await db.execute(text("SELECT coalesce(sum(credits),0) FROM platform_credit_entries WHERE tenant_id=:t"), {"t":str(tenant)})).scalar_one())

def window(active, now=None):
    from services.common.platform_usage import add_months
    now = now or datetime.now(timezone.utc)
    if not active:
        start = now.replace(day=1,hour=0,minute=0,second=0,microsecond=0)
        return start, add_months(start,1), 0
    anchor = active["starts_at"]
    index = max(0,(now.year-anchor.year)*12+now.month-anchor.month)
    if add_months(anchor,index)>now: index=max(0,index-1)
    start = add_months(anchor,index)
    expiry = active["expires_at"]
    end = min(add_months(anchor,index+1),expiry) if expiry else add_months(anchor,index+1)
    allowance = int(active["policy"].get("monthly_credits",0)) if not expiry or expiry>now else 0
    return start,end,allowance

async def reserve(db, tenant, minimum):
    """Serialize starts/completions with purchases to prevent wallet overdrafts."""
    config = await policy(db)
    if not config["enabled"]: return 0
    await commerce.tenant_lock(db,tenant)
    active = (await db.execute(text("SELECT * FROM platform_usage_entitlements WHERE tenant_id=:t"), {"t":str(tenant)})).mappings().first()
    start,end,allowance = window(active)
    used = int((await db.execute(text("SELECT coalesce(sum(credits),0) FROM platform_usage_operations WHERE tenant_id=:t AND started_at>=:start AND started_at<:end"), {"t":str(tenant),"start":start,"end":end})).scalar_one())
    pending = int((await db.execute(text("SELECT coalesce(sum(reserved_credits),0) FROM platform_usage_operations WHERE tenant_id=:t AND status='running'"), {"t":str(tenant)})).scalar_one())
    available = max(0,allowance-used) + await balance(db,tenant) - pending
    if available<minimum: raise HTTPException(402,"Insufficient platform credits. Top up in Platform Billing & Usage.")
    return min(available,max(minimum,int(config["operation_credit_limit"])))

async def debit(db, tenant, operation, charge, started_at):
    await commerce.tenant_lock(db,tenant)
    active = (await db.execute(text("SELECT * FROM platform_usage_entitlements WHERE tenant_id=:t"), {"t":str(tenant)})).mappings().first()
    start,end,allowance = window(active,started_at)
    # An operation from a replaced period cannot consume the replacement allowance.
    if start>started_at: allowance=0
    previous = int((await db.execute(text("SELECT coalesce(sum(credits),0) FROM platform_usage_operations WHERE tenant_id=:t AND id<>:op AND started_at>=:start AND started_at<:end"), {"t":str(tenant),"op":str(operation),"start":start,"end":end})).scalar_one())
    purchased = max(0,charge-max(0,allowance-previous))
    if purchased:
        if purchased>await balance(db,tenant): raise HTTPException(409,"Credit reservation requires reconciliation")
        await db.execute(text("""INSERT INTO platform_credit_entries(id,tenant_id,operation_id,credits)
          VALUES(:id,:t,:op,:c) ON CONFLICT(operation_id) DO NOTHING"""), {"id":str(uuid.uuid4()),"t":str(tenant),"op":str(operation),"c":-purchased})

def topup_quote(amount_zar, config, tax):
    """The customer chooses gross payment; whole credits are disclosed before checkout."""
    if not config["enabled"] or not config["price_per_credit_zar"]: raise HTTPException(409,"The Platform Owner has not published credit top-up pricing")
    rate = Decimal(str(tax["rate"])) if tax["vat_registered"] else Decimal(0)
    total = Decimal(amount_zar).quantize(Decimal("0.01"),rounding=ROUND_HALF_UP)
    if not Decimal(50)<=total<=Decimal(100000): raise HTTPException(422,"Enter a top-up between R50 and R100,000")
    unit = Decimal(config["price_per_credit_zar"])*(1 if tax["prices_include_vat"] else 1+rate)
    credits = int(total/unit)
    if credits<1: raise HTTPException(422,"This amount does not buy a whole credit at the published rate")
    net = (total/(1+rate)).quantize(Decimal("0.01"),rounding=ROUND_HALF_UP)
    return {"name":f"{credits:,} OmniDome AI credits","period":"one-off","seats":0,"entitlements":[],
        "currency":"ZAR","net_zar":str(net),"vat_zar":str(total-net),"total_zar":str(total),"amount_cents":int(total*100),
        "vat_registered":tax["vat_registered"],"vat_rate":str(rate),"prices_include_vat":tax["prices_include_vat"],
        "credit_topup":{"credits":credits,"expires_at":None,"policy":config,"unit_total_zar":str(unit)},
        "lines":[{"description":"Prepaid OmniDome AI credits","quantity":credits,"net_zar":str(net)}]}


async def create_order(db, tenant, actor, amount_zar, key):
    from services.common.platform_invoice import tax_policy, snapshot
    tenant_row = await commerce.tenant_lock(db,tenant)
    old = (await db.execute(text("SELECT * FROM platform_orders WHERE tenant_id=:t AND idempotency_key=:k"), {"t":str(tenant),"k":str(key)})).mappings().first()
    if old:
        if old["intent"]!="credit_topup" or Decimal(old["quote"]["total_zar"])!=Decimal(amount_zar):
            raise HTTPException(409,"Idempotency key belongs to a different purchase")
        return dict(old)
    quote = topup_quote(amount_zar,await policy(db),await tax_policy(db))
    quote["invoice_details"] = await snapshot(db,tenant_row,quote)
    number = (await db.execute(text("SELECT nextval('platform_invoice_number_seq')"))).scalar_one()
    ident = uuid.uuid4()
    reference = f"ODP-{datetime.now(timezone.utc).year}-{number:06d}"
    row = (await db.execute(text("""INSERT INTO platform_orders(id,tenant_id,actor_id,idempotency_key,reference,intent,quote,revision)
      VALUES(:id,:t,:a,:k,:r,'credit_topup',CAST(:q AS jsonb),0) RETURNING *"""), {"id":str(ident),"t":str(tenant),"a":str(actor),"k":str(key),"r":reference,"q":json.dumps(quote)})).mappings().one()
    return dict(row)

async def settle(db, order, payment):
    # commerce.paid has already checked provider status, amount, currency and reference.
    await commerce.tenant_lock(db,order["tenant_id"])
    fresh = (await db.execute(text("SELECT * FROM platform_orders WHERE id=:id FOR UPDATE"), {"id":str(order["id"])})).mappings().one()
    if fresh["paid_at"]: return {"status":fresh["status"],"duplicate":True}
    if fresh["status"]=="cancelled": raise HTTPException(409,"Credit invoice cancelled")
    await db.execute(text("INSERT INTO platform_credit_entries(id,tenant_id,order_id,credits) VALUES(:id,:t,:o,:c) ON CONFLICT(order_id) DO NOTHING"), {"id":str(uuid.uuid4()),"t":str(order["tenant_id"]),"o":str(order["id"]),"c":order["quote"]["credit_topup"]["credits"]})
    await db.execute(text("UPDATE platform_orders SET status='paid',paid_at=now(),payment_id=:p WHERE id=:id"), {"p":str(payment.get("id") or payment["reference"]),"id":str(order["id"])})
    return {"status":"paid","duplicate":False,"credits_added":order["quote"]["credit_topup"]["credits"]}
