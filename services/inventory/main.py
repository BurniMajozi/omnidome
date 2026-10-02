from fastapi import FastAPI, Depends, HTTPException, Header, status
from pydantic import BaseModel, Field, validator
from typing import List, Optional, Dict, Any, Literal
import uuid
from datetime import datetime, date
import logging
from decimal import Decimal

from services.common.entitlements import EntitlementGuard
from services.common.middleware import configure_production
from services.common.auth import get_current_tenant_id, get_current_user_id
from services.inventory.access import require_tier
from services.inventory.stock import apply_move, checkout
from services.common.background_tasks import schedule_background
from services.inventory.database import get_session, init_tables, Product, ProductCategory, Warehouse, InventoryLevel, StockMovement
from services.inventory.routes.purchasing import router as purchasing_router

app = FastAPI(title="CoreConnect Inventory Service", version="0.2.0")
guard = EntitlementGuard(module_id="inventory")

configure_production(app)
app.include_router(purchasing_router)

@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok", "service": "inventory"}

# ── DB-based stock operations (replaces in-memory store) ───────────────

@app.on_event("startup")
async def startup_entitlements() -> None:
    guard.ensure_startup()
    await init_tables()


@app.middleware("http")
async def entitlement_middleware(request, call_next):
    return await guard.middleware(request, call_next)

# --- Helpers ---

def _calc_margin(cost_price: Decimal, rrp: Decimal) -> float:
    """Calculate margin percentage from cost and RRP."""
    if rrp and rrp > 0:
        return round(float((rrp - cost_price) / rrp * 100), 2)
    return 0.0

async def _check_category(db, tenant_id, category_id):
    if category_id is not None:
        from sqlalchemy import select
        row = (await db.execute(select(ProductCategory.id).where(ProductCategory.id == category_id,
            ProductCategory.tenant_id == tenant_id))).scalar_one_or_none()
        if row is None:
            raise HTTPException(404, "Category not found")


# --- Pydantic Models ---

class ProductBase(BaseModel):
    sku: str
    name: str
    category_id: Optional[uuid.UUID] = None
    description: Optional[str] = None
    barcode: Optional[str] = None
    unit_of_measure: str = "EA"
    weight_kg: Optional[Decimal] = None
    cost_price: Decimal = Decimal("0.00")
    rrp: Decimal = Decimal("0.00")


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    sku: Optional[str] = None
    name: Optional[str] = None
    category_id: Optional[uuid.UUID] = None
    description: Optional[str] = None
    barcode: Optional[str] = None
    unit_of_measure: Optional[str] = None
    weight_kg: Optional[Decimal] = None
    cost_price: Optional[Decimal] = None
    rrp: Optional[Decimal] = None


class ProductResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    sku: str
    name: str
    category_id: Optional[uuid.UUID]
    description: Optional[str]
    barcode: Optional[str]
    unit_of_measure: str
    weight_kg: Optional[Decimal]
    cost_price: Decimal
    rrp: Decimal
    margin_percent: float
    created_at: datetime

    class Config:
        from_attributes = True


class WarehouseCreate(BaseModel):
    name: str
    location: Optional[str] = None
    is_external: bool = False
    partner_name: Optional[str] = None

    @validator("partner_name")
    def require_partner_name(cls, v, values):
        if values.get("is_external") and not v:
            raise ValueError("partner_name is required when is_external=True")
        return v

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
    quantity: int = Field(gt=0)
    movement_type: Literal["PURCHASE", "TRANSFER", "SALE", "RETURN_FROM_CUSTOMER", "WRITE_OFF"]
    destination_warehouse_id: Optional[uuid.UUID] = None
    client_ref: Optional[str] = Field(None, min_length=1, max_length=96)

class SalesPlan(BaseModel):
    product_id: uuid.UUID
    target_month: date
    forecast_units: int


class StockCheckoutItem(BaseModel):
    product_id: str
    quantity: int = Field(gt=0, le=100)
    warehouse_id: Optional[uuid.UUID] = None


class StockCheckoutRequest(BaseModel):
    job_id: str = Field("unknown", max_length=100)
    items: List[StockCheckoutItem] = Field(min_length=1, max_length=100)
    warehouse_id: Optional[uuid.UUID] = None
    client_ref: Optional[str] = Field(None, min_length=1, max_length=96)

# --- Routes ---
@app.get("/")
async def root():
    return {"message": "CoreConnect Inventory Service is active"}

