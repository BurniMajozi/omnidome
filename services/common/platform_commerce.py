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
    "ALTER TABLE platform_orders ADD COLUMN IF NOT EXISTS checkout_created_at timestamptz",
    "ALTER TABLE platform_orders ADD COLUMN IF NOT EXISTS supersedes_order_id uuid REFERENCES platform_orders(id)",
    """CREATE OR REPLACE FUNCTION platform_order_quote_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN IF NEW.quote IS DISTINCT FROM OLD.quote OR NEW.reference IS DISTINCT FROM OLD.reference
        OR NEW.tenant_id IS DISTINCT FROM OLD.tenant_id OR NEW.actor_id IS DISTINCT FROM OLD.actor_id
        OR NEW.revision IS DISTINCT FROM OLD.revision OR NEW.intent IS DISTINCT FROM OLD.intent
        OR NEW.idempotency_key IS DISTINCT FROM OLD.idempotency_key THEN
          RAISE EXCEPTION 'Frozen platform invoice cannot be changed'; END IF; RETURN NEW; END; $$""",
    "DROP TRIGGER IF EXISTS platform_order_quote_immutable_trigger ON platform_orders",
    """CREATE TRIGGER platform_order_quote_immutable_trigger BEFORE UPDATE ON platform_orders
       FOR EACH ROW EXECUTE FUNCTION platform_order_quote_immutable()""",
    """CREATE TABLE IF NOT EXISTS platform_checkout_attempts (
      reference text PRIMARY KEY, order_id uuid NOT NULL REFERENCES platform_orders(id),
      created_at timestamptz NOT NULL DEFAULT now())""",
    "CREATE INDEX IF NOT EXISTS ix_platform_orders_tenant ON platform_orders(tenant_id,created_at)",
    "CREATE INDEX IF NOT EXISTS ix_platform_subscriptions_tenant ON platform_subscriptions(tenant_id,updated_at)",
]


async def ensure_schema(conn):
    # Admin and billing can start together. Serialize shared DDL and triggers.
    if conn.dialect.name == "postgresql":
        await conn.execute(text("SELECT pg_advisory_xact_lock(7142001)"))
    for statement in DDL: await conn.execute(text(statement))
    from services.common.platform_access import DDL as ACCESS_DDL
    for statement in ACCESS_DDL: await conn.execute(text(statement))
    from services.common.platform_invoice import DDL as INVOICE_DDL
    for statement in INVOICE_DDL: await conn.execute(text(statement))
    await conn.execute(text("INSERT INTO platform_invoice_supplier(singleton,profile,actor_id) VALUES(true,CAST(:p AS jsonb),NULL) ON CONFLICT(singleton) DO NOTHING"), {"p":json.dumps(catalog()["supplier"])})
    from services.common import platform_usage
    await platform_usage.ensure_schema(conn)
    await conn.execute(text("""UPDATE platform_usage_entitlements e SET policy=e.policy || '{"permanent_free": true}'::jsonb
      FROM tenants t WHERE e.tenant_id=t.id AND t.settings->'platform_pricing'->'active_quote'->>'tier'='FREE'
      AND t.settings->'platform_pricing'->'active_quote'->>'amount_cents'='0' AND e.generation NOT LIKE 'policy:%'"""))
    for module in catalog()["modules"]:
        await conn.execute(text("INSERT INTO modules(id,key,name,is_core) VALUES(:id,:key,:name,false) ON CONFLICT(key) DO UPDATE SET name=excluded.name"),
                           {"id": str(uuid.uuid4()), "key": module["id"], "name": module["name"]})
    # Owner and organisation admin may operate every module in their own tenant.
    # Entitlement guards still decide which of those modules the tenant has.
    await conn.execute(text("""INSERT INTO role_permissions(role_id,permission_id)
      SELECT r.id,p.id FROM roles r CROSS JOIN permissions p
      WHERE r.scope='TENANT' AND r.name IN ('owner','org_admin')
        AND split_part(p.key,'.',1) IN (SELECT key FROM modules)
      ON CONFLICT DO NOTHING"""))
    for tier, limits in catalog()["tier_limits"].items():
        await conn.execute(text("""UPDATE tenant_modules SET config=config || CAST(:limits AS jsonb)
          WHERE config->>'pricing_tier'=:tier AND NOT (config ? 'writes_per_month')"""), {"tier":tier,"limits":json.dumps(limits)})
    await conn.execute(text("""UPDATE tenants t SET settings=jsonb_set(t.settings,'{platform_pricing}',
      (t.settings->'platform_pricing') || jsonb_build_object('active_quote',o.quote,'active_revision',o.revision,
        'billing_mode','payment','period_start',o.paid_at,'period_end',o.paid_at + CASE WHEN o.quote->>'period'='annually' THEN interval '1 year' ELSE interval '1 month' END))
      FROM platform_orders o WHERE o.id::text=t.settings#>>'{platform_pricing,paid_order_id}' AND o.status='paid'
      AND t.settings#>>'{platform_pricing,billing_mode}' IS NULL
      AND t.settings#>>'{platform_pricing,source}' IS DISTINCT FROM 'platform_owner'"""))


