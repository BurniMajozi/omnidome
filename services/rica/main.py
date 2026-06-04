from fastapi import FastAPI, Depends, HTTPException, status, BackgroundTasks, Request
from pydantic import BaseModel
from typing import List, Optional
import uuid
from datetime import datetime
import logging
import hashlib
import hmac
import os
from sqlalchemy import select, desc

from services.common.entitlements import EntitlementGuard
from services.common.auth import get_current_tenant_id
from services.rica.database import get_session, init_tables
from sqlalchemy.ext.asyncio import AsyncSession

app = FastAPI(title="CoreConnect RICA Service", version="0.1.0")
guard = EntitlementGuard(module_id="rica", public_paths={"/callback"})


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok", "service": "rica"}


@app.on_event("startup")
async def startup() -> None:
    await init_tables()
    guard.ensure_startup()


@app.middleware("http")
async def entitlement_middleware(request, call_next):
    return await guard.middleware(request, call_next)

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

class RicaCallbackUpdate(BaseModel):
    status: str
    result_code: Optional[str] = None
    result_message: Optional[str] = None
    full_response: Optional[dict] = None

# --- Utils ---
def generate_smile_id_signature(timestamp: str):
    # Mock signature generation for Smile ID
    message = f"{timestamp}{SMILE_ID_PARTNER_ID}sid_request"
    return hmac.new(SMILE_ID_API_KEY.encode(), message.encode(), hashlib.sha256).hexdigest()

def _verification_to_dict(v):
    return {
        "id": str(v.id),
        "tenant_id": str(v.tenant_id),
        "contact_id": str(v.contact_id) if v.contact_id else None,
        "job_id": v.job_id,
        "smile_job_id": v.smile_job_id,
        "verification_type": v.verification_type,
        "status": v.status,
        "result_code": v.result_code,
        "result_message": v.result_message,
        "full_response": v.full_response,
        "id_number": v.id_number,
        "first_name": v.first_name,
        "last_name": v.last_name,
        "created_at": v.created_at.isoformat() if v.created_at else None,
        "updated_at": v.updated_at.isoformat() if v.updated_at else None,
    }

async def _ensure_sample_data(tenant_id: uuid.UUID, db: AsyncSession):
    from services.rica.database import RicaVerification
    result = await db.execute(
        select(RicaVerification).where(RicaVerification.tenant_id == tenant_id)
    )
    existing = result.scalars().all()
    if not existing:
        now = datetime.utcnow()
        sample_completed = RicaVerification(
            tenant_id=tenant_id,
            job_id="RICA-SAMPLE-001",
            smile_job_id="SMILE-001",
            verification_type="DOCUMENT_VERIFICATION",
            status="COMPLETED",
            result_code="1012",
            result_message="Document Verified Successfully",
            id_number="9001015009087",
            first_name="Thabo",
            last_name="Mokoena",
            created_at=now,
            updated_at=now,
        )
        sample_pending = RicaVerification(
            tenant_id=tenant_id,
            job_id="RICA-SAMPLE-002",
            smile_job_id="SMILE-002",
            verification_type="DOCUMENT_VERIFICATION",
            status="PENDING",
            id_number="8503125009081",
            first_name="Nomsa",
            last_name="Dlamini",
            created_at=now,
            updated_at=now,
        )
        db.add(sample_completed)
        db.add(sample_pending)
        await db.flush()

# --- Routes ---
@app.get("/")
async def root():
    return {"message": "CoreConnect RICA Service (Smile ID) is active"}

