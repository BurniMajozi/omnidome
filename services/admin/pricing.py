"""Commercial pricing selection, authoritative provisioning and platform invoices."""
import html
import json
import os
import uuid
from decimal import Decimal
from typing import Literal
import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict
from pydantic import Field, model_validator
from sqlalchemy import text
from services.common.auth import AuthContext, get_auth_context
from services.common.db import get_async_session
from services.common.platform_pricing import Selection, catalog, quote
from services.common import platform_commerce as commerce
from services.common.internal_auth import sign_headers, get_secret
from services.admin import iam

router = APIRouter(tags=["Platform pricing"])


@router.get("/pricing/catalog")
async def pricing_catalog(db=Depends(get_async_session)):
    from services.common.platform_invoice import tax_policy
    return {**catalog(), "tax_policy":await tax_policy(db)}


@router.post("/pricing/quote")
async def pricing_quote(selection: Selection, db=Depends(get_async_session)):
    from services.common.platform_invoice import tax_policy
    try: return quote(selection, await tax_policy(db))
    except ValueError as exc: raise HTTPException(422, str(exc))


class OrderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    selection: Selection
    intent: Literal["invoice", "subscription"] = "invoice"
    idempotency_key: uuid.UUID


class BillingProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1,max_length=200)
    address: str = Field(min_length=1,max_length=500)
    vat_registered: bool = False
    prices_include_vat: bool = True
    vat_number: str | None = Field(None,pattern=r"^4[0-9]{9}$")

    @model_validator(mode="after")
    def vendor_number(self):
        if self.vat_registered and not self.vat_number: raise ValueError("A registered vendor requires its VAT number")
        return self


@router.get("/pricing/supplier")
async def supplier_read(ctx: AuthContext = Depends(get_auth_context), db=Depends(get_async_session)):
    await iam.require_platform_admin(ctx, db)
    return (await db.execute(text("SELECT profile FROM platform_invoice_supplier WHERE singleton=true"))).scalar_one_or_none() or {}


@router.put("/pricing/supplier")
async def supplier_update(body: BillingProfile, ctx: AuthContext = Depends(get_auth_context), db=Depends(get_async_session)):
    await iam.require_platform_admin(ctx, db)
    await db.execute(text("""INSERT INTO platform_invoice_supplier(singleton,profile,actor_id) VALUES(true,CAST(:p AS jsonb),:a)
      ON CONFLICT(singleton) DO UPDATE SET profile=excluded.profile,actor_id=excluded.actor_id,updated_at=now()"""), {"p":body.model_dump_json(),"a":str(ctx.user_id)})
    await iam.audit(db,ctx,"pricing.supplier.update","supplier",ctx.user_id,None,{"vat_registered":body.vat_registered})
    return body


@router.get("/tenants/{tenant}/pricing/billing-profile")
async def billing_profile_read(tenant: uuid.UUID, ctx: AuthContext = Depends(get_auth_context), db=Depends(get_async_session)):
    await check_scope(ctx, tenant, db)
    row = await commerce.tenant_lock(db,tenant)
    return {"name":row["name"],"address":"","vat_registered":False,"vat_number":None,"prices_include_vat":True,**((row["settings"] or {}).get("platform_billing") or {})}


@router.put("/tenants/{tenant}/pricing/billing-profile")
async def billing_profile_update(tenant: uuid.UUID, body: BillingProfile, ctx: AuthContext = Depends(get_auth_context), db=Depends(get_async_session)):
    await check_scope(ctx, tenant, db)
    row = await commerce.tenant_lock(db,tenant)
    settings = {**(row["settings"] or {}),"platform_billing":body.model_dump()}
    await db.execute(text("UPDATE tenants SET settings=CAST(:s AS jsonb) WHERE id=:t"), {"s":json.dumps(settings),"t":str(tenant)})
    await iam.audit(db,ctx,"tenant.billing_profile.update","tenant",tenant,tenant,{"vat_registered":body.vat_registered})
    return body


async def check_scope(ctx, tenant, db):
    # Platform owners may administer any tenant; organisation admins only their own.
    await iam.ensure_tenant_scope(ctx, tenant, db)


@router.post("/tenants/{tenant}/pricing/quote")
async def change_preview(tenant: uuid.UUID, selection: Selection, ctx: AuthContext = Depends(get_auth_context), db=Depends(get_async_session)):
    await check_scope(ctx, tenant, db)
    row = await commerce.tenant_lock(db, tenant)
    from services.common.platform_invoice import tax_policy
    try: priced = quote(selection, await tax_policy(db))
    except ValueError as exc: raise HTTPException(422, str(exc))
    current = commerce.state(row)
    if current.get("billing_mode") == "payment" and current.get("active_quote", {}).get("selection") != priced["selection"]:
        from services.common.platform_proration import change_quote
        priced = change_quote(priced, current)
    return priced


