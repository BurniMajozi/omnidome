"""Company (B2B Account) Management routes — CRUD, corporate member listing."""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select

from services.common.auth import AuthContext, get_auth_context
from services.crm.database import get_session
from services.crm.models import Company, Customer
from services.crm.schemas import (
    CompanyCreate,
    CompanyRead,
    CompanyUpdate,
    CustomerRead,
    PaginatedResponse,
)

router = APIRouter(prefix="/companies", tags=["Companies"])


# ---------------------------------------------------------------------------
# POST /companies — Create company
# ---------------------------------------------------------------------------

@router.post("", response_model=CompanyRead, status_code=status.HTTP_201_CREATED)
async def create_company(
    body: CompanyCreate,
    ctx: AuthContext = Depends(get_auth_context),
):
    async with get_session() as session:
        company = Company(
            tenant_id=ctx.tenant_id,
            name=body.name,
            registration_number=body.registration_number,
            tax_id=body.tax_id,
            industry=body.industry,
            contact_person=body.contact_person,
            email=body.email,
            phone=body.phone,
            address=body.address,
            billing_email=body.billing_email,
            payment_terms=body.payment_terms or "Net 30",
            credit_limit_zar=body.credit_limit_zar,
            notes=body.notes,
        )
        session.add(company)
        await session.flush()
        await session.refresh(company)

        record = CompanyRead.model_validate(company)
        record.members_count = 0
        return record


# ---------------------------------------------------------------------------
# GET /companies — List companies with pagination, search, and member counts
# ---------------------------------------------------------------------------

@router.get("", response_model=PaginatedResponse)
async def list_companies(
    ctx: AuthContext = Depends(get_auth_context),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None, description="Search company name, industry, registration, email"),
    is_active: Optional[bool] = Query(None),
):
    async with get_session() as session:
        stmt = select(Company).where(Company.tenant_id == ctx.tenant_id)

        if is_active is not None:
            stmt = stmt.where(Company.is_active == is_active)
        if search:
            term = f"%{search}%"
            stmt = stmt.where(
                or_(
                    Company.name.ilike(term),
                    Company.industry.ilike(term),
                    Company.registration_number.ilike(term),
                    Company.email.ilike(term),
                    Company.contact_person.ilike(term),
                )
            )

        # Count total
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total_result = await session.execute(count_stmt)
        total = total_result.scalar_one()

        # Fetch page
        stmt = (
            stmt.order_by(Company.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await session.execute(stmt)
        companies = result.scalars().all()

        # Fetch member counts
        company_ids = [c.id for c in companies]
        member_counts: dict[uuid.UUID, int] = {}
        if company_ids:
            counts_stmt = (
                select(Customer.company_id, func.count(Customer.id))
                .where(Customer.company_id.in_(company_ids))
                .group_by(Customer.company_id)
            )
            count_rows = await session.execute(counts_stmt)
            for cid, cnt in count_rows.all():
                if cid:
                    member_counts[cid] = cnt

    pages = max(1, (total + page_size - 1) // page_size)

    items = []
    for c in companies:
        record = CompanyRead.model_validate(c)
        record.members_count = member_counts.get(c.id, 0)
        items.append(record.model_dump(mode="json"))

    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


# ---------------------------------------------------------------------------
# GET /companies/{id} — Company detail with members
# ---------------------------------------------------------------------------

@router.get("/{company_id}")
async def get_company(
    company_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    async with get_session() as session:
        result = await session.execute(
            select(Company).where(Company.id == company_id, Company.tenant_id == ctx.tenant_id)
        )
        company = result.scalar_one_or_none()
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        # Fetch member customers
        members_stmt = select(Customer).where(Customer.company_id == company_id, Customer.tenant_id == ctx.tenant_id)
        members_result = await session.execute(members_stmt)
        members = members_result.scalars().all()

        record = CompanyRead.model_validate(company).model_dump(mode="json")
        record["members_count"] = len(members)
        record["members"] = [CustomerRead.model_validate(m).model_dump(mode="json") for m in members]
        return record


# ---------------------------------------------------------------------------
# PUT /companies/{id} — Update company
# ---------------------------------------------------------------------------

@router.put("/{company_id}", response_model=CompanyRead)
async def update_company(
    company_id: uuid.UUID,
    body: CompanyUpdate,
    ctx: AuthContext = Depends(get_auth_context),
):
    async with get_session() as session:
        result = await session.execute(
            select(Company).where(Company.id == company_id, Company.tenant_id == ctx.tenant_id)
        )
        company = result.scalar_one_or_none()
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        update_data = body.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(company, field, value)

        await session.flush()
        await session.refresh(company)

        # Count members
        cnt_stmt = select(func.count(Customer.id)).where(Customer.company_id == company_id)
        cnt_res = await session.execute(cnt_stmt)
        members_count = cnt_res.scalar_one()

        record = CompanyRead.model_validate(company)
        record.members_count = members_count
        return record
