"""Customer Management routes — CRUD, 360 view, timeline."""

import asyncio
import logging
import os
import uuid
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError

from services.common.auth import AuthContext, get_auth_context
from services.common.http_client import service_get
from services.crm.access import has_tier, redact_customer, require_write
from services.crm.database import generate_account_number, get_session
from services.crm.dedupe import find_duplicate_customer, merge_missing_fields
from services.crm.models import ActivityEvent, Customer, CustomerNote, CustomerTag
from services.crm.normalize import normalize_email, normalize_phone
from services.crm.schemas import (
    Customer360,
    CustomerCreate,
    CustomerRead,
    CustomerUpdate,
    PaginatedResponse,
    TimelineEvent,
)
from services.lifecycle.models import CustomerLifecycle

router = APIRouter(prefix="/customers", tags=["Customers"])
logger = logging.getLogger("crm.customers")

# Internal service URLs (Docker Compose service names)
LIFECYCLE_URL = os.getenv("LIFECYCLE_SERVICE_URL", "http://lifecycle:8018")
JOURNEY_ENGINE_URL = os.getenv("JOURNEY_ENGINE_SERVICE_URL", "http://journey_engine:8017")

# Each upstream call of the 360 view is bounded so one slow service cannot stall the page.
UPSTREAM_TIMEOUT_SECONDS = float(os.getenv("CRM_UPSTREAM_TIMEOUT_SECONDS", "2"))


def _public(customer: Customer, is_admin: bool) -> dict:
    """Customer as a JSON-ready dict, with ID numbers masked unless the viewer is an admin."""
    return redact_customer(CustomerRead.model_validate(customer).model_dump(mode="json"), is_admin)


def _duplicate_409(existing: Customer) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "message": "A customer with this phone number or e-mail already exists",
            "existing_customer_id": str(existing.id),
        },
    )


# ---------------------------------------------------------------------------
# CRM → Journey Engine Sync
# ---------------------------------------------------------------------------

async def _sync_customer_to_journey_engine(
    session,
    customer: Customer,
    source_event: str = "status_change",
):
    """Push a customer snapshot to the journey engine for cancel-flow matching.

    Non-blocking: a sync failure never breaks the CRM operation, but it is logged with context.
    The snapshot carries no national ID number: the journey engine matches on the customer id.
    """
    try:
        notes_count = (await session.execute(
            select(func.count(CustomerNote.id)).where(CustomerNote.customer_id == customer.id)
        )).scalar() or 0
        tags = [row[0] for row in (await session.execute(
            select(CustomerTag.tag).where(CustomerTag.customer_id == customer.id)
        )).all()]

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
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "journey-engine sync failed (event=%s customer=%s tenant=%s): %s: %s",
            source_event, customer.id, customer.tenant_id, type(exc).__name__, exc,
        )


def _detect_sync_event(body: CustomerUpdate, old_status: Optional[str]) -> Optional[str]:
    """Does this update warrant a journey-engine sync? Returns source_event or None.

    `old_status` MUST be captured before the update is applied to the row.
    """
    if body.status is not None and body.status != old_status:
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
    merge: bool = Query(False, description="On a duplicate, fill the existing customer's empty fields instead of 409"),
    ctx: AuthContext = Depends(require_write),
):
    email = normalize_email(body.email)
    phone_norm = normalize_phone(body.phone)
    async with get_session() as session:
        is_admin = await has_tier(ctx, session, "admin")
        existing = await find_duplicate_customer(session, ctx.tenant_id, phone_norm, email)
        if existing is not None:
            if not merge:
                raise _duplicate_409(existing)
            merge_missing_fields(existing, {
                "phone": body.phone, "phone_normalized": phone_norm, "id_number": body.id_number,
                "address": body.address, "province": body.province, "email": email,
            })
            await session.flush()
            await session.refresh(existing)
            return _public(existing, is_admin)

        customer = Customer(
            tenant_id=ctx.tenant_id,
            first_name=body.first_name,
            last_name=body.last_name,
            email=email,
            phone=body.phone,
            phone_normalized=phone_norm,
            id_number=body.id_number,
            address=body.address,
            province=body.province,
            account_number=generate_account_number(ctx.tenant_id),
        )
        session.add(customer)
        try:
            async with session.begin_nested():
                await session.flush()
        except IntegrityError:
            # lost a race against a concurrent create: the unique indexes are the final arbiter
            raced = await find_duplicate_customer(session, ctx.tenant_id, phone_norm, email)
            if raced is None:
                raise
            raise _duplicate_409(raced)

        session.add(ActivityEvent(
            tenant_id=ctx.tenant_id,
            customer_id=customer.id,
            event_type="signup",
            summary=f"Customer {body.first_name} {body.last_name} created",
        ))
        await session.flush()
        await session.refresh(customer)

        await _sync_customer_to_journey_engine(session, customer, source_event="signup")
        return _public(customer, is_admin)