def public_order(row):
    return {**{k: row[k] for k in ("id", "tenant_id", "reference", "intent", "quote", "revision", "status", "created_at", "paid_at")},"subscription_status":row.get("subscription_status")}


@router.get("/tenants/{tenant}/pricing")
async def tenant_pricing(tenant: uuid.UUID, ctx: AuthContext = Depends(get_auth_context), db=Depends(get_async_session)):
    await check_scope(ctx, tenant, db)
    from services.common.platform_trials import expire
    await expire(db,tenant)
    row = (await db.execute(text("SELECT settings FROM tenants WHERE id=:t"), {"t": str(tenant)})).mappings().first()
    if not row: raise HTTPException(404, "Tenant not found")
    orders = (await db.execute(text("SELECT * FROM platform_orders WHERE tenant_id=:t ORDER BY created_at DESC LIMIT 30"), {"t": str(tenant)})).mappings().all()
    sub = (await db.execute(text("SELECT status,order_id,updated_at FROM platform_subscriptions WHERE tenant_id=:t ORDER BY updated_at DESC LIMIT 1"), {"t": str(tenant)})).mappings().first()
    return {"pricing": commerce.state(row), "orders": [public_order(x) for x in orders], "subscription": dict(sub) if sub else None}


@router.get("/tenants/{tenant}/pricing/trial")
async def trial_state(tenant: uuid.UUID, ctx: AuthContext = Depends(get_auth_context), db=Depends(get_async_session)):
    await check_scope(ctx,tenant,db)
    from services.common.platform_trials import expire
    await expire(db,tenant)
    row = await commerce.tenant_lock(db,tenant)
    return (row["settings"] or {}).get("platform_trial")


@router.post("/tenants/{tenant}/pricing/trial")
async def trial_start(tenant: uuid.UUID, ctx: AuthContext = Depends(get_auth_context), db=Depends(get_async_session)):
    await check_scope(ctx,tenant,db)
    from services.common.platform_trials import start
    return await start(db,tenant,ctx.user_id)


class FreeSeat(BaseModel):
    user_id: uuid.UUID


@router.put("/tenants/{tenant}/pricing/trial/seat")
async def trial_seat(tenant: uuid.UUID, body: FreeSeat, ctx: AuthContext = Depends(get_auth_context), db=Depends(get_async_session)):
    await check_scope(ctx,tenant,db)
    from services.common.platform_trials import expire
    await expire(db,tenant)
    row = await commerce.tenant_lock(db,tenant)
    settings = row["settings"] or {}
    trial = settings.get("platform_trial") or {}
    if trial.get("status") != "expired" or commerce.state(row).get("billing_mode") != "free":
        raise HTTPException(409,"Free seat selection applies after trial expiry")
    if not (await db.execute(text("SELECT 1 FROM users WHERE id=:u AND tenant_id=:t AND is_active=true"), {"u":str(body.user_id),"t":str(tenant)})).first():
        raise HTTPException(422,"Choose an active member of this organisation")
    settings["platform_trial"] = {**trial,"free_user_id":str(body.user_id)}
    await db.execute(text("UPDATE tenants SET settings=CAST(:s AS jsonb) WHERE id=:t"), {"s":json.dumps(settings),"t":str(tenant)})
    await iam.audit(db,ctx,"trial.free_seat","tenant",tenant,tenant,{"user_id":str(body.user_id)})
    return settings["platform_trial"]


@router.get("/tenants/{tenant}/pricing/orders")
async def invoice_history(tenant: uuid.UUID,limit: int = Query(25,ge=1,le=100),offset: int = Query(0,ge=0,le=100000),
                          ctx: AuthContext = Depends(get_auth_context),db=Depends(get_async_session)):
    await check_scope(ctx,tenant,db)
    count = (await db.execute(text("SELECT count(*) FROM platform_orders WHERE tenant_id=:t"),{"t":str(tenant)})).scalar_one()
    rows = (await db.execute(text("SELECT * FROM platform_orders WHERE tenant_id=:t ORDER BY created_at DESC,id DESC LIMIT :limit OFFSET :offset"),{"t":str(tenant),"limit":limit,"offset":offset})).mappings().all()
    return {"total":count,"limit":limit,"offset":offset,"rows":[public_order(row) for row in rows]}