async def tenant_lock(db, tenant):
    row = (await db.execute(text("SELECT id,name,settings,seat_limit,billing_status FROM tenants WHERE id=:t FOR UPDATE"), {"t": str(tenant)})).mappings().first()
    if not row: raise HTTPException(404, "Tenant not found")
    return row


def state(row):
    return (row.get("settings") or {}).get("platform_pricing") or {}


async def save_choice(db, tenant, selection, actor, *, enable=False):
    row = await tenant_lock(db, tenant)
    from services.common.platform_invoice import tax_policy
    try: priced = quote(selection, await tax_policy(db))
    except ValueError as exc: raise HTTPException(422, str(exc))
    old = state(row)
    priced["manual_panels"] = list((old.get("quote") or {}).get("manual_panels", []))
    revision = int(state(row).get("revision", 0)) + 1
    settings = {**(row.get("settings") or {}), "platform_pricing": {
        **old, "selection": priced["selection"], "quote": priced, "revision": revision,
        "source": "platform_owner" if enable else "checkout", "provisioned": enable,
    }}
    await db.execute(text("UPDATE tenants SET settings=CAST(:s AS jsonb),updated_at=now() WHERE id=:t"), {"s": json.dumps(settings), "t": str(tenant)})
    if enable:
        settings["platform_pricing"].update(active_quote=priced, billing_mode="platform_owner")
        if settings.get("platform_trial",{}).get("status") in {"active","pending"}:
            settings["platform_trial"]={**settings["platform_trial"],"status":"upgraded"}
        await db.execute(text("UPDATE tenants SET settings=CAST(:s AS jsonb) WHERE id=:t"), {"s":json.dumps(settings),"t":str(tenant)})
        await provision(db, tenant, priced, actor)
        from services.common.platform_usage import activate
        await activate(db, tenant, priced, f"override:{revision}", revision, source="platform_owner", actor=actor, reason="Panel and plan provisioning")
    return priced, revision


async def occupied_seats(db, tenant):
    return (await db.execute(text("""SELECT (SELECT count(*) FROM users WHERE tenant_id=:t AND is_active=true) +
      (SELECT count(*) FROM invites WHERE tenant_id=:t AND status='pending' AND expires_at>now())"""), {"t": str(tenant)})).scalar_one()


async def provision(db, tenant, priced, actor, *, retain_members=False):
    used = await occupied_seats(db, tenant)
    if used > priced["seats"] and not retain_members: raise HTTPException(409, f"{used} seats are in use, including pending invitations")
    enabled = set(priced["entitlements"]) | set(priced.get("manual_panels", [])) | {"agents", "memory", "voicebox", "overview", "admin"}
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
                         {"config": json.dumps({"pricing_tier": tier, **(priced.get("usage_policy", {}).get("module_limits", {}).get(key) or catalog()["tier_limits"][tier])}), "t": str(tenant), "key": key})
    await db.execute(text("UPDATE tenants SET tier=:tier,seat_limit=:seats,seat_price=:price,updated_at=now() WHERE id=:t"),
                     {"tier": priced["tier"], "seats": priced["seats"], "price": priced["seat_price"], "t": str(tenant)})
    await db.execute(text("""INSERT INTO role_permissions(role_id,permission_id)
      SELECT r.id,p.id FROM roles r CROSS JOIN permissions p WHERE r.tenant_id=:t AND r.name IN ('owner','org_admin')
        AND split_part(p.key,'.',1) IN (SELECT key FROM modules) ON CONFLICT DO NOTHING"""), {"t": str(tenant)})


