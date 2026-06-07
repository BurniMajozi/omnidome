"""Subscription Transfer routes — tenant-to-tenant handover.

Handles the billing side of account handover when a tenant leaves and a new
tenant moves in at the same property. Key operations:
- Initiate transfer (calculate proration, validate)
- Approve transfer (generate settlement invoices)
- Complete transfer (activate new customer's subscription)
- Cancel transfer (rollback)
"""

import logging
import uuid
from datetime import date, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select

from services.common.auth import AuthContext, get_auth_context
from services.billing.database import compute_vat, get_session, next_invoice_number
from services.billing.models import (
    BillingAccount,
    Invoice,
    Subscription,
    SubscriptionTransfer,
)
from services.billing.schemas import (
    SubscriptionTransferCreate,
    SubscriptionTransferRead,
    TransferApprovalRequest,
)

logger = logging.getLogger("billing.transfers")

router = APIRouter(prefix="/transfers", tags=["Subscription Transfers"])

DEFAULT_DUE_DAYS = 30


# ---------------------------------------------------------------------------
# POST /transfers — Initiate a transfer
# ---------------------------------------------------------------------------

@router.post("", response_model=SubscriptionTransferRead, status_code=status.HTTP_201_CREATED)
async def create_transfer(
    body: SubscriptionTransferCreate,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Initiate a subscription transfer from one customer to another.

    This calculates prorated amounts for both outgoing and incoming tenants,
    creates a transfer record, and puts the subscription into pending-transfer
    state. The transfer must then be approved to finalize.
    """
    async with get_session() as session:
        # Validate subscription exists and is active
        sub_result = await session.execute(
            select(Subscription).where(
                Subscription.id == body.subscription_id,
                Subscription.tenant_id == ctx.tenant_id,
            )
        )
        sub = sub_result.scalar_one_or_none()
        if not sub:
            raise HTTPException(status_code=404, detail="Subscription not found")
        if sub.status not in ("active", "trial"):
            raise HTTPException(
                status_code=400,
                detail=f"Cannot transfer a {sub.status} subscription",
            )

        # Validate not already in a transfer
        existing_result = await session.execute(
            select(SubscriptionTransfer).where(
                SubscriptionTransfer.subscription_id == body.subscription_id,
                SubscriptionTransfer.tenant_id == ctx.tenant_id,
                SubscriptionTransfer.status.in_(["pending", "in_progress", "approved"]),
            )
        )
        if existing_result.scalar_one_or_none():
            raise HTTPException(
                status_code=409,
                detail="A transfer is already in progress for this subscription",
            )

        # Calculate proration for outgoing tenant
        transfer_date = body.transfer_date
        period_start = sub.current_period_start or sub.billing_anchor
        period_end = sub.current_period_end or period_start  # simplified

        if transfer_date < period_start or transfer_date >= period_end:
            raise HTTPException(
                status_code=400,
                detail=f"transfer_date must be within current billing period ({period_start} to {period_end})",
            )

        segment = sub.segment
        if segment and sub.segment_pricing and segment in sub.segment_pricing:
            daily_rate = Decimal(str(sub.segment_pricing[segment])) / Decimal(
                (period_end - period_start).days or 1
            )
        else:
            daily_rate = sub.base_price_zar / Decimal(
                (period_end - period_start).days or 1
            )

        days_outgoing = (transfer_date - period_start).days
        days_incoming = (period_end - transfer_date).days
        from_prorated = (daily_rate * Decimal(days_outgoing)).quantize(Decimal("0.01"))
        to_prorated = (daily_rate * Decimal(days_incoming)).quantize(Decimal("0.01"))

        # Validate billing accounts
        if body.to_billing_account_id:
            acct_result = await session.execute(
                select(BillingAccount).where(
                    BillingAccount.id == body.to_billing_account_id,
                    BillingAccount.tenant_id == ctx.tenant_id,
                )
            )
            if not acct_result.scalar_one_or_none():
                raise HTTPException(status_code=404, detail="Target billing account not found")

        # Ensure target customer has a billing account if none specified
        to_billing_account_id = body.to_billing_account_id
        if not to_billing_account_id:
            # Create a billing account for the incoming customer
            acct = BillingAccount(
                tenant_id=ctx.tenant_id,
                customer_id=body.to_customer_id,
                account_number=f"ACCT-{body.to_customer_id.hex[:8]}",
                account_name=f"Auto-created for transfer",
            )
            session.add(acct)
            await session.flush()
            to_billing_account_id = acct.id
            logger.info(
                "Auto-created billing account %s for incoming customer %s",
                acct.id, body.to_customer_id,
            )

        xfer = SubscriptionTransfer(
            tenant_id=ctx.tenant_id,
            subscription_id=body.subscription_id,
            property_id=body.property_id,
            from_customer_id=body.from_customer_id,
            to_customer_id=body.to_customer_id,
            from_billing_account_id=body.from_billing_account_id or sub.billing_account_id,
            to_billing_account_id=to_billing_account_id,
            trigger=body.trigger,
            transfer_date=transfer_date,
            from_prorated_amount_zar=from_prorated,
            to_prorated_amount_zar=to_prorated,
            equipment_transfers=body.equipment_transfers,
            equipment_condition=body.equipment_condition,
            equipment_notes=body.equipment_notes,
            deposit_transfer_zar=body.deposit_transfer_zar,
            initiated_by=body.initiated_by,
            initiated_by_type=body.initiated_by_type,
            notes=body.notes,
            status="pending",
        )
        session.add(xfer)

        # Set subscription status
        sub.status = "active"  # remains active during transfer

        await session.flush()
        await session.refresh(xfer)
        logger.info(
            "Transfer %s initiated: sub %s from %s to %s, prorated R%s / R%s",
            xfer.id, sub.id, body.from_customer_id, body.to_customer_id,
            from_prorated, to_prorated,
        )
        return SubscriptionTransferRead.model_validate(xfer)


# ---------------------------------------------------------------------------
# POST /transfers/{id}/approve — Approve and execute transfer
# ---------------------------------------------------------------------------

@router.post("/{transfer_id}/approve", response_model=SubscriptionTransferRead)
async def approve_transfer(
    transfer_id: uuid.UUID,
    body: TransferApprovalRequest,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Approve a pending transfer and execute it.

    This:
    1. Generates a final prorated invoice for the outgoing tenant
    2. Generates a first prorated invoice for the incoming tenant
    3. Transfers the subscription to the new customer/billing account
    4. Marks the transfer as completed
    """
    async with get_session() as session:
        xfer_result = await session.execute(
            select(SubscriptionTransfer).where(
                SubscriptionTransfer.id == transfer_id,
                SubscriptionTransfer.tenant_id == ctx.tenant_id,
            )
        )
        xfer = xfer_result.scalar_one_or_none()
        if not xfer:
            raise HTTPException(status_code=404, detail="Transfer not found")
        if xfer.status != "pending":
            raise HTTPException(
                status_code=400,
                detail=f"Cannot approve a {xfer.status} transfer",
            )

        sub_result = await session.execute(
            select(Subscription).where(Subscription.id == xfer.subscription_id)
        )
        sub = sub_result.scalar_one_or_none()
        if not sub:
            raise HTTPException(status_code=404, detail="Subscription not found")

        if not body.approved:
            # Cancel the transfer
            xfer.status = "cancelled"
            xfer.cancelled_at = __import__("datetime").datetime.now(
                tz=__import__("datetime").timezone.utc
            )
            xfer.notes = (xfer.notes or "") + f"\nCancelled: {body.notes or 'Rejected'}"
            await session.flush()
            await session.refresh(xfer)
            logger.info("Transfer %s cancelled", xfer.id)
            return SubscriptionTransferRead.model_validate(xfer)

        now = __import__("datetime").datetime.now(tz=__import__("datetime").timezone.utc)

        # 1. Final invoice for outgoing tenant
        if xfer.from_prorated_amount_zar > 0:
            out_vat = compute_vat(xfer.from_prorated_amount_zar)
            out_number = next_invoice_number(session, ctx.tenant_id)
            out_inv = Invoice(
                tenant_id=ctx.tenant_id,
                customer_id=xfer.from_customer_id,
                billing_account_id=xfer.from_billing_account_id,
                property_id=xfer.property_id,
                subscription_id=sub.id,
                number=out_number,
                status="draft",
                subtotal_zar=xfer.from_prorated_amount_zar,
                vat_zar=out_vat,
                total_zar=xfer.from_prorated_amount_zar + out_vat,
                due_date=date.today() + timedelta(days=DEFAULT_DUE_DAYS),
                billing_period_start=sub.current_period_start or sub.billing_anchor,
                billing_period_end=xfer.transfer_date,
                line_items=[{
                    "description": f"Final prorated charge — {sub.plan} (transfer out)",
                    "quantity": 1,
                    "unit_price_zar": str(xfer.from_prorated_amount_zar),
                    "total_zar": str(xfer.from_prorated_amount_zar),
                }],
                notes=f"Transfer out to customer {xfer.to_customer_id}",
            )
            session.add(out_inv)
            await session.flush()
            xfer.settlement_invoice_id = out_inv.id

        # 2. First invoice for incoming tenant
        if xfer.to_prorated_amount_zar > 0:
            in_vat = compute_vat(xfer.to_prorated_amount_zar)
            in_number = next_invoice_number(session, ctx.tenant_id)
            in_inv = Invoice(
                tenant_id=ctx.tenant_id,
                customer_id=xfer.to_customer_id,
                billing_account_id=xfer.to_billing_account_id,
                property_id=xfer.property_id,
                subscription_id=sub.id,
                number=in_number,
                status="draft",
                subtotal_zar=xfer.to_prorated_amount_zar,
                vat_zar=in_vat,
                total_zar=xfer.to_prorated_amount_zar + in_vat,
                due_date=date.today() + timedelta(days=DEFAULT_DUE_DAYS),
                billing_period_start=xfer.transfer_date,
                billing_period_end=sub.current_period_end or xfer.transfer_date,
                line_items=[{
                    "description": f"First prorated charge — {sub.plan} (transfer in)",
                    "quantity": 1,
                    "unit_price_zar": str(xfer.to_prorated_amount_zar),
                    "total_zar": str(xfer.to_prorated_amount_zar),
                }],
                notes=f"Transfer in from customer {xfer.from_customer_id}",
            )
            session.add(in_inv)

        # 3. Transfer the subscription
        sub.customer_id = xfer.to_customer_id
        sub.billing_account_id = xfer.to_billing_account_id
        sub.property_id = xfer.property_id
        sub.current_period_start = xfer.transfer_date
        # period_end stays the same (end of current cycle)

        # 4. Mark transfer completed
        xfer.status = "completed"
        xfer.approved_at = now
        xfer.completed_at = now
        if body.notes:
            xfer.notes = (xfer.notes or "") + f"\nApproval note: {body.notes}"

        await session.flush()
        await session.refresh(xfer)
        logger.info(
            "Transfer %s completed: subscription %s now belongs to customer %s",
            xfer.id, sub.id, xfer.to_customer_id,
        )
        return SubscriptionTransferRead.model_validate(xfer)


# ---------------------------------------------------------------------------
# GET /transfers/{id} — Get transfer detail
# ---------------------------------------------------------------------------

@router.get("/{transfer_id}", response_model=SubscriptionTransferRead)
async def get_transfer(
    transfer_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    async with get_session() as session:
        result = await session.execute(
            select(SubscriptionTransfer).where(
                SubscriptionTransfer.id == transfer_id,
                SubscriptionTransfer.tenant_id == ctx.tenant_id,
            )
        )
        xfer = result.scalar_one_or_none()
        if not xfer:
            raise HTTPException(status_code=404, detail="Transfer not found")
        return SubscriptionTransferRead.model_validate(xfer)


# ---------------------------------------------------------------------------
# GET /transfers — List transfers
# ---------------------------------------------------------------------------

@router.get("", response_model=list[SubscriptionTransferRead])
async def list_transfers(
    ctx: AuthContext = Depends(get_auth_context),
    subscription_id: Optional[uuid.UUID] = Query(None),
    from_customer_id: Optional[uuid.UUID] = Query(None),
    to_customer_id: Optional[uuid.UUID] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
):
    async with get_session() as session:
        stmt = select(SubscriptionTransfer).where(
            SubscriptionTransfer.tenant_id == ctx.tenant_id
        )
        if subscription_id:
            stmt = stmt.where(SubscriptionTransfer.subscription_id == subscription_id)
        if from_customer_id:
            stmt = stmt.where(SubscriptionTransfer.from_customer_id == from_customer_id)
        if to_customer_id:
            stmt = stmt.where(SubscriptionTransfer.to_customer_id == to_customer_id)
        if status_filter:
            stmt = stmt.where(SubscriptionTransfer.status == status_filter)

        stmt = stmt.order_by(SubscriptionTransfer.created_at.desc()).limit(200)
        result = await session.execute(stmt)
        items = result.scalars().all()
        return [SubscriptionTransferRead.model_validate(x) for x in items]