@router.put("/tenants/{tenant}/pricing")
async def set_pricing(tenant: uuid.UUID, body: OrderRequest, ctx: AuthContext = Depends(get_auth_context), db=Depends(get_async_session)):
    await iam.require_platform_admin(ctx, db)
    await commerce.tenant_lock(db, tenant)
    existing = (await db.execute(text("SELECT id FROM platform_orders WHERE tenant_id=:t AND idempotency_key=:k"), {"t": str(tenant), "k": str(body.idempotency_key)})).first()
    if existing:
        order = await commerce.create_order(db, tenant, ctx.user_id, body.selection, body.intent, body.idempotency_key)
        return {"quote": order["quote"], "order": public_order(order)}
    before = await commerce.tenant_lock(db,tenant)
    if commerce.state(before).get("billing_mode") == "payment":
        order = await commerce.create_order(db,tenant,ctx.user_id,body.selection,body.intent,body.idempotency_key)
        priced,revision = order["quote"],order["revision"]
        await commerce.provision(db,tenant,priced,ctx.user_id)
        changed = await commerce.tenant_lock(db,tenant)
        settings = {**changed["settings"],"platform_pricing":{**commerce.state(changed),"source":"platform_owner","provisioned":True}}
        await db.execute(text("UPDATE tenants SET settings=CAST(:s AS jsonb) WHERE id=:t"),{"s":json.dumps(settings),"t":str(tenant)})
    else:
        priced, revision = await commerce.save_choice(db, tenant, body.selection, ctx.user_id, enable=True)
        order = await commerce.create_order(db, tenant, ctx.user_id, body.selection, body.intent, body.idempotency_key)
    await iam.audit(db, ctx, "tenant.pricing.update", "tenant", tenant, tenant, {"revision": revision, "panels": priced["entitlements"], "order_id": str(order["id"])})
    if order["quote"]["amount_cents"] == 0:
        if order["quote"].get("proration"):
            await db.commit()
            from dataclasses import replace
            settled = await gateway_call(replace(ctx,tenant_id=tenant),"/platform-checkout/settle",{"order_id":str(order["id"])})
            order["status"] = settled["status"]
            order["subscription_status"] = settled.get("subscription_status")
        else:
            settled = await commerce.paid(db,order,{"status":"success","currency":"ZAR","amount":0,"reference":order["reference"]})
            order["status"] = settled["status"]
    return {"quote": priced, "order": public_order(order)}


@router.post("/tenants/{tenant}/pricing/orders", status_code=201)
async def order(tenant: uuid.UUID, body: OrderRequest, ctx: AuthContext = Depends(get_auth_context), db=Depends(get_async_session)):
    await check_scope(ctx, tenant, db)
    row = await commerce.create_order(db, tenant, ctx.user_id, body.selection, body.intent, body.idempotency_key)
    if row["quote"]["amount_cents"] == 0:
        if row["quote"].get("proration"):
            # Commit the frozen order before the signed broker settles credit and disables old recurrence.
            await db.commit()
            from dataclasses import replace
            settled = await gateway_call(replace(ctx, tenant_id=tenant), "/platform-checkout/settle", {"order_id":str(row["id"])})
            row["status"] = settled["status"]
            row["subscription_status"] = settled.get("subscription_status")
        else:
            await commerce.paid(db, row, {"status": "success", "currency": "ZAR", "amount": 0, "reference": row["reference"], "id": "free"})
            row["status"] = "paid"
    return public_order(row)


async def gateway_call(ctx, path, body):
    url = os.getenv("BILLING_SERVICE_URL", "http://billing:8003").rstrip("/") + path
    headers = {"X-Tenant-Id": str(ctx.tenant_id), "X-User-Id": str(ctx.user_id), "X-Roles": ",".join(ctx.roles)}
    headers.update(sign_headers(headers, "POST", path, get_secret()))
    try:
        async with httpx.AsyncClient(timeout=40) as client: response = await client.post(url, headers=headers, json=body)
    except httpx.HTTPError: raise HTTPException(503, "Payment gateway is unavailable; your invoice is saved")
    if response.status_code >= 400:
        try: detail = response.json().get("detail", "Payment gateway request failed")
        except ValueError: detail = "Payment gateway request failed"
        raise HTTPException(response.status_code, detail)
    return response.json()


class CheckoutRequest(BaseModel):
    order_id: uuid.UUID


@router.post("/tenants/{tenant}/pricing/checkout")
async def checkout(tenant: uuid.UUID, body: CheckoutRequest, ctx: AuthContext = Depends(get_auth_context), db=Depends(get_async_session)):
    await check_scope(ctx, tenant, db)
    row = (await db.execute(text("SELECT id FROM platform_orders WHERE id=:id AND tenant_id=:t"), {"id": str(body.order_id), "t": str(tenant)})).first()
    if not row: raise HTTPException(404, "Invoice not found")
    # A platform owner administering another tenant uses its identity with the
    # target tenant on this signed service call; the broker verifies the platform role.
    from dataclasses import replace
    return await gateway_call(replace(ctx, tenant_id=tenant), "/platform-checkout/initialize", {"order_id": str(body.order_id)})


