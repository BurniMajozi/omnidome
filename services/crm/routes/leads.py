"""Lead Management routes — CRUD and conversion to customer."""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select

from services.common.auth import AuthContext, get_auth_context
from services.crm.database import generate_account_number, get_session
from services.crm.models import ActivityEvent, Customer, Lead
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
    ctx: AuthContext = Depends(get_auth_context),
):
    async with get_session() as session:
        lead = Lead(
            tenant_id=ctx.tenant_id,
            source=body.source,
            first_name=body.first_name,
            last_name=body.last_name,
            email=body.email,
            phone=body.phone,
            coverage_area=body.coverage_area,
            interested_package=body.interested_package,
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
    async with get_session() as session:
        stmt = select(Lead).where(Lead.tenant_id == ctx.tenant_id)

        if status_filter:
            stmt = stmt.where(Lead.status == status_filter)
        if source:
            stmt = stmt.where(Lead.source == source)
        if assigned_to:
            stmt = stmt.where(Lead.assigned_to == assigned_to)

        # Count total
        count_stmt = select(Lead.id).where(Lead.tenant_id == ctx.tenant_id)
        if status_filter:
            count_stmt = count_stmt.where(Lead.status == status_filter)
        if source:
            count_stmt = count_stmt.where(Lead.source == source)
        if assigned_to:
            count_stmt = count_stmt.where(Lead.assigned_to == assigned_to)

        total_result = await session.execute(select(Lead.id).select_from(Lead).where(Lead.tenant_id == ctx.tenant_id))
        total = len(total_result.scalars().all())

        items_result = await session.execute(
            stmt.order_by(Lead.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        items = items_result.scalars().all()

        pages = max(1, (total + page_size - 1) // page_size)

        return PaginatedResponse(
            items=[LeadRead.model_validate(l) for l in items],
            total=total,
            page=page,
            page_size=page_size,
            pages=pages,
        )


# ---------------------------------------------------------------------------
# PUT /leads/{id} — Update lead
# ---------------------------------------------------------------------------

@router.put("/{lead_id}", response_model=LeadRead)
async def update_lead(
    lead_id: uuid.UUID,
    body: LeadUpdate,
    ctx: AuthContext = Depends(get_auth_context),
):
    async with get_session() as session:
        result = await session.execute(
            select(Lead).where(Lead.id == lead_id, Lead.tenant_id == ctx.tenant_id)
        )
        lead = result.scalar_one_or_none()

        if not lead:
            raise HTTPException(status_code=404, detail="Lead not found")

        update_data = body.model_dump(exclude_unset=True)
        for field, value in update_data.items():
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
    ctx: AuthContext = Depends(get_auth_context),
):
    async with get_session() as session:
        result = await session.execute(
            select(Lead).where(Lead.id == lead_id, Lead.tenant_id == ctx.tenant_id)
        )
        lead = result.scalar_one_or_none()

        if not lead:
            raise HTTPException(status_code=404, detail="Lead not found")
        if lead.status == "converted":
            raise HTTPException(status_code=400, detail="Lead already converted")
        if lead.status == "lost":
            raise HTTPException(status_code=400, detail="Cannot convert a lost lead")

        # Create customer from lead
        customer = Customer(
            tenant_id=ctx.tenant_id,
            first_name=lead.first_name,
            last_name=lead.last_name,
            email=lead.email or "",
            phone=lead.phone,
            account_number=generate_account_number(ctx.tenant_id),
        )
        session.add(customer)
        await session.flush()

        # Update lead
        lead.status = "converted"
        lead.converted_customer_id = customer.id

        # Timeline event
        event = ActivityEvent(
            tenant_id=ctx.tenant_id,
            customer_id=customer.id,
            event_type="lead_conversion",
            summary=f"Converted from lead (source: {lead.source or 'unknown'})",
            details={"lead_id": str(lead.id)},
        )
        session.add(event)
        await session.flush()
        await session.refresh(customer)
        return customer
