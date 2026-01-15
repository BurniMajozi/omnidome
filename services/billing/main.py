from fastapi import FastAPI, Depends, HTTPException, status, BackgroundTasks
from pydantic import BaseModel
from typing import List, Optional
import uuid
from datetime import datetime, date
import logging

app = FastAPI(title="CoreConnect Billing Service", version="0.1.0")

# --- Models ---
class PlanBase(BaseModel):
    name: str
    description: str
    price: float
    currency: str = "ZAR"
    billing_cycle: str = "MONTHLY"

class Plan(PlanBase):
    id: uuid.UUID
    tenant_id: uuid.UUID
    created_at: datetime

class SubscriptionCreate(BaseModel):
    contact_id: uuid.UUID
    plan_id: uuid.UUID
    start_date: date

class Subscription(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    contact_id: uuid.UUID
    plan_id: uuid.UUID
    status: str
    next_billing_date: date
    created_at: datetime

class Invoice(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    contact_id: uuid.UUID
    invoice_number: str
    amount: float
    tax_amount: float
    total_amount: float
    status: str
    due_date: date

# --- IAM Middleware (Stub) ---
async def get_current_tenant_id():
    return uuid.UUID("00000000-0000-0000-0000-000000000000")

# --- Routes ---
@app.get("/")
async def root():
    return {"message": "CoreConnect Billing Service is active"}

@app.post("/plans", response_model=Plan, status_code=status.HTTP_201_CREATED)
async def create_plan(plan: PlanBase, tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    return {
        "id": uuid.uuid4(),
        "tenant_id": tenant_id,
        "created_at": datetime.now(),
        **plan.dict()
    }

@app.post("/subscriptions", response_model=Subscription, status_code=status.HTTP_201_CREATED)
async def subscribe_customer(sub: SubscriptionCreate, tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    # Logic to initialize subscription and schedule next bill
    return {
        "id": uuid.uuid4(),
        "tenant_id": tenant_id,
        "status": "ACTIVE",
        "next_billing_date": date.today(), # Normalized for demo
        "created_at": datetime.now(),
        **sub.dict()
    }

@app.post("/payments/webhook")
async def paystack_webhook(payload: dict, background_tasks: BackgroundTasks):
    # Process Paystack webhook (payment.success, subscription.create)
    logging.info(f"Received Paystack webhook: {payload.get('event')}")
    return {"status": "accepted"}

@app.post("/refunds/{invoice_id}")
async def process_refund(invoice_id: uuid.UUID, reason: str, tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    # Internal logic to trigger Paystack refund and update ledger
    return {"status": "REFUND_INITIATED", "invoice_id": invoice_id, "amount_refunded": 0.0}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)
