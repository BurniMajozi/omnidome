"""Tenant-scoped inventory reports. Valuation uses current catalogue cost, not FIFO."""
import csv
import io
import uuid
from datetime import date
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.common.auth import get_current_tenant_id
from services.inventory.access import require_tier
from services.inventory.database import get_session, Product, InventoryLevel, Warehouse, PurchaseOrder, GoodsReceipt, Supplier

router = APIRouter(tags=["Inventory reports"])
Report = Literal["valuation", "reorder", "spend", "margin"]

def csv_cell(value):
    if isinstance(value, (int, float, Decimal)):
        return value
    text = "" if value is None else str(value)
    # Spreadsheet applications also interpret formulas after leading whitespace.
    return "'" + text if text.lstrip().startswith(("=", "+", "-", "@")) else text

def json_value(value):
    if isinstance(value, Decimal):
        return format(value.quantize(Decimal("0.01")), "f")
    if isinstance(value, (uuid.UUID, date)):
        return str(value)
    return value

def report_query(kind, tenant, warehouse_id=None, start=None, end=None):
    cost = func.coalesce(Product.cost_price, 0)
    price = func.coalesce(Product.rrp, 0)
    if kind == "margin":
        query = select(Product.id.label("product_id"), Product.sku, Product.name,
            cost.label("cost_zar"), price.label("price_zar"), (price - cost).label("unit_margin_zar"),
            case((price > 0, (price - cost) * 100 / price), else_=None).label("margin_percent")
        ).where(Product.tenant_id == tenant, Product.is_active.is_(True))
        return query.order_by(Product.sku), "Prospective unit margin at current catalogue prices; zero-price margin is undefined."
    if kind == "spend":
        # One row per PO: pre-aggregate receipts so joining cannot multiply order totals.
        receipts = select(GoodsReceipt.po_id,
            func.sum(GoodsReceipt.value_ex_vat_zar).label("received_net"),
            func.sum(GoodsReceipt.vat_zar).label("received_vat"),
        ).where(GoodsReceipt.tenant_id == tenant, GoodsReceipt.status.in_(["accepted", "partially_accepted"])).group_by(GoodsReceipt.po_id).subquery()
        query = select(PurchaseOrder.id.label("po_id"), PurchaseOrder.po_number, PurchaseOrder.supplier_id,
            Supplier.name.label("supplier"), PurchaseOrder.warehouse_id, Warehouse.name.label("warehouse"), PurchaseOrder.order_date, PurchaseOrder.status,
            PurchaseOrder.total_zar.label("committed_gross_zar"),
            func.coalesce(receipts.c.received_net, 0).label("received_net_zar"),
            func.coalesce(receipts.c.received_vat, 0).label("received_vat_zar"),
        ).outerjoin(receipts, receipts.c.po_id == PurchaseOrder.id).outerjoin(Supplier,
            (Supplier.id == PurchaseOrder.supplier_id) & (Supplier.tenant_id == tenant)).outerjoin(Warehouse,
            (Warehouse.id == PurchaseOrder.warehouse_id) & (Warehouse.tenant_id == tenant)).where(
            PurchaseOrder.tenant_id == tenant, PurchaseOrder.deleted_at.is_(None),
            PurchaseOrder.currency == "ZAR", PurchaseOrder.status.in_(["approved", "sent", "partially_received", "received"]),
        )
        if warehouse_id: query = query.where(PurchaseOrder.warehouse_id == warehouse_id)
        if start: query = query.where(PurchaseOrder.order_date >= start)
        if end: query = query.where(PurchaseOrder.order_date <= end)
        return query.order_by(PurchaseOrder.order_date.desc(), PurchaseOrder.id), "ZAR order cohort by order date: committed gross includes VAT; accepted receipts show net and VAT separately. Not cash paid."
    query = select(Product.id.label("product_id"), Product.sku, Product.name,
        Warehouse.id.label("warehouse_id"), Warehouse.name.label("warehouse"),
        InventoryLevel.soh, InventoryLevel.allocated, InventoryLevel.reserved, InventoryLevel.available,
        InventoryLevel.sit, cost.label("unit_cost_zar"),
    ).join(InventoryLevel, InventoryLevel.product_id == Product.id).join(Warehouse, Warehouse.id == InventoryLevel.warehouse_id).where(
        Product.tenant_id == tenant, InventoryLevel.tenant_id == tenant, Warehouse.tenant_id == tenant,
        Warehouse.deleted_at.is_(None),
    )
    if warehouse_id: query = query.where(Warehouse.id == warehouse_id)
    if kind == "valuation":
        query = query.add_columns((InventoryLevel.soh * cost).label("value_zar"))
        basis = "Physical warehouse stock on hand at current catalogue cost, excluding transit and technician stock. Not a FIFO or historical-cost valuation."
    else:
        target = func.coalesce(InventoryLevel.max_threshold, InventoryLevel.reorder_point + InventoryLevel.reorder_quantity)
        net = InventoryLevel.available + InventoryLevel.sit
        suggested = case((target > net, target - net), else_=0)
        query = query.add_columns(InventoryLevel.reorder_point, suggested.label("suggested_quantity"),
            (suggested * cost).label("estimated_net_zar"), Product.preferred_supplier_id)
        query = query.where(InventoryLevel.available < InventoryLevel.reorder_point)
        basis = "Recommendations up to maximum threshold after available and in-transit stock. No purchase order is created automatically."
    return query.order_by(Warehouse.name, Product.sku), basis

