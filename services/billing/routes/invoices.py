"""Invoice Management routes - generation, listing, detail, send, void, credit notes.

Sync SQLAlchemy sessions inside async handlers (billing's pattern). Revenue is posted to the
finance service from INVOICES ONLY, through the durable outbox in finance_posting.py: the journal
entry is queued in the same transaction as the status change and delivered after commit.
"""

import logging
import uuid
from datetime import date
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select

from services.common.auth import AuthContext, get_auth_context
from services.billing import finance_posting as fp, invoicing
from services.billing.access import require_tier
from services.billing.database import compute_vat, get_session, next_invoice_number
from services.billing.models import CustomerCredit, Invoice, Subscription
from services.billing.schemas import (
    CreditNoteRequest,
    GeneratedInvoice,
    InvoiceGenerateRequest,
    InvoiceRead,
    InvoiceSendRequest,
    PaginatedResponse,
)

logger = logging.getLogger("billing.invoices")

router = APIRouter(prefix="/invoices", tags=["Invoices"])

DEFAULT_DUE_DAYS = invoicing.DEFAULT_DUE_DAYS


# ---------------------------------------------------------------------------
# POST /invoices/generate - idempotent batch generation
# ---------------------------------------------------------------------------

@router.post("/generate", response_model=list[GeneratedInvoice], status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_tier("admin"))])
async def generate_invoices(
    body: InvoiceGenerateRequest,
    response: Response,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Create-or-get one invoice per subscription whose current period is due on/before
    ``billing_date``. Idempotent: a second call creates nothing and reports the existing invoices
    (``created: false``); the period advances once, in the same transaction as the invoice.
    Response status is 201 when something was created, else 200."""
    with get_session() as session:
        stmt = select(Subscription).where(
            Subscription.tenant_id == ctx.tenant_id,
            Subscription.status.in_(["active", "trial"]),
        ).order_by(Subscription.created_at).with_for_update()
        if body.customer_ids:
            stmt = stmt.where(Subscription.customer_id.in_(body.customer_ids))
        subscriptions = session.execute(stmt).scalars().all()

        out: list[tuple[Invoice, bool]] = []
        not_due: list = []
        for sub in subscriptions:
            if sub.is_in_trial():
                continue
            inv, created = invoicing.bill_period(session, sub, body.billing_date)
            if inv is None:
                not_due.append(sub.id)
            else:
                out.append((inv, created))
        for inv in invoicing.covering_invoices(session, ctx.tenant_id, not_due, body.billing_date):
            out.append((inv, False))

        result = [GeneratedInvoice.model_validate({**InvoiceRead.model_validate(i).model_dump(), "created": c})
                  for i, c in out]
    response.status_code = status.HTTP_201_CREATED if any(r.created for r in result) else status.HTTP_200_OK
    return result


# ---------------------------------------------------------------------------
# GET /invoices - List with filters and pagination
# ---------------------------------------------------------------------------

@router.get("", response_model=PaginatedResponse, dependencies=[Depends(require_tier("reader"))])
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
    with get_session() as session:
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

        total = session.execute(count_stmt).scalar() or 0
        pages = max(1, (total + page_size - 1) // page_size)

        stmt = stmt.order_by(Invoice.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        items = session.execute(stmt).scalars().all()

        return PaginatedResponse(
            items=[InvoiceRead.model_validate(i) for i in items],
            total=total, page=page, page_size=page_size, pages=pages,
        )


# ---------------------------------------------------------------------------
# GET /invoices/{id} - Detail
# ---------------------------------------------------------------------------

@router.get("/{invoice_id}", response_model=InvoiceRead, dependencies=[Depends(require_tier("reader"))])
async def get_invoice(
    invoice_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    with get_session() as session:
        inv = session.execute(
            select(Invoice).where(Invoice.id == invoice_id, Invoice.tenant_id == ctx.tenant_id)
        ).scalar_one_or_none()
        if not inv:
            raise HTTPException(status_code=404, detail="Invoice not found")
        return InvoiceRead.model_validate(inv)


# ---------------------------------------------------------------------------
# POST /invoices/{id}/send - issue the invoice (clerk may send)
# ---------------------------------------------------------------------------

@router.post("/{invoice_id}/send", response_model=InvoiceRead, dependencies=[Depends(require_tier("clerk"))])
async def send_invoice(
    invoice_id: uuid.UUID,
    body: InvoiceSendRequest,
    ctx: AuthContext = Depends(get_auth_context),
):
    entries = []
    with get_session() as session:
        inv = session.execute(
            select(Invoice).where(Invoice.id == invoice_id, Invoice.tenant_id == ctx.tenant_id).with_for_update()
        ).scalar_one_or_none()
        if not inv:
            raise HTTPException(status_code=404, detail="Invoice not found")
        if inv.status == "voided":
            raise HTTPException(status_code=400, detail="Cannot send a voided invoice")

        logger.info("Sending invoice %s via %s to customer %s", inv.number, body.channel, inv.customer_id)

        if inv.status == "draft":
            inv.status = "sent"
            session.flush()
            invoicing.schedule_dunning(session, inv)       # only issued invoices are dunned
            entry = invoicing.enqueue_issue(session, inv)  # revenue is posted from the invoice
            if entry:
                entries.append(entry)
        result = InvoiceRead.model_validate(inv)
    await fp.deliver_after_commit(ctx.tenant_id, entries)
    return result


# ---------------------------------------------------------------------------
# POST /invoices/{id}/void - void an unpaid invoice (admin)
# ---------------------------------------------------------------------------

@router.post("/{invoice_id}/void", response_model=InvoiceRead, dependencies=[Depends(require_tier("admin"))])
async def void_invoice(invoice_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context)):
    entries = []
    with get_session() as session:
        inv = session.execute(
            select(Invoice).where(Invoice.id == invoice_id, Invoice.tenant_id == ctx.tenant_id).with_for_update()
        ).scalar_one_or_none()
        if not inv:
            raise HTTPException(status_code=404, detail="Invoice not found")
        if inv.credit_note_of is not None:
            raise HTTPException(status_code=400, detail="A credit note cannot be voided")
        if inv.status == "voided":
            raise HTTPException(status_code=409, detail="Invoice is already voided")
        if inv.amount_paid_zar and inv.amount_paid_zar > 0:
            raise HTTPException(status_code=409, detail="Invoice has payments: issue a credit note instead")
        has_credit = session.execute(select(func.count(Invoice.id)).where(
            Invoice.credit_note_of == inv.id, Invoice.tenant_id == ctx.tenant_id)).scalar_one()
        if has_credit:
            raise HTTPException(status_code=409, detail="Invoice has credit notes: it cannot be voided")
        was_issued = inv.status != "draft"
        inv.status = "voided"
        session.flush()
        if was_issued:  # a draft never reached the ledger
            e = fp.void_entry(inv.id, inv.number, fp.sast_today(), inv.total_zar, inv.subtotal_zar, inv.vat_zar)
            if fp.enqueue(session, ctx.tenant_id, e) is not None:
                entries.append(e)
        result = InvoiceRead.model_validate(inv)
    await fp.deliver_after_commit(ctx.tenant_id, entries)
    return result


# ---------------------------------------------------------------------------
# POST /invoices/{id}/credit-note - issue credit note (admin)
# ---------------------------------------------------------------------------

def credit_amounts(original: Invoice, already_sub: Decimal, already_vat: Decimal, body: CreditNoteRequest):
    """(subtotal, vat, line_items) of the requested credit. No line items = credit everything that
    is still creditable (exact, so the last credit never leaves a rounding cent behind)."""
    if body.line_items:
        li = [l.model_dump(mode="json") for l in body.line_items]
        for l, d in zip(body.line_items, li):
            d["total_zar"] = str((Decimal(str(l.unit_price_zar)) * l.quantity).quantize(Decimal("0.01")))
        subtotal = sum((Decimal(str(l.unit_price_zar)) * l.quantity for l in body.line_items),
                       Decimal("0")).quantize(Decimal("0.01"))
        return subtotal, compute_vat(subtotal), li
    return (original.subtotal_zar - already_sub, original.vat_zar - already_vat, original.line_items or [])


def refund_due_increment(total: Decimal, already_credited: Decimal, paid: Decimal, credit: Decimal) -> Decimal:
    """Extra money we now hold for the customer: what they paid beyond what they still owe once
    `credit` is applied, minus what was already owed back before it."""
    net_before = total - already_credited - paid
    net_after = net_before - credit
    return max(Decimal("0"), -net_after) - max(Decimal("0"), -net_before)


@router.post("/{invoice_id}/credit-note", response_model=InvoiceRead, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_tier("admin"))])
async def create_credit_note(
    invoice_id: uuid.UUID,
    body: CreditNoteRequest,
    ctx: AuthContext = Depends(get_auth_context),
):
    entries = []
    with get_session() as session:
        # Row lock: two credit notes at once must see each other's amounts.
        original = session.execute(
            select(Invoice).where(Invoice.id == invoice_id, Invoice.tenant_id == ctx.tenant_id).with_for_update()
        ).scalar_one_or_none()
        if not original:
            raise HTTPException(status_code=404, detail="Invoice not found")
        if original.credit_note_of is not None:
            raise HTTPException(status_code=400, detail="A credit note cannot be credited")
        if original.status == "voided":
            raise HTTPException(status_code=400, detail="Cannot credit a voided invoice")
        if original.status == "draft":
            raise HTTPException(status_code=409, detail="Invoice was never issued: void it instead of crediting it")

        agg = session.execute(select(
            func.coalesce(func.sum(Invoice.total_zar), 0), func.coalesce(func.sum(Invoice.subtotal_zar), 0),
            func.coalesce(func.sum(Invoice.vat_zar), 0),
        ).where(Invoice.credit_note_of == original.id, Invoice.tenant_id == ctx.tenant_id)).one()
        already_credited, already_sub, already_vat = -Decimal(agg[0]), -Decimal(agg[1]), -Decimal(agg[2])

        subtotal, vat, li_dicts = credit_amounts(original, already_sub, already_vat, body)
        total = subtotal + vat
        creditable = original.total_zar - already_credited
        if total <= 0:
            raise HTTPException(status_code=422, detail="Credit total must be greater than zero")
        if total > creditable:
            raise HTTPException(
                status_code=409,
                detail=f"Credit of R{total} exceeds the remaining creditable amount R{creditable} "
                       f"(invoice total R{original.total_zar}, R{already_credited} already credited)",
            )

        refund_due = refund_due_increment(original.total_zar, already_credited, original.amount_paid_zar, total)
        cn = Invoice(
            id=uuid.uuid4(),
            tenant_id=ctx.tenant_id, customer_id=original.customer_id,
            number=f"CN-{next_invoice_number(session, ctx.tenant_id)}",
            status="credit_issued" if refund_due > 0 else "paid",
            subtotal_zar=-subtotal, vat_zar=-vat, total_zar=-total,
            amount_paid_zar=Decimal("0.00"), due_date=date.today(), line_items=li_dicts,
            notes=f"Credit note for {original.number}: {body.reason}", credit_note_of=original.id,
        )
        session.add(cn)

        if refund_due > 0:
            session.add(CustomerCredit(
                tenant_id=ctx.tenant_id, customer_id=original.customer_id, invoice_id=original.id,
                amount_zar=refund_due, kind="refund_required", reference=f"cn:{cn.id}",
                reason=f"Credit note {cn.number} on {original.number} exceeds the unpaid balance"))
        # Fully credited and not paid in full: the invoice is closed. A PAID invoice is never voided.
        if already_credited + total >= original.total_zar and original.status != "paid":
            original.status = "voided"

        session.flush()
        e = fp.credit_note_entry(cn.id, cn.number, fp.sast_today(), total, subtotal, vat)
        if fp.enqueue(session, ctx.tenant_id, e) is not None:
            entries.append(e)
        session.refresh(cn)
        result = InvoiceRead.model_validate(cn)
    await fp.deliver_after_commit(ctx.tenant_id, entries)
    return result
