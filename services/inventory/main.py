from fastapi import FastAPI, Depends, HTTPException, status, BackgroundTasks
from pydantic import BaseModel
from typing import List, Optional, Dict
import uuid
from datetime import datetime, date
import logging

app = FastAPI(title="CoreConnect Inventory Service", version="0.1.0")

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

# --- IAM Middleware (Stub) ---
async def get_current_tenant_id():
    return uuid.UUID("00000000-0000-0000-0000-000000000000")

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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8007)
