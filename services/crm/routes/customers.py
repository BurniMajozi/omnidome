"""Customer Management routes — CRUD, 360 view, timeline."""

import os
import uuid
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_

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


# ---------------------------------------------------------------------------
# POST /customers — Create customer
# ---------------------------------------------------------------------------

@router.post("", response_model=CustomerRead, status_code=status.HTTP_201_CREATED)
def create_customer(
    body: CustomerCreate,
    ctx: AuthContext = Depends(get_auth_context),
):
    with get_session() as session:
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
        session.flush()

        # Record timeline event
        event = ActivityEvent(
            tenant_id=ctx.tenant_id,
            customer_id=customer.id,
            event_type="signup",
            summary=f"Customer {body.first_name} {body.last_name} created",
        )
        session.add(event)
        session.flush()
        session.refresh(customer)
        return customer


# ---------------------------------------------------------------------------
# GET /customers — List / search with pagination & full-text search
# ---------------------------------------------------------------------------

@router.get("", response_model=PaginatedResponse)
def list_customers(
    ctx: AuthContext = Depends(get_auth_context),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None, description="Full-text search across name, email, phone, account number"),
    status_filter: Optional[str] = Query(None, alias="status"),
    province: Optional[str] = Query(None),
):
    with get_session() as session:
        query = session.query(Customer).filter(Customer.tenant_id == ctx.tenant_id)

        if status_filter:
            query = query.filter(Customer.status == status_filter)
        if province:
            query = query.filter(Customer.province == province)
        if search:
            term = f"%{search}%"
            query = query.filter(
                or_(
                    Customer.first_name.ilike(term),
                    Customer.last_name.ilike(term),
                    Customer.email.ilike(term),
                    Customer.phone.ilike(term),
                    Customer.account_number.ilike(term),
                )
            )

        total = query.count()
        pages = max(1, (total + page_size - 1) // page_size)
        items = (
            query.order_by(Customer.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

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
    with get_session() as session:
        customer = (
            session.query(Customer)
            .filter(Customer.id == customer_id, Customer.tenant_id == ctx.tenant_id)
            .first()
        )
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")

        tags = (
            session.query(CustomerTag)
            .filter(CustomerTag.customer_id == customer_id, CustomerTag.tenant_id == ctx.tenant_id)
            .all()
        )
        notes_count = (
            session.query(func.count(CustomerNote.id))
            .filter(CustomerNote.customer_id == customer_id, CustomerNote.tenant_id == ctx.tenant_id)
            .scalar()
        ) or 0

        # Build 360 base
        result = Customer360.model_validate(customer)
        result.tags = [t.tag for t in tags]
        result.notes_count = notes_count

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

    result.billing = billing_data
    result.support = support_data
    result.network = network_data
    result.services = network_data  # alias

    return result


# ---------------------------------------------------------------------------
# PUT /customers/{id} — Update customer
# ---------------------------------------------------------------------------

@router.put("/{customer_id}", response_model=CustomerRead)
def update_customer(
    customer_id: uuid.UUID,
    body: CustomerUpdate,
    ctx: AuthContext = Depends(get_auth_context),
):
    with get_session() as session:
        customer = (
            session.query(Customer)
            .filter(Customer.id == customer_id, Customer.tenant_id == ctx.tenant_id)
            .first()
        )
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")

        update_data = body.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(customer, field, value)
        session.flush()
        session.refresh(customer)
        return customer


# ---------------------------------------------------------------------------
# GET /customers/{id}/timeline — Activity timeline
# ---------------------------------------------------------------------------

@router.get("/{customer_id}/timeline", response_model=list[TimelineEvent])
def get_customer_timeline(
    customer_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    limit: int = Query(50, ge=1, le=200),
):
    with get_session() as session:
        # Verify customer belongs to tenant
        exists = (
            session.query(Customer.id)
            .filter(Customer.id == customer_id, Customer.tenant_id == ctx.tenant_id)
            .first()
        )
        if not exists:
            raise HTTPException(status_code=404, detail="Customer not found")

        events = (
            session.query(ActivityEvent)
            .filter(
                ActivityEvent.customer_id == customer_id,
                ActivityEvent.tenant_id == ctx.tenant_id,
            )
            .order_by(ActivityEvent.created_at.desc())
            .limit(limit)
            .all()
        )
        return [TimelineEvent.model_validate(e) for e in events]
