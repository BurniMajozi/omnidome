"""Tenant-scoped purchasing lifecycle, signed approval, and atomic stock receipts."""
import logging
import hashlib
import base64
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import or_, select, update
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from services.common.auth import AuthContext, get_auth_context, get_current_tenant_id, get_current_user_id
from services.common.http_client import service_get, service_post
from services.inventory.access import require_access, require_tier
from services.inventory import finance_outbox
from services.inventory.purchasing_helpers import (
    VAT_RATE, money, approval_hash, validate_signature, require_state,
    validate_receipt, matches_receipt, render_purchase_order_pdf,
)
from services.inventory.database import (
    get_session,
    next_sequence_number,
    GoodsReceipt,
    GoodsReceiptItem,
    PurchaseOrder,
    PurchaseOrderItem,
    Supplier,
    Warehouse,
    StockMovement,
    InventoryLevel,
    InventorySettings,
    PurchaseOrderApproval,
    InventoryFinanceOutbox,
    Product,
)

logger = logging.getLogger("inventory.purchasing")

router = APIRouter(tags=["Purchasing"])



async def _product_exists(db: AsyncSession, tenant_id: uuid.UUID, product_id: uuid.UUID) -> bool:
    result = await db.execute(select(Product.id).where(
        Product.id == product_id, Product.tenant_id == tenant_id, Product.is_active.is_(True)))
    return result.first() is not None


# ── Schemas ─────────────────────────────────────────────────────────────

class SupplierCreate(BaseModel):
    code: str
    name: str
    contact_person: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    tax_id: Optional[str] = None
    payment_terms: Optional[str] = None
    lead_time_days: int = 7
    notes: Optional[str] = None


