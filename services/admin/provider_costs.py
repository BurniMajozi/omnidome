"""Platform Owner supplier evidence; no payment, invoice or entitlement mutation."""
import uuid
from datetime import date
from decimal import Decimal
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import text
from services.common.auth import AuthContext, get_auth_context
from services.common.db import get_async_session
from services.common.platform_usage import append_cost
from services.common.platform_commerce import tenant_lock
from services.admin import iam

router = APIRouter(tags=["Provider cost reconciliation"])


class Receipt(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: Literal["Deepgram", "Firecrawl", "Zernio", "AgentMail"]
    reference: str = Field(min_length=1, max_length=120)
    amount: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    currency: Literal["USD", "ZAR"]
    period_start: date
    period_end: date

    @model_validator(mode="after")
    def period_valid(self):
        self.reference = self.reference.strip()
        if not self.reference or self.period_end <= self.period_start:
            raise ValueError("Enter a supplier reference and a valid service period")
        return self


class Allocation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    receipt_id: uuid.UUID
    amount: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    quantity: Decimal = Field(ge=0, max_digits=18, decimal_places=6)
    unit: Literal["audio minutes", "provider credits", "account months", "inbox months", "domain months", "email capacity blocks", "subscription months", "provider requests", "storage GB months"]
    reason: str = Field(min_length=5, max_length=500)


class Void(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=5, max_length=500)


@router.post("/provider-costs/receipts")
async def record_receipt(body: Receipt, ctx: AuthContext = Depends(get_auth_context), db=Depends(get_async_session)):
    await iam.require_platform_admin(ctx, db)
    normalized = body.reference.casefold()
    ident = uuid.uuid5(uuid.NAMESPACE_URL, f"omnidome:supplier:{body.provider}:{normalized}")
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key,716))"), {"key": str(ident)})
    existing = (await db.execute(text("SELECT * FROM platform_provider_receipts WHERE id=:id"), {"id": str(ident)})).mappings().first()
    if existing:
        if any(existing[key] != getattr(body,key) for key in ("provider", "amount", "currency", "period_start", "period_end")):
            raise HTTPException(409, "This supplier reference already has different evidence; review the original entry")
        return {"id": ident, "status": "recorded", "duplicate": True}
    await db.execute(text("""INSERT INTO platform_provider_receipts
      (id,provider,reference,normalized_reference,amount,currency,period_start,period_end,actor_id)
      VALUES(:id,:provider,:reference,:normalized,:amount,:currency,:period_start,:period_end,:actor)"""),
      {**body.model_dump(), "id": str(ident), "normalized": normalized, "actor": str(ctx.user_id)})
    await iam.audit(db,ctx,"provider.receipt.record","provider_receipt",ident,metadata={"provider":body.provider,"reference":body.reference})
    return {"id": ident, "status": "recorded", "duplicate": False}


@router.get("/provider-costs/receipts")
async def receipts(ctx: AuthContext = Depends(get_auth_context), db=Depends(get_async_session)):
    await iam.require_platform_admin(ctx, db)
    rows = (await db.execute(text("""SELECT r.*,coalesce(sum(a.amount) FILTER(WHERE v.allocation_id IS NULL),0) allocated
      FROM platform_provider_receipts r LEFT JOIN platform_provider_cost_allocations a ON a.receipt_id=r.id
      LEFT JOIN platform_provider_allocation_voids v ON v.allocation_id=a.id
      GROUP BY r.id ORDER BY r.created_at DESC LIMIT 100"""))).mappings().all()
    return [{**dict(row), "amount":str(row["amount"]), "allocated":str(row["allocated"]), "remaining":str(row["amount"]-row["allocated"]), "evidence_source":"platform_owner_entry"} for row in rows]