@app.post("/sessions", response_model=RicaSessionResponse)
async def create_rica_session(
    req: RicaSessionCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    """Initialize a Smile ID verification session"""
    from services.rica.database import RicaVerification

    job_id = f"RICA-{uuid.uuid4().hex[:8].upper()}"
    timestamp = datetime.now().isoformat()

    verification = RicaVerification(
        tenant_id=tenant_id,
        contact_id=req.contact_id,
        job_id=job_id,
        verification_type=req.verification_type,
        status="PENDING",
    )
    db.add(verification)
    await db.flush()

    return {
        "job_id": job_id,
        "signature": generate_smile_id_signature(timestamp),
        "timestamp": timestamp,
        "partner_id": SMILE_ID_PARTNER_ID,
    }

@app.post("/callback")
async def smile_id_callback(
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_session),
):
    """Webhook for Smile ID verification results"""
    from services.rica.database import RicaVerification

    payload = await request.json()
    logging.info(f"Received Smile ID callback: {payload.get('job_id')}")

    job_id = payload.get("job_id")
    result_code = payload.get("result_code")

    # Update the verification in DB
    result = await db.execute(
        select(RicaVerification).where(RicaVerification.job_id == job_id)
    )
    verification = result.scalar_one_or_none()
    if verification:
        verification.status = "COMPLETED" if result_code == "1012" else "FAILED"
        verification.result_code = result_code
        verification.result_message = payload.get("result_message")
        verification.full_response = payload
        verification.smile_job_id = payload.get("smile_job_id", verification.smile_job_id)
        await db.flush()

    # Background task to sync with CRM
    return {"status": "accepted"}

@app.get("/status/{job_id}", response_model=VerificationResult)
async def get_verification_status(
    job_id: str,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    from services.rica.database import RicaVerification

    result = await db.execute(
        select(RicaVerification).where(
            RicaVerification.job_id == job_id,
            RicaVerification.tenant_id == tenant_id,
        )
    )
    verification = result.scalar_one_or_none()
    if not verification:
        raise HTTPException(status_code=404, detail="Verification not found")

    return {
        "job_id": verification.job_id,
        "status": verification.status,
        "result_code": verification.result_code,
        "result_message": verification.result_message,
    }

@app.get("/verifications")
async def list_verifications(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    from services.rica.database import RicaVerification

    await _ensure_sample_data(tenant_id, db)

    result = await db.execute(
        select(RicaVerification)
        .where(RicaVerification.tenant_id == tenant_id)
        .order_by(desc(RicaVerification.created_at))
    )
    verifications = result.scalars().all()
    return [_verification_to_dict(v) for v in verifications]

@app.get("/verifications/{verification_id}")
async def get_verification(
    verification_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    from services.rica.database import RicaVerification

    result = await db.execute(
        select(RicaVerification).where(
            RicaVerification.id == verification_id,
            RicaVerification.tenant_id == tenant_id,
        )
    )
    verification = result.scalar_one_or_none()
    if not verification:
        raise HTTPException(status_code=404, detail="Verification not found")
    return _verification_to_dict(verification)

@app.put("/verifications/{verification_id}/callback")
async def update_verification_callback(
    verification_id: uuid.UUID,
    update: RicaCallbackUpdate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    from services.rica.database import RicaVerification

    result = await db.execute(
        select(RicaVerification).where(
            RicaVerification.id == verification_id,
            RicaVerification.tenant_id == tenant_id,
        )
    )
    verification = result.scalar_one_or_none()
    if not verification:
        raise HTTPException(status_code=404, detail="Verification not found")

    verification.status = update.status
    if update.result_code is not None:
        verification.result_code = update.result_code
    if update.result_message is not None:
        verification.result_message = update.result_message
    if update.full_response is not None:
        verification.full_response = update.full_response
    await db.flush()

    return _verification_to_dict(verification)


@app.delete("/verifications/{verification_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_verification(
    verification_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    from services.rica.database import RicaVerification

    result = await db.execute(
        select(RicaVerification).where(
            RicaVerification.id == verification_id,
            RicaVerification.tenant_id == tenant_id,
        )
    )
    verification = result.scalar_one_or_none()
    if not verification:
        raise HTTPException(status_code=404, detail="Verification not found")

    await db.delete(verification)
    await db.flush()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8004)
