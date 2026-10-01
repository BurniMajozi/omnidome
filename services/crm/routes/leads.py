"""Lead Management routes — CRUD and conversion to customer.

Lead statuses are UPPERCASE across the platform (the `leads` table is shared with the sales
service). Everything that writes, filters or compares a status goes through
services.crm.normalize, so legacy lowercase rows and mixed-case input behave identically.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from services.common.auth import AuthContext, get_auth_context
from services.crm.access import has_tier, require_write
from services.crm.database import generate_account_number, get_session
from services.crm.dedupe import find_duplicate_customer
from services.crm.models import ActivityEvent, Customer, Lead
from services.crm.normalize import (
    CLOSED_LEAD_STATUSES,
    CONVERTED_LEAD_STATUSES,
    LEAD_STATUSES,
    normalize_email,
    normalize_phone,
    normalize_status,
    status_key,
)
from services.crm.routes.customers import _public
from services.crm.schemas import (
    CustomerRead,
    LeadCreate,
    LeadRead,
    LeadUpdate,
    PaginatedResponse,
)

router = APIRouter(prefix="/leads", tags=["Leads"])


# ---------------------------------------------------------------------------
# POST /leads — Create lead
# ---------------------------------------------------------------------------

@router.post("", response_model=LeadRead, status_code=status.HTTP_201_CREATED)
async def create_lead(
    body: LeadCreate,
    ctx: AuthContext = Depends(require_write),
):
    async with get_session() as session:
        lead = Lead(
            tenant_id=ctx.tenant_id,
            source=body.source,
            first_name=body.first_name,
            last_name=body.last_name,
            email=normalize_email(body.email),
            phone=normalize_phone(body.phone) or (body.phone or None),
            coverage_area=body.coverage_area,
            interested_package=body.interested_package,
            status="NEW",
        )
        session.add(lead)
        await session.flush()
        await session.refresh(lead)
        return lead


# ---------------------------------------------------------------------------
# GET /leads — List leads with status filter and pagination
# ---------------------------------------------------------------------------

@router.get("", response_model=PaginatedResponse)
async def list_leads(
    ctx: AuthContext = Depends(get_auth_context),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: Optional[str] = Query(None, alias="status"),
    source: Optional[str] = Query(None),
    assigned_to: Optional[uuid.UUID] = Query(None),
):
    try:
        wanted = normalize_status(status_filter) if status_filter else None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    def apply_filters(stmt):
        stmt = stmt.where(Lead.tenant_id == ctx.tenant_id)
        if wanted:
            stmt = stmt.where(func.upper(func.trim(Lead.status)) == wanted)  # case-insensitive
        if source:
            stmt = stmt.where(Lead.source == source)
        if assigned_to:
            stmt = stmt.where(Lead.assigned_to == assigned_to)
        return stmt

    async with get_session() as session:
        # total honours exactly the same filters as the page of items
        total = (await session.execute(apply_filters(select(func.count(Lead.id))))).scalar() or 0

        items = (await session.execute(
            apply_filters(select(Lead))
            .order_by(Lead.created_at.desc(), Lead.id)  # id tiebreak: stable pages for bulk imports
            .offset((page - 1) * page_size)
            .limit(page_size)
        )).scalars().all()

        pages = max(1, (total + page_size - 1) // page_size)
        return PaginatedResponse(
            items=[LeadRead.model_validate(l) for l in items],
            total=total, page=page, page_size=page_size, pages=pages,
        )


# ---------------------------------------------------------------------------
# PUT /leads/{id} — Update lead
# ---------------------------------------------------------------------------

@router.put("/{lead_id}", response_model=LeadRead)
async def update_lead(
    lead_id: uuid.UUID,
    body: LeadUpdate,
    ctx: AuthContext = Depends(require_write),
):
    async with get_session() as session:
        lead = (await session.execute(
            select(Lead).where(Lead.id == lead_id, Lead.tenant_id == ctx.tenant_id)
        )).scalar_one_or_none()
        if not lead:
            raise HTTPException(status_code=404, detail="Lead not found")

        for field, value in body.model_dump(exclude_unset=True).items():
            setattr(lead, field, value)
        await session.flush()
        await session.refresh(lead)
        return lead


# ---------------------------------------------------------------------------
# POST /leads/{id}/convert — Convert lead to customer
# ---------------------------------------------------------------------------

@router.post("/{lead_id}/convert", response_model=CustomerRead, status_code=status.HTTP_201_CREATED)
async def convert_lead(
    lead_id: uuid.UUID,
    response: Response,
    merge: bool = Query(False, description="If the customer already exists, link the lead to it instead of 409"),
    ctx: AuthContext = Depends(require_write),
):
    async with get_session() as session:
        # lock the row so two concurrent conversions cannot both create a customer
        lead = (await session.execute(
            select(Lead).where(Lead.id == lead_id, Lead.tenant_id == ctx.tenant_id).with_for_update()
        )).scalar_one_or_none()
        if not lead:
            raise HTTPException(status_code=404, detail="Lead not found")

        is_admin = await has_tier(ctx, session, "admin")
        key = status_key(lead.status)
        email = normalize_email(lead.email)
        phone_norm = normalize_phone(lead.phone)

        if key in CONVERTED_LEAD_STATUSES or lead.converted_customer_id is not None:
            existing_id = lead.converted_customer_id
            if existing_id is None:  # marked converted by the sales service: find the customer if there is one
                match = await find_duplicate_customer(session, ctx.tenant_id, phone_norm, email)
                existing_id = match.id if match else None
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"message": "Lead already converted",
                        "customer_id": str(existing_id) if existing_id else None},
            )
        if key in CLOSED_LEAD_STATUSES:
            raise HTTPException(status_code=400, detail=f"Cannot convert a {key.lower()} lead")

        existing = await find_duplicate_customer(session, ctx.tenant_id, phone_norm, email)
        if existing is not None:
            if not merge:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={"message": "A customer with this phone number or e-mail already exists",
                            "existing_customer_id": str(existing.id)},
                )
            customer = existing
            response.status_code = status.HTTP_200_OK
        else:
            customer = Customer(
                tenant_id=ctx.tenant_id,
                first_name=lead.first_name,
                last_name=lead.last_name,
                email=email,  # NULL (not '') when the lead has none
                phone=lead.phone,
                phone_normalized=phone_norm,
                account_number=generate_account_number(ctx.tenant_id),
            )
            session.add(customer)
            try:
                async with session.begin_nested():
                    await session.flush()
            except IntegrityError:
                raced = await find_duplicate_customer(session, ctx.tenant_id, phone_norm, email)
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={"message": "A customer with this phone number or e-mail already exists",
                            "existing_customer_id": str(raced.id) if raced else None},
                )

        lead.status = "CONVERTED"
        lead.converted_customer_id = customer.id
        lead.converted_at = datetime.now(timezone.utc)

        session.add(ActivityEvent(
            tenant_id=ctx.tenant_id,
            customer_id=customer.id,
            event_type="lead_conversion",
            summary=f"Converted from lead (source: {lead.source or 'unknown'})",
            details={"lead_id": str(lead.id)},
        ))
        await session.flush()
        await session.refresh(customer)
        return _public(customer, is_admin)
