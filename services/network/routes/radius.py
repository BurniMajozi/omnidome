"""RADIUS account management routes.

Manages RADIUS credentials (radcheck/radusergroup) and live session
queries (radacct) for PPPoE/IPoE subscriber authentication.
"""

import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func

from services.common.auth import AuthContext, get_auth_context
from services.network.database import get_session
from services.network.models import RadiusAccount, NetworkService
from services.network.schemas import (
    PaginatedResponse,
    RadiusAccountCreate,
    RadiusAccountRead,
    RadiusAccountUpdate,
    RadiusSessionInfo,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/radius", tags=["RADIUS"])


# ---------------------------------------------------------------------------
# CREATE
# ---------------------------------------------------------------------------

@router.post("/accounts", response_model=RadiusAccountRead, status_code=status.HTTP_201_CREATED)
async def create_radius_account(
    payload: RadiusAccountCreate,
    auth: AuthContext = Depends(get_auth_context),
):
    """Provision a new RADIUS account linked to a network service."""
    with get_session() as session:
        # Verify service exists and belongs to tenant
        svc = session.execute(
            select(NetworkService).where(
                NetworkService.id == payload.service_id,
                NetworkService.tenant_id == auth.tenant_id,
            )
        ).scalar_one_or_none()
        if not svc:
            raise HTTPException(status_code=404, detail="Network service not found")

        # Check for duplicate username within tenant
        existing = session.execute(
            select(RadiusAccount).where(
                RadiusAccount.tenant_id == auth.tenant_id,
                RadiusAccount.username == payload.username,
            )
        ).scalar_one_or_none()
        if existing:
            raise HTTPException(status_code=409, detail="RADIUS username already exists for this tenant")

        # Check service doesn't already have a RADIUS account
        existing_for_svc = session.execute(
            select(RadiusAccount).where(
                RadiusAccount.service_id == payload.service_id,
            )
        ).scalar_one_or_none()
        if existing_for_svc:
            raise HTTPException(status_code=409, detail="Service already has a RADIUS account")

        account = RadiusAccount(
            tenant_id=auth.tenant_id,
            service_id=payload.service_id,
            username=payload.username,
            password_hash=payload.password,  # In production: hash with bcrypt / NT-Hash
            framing_protocol=payload.framing_protocol,
            profile_name=payload.profile_name,
            mikrotik_rate_limit=payload.mikrotik_rate_limit,
            nas_ip_address=payload.nas_ip_address,
            nas_port_id=payload.nas_port_id,
        )
        session.add(account)
        session.flush()
        session.refresh(account)
        logger.info("Created RADIUS account %s for service %s", account.username, payload.service_id)
        return RadiusAccountRead.model_validate(account)


# ---------------------------------------------------------------------------
# LIST
# ---------------------------------------------------------------------------

@router.get("/accounts", response_model=PaginatedResponse)
async def list_radius_accounts(
    auth: AuthContext = Depends(get_auth_context),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
):
    """List RADIUS accounts for the current tenant."""
    with get_session() as session:
        q = select(RadiusAccount).where(RadiusAccount.tenant_id == auth.tenant_id)
        count_q = select(func.count(RadiusAccount.id)).where(RadiusAccount.tenant_id == auth.tenant_id)

        if search:
            q = q.where(RadiusAccount.username.ilike(f"%{search}%"))
            count_q = count_q.where(RadiusAccount.username.ilike(f"%{search}%"))

        if status_filter:
            q = q.where(RadiusAccount.status == status_filter)
            count_q = count_q.where(RadiusAccount.status == status_filter)

        total = session.execute(count_q).scalar() or 0
        rows = session.execute(
            q.order_by(RadiusAccount.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).scalars().all()

        return PaginatedResponse(
            items=[RadiusAccountRead.model_validate(r) for r in rows],
            total=total,
            page=page,
            page_size=page_size,
        )


# ---------------------------------------------------------------------------
# GET by ID
# ---------------------------------------------------------------------------

@router.get("/accounts/{account_id}", response_model=RadiusAccountRead)
async def get_radius_account(
    account_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth_context),
):
    with get_session() as session:
        account = session.execute(
            select(RadiusAccount).where(
                RadiusAccount.id == account_id,
                RadiusAccount.tenant_id == auth.tenant_id,
            )
        ).scalar_one_or_none()
        if not account:
            raise HTTPException(status_code=404, detail="RADIUS account not found")
        return RadiusAccountRead.model_validate(account)


# ---------------------------------------------------------------------------
# UPDATE
# ---------------------------------------------------------------------------

@router.put("/accounts/{account_id}", response_model=RadiusAccountRead)
async def update_radius_account(
    account_id: uuid.UUID,
    payload: RadiusAccountUpdate,
    auth: AuthContext = Depends(get_auth_context),
):
    """Update RADIUS account (password, profile, status, etc.)."""
    with get_session() as session:
        account = session.execute(
            select(RadiusAccount).where(
                RadiusAccount.id == account_id,
                RadiusAccount.tenant_id == auth.tenant_id,
            )
        ).scalar_one_or_none()
        if not account:
            raise HTTPException(status_code=404, detail="RADIUS account not found")

        updates = payload.model_dump(exclude_unset=True)
        if "password" in updates:
            updates["password_hash"] = updates.pop("password")

        for field, value in updates.items():
            setattr(account, field, value)

        session.flush()
        session.refresh(account)
        logger.info("Updated RADIUS account %s", account.username)
        return RadiusAccountRead.model_validate(account)


# ---------------------------------------------------------------------------
# DISCONNECT session (CoA / PoD)
# ---------------------------------------------------------------------------

@router.post("/accounts/{account_id}/disconnect")
async def disconnect_radius_session(
    account_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth_context),
):
    """Send a RADIUS Disconnect-Request (Packet of Disconnect) for active sessions.

    In production this would send a CoA/PoD packet to the NAS via a RADIUS
    client library (e.g. pyrad).  Currently returns a stub response.
    """
    with get_session() as session:
        account = session.execute(
            select(RadiusAccount).where(
                RadiusAccount.id == account_id,
                RadiusAccount.tenant_id == auth.tenant_id,
            )
        ).scalar_one_or_none()
        if not account:
            raise HTTPException(status_code=404, detail="RADIUS account not found")

        logger.info(
            "Sending PoD for %s to NAS %s",
            account.username,
            account.nas_ip_address or "unknown",
        )
        # TODO: integrate pyrad to send actual PoD
        return {
            "username": account.username,
            "nas_ip_address": account.nas_ip_address,
            "status": "DISCONNECT_SENT",
            "message": "Packet of Disconnect sent to NAS",
        }


# ---------------------------------------------------------------------------
# ACTIVE SESSIONS (read from radacct)
# ---------------------------------------------------------------------------

@router.get("/sessions", response_model=list[RadiusSessionInfo])
async def get_active_sessions(
    auth: AuthContext = Depends(get_auth_context),
    username: Optional[str] = None,
):
    """Query radacct for live RADIUS sessions.

    In production this would query the FreeRADIUS radacct table or a
    session cache.  Currently returns illustrative stub data.
    """
    # TODO: query radacct table directly via raw SQL or dedicated view
    logger.info("Querying active RADIUS sessions for tenant %s", auth.tenant_id)
    sessions: list[dict] = []
    if username:
        sessions.append(
            {
                "username": username,
                "nas_ip_address": "154.22.8.5",
                "framed_ip_address": "100.64.1.12",
                "session_id": "sess-001",
                "uptime_seconds": 51720,
                "input_octets": 4_523_000,
                "output_octets": 12_500_000,
                "calling_station_id": "AA:BB:CC:DD:EE:FF",
            }
        )
    return [RadiusSessionInfo(**s) for s in sessions]
