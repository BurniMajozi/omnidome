"""Network service management routes.

CRUD for network services plus operational endpoints:
  - suspend / reinstate individual services
  - suspend / reinstate ALL services for a customer (used by Billing)
  - speed upgrade / downgrade
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func

from services.common.auth import AuthContext, get_auth_context
from services.network.database import generate_service_reference, get_session
from services.network.models import NetworkService, RadiusAccount
from services.network.schemas import (
    BulkCustomerReinstateRequest,
    BulkCustomerSuspendRequest,
    NetworkServiceCreate,
    NetworkServiceRead,
    NetworkServiceUpdate,
    PaginatedResponse,
    ServiceReinstateRequest,
    ServiceSuspendRequest,
    SpeedChangeRequest,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/services", tags=["Services"])


# ---------------------------------------------------------------------------
# CREATE
# ---------------------------------------------------------------------------

@router.post("", response_model=NetworkServiceRead, status_code=status.HTTP_201_CREATED)
async def create_service(
    payload: NetworkServiceCreate,
    auth: AuthContext = Depends(get_auth_context),
):
    """Register a new network service for a customer."""
    with get_session() as session:
        ref = generate_service_reference(auth.tenant_id)
        service = NetworkService(
            tenant_id=auth.tenant_id,
            customer_id=payload.customer_id,
            service_reference=ref,
            description=payload.description,
            technology=payload.technology,
            fno_provider=payload.fno_provider,
            download_speed_mbps=payload.download_speed_mbps,
            upload_speed_mbps=payload.upload_speed_mbps,
            speed_profile_name=payload.speed_profile_name,
            address_line1=payload.address_line1,
            address_line2=payload.address_line2,
            city=payload.city,
            province=payload.province,
            postal_code=payload.postal_code,
            gps_latitude=payload.gps_latitude,
            gps_longitude=payload.gps_longitude,
            ont_serial=payload.ont_serial,
        )
        session.add(service)
        session.flush()
        session.refresh(service)
        logger.info("Created network service %s [%s] for customer %s", ref, service.id, payload.customer_id)
        return NetworkServiceRead.model_validate(service)


# ---------------------------------------------------------------------------
# LIST
# ---------------------------------------------------------------------------

@router.get("", response_model=PaginatedResponse)
async def list_services(
    auth: AuthContext = Depends(get_auth_context),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    customer_id: Optional[uuid.UUID] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    fno_provider: Optional[str] = None,
    search: Optional[str] = None,
):
    """List network services for the current tenant."""
    with get_session() as session:
        q = select(NetworkService).where(NetworkService.tenant_id == auth.tenant_id)
        count_q = select(func.count(NetworkService.id)).where(NetworkService.tenant_id == auth.tenant_id)

        if customer_id:
            q = q.where(NetworkService.customer_id == customer_id)
            count_q = count_q.where(NetworkService.customer_id == customer_id)
        if status_filter:
            q = q.where(NetworkService.status == status_filter)
            count_q = count_q.where(NetworkService.status == status_filter)
        if fno_provider:
            q = q.where(NetworkService.fno_provider == fno_provider.lower())
            count_q = count_q.where(NetworkService.fno_provider == fno_provider.lower())
        if search:
            like = f"%{search}%"
            q = q.where(
                NetworkService.service_reference.ilike(like)
                | NetworkService.description.ilike(like)
                | NetworkService.city.ilike(like)
            )
            count_q = count_q.where(
                NetworkService.service_reference.ilike(like)
                | NetworkService.description.ilike(like)
                | NetworkService.city.ilike(like)
            )

        total = session.execute(count_q).scalar() or 0
        rows = session.execute(
            q.order_by(NetworkService.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).scalars().all()

        return PaginatedResponse(
            items=[NetworkServiceRead.model_validate(r) for r in rows],
            total=total,
            page=page,
            page_size=page_size,
        )


# ---------------------------------------------------------------------------
# GET by ID
# ---------------------------------------------------------------------------

@router.get("/{service_id}", response_model=NetworkServiceRead)
async def get_service(
    service_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth_context),
):
    with get_session() as session:
        svc = session.execute(
            select(NetworkService).where(
                NetworkService.id == service_id,
                NetworkService.tenant_id == auth.tenant_id,
            )
        ).scalar_one_or_none()
        if not svc:
            raise HTTPException(status_code=404, detail="Network service not found")
        return NetworkServiceRead.model_validate(svc)


# ---------------------------------------------------------------------------
# UPDATE
# ---------------------------------------------------------------------------

@router.put("/{service_id}", response_model=NetworkServiceRead)
async def update_service(
    service_id: uuid.UUID,
    payload: NetworkServiceUpdate,
    auth: AuthContext = Depends(get_auth_context),
):
    with get_session() as session:
        svc = session.execute(
            select(NetworkService).where(
                NetworkService.id == service_id,
                NetworkService.tenant_id == auth.tenant_id,
            )
        ).scalar_one_or_none()
        if not svc:
            raise HTTPException(status_code=404, detail="Network service not found")

        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(svc, field, value)

        session.flush()
        session.refresh(svc)
        return NetworkServiceRead.model_validate(svc)


# ---------------------------------------------------------------------------
# SUSPEND / REINSTATE — individual service
# ---------------------------------------------------------------------------

@router.post("/{service_id}/suspend", response_model=NetworkServiceRead)
async def suspend_service(
    service_id: uuid.UUID,
    payload: ServiceSuspendRequest,
    auth: AuthContext = Depends(get_auth_context),
):
    """Suspend an individual network service (sets RADIUS to suspended)."""
    with get_session() as session:
        svc = session.execute(
            select(NetworkService).where(
                NetworkService.id == service_id,
                NetworkService.tenant_id == auth.tenant_id,
            )
        ).scalar_one_or_none()
        if not svc:
            raise HTTPException(status_code=404, detail="Network service not found")
        if svc.status == "suspended":
            raise HTTPException(status_code=400, detail="Service is already suspended")
        if svc.status == "terminated":
            raise HTTPException(status_code=400, detail="Cannot suspend a terminated service")

        svc.status = "suspended"
        svc.suspended_at = datetime.now(timezone.utc)

        # Also suspend RADIUS account
        radius = session.execute(
            select(RadiusAccount).where(RadiusAccount.service_id == service_id)
        ).scalar_one_or_none()
        if radius:
            radius.status = "suspended"

        session.flush()
        session.refresh(svc)
        logger.info("Suspended service %s reason=%s", service_id, payload.reason)
        return NetworkServiceRead.model_validate(svc)


@router.post("/{service_id}/reinstate", response_model=NetworkServiceRead)
async def reinstate_service(
    service_id: uuid.UUID,
    payload: ServiceReinstateRequest,
    auth: AuthContext = Depends(get_auth_context),
):
    """Reinstate a suspended network service."""
    with get_session() as session:
        svc = session.execute(
            select(NetworkService).where(
                NetworkService.id == service_id,
                NetworkService.tenant_id == auth.tenant_id,
            )
        ).scalar_one_or_none()
        if not svc:
            raise HTTPException(status_code=404, detail="Network service not found")
        if svc.status != "suspended":
            raise HTTPException(status_code=400, detail="Service is not suspended")

        svc.status = "active"
        svc.suspended_at = None

        # Reactivate RADIUS
        radius = session.execute(
            select(RadiusAccount).where(RadiusAccount.service_id == service_id)
        ).scalar_one_or_none()
        if radius:
            radius.status = "active"

        session.flush()
        session.refresh(svc)
        logger.info("Reinstated service %s reason=%s", service_id, payload.reason)
        return NetworkServiceRead.model_validate(svc)


# ---------------------------------------------------------------------------
# BULK SUSPEND / REINSTATE by customer — called by Billing service
# ---------------------------------------------------------------------------

@router.post("/suspend-by-customer")
async def suspend_all_customer_services(
    payload: BulkCustomerSuspendRequest,
    auth: AuthContext = Depends(get_auth_context),
):
    """Suspend ALL active services for a customer.

    Called by the Billing service when a customer's account is past due.
    """
    with get_session() as session:
        services = session.execute(
            select(NetworkService).where(
                NetworkService.tenant_id == auth.tenant_id,
                NetworkService.customer_id == payload.customer_id,
                NetworkService.status == "active",
            )
        ).scalars().all()

        now = datetime.now(timezone.utc)
        suspended_count = 0
        for svc in services:
            svc.status = "suspended"
            svc.suspended_at = now
            # Suspend RADIUS
            radius = session.execute(
                select(RadiusAccount).where(RadiusAccount.service_id == svc.id)
            ).scalar_one_or_none()
            if radius:
                radius.status = "suspended"
            suspended_count += 1

        logger.info(
            "Bulk suspended %d services for customer %s reason=%s",
            suspended_count, payload.customer_id, payload.reason,
        )
        return {
            "customer_id": str(payload.customer_id),
            "suspended_count": suspended_count,
            "reason": payload.reason,
        }


@router.post("/reinstate-by-customer")
async def reinstate_all_customer_services(
    payload: BulkCustomerReinstateRequest,
    auth: AuthContext = Depends(get_auth_context),
):
    """Reinstate ALL suspended services for a customer.

    Called by the Billing service after payment is received.
    """
    with get_session() as session:
        services = session.execute(
            select(NetworkService).where(
                NetworkService.tenant_id == auth.tenant_id,
                NetworkService.customer_id == payload.customer_id,
                NetworkService.status == "suspended",
            )
        ).scalars().all()

        reinstated_count = 0
        for svc in services:
            svc.status = "active"
            svc.suspended_at = None
            # Reactivate RADIUS
            radius = session.execute(
                select(RadiusAccount).where(RadiusAccount.service_id == svc.id)
            ).scalar_one_or_none()
            if radius:
                radius.status = "active"
            reinstated_count += 1

        logger.info(
            "Bulk reinstated %d services for customer %s reason=%s",
            reinstated_count, payload.customer_id, payload.reason,
        )
        return {
            "customer_id": str(payload.customer_id),
            "reinstated_count": reinstated_count,
            "reason": payload.reason,
        }


# ---------------------------------------------------------------------------
# SPEED CHANGE (upgrade / downgrade)
# ---------------------------------------------------------------------------

@router.post("/{service_id}/speed-change", response_model=NetworkServiceRead)
async def change_service_speed(
    service_id: uuid.UUID,
    payload: SpeedChangeRequest,
    auth: AuthContext = Depends(get_auth_context),
):
    """Change the speed profile for a network service and its RADIUS account."""
    with get_session() as session:
        svc = session.execute(
            select(NetworkService).where(
                NetworkService.id == service_id,
                NetworkService.tenant_id == auth.tenant_id,
            )
        ).scalar_one_or_none()
        if not svc:
            raise HTTPException(status_code=404, detail="Network service not found")
        if svc.status not in ("active", "provisioning"):
            raise HTTPException(status_code=400, detail="Speed change only allowed on active/provisioning services")

        old_down = svc.download_speed_mbps
        old_up = svc.upload_speed_mbps

        svc.download_speed_mbps = payload.download_speed_mbps
        svc.upload_speed_mbps = payload.upload_speed_mbps
        if payload.speed_profile_name:
            svc.speed_profile_name = payload.speed_profile_name

        # Update RADIUS profile
        radius = session.execute(
            select(RadiusAccount).where(RadiusAccount.service_id == service_id)
        ).scalar_one_or_none()
        if radius and payload.speed_profile_name:
            radius.profile_name = payload.speed_profile_name
            radius.mikrotik_rate_limit = f"{payload.download_speed_mbps}M/{payload.upload_speed_mbps}M"

        session.flush()
        session.refresh(svc)
        logger.info(
            "Speed change for service %s: %d/%d → %d/%d",
            service_id, old_down, old_up,
            payload.download_speed_mbps, payload.upload_speed_mbps,
        )
        return NetworkServiceRead.model_validate(svc)


# ---------------------------------------------------------------------------
# ACTIVATE (mark provisioning → active)
# ---------------------------------------------------------------------------

@router.post("/{service_id}/activate", response_model=NetworkServiceRead)
async def activate_service(
    service_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth_context),
):
    """Mark a service as active after FNO installation is complete."""
    with get_session() as session:
        svc = session.execute(
            select(NetworkService).where(
                NetworkService.id == service_id,
                NetworkService.tenant_id == auth.tenant_id,
            )
        ).scalar_one_or_none()
        if not svc:
            raise HTTPException(status_code=404, detail="Network service not found")
        if svc.status not in ("pending", "provisioning"):
            raise HTTPException(status_code=400, detail=f"Cannot activate a service in '{svc.status}' state")

        svc.status = "active"
        svc.activated_at = datetime.now(timezone.utc)

        session.flush()
        session.refresh(svc)
        logger.info("Activated service %s", service_id)
        return NetworkServiceRead.model_validate(svc)


# ---------------------------------------------------------------------------
# TERMINATE
# ---------------------------------------------------------------------------

@router.post("/{service_id}/terminate", response_model=NetworkServiceRead)
async def terminate_service(
    service_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth_context),
):
    """Permanently terminate a network service."""
    with get_session() as session:
        svc = session.execute(
            select(NetworkService).where(
                NetworkService.id == service_id,
                NetworkService.tenant_id == auth.tenant_id,
            )
        ).scalar_one_or_none()
        if not svc:
            raise HTTPException(status_code=404, detail="Network service not found")
        if svc.status == "terminated":
            raise HTTPException(status_code=400, detail="Service is already terminated")

        svc.status = "terminated"
        svc.terminated_at = datetime.now(timezone.utc)

        # Disable RADIUS
        radius = session.execute(
            select(RadiusAccount).where(RadiusAccount.service_id == service_id)
        ).scalar_one_or_none()
        if radius:
            radius.status = "disabled"

        session.flush()
        session.refresh(svc)
        logger.info("Terminated service %s", service_id)
        return NetworkServiceRead.model_validate(svc)
