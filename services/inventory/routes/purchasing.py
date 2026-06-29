"""Purchasing routes — Supplier, PurchaseOrder, GoodsReceipt.

Implements the procure-to-receive lifecycle:
    Supplier -> PurchaseOrder (draft -> submitted -> approved) -> GoodsReceipt

Three-way-match discipline lives in create_goods_receipt: a receipt can only
be recorded against an *approved* PO, and the quantity received against each
line can never exceed what remains outstanding on that PO line. On
completion, a GL entry (debit Inventory, credit Accounts Payable) is pushed
to the finance service the same way billing pushes revenue recognition on
invoice send — best-effort, logged on failure, never blocking the receipt.

Note: this module deliberately does not touch the Product or InventoryLevel
models. The live inventory_products/inventory_levels tables were created by
config/master_schema.sql under a different, incompatible schema than what
database.py now models (see services/inventory/migrations/env.py for the
full explanation) — stock-on-hand is not incremented here as a result. That
reconciliation is a separate, deliberate piece of follow-up work.

Also note: an approval gate above PO_AUTO_APPROVE_THRESHOLD_ZAR is enforced
(submit() requires a separate approve() call), but it does not push a record
into services.communication's Approval inbox — Approval.channel_id is a
mandatory FK to an existing chat channel, and there's no "Procurement"
channel to attach to without inventing one, which is its own decision.
"""

import logging
import os
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from services.common.auth import get_current_tenant_id, get_current_user_id
from services.common.http_client import service_post
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
)

logger = logging.getLogger("inventory.purchasing")

router = APIRouter(tags=["Purchasing"])

VAT_RATE = Decimal("0.15")
PO_AUTO_APPROVE_THRESHOLD_ZAR = Decimal(os.getenv("PO_AUTO_APPROVE_THRESHOLD_ZAR", "5000"))


async def _product_exists(db: AsyncSession, tenant_id: uuid.UUID, product_id: uuid.UUID) -> bool:
    """Check product existence via raw SQL on just (id, tenant_id).

    Avoids querying through the Product ORM class, whose columns don't match
    the live inventory_products table (see module docstring) — id/tenant_id
    are the only columns guaranteed present on both the legacy and current
    shape.
    """
    result = await db.execute(
        text("SELECT 1 FROM inventory_products WHERE id = :id AND tenant_id = :tenant_id"),
        {"id": str(product_id), "tenant_id": str(tenant_id)},
    )
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
    unit_cost_zar: Decimal = Field(ge=0)


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
    supplier_delivery_note: Optional[str] = None
    supplier_invoice_number: Optional[str] = None
    notes: Optional[str] = None
    items: List[GRItemInput] = Field(..., min_length=1)


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
    items: List[GRItemRead] = []

    class Config:
        from_attributes = True


# ── Suppliers ───────────────────────────────────────────────────────────

@router.post("/suppliers", response_model=SupplierRead, status_code=status.HTTP_201_CREATED)
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


@router.delete("/suppliers/{supplier_id}", status_code=status.HTTP_204_NO_CONTENT)
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

@router.post("/purchase-orders", response_model=PurchaseOrderRead, status_code=status.HTTP_201_CREATED)
async def create_purchase_order(
    body: PurchaseOrderCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_session),
):
    supplier_result = await db.execute(
        select(Supplier).where(Supplier.id == body.supplier_id, Supplier.tenant_id == tenant_id)
    )
    if not supplier_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Supplier not found")

    warehouse_result = await db.execute(
        select(Warehouse).where(Warehouse.id == body.warehouse_id, Warehouse.tenant_id == tenant_id)
    )
    if not warehouse_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Warehouse not found")

    for item in body.items:
        if not await _product_exists(db, tenant_id, item.product_id):
            raise HTTPException(status_code=404, detail=f"Product {item.product_id} not found")

    subtotal = sum((item.quantity_ordered * item.unit_cost_zar for item in body.items), Decimal("0.00"))
    tax = (subtotal * VAT_RATE).quantize(Decimal("0.01"))

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


