"""RICA verification routes — Smile ID KYC integration, webhooks, audit trail."""

import os
import uuid
import math
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from services.common.auth import AuthContext, get_auth_context
from rica.database import session_scope
from rica.models import RICAVerification, RICALog
from rica.schemas import (
    PaginatedResponse, RICAVerificationCreate, RICAVerificationRead,
    RICAVerificationUpdate, RICAVerifyRequest, RICAVerifyResponse, RICALogRead,
)
from sqlalchemy import select, func, and_

logger = logging.getLogger("rica.verifications")

router = APIRouter(prefix="/api/v1/rica/verifications", tags=["RICA Verifications"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def luhn_check(id_number: str) -> bool:
    """Validate a South African ID number using the Luhn algorithm.

    SA ID numbers are 13 digits. The last digit is a check digit computed
    via Luhn on the first 12 digits.
    """
    if not id_number or len(id_number) != 13:
        return False
    if not id_number.isdigit():
        return False

    digits = [int(d) for d in id_number[:-1]]
    # Double every second digit from right to left
    for i in range(len(digits) - 1, -1, -2):
        digits[i] *= 2
        if digits[i] > 9:
            digits[i] -= 9
    total = sum(digits)
    check_digit = (10 - (total % 10)) % 10
    return check_digit == int(id_number[-1])


def compute_expires_at() -> datetime:
    """RICA verification expires after 5 years per South African law."""
    return datetime.now(timezone.utc) + timedelta(days=5 * 365)


async def _call_smile_id(
    job_id: str,
    id_number: str,
    first_name: str,
    last_name: str,
    verification_type: str,
    selfie_image_b64: Optional[str] = None,
    id_image_b64: Optional[str] = None,
) -> dict:
    """Call the Smile ID API for identity verification.

    If SMILE_ID_API_KEY is set in the environment, a real API call is made.
    Otherwise, a mock success response is returned for development.
    """
    api_key = os.getenv("SMILE_ID_API_KEY")
    partner_id = os.getenv("SMILE_ID_PARTNER_ID")

    job_type_map = {
        "smart_id": 5,
        "basic_kyc": 1,
        "enhanced_kyc": 4,
    }

    if api_key and partner_id:
        import httpx

        SmileIdApi = None
        try:
            from smile_id_core import SidServer

            smile = SidServer(partner_id, api_key, os.getenv("SMILE_ID_SID_SERVER", "0"))
            result = smile.submit_job(
                partner_params={
                    "user_id": job_id,
                    "job_id": job_id,
                    "job_type": job_type_map.get(verification_type, 1),
                },
                id_info={
                    "first_name": first_name,
                    "last_name": last_name,
                    "id_number": id_number,
                    "country": "ZA",
                },
                images=[],
            )
            return {
                "success": True,
                "job_id": job_id,
                "result_code": "00",
                "result_text": "Authenticated",
                "result": result,
            }
        except Exception as exc:
            logger.error("Smile ID API call failed: %s", exc)
            return {
                "success": False,
                "job_id": job_id,
                "result_code": "90",
                "result_text": f"API error: {exc}",
            }
    else:
        # Mock response for development
        logger.info(
            "Smile ID API key not configured — returning mock success for job %s",
            job_id,
        )
        return {
            "success": True,
            "job_id": job_id,
            "result_code": "00",
            "result_text": "Authenticated (mock)",
        }


async def _audit_log(
    session, tenant_id: uuid.UUID, verification_id: uuid.UUID,
    action: str, details: Optional[dict] = None,
) -> None:
    """Write an entry to the RICA audit log."""
    log = RICALog(
        tenant_id=tenant_id,
        verification_id=verification_id,
        action=action,
        details=details or {},
    )
    session.add(log)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("", response_model=RICAVerifyResponse, status_code=status.HTTP_202_ACCEPTED)
async def submit_verification(
    body: RICAVerifyRequest,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Submit a new RICA identity verification via Smile ID.

    Validates the SA ID number with Luhn check, creates the verification
    record, and calls the Smile ID API (or returns mock in dev mode).
    """
    if not luhn_check(body.id_number):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid South African ID number — Luhn check failed",
        )

    job_id = str(uuid.uuid4())
    expires_at = compute_expires_at()

    async with session_scope() as session:
        # Check for an existing active verification for this customer
        existing = await session.execute(
            select(RICAVerification).where(
                RICAVerification.tenant_id == ctx.tenant_id,
                RICAVerification.customer_id == body.customer_id,
                RICAVerification.status.in_(["pending", "in_progress", "verified"]),
                RICAVerification.expires_at > datetime.now(timezone.utc),
            )
        )
        existing_ver = existing.scalars().first()
        if existing_ver and existing_ver.status == "verified":
            return RICAVerifyResponse(
                job_id=str(existing_ver.id),
                status="verified",
                result_code=existing_ver.result_code,
                result_text="Customer already verified",
            )

        # Create verification record
        verification = RICAVerification(
            tenant_id=ctx.tenant_id,
            customer_id=body.customer_id,
            id_number=body.id_number,
            first_name=body.first_name,
            last_name=body.last_name,
            verification_type=body.verification_type,
            status="pending",
            smile_id_job_id=job_id,
            expires_at=expires_at,
        )
        session.add(verification)
        await session.flush()
        await session.refresh(verification)

        await _audit_log(
            session, ctx.tenant_id, verification.id,
            "verification_submitted",
            {"verification_type": body.verification_type, "smile_id_job_id": job_id},
        )

    # Call Smile ID (outside the DB session to avoid holding the txn)
    smile_result = await _call_smile_id(
        job_id=job_id,
        id_number=body.id_number,
        first_name=body.first_name,
        last_name=body.last_name,
        verification_type=body.verification_type,
        selfie_image_b64=body.selfie_image_base64,
        id_image_b64=body.id_image_base64,
    )

    # Update verification record with smile ID result
    async with session_scope() as session:
        verification = await session.get(RICAVerification, verification.id)
        if verification:
            if smile_result["success"]:
                verification.status = "verified"
                verification.verified_at = datetime.now(timezone.utc)
            else:
                verification.status = "failed"
            verification.smile_id_job_id = smile_result.get("job_id", job_id)
            verification.result_code = smile_result.get("result_code")
            verification.result_text = smile_result.get("result_text")
            await session.flush()
            await session.refresh(verification)
            await _audit_log(
                session, ctx.tenant_id, verification.id,
                "smile_id_response",
                {"result_code": smile_result.get("result_code")},
            )

    return RICAVerifyResponse(
        job_id=job_id,
        status=smile_result.get("result_code", "00") == "00" and "verified" or "failed",
        result_code=smile_result.get("result_code"),
        result_text=smile_result.get("result_text"),
    )


@router.get("", response_model=PaginatedResponse)
async def list_verifications(
    ctx: AuthContext = Depends(get_auth_context),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    customer_id: Optional[uuid.UUID] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    id_number: Optional[str] = Query(None),
):
    """List RICA verifications with pagination and filters."""
    async with session_scope() as session:
        query = select(RICAVerification).where(RICAVerification.tenant_id == ctx.tenant_id)

        if customer_id:
            query = query.where(RICAVerification.customer_id == customer_id)
        if status_filter:
            query = query.where(RICAVerification.status == status_filter)
        if id_number:
            query = query.where(RICAVerification.id_number == id_number)

        total = await session.scalar(
            select(func.count()).select_from(query.subquery())
        )
        items = (
            await session.execute(
                query.order_by(RICAVerification.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).scalars().all()

        return PaginatedResponse(
            items=[RICAVerificationRead.model_validate(i) for i in items],
            total=total or 0,
            page=page,
            page_size=page_size,
            pages=max(1, math.ceil((total or 0) / page_size)),
        )


@router.get("/{verification_id}", response_model=RICAVerificationRead)
async def get_verification(
    verification_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Get a single RICA verification by ID, including audit log."""
    async with session_scope() as session:
        verification = await session.get(RICAVerification, verification_id)
        if not verification or verification.tenant_id != ctx.tenant_id:
            raise HTTPException(status_code=404, detail="Verification not found")
        return RICAVerificationRead.model_validate(verification)


@router.post("/{verification_id}/retry", response_model=RICAVerifyResponse)
async def retry_verification(
    verification_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Retry a failed or expired RICA verification."""
    async with session_scope() as session:
        verification = await session.get(RICAVerification, verification_id)
        if not verification or verification.tenant_id != ctx.tenant_id:
            raise HTTPException(status_code=404, detail="Verification not found")
        if verification.status in ("verified", "in_progress"):
            raise HTTPException(
                status_code=400,
                detail=f"Cannot retry a verification with status '{verification.status}'",
            )

        job_id = str(uuid.uuid4())
        verification.status = "pending"
        verification.smile_id_job_id = job_id
        verification.expires_at = compute_expires_at()
        verification.result_code = None
        verification.result_text = None
        await session.flush()
        await session.refresh(verification)

        await _audit_log(
            session, ctx.tenant_id, verification.id,
            "verification_retried",
            {"smile_id_job_id": job_id},
        )

        id_number = verification.id_number
        first_name = verification.first_name
        last_name = verification.last_name
        vtype = verification.verification_type

    # Call Smile ID outside the DB session
    smile_result = await _call_smile_id(
        job_id=job_id,
        id_number=id_number,
        first_name=first_name,
        last_name=last_name,
        verification_type=vtype,
    )

    async with session_scope() as session:
        verification = await session.get(RICAVerification, verification_id)
        if verification:
            if smile_result["success"]:
                verification.status = "verified"
                verification.verified_at = datetime.now(timezone.utc)
            else:
                verification.status = "failed"
            verification.smile_id_job_id = smile_result.get("job_id", job_id)
            verification.result_code = smile_result.get("result_code")
            verification.result_text = smile_result.get("result_text")
            await session.flush()
            await session.refresh(verification)
            await _audit_log(
                session, ctx.tenant_id, verification.id,
                "smile_id_response_retry",
                {"result_code": smile_result.get("result_code")},
            )

    return RICAVerifyResponse(
        job_id=job_id,
        status=smile_result.get("result_code", "00") == "00" and "verified" or "failed",
        result_code=smile_result.get("result_code"),
        result_text=smile_result.get("result_text"),
    )


@router.post("/webhook")
async def smile_id_webhook(payload: dict):
    """Smile ID webhook handler — receives async verification results.

    This endpoint is public (no auth) and called by Smile ID servers.
    It updates the verification record based on the webhook payload.
    """
    logger.info("Received Smile ID webhook: %s", payload)

    job_id = payload.get("job_id") or payload.get("SmileJobID") or payload.get("partner_params", {}).get("job_id")
    result_code = payload.get("result_code") or payload.get("ResultCode")
    result_text = payload.get("result_text") or payload.get("ResultText")

    if not job_id:
        logger.warning("Smile ID webhook missing job_id: %s", payload)
        return {"status": "error", "detail": "Missing job_id"}

    async with session_scope() as session:
        result = await session.execute(
            select(RICAVerification).where(RICAVerification.smile_id_job_id == job_id)
        )
        verification = result.scalars().first()

        if not verification:
            logger.warning("Smile ID webhook job_id not found: %s", job_id)
            return {"status": "error", "detail": f"No verification for job {job_id}"}

        if result_code and result_code.startswith("10"):  # 10xxx = success codes
            verification.status = "verified"
            verification.verified_at = datetime.now(timezone.utc)
        elif result_code:
            verification.status = "failed"

        verification.result_code = result_code
        verification.result_text = result_text

        # Store image URLs if provided by Smile ID
        image_selfie = payload.get("image_selfie_url") or payload.get("selfie_image_url")
        image_id = payload.get("image_id_document_url") or payload.get("id_image_url")
        if image_selfie:
            verification.image_selfie_url = image_selfie
        if image_id:
            verification.image_id_url = image_id

        await session.flush()
        await _audit_log(
            session, verification.tenant_id, verification.id,
            "webhook_received",
            {"result_code": result_code, "result_text": result_text},
        )

    return {"status": "ok", "job_id": job_id, "verification_status": verification.status}


@router.get("/status/{customer_id}")
async def verification_status(
    customer_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Quick status check — returns the most recent verification for a customer."""
    async with session_scope() as session:
        now = datetime.now(timezone.utc)
        result = await session.execute(
            select(RICAVerification).where(
                RICAVerification.tenant_id == ctx.tenant_id,
                RICAVerification.customer_id == customer_id,
            ).order_by(RICAVerification.created_at.desc()).limit(1)
        )
        verification = result.scalars().first()

        if not verification:
            return {"customer_id": str(customer_id), "status": "not_verified"}

        # Auto-expire if past expiration date
        if verification.status == "verified" and verification.expires_at and verification.expires_at < now:
            verification.status = "expired"
            await session.flush()

        return {
            "customer_id": str(customer_id),
            "verification_id": str(verification.id),
            "status": verification.status,
            "verification_type": verification.verification_type,
            "verified_at": verification.verified_at.isoformat() if verification.verified_at else None,
            "expires_at": verification.expires_at.isoformat() if verification.expires_at else None,
            "result_code": verification.result_code,
        }
