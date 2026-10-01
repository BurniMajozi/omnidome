"""RADIUS account management routes.

Manages RADIUS credentials (radcheck/radusergroup) and live session
queries (radacct) for PPPoE/IPoE subscriber authentication.
"""

import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func
from starlette.concurrency import run_in_threadpool

from services.common import secretbox
from services.common.auth import AuthContext, get_auth_context
from services.network import radius_coa
from services.network.access import require_tier
from services.network.database import get_session
from services.network.models import RadiusAccount, NetworkService, NasClient
from services.network.schemas import (
    NasClientCreate,
    NasClientRead,
    PaginatedResponse,
    RadiusAccountCreate,
    RadiusAccountRead,
    RadiusAccountUpdate,
    RadiusSessionInfo,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/radius", tags=["RADIUS"])


def _encrypt_or_503(value: str) -> str:
    """Fail closed: without SECRETS_ENCRYPTION_KEY no credential is stored."""
    try:
        return secretbox.encrypt(value)
    except secretbox.SecretsUnavailable:
        logger.error("SECRETS_ENCRYPTION_KEY unavailable: refusing to store a RADIUS credential")
        raise HTTPException(status_code=503, detail="Secret storage is not configured")


# ---------------------------------------------------------------------------
# NAS clients (shared secret encrypted, never returned) -- admin tier (enforced in main.py)
# ---------------------------------------------------------------------------

@router.post("/nas", response_model=NasClientRead, status_code=status.HTTP_201_CREATED)
async def create_nas(payload: NasClientCreate, auth: AuthContext = Depends(get_auth_context)):
    enc = _encrypt_or_503(payload.shared_secret)
    with get_session() as session:
        dup = session.execute(select(NasClient).where(
            NasClient.tenant_id == auth.tenant_id, NasClient.ip_address == payload.ip_address)).scalar_one_or_none()
        if dup:
            raise HTTPException(status_code=409, detail="A NAS with this address already exists")
        nas = NasClient(tenant_id=auth.tenant_id, name=payload.name, ip_address=payload.ip_address,
                        shared_secret_enc=enc, coa_port=payload.coa_port)
        session.add(nas)
        session.flush()
        session.refresh(nas)
        return NasClientRead.model_validate(nas)


@router.get("/nas", response_model=list[NasClientRead])
async def list_nas(auth: AuthContext = Depends(get_auth_context)):
    with get_session() as session:
        rows = session.execute(select(NasClient).where(NasClient.tenant_id == auth.tenant_id)
                               .order_by(NasClient.created_at)).scalars().all()
        return [NasClientRead.model_validate(r) for r in rows]


@router.delete("/nas/{nas_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_nas(nas_id: uuid.UUID, auth: AuthContext = Depends(get_auth_context)):
    with get_session() as session:
        nas = session.execute(select(NasClient).where(
            NasClient.id == nas_id, NasClient.tenant_id == auth.tenant_id)).scalar_one_or_none()
        if not nas:
            raise HTTPException(status_code=404, detail="NAS not found")
        session.delete(nas)


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
            password_hash=secretbox.hash_password(payload.password),  # salted hash, never plaintext
            password_enc=_encrypt_or_503(payload.password),           # Fernet; RADIUS needs the cleartext
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
            new_pw = updates.pop("password")
            updates["password_enc"] = _encrypt_or_503(new_pw)
            updates["password_hash"] = secretbox.hash_password(new_pw)

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
    """Send a real RFC 5176 Disconnect-Request to the account's registered NAS (UDP 3799, NAS shared
    secret). Reports ACK / NAK / TIMEOUT honestly; never claims a disconnect without a verified ACK."""
    with get_session() as session:
        account = session.execute(
            select(RadiusAccount).where(
                RadiusAccount.id == account_id,
                RadiusAccount.tenant_id == auth.tenant_id,
            )
        ).scalar_one_or_none()
        if not account:
            raise HTTPException(status_code=404, detail="RADIUS account not found")
        if not account.nas_ip_address:
            raise HTTPException(status_code=409, detail="Account has no NAS address; cannot send a Disconnect-Request")
        nas = session.execute(select(NasClient).where(
            NasClient.tenant_id == auth.tenant_id, NasClient.ip_address == account.nas_ip_address)
        ).scalar_one_or_none()
        if not nas:
            raise HTTPException(status_code=409, detail="NAS is not registered for this tenant (POST /radius/nas first)")
        try:
            secret = secretbox.decrypt(nas.shared_secret_enc)
        except secretbox.SecretsUnavailable:
            raise HTTPException(status_code=503, detail="Secret storage is not configured")
        username, host, port = account.username, nas.ip_address, nas.coa_port

    result = await run_in_threadpool(
        radius_coa.send_disconnect, host, port, secret.encode(), username=username)
    logger.info("Disconnect-Request for %s to NAS %s: %s", username, host, result.outcome)
    body = {"username": username, "nas_ip_address": host, "result": result.outcome,
            "error_cause": result.error_cause}
    if result.outcome == "ACK":
        return {**body, "status": "DISCONNECTED", "message": "NAS acknowledged the Disconnect-Request"}
    if result.outcome == "NAK":
        raise HTTPException(status_code=409, detail={**body, "message": "NAS refused the Disconnect-Request (NAK)"})
    if result.outcome == "TIMEOUT":
        raise HTTPException(status_code=504, detail={**body, "message": "No reply from the NAS (timeout); session state unknown"})
    raise HTTPException(status_code=502, detail={**body, "message": "Invalid or unauthentic reply from the NAS"})


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
    session cache.  Not wired yet: returns an empty list (no invented data).
    """
    # No radacct source is wired to this service yet: report no sessions rather than invent one.
    logger.info("RADIUS session query for tenant %s: no accounting source configured", auth.tenant_id)
    return []