class SupplierRead(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    code: str
    name: str
    contact_person: Optional[str]
    email: Optional[str]
    phone: Optional[str]
    address: Optional[str]
    tax_id: Optional[str]
    payment_terms: Optional[str]
    lead_time_days: int
    is_active: bool
    notes: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class POItemInput(BaseModel):
    product_id: uuid.UUID
    quantity_ordered: int = Field(gt=0)
    unit_cost_zar: Decimal = Field(ge=0, max_digits=12, decimal_places=2)


class PurchaseOrderCreate(BaseModel):
    supplier_id: uuid.UUID
    warehouse_id: uuid.UUID
    expected_delivery: Optional[date] = None
    notes: Optional[str] = None
    items: List[POItemInput] = Field(..., min_length=1)


class POItemRead(BaseModel):
    id: uuid.UUID
    product_id: uuid.UUID
    quantity_ordered: int
    quantity_received: int
    unit_cost_zar: Decimal
    total_cost_zar: Decimal

    class Config:
        from_attributes = True


class PurchaseOrderRead(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    supplier_id: uuid.UUID
    warehouse_id: uuid.UUID
    po_number: str
    status: str
    subtotal_zar: Decimal
    tax_zar: Decimal
    total_zar: Decimal
    order_date: date
    expected_delivery: Optional[date]
    received_at: Optional[datetime]
    created_by: Optional[uuid.UUID]
    approved_by: Optional[uuid.UUID]
    currency: str = "ZAR"
    submitted_by: Optional[uuid.UUID] = None
    submitted_at: Optional[datetime] = None
    approved_at: Optional[datetime] = None
    approval_mode: Optional[str] = None
    approval_hash: Optional[str] = None
    rejection_reason: Optional[str] = None
    sent_at: Optional[datetime] = None
    sent_to: Optional[str] = None
    sent_message_id: Optional[str] = None
    cancelled_at: Optional[datetime] = None
    notes: Optional[str]
    created_at: datetime
    items: List[POItemRead] = []

    class Config:
        from_attributes = True


class GRItemInput(BaseModel):
    po_item_id: uuid.UUID
    quantity_received: int = Field(gt=0)
    quantity_rejected: int = Field(0, ge=0)
    rejection_reason: Optional[str] = None
    serial_numbers: Optional[List[str]] = None


class GoodsReceiptCreate(BaseModel):
    receipt_ref: str = Field(min_length=1, max_length=128)
    supplier_delivery_note: Optional[str] = None
    supplier_invoice_number: Optional[str] = None
    notes: Optional[str] = None
    items: List[GRItemInput] = Field(..., min_length=1)

    @field_validator("receipt_ref")
    @classmethod
    def nonempty_ref(cls, value):
        if not value.strip():
            raise ValueError("receipt_ref cannot be blank")
        return value.strip()


class GRItemRead(BaseModel):
    id: uuid.UUID
    product_id: uuid.UUID
    quantity_ordered: int
    quantity_received: int
    quantity_accepted: int
    quantity_rejected: int
    unit_cost_zar: Decimal

    class Config:
        from_attributes = True


class GoodsReceiptRead(BaseModel):
    id: uuid.UUID
    po_id: Optional[uuid.UUID]
    warehouse_id: uuid.UUID
    gr_number: str
    status: str
    received_by: Optional[uuid.UUID]
    received_at: Optional[datetime]
    supplier_delivery_note: Optional[str]
    supplier_invoice_number: Optional[str]
    notes: Optional[str]
    created_at: datetime
    receipt_ref: Optional[str] = None
    value_ex_vat_zar: Decimal = Decimal("0.00")
    vat_zar: Decimal = Decimal("0.00")
    items: List[GRItemRead] = []

    class Config:
        from_attributes = True


# ── Suppliers ───────────────────────────────────────────────────────────

@router.post("/suppliers", response_model=SupplierRead, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_tier("write"))])
async def create_supplier(
    body: SupplierCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    supplier = Supplier(tenant_id=tenant_id, **body.model_dump())
    db.add(supplier)
    await db.flush()
    await db.refresh(supplier)
    return supplier


@router.get("/suppliers", response_model=List[SupplierRead])
async def list_suppliers(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
    active_only: bool = Query(True),
):
    stmt = select(Supplier).where(
        Supplier.tenant_id == tenant_id,
        Supplier.deleted_at.is_(None),
    )
    if active_only:
        stmt = stmt.where(Supplier.is_active.is_(True))
    result = await db.execute(stmt.order_by(Supplier.name))
    return result.scalars().all()


@router.get("/suppliers/{supplier_id}", response_model=SupplierRead)
async def get_supplier(
    supplier_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    result = await db.execute(
        select(Supplier).where(
            Supplier.id == supplier_id,
            Supplier.tenant_id == tenant_id,
            Supplier.deleted_at.is_(None),
        )
    )
    supplier = result.scalar_one_or_none()
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")
    return supplier


@router.delete("/suppliers/{supplier_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_tier("write"))])
async def delete_supplier(
    supplier_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    result = await db.execute(
        select(Supplier).where(
            Supplier.id == supplier_id,
            Supplier.tenant_id == tenant_id,
            Supplier.deleted_at.is_(None),
        )
    )
    supplier = result.scalar_one_or_none()
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")
    supplier.deleted_at = datetime.utcnow()
    await db.flush()


# ── Purchase Orders ─────────────────────────────────────────────────────

@router.post("/purchase-orders", response_model=PurchaseOrderRead, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_tier("write"))])
async def create_purchase_order(
    body: PurchaseOrderCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_session),
):
    supplier_result = await db.execute(
        select(Supplier).where(Supplier.id == body.supplier_id, Supplier.tenant_id == tenant_id, Supplier.deleted_at.is_(None), Supplier.is_active.is_(True))
    )
    if not supplier_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Supplier not found")

    warehouse_result = await db.execute(
        select(Warehouse).where(Warehouse.id == body.warehouse_id, Warehouse.tenant_id == tenant_id, Warehouse.deleted_at.is_(None), Warehouse.is_active.is_(True))
    )
    if not warehouse_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Warehouse not found")

    for item in body.items:
        if not await _product_exists(db, tenant_id, item.product_id):
            raise HTTPException(status_code=404, detail=f"Product {item.product_id} not found")

    subtotal = sum((item.quantity_ordered * item.unit_cost_zar for item in body.items), Decimal("0.00"))
    subtotal = money(subtotal)
    tax = money(subtotal * VAT_RATE)

    po_number = await next_sequence_number(db, tenant_id, "po", "PO")
    po = PurchaseOrder(
        tenant_id=tenant_id,
        supplier_id=body.supplier_id,
        warehouse_id=body.warehouse_id,
        po_number=po_number,
        status="draft",
        subtotal_zar=subtotal,
        tax_zar=tax,
        total_zar=subtotal + tax,
        expected_delivery=body.expected_delivery,
        created_by=user_id,
        notes=body.notes,
    )
    db.add(po)
    await db.flush()

    for item in body.items:
        db.add(PurchaseOrderItem(
            po_id=po.id,
            product_id=item.product_id,
            quantity_ordered=item.quantity_ordered,
            unit_cost_zar=item.unit_cost_zar,
            total_cost_zar=item.quantity_ordered * item.unit_cost_zar,
        ))
    await db.flush()
    await db.refresh(po, attribute_names=["items"])
    return po


class ApprovalInput(BaseModel):
    signer_name: str = Field(min_length=1, max_length=200)
    signature_data: str
    comment: Optional[str] = Field(None, max_length=2000)

    @field_validator("signature_data")
    @classmethod
    def png_signature(cls, value):
        return validate_signature(value)

    @field_validator("signer_name")
    @classmethod
    def nonblank_name(cls, value):
        if not value.strip():
            raise ValueError("Signer name is required")
        return value.strip()


class RejectionInput(ApprovalInput):
    comment: str = Field(min_length=1, max_length=2000)

    @field_validator("comment")
    @classmethod
    def nonblank_reason(cls, value):
        if not value.strip():
            raise ValueError("Rejection reason is required")
        return value.strip()


class SettingsInput(BaseModel):
    auto_approve_limit: Decimal = Field(ge=0, max_digits=14, decimal_places=2)


@router.get("/purchasing/settings")
async def get_purchasing_settings(tenant_id: uuid.UUID = Depends(get_current_tenant_id), db: AsyncSession = Depends(get_session)):
    row = (await db.execute(select(InventorySettings).where(InventorySettings.tenant_id == tenant_id))).scalar_one_or_none()
    return {"auto_approve_limit": str(row.auto_approve_limit if row else Decimal("0.00"))}


@router.put("/purchasing/settings", dependencies=[Depends(require_tier("manager"))])
async def update_purchasing_settings(body: SettingsInput, tenant_id: uuid.UUID = Depends(get_current_tenant_id),
                                     user_id: uuid.UUID = Depends(get_current_user_id), db: AsyncSession = Depends(get_session)):
    # Upsert also serializes concurrent creation of a tenant's first settings row.
    from sqlalchemy.dialects.postgresql import insert
    stmt = insert(InventorySettings).values(tenant_id=tenant_id, auto_approve_limit=body.auto_approve_limit, updated_by=user_id)
    await db.execute(stmt.on_conflict_do_update(index_elements=[InventorySettings.tenant_id],
                      set_={"auto_approve_limit": body.auto_approve_limit, "updated_by": user_id,
                            "updated_at": datetime.now(timezone.utc)}))
    return {"auto_approve_limit": str(money(body.auto_approve_limit))}


async def _locked_items(db, po):
    return (await db.execute(select(PurchaseOrderItem).where(PurchaseOrderItem.po_id == po.id)
                            .order_by(PurchaseOrderItem.id).with_for_update())).scalars().all()


def _audit(db, po, items, decision, user_id=None, body=None):
    digest = approval_hash(po, items)
    mode = "manual" if body else "auto"
    db.add(PurchaseOrderApproval(
        tenant_id=po.tenant_id, po_id=po.id, decision=decision, mode=mode,
        signature_data=body.signature_data if body else None,
        signer_user_id=user_id if body else None,
        signer_name=body.signer_name if body else "auto-approval",
        comment=body.comment if body else None, po_total_hash=digest, po_total_zar=po.total_zar,
    ))
    if decision == "approved":
        po.approval_hash = digest
        po.approval_mode = mode
        po.approved_by = user_id if body else None
        po.approved_at = datetime.now(timezone.utc)


@router.post("/purchase-orders/{po_id}/submit", response_model=PurchaseOrderRead, dependencies=[Depends(require_tier("write"))])
async def submit_purchase_order(po_id: uuid.UUID, tenant_id: uuid.UUID = Depends(get_current_tenant_id),
                                user_id: uuid.UUID = Depends(get_current_user_id), db: AsyncSession = Depends(get_session)):
    po = await _load_po(db, tenant_id, po_id, lock=True)
    require_state(po, ("draft",), "submit")
    items = await _locked_items(db, po)
    if not items:
        raise HTTPException(409, "Cannot submit an empty purchase order")
    settings = (await db.execute(select(InventorySettings).where(InventorySettings.tenant_id == tenant_id)
                                .with_for_update())).scalar_one_or_none()
    limit = settings.auto_approve_limit if settings else Decimal("0")
    po.submitted_by = user_id
    po.submitted_at = datetime.now(timezone.utc)
    po.status = "pending_approval"
    if limit > 0 and po.total_zar <= limit:
        po.status = "approved"
        _audit(db, po, items, "approved")
    await db.flush()
    await db.refresh(po, attribute_names=["items"])
    return po


async def _decide(db, tenant_id, po_id, user_id, body, decision):
    po = await _load_po(db, tenant_id, po_id, lock=True)
    require_state(po, ("pending_approval", "submitted"), decision)
    if user_id in (po.created_by, po.submitted_by):
        raise HTTPException(403, "Creator or submitter cannot manually decide their own purchase order")
    items = await _locked_items(db, po)
    _audit(db, po, items, decision, user_id, body)
    po.status = decision
    if decision == "rejected":
        po.rejection_reason = body.comment
    await db.flush()
    await db.refresh(po, attribute_names=["items"])
    return po


@router.post("/purchase-orders/{po_id}/approve", response_model=PurchaseOrderRead, dependencies=[Depends(require_tier("manager"))])
async def approve_purchase_order(po_id: uuid.UUID, body: ApprovalInput,
                                 tenant_id: uuid.UUID = Depends(get_current_tenant_id),
                                 user_id: uuid.UUID = Depends(get_current_user_id), db: AsyncSession = Depends(get_session)):
    return await _decide(db, tenant_id, po_id, user_id, body, "approved")


@router.post("/purchase-orders/{po_id}/reject", response_model=PurchaseOrderRead, dependencies=[Depends(require_tier("manager"))])
async def reject_purchase_order(po_id: uuid.UUID, body: RejectionInput,
                                tenant_id: uuid.UUID = Depends(get_current_tenant_id),
                                user_id: uuid.UUID = Depends(get_current_user_id), db: AsyncSession = Depends(get_session)):
    return await _decide(db, tenant_id, po_id, user_id, body, "rejected")


async def _is_manager(ctx: AuthContext) -> bool:
    try:
        await require_access(ctx, "manager")
        return True
    except HTTPException:
        return False


def _header_value(value) -> Optional[str]:
    """Header(...) defaults leak through on direct (non-HTTP) calls; accept only real strings."""
    if isinstance(value, str) and value.strip():
        return value.strip()[:128]
    return None


@router.get("/purchase-orders/{po_id}/approvals")
async def list_po_approvals(po_id: uuid.UUID, tenant_id: uuid.UUID = Depends(get_current_tenant_id),
                            db: AsyncSession = Depends(get_session), ctx: AuthContext = Depends(get_auth_context)):
    await _load_po(db, tenant_id, po_id)
    rows = (await db.execute(select(PurchaseOrderApproval).where(PurchaseOrderApproval.tenant_id == tenant_id,
                            PurchaseOrderApproval.po_id == po_id).order_by(PurchaseOrderApproval.decided_at))).scalars().all()
    manager = await _is_manager(ctx)
    # Drawn signatures are sensitive: only managers/admins and the signer themself may read them.
    # Everyone else still gets the signature hash as proof one exists.
    return [{"id": r.id, "decision": r.decision, "mode": r.mode, "signer_user_id": r.signer_user_id,
             "signer_name": r.signer_name,
             "signature_data": r.signature_data if (manager or (r.signer_user_id and r.signer_user_id == ctx.user_id)) else None,
             "signature_hash": hashlib.sha256(r.signature_data.encode()).hexdigest() if r.signature_data else None,
             "comment": r.comment,
             "po_total_hash": r.po_total_hash, "po_total_zar": r.po_total_zar, "decided_at": r.decided_at} for r in rows]


@router.post("/purchase-orders/{po_id}/cancel", response_model=PurchaseOrderRead, dependencies=[Depends(require_tier("write"))])
async def cancel_purchase_order(po_id: uuid.UUID, tenant_id: uuid.UUID = Depends(get_current_tenant_id),
                                db: AsyncSession = Depends(get_session), ctx: AuthContext = Depends(get_auth_context)):
    po = await _load_po(db, tenant_id, po_id, lock=True)
    if not await _is_manager(ctx):
        # Non-managers may only withdraw their own draft.
        if not (po.status == "draft" and po.created_by is not None and po.created_by == ctx.user_id):
            raise HTTPException(403, "Only a manager can cancel this purchase order (creators may cancel their own draft)")
    require_state(po, ("draft", "pending_approval", "submitted", "approved", "rejected", "sent"), "cancel")
    if po.send_claimed_at:
        raise HTTPException(409, "Reconcile the pending supplier email before cancelling this order")
    items = await _locked_items(db, po)
    if any(i.quantity_received for i in items):
        raise HTTPException(409, "Cannot cancel an order being sent or already received")
    po.status = "cancelled"
    po.cancelled_at = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(po, attribute_names=["items"])
    return po


@router.post("/purchase-orders/{po_id}/reapprove", response_model=PurchaseOrderRead, dependencies=[Depends(require_tier("manager"))])
async def reapprove_legacy_purchase_order(po_id: uuid.UUID, body: ApprovalInput,
                                          tenant_id: uuid.UUID = Depends(get_current_tenant_id),
                                          user_id: uuid.UUID = Depends(get_current_user_id),
                                          db: AsyncSession = Depends(get_session)):
    """Manager re-approval of a pre-signature (legacy) approved PO: records a signed approval and stamps the hash."""
    po = await _load_po(db, tenant_id, po_id, lock=True)
    require_state(po, ("approved", "sent", "partially_received"), "re-approve")
    if po.approval_hash or po.approval_mode != "legacy":
        raise HTTPException(409, "Only legacy approvals without a signed snapshot can be re-approved")
    if user_id in (po.created_by, po.submitted_by):
        raise HTTPException(403, "Creator or submitter cannot manually decide their own purchase order")
    items = await _locked_items(db, po)
    _audit(db, po, items, "approved", user_id, body)
    await db.flush()
    await db.refresh(po, attribute_names=["items"])
    return po


@router.get("/purchase-orders/{po_id}/pdf")
async def purchase_order_pdf(po_id: uuid.UUID, tenant_id: uuid.UUID = Depends(get_current_tenant_id),
                             db: AsyncSession = Depends(get_session),
                             user_id: uuid.UUID = Depends(get_current_user_id)):
    # Rendering is a pure local read: no row locks and no dependency on the mail service
    # (mail availability only matters when actually sending).
    po = await _load_po(db, tenant_id, po_id)
    items = (await db.execute(select(PurchaseOrderItem).where(PurchaseOrderItem.po_id == po.id)
                              .order_by(PurchaseOrderItem.id))).scalars().all()
    supplier = await get_supplier(po.supplier_id, tenant_id, db)
    pdf = render_purchase_order_pdf(po, items, supplier.name)
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="PO-{po.id}.pdf"'})


def _is_definite_send_failure(exc: Exception) -> bool:
    """True only when the mail service positively refused the request (nothing was sent)."""
    code = getattr(getattr(exc, "response", None), "status_code", None)
    return isinstance(code, int) and 400 <= code < 500 and code != 408


@router.post("/purchase-orders/{po_id}/send", dependencies=[Depends(require_tier("write"))])
async def send_purchase_order(po_id: uuid.UUID, tenant_id: uuid.UUID = Depends(get_current_tenant_id),
                              db: AsyncSession = Depends(get_session), user_id: uuid.UUID = Depends(get_current_user_id),
                              idempotency_key: Optional[str] = Header(None)):
    key = _header_value(idempotency_key)
    po = await _load_po(db, tenant_id, po_id, lock=True)
    if key and po.status == "sent" and po.send_idempotency_key == key and po.sent_message_id:
        return {"status": "sent", "message_id": po.sent_message_id, "replayed": True}
    require_state(po, ("approved",), "send")
    items = await _locked_items(db, po)
    if po.approval_hash != approval_hash(po, items):
        raise HTTPException(409, "Purchase order changed after approval; a new approval is required")
    if po.send_claimed_at:
        raise HTTPException(409, "A send is already pending; a manager must reconcile it before retrying")
    supplier = await get_supplier(po.supplier_id, tenant_id, db)
    if not supplier.email:
        raise HTTPException(422, "Supplier has no email address")
    pdf = render_purchase_order_pdf(po, items, supplier.name)
    mailboxes = await service_get("communication", "/api/v1/mail/mailboxes", tenant_id=tenant_id, user_id=user_id)
    active = [m for m in mailboxes if m.get("is_active", True)] if isinstance(mailboxes, list) else []
    if len(active) != 1:
        raise HTTPException(409, "Configure one active purchasing mailbox before sending")
    body = {"mailbox_id": active[0]["id"], "to": [supplier.email], "subject": f"Purchase order {po.po_number}",
            "body_text": f"Please find purchase order {po.po_number} attached.",
            "attachments": [{"filename": f"PO-{po.id}.pdf", "content_type": "application/pdf",
                             "content": base64.b64encode(pdf).decode("ascii")}]}
    # Persist the claim before I/O; a crash or uncertain delivery must never auto-send twice.
    po.send_claimed_at = datetime.now(timezone.utc)
    po.sent_to = supplier.email
    po.send_idempotency_key = key or str(uuid.uuid4())
    await db.commit()

    async def release_claim():
        locked = await _load_po(db, tenant_id, po_id, lock=True)
        locked.send_claimed_at = None
        locked.sent_to = None
        locked.send_idempotency_key = None
        await db.commit()

    try:
        delivery = await service_post("communication", "/api/v1/mail/send", json=body,
            tenant_id=tenant_id, user_id=user_id, timeout=30, retries=0)
    except Exception as exc:
        if _is_definite_send_failure(exc):
            await release_claim()
            raise HTTPException(502, "The mail service rejected the email; nothing was sent. You can retry")
        raise HTTPException(502, "Delivery could not be confirmed. Check the mailbox, then ask a manager to reconcile")
    if isinstance(delivery, dict) and str(delivery.get("status", "")).lower() in {"failed", "rejected", "error"}:
        await release_claim()
        raise HTTPException(502, "The mail service reported the email as failed; nothing was sent. You can retry")
    if not isinstance(delivery, dict) or delivery.get("status") != "sent" or not delivery.get("message_id"):
        raise HTTPException(502, "Email was not confirmed sent. Check the mailbox, then ask a manager to reconcile")
    po = await _load_po(db, tenant_id, po_id, lock=True)
    if po.status == "approved":
        po.status = "sent"
    po.sent_message_id = delivery["message_id"]
    po.sent_at = datetime.now(timezone.utc)
    po.send_claimed_at = None
    await db.flush()
    return {"status": "sent", "message_id": po.sent_message_id}


class SendReconcileInput(BaseModel):
    outcome: str = Field(pattern="^(sent|not_sent)$")
    message_id: Optional[str] = Field(None, max_length=255)
    note: Optional[str] = Field(None, max_length=2000)


@router.post("/purchase-orders/{po_id}/send/reconcile", dependencies=[Depends(require_tier("manager"))])
async def reconcile_purchase_order_send(po_id: uuid.UUID, body: SendReconcileInput,
                                        tenant_id: uuid.UUID = Depends(get_current_tenant_id),
                                        db: AsyncSession = Depends(get_session)):
    """Manager resolves an ambiguous/stuck send claim after checking the mailbox."""
    po = await _load_po(db, tenant_id, po_id, lock=True)
    if not po.send_claimed_at:
        raise HTTPException(409, "No pending send claim to reconcile")
    if body.outcome == "sent":
        if po.status == "approved":
            po.status = "sent"
        po.sent_message_id = (body.message_id or "").strip() or "manual-reconcile"
        po.sent_at = datetime.now(timezone.utc)
    else:
        po.sent_to = None
        po.send_idempotency_key = None
    po.send_claimed_at = None
    await db.flush()
    return {"status": po.status, "outcome": body.outcome, "message_id": po.sent_message_id}


@router.get("/purchasing/finance-outbox", dependencies=[Depends(require_tier("manager"))])
async def list_finance_outbox(tenant_id: uuid.UUID = Depends(get_current_tenant_id), db: AsyncSession = Depends(get_session)):
    rows = (await db.execute(select(InventoryFinanceOutbox).where(InventoryFinanceOutbox.tenant_id == tenant_id)
                            .order_by(InventoryFinanceOutbox.created_at.desc()).limit(200))).scalars().all()
    return [{"id": r.id, "source_id": r.source_id, "status": r.status, "attempts": r.attempts,
             "last_error": r.last_error, "next_attempt_at": r.next_attempt_at} for r in rows]


@router.post("/purchasing/finance-outbox/retry", dependencies=[Depends(require_tier("manager"))])
async def retry_finance_outbox(tenant_id: uuid.UUID = Depends(get_current_tenant_id),
                              user_id: uuid.UUID = Depends(get_current_user_id), limit: int = Query(100, ge=1, le=500)):
    return await finance_outbox.deliver(tenant_id, user_id, force=True, limit=limit)


@router.post("/purchase-orders/{po_id}/goods-receipts", response_model=GoodsReceiptRead,
             status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_tier("write"))])
