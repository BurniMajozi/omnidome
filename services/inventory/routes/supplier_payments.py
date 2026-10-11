"""Supplier payments: bank details and paying purchase orders from the tenant's funded payout wallet.

Same money rule as payroll: nothing leaves unless the tenant's payout wallet (billing) already holds the amount plus
OmniDome's fee, so a short wallet is refused with 402 before anything is sent. A payment is only allowed once the
purchase order has been approved (and so passed the spend-limit / signature control), and the total paid across
non-failed payments can never exceed the order total. Manager access only: this moves money.
"""
import logging
import uuid
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.common.auth import AuthContext, get_auth_context, get_current_tenant_id, get_current_user_id
from services.inventory import payouts_client as payouts
from services.inventory.access import require_tier
from services.inventory.database import PurchaseOrder, Supplier, SupplierBank, SupplierPayment, get_session

logger = logging.getLogger("inventory.supplier_payments")

router = APIRouter(tags=["Supplier payments"])

PAYABLE_PO = ("approved", "sent", "partially_received", "received")
LIVE = ("pending", "processing", "paid")
STATUS = {"success": "paid", "processing": "processing", "pending": "processing", "failed": "failed"}


class BankIn(BaseModel):
    bank_code: str = Field(min_length=1, max_length=20)
    account_name: str = Field(min_length=2, max_length=200)
    account_number: str = Field(min_length=6, max_length=20, pattern=r"^\d+$")


class PayIn(BaseModel):
    amount_zar: Optional[Decimal] = Field(None, gt=0, max_digits=14, decimal_places=2)
    supplier_invoice_ref: Optional[str] = Field(None, max_length=100)


def _pay_dict(p: SupplierPayment) -> dict:
    return {"id": str(p.id), "po_id": str(p.po_id), "amount_zar": float(p.amount_zar), "fee_zar": float(p.fee_zar), "status": p.status,
            "supplier_invoice_ref": p.supplier_invoice_ref, "message": p.message,
            "created_at": p.created_at.isoformat() if p.created_at else None}


async def _supplier(db: AsyncSession, tenant_id, supplier_id) -> Supplier:
    s = (await db.execute(select(Supplier).where(Supplier.id == supplier_id, Supplier.tenant_id == tenant_id))).scalar_one_or_none()
    if s is None:
        raise HTTPException(status_code=404, detail="Supplier not found")
    return s


@router.get("/suppliers/{supplier_id}/bank-details", dependencies=[Depends(require_tier("write"))])
async def get_bank(supplier_id: uuid.UUID, tenant_id: uuid.UUID = Depends(get_current_tenant_id), db: AsyncSession = Depends(get_session)):
    await _supplier(db, tenant_id, supplier_id)
    b = (await db.execute(select(SupplierBank).where(SupplierBank.supplier_id == supplier_id, SupplierBank.tenant_id == tenant_id))).scalar_one_or_none()
    if b is None:
        return {"configured": False}
    return {"configured": True, "bank_code": b.bank_code, "account_name": b.account_name, "account_last4": b.account_last4}


