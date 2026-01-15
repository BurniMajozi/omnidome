from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from typing import List, Optional
import uuid
from datetime import datetime

app = FastAPI(title="CoreConnect CRM Service", version="0.1.0")

# --- Models ---
class ContactBase(BaseModel):
    first_name: str
    last_name: str
    email: str
    phone: Optional[str] = None
    physical_address: Optional[str] = None

class ContactCreate(ContactBase):
    pass

class Contact(ContactBase):
    id: uuid.UUID
    tenant_id: uuid.UUID
    rica_verified: bool
    created_at: datetime

    class Config:
        orm_mode = True

# --- IAM Middleware (Stub) ---
async def get_current_tenant_id():
    # In a real scenario, this would extract the tenant_id from the JWT
    # For foundation stage, we use a placeholder
    return uuid.UUID("00000000-0000-0000-0000-000000000000")

# --- Routes ---
@app.get("/")
async def root():
    return {"message": "CoreConnect CRM Service is active"}

@app.get("/contacts", response_model=List[Contact])
async def list_contacts(tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    # Mock data for initial foundation
    return [
        {
            "id": uuid.uuid4(),
            "tenant_id": tenant_id,
            "first_name": "John",
            "last_name": "Doe",
            "email": "john.doe@example.co.za",
            "phone": "0123456789",
            "rica_verified": True,
            "created_at": datetime.now()
        }
    ]

@app.post("/contacts", response_model=Contact, status_code=status.HTTP_201_CREATED)
async def create_contact(contact: ContactCreate, tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    # Mock creation for initial foundation
    return {
        "id": uuid.uuid4(),
        "tenant_id": tenant_id,
        **contact.dict(),
        "rica_verified": False,
        "created_at": datetime.now()
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