@router.post("/tenants/{tenant}/usage/cost-allocations")
async def allocate(tenant: uuid.UUID, body: Allocation, ctx: AuthContext = Depends(get_auth_context), db=Depends(get_async_session)):
    await iam.require_platform_admin(ctx, db)
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key,717))"), {"key": str(body.id)})
    await tenant_lock(db,tenant)
    receipt = (await db.execute(text("SELECT * FROM platform_provider_receipts WHERE id=:id FOR UPDATE"), {"id":str(body.receipt_id)})).mappings().first()
    if not receipt:
        raise HTTPException(404, "Supplier evidence not found")
    existing = (await db.execute(text("SELECT * FROM platform_provider_cost_allocations WHERE id=:id"), {"id":str(body.id)})).mappings().first()
    if existing:
        if str(existing["tenant_id"])!=str(tenant) or any(existing[key]!=getattr(body,key) for key in ("receipt_id","amount","quantity","unit","reason")):
            raise HTTPException(409, "Allocation retry differs from the original")
        return {"id":body.id,"duplicate":True}
    used = (await db.execute(text("""SELECT coalesce(sum(a.amount),0) FROM platform_provider_cost_allocations a
      WHERE a.receipt_id=:id AND NOT EXISTS(SELECT 1 FROM platform_provider_allocation_voids v WHERE v.allocation_id=a.id)"""), {"id":str(body.receipt_id)})).scalar()
    if used+body.amount>receipt["amount"]:
        raise HTTPException(409, "Allocation exceeds the supplier invoice's unallocated amount")
    event = uuid.uuid5(uuid.NAMESPACE_URL,"omnidome:supplier-allocation:"+str(body.id))
    await append_cost(db,tenant=tenant,operation=body.id,event_id=event,category="provider_invoice",provider=receipt["provider"],
        quantity=body.quantity,unit=body.unit,amount=body.amount,currency=receipt["currency"],source="allocated",metadata={"receipt_id":str(body.receipt_id),"purpose":"supplier invoice allocation"})
    await db.execute(text("""INSERT INTO platform_provider_cost_allocations
      (id,receipt_id,tenant_id,cost_event_id,amount,quantity,unit,reason,actor_id)
      VALUES(:id,:receipt_id,:tenant,:event,:amount,:quantity,:unit,:reason,:actor)"""),
      {**body.model_dump(),"id":str(body.id),"receipt_id":str(body.receipt_id),"tenant":str(tenant),"event":str(event),"actor":str(ctx.user_id)})
    await iam.audit(db,ctx,"provider.cost.allocate","provider_allocation",body.id,tenant,{"receipt_id":str(body.receipt_id),"reason":body.reason})
    return {"id":body.id,"duplicate":False}


@router.get("/tenants/{tenant}/usage/cost-allocations")
async def allocations(tenant: uuid.UUID, ctx: AuthContext = Depends(get_auth_context), db=Depends(get_async_session)):
    await iam.require_platform_admin(ctx, db)
    await tenant_lock(db,tenant)
    rows = (await db.execute(text("""SELECT a.*,r.provider,r.reference,r.currency,r.period_start,r.period_end,v.reason void_reason
      FROM platform_provider_cost_allocations a JOIN platform_provider_receipts r ON r.id=a.receipt_id
      LEFT JOIN platform_provider_allocation_voids v ON v.allocation_id=a.id WHERE a.tenant_id=:t ORDER BY a.created_at DESC LIMIT 100"""),{"t":str(tenant)})).mappings().all()
    return [{**dict(row),"amount":str(row["amount"]),"quantity":str(row["quantity"])} for row in rows]


@router.post("/tenants/{tenant}/usage/cost-allocations/{allocation}/void")
async def void_allocation(tenant: uuid.UUID, allocation: uuid.UUID, body: Void, ctx: AuthContext = Depends(get_auth_context), db=Depends(get_async_session)):
    await iam.require_platform_admin(ctx, db)
    await tenant_lock(db,tenant)
    row = (await db.execute(text("SELECT * FROM platform_provider_cost_allocations WHERE id=:id AND tenant_id=:t"),{"id":str(allocation),"t":str(tenant)})).mappings().first()
    if not row:
        raise HTTPException(404,"Allocation not found")
    await db.execute(text("SELECT id FROM platform_provider_receipts WHERE id=:id FOR UPDATE"),{"id":str(row["receipt_id"])})
    inserted = (await db.execute(text("""INSERT INTO platform_provider_allocation_voids(allocation_id,actor_id,reason)
      VALUES(:id,:actor,:reason) ON CONFLICT(allocation_id) DO NOTHING RETURNING allocation_id"""),
      {"id":str(allocation),"actor":str(ctx.user_id),"reason":body.reason})).first()
    if inserted:
        await iam.audit(db,ctx,"provider.cost.void","provider_allocation",allocation,tenant,{"reason":body.reason})
    return {"id":allocation,"status":"void","duplicate":not bool(inserted)}
