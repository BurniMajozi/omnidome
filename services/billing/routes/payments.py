"""Payment routes — record payments, list payment history."""

import uuid
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from services.common.auth import AuthContext, get_auth_context
from services.billing.database import get_session
from services.billing.models import Invoice, Payment
from services.billing.schemas import PaymentCreate, PaymentRead, PaginatedResponse

router = APIRouter(prefix="/payments", tags=["Payments"])


# ---------------------------------------------------------------------------
# POST /payments — Record a manual / EFT / debit order payment
# ---------------------------------------------------------------------------

@router.post("", response_model=PaymentRead, status_code=status.HTTP_201_CREATED)
def record_payment(
    body: PaymentCreate,
    ctx: AuthContext = Depends(get_auth_context),
):
    with get_session() as session:
        inv = (
            session.query(Invoice)
            .filter(Invoice.id == body.invoice_id, Invoice.tenant_id == ctx.tenant_id)
            .first()
        )
        if not inv:
            raise HTTPException(status_code=404, detail="Invoice not found")
        if inv.status in ("paid", "voided"):
            raise HTTPException(status_code=400, detail=f"Invoice is already {inv.status}")

        outstanding = inv.total_zar - inv.amount_paid_zar
        if body.amount_zar > outstanding:
            raise HTTPException(
                status_code=400,
                detail=f"Amount exceeds outstanding balance of R{outstanding}"
            )

        payment = Payment(
            tenant_id=ctx.tenant_id,
            invoice_id=inv.id,
            customer_id=inv.customer_id,
            amount_zar=body.amount_zar,
            method=body.method,
            reference=body.reference,
            status="completed",
        )
        session.add(payment)

        # Update invoice
        inv.amount_paid_zar += body.amount_zar
        if inv.amount_paid_zar >= inv.total_zar:
            inv.status = "paid"
        elif inv.amount_paid_zar > 0:
            inv.status = "partially_paid"

        session.flush()
        session.refresh(payment)
        return PaymentRead.model_validate(payment)


# ---------------------------------------------------------------------------
# GET /payments — Payment history with filters
# ---------------------------------------------------------------------------

@router.get("", response_model=PaginatedResponse)
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
            total=total,
            page=page,
            page_size=page_size,
            pages=pages,
        )
