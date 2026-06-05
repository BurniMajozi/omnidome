"""Customer Lifecycle routes — Move House, Service Pause, Coverage Check.

Handles non-cancellation customer lifecycle events:
- Moving house: coverage check at new address, service transfer
- Service pause: temporary billing suspension (max 3 months)
- Coverage availability: check FNO coverage by address
"""

import logging
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from services.journey_engine.models import (
    MoveHouseRequest, ServicePauseRequest,
    MOVE_HOUSE_STATUS, PAUSE_STATUS,
)
from services.common.auth import AuthContext, get_auth_context

logger = logging.getLogger("customer-journey.lifecycle")

router = APIRouter(prefix="/customer-lifecycle", tags=["Customer Lifecycle"])


# ── Request/Response Schemas ─────────────────────────────────────────────

class MoveHouseInitiateRequest(BaseModel):
    subscription_id: uuid.UUID
    old_address_line1: str
    old_address_line2: Optional[str] = None
    old_city: str
    old_postal_code: str
    new_address_line1: str
    new_address_line2: Optional[str] = None
    new_city: str
    new_postal_code: str
    new_province: Optional[str] = None
    new_gps_lat: Optional[Decimal] = None
    new_gps_lng: Optional[Decimal] = None
    requested_date: Optional[date] = None


class MoveHouseResponse(BaseModel):
    move_request_id: uuid.UUID
    status: str
    coverage_available: Optional[bool] = None
    fno_at_new_address: Optional[str] = None
    recommended_package: Optional[str] = None
    message: str


class MoveHouseCoverageCheckResponse(BaseModel):
    move_request_id: uuid.UUID
    coverage_available: bool
    fno_name: Optional[str] = None
    fno_technology: Optional[str] = None  # FTTH, FTTB, LTE
    available_packages: list[dict]
    estimated_installation_days: int


class PauseInitiateRequest(BaseModel):
    subscription_id: uuid.UUID
    reason: Optional[str] = None
    pause_start_date: date
    pause_end_date: date


class PauseResponse(BaseModel):
    pause_request_id: uuid.UUID
    status: str
    pause_start_date: date
    pause_end_date: date
    pause_monthly_fee_zar: Decimal
    message: str


class RequestIdPath(BaseModel):
    request_id: uuid.UUID


# ── POST /customer-lifecycle/move-house ──────────────────────────────────

