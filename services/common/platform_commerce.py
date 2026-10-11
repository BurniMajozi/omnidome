"""Shared transaction records for SaaS tenant pricing, separate from ISP customer billing."""
import json
import uuid
from sqlalchemy import text
from fastapi import HTTPException
from services.common.platform_pricing import catalog, Selection, quote

DDL = [
    """CREATE TABLE IF NOT EXISTS platform_orders (
      id uuid PRIMARY KEY, tenant_id uuid NOT NULL REFERENCES tenants(id), actor_id uuid NOT NULL,
      idempotency_key uuid NOT NULL, reference text NOT NULL UNIQUE, intent text NOT NULL,
      quote jsonb NOT NULL, revision integer NOT NULL, status text NOT NULL DEFAULT 'issued',
      checkout_url text, plan_code text, payment_id text, created_at timestamptz NOT NULL DEFAULT now(), paid_at timestamptz,
      UNIQUE(tenant_id,idempotency_key))""",
    """CREATE TABLE IF NOT EXISTS platform_subscriptions (
      tenant_id uuid NOT NULL REFERENCES tenants(id), order_id uuid PRIMARY KEY REFERENCES platform_orders(id),
      plan_code text UNIQUE, subscription_code text UNIQUE, status text NOT NULL,
      quote jsonb NOT NULL, revision integer NOT NULL, email_token text, updated_at timestamptz NOT NULL DEFAULT now())""",
    "ALTER TABLE platform_subscriptions ADD COLUMN IF NOT EXISTS email_token text",
    "CREATE INDEX IF NOT EXISTS ix_platform_orders_tenant ON platform_orders(tenant_id,created_at)",
    "CREATE INDEX IF NOT EXISTS ix_platform_subscriptions_tenant ON platform_subscriptions(tenant_id,updated_at)",
]


async def ensure_schema(conn):
    # Admin and billing can start together. Serialize shared DDL and triggers.
    if conn.dialect.name == "postgresql":
        await conn.execute(text("SELECT pg_advisory_xact_lock(7142001)"))
    for statement in DDL: await conn.execute(text(statement))
    from services.common import platform_usage
    await platform_usage.ensure_schema(conn)
    for module in catalog()["modules"]:
        await conn.execute(text("INSERT INTO modules(id,key,name,is_core) VALUES(:id,:key,:name,false) ON CONFLICT(key) DO NOTHING"),
                           {"id": str(uuid.uuid4()), "key": module["id"], "name": module["name"]})
    # Owner and organisation admin may operate every module in their own tenant.
    # Entitlement guards still decide which of those modules the tenant has.
    await conn.execute(text("""INSERT INTO role_permissions(role_id,permission_id)
      SELECT r.id,p.id FROM roles r CROSS JOIN permissions p
      WHERE r.scope='TENANT' AND r.name IN ('owner','org_admin')
        AND split_part(p.key,'.',1) IN (SELECT key FROM modules)
      ON CONFLICT DO NOTHING"""))


async def tenant_lock(db, tenant):
    row = (await db.execute(text("SELECT id,settings,seat_limit FROM tenants WHERE id=:t FOR UPDATE"), {"t": str(tenant)})).mappings().first()
    if not row: raise HTTPException(404, "Tenant not found")
    return row


def state(row):
    return (row.get("settings") or {}).get("platform_pricing") or {}


async def save_choice(db, tenant, selection, actor, *, enable=False):
    row = await tenant_lock(db, tenant)
    try: priced = quote(selection)
    except ValueError as exc: raise HTTPException(422, str(exc))
    revision = int(state(row).get("revision", 0)) + 1
    settings = {**(row.get("settings") or {}), "platform_pricing": {
        "selection": priced["selection"], "quote": priced, "revision": revision,
        "source": "platform_owner" if enable else "checkout", "provisioned": enable,
    }}
    await db.execute(text("UPDATE tenants SET settings=CAST(:s AS jsonb),updated_at=now() WHERE id=:t"), {"s": json.dumps(settings), "t": str(tenant)})
    if enable:
        await provision(db, tenant, priced, actor)
        from services.common.platform_usage import activate
        await activate(db, tenant, priced, f"override:{revision}", revision, source="platform_owner", actor=actor, reason="Panel and plan provisioning")
    return priced, revision


async def occupied_seats(db, tenant):
    return (await db.execute(text("""SELECT (SELECT count(*) FROM users WHERE tenant_id=:t AND is_active=true) +
      (SELECT count(*) FROM invites WHERE tenant_id=:t AND status='pending' AND expires_at>now())"""), {"t": str(tenant)})).scalar_one()


