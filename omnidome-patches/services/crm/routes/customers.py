"""Customer Management routes — CRUD, 360 view, timeline."""

import os
import uuid
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select

from services.common.auth import AuthContext, get_auth_context
from services.crm.database import generate_account_number, get_session
from services.crm.models import ActivityEvent, Customer, CustomerNote, CustomerTag
from services.crm.schemas import (
    Customer360,
    CustomerCreate,
    CustomerRead,
    CustomerUpdate,
    PaginatedResponse,
    TimelineEvent,
)

router = APIRouter(prefix="/customers", tags=["Customers"])

# Internal service URLs (Docker Compose service names)
BILLING_URL = os.getenv("BILLING_SERVICE_URL", "http://billing:8003")
SUPPORT_URL = os.getenv("SUPPORT_SERVICE_URL", "http://support:8008")
NETWORK_URL = os.getenv("NETWORK_SERVICE_URL", "http://network:8005")
JOURNEY_ENGINE_URL = os.getenv("JOURNEY_ENGINE_SERVICE_URL", "http://journey_engine:8017")


async def _sync_to_journey_engine(customer, ctx: AuthContext) -> None:
    """Push a customer snapshot to the Journey Engine for retention analysis.

    Fire-and-forget: failures are logged but must not block the CRM operation.
    """
    snapshot = {
        "customer_id": str(customer.id),
        "tenant_id": str(ctx.tenant_id),
        "first_name": customer.first_name,
        "last_name": customer.last_name,
        "email": customer.email,
        "phone": customer.phone,
        "account_number": customer.account_number,
        "status": customer.status,
        "province": customer.province,
        "rica_verified": customer.rica_verified,
    }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(
                f"{JOURNEY_ENGINE_URL}/customers/snapshot",
                json=snapshot,
                headers={
                    "X-User-Id": str(ctx.user_id),
                    "X-Tenant-Id": str(ctx.tenant_id),
                },
            )
    except Exception:
        pass  # non-blocking: CRM operation must succeed regardless


# ---------------------------------------------------------------------------
# POST /customers — Create customer
# ---------------------------------------------------------------------------

@router.post("", response_model=CustomerRead, status_code=status.HTTP_201_CREATED)
async def create_customer(
    body: CustomerCreate,
    ctx: AuthContext = Depends(get_auth_context),
):
    async with get_session() as session:
        customer = Customer(
            tenant_id=ctx.tenant_id,
            first_name=body.first_name,
            last_name=body.last_name,
            email=body.email,
            phone=body.phone,
            id_number=body.id_number,
            address=body.address,
            province=body.province,
            account_number=generate_account_number(ctx.tenant_id),
        )
        session.add(customer)
        await session.flush()

        # Record timeline event
        event = ActivityEvent(
            tenant_id=ctx.tenant_id,
            customer_id=customer.id,
            event_type="signup",
            summary=f"Customer {body.first_name} {body.last_name} created",
        )
        session.add(event)
        await session.flush()
        await session.refresh(customer)

    # Sync to Journey Engine (non-blocking, fire-and-forget)
    await _sync_to_journey_engine(customer, ctx)

    return customer


# ---------------------------------------------------------------------------
# GET /customers — List / search with pagination & full-text search
# ---------------------------------------------------------------------------