@router.put("/suppliers/{supplier_id}/bank-details", dependencies=[Depends(require_tier("manager"))])
async def set_bank(supplier_id: uuid.UUID, body: BankIn, tenant_id: uuid.UUID = Depends(get_current_tenant_id),
                   user_id: uuid.UUID = Depends(get_current_user_id), db: AsyncSession = Depends(get_session)):
    """Register where the supplier is paid. A change to an existing supplier's account is refused while the supplier has a
    payment still in flight, so a payment cannot be redirected mid-flight."""
    await _supplier(db, tenant_id, supplier_id)
    in_flight = (await db.execute(select(func.count()).select_from(SupplierPayment).where(
        SupplierPayment.tenant_id == tenant_id, SupplierPayment.supplier_id == supplier_id,
        SupplierPayment.status.in_(("pending", "processing"))))).scalar_one()
    if in_flight:
        raise HTTPException(status_code=409, detail="This supplier has a payment in progress; change the bank details once it completes")
    try:
        code = await payouts.create_recipient(tenant_id, body.account_name, body.account_number, body.bank_code)
    except payouts.PayoutError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    b = (await db.execute(select(SupplierBank).where(SupplierBank.supplier_id == supplier_id, SupplierBank.tenant_id == tenant_id))).scalar_one_or_none()
    if b is None:
        b = SupplierBank(tenant_id=tenant_id, supplier_id=supplier_id, bank_code=body.bank_code, account_name=body.account_name,
                         account_last4=body.account_number[-4:], recipient_code=code, updated_by=user_id)
        db.add(b)
    else:
        b.bank_code, b.account_name, b.account_last4, b.recipient_code, b.updated_by = (
            body.bank_code, body.account_name, body.account_number[-4:], code, user_id)
    logger.info("AUDIT inventory.supplier_bank tenant=%s supplier=%s by=%s last4=%s", tenant_id, supplier_id, user_id, body.account_number[-4:])
    await db.flush()
    return {"configured": True, "bank_code": b.bank_code, "account_name": b.account_name, "account_last4": b.account_last4}


async def _paid_so_far(db: AsyncSession, tenant_id, po_id) -> Decimal:
    return Decimal((await db.execute(select(func.coalesce(func.sum(SupplierPayment.amount_zar), 0)).where(
        SupplierPayment.tenant_id == tenant_id, SupplierPayment.po_id == po_id, SupplierPayment.status.in_(LIVE)))).scalar_one())


@router.get("/purchase-orders/{po_id}/payments", dependencies=[Depends(require_tier("write"))])
async def list_payments(po_id: uuid.UUID, tenant_id: uuid.UUID = Depends(get_current_tenant_id), db: AsyncSession = Depends(get_session)):
    po = (await db.execute(select(PurchaseOrder).where(PurchaseOrder.id == po_id, PurchaseOrder.tenant_id == tenant_id))).scalar_one_or_none()
    if po is None:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    rows = (await db.execute(select(SupplierPayment).where(SupplierPayment.tenant_id == tenant_id, SupplierPayment.po_id == po_id)
                             .order_by(SupplierPayment.created_at))).scalars().all()
    paid = await _paid_so_far(db, tenant_id, po_id)
    return {"po_total_zar": float(po.total_zar), "paid_zar": float(paid), "outstanding_zar": float(max(Decimal(po.total_zar) - paid, Decimal(0))),
            "payments": [_pay_dict(p) for p in rows]}