async def create_goods_receipt(po_id: uuid.UUID, body: GoodsReceiptCreate,
                               tenant_id: uuid.UUID = Depends(get_current_tenant_id),
                               user_id: uuid.UUID = Depends(get_current_user_id), db: AsyncSession = Depends(get_session),
                               idempotency_key: Optional[str] = Header(None)):
    po = await _load_po(db, tenant_id, po_id, lock=True)
    # Dedicated idempotency key: Idempotency-Key header, falling back to the caller's receipt_ref.
    key = _header_value(idempotency_key) or body.receipt_ref
    # PO lock serializes key lookup with receipt creation, including first delivery.
    existing = (await db.execute(select(GoodsReceipt).where(GoodsReceipt.tenant_id == tenant_id,
                     GoodsReceipt.po_id == po.id,
                     or_(GoodsReceipt.idempotency_key == key, GoodsReceipt.receipt_ref == body.receipt_ref))
                     )).scalars().first()
    if existing:
        await db.refresh(existing, attribute_names=["items"])
        existing_lines = await _locked_items(db, po)
        if not matches_receipt(existing, body, {str(i.id): i for i in existing_lines}):
            raise HTTPException(409, "receipt_ref was already used for a different delivery payload")
        return existing
    require_state(po, ("approved", "sent", "partially_received"), "receive")
    items = await _locked_items(db, po)
    # Legacy approvals pre-date signed snapshots (approval_mode='legacy', no hash): receivable as-is.
    legacy = po.approval_mode == "legacy" and not po.approval_hash
    if not legacy and (not po.approval_hash or po.approval_hash != approval_hash(po, items)):
        raise HTTPException(409, "Purchase order has no matching approval snapshot")
    by_id = {str(i.id): i for i in items}
    validate_receipt(body.items, by_id)

    # Parent helper validates/locks product then warehouse level; deterministic product
    # order prevents deadlocks between receipts for different POs sharing products.
    from services.inventory.stock import locked_level
    levels = {}
    for product_id in sorted({by_id[str(i.po_item_id)].product_id for i in body.items}, key=str):
        levels[product_id] = await locked_level(db, tenant_id, product_id, po.warehouse_id)

    now = datetime.now(timezone.utc)
    gr = GoodsReceipt(tenant_id=tenant_id, po_id=po.id, warehouse_id=po.warehouse_id,
        gr_number=await next_sequence_number(db, tenant_id, "gr", "GR"), receipt_ref=body.receipt_ref,
        idempotency_key=key,
        status="accepted", received_by=user_id, received_at=now,
        supplier_delivery_note=body.supplier_delivery_note, supplier_invoice_number=body.supplier_invoice_number,
        notes=body.notes)
    db.add(gr)
    await db.flush()
    accepted_value = Decimal("0.00")
    rejected = accepted_total = 0
    for item in body.items:
        line = by_id[str(item.po_item_id)]
        accepted = item.quantity_received - item.quantity_rejected
        rejected += item.quantity_rejected
        accepted_total += accepted
        db.add(GoodsReceiptItem(gr_id=gr.id, product_id=line.product_id, quantity_ordered=line.quantity_ordered,
            quantity_received=item.quantity_received, quantity_accepted=accepted, quantity_rejected=item.quantity_rejected,
            unit_cost_zar=line.unit_cost_zar, serial_numbers=item.serial_numbers or [], rejection_reason=item.rejection_reason))
        if accepted:
            level = levels[line.product_id]
            await db.execute(update(InventoryLevel).where(InventoryLevel.id == level.id, InventoryLevel.tenant_id == tenant_id)
                             .values(soh=InventoryLevel.soh + accepted))
            db.add(StockMovement(tenant_id=tenant_id, product_id=line.product_id, movement_type="purchase_receipt",
                quantity=accepted, from_location_type="supplier", from_location_id=po.supplier_id,
                to_location_type="warehouse", to_location_id=po.warehouse_id, po_id=po.id, gr_id=gr.id,
                performed_by=user_id, performed_by_type="stock_controller", serial_numbers=item.serial_numbers or [],
                notes=f"Received against {po.po_number} / {gr.gr_number}"))
        # Rejected units remain outstanding for replacement; only accepted units fulfill the PO.
        line.quantity_received += accepted
        accepted_value += accepted * line.unit_cost_zar
    gr.status = "partially_accepted" if rejected and accepted_total else "rejected" if rejected else "accepted"
    gr.value_ex_vat_zar = money(accepted_value)
    gr.vat_zar = money(accepted_value * VAT_RATE)
    po.status = "received" if all(i.quantity_received >= i.quantity_ordered for i in items) else "partially_received"
    if po.status == "received":
        po.received_at = now
    finance_outbox.enqueue(db, gr, tenant_id, accepted_value)
    await db.flush()
    await db.refresh(gr, attribute_names=["items"])
    # All local state is durable before any cross-service request. Delivery failure must
    # never turn a committed receipt into an HTTP failure; durable rows can be retried.
    await db.commit()
    try:
        await finance_outbox.deliver(tenant_id, user_id)
    except Exception:
        logger.exception("Finance outbox delivery deferred for receipt %s", gr.id)
    return gr