@app.post("/products", response_model=ProductResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_tier("write"))])
async def create_product(
    product: ProductCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    """Create a new product."""
    await _check_category(db, tenant_id, product.category_id)
    p = Product(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        sku=product.sku,
        name=product.name,
        category_id=product.category_id,
        description=product.description,
        barcode=product.barcode,
        unit_of_measure=product.unit_of_measure,
        weight_kg=product.weight_kg,
        cost_price=product.cost_price,
        rrp=product.rrp,
    )
    db.add(p)
    await db.flush()
    await db.refresh(p)
    return ProductResponse(
        id=p.id,
        tenant_id=p.tenant_id,
        sku=p.sku,
        name=p.name,
        category_id=p.category_id,
        description=p.description,
        barcode=p.barcode,
        unit_of_measure=p.unit_of_measure,
        weight_kg=p.weight_kg,
        cost_price=p.cost_price,
        rrp=p.rrp,
        margin_percent=_calc_margin(p.cost_price, p.rrp),
        created_at=p.created_at,
    )


@app.get("/products", response_model=List[ProductResponse])
async def list_products(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    """List all products for tenant."""
    from sqlalchemy import select

    result = await db.execute(
        select(Product).where(Product.tenant_id == tenant_id)
    )
    products = result.scalars().all()
    return [
        ProductResponse(
            id=p.id,
            tenant_id=p.tenant_id,
            sku=p.sku,
            name=p.name,
            category_id=p.category_id,
            description=p.description,
            barcode=p.barcode,
            unit_of_measure=p.unit_of_measure,
            weight_kg=p.weight_kg,
            cost_price=p.cost_price,
            rrp=p.rrp,
            margin_percent=_calc_margin(p.cost_price, p.rrp),
            created_at=p.created_at,
        )
        for p in products
    ]


@app.get("/products/{product_id}", response_model=ProductResponse)
async def get_product(
    product_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    """Get a single product by ID."""
    from sqlalchemy import select

    result = await db.execute(
        select(Product).where(
            Product.id == product_id,
            Product.tenant_id == tenant_id,
        )
    )
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Product not found")
    return ProductResponse(
        id=p.id,
        tenant_id=p.tenant_id,
        sku=p.sku,
        name=p.name,
        category_id=p.category_id,
        description=p.description,
        barcode=p.barcode,
        unit_of_measure=p.unit_of_measure,
        weight_kg=p.weight_kg,
        cost_price=p.cost_price,
        rrp=p.rrp,
        margin_percent=_calc_margin(p.cost_price, p.rrp),
        created_at=p.created_at,
    )


@app.put("/products/{product_id}", response_model=ProductResponse, dependencies=[Depends(require_tier("write"))])
async def update_product(
    product_id: uuid.UUID,
    body: ProductUpdate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    """Update a product."""
    from sqlalchemy import select

    result = await db.execute(
        select(Product).where(
            Product.id == product_id,
            Product.tenant_id == tenant_id,
        )
    )
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Product not found")

    update_data = body.dict(exclude_unset=True)
    if "category_id" in update_data:
        await _check_category(db, tenant_id, update_data["category_id"])
    for field, value in update_data.items():
        setattr(p, field, value)

    await db.flush()
    await db.refresh(p)
    return ProductResponse(
        id=p.id,
        tenant_id=p.tenant_id,
        sku=p.sku,
        name=p.name,
        category_id=p.category_id,
        description=p.description,
        barcode=p.barcode,
        unit_of_measure=p.unit_of_measure,
        weight_kg=p.weight_kg,
        cost_price=p.cost_price,
        rrp=p.rrp,
        margin_percent=_calc_margin(p.cost_price, p.rrp),
        created_at=p.created_at,
    )


@app.delete("/products/{product_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_tier("manager"))])
async def delete_product(
    product_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    """Delete a product"""
    from sqlalchemy import select

    result = await db.execute(
        select(Product).where(
            Product.id == product_id,
            Product.tenant_id == tenant_id,
        )
    )
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Product not found")

    await db.delete(p)
    await db.flush()


@app.post("/stock/move", dependencies=[Depends(require_tier("write"))])
async def move_stock(
    move: StockUpdate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    user_id: uuid.UUID = Depends(get_current_user_id),
    idempotency_key: Optional[str] = Header(None),
    db=Depends(get_session),
):
    return await apply_move(db, tenant_id, user_id, move, idempotency_key or move.client_ref)

@app.post("/warehouses", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_tier("manager"))])
async def create_warehouse(wh: WarehouseCreate, tenant_id: uuid.UUID = Depends(get_current_tenant_id), db=Depends(get_session)):
    warehouse = Warehouse(tenant_id=tenant_id, code=f"WH-{uuid.uuid4().hex[:12]}", **wh.model_dump())
    db.add(warehouse)
    await db.flush()
    await db.refresh(warehouse)
    return {"id": str(warehouse.id), **wh.model_dump()}


@app.get("/warehouses")
async def list_warehouses(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    """List all warehouses for tenant"""
    from sqlalchemy import select

    result = await db.execute(
        select(Warehouse).where(Warehouse.tenant_id == tenant_id)
    )
    warehouses = result.scalars().all()
    return [
        {
            "id": str(w.id),
            "tenant_id": str(w.tenant_id),
            "name": w.name,
            "location": w.location,
            "is_external": w.is_external,
            "created_at": w.created_at.isoformat() if w.created_at else None,
        }
        for w in warehouses
    ]


@app.get("/warehouses/{warehouse_id}")
async def get_warehouse(
    warehouse_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    """Get a single warehouse by ID"""
    from sqlalchemy import select

    result = await db.execute(
        select(Warehouse).where(
            Warehouse.id == warehouse_id,
            Warehouse.tenant_id == tenant_id,
        )
    )
    w = result.scalar_one_or_none()
    if not w:
        raise HTTPException(status_code=404, detail="Warehouse not found")
    return {
        "id": str(w.id),
        "tenant_id": str(w.tenant_id),
        "name": w.name,
        "location": w.location,
        "is_external": w.is_external,
        "created_at": w.created_at.isoformat() if w.created_at else None,
    }


@app.put("/warehouses/{warehouse_id}", dependencies=[Depends(require_tier("manager"))])
async def update_warehouse(
    warehouse_id: uuid.UUID,
    body: WarehouseCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    """Update a warehouse"""
    from sqlalchemy import select

    result = await db.execute(
        select(Warehouse).where(
            Warehouse.id == warehouse_id,
            Warehouse.tenant_id == tenant_id,
        )
    )
    w = result.scalar_one_or_none()
    if not w:
        raise HTTPException(status_code=404, detail="Warehouse not found")

    update_data = body.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(w, field, value)

    await db.flush()
    await db.refresh(w)
    return {
        "id": str(w.id),
        "tenant_id": str(w.tenant_id),
        "name": w.name,
        "location": w.location,
        "is_external": w.is_external,
        "created_at": w.created_at.isoformat() if w.created_at else None,
    }


@app.delete("/warehouses/{warehouse_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_tier("manager"))])
async def delete_warehouse(
    warehouse_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    """Delete a warehouse"""
    from sqlalchemy import select

    result = await db.execute(
        select(Warehouse).where(
            Warehouse.id == warehouse_id,
            Warehouse.tenant_id == tenant_id,
        )
    )
    w = result.scalar_one_or_none()
    if not w:
        raise HTTPException(status_code=404, detail="Warehouse not found")

    await db.delete(w)
    await db.flush()


@app.post("/shipments", dependencies=[Depends(require_tier("write"))])
async def create_global_shipment(shipment: ShipmentCreate, tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    """Track stock from origin (e.g. China) to destination via global supply chain"""
    raise HTTPException(501, "Shipment tracking is not connected")

@app.get("/reports/sell-thru")
async def get_sell_thru(category_id: Optional[uuid.UUID] = None, tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    """Calculate sell-thru % against every SKU"""
    raise HTTPException(501, "Sell-through reporting is not connected")

@app.post("/planning", dependencies=[Depends(require_tier("write"))])
async def create_sales_plan(plan: SalesPlan, tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    raise HTTPException(501, "Sales planning is not connected")

@app.post("/stock/monitor", dependencies=[Depends(require_tier("write"))])
async def trigger_manual_scan(tenant_id: uuid.UUID = Depends(get_current_tenant_id), db=Depends(get_session)):
    from sqlalchemy import select
    result = await db.execute(select(InventoryLevel).where(InventoryLevel.tenant_id == tenant_id,
        InventoryLevel.available < InventoryLevel.reorder_point))
    return {"status": "completed", "low_stock": [{"product_id": str(row.product_id),
        "warehouse_id": str(row.warehouse_id), "available": row.available,
        "reorder_point": row.reorder_point} for row in result.scalars().all()], "purchase_orders_created": 0}


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

    stmt = (
        select(Product, InventoryLevel, Warehouse)
        .join(InventoryLevel, InventoryLevel.product_id == Product.id)
        .join(Warehouse, Warehouse.id == InventoryLevel.warehouse_id)
        .where(InventoryLevel.tenant_id == tenant_id, Product.tenant_id == tenant_id, Warehouse.tenant_id == tenant_id)
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
            "reserved": level.reserved,
            "available": level.soh - level.allocated - level.reserved,
            "warehouse_id": str(wh.id),
            "warehouse_name": wh.name,
        })

    return items


@app.post("/stock/checkout", dependencies=[Depends(require_tier("write"))])
async def checkout_stock(
    payload: StockCheckoutRequest,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    user_id: uuid.UUID = Depends(get_current_user_id),
    idempotency_key: Optional[str] = Header(None),
    db=Depends(get_session),
):
    return await checkout(db, tenant_id, user_id, payload, idempotency_key or payload.client_ref)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8010)
