"""Billing Collections service — routes for the financial collection journey.

Covers:
 1. Debit order / stop order mandates
 2. EFT payments (submit, match, list)
 3. Reference number cleaning
 4. Billing batch runs (create, execute, list, items)
 5. Invoice status movements (log, list)
 6. Network provisioning queue (create, update, process)
 7. Product movements (create, list, update)
 8. Collection events (list, feed)
"""

import logging
import os
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional

import httpx
from fastapi import FastAPI, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from services.common.auth import get_current_tenant_id
from services.common.entitlements import EntitlementGuard
from services.billing_collections.database import get_session, init_tables
from services.billing_collections.models import (
    Base,
    BillingBatchItem,
    BillingBatchRun,
    CollectionEvent,
    DebitOrderMandate,
    EFTPayment,
    InvoiceMovement,
    NetworkProvisioningQueue,
    ProductMovement,
    ReferenceCleanup,
    SubscriptionPaymentMethod,
)

logger = logging.getLogger("billing_collections")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())

app = FastAPI(
    title="OmniDome Billing Collections Service",
    version="1.0.0",
    description="Financial collection journey: debit orders, EFT, batch runs, invoice movement, provisioning, product movement.",
)

guard = EntitlementGuard(module_id="billing_collections")

BILLING_SERVICE_URL = os.getenv("BILLING_SERVICE_URL", "http://billing:8003")
FINANCE_SERVICE_URL = os.getenv("FINANCE_SERVICE_URL", "http://finance:8015")


@app.on_event("startup")
async def startup():
    guard.ensure_startup()
    await init_tables()


@app.middleware("http")
async def entitlement_middleware(request, call_next):
    return await guard.middleware(request, call_next)


# ════════════════════════════════════════════════════════════════════════
# 1. DEBIT ORDER / STOP ORDER MANDATES
# ════════════════════════════════════════════════════════════════════════

class MandateCreate(BaseModel):
    customer_id: str
    account_number: str
    mandate_type: str = "debit_order"  # debit_order, stop_order
    bank_name: Optional[str] = None
    branch_code: Optional[str] = None
    branch_name: Optional[str] = None
    account_holder: Optional[str] = None
    account_number_bank: Optional[str] = None
    account_type: Optional[str] = None
    debit_day: Optional[int] = Field(None, ge=1, le=31)
    first_debit_date: Optional[date] = None
    fixed_amount_zar: Optional[float] = None
    max_amount_zar: Optional[float] = None
    is_notedo: bool = True
    signature_method: Optional[str] = None
    external_reference: Optional[str] = None


class MandateUpdate(BaseModel):
    status: Optional[str] = None
    debit_day: Optional[int] = None
    fixed_amount_zar: Optional[float] = None
    max_amount_zar: Optional[float] = None
    cancellation_reason: Optional[str] = None
    response_day_1: Optional[date] = None
    response_day_2: Optional[date] = None