@router.post("/tenants/{tenant}/pricing/verify")
async def verify(tenant: uuid.UUID, body: CheckoutRequest, ctx: AuthContext = Depends(get_auth_context), db=Depends(get_async_session)):
    await check_scope(ctx, tenant, db)
    exists = (await db.execute(text("SELECT id FROM platform_orders WHERE id=:id AND tenant_id=:t"), {"id": str(body.order_id), "t": str(tenant)})).first()
    if not exists: raise HTTPException(404, "Invoice not found")
    from dataclasses import replace
    return await gateway_call(replace(ctx, tenant_id=tenant), "/platform-checkout/verify", {"order_id": str(body.order_id)})


@router.post("/tenants/{tenant}/pricing/cancel")
async def cancel_subscription(tenant: uuid.UUID, body: CheckoutRequest, ctx: AuthContext = Depends(get_auth_context), db=Depends(get_async_session)):
    await check_scope(ctx, tenant, db)
    exists = (await db.execute(text("SELECT id FROM platform_orders WHERE id=:id AND tenant_id=:t"), {"id": str(body.order_id), "t": str(tenant)})).first()
    if not exists: raise HTTPException(404, "Invoice not found")
    from dataclasses import replace
    return await gateway_call(replace(ctx, tenant_id=tenant), "/platform-checkout/cancel", {"order_id": str(body.order_id)})


@router.get("/tenants/{tenant}/pricing/orders/{order_id}/document", response_class=HTMLResponse)
async def invoice_document(tenant: uuid.UUID, order_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context), db=Depends(get_async_session)):
    await check_scope(ctx, tenant, db)
    row = (await db.execute(text("SELECT o.*,t.name AS tenant_name FROM platform_orders o JOIN tenants t ON t.id=o.tenant_id WHERE o.id=:id AND o.tenant_id=:t"), {"id": str(order_id), "t": str(tenant)})).mappings().first()
    if not row: raise HTTPException(404, "Invoice not found")
    e = lambda value: html.escape(str(value))
    priced = row["quote"]
    details = priced.get("invoice_details") or {}
    supplier, customer = details.get("supplier") or {}, details.get("customer") or {"name":row["tenant_name"]}
    heading = details.get("document_type", "Pro forma invoice")
    parties = f"<h2>Supplier</h2><p>{e(supplier.get('name','Not configured'))}<br>{e(supplier.get('address','Not configured'))}<br>VAT number: {e(supplier.get('vat_number') or ('Not supplied' if supplier.get('vat_registered') else 'Not VAT registered'))}</p><h2>Customer</h2><p>{e(customer.get('name',row['tenant_name']))}<br>{e(customer.get('address','Not configured'))}<br>VAT number: {e(customer.get('vat_number') or 'Not registered / not supplied')}</p>"
    incomplete = "" if details.get("complete") else "<p>Pro forma only: required billing details are incomplete. This document is not valid for an input VAT claim.</p>"
    lines = "".join(f"<tr><td>{e(l['description'])}</td><td>{e(l['quantity'])}</td><td>R{e(l['net_zar'])}</td></tr>" for l in priced["lines"])
    capacity = "Purchased credits do not expire and do not change your plan or panel limits." if row["intent"]=="credit_topup" else f"{e(priced['seats'])} seats · Panels: {e(', '.join(priced['entitlements']))}"
    return HTMLResponse(f"<!doctype html><html><head><meta charset='utf-8'><title>Invoice {e(row['reference'])}</title><style>body{{font:16px Arial;max-width:800px;margin:40px auto;padding:20px}}table{{width:100%;border-collapse:collapse}}td,th{{text-align:left;padding:12px;border-bottom:1px solid #ddd}}</style></head><body><h1>{e(heading)}</h1>{incomplete}{parties}<p>{e(row['reference'])} · {e(row['status'])} · Issued {e(row['created_at'].date())}</p><h2>{e(row['tenant_name'])}</h2><p>{e(priced['name'])} · {e(priced['period'])}</p><table><thead><tr><th>Item</th><th>Quantity</th><th>Net</th></tr></thead><tbody>{lines}</tbody></table><p>Net: R{e(priced['net_zar'])}<br>VAT ({e(Decimal(priced.get('vat_rate','0.15'))*100)}%): R{e(priced['vat_zar'])}<br><strong>Total: R{e(priced['total_zar'])} {e(priced['currency'])}</strong></p><p>{capacity}</p></body></html>", headers={"Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'", "Cache-Control": "no-store"})