async def create_order(db, tenant, actor, selection, intent, key):
    await tenant_lock(db, tenant)
    from services.common.platform_invoice import tax_policy
    try: expected = quote(selection, await tax_policy(db))
    except ValueError as exc: raise HTTPException(422, str(exc))
    existing = (await db.execute(text("SELECT * FROM platform_orders WHERE tenant_id=:t AND idempotency_key=:key"), {"t": str(tenant), "key": str(key)})).mappings().first()
    if existing:
        if existing["quote"]["selection"] != expected["selection"] or existing["intent"] != intent:
            raise HTTPException(409, "This checkout key already belongs to a different selection")
        return dict(existing)
    tenant_row = await tenant_lock(db, tenant)
    try: priced = expected
    except ValueError as exc: raise HTTPException(422, str(exc))
    current = state(tenant_row)
    priced, revision = await save_choice(db, tenant, selection, actor)
    from services.common.platform_proration import change_quote
    if current.get("billing_mode") == "payment":
        from datetime import datetime, timezone
        if current.get("active_quote", {}).get("selection") == expected["selection"] and current.get("period_end") and datetime.fromisoformat(current["period_end"]) > datetime.now(timezone.utc):
            raise HTTPException(409, "This plan is already active; a new invoice can be issued when its paid period ends")
        priced = change_quote(expected, current)
        priced["manual_panels"] = list((current.get("quote") or current.get("active_quote") or {}).get("manual_panels", []))
    ident = uuid.uuid4()
    from services.common.platform_invoice import snapshot
    from datetime import datetime, timezone
    priced["invoice_details"] = await snapshot(db, tenant_row, priced)
    serial = (await db.execute(text("SELECT nextval('platform_invoice_number_seq')"))).scalar_one()
    result = await db.execute(text("""INSERT INTO platform_orders(id,tenant_id,actor_id,idempotency_key,reference,intent,quote,revision)
      VALUES(:id,:t,:actor,:key,:ref,:intent,CAST(:q AS jsonb),:rev) RETURNING *"""),
      {"id": str(ident), "t": str(tenant), "actor": str(actor), "key": str(key),
       "intent": intent, "q": json.dumps(priced), "rev": revision, "ref":f"ODP-{datetime.now(timezone.utc).year}-{serial:08d}"})
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
    chosen = {r["key"]: (r["config"] or {}).get("pricing_tier", old["modules"].get(r["key"], "free" if r["key"] in catalog()["free_modules"] else "starter")) for r in rows if r["key"] in ids}
    # A bundle stays intact only while all its included panels retain their tier.
    bundle = catalog()["bundles"].get(old.get("bundle"))
    expected = {m: "free" for m in catalog()["free_modules"]} if bundle else {}
    if bundle: expected.update({m: bundle["tier"] for m in bundle["modules"]})
    keep = bundle and all(chosen.get(m) == tier for m, tier in expected.items())
    if not chosen: raise HTTPException(422, "Keep at least one panel, or choose the Free plan")
    selection = Selection(bundle=old.get("bundle") if keep else None, modules=chosen, seats=old["seats"], period=old["period"])
    priced, revision = await save_choice(db, tenant, selection, actor)
    priced["manual_panels"] = sorted(r["key"] for r in rows if r["key"] not in ids)
    revised = {**current, "selection":priced["selection"],"quote":priced,"revision":revision,"source":"platform_owner","provisioned":True}
    if current.get("billing_mode") != "payment": revised.update(active_quote=priced,billing_mode="platform_owner")
    settings = {**(row["settings"] or {}), "platform_pricing":revised}
    await db.execute(text("UPDATE tenants SET settings=CAST(:s AS jsonb) WHERE id=:t"), {"s": json.dumps(settings), "t": str(tenant)})
    await db.execute(text("UPDATE tenants SET tier=:tier,seat_limit=:seats,seat_price=:price WHERE id=:t"),
                     {"tier": priced["tier"], "seats": priced["seats"], "price": priced["seat_price"], "t": str(tenant)})
    if current.get("billing_mode") == "payment" and (current.get("active_quote") or {}).get("selection") == priced["selection"]:
        # A manual unpriced grant changes no commercial selection or paid period.
        revised["active_quote"] = {**current["active_quote"],"manual_panels":priced["manual_panels"]}
        await db.execute(text("UPDATE tenants SET settings=CAST(:s AS jsonb) WHERE id=:t"),{"s":json.dumps(settings),"t":str(tenant)})
    else:
        await create_order(db, tenant, actor, selection, "invoice", uuid.uuid4())
    from services.common.platform_usage import activate
    await activate(db, tenant, priced, f"override:{revision}", revision, source="platform_owner", actor=actor, reason="Panel checkbox edit")


