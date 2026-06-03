from fastapi import FastAPI, Depends, HTTPException, status, BackgroundTasks
from pydantic import BaseModel
from typing import List, Optional, Dict
import uuid
from datetime import datetime, date
import logging
from services.common.entitlements import EntitlementGuard
from services.common.auth import get_current_tenant_id

app = FastAPI(title="CoreConnect Inventory Service", version="0.1.0")
guard = EntitlementGuard(module_id="inventory")

# ── In-memory stock store (replace with DB in production) ─────────────
# Structure: {tenant_id: {product_id: {"sku": str, "name": str, "soh": int, "allocated": int, "warehouse": str}}}
_stock_store: Dict[str, Dict[str, dict]] = {}


def _get_tenant_stock(tenant_id: str) -> Dict[str, dict]:
    if tenant_id not in _stock_store:
        _stock_store[tenant_id] = {}
    return _stock_store[tenant_id]


def _ensure_sample_stock(tenant_id: str):
    """Seed sample stock data for demo purposes"""
    stock = _get_tenant_stock(tenant_id)
    if not stock:
        sample_items = {
            "prod-ont-001": {"sku": "ONT-V1", "name": "Vumatel ONT", "soh": 150, "allocated": 10, "warehouse": "Main JHB"},
            "prod-ont-002": {"sku": "ONT-H1", "name": "Huawei ONT", "soh": 80, "allocated": 5, "warehouse": "Main JHB"},
            "prod-rtr-001": {"sku": "RTR-NET-05", "name": "Netgear Router", "soh": 12, "allocated": 2, "warehouse": "Main JHB"},
            "prod-rtr-002": {"sku": "RTR-TP-01", "name": "TP-Link Router", "soh": 45, "allocated": 8, "warehouse": "Cape Town"},
            "prod-sc-001": {"sku": "SC-SC-SM", "name": "SC-SC Single Mode Patch", "soh": 500, "allocated": 50, "warehouse": "Main JHB"},
            "prod-sc-002": {"sku": "SC-LC-MM", "name": "SC-LC Multi Mode Patch", "soh": 200, "allocated": 20, "warehouse": "Main JHB"},
            "prod-ont-003": {"sku": "ONT-FTTH", "name": "FTTH ONT Generic", "soh": 30, "allocated": 3, "warehouse": "Durban"},
        }
        stock.update(sample_items)


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
async def move_stock(move: StockUpdate, tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    """Handle stock movements including reverse logistics (returns)"""
    logging.info(f"Stock Movement: {move.movement_type} for {move.product_id} x {move.quantity}")
    return {"status": "MOVING", "job_id": uuid.uuid4()}

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


# ── Stock Query (for mobile technician app) ───────────────────────────

@app.get("/stock")
async def query_stock(
    sku: Optional[str] = None,
    warehouse: Optional[str] = None,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Query stock levels by SKU or warehouse"""
    _ensure_sample_stock(str(tenant_id))
    stock = _get_tenant_stock(str(tenant_id))

    items = []
    for pid, item in stock.items():
        if sku and sku.upper() not in item["sku"].upper():
            continue
        if warehouse and warehouse.lower() not in item["warehouse"].lower():
            continue
        items.append({
            "id": pid,
            "sku": item["sku"],
            "name": item["name"],
            "soh": item["soh"],
            "allocated": item["allocated"],
            "available": item["soh"] - item["allocated"],
            "warehouse_name": item["warehouse"],
        })

    return items


@app.post("/stock/checkout")
async def checkout_stock(
    payload: dict,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Checkout stock for a job (mobile technician app)"""
    job_id = payload.get("job_id", "unknown")
    items = payload.get("items", [])

    _ensure_sample_stock(str(tenant_id))
    stock = _get_tenant_stock(str(tenant_id))

    results = []
    for item in items:
        product_id = item.get("product_id", "")
        quantity = item.get("quantity", 0)

        # Find by product_id or SKU
        found = None
        for pid, s in stock.items():
            if pid == product_id or s["sku"] == product_id:
                found = (pid, s)
                break

        if not found:
            results.append({"product_id": product_id, "status": "NOT_FOUND"})
            continue

        pid, s = found
        available = s["soh"] - s["allocated"]
        if available < quantity:
            results.append({
                "product_id": product_id, "status": "INSUFFICIENT",
                "requested": quantity, "available": available,
            })
            continue

        s["allocated"] += quantity
        results.append({
            "product_id": product_id, "status": "CHECKED_OUT",
            "quantity": quantity, "remaining": s["soh"] - s["allocated"],
        })

    # Create stock movement records for checked-out items
    for r in results:
        if r["status"] == "CHECKED_OUT":
            logging.info(f"Stock Movement: SALE for {r['product_id']} x {r.get('quantity', 0)} (job: {job_id})")

    return {"job_id": job_id, "items": results, "status": "complete"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8010)
