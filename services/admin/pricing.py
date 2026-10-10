"""Commercial pricing selection, authoritative provisioning and platform invoices."""
import html
import json
import os
import uuid
from typing import Literal
import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text
from services.common.auth import AuthContext, get_auth_context
from services.common.db import get_async_session
from services.common.platform_pricing import Selection, catalog, quote
from services.common import platform_commerce as commerce
from services.common.internal_auth import sign_headers, get_secret
from services.admin import iam

router = APIRouter(tags=["Platform pricing"])


@router.get("/pricing/catalog")
async def pricing_catalog(): return catalog()


@router.post("/pricing/quote")
async def pricing_quote(selection: Selection):
    try: return quote(selection)
    except ValueError as exc: raise HTTPException(422, str(exc))


class OrderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    selection: Selection
    intent: Literal["invoice", "subscription"] = "invoice"
    idempotency_key: uuid.UUID


async def check_scope(ctx, tenant, db):
    # Platform owners may administer any tenant; organisation admins only their own.
    await iam.ensure_tenant_scope(ctx, tenant, db)


def public_order(row):
    return {k: row[k] for k in ("id", "tenant_id", "reference", "intent", "quote", "revision", "status", "created_at", "paid_at")}


@router.get("/tenants/{tenant}/pricing")
async def tenant_pricing(tenant: uuid.UUID, ctx: AuthContext = Depends(get_auth_context), db=Depends(get_async_session)):
    await check_scope(ctx, tenant, db)
    row = (await db.execute(text("SELECT settings FROM tenants WHERE id=:t"), {"t": str(tenant)})).mappings().first()
    if not row: raise HTTPException(404, "Tenant not found")
    orders = (await db.execute(text("SELECT * FROM platform_orders WHERE tenant_id=:t ORDER BY created_at DESC LIMIT 30"), {"t": str(tenant)})).mappings().all()
    sub = (await db.execute(text("SELECT status,order_id,updated_at FROM platform_subscriptions WHERE tenant_id=:t ORDER BY updated_at DESC LIMIT 1"), {"t": str(tenant)})).mappings().first()
    return {"pricing": commerce.state(row), "orders": [public_order(x) for x in orders], "subscription": dict(sub) if sub else None}


@router.put("/tenants/{tenant}/pricing")
async def set_pricing(tenant: uuid.UUID, body: OrderRequest, ctx: AuthContext = Depends(get_auth_context), db=Depends(get_async_session)):
    await iam.require_platform_admin(ctx, db)
    await commerce.tenant_lock(db, tenant)
    existing = (await db.execute(text("SELECT id FROM platform_orders WHERE tenant_id=:t AND idempotency_key=:k"), {"t": str(tenant), "k": str(body.idempotency_key)})).first()
    if existing:
        order = await commerce.create_order(db, tenant, ctx.user_id, body.selection, body.intent, body.idempotency_key)
        return {"quote": order["quote"], "order": public_order(order)}
    priced, revision = await commerce.save_choice(db, tenant, body.selection, ctx.user_id, enable=True)
    order = await commerce.create_order(db, tenant, ctx.user_id, body.selection, body.intent, body.idempotency_key)
    await iam.audit(db, ctx, "tenant.pricing.update", "tenant", tenant, tenant, {"revision": revision, "panels": priced["entitlements"], "order_id": str(order["id"])})
    return {"quote": priced, "order": public_order(order)}


@router.post("/tenants/{tenant}/pricing/orders", status_code=201)
async def order(tenant: uuid.UUID, body: OrderRequest, ctx: AuthContext = Depends(get_auth_context), db=Depends(get_async_session)):
    await check_scope(ctx, tenant, db)
    row = await commerce.create_order(db, tenant, ctx.user_id, body.selection, body.intent, body.idempotency_key)
    if row["quote"]["amount_cents"] == 0:
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
    lines = "".join(f"<tr><td>{e(l['description'])}</td><td>{e(l['quantity'])}</td><td>R{e(l['net_zar'])}</td></tr>" for l in priced["lines"])
    return HTMLResponse(f"<!doctype html><html><head><meta charset='utf-8'><title>Invoice {e(row['reference'])}</title><style>body{{font:16px Arial;max-width:800px;margin:40px auto;padding:20px}}table{{width:100%;border-collapse:collapse}}td,th{{text-align:left;padding:12px;border-bottom:1px solid #ddd}}</style></head><body><h1>OminiDome platform invoice</h1><p>{e(row['reference'])} · {e(row['status'])}</p><h2>{e(row['tenant_name'])}</h2><p>{e(priced['name'])} · {e(priced['period'])} · {e(priced['seats'])} seats</p><table><thead><tr><th>Item</th><th>Months</th><th>Net</th></tr></thead><tbody>{lines}</tbody></table><p>Net: R{e(priced['net_zar'])}<br>VAT: R{e(priced['vat_zar'])}<br><strong>Total: R{e(priced['total_zar'])} {e(priced['currency'])}</strong></p><p>Panels: {e(', '.join(priced['entitlements']))}</p></body></html>", headers={"Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'", "Cache-Control": "no-store"})