async def build_report(db, kind, tenant, warehouse, start, end, page, size, export):
    if start and end and start > end: raise HTTPException(422, "Start date must precede end date")
    query, basis = report_query(kind, tenant, warehouse, start, end)
    source = query.order_by(None).subquery()
    total = (await db.execute(select(func.count()).select_from(source))).scalar_one()
    totals = {}
    for name in ("value_zar", "estimated_net_zar", "committed_gross_zar", "received_net_zar", "received_vat_zar"):
        if name in source.c:
            totals[name] = json_value((await db.execute(select(func.coalesce(func.sum(source.c[name]), 0)))).scalar_one())
    if export and total > 100000:
        raise HTTPException(413, "Export exceeds 100000 rows. Filter by warehouse or date range.")
    result = await db.execute(query if export else query.offset((page - 1) * size).limit(size))
    rows = [dict(row) for row in result.mappings()]
    if export:
        buffer = io.StringIO(newline="")
        writer = csv.writer(buffer)
        columns = list(source.c.keys())
        writer.writerow(columns)
        writer.writerows([[csv_cell(row.get(key)) for key in columns] for row in rows])
        return Response("\ufeff" + buffer.getvalue(), media_type="text/csv", headers={
            "Content-Disposition": f'attachment; filename="inventory-{kind}.csv"', "Cache-Control": "no-store",
        })
    return {"report": kind, "basis": basis, "items": [{k: json_value(v) for k, v in row.items()} for row in rows],
        "total": total, "page": page, "page_size": size, "totals": totals}

@router.get("/reports/{kind}")
async def inventory_report(kind: Report, tenant: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session), warehouse_id: uuid.UUID | None = None,
    start: date | None = None, end: date | None = None, page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200), format: Literal["json", "csv"] = "json"):
    return await build_report(db, kind, tenant, warehouse_id, start, end, page, page_size, format == "csv")

@router.get("/approvals/inbox", dependencies=[Depends(require_tier("manager"))])
async def approval_inbox(tenant: uuid.UUID = Depends(get_current_tenant_id), db: AsyncSession = Depends(get_session)):
    rows = (await db.execute(select(PurchaseOrder.id, PurchaseOrder.po_number, PurchaseOrder.total_zar,
        PurchaseOrder.submitted_at, PurchaseOrder.submitted_by, PurchaseOrder.supplier_id, PurchaseOrder.warehouse_id,
    ).where(PurchaseOrder.tenant_id == tenant, PurchaseOrder.deleted_at.is_(None),
        PurchaseOrder.status.in_(["pending_approval", "submitted"])).order_by(PurchaseOrder.submitted_at, PurchaseOrder.id))).mappings()
    return {"items": [{k: json_value(v) for k, v in dict(row).items()} for row in rows]}
