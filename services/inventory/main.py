from fastapi import FastAPI, Depends, HTTPException, status, BackgroundTasks
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime, date
import logging
from decimal import Decimal
from services.common.entitlements import EntitlementGuard
from services.common.auth import get_current_tenant_id
from services.inventory.database import get_session, init_tables, Product, Warehouse, InventoryLevel, StockMovement

app = FastAPI(title="CoreConnect Inventory Service", version="0.2.0")
guard = EntitlementGuard(module_id="inventory")


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok", "service": "inventory"}

# ── DB-based stock operations (replaces in-memory store) ───────────────

async def _ensure_sample_data(tenant_id: uuid.UUID, db):
    """Seed sample products, warehouses, and inventory levels if empty"""
    from sqlalchemy import select

    # Check if tenant already has products
    result = await db.execute(select(Product).where(Product.tenant_id == tenant_id).limit(1))
    if result.scalar_one_or_none():
        return  # Already seeded

    # Create sample products
    products = [
        Product(id=uuid.uuid4(), tenant_id=tenant_id, sku="ONT-V1", name="Vumatel ONT",
                cost_price=Decimal("450.00"), rrp=Decimal("799.00")),
        Product(id=uuid.uuid4(), tenant_id=tenant_id, sku="ONT-H1", name="Huawei ONT",
                cost_price=Decimal("520.00"), rrp=Decimal("899.00")),
        Product(id=uuid.uuid4(), tenant_id=tenant_id, sku="RTR-NET-05", name="Netgear Router",
                cost_price=Decimal("350.00"), rrp=Decimal("599.00")),
        Product(id=uuid.uuid4(), tenant_id=tenant_id, sku="RTR-TP-01", name="TP-Link Router",
                cost_price=Decimal("200.00"), rrp=Decimal("349.00")),
        Product(id=uuid.uuid4(), tenant_id=tenant_id, sku="SC-SC-SM", name="SC-SC Single Mode Patch",
                cost_price=Decimal("15.00"), rrp=Decimal("35.00")),
        Product(id=uuid.uuid4(), tenant_id=tenant_id, sku="SC-LC-MM", name="SC-LC Multi Mode Patch",
                cost_price=Decimal("20.00"), rrp=Decimal("45.00")),
        Product(id=uuid.uuid4(), tenant_id=tenant_id, sku="ONT-FTTH", name="FTTH ONT Generic",
                cost_price=Decimal("400.00"), rrp=Decimal("699.00")),
    ]
    for p in products:
        db.add(p)
    await db.flush()

    # Create sample warehouses
    wh_jhb = Warehouse(id=uuid.uuid4(), tenant_id=tenant_id, name="Main JHB", location="Johannesburg")
    wh_ct = Warehouse(id=uuid.uuid4(), tenant_id=tenant_id, name="Cape Town", location="Cape Town")
    wh_dbn = Warehouse(id=uuid.uuid4(), tenant_id=tenant_id, name="Durban", location="Durban")
    for wh in [wh_jhb, wh_ct, wh_dbn]:
        db.add(wh)
    await db.flush()

    # Create inventory levels
    levels = [
        (products[0].id, wh_jhb.id, 150, 10),
        (products[1].id, wh_jhb.id, 80, 5),
        (products[2].id, wh_jhb.id, 12, 2),
        (products[3].id, wh_ct.id, 45, 8),
        (products[4].id, wh_jhb.id, 500, 50),
        (products[5].id, wh_jhb.id, 200, 20),
        (products[6].id, wh_dbn.id, 30, 3),
    ]
    for pid, wid, soh, alloc in levels:
        db.add(InventoryLevel(
            tenant_id=tenant_id, warehouse_id=wid, product_id=pid,
            soh=soh, allocated=alloc,
        ))
    await db.flush()


@app.on_event("startup")
async def startup_entitlements() -> None:
    guard.ensure_startup()


@app.middleware("http")
async def entitlement_middleware(request, call_next):
    return await guard.middleware(request, call_next)

# --- Models ---
class ProductBase(BaseModel):
    sku: str
    name: str
    category_id: uuid.UUID
    cost_price: float
    rrp: float

class Product(ProductBase):
    id: uuid.UUID
    margin_percent: float
    created_at: datetime

class WarehouseCreate(BaseModel):
    name: str
    location: Optional[str]
    is_external: bool = False
    partner_name: Optional[str]