@router.get("", response_model=PaginatedResponse)
async def list_customers(
    ctx: AuthContext = Depends(get_auth_context),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None, description="Full-text search across name, email, phone, account number"),
    status_filter: Optional[str] = Query(None, alias="status"),
    province: Optional[str] = Query(None),
):
    async with get_session() as session:
        stmt = select(Customer).where(Customer.tenant_id == ctx.tenant_id)

        if status_filter:
            stmt = stmt.where(Customer.status == status_filter)
        if province:
            stmt = stmt.where(Customer.province == province)
        if search:
            term = f"%{search}%"
            stmt = stmt.where(
                or_(
                    Customer.first_name.ilike(term),
                    Customer.last_name.ilike(term),
                    Customer.email.ilike(term),
                    Customer.phone.ilike(term),
                    Customer.account_number.ilike(term),
                )
            )

        # Count total
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total_result = await session.execute(count_stmt)
        total = total_result.scalar_one()

        # Fetch paginated items
        stmt = (
            stmt.order_by(Customer.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await session.execute(stmt)
        items = result.scalars().all()

    pages = max(1, (total + page_size - 1) // page_size)

    return PaginatedResponse(
        items=[CustomerRead.model_validate(c) for c in items],
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


# ---------------------------------------------------------------------------
# GET /customers/{id} — Customer 360 view
# ---------------------------------------------------------------------------

def _forward_headers(ctx: AuthContext) -> dict:
    return {
        "X-User-Id": str(ctx.user_id),
        "X-Tenant-Id": str(ctx.tenant_id),
    }


async def _fetch_service_data(url: str, headers: dict) -> list:
    """Fetch data from a sibling service; return empty list on failure."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                return data if isinstance(data, list) else data.get("items", [])
    except Exception:
        pass
    return []


@router.get("/{customer_id}", response_model=Customer360)
async def get_customer_360(
    customer_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    async with get_session() as session:
        result = await session.execute(
            select(Customer).where(
                Customer.id == customer_id,
                Customer.tenant_id == ctx.tenant_id,
            )
        )
        customer = result.scalar_one_or_none()

        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")

        # Fetch tags
        tags_result = await session.execute(
            select(CustomerTag).where(
                CustomerTag.customer_id == customer_id,
                CustomerTag.tenant_id == ctx.tenant_id,
            )
        )
        tags = tags_result.scalars().all()

        # Count notes
        notes_count_result = await session.execute(
            select(func.count(CustomerNote.id)).where(
                CustomerNote.customer_id == customer_id,
                CustomerNote.tenant_id == ctx.tenant_id,
            )
        )
        notes_count = notes_count_result.scalar_one() or 0

        # Build 360 base
        view = Customer360.model_validate(customer)
        view.tags = [t.tag for t in tags]
        view.notes_count = notes_count

    # Aggregate cross-service data (best-effort, non-blocking)
    headers = _forward_headers(ctx)
    cid = str(customer_id)

    billing_data, support_data, network_data = [], [], []
    try:
        billing_data = await _fetch_service_data(
            f"{BILLING_URL}/invoices?customer_id={cid}", headers
        )
    except Exception:
        pass
    try:
        support_data = await _fetch_service_data(
            f"{SUPPORT_URL}/tickets?customer_id={cid}", headers
        )
    except Exception:
        pass
    try:
        network_data = await _fetch_service_data(
            f"{NETWORK_URL}/services?customer_id={cid}", headers
        )
    except Exception:
        pass

    view.billing = billing_data
    view.support = support_data
    view.network = network_data
    view.services = network_data  # alias

    return view


# ---------------------------------------------------------------------------
# PUT /customers/{id} — Update customer
# ---------------------------------------------------------------------------

@router.put("/{customer_id}", response_model=CustomerRead)
async def update_customer(
    customer_id: uuid.UUID,
    body: CustomerUpdate,
    ctx: AuthContext = Depends(get_auth_context),
):
    async with get_session() as session:
        result = await session.execute(
            select(Customer).where(
                Customer.id == customer_id,
                Customer.tenant_id == ctx.tenant_id,
            )
        )
        customer = result.scalar_one_or_none()

        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")

        update_data = body.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(customer, field, value)
        await session.flush()
        await session.refresh(customer)

    # Sync to Journey Engine (non-blocking, fire-and-forget)
    await _sync_to_journey_engine(customer, ctx)

    return customer


# ---------------------------------------------------------------------------
# GET /customers/{id}/timeline — Activity timeline
# ---------------------------------------------------------------------------

@router.get("/{customer_id}/timeline", response_model=list[TimelineEvent])
async def get_customer_timeline(
    customer_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    limit: int = Query(50, ge=1, le=200),
):
    async with get_session() as session:
        # Verify customer belongs to tenant
        exists_result = await session.execute(
            select(Customer.id).where(
                Customer.id == customer_id,
                Customer.tenant_id == ctx.tenant_id,
            )
        )
        exists = exists_result.scalar_one_or_none()

        if not exists:
            raise HTTPException(status_code=404, detail="Customer not found")

        events_result = await session.execute(
            select(ActivityEvent).where(
                ActivityEvent.customer_id == customer_id,
                ActivityEvent.tenant_id == ctx.tenant_id,
            )
            .order_by(ActivityEvent.created_at.desc())
            .limit(limit)
        )
        events = events_result.scalars().all()

    return [TimelineEvent.model_validate(e) for e in events]
