"""Payment routes - record payments, list payment history."""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from sqlalchemy.exc import IntegrityError

from services.common.auth import AuthContext, get_auth_context
from services.billing import finance_posting as fp, invoicing
from services.billing.access import require_tier
from services.billing.database import get_session
from services.billing.models import Invoice, Payment
from services.billing.schemas import PaymentCreate, PaymentRead, PaginatedResponse

router = APIRouter(prefix="/payments", tags=["Payments"])


# ---------------------------------------------------------------------------
# POST /payments - Record a manual / EFT / debit order payment (clerk tier)
# ---------------------------------------------------------------------------

@router.post("", response_model=PaymentRead, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_tier("clerk"))])
async def record_payment(
    body: PaymentCreate,
    response: Response,
    ctx: AuthContext = Depends(get_auth_context),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key", max_length=128),
):
    """Record a payment. Send an ``Idempotency-Key`` header (or body ``idempotency_key``): a retry with
    the same key returns the original payment (200) instead of recording it twice."""
    key = idempotency_key or body.idempotency_key
    entries: list = []
    with get_session() as session:
        if key:
            prior = session.query(Payment).filter(Payment.tenant_id == ctx.tenant_id, Payment.idempotency_key == key).first()
            if prior is not None:
                response.status_code = status.HTTP_200_OK
                return PaymentRead.model_validate(prior)

        # Row lock until commit: concurrent payments on one invoice must each
        # see the others' amounts, or all of them pass the balance check.
        inv = (
            session.query(Invoice)
            .filter(Invoice.id == body.invoice_id, Invoice.tenant_id == ctx.tenant_id)
            .with_for_update()
            .first()
        )
        if not inv:
            raise HTTPException(status_code=404, detail="Invoice not found")
        if inv.status in ("paid", "voided", "credit_issued") or inv.credit_note_of is not None:
            raise HTTPException(status_code=400, detail=f"Invoice is already {inv.status}")

        outstanding = inv.total_zar - inv.amount_paid_zar
        if body.amount_zar > outstanding:
            raise HTTPException(status_code=400, detail=f"Amount exceeds outstanding balance of R{outstanding}")

        try:
            with session.begin_nested():
                payment, entries = invoicing.apply_payment(
                    session, inv, body.amount_zar, body.method, reference=body.reference, idempotency_key=key)
        except IntegrityError:
            prior = session.query(Payment).filter(
                Payment.tenant_id == ctx.tenant_id, Payment.idempotency_key == key).first() if key else None
            if prior is None:
                raise
            response.status_code = status.HTTP_200_OK
            return PaymentRead.model_validate(prior)
        session.refresh(payment)
        result = PaymentRead.model_validate(payment)
    await fp.deliver_after_commit(ctx.tenant_id, entries)
    return result


# ---------------------------------------------------------------------------
# GET /payments - Payment history with filters
# ---------------------------------------------------------------------------

@router.get("", response_model=PaginatedResponse, dependencies=[Depends(require_tier("reader"))])
def list_payments(
    ctx: AuthContext = Depends(get_auth_context),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    customer_id: Optional[uuid.UUID] = Query(None),
    invoice_id: Optional[uuid.UUID] = Query(None),
    method: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
):
    with get_session() as session:
        q = session.query(Payment).filter(Payment.tenant_id == ctx.tenant_id)

        if customer_id:
            q = q.filter(Payment.customer_id == customer_id)
        if invoice_id:
            q = q.filter(Payment.invoice_id == invoice_id)
        if method:
            q = q.filter(Payment.method == method)
        if status_filter:
            q = q.filter(Payment.status == status_filter)

        total = q.count()
        pages = max(1, (total + page_size - 1) // page_size)
        items = (
            q.order_by(Payment.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

        return PaginatedResponse(
            items=[PaymentRead.model_validate(p) for p in items],
            total=total, page=page, page_size=page_size, pages=pages,
        )