async def paid(db, order, payment, *, force_review=False):
    # Payment payloads reach this only after server-side provider verification
    # or a signature-verified webhook. Neither redirects nor client amounts count.
    if payment.get("status") != "success" or str(payment.get("currency", "")).upper() != order["quote"]["currency"] or payment.get("amount") != order["quote"]["amount_cents"]:
        raise HTTPException(409, "Payment status, currency or amount does not match this invoice")
    reference = payment.get("reference")
    if reference != order["reference"]:
        attempt = (await db.execute(text("SELECT 1 FROM platform_checkout_attempts WHERE reference=:r AND order_id=:id"), {"r":reference,"id":str(order["id"])})).first()
        if not attempt: raise HTTPException(409, "Payment reference mismatch")
    if order["intent"] == "credit_topup":
        from services.common.platform_credits import settle
        return await settle(db,order,payment)
    if order["intent"] == "subscription" and order["quote"]["amount_cents"] > 0 and not order.get("plan_code"):
        raise HTTPException(409, "Subscription checkout has no provider plan")
    tenant = await tenant_lock(db, order["tenant_id"])
    row = (await db.execute(text("SELECT * FROM platform_orders WHERE id=:id FOR UPDATE"), {"id": str(order["id"])})).mappings().one()
    if row["paid_at"]: return {"status": row["status"], "duplicate": True}
    current = state(tenant)
    from services.common.platform_proration import quote_expired
    matching = current.get("revision") == order["revision"] and not force_review and not quote_expired(order["quote"])
    if order["intent"] == "renewal":
        matching = current.get("active_revision", current.get("revision")) == order["revision"] and not force_review
    if matching and await occupied_seats(db, order["tenant_id"]) > order["quote"]["seats"]:
        matching = False
    status = "paid" if matching else "payment_review"
    await db.execute(text("UPDATE platform_orders SET status=:status,paid_at=now(),payment_id=:pid WHERE id=:id"),
                     {"status": status, "pid": str(payment.get("id") or order["reference"]), "id": str(order["id"])})
    if matching:
        effective = {**order["quote"],"manual_panels":list((current.get("quote") or {}).get("manual_panels",order["quote"].get("manual_panels",[])))}
        await provision(db, order["tenant_id"], effective, order["actor_id"])
        from services.common.platform_usage import activate
        await activate(db, order["tenant_id"], order["quote"], "order:" + str(order["id"]), order["revision"], source="payment", actor=order["actor_id"])
        from datetime import datetime, timezone
        from services.common.platform_usage import add_months
        start = datetime.now(timezone.utc)
        if order["intent"] == "renewal" and current.get("period_end"):
            start = max(start, datetime.fromisoformat(current["period_end"]))
        end = add_months(start, 12 if order["quote"]["period"] == "annually" else 1)
        settings = {**(tenant["settings"] or {}), "platform_pricing": {**current, "provisioned": True,
            "paid_order_id": str(order["id"]), "active_quote": effective, "active_revision":order["revision"],
            "active_plan_code":order.get("plan_code"),
            "billing_mode":"payment", "period_start":start.isoformat(),"period_end":end.isoformat(),
            "credit_net_zar":(order["quote"].get("proration") or {}).get("credit_remaining", current.get("credit_net_zar","0"))}}
        if settings.get("platform_trial",{}).get("status") in {"active","pending"}:
            settings["platform_trial"]={**settings["platform_trial"],"status":"upgraded"}
        await db.execute(text("UPDATE tenants SET settings=CAST(:s AS jsonb),billing_status='active' WHERE id=:t"), {"s": json.dumps(settings), "t": str(order["tenant_id"])})
        if order["intent"] == "subscription" and order["quote"]["amount_cents"] > 0 and not order["quote"].get("proration"):
            await db.execute(text("""INSERT INTO platform_subscriptions(tenant_id,order_id,plan_code,status,quote,revision)
              VALUES(:t,:id,:plan,'active',CAST(:q AS jsonb),:rev) ON CONFLICT(order_id) DO UPDATE SET
                order_id=excluded.order_id,plan_code=excluded.plan_code,status='active',quote=excluded.quote,revision=excluded.revision,updated_at=now()"""),
              {"t": str(order["tenant_id"]), "id": str(order["id"]), "plan": order.get("plan_code"), "q": json.dumps(order["quote"]), "rev": order["revision"]})
    from services.common.platform_billing_events import emit
    await emit(db,order["tenant_id"],"plan.activated" if matching else "payment.review",
        {"order_id":str(order["id"]),"reference":order["reference"],"status":status,"intent":order["intent"],
         "plan_name":order["quote"].get("name"),"seats":order["quote"].get("seats"),"total_zar":order["quote"]["total_zar"]},
        "settled:"+str(order["id"]),("platform_order",order["id"]))
    return {"status": status, "duplicate": False}