@router.post("/move-house", response_model=MoveHouseResponse, status_code=status.HTTP_201_CREATED)
async def initiate_move_house(
    body: MoveHouseInitiateRequest,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Customer initiates moving house — check coverage at new address."""
    from sqlalchemy import select, create_engine
    from services.common.db import get_engine
    from services.billing.models import Subscription

    engine = get_engine()
    with engine.connect() as conn:
        # Verify subscription
        sub_result = conn.execute(
            select(Subscription).where(
                Subscription.id == body.subscription_id,
                Subscription.tenant_id == ctx.tenant_id,
            )
        ).first()
        if not sub_result:
            raise HTTPException(status_code=404, detail="Subscription not found")

    # Create move request
    move_req = MoveHouseRequest(
        tenant_id=ctx.tenant_id,
        customer_id=ctx.user_id,  # Simplified — would come from subscription
        subscription_id=body.subscription_id,
        account_number="ACC-0001",
        old_address={
            "line1": body.old_address_line1,
            "line2": body.old_address_line2,
            "city": body.old_city,
            "postal_code": body.old_postal_code,
        },
        new_address={
            "line1": body.new_address_line1,
            "line2": body.new_address_line2,
            "city": body.new_city,
            "postal_code": body.new_postal_code,
            "province": body.new_province,
        },
        new_address_line1=body.new_address_line1,
        new_address_line2=body.new_address_line2,
        new_city=body.new_city,
        new_postal_code=body.new_postal_code,
        new_province=body.new_province,
        new_gps_lat=body.new_gps_lat,
        new_gps_lng=body.new_gps_lng,
        status="pending",
        requested_date=body.requested_date or (date.today() + timedelta(days=14)),
    )

    from sqlalchemy.orm import Session
    with Session(engine) as session:
        session.add(move_req)
        session.commit()
        move_id = move_req.id

    return MoveHouseResponse(
        move_request_id=move_id,
        status="pending",
        message="Move request submitted. Coverage check will be performed.",
    )


# ── POST /customer-lifecycle/move-house/{id}/check-coverage ──────────────

@router.post("/move-house/{request_id}/check-coverage", response_model=MoveHouseCoverageCheckResponse)
async def check_move_house_coverage(
    request_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Check FNO coverage at the new address."""
    from sqlalchemy.orm import Session
    from services.common.db import get_engine

    engine = get_engine()
    with Session(engine) as session:
        move_req = session.query(MoveHouseRequest).filter(
            MoveHouseRequest.id == request_id,
            MoveHouseRequest.tenant_id == ctx.tenant_id,
        ).first()
        if not move_req:
            raise HTTPException(status_code=404, detail="Move request not found")

        # Simulate coverage check — in production, call FNO API or coverage_areas table
        # This would check availability_areas table by GPS/postal code
        coverage_available = True  # Mock
        fno_name = "Vumatel"
        fno_technology = "FTTH"

        move_req.coverage_checked = True
        move_req.coverage_available = coverage_available
        move_req.fno_at_new_address = fno_name
        move_req.status = "covered" if coverage_available else "not_covered"

        session.commit()

        if coverage_available:
            return MoveHouseCoverageCheckResponse(
                move_request_id=request_id,
                coverage_available=True,
                fno_name=fno_name,
                fno_technology=fno_technology,
                available_packages=[
                    {"name": "Home 50Mbps", "monthly_zar": 799, "once_off_zar": 0},
                    {"name": "Home 100Mbps", "monthly_zar": 999, "once_off_zar": 0},
                    {"name": "Home 200Mbps", "monthly_zar": 1299, "once_off_zar": 0},
                ],
                estimated_installation_days=14,
            )
        else:
            return MoveHouseCoverageCheckResponse(
                move_request_id=request_id,
                coverage_available=False,
                available_packages=[],
                estimated_installation_days=0,
            )


# ── POST /customer-lifecycle/move-house/{id}/schedule ────────────────────

@router.post("/move-house/{request_id}/schedule")
async def schedule_move_house_installation(
    request_id: uuid.UUID,
    preferred_date: date = Query(...),
    ctx: AuthContext = Depends(get_auth_context),
):
    """Schedule installation at new address after coverage confirmed."""
    from sqlalchemy.orm import Session
    from services.common.db import get_engine

    engine = get_engine()
    with Session(engine) as session:
        move_req = session.query(MoveHouseRequest).filter(
            MoveHouseRequest.id == request_id,
            MoveHouseRequest.tenant_id == ctx.tenant_id,
        ).first()
        if not move_req:
            raise HTTPException(status_code=404, detail="Move request not found")
        if not move_req.coverage_available:
            raise HTTPException(status_code=400, detail="Coverage not available at new address")

        move_req.installation_date = preferred_date
        move_req.status = "installation_scheduled"
        session.commit()

        return {
            "move_request_id": str(request_id),
            "installation_date": preferred_date.isoformat(),
            "status": "installation_scheduled",
            "message": f"Installation scheduled for {preferred_date}. Technician will contact you.",
        }


# ── POST /customer-lifecycle/pause ───────────────────────────────────────

@router.post("/pause", response_model=PauseResponse, status_code=status.HTTP_201_CREATED)
async def initiate_service_pause(
    body: PauseInitiateRequest,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Customer requests service pause (max 3 months)."""
    from sqlalchemy.orm import Session
    from services.common.db import get_engine
    from services.billing.models import Subscription

    engine = get_engine()
    with Session(engine) as session:
        # Verify subscription
        sub = session.query(Subscription).filter(
            Subscription.id == body.subscription_id,
            Subscription.tenant_id == ctx.tenant_id,
        ).first()
        if not sub:
            raise HTTPException(status_code=404, detail="Subscription not found")

        # Validate dates
        pause_duration = (body.pause_end_date - body.pause_start_date).days
        if pause_duration > 90:  # Max 3 months
            raise HTTPException(status_code=400, detail="Maximum pause period is 3 months (90 days)")
        if pause_duration <= 0:
            raise HTTPException(status_code=400, detail="End date must be after start date")

        pause_req = ServicePauseRequest(
            tenant_id=ctx.tenant_id,
            customer_id=sub.customer_id,
            subscription_id=body.subscription_id,
            account_number="ACC-0001",
            reason=body.reason,
            pause_start_date=body.pause_start_date,
            pause_end_date=body.pause_end_date,
            max_pause_months=3,
            status="approved",
            pause_monthly_fee_zar=Decimal("49.00"),  # Minimal monthly fee during pause
        )
        session.add(pause_req)

        # Update subscription
        sub.status = "paused"

        session.commit()
        pause_id = pause_req.id

    return PauseResponse(
        pause_request_id=pause_id,
        status="approved",
        pause_start_date=body.pause_start_date,
        pause_end_date=body.pause_end_date,
        pause_monthly_fee_zar=Decimal("49.00"),
        message="Service paused. Minimal monthly fee of R49 applies. Auto-reactivation scheduled.",
    )


# ── POST /customer-lifecycle/pause/{id}/reactivate ───────────────────────

@router.post("/pause/{pause_id}/reactivate")
async def reactivate_service(
    pause_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Reactivate service early (before pause end date)."""
    from sqlalchemy.orm import Session
    from services.common.db import get_engine

    engine = get_engine()
    with Session(engine) as session:
        pause_req = session.query(ServicePauseRequest).filter(
            ServicePauseRequest.id == pause_id,
            ServicePauseRequest.tenant_id == ctx.tenant_id,
        ).first()
        if not pause_req:
            raise HTTPException(status_code=404, detail="Pause request not found")

        pause_req.status = "reactivated"
        pause_req.reactivated_at = datetime.utcnow()

        # Reactivate subscription
        from services.billing.models import Subscription
        sub = session.query(Subscription).filter(
            Subscription.id == pause_req.subscription_id,
        ).first()
        if sub:
            sub.status = "active"

        session.commit()

        return {
            "pause_request_id": str(pause_id),
            "status": "reactivated",
            "message": "Service reactivated. Full billing resumes from today.",
        }


# ── GET /customer-lifecycle/pause/{id}/status ────────────────────────────

@router.get("/pause/{pause_id}/status")
async def get_pause_status(
    pause_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    from sqlalchemy.orm import Session
    from services.common.db import get_engine

    engine = get_engine()
    with Session(engine) as session:
        pause_req = session.query(ServicePauseRequest).filter(
            ServicePauseRequest.id == pause_id,
            ServicePauseRequest.tenant_id == ctx.tenant_id,
        ).first()
        if not pause_req:
            raise HTTPException(status_code=404, detail="Pause request not found")

        days_remaining = max(0, (pause_req.pause_end_date - date.today()).days)

        return {
            "pause_request_id": str(pause_id),
            "status": pause_req.status,
            "pause_start_date": pause_req.pause_start_date.isoformat(),
            "pause_end_date": pause_req.pause_end_date.isoformat(),
            "days_remaining": days_remaining,
            "pause_monthly_fee_zar": float(pause_req.pause_monthly_fee_zar),
            "reason": pause_req.reason,
        }


# ── GET /customer-lifecycle/coverage-check ───────────────────────────────

@router.get("/coverage-check")
async def check_coverage(
    address: str = Query(..., description="Street address or postal code"),
    gps_lat: Optional[Decimal] = Query(None),
    gps_lng: Optional[Decimal] = Query(None),
    ctx: AuthContext = Depends(get_auth_context),
):
    """Check fiber coverage availability at an address.

    In production, queries coverage_areas table with FNO coverage data.
    Could also call FNO APIs directly (Vumatel, Openserve).
    """
    # Mock coverage check — in production:
    # 1. Geocode address to GPS
    # 2. Query coverage_areas table by GPS proximity
    # 3. Return available FNOs and packages
    # 4. For FNOs without API, return "check manually" flag

    # Simulate lookup
    postal_code = address.split()[-1] if address else ""
    gauteng_postals = ["2000", "2001", "2017", "2092", "2190", "2196"]
    available = postal_code[:2] in ["20", "21", "16", "17"] or postal_code in gauteng_postals

    if available:
        return {
            "available": True,
            "fnos": [
                {"name": "Vumatel", "technology": "FTTH", "max_speed_mbps": 1000},
                {"name": "Openserve", "technology": "FTTH", "max_speed_mbps": 500},
            ],
            "packages": [
                {"name": "Home 50Mbps", "monthly_zar": 799, "once_off_zar": 0},
                {"name": "Home 100Mbps", "monthly_zar": 999, "once_off_zar": 0},
                {"name": "Home 200Mbps", "monthly_zar": 1299, "once_off_zar": 0},
                {"name": "Uncapped 50Mbps", "monthly_zar": 1099, "once_off_zar": 0},
            ],
            "estimated_installation_days": 14,
        }
    else:
        return {
            "available": False,
            "message": "Fiber not yet available in this area. Register for notifications.",
            "notification_signup": True,
            "alternatives": [
                {"type": "LTE", "available": True, "monthly_zar_from": 499},
                {"type": "Fixed Wireless", "available": True, "monthly_zar_from": 699},
            ],
        }