# ---------------------------------------------------------------------------
# GET /customers — List / search with pagination & full-text search
# ---------------------------------------------------------------------------

def _like_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@router.get("", response_model=PaginatedResponse)
async def list_customers(
    ctx: AuthContext = Depends(get_auth_context),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None, max_length=100, description="Search name, email, phone, account number"),
    status_filter: Optional[str] = Query(None, alias="status"),
    province: Optional[str] = Query(None),
):
    async with get_session() as session:
        is_admin = await has_tier(ctx, session, "admin")
        stmt = select(Customer).where(Customer.tenant_id == ctx.tenant_id)

        if status_filter:
            stmt = stmt.where(Customer.status == status_filter.strip().lower())
        if province:
            stmt = stmt.where(Customer.province == province)
        if search:
            term = f"%{_like_escape(search)}%"
            stmt = stmt.where(
                or_(
                    Customer.first_name.ilike(term, escape="\\"),
                    Customer.last_name.ilike(term, escape="\\"),
                    Customer.email.ilike(term, escape="\\"),
                    Customer.phone.ilike(term, escape="\\"),
                    Customer.account_number.ilike(term, escape="\\"),
                )
            )

        total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()

        # `id` tiebreak: bulk imports share created_at, which would repeat/skip rows across pages
        stmt = (
            stmt.order_by(Customer.created_at.desc(), Customer.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        items = (await session.execute(stmt)).scalars().all()

        lifecycle_by_customer: dict[uuid.UUID, dict] = {}
        if items:
            try:
                async with session.begin_nested():  # lifecycle table belongs to another service
                    lifecycle_rows = await session.execute(
                        select(CustomerLifecycle.customer_id, CustomerLifecycle.health_score,
                               CustomerLifecycle.monthly_recurring_revenue)
                        .where(CustomerLifecycle.customer_id.in_([c.id for c in items]),
                               CustomerLifecycle.tenant_id == ctx.tenant_id)
                    )
                    for customer_id, health_score, mrr in lifecycle_rows.all():
                        lifecycle_by_customer[customer_id] = {"health_score": health_score, "mrr": float(mrr or 0)}
            except Exception as exc:  # noqa: BLE001 - enrichment is optional
                logger.warning("customer list: lifecycle enrichment unavailable: %s", type(exc).__name__)

    pages = max(1, (total + page_size - 1) // page_size)

    enriched_items = []
    for c in items:
        record = _public(c, is_admin)
        lifecycle = lifecycle_by_customer.get(c.id)
        if lifecycle is None:  # no lifecycle record: nothing is known, nothing is invented
            record.update(mrr=None, customer_type=None, health="Unknown")
        else:
            mrr = lifecycle["mrr"]
            health_score = lifecycle["health_score"]
            record["mrr"] = mrr
            record["customer_type"] = "Enterprise" if mrr >= 2000 else "SMB" if mrr >= 500 else "Residential"
            record["health"] = (
                "Unknown" if health_score is None
                else "Excellent" if health_score >= 80
                else "Good" if health_score >= 60
                else "At Risk" if health_score >= 30
                else "Critical"
            )
        enriched_items.append(record)

    return PaginatedResponse(items=enriched_items, total=total, page=page, page_size=page_size, pages=pages)


# ---------------------------------------------------------------------------
# GET /customers/{id} — Customer 360 view
# ---------------------------------------------------------------------------

def _as_list(result: Any) -> list:
    if isinstance(result, list):
        return result
    if isinstance(result, dict):
        for key in ("items", "events", "invoices", "tickets", "services"):
            if isinstance(result.get(key), list):
                return result[key]
    return []


async def _upstream(name: str, service: str, path: str, ctx: AuthContext, errors: dict[str, str]) -> Any:
    """One bounded cross-service call; failure is recorded in `errors` and returns None."""
    try:
        return await asyncio.wait_for(
            service_get(service, path, tenant_id=ctx.tenant_id, user_id=ctx.user_id,
                        timeout=UPSTREAM_TIMEOUT_SECONDS, retries=0),
            timeout=UPSTREAM_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        errors[name] = "timeout"
    except Exception as exc:  # noqa: BLE001
        errors[name] = "upstream_error"
        logger.warning("customer 360 upstream %s failed: %s: %s", name, type(exc).__name__, exc)
    return None


@router.get("/{customer_id}", response_model=Customer360)
async def get_customer_360(
    customer_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    async with get_session() as session:
        customer = (await session.execute(
            select(Customer).where(Customer.id == customer_id, Customer.tenant_id == ctx.tenant_id)
        )).scalar_one_or_none()
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")

        is_admin = await has_tier(ctx, session, "admin")
        tags = (await session.execute(
            select(CustomerTag.tag).where(CustomerTag.customer_id == customer_id,
                                          CustomerTag.tenant_id == ctx.tenant_id)
        )).scalars().all()
        notes_count = (await session.execute(
            select(func.count(CustomerNote.id)).where(CustomerNote.customer_id == customer_id,
                                                      CustomerNote.tenant_id == ctx.tenant_id)
        )).scalar_one() or 0

        cust_dict = redact_customer(CustomerRead.model_validate(customer).model_dump(), is_admin)
        cust_dict["tags"] = list(tags)
        cust_dict["notes_count"] = notes_count
        view = Customer360.model_validate(cust_dict)

    # Independent upstream calls run concurrently (no DB session is shared with them).
    cid = str(customer_id)
    errors: dict[str, str] = {}
    billing, support, network, lc_current, lc_events = await asyncio.gather(
        _upstream("billing", "billing", f"/invoices?customer_id={cid}", ctx, errors),
        _upstream("support", "support", f"/tickets?customer_id={cid}", ctx, errors),
        _upstream("network", "network", f"/services?customer_id={cid}", ctx, errors),
        _upstream("lifecycle", "lifecycle", f"/lifecycle/customer/{cid}", ctx, errors),
        _upstream("lifecycle_history", "lifecycle", f"/lifecycle/events?customer_id={cid}&limit=20", ctx, errors),
    )

    view.billing = _as_list(billing) if "billing" not in errors else None
    view.support = _as_list(support) if "support" not in errors else None
    view.network = _as_list(network) if "network" not in errors else None
    view.services = view.network  # alias

    if "lifecycle" in errors:
        view.lifecycle_data = None
    else:
        lc = (lc_current or {}).get("lifecycle") if isinstance(lc_current, dict) else None
        lc = lc or {}
        view.lifecycle_data = {
            "current_stage": lc.get("current_stage"),
            "health_score": lc.get("health_score"),
            "churn_probability": lc.get("churn_probability"),
            "history": _as_list(lc_events) if "lifecycle_history" not in errors else None,
        }

    view.section_errors = errors
    view.partial = bool(errors)
    return view


# ---------------------------------------------------------------------------
# PUT /customers/{id} — Update customer
# ---------------------------------------------------------------------------

@router.put("/{customer_id}", response_model=CustomerRead)
async def update_customer(
    customer_id: uuid.UUID,
    body: CustomerUpdate,
    ctx: AuthContext = Depends(require_write),
):
    async with get_session() as session:
        customer = (await session.execute(
            select(Customer).where(Customer.id == customer_id, Customer.tenant_id == ctx.tenant_id)
        )).scalar_one_or_none()
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")
        is_admin = await has_tier(ctx, session, "admin")

        old_status = customer.status  # captured BEFORE the row is mutated
        update_data = body.model_dump(exclude_unset=True)
        if "email" in update_data:
            update_data["email"] = normalize_email(update_data["email"])
        if "phone" in update_data:
            update_data["phone_normalized"] = normalize_phone(update_data["phone"])

        if update_data.get("email") or update_data.get("phone_normalized"):
            clash = await find_duplicate_customer(
                session, ctx.tenant_id, update_data.get("phone_normalized"), update_data.get("email"),
                exclude_id=customer_id,
            )
            if clash is not None:
                raise _duplicate_409(clash)

        for field, value in update_data.items():
            setattr(customer, field, value)
        try:
            async with session.begin_nested():
                await session.flush()
        except IntegrityError:
            raise HTTPException(status_code=409, detail="Another customer already uses this phone number or e-mail")
        await session.refresh(customer)

        sync_event = _detect_sync_event(body, old_status)
        if sync_event:
            await _sync_customer_to_journey_engine(session, customer, source_event=sync_event)

        return _public(customer, is_admin)


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
        exists = (await session.execute(
            select(Customer.id).where(Customer.id == customer_id, Customer.tenant_id == ctx.tenant_id)
        )).scalar_one_or_none()
        if not exists:
            raise HTTPException(status_code=404, detail="Customer not found")

        events = (await session.execute(
            select(ActivityEvent).where(
                ActivityEvent.customer_id == customer_id,
                ActivityEvent.tenant_id == ctx.tenant_id,
            )
            .order_by(ActivityEvent.created_at.desc(), ActivityEvent.id)
            .limit(limit)
        )).scalars().all()

    return [TimelineEvent.model_validate(e) for e in events]
