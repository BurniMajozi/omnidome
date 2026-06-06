"""Invoice Management routes — generation, listing, detail, send, credit notes.

All routes use async SQLAlchemy (session.execute(select(...))).
"""

import logging
import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select

from services.common.auth import AuthContext, get_auth_context
from services.billing.database import compute_vat, get_session, next_invoice_number
from services.billing.models import DunningAction, Invoice
from services.billing.schemas import (
    CreditNoteRequest,
    InvoiceGenerateRequest,
    InvoiceRead,
    InvoiceSendRequest,
    LineItem,
    PaginatedResponse,
)

logger = logging.getLogger("billing.invoices")

router = APIRouter(prefix="/invoices", tags=["Invoices"])

DEFAULT_DUE_DAYS = 30


# ---------------------------------------------------------------------------
# POST /invoices/generate — Batch-generate monthly invoices
# ---------------------------------------------------------------------------

@router.post("/generate", response_model=list[InvoiceRead], status_code=status.HTTP_201_CREATED)
async def generate_invoices(
    body: InvoiceGenerateRequest,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Batch-generate invoices for active customers."""
    async with get_session() as session:
        created: list[Invoice] = []

        customer_ids = body.customer_ids
        if not customer_ids:
            result = await session.execute(
                select(Invoice.customer_id)
                .where(Invoice.tenant_id == ctx.tenant_id)
                .distinct()
            )
            customer_ids = [r[0] for r in result.all()]

        for cid in customer_ids:
            number = next_invoice_number(session, ctx.tenant_id)
            due = body.billing_date + timedelta(days=DEFAULT_DUE_DAYS)

            line_items = [
                {"description": "Monthly internet service", "quantity": 1,
                 "unit_price_zar": "0.00", "total_zar": "0.00"}
            ]
            subtotal = Decimal("0.00")
            vat = compute_vat(subtotal)
            total = subtotal + vat

            inv = Invoice(
                tenant_id=ctx.tenant_id,
                customer_id=cid,
                number=number,
                status="draft",
                subtotal_zar=subtotal,
                vat_zar=vat,
                total_zar=total,
                due_date=due,
                line_items=line_items,
            )
            session.add(inv)
            await session.flush()
            await session.refresh(inv)

            _schedule_dunning(session, inv)
            created.append(inv)

        return [InvoiceRead.model_validate(i) for i in created]


def _schedule_dunning(session, inv: Invoice) -> None:
    """Pre-schedule the dunning workflow for an invoice."""
    due = inv.due_date
    steps = [
        ("sms_reminder", timedelta(days=1)),
        ("email_warning", timedelta(days=7)),
        ("auto_suspend", timedelta(days=14)),
        ("send_to_collections", timedelta(days=30)),
    ]
    for action_type, delta in steps:
        session.add(DunningAction(
            tenant_id=inv.tenant_id,
            invoice_id=inv.id,
            customer_id=inv.customer_id,
            action_type=action_type,
            scheduled_at=due + delta,
        ))


# ---------------------------------------------------------------------------
# GET /invoices — List with filters and pagination
# ---------------------------------------------------------------------------

@router.get("", response_model=PaginatedResponse)
async def list_invoices(
    ctx: AuthContext = Depends(get_auth_context),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: Optional[str] = Query(None, alias="status"),
    customer_id: Optional[uuid.UUID] = Query(None),
    due_from: Optional[date] = Query(None),
    due_to: Optional[date] = Query(None),
    min_amount: Optional[Decimal] = Query(None),
    max_amount: Optional[Decimal] = Query(None),
):
    async with get_session() as session:
        stmt = select(Invoice).where(Invoice.tenant_id == ctx.tenant_id)
        count_stmt = select(func.count(Invoice.id)).where(Invoice.tenant_id == ctx.tenant_id)

        if status_filter:
            stmt = stmt.where(Invoice.status == status_filter)
            count_stmt = count_stmt.where(Invoice.status == status_filter)
        if customer_id:
            stmt = stmt.where(Invoice.customer_id == customer_id)
            count_stmt = count_stmt.where(Invoice.customer_id == customer_id)
        if due_from:
            stmt = stmt.where(Invoice.due_date >= due_from)
            count_stmt = count_stmt.where(Invoice.due_date >= due_from)
        if due_to:
            stmt = stmt.where(Invoice.due_date <= due_to)
            count_stmt = count_stmt.where(Invoice.due_date <= due_to)
        if min_amount is not None:
            stmt = stmt.where(Invoice.total_zar >= min_amount)
            count_stmt = count_stmt.where(Invoice.total_zar >= min_amount)
        if max_amount is not None:
            stmt = stmt.where(Invoice.total_zar <= max_amount)
            count_stmt = count_stmt.where(Invoice.total_zar <= max_amount)

        total_result = await session.execute(count_stmt)
        total = total_result.scalar() or 0
        pages = max(1, (total + page_size - 1) // page_size)

        stmt = stmt.order_by(Invoice.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        items_result = await session.execute(stmt)
        items = items_result.scalars().all()

        return PaginatedResponse(
            items=[InvoiceRead.model_validate(i) for i in items],
            total=total,
            page=page,
            page_size=page_size,
            pages=pages,
        )


# ---------------------------------------------------------------------------
# GET /invoices/{id} — Detail
# ---------------------------------------------------------------------------

@router.get("/{invoice_id}", response_model=InvoiceRead)
async def get_invoice(
    invoice_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    async with get_session() as session:
        result = await session.execute(
            select(Invoice).where(
                Invoice.id == invoice_id,
                Invoice.tenant_id == ctx.tenant_id,
            )
        )
        inv = result.scalar_one_or_none()
        if not inv:
            raise HTTPException(status_code=404, detail="Invoice not found")
        return InvoiceRead.model_validate(inv)


# ---------------------------------------------------------------------------
# POST /invoices/{id}/send — Send invoice via email/SMS
# ---------------------------------------------------------------------------

@router.post("/{invoice_id}/send", response_model=InvoiceRead)
async def send_invoice(
    invoice_id: uuid.UUID,
    body: InvoiceSendRequest,
    ctx: AuthContext = Depends(get_auth_context),
):
    async with get_session() as session:
        result = await session.execute(
            select(Invoice).where(
                Invoice.id == invoice_id,
                Invoice.tenant_id == ctx.tenant_id,
            )
        )
        inv = result.scalar_one_or_none()
        if not inv:
            raise HTTPException(status_code=404, detail="Invoice not found")
        if inv.status == "voided":
            raise HTTPException(status_code=400, detail="Cannot send a voided invoice")

        logger.info("Sending invoice %s via %s to customer %s", inv.number, body.channel, inv.customer_id)

        if inv.status == "draft":
            inv.status = "sent"
            await session.flush()
            await session.refresh(inv)

        return InvoiceRead.model_validate(inv)


# ---------------------------------------------------------------------------
# POST /invoices/{id}/credit-note — Issue credit note
# ---------------------------------------------------------------------------

@router.post("/{invoice_id}/credit-note", response_model=InvoiceRead, status_code=status.HTTP_201_CREATED)
async def create_credit_note(
    invoice_id: uuid.UUID,
    body: CreditNoteRequest,
    ctx: AuthContext = Depends(get_auth_context),
):
    async with get_session() as session:
        result = await session.execute(
            select(Invoice).where(
                Invoice.id == invoice_id,
                Invoice.tenant_id == ctx.tenant_id,
            )
        )
        original = result.scalar_one_or_none()
        if not original:
            raise HTTPException(status_code=404, detail="Invoice not found")
        if original.status == "voided":
            raise HTTPException(status_code=400, detail="Cannot credit a voided invoice")

        if body.line_items:
            li_dicts = [li.model_dump(mode="json") for li in body.line_items]
            subtotal = sum(
                Decimal(str(li.unit_price_zar)) * li.quantity for li in body.line_items
            )
        else:
            li_dicts = original.line_items or []
            subtotal = original.subtotal_zar

        vat = compute_vat(subtotal)
        total = subtotal + vat

        number = next_invoice_number(session, ctx.tenant_id)

        cn = Invoice(
            tenant_id=ctx.tenant_id,
            customer_id=original.customer_id,
            number=f"CN-{number}",
            status="paid",
            subtotal_zar=-subtotal,
            vat_zar=-vat,
            total_zar=-total,
            amount_paid_zar=Decimal("0.00"),
            due_date=date.today(),
            line_items=li_dicts,
            notes=f"Credit note for {original.number}: {body.reason}",
            credit_note_of=original.id,
        )
        session.add(cn)

        if abs(total) >= original.total_zar:
            original.status = "voided"

        await session.flush()
        await session.refresh(cn)
        return InvoiceRead.model_validate(cn)
