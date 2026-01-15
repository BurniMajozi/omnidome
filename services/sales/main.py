from fastapi import FastAPI, Depends, HTTPException, status
from pydantic import BaseModel
from typing import List, Optional
import uuid
from datetime import datetime, date

app = FastAPI(title="CoreConnect Sales Service", version="0.1.0")

# --- Models ---
class LeadBase(BaseModel):
    first_name: str
    last_name: str
    email: str
    phone: Optional[str] = None
    source: Optional[str] = None
    address: Optional[str] = None

class LeadCreate(LeadBase):
    pass

class Lead(LeadBase):
    id: uuid.UUID
    tenant_id: uuid.UUID
    status: str
    created_at: datetime

    class Config:
        orm_mode = True

class DealBase(BaseModel):
    name: str
    amount: float
    close_date: Optional[date] = None

class DealCreate(DealBase):
    contact_id: uuid.UUID
    stage_id: uuid.UUID

class Deal(DealBase):
    id: uuid.UUID
    tenant_id: uuid.UUID
    contact_id: uuid.UUID
    stage_id: uuid.UUID
    created_at: datetime

    class Config:
        orm_mode = True

# --- IAM Middleware (Stub) ---
async def get_current_tenant_id():
    return uuid.UUID("00000000-0000-0000-0000-000000000000")

# --- Routes ---
@app.get("/")
async def root():
    return {"message": "CoreConnect Sales Service is active"}

@app.get("/leads", response_model=List[Lead])
async def list_leads(tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    return [
        {
            "id": uuid.uuid4(),
            "tenant_id": tenant_id,
            "first_name": "Sipho",
            "last_name": "Nkosi",
            "email": "sipho@example.com",
            "phone": "0821234567",
            "source": "Website",
            "status": "NEW",
            "created_at": datetime.now()
        }
    ]

@app.post("/deals", response_model=Deal, status_code=status.HTTP_201_CREATED)
async def create_deal(deal: DealCreate, tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    return {
        "id": uuid.uuid4(),
        "tenant_id": tenant_id,
        "created_at": datetime.now(),
        **deal.dict()
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