@router.post("/purchase-orders/{po_id}/payments", dependencies=[Depends(require_tier("manager"))], status_code=201)
async def pay_purchase_order(po_id: uuid.UUID, body: PayIn, tenant_id: uuid.UUID = Depends(get_current_tenant_id),
                             user_id: uuid.UUID = Depends(get_current_user_id), db: AsyncSession = Depends(get_session)):
    po = (await db.execute(select(PurchaseOrder).where(PurchaseOrder.id == po_id, PurchaseOrder.tenant_id == tenant_id,
                                                       PurchaseOrder.deleted_at.is_(None)).with_for_update())).scalar_one_or_none()
    if po is None:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    if po.status not in PAYABLE_PO:
        raise HTTPException(status_code=409, detail=f"A purchase order must be approved before it is paid (status: {po.status})")
    bank = (await db.execute(select(SupplierBank).where(SupplierBank.supplier_id == po.supplier_id, SupplierBank.tenant_id == tenant_id))).scalar_one_or_none()
    if bank is None:
        raise HTTPException(status_code=409, detail="Add the supplier's bank details first")
    outstanding = Decimal(po.total_zar) - await _paid_so_far(db, tenant_id, po.id)
    amount = Decimal(body.amount_zar) if body.amount_zar is not None else outstanding
    if amount <= 0 or amount > outstanding:
        raise HTTPException(status_code=400, detail=f"Amount must be between 0.01 and the outstanding R{outstanding:.2f}")
    payment = SupplierPayment(tenant_id=tenant_id, po_id=po.id, supplier_id=po.supplier_id, amount_zar=amount, status="pending",
                              supplier_invoice_ref=body.supplier_invoice_ref, created_by=user_id)
    db.add(payment)
    await db.flush()
    pid, po_number, recipient = payment.id, po.po_number, bank.recipient_code
    # Commit the pending row first: if billing is slow or the connection drops, the payment is recorded (and counts
    # against the order) and can be reconciled, instead of the money moving with no trace here.
    await db.commit()
    try:
        out = await payouts.pay(tenant_id, user_id, str(po_id), str(pid), recipient, f"{amount:.2f}", f"PO {po_number}")
    except payouts.InsufficientFunding as exc:
        await _mark(db, pid, "failed", "Payout wallet was short")
        d = exc.detail
        raise HTTPException(status_code=402, detail={
            "message": f"The payout wallet is short by R{d.get('shortfall_zar', '?')}. Fund it in Billing, then pay again.", **d})
    except payouts.PayoutError as exc:
        # outcome unknown (timeout / gateway): leave it pending; the sync endpoint asks billing/Paystack what happened
        logger.error("supplier payment %s outcome unknown: %s", pid, exc)
        raise HTTPException(status_code=502, detail=f"{exc}. The payment is recorded as pending: use Refresh status before paying again.")
    item = next((i for i in out.get("items", []) if i.get("item_ref") == str(pid)), None)
    status = STATUS.get((item or {}).get("status"), "processing")
    await _mark(db, pid, status, (item or {}).get("message"), (item or {}).get("reference"), Decimal(str((item or {}).get("fee_zar", 0))))
    p = (await db.execute(select(SupplierPayment).where(SupplierPayment.id == pid))).scalar_one()
    return _pay_dict(p)


async def _mark(db: AsyncSession, pid, status: str, message=None, reference=None, fee: Optional[Decimal] = None) -> None:
    p = (await db.execute(select(SupplierPayment).where(SupplierPayment.id == pid).with_for_update())).scalar_one()
    p.status = status
    if message:
        p.message = str(message)[:500]
    if reference:
        p.transfer_reference = reference
    if fee is not None:
        p.fee_zar = fee
    await db.flush()
    await db.commit()


@router.post("/purchase-orders/{po_id}/payments/sync", dependencies=[Depends(require_tier("manager"))])
async def sync_payments(po_id: uuid.UUID, tenant_id: uuid.UUID = Depends(get_current_tenant_id), db: AsyncSession = Depends(get_session)):
    """Ask billing (and through it Paystack) about every payment still in flight and update this order's payments."""
    try:
        doc = await payouts.status(tenant_id, str(po_id))
    except payouts.PayoutError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    rows = {str(p.id): p for p in (await db.execute(select(SupplierPayment).where(
        SupplierPayment.tenant_id == tenant_id, SupplierPayment.po_id == po_id).with_for_update())).scalars().all()}
    seen = set()
    for batch in doc.get("batches", []):                       # oldest first
        for it in batch.get("items", []):
            p = rows.get(it.get("item_ref"))
            if p is None:
                continue
            seen.add(str(p.id))
            p.status = STATUS.get(it.get("status"), "processing")
            p.transfer_reference = it.get("reference") or p.transfer_reference
            p.fee_zar = Decimal(str(it.get("fee_zar", p.fee_zar)))
            if it.get("message"):
                p.message = str(it["message"])[:500]
    for pid, p in rows.items():                                # never reached billing at all: it did not leave
        if pid not in seen and p.status == "pending":
            p.status, p.message = "failed", "The payment never reached the payout provider"
    await db.flush()
    paid = await _paid_so_far(db, tenant_id, po_id)
    return {"paid_zar": float(paid), "payments": [_pay_dict(p) for p in rows.values()]}