class ShipmentCreate(BaseModel):
    origin_warehouse_id: uuid.UUID
    destination_warehouse_id: uuid.UUID
    status: str = "ORDERED"
    tracking_number: Optional[str]
    eta: Optional[datetime]
    items: List[Dict[str, Any]] # List of {product_id, quantity}

class StockUpdate(BaseModel):
    product_id: uuid.UUID
    warehouse_id: uuid.UUID
    quantity: int
    movement_type: str # PURCHASE, TRANSFER, SALE, RETURN_FROM_CUSTOMER

class SalesPlan(BaseModel):
    product_id: uuid.UUID
    target_month: date
    forecast_units: int


class StockCheckoutItem(BaseModel):
    product_id: str
    quantity: int = Field(gt=0, le=100)


class StockCheckoutRequest(BaseModel):
    job_id: str = "unknown"
    items: List[StockCheckoutItem] = []

# --- Routes ---
@app.get("/")
async def root():
    return {"message": "CoreConnect Inventory Service is active"}

@app.post("/products", response_model=Product, status_code=status.HTTP_201_CREATED)
async def create_product(product: ProductBase, tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    margin = ((product.rrp - product.cost_price) / product.rrp * 100) if product.rrp > 0 else 0
    return {
        "id": uuid.uuid4(),
        "margin_percent": margin,
        "created_at": datetime.now(),
        **product.dict()
    }

@app.post("/stock/move", status_code=status.HTTP_202_ACCEPTED)
async def move_stock(
    move: StockUpdate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    """Handle stock movements including reverse logistics (returns) — DB-persisted"""
    from sqlalchemy import select

    await _ensure_sample_data(tenant_id, db)

    # Record the movement
    db.add(StockMovement(
        tenant_id=tenant_id,
        product_id=move.product_id,
        from_warehouse_id=move.warehouse_id if move.movement_type in ("TRANSFER", "SALE") else None,
        to_warehouse_id=move.warehouse_id if move.movement_type in ("PURCHASE", "RETURN_FROM_CUSTOMER") else None,
        quantity=move.quantity,
        movement_type=move.movement_type,
    ))

    # Update inventory level
    level_result = await db.execute(
        select(InventoryLevel).where(
            InventoryLevel.tenant_id == tenant_id,
            InventoryLevel.product_id == move.product_id,
            InventoryLevel.warehouse_id == move.warehouse_id,
        )
    )
    level = level_result.scalar_one_or_none()

    if level:
        if move.movement_type == "PURCHASE":
            level.soh += move.quantity
        elif move.movement_type == "SALE":
            level.allocated += move.quantity
        elif move.movement_type == "RETURN_FROM_CUSTOMER":
            level.soh += move.quantity
        elif move.movement_type == "TRANSFER":
            level.soh -= move.quantity
        elif move.movement_type == "WRITE_OFF":
            level.soh -= move.quantity

    await db.flush()
    logging.info(f"Stock Movement: {move.movement_type} for {move.product_id} x {move.quantity}")
    return {"status": "MOVING", "job_id": str(uuid.uuid4())}

@app.post("/warehouses", status_code=status.HTTP_201_CREATED)
async def create_warehouse(wh: WarehouseCreate, tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    logging.info(f"Creating Warehouse: {wh.name} (External: {wh.is_external})")
    return {"id": uuid.uuid4(), **wh.dict()}

@app.post("/shipments", status_code=status.HTTP_201_CREATED)
async def create_global_shipment(shipment: ShipmentCreate, tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    """Track stock from origin (e.g. China) to destination via global supply chain"""
    logging.info(f"New Global Shipment created. ETA: {shipment.eta}")
    return {"id": uuid.uuid4(), "status": shipment.status, "eta": shipment.eta}

@app.get("/reports/sell-thru")
async def get_sell_thru(category_id: Optional[uuid.UUID] = None):
    """Calculate sell-thru % against every SKU"""
    # Mock data
    return [
        {
            "sku": "ONT-V1",
            "name": "Vumatel ONT",
            "category": "Network",
            "soh": 150,
            "sold": 45,
            "sell_thru_percent": 30.0
        }
    ]

@app.post("/planning", status_code=status.HTTP_201_CREATED)
async def create_sales_plan(plan: SalesPlan, tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    return {"status": "PLANNED", "plan_id": uuid.uuid4()}

# --- Auto-Replenishment Logic ---
async def check_low_stock_thresholds():
    """Background task to scan for stock falling below min_threshold"""
    logging.info("Scanning for low stock items...")
    # Mock finding a low stock item
    low_stock_items = [
        {"sku": "RTR-NET-05", "soh": 12, "min_threshold": 20, "warehouse": "Main JHB"}
    ]
    
    for item in low_stock_items:
        if item["soh"] < item["min_threshold"]:
            logging.warning(f"THRESHOLD ALERT: {item['sku']} at {item['soh']} units. Triggering Auto-Replenishment...")
            # Here we would create a Draft Purchase Order in the DB
            # and notify the procurement team via email/Slack

@app.on_event("startup")
async def startup_event():
    # In a real app, use a task scheduler like Celery or APScheduler
    # For demo, we just log the startup
    logging.info("Inventory Service Started. Auto-Replenishment engine active.")

@app.post("/stock/monitor", status_code=status.HTTP_200_OK)
async def trigger_manual_scan(background_tasks: BackgroundTasks):
    """Manually trigger a threshold check"""
    background_tasks.add_task(check_low_stock_thresholds)
    return {"message": "Replenishment scan initiated"}


# ── Stock Query (DB-persisted) ─────────────────────────────────────────

@app.get("/stock")
async def query_stock(
    sku: Optional[str] = None,
    warehouse: Optional[str] = None,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    """Query stock levels by SKU or warehouse"""
    from sqlalchemy import select, join

    await _ensure_sample_data(tenant_id, db)

    stmt = (
        select(Product, InventoryLevel, Warehouse)
        .join(InventoryLevel, InventoryLevel.product_id == Product.id)
        .join(Warehouse, Warehouse.id == InventoryLevel.warehouse_id)
        .where(InventoryLevel.tenant_id == tenant_id)
    )

    if sku:
        stmt = stmt.where(Product.sku.ilike(f"%{sku}%"))
    if warehouse:
        stmt = stmt.where(Warehouse.name.ilike(f"%{warehouse}%"))

    result = await db.execute(stmt)
    rows = result.all()

    items = []
    for product, level, wh in rows:
        items.append({
            "id": str(product.id),
            "sku": product.sku,
            "name": product.name,
            "soh": level.soh,
            "allocated": level.allocated,
            "available": level.soh - level.allocated,
            "warehouse_name": wh.name,
        })

    return items


@app.post("/stock/checkout")
async def checkout_stock(
    payload: StockCheckoutRequest,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    """Checkout stock for a job (mobile technician app) — DB-persisted"""
    from sqlalchemy import select

    await _ensure_sample_data(tenant_id, db)

    job_id = payload.job_id
    results = []

    for item in payload.items:
        # Find product by ID or SKU
        product_result = await db.execute(
            select(Product).where(
                Product.tenant_id == tenant_id,
                (Product.id == uuid.UUID(item.product_id)) | (Product.sku == item.product_id),
            )
        )
        product = product_result.scalar_one_or_none()

        if not product:
            results.append({"product_id": item.product_id, "status": "NOT_FOUND"})
            continue

        # Find inventory level for this product
        level_result = await db.execute(
            select(InventoryLevel).where(
                InventoryLevel.tenant_id == tenant_id,
                InventoryLevel.product_id == product.id,
            )
        )
        level = level_result.scalar_one_or_none()

        if not level:
            results.append({"product_id": item.product_id, "status": "NO_STOCK_RECORD"})
            continue

        available = level.soh - level.allocated
        if available < item.quantity:
            results.append({
                "product_id": item.product_id, "status": "INSUFFICIENT",
                "requested": item.quantity, "available": available,
            })
            continue

        # Update allocated
        level.allocated += item.quantity

        # Record stock movement
        db.add(StockMovement(
            tenant_id=tenant_id,
            product_id=product.id,
            quantity=item.quantity,
            movement_type="SALE",
            reference_id=uuid.UUID(job_id) if job_id != "unknown" else None,
        ))

        results.append({
            "product_id": item.product_id, "status": "CHECKED_OUT",
            "quantity": item.quantity, "remaining": level.soh - level.allocated,
        })

    await db.flush()
    return {"job_id": job_id, "items": results, "status": "complete"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8010)