async def provision(db, tenant, priced, actor):
    used = await occupied_seats(db, tenant)
    if used > priced["seats"]: raise HTTPException(409, f"{used} seats are in use, including pending invitations")
    enabled = set(priced["entitlements"]) | set(priced.get("manual_panels", [])) | {"agents", "memory", "voicebox"}
    actor_exists = (await db.execute(text("SELECT 1 FROM users WHERE id=:u"), {"u": str(actor)})).first() if actor else None
    if "portal" in enabled: enabled |= {"lifecycle", "customer_journey", "journey_engine"}
    # A selected price is a full desired state, not an additive grant.
    await db.execute(text("""INSERT INTO tenant_modules(tenant_id,module_id,status,enabled_by,enabled_at,disabled_at,config)
      SELECT :t,m.id,CASE WHEN m.key=ANY(CAST(:keys AS text[])) THEN 'ENABLED' ELSE 'DISABLED' END,
        :actor,now(),CASE WHEN m.key=ANY(CAST(:keys AS text[])) THEN NULL ELSE now() END,'{}'::jsonb
      FROM modules m ON CONFLICT(tenant_id,module_id) DO UPDATE SET
        status=excluded.status,enabled_by=excluded.enabled_by,enabled_at=excluded.enabled_at,disabled_at=excluded.disabled_at,config=excluded.config"""),
      {"t": str(tenant), "keys": sorted(enabled), "actor": str(actor) if actor_exists else None})
    # Module tiers are retained alongside the enabled flag.
    for key, tier in priced["selection"]["modules"].items():
        await db.execute(text("UPDATE tenant_modules SET config=CAST(:config AS jsonb) WHERE tenant_id=:t AND module_id=(SELECT id FROM modules WHERE key=:key)"),
                         {"config": json.dumps({"pricing_tier": tier}), "t": str(tenant), "key": key})
    await db.execute(text("UPDATE tenants SET tier=:tier,seat_limit=:seats,seat_price=:price,updated_at=now() WHERE id=:t"),
                     {"tier": priced["tier"], "seats": priced["seats"], "price": priced["seat_price"], "t": str(tenant)})
    await db.execute(text("""INSERT INTO role_permissions(role_id,permission_id)
      SELECT r.id,p.id FROM roles r CROSS JOIN permissions p WHERE r.tenant_id=:t AND r.name IN ('owner','org_admin')
        AND split_part(p.key,'.',1) IN (SELECT key FROM modules) ON CONFLICT DO NOTHING"""), {"t": str(tenant)})


async def create_order(db, tenant, actor, selection, intent, key):
    await tenant_lock(db, tenant)
    existing = (await db.execute(text("SELECT * FROM platform_orders WHERE tenant_id=:t AND idempotency_key=:key"), {"t": str(tenant), "key": str(key)})).mappings().first()
    if existing:
        expected = quote(selection)
        if existing["quote"]["selection"] != expected["selection"] or existing["intent"] != intent:
            raise HTTPException(409, "This checkout key already belongs to a different selection")
        return dict(existing)
    tenant_row = await tenant_lock(db, tenant)
    try: priced = quote(selection)
    except ValueError as exc: raise HTTPException(422, str(exc))
    current = state(tenant_row)
    if current.get("selection") == priced["selection"] and current.get("revision"):
        revision = current["revision"]
        priced = current["quote"]
    else:
        priced, revision = await save_choice(db, tenant, selection, actor)
    ident = uuid.uuid4()
    result = await db.execute(text("""INSERT INTO platform_orders(id,tenant_id,actor_id,idempotency_key,reference,intent,quote,revision)
      VALUES(:id,:t,:actor,:key,:ref,:intent,CAST(:q AS jsonb),:rev) RETURNING *"""),
      {"id": str(ident), "t": str(tenant), "actor": str(actor), "key": str(key), "ref": "ODP-" + ident.hex,
       "intent": intent, "q": json.dumps(priced), "rev": revision})
    return dict(result.mappings().one())