@router.get("/purchase-orders", response_model=List[PurchaseOrderRead])
async def list_purchase_orders(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
    status_filter: Optional[str] = Query(None, alias="status"),
):
    stmt = select(PurchaseOrder).where(
        PurchaseOrder.tenant_id == tenant_id,
        PurchaseOrder.deleted_at.is_(None),
    )
    if status_filter:
        stmt = stmt.where(PurchaseOrder.status == status_filter)
    result = await db.execute(stmt.order_by(PurchaseOrder.created_at.desc()))
    pos = result.scalars().unique().all()
    for po in pos:
        await db.refresh(po, attribute_names=["items"])
    return pos


@router.get("/purchase-orders/{po_id}", response_model=PurchaseOrderRead)
async def get_purchase_order(
    po_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    po = await _load_po(db, tenant_id, po_id)
    await db.refresh(po, attribute_names=["items"])
    return po


async def _load_po(db: AsyncSession, tenant_id: uuid.UUID, po_id: uuid.UUID) -> PurchaseOrder:
    result = await db.execute(
        select(PurchaseOrder).where(
            PurchaseOrder.id == po_id,
            PurchaseOrder.tenant_id == tenant_id,
            PurchaseOrder.deleted_at.is_(None),
        )
    )
    po = result.scalar_one_or_none()
    if not po:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    return po


@router.post("/purchase-orders/{po_id}/submit", response_model=PurchaseOrderRead)
async def submit_purchase_order(
    po_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_session),
):
    """Submit a draft PO. Auto-approves under PO_AUTO_APPROVE_THRESHOLD_ZAR,
    otherwise moves to 'submitted' and waits for an explicit /approve call."""
    po = await _load_po(db, tenant_id, po_id)
    if po.status != "draft":
        raise HTTPException(status_code=400, detail=f"Cannot submit a PO in '{po.status}' status")

    if po.total_zar <= PO_AUTO_APPROVE_THRESHOLD_ZAR:
        po.status = "approved"
        po.approved_by = user_id
    else:
        po.status = "submitted"
    await db.flush()
    await db.refresh(po, attribute_names=["items"])
    return po


@router.post("/purchase-orders/{po_id}/approve", response_model=PurchaseOrderRead)
async def approve_purchase_order(
    po_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_session),
):
    po = await _load_po(db, tenant_id, po_id)
    if po.status != "submitted":
        raise HTTPException(status_code=400, detail=f"Cannot approve a PO in '{po.status}' status")
    po.status = "approved"
    po.approved_by = user_id
    await db.flush()
    await db.refresh(po, attribute_names=["items"])
    return po


# ── Goods Receipts (three-way match) ────────────────────────────────────

async def _post_goods_receipt_to_gl(
    gr: GoodsReceipt, tenant_id: uuid.UUID, user_id: uuid.UUID, accepted_value_zar: Decimal,
) -> None:
    """Push an AP/Inventory GL entry to finance the moment goods are received.

    Same push-on-event pattern as billing's invoice-send -> finance posting:
    best-effort, logged on failure, never blocks the receipt itself.
    """
    if accepted_value_zar <= 0:
        return
    try:
        await service_post(
            "finance", "/journal-entries",
            tenant_id=tenant_id, user_id=user_id,
            json={
                "entry_date": date.today().isoformat(),
                "description": f"Goods receipt {gr.gr_number} — stock received",
                "source": "INVENTORY",
                "source_id": str(gr.id),
                "lines": [
                    {
                        "account_code": "1200", "account_name": "Inventory",
                        "description": f"Stock received — GR {gr.gr_number}",
                        "debit": float(accepted_value_zar), "credit": 0,
                    },
                    {
                        "account_code": "2000", "account_name": "Accounts Payable",
                        "description": f"Payable to supplier — GR {gr.gr_number}",
                        "debit": 0, "credit": float(accepted_value_zar),
                    },
                ],
            },
        )
    except Exception as exc:
        logger.warning(
            "Failed to post GL entry for goods receipt %s to finance (%s) — "
            "requires manual reconciliation; inventory has no pull-based fallback for this path",
            gr.gr_number, exc,
        )


