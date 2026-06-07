"""Billing Account routes — CRUD for top-level billing entities.

A BillingAccount can be owned by either a customer or a company, and groups
all subscriptions and invoices for that billing entity. This enables:
- Company billing (one account, many employee subscriptions)
- Multi-property billing (one account, subscriptions at different addresses)
- Consolidated invoicing and dunning
"""

import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select

from services.common.auth import AuthContext, get_auth_context
from services.billing.database import get_session
from services.billing.models import BillingAccount, Invoice, Subscription
from services.billing.schemas import BillingAccountCreate, BillingAccountRead

logger = logging.getLogger("billing.accounts")

router = APIRouter(prefix="/billing-accounts", tags=["Billing Accounts"])


# ---------------------------------------------------------------------------
# POST /billing-accounts — Create
# ---------------------------------------------------------------------------

@router.post("", response_model=BillingAccountRead, status_code=status.HTTP_201_CREATED)
async def create_billing_account(
    body: BillingAccountCreate,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Create a new billing account.

    Provide either customer_id (individual) or company_id (corporate),
    never both. The account_number must be unique per tenant.
    """
    if body.customer_id and body.company_id:
        raise HTTPException(
            status_code=400,
            detail="Provide either customer_id or company_id, not both",
        )
    if not body.customer_id and not body.company_id:
        raise HTTPException(
            status_code=400,
            detail="Either customer_id or company_id is required",
        )

    async with get_session() as session:
        # Check uniqueness of account_number per tenant
        existing = await session.execute(
            select(BillingAccount).where(
                BillingAccount.tenant_id == ctx.tenant_id,
                BillingAccount.account_number == body.account_number,
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=409,
                detail=f"Account number '{body.account_number}' already exists",
            )

        acct = BillingAccount(
            tenant_id=ctx.tenant_id,
            customer_id=body.customer_id,
            company_id=body.company_id,
            account_number=body.account_number,
            account_name=body.account_name,
            billing_email=body.billing_email,
            payment_method=body.payment_method,
            payment_terms=body.payment_terms,
            credit_limit_zar=body.credit_limit_zar,
            auto_debit=body.auto_debit,
        )
        session.add(acct)
        await session.flush()
        await session.refresh(acct)
        logger.info("Created billing account %s (%s)", acct.id, acct.account_number)
        return BillingAccountRead.model_validate(acct)


# ---------------------------------------------------------------------------
# GET /billing-accounts/{id} — Detail
# ---------------------------------------------------------------------------

@router.get("/{account_id}", response_model=BillingAccountRead)
async def get_billing_account(
    account_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    async with get_session() as session:
        result = await session.execute(
            select(BillingAccount).where(
                BillingAccount.id == account_id,
                BillingAccount.tenant_id == ctx.tenant_id,
            )
        )
        acct = result.scalar_one_or_none()
        if not acct:
            raise HTTPException(status_code=404, detail="Billing account not found")
        return BillingAccountRead.model_validate(acct)


# ---------------------------------------------------------------------------
# GET /billing-accounts — List
# ---------------------------------------------------------------------------

@router.get("", response_model=list[BillingAccountRead])
async def list_billing_accounts(
    ctx: AuthContext = Depends(get_auth_context),
    customer_id: Optional[uuid.UUID] = Query(None),
    company_id: Optional[uuid.UUID] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
):
    async with get_session() as session:
        stmt = select(BillingAccount).where(BillingAccount.tenant_id == ctx.tenant_id)
        if customer_id:
            stmt = stmt.where(BillingAccount.customer_id == customer_id)
        if company_id:
            stmt = stmt.where(BillingAccount.company_id == company_id)
        if status_filter:
            stmt = stmt.where(BillingAccount.status == status_filter)

        stmt = stmt.order_by(BillingAccount.created_at.desc()).limit(200)
        result = await session.execute(stmt)
        items = result.scalars().all()
        return [BillingAccountRead.model_validate(a) for a in items]


# ---------------------------------------------------------------------------
# GET /billing-accounts/{id}/subscriptions — List subscriptions for account
# ---------------------------------------------------------------------------

@router.get("/{account_id}/subscriptions", response_model=list[uuid.UUID])
async def list_account_subscriptions(
    account_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Return subscription IDs linked to this billing account."""
    async with get_session() as session:
        result = await session.execute(
            select(Subscription.id).where(
                Subscription.billing_account_id == account_id,
                Subscription.tenant_id == ctx.tenant_id,
            )
        )
        return [row[0] for row in result.all()]


# ---------------------------------------------------------------------------
# GET /billing-accounts/{id}/invoices — List invoices for account
# ---------------------------------------------------------------------------

@router.get("/{account_id}/invoices")
async def list_account_invoices(
    account_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """Return invoices linked to this billing account."""
    from services.billing.schemas import InvoiceRead, PaginatedResponse

    async with get_session() as session:
        stmt = select(Invoice).where(
            Invoice.billing_account_id == account_id,
            Invoice.tenant_id == ctx.tenant_id,
        )
        count_stmt = select(func.count(Invoice.id)).where(
            Invoice.billing_account_id == account_id,
            Invoice.tenant_id == ctx.tenant_id,
        )
        total = (await session.execute(count_stmt)).scalar() or 0
        pages = max(1, (total + page_size - 1) // page_size)

        stmt = stmt.order_by(Invoice.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        items = (await session.execute(stmt)).scalars().all()
        return PaginatedResponse(
            items=[InvoiceRead.model_validate(i) for i in items],
            total=total,
            page=page,
            page_size=page_size,
            pages=pages,
        )


# ---------------------------------------------------------------------------
# POST /billing-accounts/{id}/close — Close account
# ---------------------------------------------------------------------------

@router.post("/{account_id}/close", response_model=BillingAccountRead)
async def close_billing_account(
    account_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Close a billing account. All active subscriptions must be cancelled first."""
    async with get_session() as session:
        result = await session.execute(
            select(BillingAccount).where(
                BillingAccount.id == account_id,
                BillingAccount.tenant_id == ctx.tenant_id,
            )
        )
        acct = result.scalar_one_or_none()
        if not acct:
            raise HTTPException(status_code=404, detail="Billing account not found")
        if acct.status == "closed":
            raise HTTPException(status_code=400, detail="Account is already closed")

        # Check for active subscriptions
        sub_result = await session.execute(
            select(func.count(Subscription.id)).where(
                Subscription.billing_account_id == account_id,
                Subscription.status.in_(["active", "trial", "paused"]),
            )
        )
        active_count = sub_result.scalar() or 0
        if active_count > 0:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot close account with {active_count} active subscriptions. Cancel them first.",
            )

        acct.status = "closed"
        await session.flush()
        await session.refresh(acct)
        logger.info("Closed billing account %s", acct.id)
        return BillingAccountRead.model_validate(acct)