async def capture_module_edits(db, tenant, actor):
    """Checkbox changes freeze a new invoice and invalidate earlier payment revisions."""
    row = await tenant_lock(db, tenant)
    current = state(row)
    if not current.get("selection"): return  # Legacy tenants retain their negotiated contract.
    rows = (await db.execute(text("""SELECT m.key,tm.config FROM tenant_modules tm JOIN modules m ON m.id=tm.module_id
      WHERE tm.tenant_id=:t AND tm.status IN ('ENABLED','TRIAL')"""), {"t": str(tenant)})).mappings().all()
    ids = {m["id"] for m in catalog()["modules"]}
    old = current["selection"]
    chosen = {r["key"]: (r["config"] or {}).get("pricing_tier", old["modules"].get(r["key"], "starter")) for r in rows if r["key"] in ids}
    # A bundle stays intact only while all its included panels retain their tier.
    bundle = catalog()["bundles"].get(old.get("bundle"))
    keep = bundle and all(chosen.get(m) == bundle["tier"] for m in bundle["modules"])
    if not chosen: raise HTTPException(422, "Keep at least one priced panel, or choose the free Starter plan")
    selection = Selection(bundle=old.get("bundle") if keep else None, modules=chosen, seats=old["seats"], period=old["period"])
    priced, revision = await save_choice(db, tenant, selection, actor)
    priced["manual_panels"] = sorted(r["key"] for r in rows if r["key"] not in ids)
    settings = {**(row["settings"] or {}), "platform_pricing": {"selection": priced["selection"], "quote": priced, "revision": revision, "source": "platform_owner", "provisioned": True}}
    await db.execute(text("UPDATE tenants SET settings=CAST(:s AS jsonb) WHERE id=:t"), {"s": json.dumps(settings), "t": str(tenant)})
    await db.execute(text("UPDATE tenants SET tier=:tier,seat_limit=:seats,seat_price=:price WHERE id=:t"),
                     {"tier": priced["tier"], "seats": priced["seats"], "price": priced["seat_price"], "t": str(tenant)})
    await create_order(db, tenant, actor, selection, "invoice", uuid.uuid4())
    from services.common.platform_usage import activate
    await activate(db, tenant, priced, f"override:{revision}", revision, source="platform_owner", actor=actor, reason="Panel checkbox edit")


async def paid(db, order, payment, *, force_review=False):
    # Payment payloads reach this only after server-side provider verification
    # or a signature-verified webhook. Neither redirects nor client amounts count.
    if payment.get("status") != "success" or str(payment.get("currency", "")).upper() != order["quote"]["currency"] or payment.get("amount") != order["quote"]["amount_cents"]:
        raise HTTPException(409, "Payment status, currency or amount does not match this invoice")
    if payment.get("reference") != order["reference"]: raise HTTPException(409, "Payment reference mismatch")
    if order["intent"] == "subscription" and order["quote"]["amount_cents"] > 0 and not order.get("plan_code"):
        raise HTTPException(409, "Subscription checkout has no provider plan")
    tenant = await tenant_lock(db, order["tenant_id"])
    row = (await db.execute(text("SELECT * FROM platform_orders WHERE id=:id FOR UPDATE"), {"id": str(order["id"])})).mappings().one()
    if row["paid_at"]: return {"status": row["status"], "duplicate": True}
    current = state(tenant)
    matching = current.get("revision") == order["revision"] and not force_review
    if matching and await occupied_seats(db, order["tenant_id"]) > order["quote"]["seats"]:
        matching = False
    status = "paid" if matching else "payment_review"
    await db.execute(text("UPDATE platform_orders SET status=:status,paid_at=now(),payment_id=:pid WHERE id=:id"),
                     {"status": status, "pid": str(payment.get("id") or order["reference"]), "id": str(order["id"])})
    if matching:
        await provision(db, order["tenant_id"], order["quote"], order["actor_id"])
        from services.common.platform_usage import activate
        await activate(db, order["tenant_id"], order["quote"], "order:" + str(order["id"]), order["revision"], source="payment", actor=order["actor_id"])
        settings = {**(tenant["settings"] or {}), "platform_pricing": {**current, "provisioned": True, "paid_order_id": str(order["id"])}}
        await db.execute(text("UPDATE tenants SET settings=CAST(:s AS jsonb),billing_status='active' WHERE id=:t"), {"s": json.dumps(settings), "t": str(order["tenant_id"])})
        if order["intent"] == "subscription" and order["quote"]["amount_cents"] > 0:
            await db.execute(text("""INSERT INTO platform_subscriptions(tenant_id,order_id,plan_code,status,quote,revision)
              VALUES(:t,:id,:plan,'active',CAST(:q AS jsonb),:rev) ON CONFLICT(order_id) DO UPDATE SET
                order_id=excluded.order_id,plan_code=excluded.plan_code,status='active',quote=excluded.quote,revision=excluded.revision,updated_at=now()"""),
              {"t": str(order["tenant_id"]), "id": str(order["id"]), "plan": order.get("plan_code"), "q": json.dumps(order["quote"]), "rev": order["revision"]})
    return {"status": status, "duplicate": False}