@app.post("/mandates")
async def create_mandate(
    payload: MandateCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    mandate = DebitOrderMandate(
        tenant_id=tenant_id,
        customer_id=uuid.UUID(payload.customer_id),
        account_number=payload.account_number,
        mandate_type=payload.mandate_type,
        bank_name=payload.bank_name,
        branch_code=payload.branch_code,
        branch_name=payload.branch_name,
        account_holder=payload.account_holder,
        account_number_bank=payload.account_number_bank,
        account_type=payload.account_type,
        debit_day=payload.debit_day,
        first_debit_date=payload.first_debit_date,
        fixed_amount_zar=Decimal(str(payload.fixed_amount_zar)) if payload.fixed_amount_zar else None,
        max_amount_zar=Decimal(str(payload.max_amount_zar)) if payload.max_amount_zar else None,
        is_notedo=payload.is_notedo,
        signature_method=payload.signature_method,
        external_reference=payload.external_reference,
    )
    db.add(mandate)
    await db.flush()
    await db.refresh(mandate)
    return {"id": str(mandate.id), "status": mandate.status, "mandate_type": mandate.mandate_type}


@app.get("/mandates")
async def list_mandates(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
    customer_id: Optional[str] = None,
    status: Optional[str] = None,
    mandate_type: Optional[str] = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
):
    query = select(DebitOrderMandate).where(DebitOrderMandate.tenant_id == tenant_id)
    if customer_id:
        query = query.where(DebitOrderMandate.customer_id == uuid.UUID(customer_id))
    if status:
        query = query.where(DebitOrderMandate.status == status)
    if mandate_type:
        query = query.where(DebitOrderMandate.mandate_type == mandate_type)
    query = query.order_by(desc(DebitOrderMandate.created_at)).limit(limit).offset(offset)
    result = await db.execute(query)
    mandates = result.scalars().all()
    return [
        {
            "id": str(m.id),
            "customer_id": str(m.customer_id),
            "account_number": m.account_number,
            "mandate_type": m.mandate_type,
            "bank_name": m.bank_name,
            "branch_code": m.branch_code,
            "account_holder": m.account_holder,
            "debit_day": m.debit_day,
            "fixed_amount_zar": float(m.fixed_amount_zar) if m.fixed_amount_zar else None,
            "max_amount_zar": float(m.max_amount_zar) if m.max_amount_zar else None,
            "status": m.status,
            "is_notedo": m.is_notedo,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in mandates
    ]


@app.get("/mandates/{mandate_id}")
async def get_mandate(
    mandate_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    result = await db.execute(
        select(DebitOrderMandate).where(
            DebitOrderMandate.id == mandate_id,
            DebitOrderMandate.tenant_id == tenant_id,
        )
    )
    m = result.scalar_one_or_none()
    if not m:
        raise HTTPException(status_code=404, detail="Mandate not found")
    return {
        "id": str(m.id),
        "customer_id": str(m.customer_id),
        "account_number": m.account_number,
        "mandate_type": m.mandate_type,
        "bank_name": m.bank_name,
        "branch_code": m.branch_code,
        "branch_name": m.branch_name,
        "account_holder": m.account_holder,
        "account_number_bank": m.account_number_bank,
        "account_type": m.account_type,
        "debit_day": m.debit_day,
        "first_debit_date": m.first_debit_date.isoformat() if m.first_debit_date else None,
        "fixed_amount_zar": float(m.fixed_amount_zar) if m.fixed_amount_zar else None,
        "max_amount_zar": float(m.max_amount_zar) if m.max_amount_zar else None,
        "status": m.status,
        "is_notedo": m.is_notedo,
        "response_day_1": m.response_day_1.isoformat() if m.response_day_1 else None,
        "response_day_2": m.response_day_2.isoformat() if m.response_day_2 else None,
        "signature_method": m.signature_method,
        "signature_date": m.signature_date.isoformat() if m.signature_date else None,
        "cancellation_reason": m.cancellation_reason,
        "external_reference": m.external_reference,
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }


@app.put("/mandates/{mandate_id}")
async def update_mandate(
    mandate_id: uuid.UUID,
    payload: MandateUpdate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    result = await db.execute(
        select(DebitOrderMandate).where(
            DebitOrderMandate.id == mandate_id,
            DebitOrderMandate.tenant_id == tenant_id,
        )
    )
    m = result.scalar_one_or_none()
    if not m:
        raise HTTPException(status_code=404, detail="Mandate not found")

    if payload.status is not None:
        m.status = payload.status
    if payload.debit_day is not None:
        m.debit_day = payload.debit_day
    if payload.fixed_amount_zar is not None:
        m.fixed_amount_zar = Decimal(str(payload.fixed_amount_zar))
    if payload.max_amount_zar is not None:
        m.max_amount_zar = Decimal(str(payload.max_amount_zar))
    if payload.cancellation_reason is not None:
        m.cancellation_reason = payload.cancellation_reason
    if payload.response_day_1 is not None:
        m.response_day_1 = payload.response_day_1
    if payload.response_day_2 is not None:
        m.response_day_2 = payload.response_day_2

    await db.flush()
    return {"id": str(m.id), "status": m.status}


@app.delete("/mandates/{mandate_id}", status_code=204)
async def delete_mandate(
    mandate_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    result = await db.execute(
        select(DebitOrderMandate).where(
            DebitOrderMandate.id == mandate_id,
            DebitOrderMandate.tenant_id == tenant_id,
        )
    )
    m = result.scalar_one_or_none()
    if not m:
        raise HTTPException(status_code=404, detail="Mandate not found")
    await db.delete(m)


# ════════════════════════════════════════════════════════════════════════
# 2. EFT PAYMENTS
# ════════════════════════════════════════════════════════════════════════

class EFTPaymentCreate(BaseModel):
    customer_id: str
    account_number: str
    amount_zar: float
    bank_reference: Optional[str] = None
    customer_reference: Optional[str] = None
    bank_name: Optional[str] = None
    branch_code: Optional[str] = None
    payment_date: date = Field(default_factory=date.today)
    notes: Optional[str] = None


class EFTMatchRequest(BaseModel):
    invoice_id: str
    matched_by: Optional[str] = None


@app.post("/eft-payments")
async def create_eft_payment(
    payload: EFTPaymentCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    payment = EFTPayment(
        tenant_id=tenant_id,
        customer_id=uuid.UUID(payload.customer_id),
        account_number=payload.account_number,
        amount_zar=Decimal(str(payload.amount_zar)),
        bank_reference=payload.bank_reference,
        customer_reference=payload.customer_reference,
        bank_name=payload.bank_name,
        branch_code=payload.branch_code,
        payment_date=payload.payment_date,
        notes=payload.notes,
    )
    db.add(payment)
    await db.flush()
    await db.refresh(payment)
    return {"id": str(payment.id), "status": payment.status}


@app.get("/eft-payments")
async def list_eft_payments(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
    customer_id: Optional[str] = None,
    status: Optional[str] = None,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
):
    query = select(EFTPayment).where(EFTPayment.tenant_id == tenant_id)
    if customer_id:
        query = query.where(EFTPayment.customer_id == uuid.UUID(customer_id))
    if status:
        query = query.where(EFTPayment.status == status)
    if from_date:
        query = query.where(EFTPayment.payment_date >= from_date)
    if to_date:
        query = query.where(EFTPayment.payment_date <= to_date)
    query = query.order_by(desc(EFTPayment.payment_date)).limit(limit).offset(offset)
    result = await db.execute(query)
    payments = result.scalars().all()
    return [
        {
            "id": str(p.id),
            "customer_id": str(p.customer_id),
            "account_number": p.account_number,
            "amount_zar": float(p.amount_zar),
            "bank_reference": p.bank_reference,
            "customer_reference": p.customer_reference,
            "status": p.status,
            "matched_invoice_id": str(p.matched_invoice_id) if p.matched_invoice_id else None,
            "payment_date": p.payment_date.isoformat() if p.payment_date else None,
            "created_at": p.created_at.isoformat() if p.created_at else None,
        }
        for p in payments
    ]


@app.post("/eft-payments/{payment_id}/match")
async def match_eft_payment(
    payment_id: uuid.UUID,
    payload: EFTMatchRequest,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    result = await db.execute(
        select(EFTPayment).where(
            EFTPayment.id == payment_id,
            EFTPayment.tenant_id == tenant_id,
        )
    )
    payment = result.scalar_one_or_none()
    if not payment:
        raise HTTPException(status_code=404, detail="EFT payment not found")
    if payment.status != "unmatched":
        raise HTTPException(status_code=400, detail=f"Payment already {payment.status}")

    payment.matched_invoice_id = uuid.UUID(payload.invoice_id)
    payment.matched_at = datetime.utcnow()
    payment.matched_by = uuid.UUID(payload.matched_by) if payload.matched_by else None
    payment.status = "matched"

    # Log collection event
    db.add(CollectionEvent(
        tenant_id=tenant_id,
        customer_id=payment.customer_id,
        account_number=payment.account_number,
        event_type="payment_matched",
        summary=f"EFT payment R{payment.amount_zar} matched to invoice {payload.invoice_id}",
        amount_zar=payment.amount_zar,
        payment_id=payment.id,
        source="billing_collections",
    ))

    await db.flush()
    return {"id": str(payment.id), "status": payment.status, "matched_invoice_id": str(payment.matched_invoice_id)}


# ════════════════════════════════════════════════════════════════════════
# 3. REFERENCE NUMBER CLEANING
# ════════════════════════════════════════════════════════════════════════

class ReferenceCleanRequest(BaseModel):
    original_reference: str
    cleaning_method: str = "strip_spaces"  # strip_spaces, strip_prefix, remove_dashes, account_number_extract, regex_match, manual
    eft_payment_id: Optional[str] = None
    invoice_id: Optional[str] = None
    notes: Optional[str] = None


def _clean_reference(raw: str, method: str) -> str:
    """Apply cleaning rules to a reference number."""
    cleaned = raw.strip()
    if method == "strip_spaces":
        cleaned = cleaned.replace(" ", "").replace("\t", "")
    elif method == "strip_prefix":
        # Remove common prefixes like "REF", "PAY", "INV"
        for prefix in ["REF", "PAY", "INV", "PAYMENT"]:
            if cleaned.upper().startswith(prefix):
                cleaned = cleaned[len(prefix):]
                break
    elif method == "remove_dashes":
        cleaned = cleaned.replace("-", "").replace("_", "")
    elif method == "account_number_extract":
        # Extract last 6-10 digits (likely account number)
        import re
        digits = re.findall(r'\d+', cleaned)
        if digits:
            # Pick the longest digit sequence (likely account number)
            cleaned = max(digits, key=len)
    elif method == "regex_match":
        import re
        # Match patterns like 6-10 consecutive digits
        match = re.search(r'\d{6,10}', cleaned)
        if match:
            cleaned = match.group()
    # "manual" — return as-is, human will edit
    return cleaned.strip()


class ReferenceMatchRequest(BaseModel):
    customer_id: str
    account_number: str
    match_confidence: str = "high"  # high, medium, low


@app.post("/reference-clean")
async def clean_reference(
    payload: ReferenceCleanRequest,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    cleaned = _clean_reference(payload.original_reference, payload.cleaning_method)

    cleanup = ReferenceCleanup(
        tenant_id=tenant_id,
        eft_payment_id=uuid.UUID(payload.eft_payment_id) if payload.eft_payment_id else None,
        invoice_id=uuid.UUID(payload.invoice_id) if payload.invoice_id else None,
        original_reference=payload.original_reference,
        cleaned_reference=cleaned,
        cleaning_method=payload.cleaning_method,
        notes=payload.notes,
    )
    db.add(cleanup)
    await db.flush()
    await db.refresh(cleanup)

    return {
        "id": str(cleanup.id),
        "original_reference": payload.original_reference,
        "cleaned_reference": cleaned,
        "cleaning_method": payload.cleaning_method,
    }


@app.post("/reference-clean/{cleanup_id}/match")
async def match_cleaned_reference(
    cleanup_id: uuid.UUID,
    payload: ReferenceMatchRequest,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    result = await db.execute(
        select(ReferenceCleanup).where(
            ReferenceCleanup.id == cleanup_id,
            ReferenceCleanup.tenant_id == tenant_id,
        )
    )
    cleanup = result.scalar_one_or_none()
    if not cleanup:
        raise HTTPException(status_code=404, detail="Reference cleanup not found")

    cleanup.matched_customer_id = uuid.UUID(payload.customer_id)
    cleanup.matched_account_number = payload.account_number
    cleanup.match_confidence = payload.match_confidence
    cleanup.auto_matched = False

    await db.flush()
    return {"id": str(cleanup.id), "matched_account_number": payload.account_number, "confidence": payload.match_confidence}


@app.get("/reference-clean")
async def list_reference_cleanups(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
    match_confidence: Optional[str] = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
):
    query = select(ReferenceCleanup).where(ReferenceCleanup.tenant_id == tenant_id)
    if match_confidence:
        query = query.where(ReferenceCleanup.match_confidence == match_confidence)
    query = query.order_by(desc(ReferenceCleanup.cleaned_at)).limit(limit).offset(offset)
    result = await db.execute(query)
    items = result.scalars().all()
    return [
        {
            "id": str(i.id),
            "original_reference": i.original_reference,
            "cleaned_reference": i.cleaned_reference,
            "cleaning_method": i.cleaning_method,
            "matched_account_number": i.matched_account_number,
            "match_confidence": i.match_confidence,
            "auto_matched": i.auto_matched,
            "cleaned_at": i.cleaned_at.isoformat() if i.cleaned_at else None,
        }
        for i in items
    ]


# ════════════════════════════════════════════════════════════════════════
# 4. BILLING BATCH RUNS
# ════════════════════════════════════════════════════════════════════════

class BatchRunCreate(BaseModel):
    description: Optional[str] = None
    frequency: str = "monthly"
    run_type: str = "initial"
    billing_day: int = Field(1, ge=1, le=31)
    billing_period_start: date
    billing_period_end: date
    debit_date: date
    payment_instruments: list[str] = Field(default_factory=lambda: ["debit_order"])
    subscription_segments: list[str] = Field(default_factory=list)


class BatchRunExecute(BaseModel):
    triggered_by: Optional[str] = None


@app.post("/batch-runs")
async def create_batch_run(
    payload: BatchRunCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    # Generate batch code
    today = date.today()
    count_result = await db.execute(
        select(func.count(BillingBatchRun.id)).where(
            BillingBatchRun.tenant_id == tenant_id,
            func.date(BillingBatchRun.created_at) == today,
        )
    )
    count = count_result.scalar() or 0
    batch_code = f"BATCH-{today.isoformat()}-{count + 1:04d}"

    batch = BillingBatchRun(
        tenant_id=tenant_id,
        batch_code=batch_code,
        description=payload.description,
        frequency=payload.frequency,
        run_type=payload.run_type,
        billing_day=payload.billing_day,
        billing_period_start=payload.billing_period_start,
        billing_period_end=payload.billing_period_end,
        debit_date=payload.debit_date,
        payment_instruments=payload.payment_instruments,
        subscription_segments=payload.subscription_segments,
    )
    db.add(batch)
    await db.flush()
    await db.refresh(batch)
    return {"id": str(batch.id), "batch_code": batch.batch_code, "status": batch.status}


@app.post("/batch-runs/{batch_id}/execute")
async def execute_batch_run(
    batch_id: uuid.UUID,
    payload: BatchRunExecute,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    """Execute a billing batch run — processes all matching subscriptions."""
    result = await db.execute(
        select(BillingBatchRun).where(
            BillingBatchRun.id == batch_id,
            BillingBatchRun.tenant_id == tenant_id,
        )
    )
    batch = result.scalar_one_or_none()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch run not found")
    if batch.status not in ("scheduled", "failed"):
        raise HTTPException(status_code=400, detail=f"Cannot execute batch in '{batch.status}' status")

    batch.status = "running"
    batch.started_at = datetime.utcnow()
    batch.triggered_by = uuid.UUID(payload.triggered_by) if payload.triggered_by else None

    # Fetch active subscriptions matching batch criteria
    # In production, this would query the billing service's subscriptions table
    # For now, we create batch items from a simplified query
    sub_result = await db.execute(
        select(SubscriptionPaymentMethod).where(
            SubscriptionPaymentMethod.tenant_id == tenant_id,
            SubscriptionPaymentMethod.is_active == True,
        )
    )
    subs = sub_result.scalars().all()

    total_amount = Decimal("0.00")
    for sub in subs:
        item = BillingBatchItem(
            batch_run_id=batch.id,
            tenant_id=tenant_id,
            customer_id=sub.customer_id,
            subscription_id=sub.subscription_id,
            account_number="",  # Would be populated from subscription
            payment_instrument=sub.instrument_type,
            amount_zar=Decimal("0.00"),  # Would be calculated from plan
            status="pending",
        )
        db.add(item)
        total_amount += item.amount_zar

    batch.total_subscriptions = len(subs)
    batch.total_amount_zar = total_amount

    # Simulate processing — in production this would be async workers
    batch.status = "completed"
    batch.completed_at = datetime.utcnow()
    batch.successful_count = len(subs)
    batch.total_invoices_generated = len(subs)

    # Update all items to processed
    for sub in subs:
        pass  # Items would be updated by workers

    # Log collection events
    db.add(CollectionEvent(
        tenant_id=tenant_id,
        customer_id=uuid.UUID("00000000-0000-0000-0000-000000000000"),  # system-level
        event_type="batch_run_completed",
        summary=f"Batch {batch.batch_code} completed: {batch.successful_count}/{batch.total_subscriptions} processed",
        amount_zar=total_amount,
        batch_run_id=batch.id,
        source="billing_collections",
    ))

    await db.flush()
    return {
        "id": str(batch.id),
        "batch_code": batch.batch_code,
        "status": batch.status,
        "total_subscriptions": batch.total_subscriptions,
        "successful_count": batch.successful_count,
        "failed_count": batch.failed_count,
        "total_amount_zar": float(batch.total_amount_zar),
    }


@app.get("/batch-runs")
async def list_batch_runs(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
    status: Optional[str] = None,
    from_date: Optional[date] = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
):
    query = select(BillingBatchRun).where(BillingBatchRun.tenant_id == tenant_id)
    if status:
        query = query.where(BillingBatchRun.status == status)
    if from_date:
        query = query.where(BillingBatchRun.billing_period_start >= from_date)
    query = query.order_by(desc(BillingBatchRun.created_at)).limit(limit).offset(offset)
    result = await db.execute(query)
    batches = result.scalars().all()
    return [
        {
            "id": str(b.id),
            "batch_code": b.batch_code,
            "description": b.description,
            "frequency": b.frequency,
            "run_type": b.run_type,
            "billing_day": b.billing_day,
            "debit_date": b.debit_date.isoformat() if b.debit_date else None,
            "status": b.status,
            "total_subscriptions": b.total_subscriptions,
            "total_invoices_generated": b.total_invoices_generated,
            "total_amount_zar": float(b.total_amount_zar),
            "successful_count": b.successful_count,
            "failed_count": b.failed_count,
            "started_at": b.started_at.isoformat() if b.started_at else None,
            "completed_at": b.completed_at.isoformat() if b.completed_at else None,
            "created_at": b.created_at.isoformat() if b.created_at else None,
        }
        for b in batches
    ]


@app.get("/batch-runs/{batch_id}")
async def get_batch_run(
    batch_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    result = await db.execute(
        select(BillingBatchRun).where(
            BillingBatchRun.id == batch_id,
            BillingBatchRun.tenant_id == tenant_id,
        )
    )
    b = result.scalar_one_or_none()
    if not b:
        raise HTTPException(status_code=404, detail="Batch run not found")
    return {
        "id": str(b.id),
        "batch_code": b.batch_code,
        "description": b.description,
        "frequency": b.frequency,
        "run_type": b.run_type,
        "billing_day": b.billing_day,
        "billing_period_start": b.billing_period_start.isoformat() if b.billing_period_start else None,
        "billing_period_end": b.billing_period_end.isoformat() if b.billing_period_end else None,
        "debit_date": b.debit_date.isoformat() if b.debit_date else None,
        "payment_instruments": b.payment_instruments,
        "subscription_segments": b.subscription_segments,
        "status": b.status,
        "total_subscriptions": b.total_subscriptions,
        "total_invoices_generated": b.total_invoices_generated,
        "total_amount_zar": float(b.total_amount_zar),
        "successful_count": b.successful_count,
        "failed_count": b.failed_count,
        "skipped_count": b.skipped_count,
        "started_at": b.started_at.isoformat() if b.started_at else None,
        "completed_at": b.completed_at.isoformat() if b.completed_at else None,
        "error_log": b.error_log,
        "s3_report_path": b.s3_report_path,
    }


@app.get("/batch-runs/{batch_id}/items")
async def list_batch_items(
    batch_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
    status: Optional[str] = None,
    limit: int = Query(100, le=500),
    offset: int = 0,
):
    query = select(BillingBatchItem).where(
        BillingBatchItem.batch_run_id == batch_id,
        BillingBatchItem.tenant_id == tenant_id,
    )
    if status:
        query = query.where(BillingBatchItem.status == status)
    query = query.order_by(BillingBatchItem.created_at).limit(limit).offset(offset)
    result = await db.execute(query)
    items = result.scalars().all()
    return [
        {
            "id": str(i.id),
            "customer_id": str(i.customer_id),
            "subscription_id": str(i.subscription_id),
            "account_number": i.account_number,
            "payment_instrument": i.payment_instrument,
            "amount_zar": float(i.amount_zar),
            "status": i.status,
            "invoice_id": str(i.invoice_id) if i.invoice_id else None,
            "error_message": i.error_message,
            "processed_at": i.processed_at.isoformat() if i.processed_at else None,
        }
        for i in items
    ]


# ════════════════════════════════════════════════════════════════════════
# 5. INVOICE STATUS MOVEMENTS
# ════════════════════════════════════════════════════════════════════════

class InvoiceMovementCreate(BaseModel):
    invoice_id: str
    action: str
    from_status: Optional[str] = None
    to_status: Optional[str] = None
    amount_zar: Optional[float] = None
    payment_id: Optional[str] = None
    credit_note_id: Optional[str] = None
    reason: Optional[str] = None
    source: Optional[str] = None
    actor_id: Optional[str] = None
    actor_type: Optional[str] = None
    external_reference: Optional[str] = None


@app.post("/invoice-movements")
async def create_invoice_movement(
    payload: InvoiceMovementCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    movement = InvoiceMovement(
        tenant_id=tenant_id,
        invoice_id=uuid.UUID(payload.invoice_id),
        action=payload.action,
        from_status=payload.from_status,
        to_status=payload.to_status,
        amount_zar=Decimal(str(payload.amount_zar)) if payload.amount_zar else None,
        payment_id=uuid.UUID(payload.payment_id) if payload.payment_id else None,
        credit_note_id=uuid.UUID(payload.credit_note_id) if payload.credit_note_id else None,
        reason=payload.reason,
        source=payload.source,
        actor_id=uuid.UUID(payload.actor_id) if payload.actor_id else None,
        actor_type=payload.actor_type,
        external_reference=payload.external_reference,
    )
    db.add(movement)
    await db.flush()
    await db.refresh(movement)
    return {"id": str(movement.id), "action": movement.action}


@app.get("/invoice-movements")
async def list_invoice_movements(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
    invoice_id: Optional[str] = None,
    action: Optional[str] = None,
    source: Optional[str] = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
):
    query = select(InvoiceMovement).where(InvoiceMovement.tenant_id == tenant_id)
    if invoice_id:
        query = query.where(InvoiceMovement.invoice_id == uuid.UUID(invoice_id))
    if action:
        query = query.where(InvoiceMovement.action == action)
    if source:
        query = query.where(InvoiceMovement.source == source)
    query = query.order_by(desc(InvoiceMovement.created_at)).limit(limit).offset(offset)
    result = await db.execute(query)
    movements = result.scalars().all()
    return [
        {
            "id": str(m.id),
            "invoice_id": str(m.invoice_id),
            "action": m.action,
            "from_status": m.from_status,
            "to_status": m.to_status,
            "amount_zar": float(m.amount_zar) if m.amount_zar else None,
            "reason": m.reason,
            "source": m.source,
            "actor_type": m.actor_type,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in movements
    ]


# ════════════════════════════════════════════════════════════════════════
# 6. NETWORK PROVISIONING QUEUE
# ════════════════════════════════════════════════════════════════════════

class ProvisioningCreate(BaseModel):
    customer_id: str
    subscription_id: Optional[str] = None
    action: str  # activate, suspend, unsuspend, cancel, upgrade, downgrade, move
    trigger_source: str
    order_id: Optional[str] = None
    technician_visit_id: Optional[str] = None
    fno_name: Optional[str] = None
    circuit_id: Optional[str] = None
    ont_serial: Optional[str] = None
    old_package: Optional[str] = None
    new_package: Optional[str] = None
    old_speed_mbps: Optional[int] = None
    new_speed_mbps: Optional[int] = None
    priority: int = Field(5, ge=1, le=10)
    scheduled_at: Optional[datetime] = None


class ProvisioningUpdate(BaseModel):
    status: Optional[str] = None
    retry_count: Optional[int] = None
    error_message: Optional[str] = None
    fno_reference: Optional[str] = None
    fno_response: Optional[dict] = None


@app.post("/provisioning")
async def create_provisioning(
    payload: ProvisioningCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    item = NetworkProvisioningQueue(
        tenant_id=tenant_id,
        customer_id=uuid.UUID(payload.customer_id),
        subscription_id=uuid.UUID(payload.subscription_id) if payload.subscription_id else None,
        action=payload.action,
        trigger_source=payload.trigger_source,
        order_id=uuid.UUID(payload.order_id) if payload.order_id else None,
        technician_visit_id=uuid.UUID(payload.technician_visit_id) if payload.technician_visit_id else None,
        fno_name=payload.fno_name,
        circuit_id=payload.circuit_id,
        ont_serial=payload.ont_serial,
        old_package=payload.old_package,
        new_package=payload.new_package,
        old_speed_mbps=payload.old_speed_mbps,
        new_speed_mbps=payload.new_speed_mbps,
        priority=payload.priority,
        scheduled_at=payload.scheduled_at,
    )
    db.add(item)
    await db.flush()
    await db.refresh(item)
    return {"id": str(item.id), "status": item.status, "action": item.action}


@app.put("/provisioning/{item_id}")
async def update_provisioning(
    item_id: uuid.UUID,
    payload: ProvisioningUpdate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    result = await db.execute(
        select(NetworkProvisioningQueue).where(
            NetworkProvisioningQueue.id == item_id,
            NetworkProvisioningQueue.tenant_id == tenant_id,
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Provisioning item not found")

    if payload.status is not None:
        item.status = payload.status
        if payload.status == "in_progress" and not item.started_at:
            item.started_at = datetime.utcnow()
        elif payload.status == "completed":
            item.completed_at = datetime.utcnow()
    if payload.retry_count is not None:
        item.retry_count = payload.retry_count
    if payload.error_message is not None:
        item.error_message = payload.error_message
    if payload.fno_reference is not None:
        item.fno_reference = payload.fno_reference
    if payload.fno_response is not None:
        item.fno_response = payload.fno_response

    await db.flush()
    return {"id": str(item.id), "status": item.status}


@app.get("/provisioning")
async def list_provisioning(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
    status: Optional[str] = None,
    action: Optional[str] = None,
    customer_id: Optional[str] = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
):
    query = select(NetworkProvisioningQueue).where(NetworkProvisioningQueue.tenant_id == tenant_id)
    if status:
        query = query.where(NetworkProvisioningQueue.status == status)
    if action:
        query = query.where(NetworkProvisioningQueue.action == action)
    if customer_id:
        query = query.where(NetworkProvisioningQueue.customer_id == uuid.UUID(customer_id))
    query = query.order_by(NetworkProvisioningQueue.priority, NetworkProvisioningQueue.created_at).limit(limit).offset(offset)
    result = await db.execute(query)
    items = result.scalars().all()
    return [
        {
            "id": str(i.id),
            "customer_id": str(i.customer_id),
            "action": i.action,
            "trigger_source": i.trigger_source,
            "fno_name": i.fno_name,
            "circuit_id": i.circuit_id,
            "old_package": i.old_package,
            "new_package": i.new_package,
            "status": i.status,
            "priority": i.priority,
            "retry_count": i.retry_count,
            "scheduled_at": i.scheduled_at.isoformat() if i.scheduled_at else None,
            "completed_at": i.completed_at.isoformat() if i.completed_at else None,
            "created_at": i.created_at.isoformat() if i.created_at else None,
        }
        for i in items
    ]


@app.post("/provisioning/{item_id}/process")
async def process_provisioning(
    item_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    """Process a pending provisioning item — triggers FNO API call."""
    result = await db.execute(
        select(NetworkProvisioningQueue).where(
            NetworkProvisioningQueue.id == item_id,
            NetworkProvisioningQueue.tenant_id == tenant_id,
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Provisioning item not found")
    if item.status not in ("pending", "retrying"):
        raise HTTPException(status_code=400, detail=f"Cannot process item in '{item.status}' status")

    item.status = "in_progress"
    item.started_at = datetime.utcnow()

    # In production: call FNO API here
    # For now, simulate success
    item.status = "completed"
    item.completed_at = datetime.utcnow()
    item.fno_reference = f"FNO-{uuid.uuid4().hex[:8].upper()}"

    await db.flush()
    return {"id": str(item.id), "status": item.status, "fno_reference": item.fno_reference}


# ════════════════════════════════════════════════════════════════════════
# 7. PRODUCT MOVEMENTS
# ════════════════════════════════════════════════════════════════════════

class ProductMovementCreate(BaseModel):
    customer_id: str
    product_id: str
    product_name: Optional[str] = None
    serial_number: Optional[str] = None
    imei: Optional[str] = None
    asset_tag: Optional[str] = None
    movement_type: str  # assigned, delivered, installed, returned, swapped, recovered
    from_location: Optional[str] = None
    to_location: Optional[str] = None
    from_status: Optional[str] = None
    to_status: Optional[str] = None
    condition: Optional[str] = None
    condition_notes: Optional[str] = None
    order_id: Optional[str] = None
    delivery_id: Optional[str] = None
    technician_visit_id: Optional[str] = None
    unit_cost_zar: Optional[float] = None
    current_value_zar: Optional[float] = None
    courier: Optional[str] = None
    tracking_number: Optional[str] = None
    performed_by: Optional[str] = None
    performed_by_type: Optional[str] = None
    notes: Optional[str] = None


@app.post("/product-movements")
async def create_product_movement(
    payload: ProductMovementCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    movement = ProductMovement(
        tenant_id=tenant_id,
        customer_id=uuid.UUID(payload.customer_id),
        product_id=uuid.UUID(payload.product_id),
        product_name=payload.product_name,
        serial_number=payload.serial_number,
        imei=payload.imei,
        asset_tag=payload.asset_tag,
        movement_type=payload.movement_type,
        from_location=payload.from_location,
        to_location=payload.to_location,
        from_status=payload.from_status,
        to_status=payload.to_status,
        condition=payload.condition,
        condition_notes=payload.condition_notes,
        order_id=uuid.UUID(payload.order_id) if payload.order_id else None,
        delivery_id=uuid.UUID(payload.delivery_id) if payload.delivery_id else None,
        technician_visit_id=uuid.UUID(payload.technician_visit_id) if payload.technician_visit_id else None,
        unit_cost_zar=Decimal(str(payload.unit_cost_zar)) if payload.unit_cost_zar else None,
        current_value_zar=Decimal(str(payload.current_value_zar)) if payload.current_value_zar else None,
        courier=payload.courier,
        tracking_number=payload.tracking_number,
        performed_by=uuid.UUID(payload.performed_by) if payload.performed_by else None,
        performed_by_type=payload.performed_by_type,
        notes=payload.notes,
    )
    db.add(movement)
    await db.flush()
    await db.refresh(movement)
    return {"id": str(movement.id), "movement_type": movement.movement_type}


@app.get("/product-movements")
async def list_product_movements(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
    customer_id: Optional[str] = None,
    product_id: Optional[str] = None,
    movement_type: Optional[str] = None,
    serial_number: Optional[str] = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
):
    query = select(ProductMovement).where(ProductMovement.tenant_id == tenant_id)
    if customer_id:
        query = query.where(ProductMovement.customer_id == uuid.UUID(customer_id))
    if product_id:
        query = query.where(ProductMovement.product_id == uuid.UUID(product_id))
    if movement_type:
        query = query.where(ProductMovement.movement_type == movement_type)
    if serial_number:
        query = query.where(ProductMovement.serial_number == serial_number)
    query = query.order_by(desc(ProductMovement.created_at)).limit(limit).offset(offset)
    result = await db.execute(query)
    items = result.scalars().all()
    return [
        {
            "id": str(i.id),
            "customer_id": str(i.customer_id),
            "product_id": str(i.product_id),
            "product_name": i.product_name,
            "serial_number": i.serial_number,
            "movement_type": i.movement_type,
            "from_location": i.from_location,
            "to_location": i.to_location,
            "condition": i.condition,
            "unit_cost_zar": float(i.unit_cost_zar) if i.unit_cost_zar else None,
            "current_value_zar": float(i.current_value_zar) if i.current_value_zar else None,
            "courier": i.courier,
            "tracking_number": i.tracking_number,
            "created_at": i.created_at.isoformat() if i.created_at else None,
        }
        for i in items
    ]


# ════════════════════════════════════════════════════════════════════════
# 8. COLLECTION EVENTS
# ════════════════════════════════════════════════════════════════════════

@app.get("/collection-events")
async def list_collection_events(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
    customer_id: Optional[str] = None,
    event_type: Optional[str] = None,
    severity: Optional[str] = None,
    from_date: Optional[date] = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
):
    query = select(CollectionEvent).where(CollectionEvent.tenant_id == tenant_id)
    if customer_id:
        query = query.where(CollectionEvent.customer_id == uuid.UUID(customer_id))
    if event_type:
        query = query.where(CollectionEvent.event_type == event_type)
    if severity:
        query = query.where(CollectionEvent.severity == severity)
    if from_date:
        query = query.where(func.date(CollectionEvent.created_at) >= from_date)
    query = query.order_by(desc(CollectionEvent.created_at)).limit(limit).offset(offset)
    result = await db.execute(query)
    events = result.scalars().all()
    return [
        {
            "id": str(e.id),
            "customer_id": str(e.customer_id),
            "account_number": e.account_number,
            "event_type": e.event_type,
            "severity": e.severity,
            "summary": e.summary,
            "amount_zar": float(e.amount_zar) if e.amount_zar else None,
            "source": e.source,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in events
    ]


# ════════════════════════════════════════════════════════════════════════
# HEALTH
# ════════════════════════════════════════════════════════════════════════

@app.get("/health")
async def health():
    return {"status": "ok", "service": "billing_collections", "version": "1.0.0"}