@router.get("/purchase-orders", response_model=List[PurchaseOrderRead])
async def list_purchase_orders(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    stmt = select(PurchaseOrder).where(
        PurchaseOrder.tenant_id == tenant_id,
        PurchaseOrder.deleted_at.is_(None),
    )
    if status_filter:
        stmt = stmt.where(PurchaseOrder.status == status_filter)
    # selectinload batches all lines in one extra query (no per-PO refresh / N+1).
    stmt = (stmt.options(selectinload(PurchaseOrder.items))
            .order_by(PurchaseOrder.created_at.desc(), PurchaseOrder.id.desc()).limit(limit).offset(offset))
    return (await db.execute(stmt)).scalars().unique().all()


@router.get("/purchase-orders/{po_id}", response_model=PurchaseOrderRead)
async def get_purchase_order(
    po_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    po = await _load_po(db, tenant_id, po_id)
    await db.refresh(po, attribute_names=["items"])
    return po


async def _load_po(db: AsyncSession, tenant_id: uuid.UUID, po_id: uuid.UUID, *, lock=False) -> PurchaseOrder:
    stmt = select(PurchaseOrder).where(
            PurchaseOrder.id == po_id,
            PurchaseOrder.tenant_id == tenant_id,
            PurchaseOrder.deleted_at.is_(None),
        )
    if lock:
        stmt = stmt.with_for_update()
    result = await db.execute(stmt)
    po = result.scalar_one_or_none()
    if not po:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    return po
