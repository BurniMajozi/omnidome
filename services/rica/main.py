from fastapi import FastAPI, Depends, HTTPException, status, BackgroundTasks, Request
from pydantic import BaseModel
from typing import List, Optional
import uuid
from datetime import datetime
import logging
import hashlib
import hmac
import os

app = FastAPI(title="CoreConnect RICA Service", version="0.1.0")

# --- SMILE ID CONFIG ---
SMILE_ID_PARTNER_ID = os.getenv("SMILE_ID_PARTNER_ID", "mock_partner")
SMILE_ID_API_KEY = os.getenv("SMILE_ID_API_KEY", "mock_key")

# --- Models ---
class RicaSessionCreate(BaseModel):
    contact_id: uuid.UUID
    verification_type: str = "DOCUMENT_VERIFICATION"

class RicaSessionResponse(BaseModel):
    job_id: str
    signature: str
    timestamp: str
    partner_id: str

class VerificationResult(BaseModel):
    job_id: str
    status: str
    result_code: Optional[str]
    result_message: Optional[str]

# --- IAM Middleware (Stub) ---
async def get_current_tenant_id():
    return uuid.UUID("00000000-0000-0000-0000-000000000000")

# --- Utils ---
def generate_smile_id_signature(timestamp: str):
    # Mock signature generation for Smile ID
    message = f"{timestamp}{SMILE_ID_PARTNER_ID}sid_request"
    return hmac.new(SMILE_ID_API_KEY.encode(), message.encode(), hashlib.sha256).hexdigest()

# --- Routes ---
@app.get("/")
async def root():
    return {"message": "CoreConnect RICA Service (Smile ID) is active"}

@app.post("/sessions", response_model=RicaSessionResponse)
async def create_rica_session(req: RicaSessionCreate, tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    """Initialize a Smile ID verification session"""
    job_id = f"RICA-{uuid.uuid4().hex[:8].upper()}"
    timestamp = datetime.now().isoformat()
    
    # Store pending session in DB (Logic later)
    
    return {
        "job_id": job_id,
        "signature": generate_smile_id_signature(timestamp),
        "timestamp": timestamp,
        "partner_id": SMILE_ID_PARTNER_ID
    }

@app.post("/callback")
async def smile_id_callback(request: Request, background_tasks: BackgroundTasks):
    """Webhook for Smile ID verification results"""
    payload = await request.json()
    logging.info(f"Received Smile ID callback: {payload.get('job_id')}")
    
    # Process job result and update CRM status
    job_id = payload.get("job_id")
    result_code = payload.get("result_code")
    
    # Background task to sync with CRM
    return {"status": "accepted"}

@app.get("/status/{job_id}", response_model=VerificationResult)
async def get_verification_status(job_id: str):
    # Mock status check
    return {
        "job_id": job_id,
        "status": "COMPLETED",
        "result_code": "1012",
        "result_message": "Document Verified Successfully"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8004)
