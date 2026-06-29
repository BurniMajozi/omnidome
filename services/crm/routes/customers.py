"""Customer Management routes — CRUD, 360 view, timeline."""

import logging
import os
import uuid
from datetime import datetime
from typing import Optional

from services.common.http_client import service_get
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select

from services.common.auth import AuthContext, get_auth_context
from services.crm.database import generate_account_number, get_session
from services.crm.models import ActivityEvent, Customer, CustomerNote, CustomerTag
from services.lifecycle.models import CustomerLifecycle
from services.crm.schemas import (
    Customer360,
    CustomerCreate,
    CustomerRead,
    CustomerUpdate,
    PaginatedResponse,
    TimelineEvent,
)

router = APIRouter(prefix="/customers", tags=["Customers"])
logger = logging.getLogger("crm.customers")

# Internal service URLs (Docker Compose service names)
LIFECYCLE_URL = os.getenv("LIFECYCLE_SERVICE_URL", "http://lifecycle:8018")
JOURNEY_ENGINE_URL = os.getenv("JOURNEY_ENGINE_SERVICE_URL", "http://journey_engine:8017")


# ---------------------------------------------------------------------------
# CRM → Journey Engine Sync
# ---------------------------------------------------------------------------

async def _sync_customer_to_journey_engine(
    session,
    customer: Customer,
    source_event: str = "status_change",
):
    """Push customer snapshot to journey engine for cancel-flow matching.
    Non-blocking: sync failures must not break CRM operations."""
    try:
        # Gather enriched snapshot data
        notes_result = await session.execute(
            select(func.count(CustomerNote.id)).where(CustomerNote.customer_id == customer.id)
        )
        notes_count = notes_result.scalar() or 0

        tags_result = await session.execute(
            select(CustomerTag.tag).where(CustomerTag.customer_id == customer.id)
        )
        tags = [row[0] for row in tags_result.all()]

        tenure_days = 0
        if customer.created_at:
            tenure_days = (datetime.utcnow() - customer.created_at.replace(tzinfo=None)).days

        snapshot_data = {
            "account_number": customer.account_number,
            "email": customer.email,
            "phone": customer.phone,
            "first_name": customer.first_name,
            "last_name": customer.last_name,
            "status": customer.status,
            "region": customer.province,
            "tenure_days": tenure_days,
            "notes_count": notes_count,
            "tags": tags,
            "id_number": customer.id_number,
        }

        from services.common.http_client import service_post as _svc_post
        await _svc_post(
            "journey_engine",
            "/customers/snapshot",
            json={
                "customer_id": str(customer.id),
                "tenant_id": str(customer.tenant_id),
                "account_number": customer.account_number,
                "snapshot_data": snapshot_data,
                "source_event": source_event,
            },
            tenant_id=customer.tenant_id,
        )
    except Exception:
        pass  # non-blocking


def _detect_sync_event(body: CustomerUpdate, existing: Customer) -> Optional[str]:
    """Detect if the update warrants a sync to journey engine. Returns source_event or None."""
    # Status change → churn risk signal
    if body.status is not None and body.status != existing.status:
        if body.status in ("churned", "suspended"):
            return "churn_risk"
        return "status_change"
    return None


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

        # Sync new customer to journey engine
        await _sync_customer_to_journey_engine(session, customer, source_event="signup")

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

        lifecycle_by_customer: dict[uuid.UUID, dict] = {}
        if items:
            lifecycle_rows = await session.execute(
                select(CustomerLifecycle.customer_id, CustomerLifecycle.health_score, CustomerLifecycle.monthly_recurring_revenue)
                .where(CustomerLifecycle.customer_id.in_([c.id for c in items]))
            )
            for customer_id, health_score, mrr in lifecycle_rows.all():
                lifecycle_by_customer[customer_id] = {"health_score": health_score, "mrr": float(mrr or 0)}

    pages = max(1, (total + page_size - 1) // page_size)

    enriched_items = []
    for c in items:
        record = CustomerRead.model_validate(c).model_dump(mode="json")
        lifecycle = lifecycle_by_customer.get(c.id, {})
        mrr = lifecycle.get("mrr", 0)
        health_score = lifecycle.get("health_score")
        record["mrr"] = mrr
        record["customer_type"] = "Enterprise" if mrr >= 2000 else "SMB" if mrr >= 500 else "Residential"
        record["health"] = (
            "Excellent" if health_score is not None and health_score >= 80
            else "Good" if health_score is not None and health_score >= 60
            else "At Risk" if health_score is not None and health_score >= 30
            else "Unknown" if health_score is None
            else "Critical"
        )
        enriched_items.append(record)

    return PaginatedResponse(
        items=enriched_items,
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


async def _fetch_service_data(service_name: str, path: str, ctx) -> list:
    """Fetch data from a sibling service via the resilient HTTP client."""
    try:
        result = await service_get(
            service_name,
            path,
            tenant_id=ctx.tenant_id,
            user_id=ctx.user_id,
            timeout=5.0,
        )
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            return result.get("items", [])
        return []
    except Exception as exc:
        logger.warning("Cross-service call failed: %s %s — %s", service_name, path, exc)
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

    # Aggregate cross-service data (resilient — circuit breaker + retry)
    cid = str(customer_id)
    billing_data = await _fetch_service_data("billing", f"/invoices?customer_id={cid}", ctx)
    support_data = await _fetch_service_data("support", f"/tickets?customer_id={cid}", ctx)
    network_data = await _fetch_service_data("network", f"/services?customer_id={cid}", ctx)

    view.billing = billing_data
    view.support = support_data
    view.network = network_data
    view.services = network_data  # alias

    # Lifecycle panel (best-effort, non-blocking)
    try:
        lifecycle_current = await _fetch_service_data(
            "lifecycle", f"/lifecycle/customers/{cid}/current", ctx
        )
        lifecycle_history = await _fetch_service_data(
            "lifecycle", f"/lifecycle/customers/{cid}/history?limit=20", ctx
        )
        # Normalize: _fetch_service_data may return list or dict
        if isinstance(lifecycle_current, list) and lifecycle_current:
            lifecycle_current = lifecycle_current[0]
        view.lifecycle_data = {
            "current_stage": lifecycle_current.get("current_stage") if isinstance(lifecycle_current, dict) else None,
            "health_score": lifecycle_current.get("health_score") if isinstance(lifecycle_current, dict) else None,
            "churn_probability": lifecycle_current.get("churn_probability") if isinstance(lifecycle_current, dict) else None,
            "history": lifecycle_history if isinstance(lifecycle_history, list) else [],
        }
    except Exception:
        pass  # Don't fail the 360 if lifecycle is down

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

        # Auto-sync to journey engine on status changes
        sync_event = _detect_sync_event(body, customer)
        if sync_event:
            await _sync_customer_to_journey_engine(session, customer, source_event=sync_event)

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