@router.post(
    "/purchase-orders/{po_id}/goods-receipts",
    response_model=GoodsReceiptRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_goods_receipt(
    po_id: uuid.UUID,
    body: GoodsReceiptCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_session),
):
    """Record goods received against an approved PO.

    Three-way match: a receipt can only be created against a PO that is
    'approved' or 'partially_received' (not draft/submitted/cancelled), and
    no line item can receive more than remains outstanding on that PO line.
    """
    po = await _load_po(db, tenant_id, po_id)
    if po.status not in ("approved", "partially_received"):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot receive goods against a PO in '{po.status}' status — it must be approved first",
        )

    po_items_result = await db.execute(
        select(PurchaseOrderItem).where(PurchaseOrderItem.po_id == po.id)
    )
    po_items_by_id = {str(i.id): i for i in po_items_result.scalars().all()}

    gr_number = await next_sequence_number(db, tenant_id, "gr", "GR")
    gr = GoodsReceipt(
        tenant_id=tenant_id,
        po_id=po.id,
        warehouse_id=po.warehouse_id,
        gr_number=gr_number,
        status="accepted",
        received_by=user_id,
        received_at=datetime.utcnow(),
        supplier_delivery_note=body.supplier_delivery_note,
        supplier_invoice_number=body.supplier_invoice_number,
        notes=body.notes,
    )
    db.add(gr)
    await db.flush()

    accepted_value = Decimal("0.00")
    for item in body.items:
        po_item = po_items_by_id.get(str(item.po_item_id))
        if not po_item:
            raise HTTPException(
                status_code=400,
                detail=f"PO item {item.po_item_id} does not belong to purchase order {po.po_number}",
            )
        remaining = po_item.quantity_ordered - po_item.quantity_received
        if item.quantity_received > remaining:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Cannot receive {item.quantity_received} units against PO line "
                    f"{po_item.id} — only {remaining} unit(s) remain outstanding "
                    f"(ordered {po_item.quantity_ordered}, already received {po_item.quantity_received})"
                ),
            )
        quantity_accepted = item.quantity_received - item.quantity_rejected
        if quantity_accepted < 0:
            raise HTTPException(status_code=400, detail="quantity_rejected cannot exceed quantity_received")

        db.add(GoodsReceiptItem(
            gr_id=gr.id,
            product_id=po_item.product_id,
            quantity_ordered=po_item.quantity_ordered,
            quantity_received=item.quantity_received,
            quantity_accepted=quantity_accepted,
            quantity_rejected=item.quantity_rejected,
            unit_cost_zar=po_item.unit_cost_zar,
            serial_numbers=item.serial_numbers or [],
            rejection_reason=item.rejection_reason,
        ))

        db.add(StockMovement(
            tenant_id=tenant_id,
            product_id=po_item.product_id,
            movement_type="purchase_receipt",
            quantity=quantity_accepted,
            from_location_type="supplier",
            from_location_id=po.supplier_id,
            to_location_type="warehouse",
            to_location_id=po.warehouse_id,
            po_id=po.id,
            gr_id=gr.id,
            performed_by=user_id,
            performed_by_type="stock_controller",
            serial_numbers=item.serial_numbers or [],
            notes=f"Received against {po.po_number} / {gr_number}",
        ))

        po_item.quantity_received += item.quantity_received
        accepted_value += quantity_accepted * po_item.unit_cost_zar

    await db.flush()

    refreshed_items = await db.execute(
        select(PurchaseOrderItem).where(PurchaseOrderItem.po_id == po.id)
    )
    all_items = refreshed_items.scalars().all()
    if all(i.quantity_received >= i.quantity_ordered for i in all_items):
        po.status = "received"
        po.received_at = datetime.utcnow()
    else:
        po.status = "partially_received"
    await db.flush()

    await _post_goods_receipt_to_gl(gr, tenant_id, user_id, accepted_value)

    await db.refresh(gr, attribute_names=["items"])
    return gr
