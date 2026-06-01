"""Customer Lifecycle routes — stage management, transitions, dashboard.

Endpoints:
  Lifecycle Stages:
    GET    /lifecycle/stages                — list tenant stages
    POST   /lifecycle/stages                — create stage (with defaults)
    PUT    /lifecycle/stages/{id}           — update stage

  Transitions:
    POST   /lifecycle/transition            — move customer to new stage
    GET    /lifecycle/events                — list transition events

  Customer Lifecycle:
    GET    /lifecycle/customer/{id}         — get customer lifecycle state
    GET    /lifecycle/customers             — list all customer lifecycles

  Dashboard:
    GET    /lifecycle/dashboard             — aggregated lifecycle metrics
    GET    /lifecycle/funnel                — stage transition funnel
    GET    /lifecycle/revenue               — MRR movement (new/churned/reactivated)
    GET    /lifecycle/health                — health score distribution

  Sales Bridge:
    POST   /lifecycle/from-sale             — record sale-originated lifecycle event
    POST   /lifecycle/from-journey          — record journey-engine outcome

  Context:
    GET    /lifecycle/context/{customer_id} — full lifecycle + CRM + billing + support
"""

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import case, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from services.lifecycle.database import get_session, init_tables
from services.lifecycle.models import (
    CustomerLifecycle,
    CustomerSegmentAssignment,
    LifecycleEvent,
    LifecycleStage,
    LifecycleSummary,
)

app = FastAPI(
    title="OmniDome Lifecycle Service",
    description="Customer lifecycle management — lead to churn tracking with sales bridge",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Default lifecycle stages per tenant
# ---------------------------------------------------------------------------

DEFAULT_STAGES = [
    {"name": "Lead", "category": "lead", "color": "#94a3b8", "sort_order": 1},
    {"name": "Qualified", "category": "lead", "color": "#60a5fa", "sort_order": 2},
    {"name": "Proposal", "category": "prospect", "color": "#a855f7", "sort_order": 3},
    {"name": "Converted", "category": "customer", "color": "#4ade80", "sort_order": 4, "is_default": True},
    {"name": "Onboarding", "category": "customer", "color": "#38bdf8", "sort_order": 5},
    {"name": "Active", "category": "customer", "color": "#4ade80", "sort_order": 6},
    {"name": "At Risk", "category": "at_risk", "color": "#f97316", "sort_order": 7},
    {"name": "Churned", "category": "churned", "color": "#ef4444", "sort_order": 8},
    {"name": "Reactivated", "category": "reactivated", "color": "#14b8a6", "sort_order": 9},
]


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def startup():
    init_tables()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class StageCreate(BaseModel):
    name: str
    category: str = "customer"
    color: str = "#60a5fa"
    sort_order: int = 0
    is_active: bool = True
    on_enter_actions: Optional[dict] = None

class StageUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    color: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None
    on_enter_actions: Optional[dict] = None

class TransitionCreate(BaseModel):
    customer_id: str
    to_stage: str
    reason: Optional[str] = None
    trigger_source: str = "manual"
    trigger_id: Optional[str] = None
    metadata_: Optional[dict] = Field(default=None, alias="metadata")

class SaleBridgeCreate(BaseModel):
    """Called by Sales service when a deal is closed won."""
    tenant_id: str
    customer_id: str
    deal_id: str
    agent_id: Optional[str] = None
    plan: Optional[str] = None
    monthly_recurring_revenue: float = 0.0
    lead_id: Optional[str] = None

class JourneyBridgeCreate(BaseModel):
    """Called by Journey Engine when customer cancels or is saved."""
    tenant_id: str
    customer_id: str
    cancel_event_id: str
    outcome: str  # "accepted", "rejected", "expired"
    journey_id: Optional[str] = None
    offer_id: Optional[str] = None
    reason: Optional[str] = None


# ---------------------------------------------------------------------------
# Lifecycle Stages CRUD
# ---------------------------------------------------------------------------

@app.get("/lifecycle/stages")
async def list_stages(
    tenant_id: str,
    category: Optional[str] = None,
    session: AsyncSession = Depends(get_session),
):
    query = select(LifecycleStage).where(
        LifecycleStage.tenant_id == uuid.UUID(tenant_id),
        LifecycleStage.is_active == True,
    )
    if category:
        query = query.where(LifecycleStage.category == category)
    query = query.order_by(LifecycleStage.sort_order)

    result = await session.execute(query)
    stages = result.scalars().all()
    return {"stages": [_stage_to_dict(s) for s in stages]}


@app.post("/lifecycle/stages")
async def create_or_ensure_stages(
    tenant_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Create default stages for a tenant if they don't exist."""
    existing = await session.execute(
        select(func.count(LifecycleStage.id)).where(
            LifecycleStage.tenant_id == uuid.UUID(tenant_id)
        )
    )
    count = existing.scalar()

    if count > 0:
        # Already has stages — just return them
        result = await session.execute(
            select(LifecycleStage)
            .where(LifecycleStage.tenant_id == uuid.UUID(tenant_id))
            .order_by(LifecycleStage.sort_order)
        )
        stages = result.scalars().all()
        return {
            "stages": [_stage_to_dict(s) for s in stages],
            "message": f"{count} stages already exist",
        }

    # Create defaults
    created = []
    for stage_data in DEFAULT_STAGES:
        stage = LifecycleStage(
            tenant_id=uuid.UUID(tenant_id),
            name=stage_data["name"],
            category=stage_data["category"],
            color=stage_data["color"],
            sort_order=stage_data["sort_order"],
            is_default=stage_data.get("is_default", False),
        )
        session.add(stage)
        created.append(stage)

    await session.flush()
    return {
        "stages": [_stage_to_dict(s) for s in created],
        "message": f"{len(created)} default stages created",
    }


@app.put("/lifecycle/stages/{stage_id}")
async def update_stage(
    stage_id: str,
    data: StageUpdate,
    tenant_id: str,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(LifecycleStage).where(
            LifecycleStage.id == uuid.UUID(stage_id),
            LifecycleStage.tenant_id == uuid.UUID(tenant_id),
        )
    )
    stage = result.scalar_one_or_none()
    if not stage:
        raise HTTPException(404, "Stage not found")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(stage, key, value)

    return {"stage": _stage_to_dict(stage)}


# ---------------------------------------------------------------------------
# Transitions
# ---------------------------------------------------------------------------

@app.post("/lifecycle/transition")
async def create_transition(
    data: TransitionCreate,
    tenant_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Move a customer to a new lifecycle stage."""
    customer_id = uuid.UUID(data.customer_id)
    tenant_uuid = uuid.UUID(tenant_id)

    # Find the target stage
    stage_result = await session.execute(
        select(LifecycleStage).where(
            LifecycleStage.tenant_id == tenant_uuid,
            LifecycleStage.name == data.to_stage,
        )
    )
    target_stage = stage_result.scalar_one_or_none()

    # Get current lifecycle
    lc_result = await session.execute(
        select(CustomerLifecycle).where(
            CustomerLifecycle.customer_id == customer_id,
            CustomerLifecycle.tenant_id == tenant_uuid,
        )
    )
    lc = lc_result.scalar_one_or_none()

    now = datetime.now(timezone.utc)

    if lc:
        from_stage = lc.current_stage
        result = await session.execute(
            update(CustomerLifecycle)
            .where(CustomerLifecycle.id == lc.id)
            .values(
                current_stage=data.to_stage,
                current_stage_id=target_stage.id if target_stage else None,
                updated_at=now,
            )
            .returning(CustomerLifecycle)
        )
        lc = result.scalar_one()

        # Update stage-specific timestamps
        if data.to_stage == "Converted":
            lc.converted_at = now
        elif data.to_stage == "At Risk":
            lc.is_at_risk = True
        elif data.to_stage == "Churned":
            lc.churned_at = now
            lc.is_at_risk = False
        elif data.to_stage == "Reactivated":
            lc.reactivated_at = now
            lc.is_at_risk = False

    else:
        # Create new lifecycle record
        lc = CustomerLifecycle(
            tenant_id=tenant_uuid,
            customer_id=customer_id,
            current_stage=data.to_stage,
            current_stage_id=target_stage.id if target_stage else None,
            first_contact_at=now,
        )
        session.add(lc)

    # Record the transition event
    event = LifecycleEvent(
        tenant_id=tenant_uuid,
        customer_id=customer_id,
        from_stage=from_stage if lc else None,
        to_stage=data.to_stage,
        trigger_source=data.trigger_source,
        trigger_id=uuid.UUID(data.trigger_id) if data.trigger_id else None,
        reason=data.reason,
        metadata_=data.metadata_,
    )
    session.add(event)
    await session.flush()

    return {
        "customer_id": str(customer_id),
        "from_stage": from_stage if lc and hasattr(lc, "current_stage") else None,
        "to_stage": data.to_stage,
        "success": True,
    }


@app.get("/lifecycle/events")
async def list_events(
    tenant_id: str,
    customer_id: Optional[str] = None,
    limit: int = 50,
    session: AsyncSession = Depends(get_session),
):
    query = select(LifecycleEvent).where(
        LifecycleEvent.tenant_id == uuid.UUID(tenant_id),
    )
    if customer_id:
        query = query.where(LifecycleEvent.customer_id == uuid.UUID(customer_id))
    query = query.order_by(LifecycleEvent.created_at.desc()).limit(limit)

    result = await session.execute(query)
    events = result.scalars().all()
    return {"events": [_event_to_dict(e) for e in events]}


# ---------------------------------------------------------------------------
# Customer Lifecycle
# ---------------------------------------------------------------------------

@app.get("/lifecycle/customer/{customer_id}")
async def get_customer_lifecycle(
    customer_id: str,
    tenant_id: str,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(CustomerLifecycle).where(
            CustomerLifecycle.customer_id == uuid.UUID(customer_id),
            CustomerLifecycle.tenant_id == uuid.UUID(tenant_id),
        )
    )
    lc = result.scalar_one_or_none()
    if not lc:
        return {"lifecycle": None, "message": "No lifecycle record found"}
    return {"lifecycle": _lc_to_dict(lc)}


@app.get("/lifecycle/customers")
async def list_customer_lifecycles(
    tenant_id: str,
    stage: Optional[str] = None,
    is_at_risk: Optional[bool] = None,
    min_health: Optional[int] = None,
    max_health: Optional[int] = None,
    page: int = 1,
    page_size: int = 50,
    session: AsyncSession = Depends(get_session),
):
    query = select(CustomerLifecycle).where(
        CustomerLifecycle.tenant_id == uuid.UUID(tenant_id),
    )
    if stage:
        query = query.where(CustomerLifecycle.current_stage == stage)
    if is_at_risk is not None:
        query = query.where(CustomerLifecycle.is_at_risk == is_at_risk)
    if min_health is not None:
        query = query.where(CustomerLifecycle.health_score >= min_health)
    if max_health is not None:
        query = query.where(CustomerLifecycle.health_score <= max_health)

    # Count
    count_result = await session.execute(
        select(func.count()).select_from(query.subquery())
    )
    total = count_result.scalar()

    # Paginated results
    query = query.order_by(CustomerLifecycle.updated_at.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size)
    result = await session.execute(query)
    items = result.scalars().all()

    return {
        "lifecycles": [_lc_to_dict(lc) for lc in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@app.get("/lifecycle/dashboard")
async def get_dashboard(
    tenant_id: str,
    days: int = 30,
    session: AsyncSession = Depends(get_session),
):
    """Aggregated lifecycle metrics for dashboard."""
    tenant_uuid = uuid.UUID(tenant_id)
    since = datetime.now(timezone.utc) - timedelta(days=days)

    # Count by stage
    stage_query = (
        select(
            CustomerLifecycle.current_stage,
            func.count(CustomerLifecycle.id).label("count"),
            func.sum(CustomerLifecycle.monthly_recurring_revenue).label("mrr"),
            func.avg(CustomerLifecycle.health_score).label("avg_health"),
        )
        .where(CustomerLifecycle.tenant_id == tenant_uuid)
        .group_by(CustomerLifecycle.current_stage)
    )
    stage_result = await session.execute(stage_query)
    stage_rows = stage_result.all()

    stages = {}
    for row in stage_rows:
        stages[row.current_stage] = {
            "count": row.count,
            "mrr": float(row.mrr or 0),
            "avg_health": round(float(row.avg_health or 0), 1),
        }

    # Risk summary
    risk_result = await session.execute(
        select(
            func.count(CustomerLifecycle.id).label("at_risk_count"),
            func.avg(CustomerLifecycle.churn_probability).label("avg_churn_prob"),
        ).where(
            CustomerLifecycle.tenant_id == tenant_uuid,
            CustomerLifecycle.is_at_risk == True,
        )
    )
    risk_row = risk_result.one()

    # Total MRR
    mrr_result = await session.execute(
        select(
            func.sum(CustomerLifecycle.monthly_recurring_revenue).label("total_mrr"),
            func.count(CustomerLifecycle.id).label("total_customers"),
        ).where(
            CustomerLifecycle.tenant_id == tenant_uuid,
            CustomerLifecycle.current_stage.notin_(["Lead", "Qualified", "Proposal", "Churned"]),
        )
    )
    mrr_row = mrr_result.one()

    # Recent transitions
    events_query = (
        select(LifecycleEvent)
        .where(
            LifecycleEvent.tenant_id == tenant_uuid,
            LifecycleEvent.created_at >= since,
        )
        .order_by(LifecycleEvent.created_at.desc())
        .limit(20)
    )
    events_result = await session.execute(events_query)
    events = events_result.scalars().all()

    return {
        "stages": stages,
        "risk": {
            "at_risk_count": risk_row.at_risk_count or 0,
            "avg_churn_probability": float(risk_row.avg_churn_prob or 0),
        },
        "revenue": {
            "total_mrr": float(mrr_row.total_mrr or 0),
            "active_customers": mrr_row.total_customers or 0,
        },
        "recent_events": [_event_to_dict(e) for e in events],
        "period_days": days,
    }


@app.get("/lifecycle/funnel")
async def get_funnel(
    tenant_id: str,
    days: int = 30,
    session: AsyncSession = Depends(get_session),
):
    """Stage transition funnel."""
    tenant_uuid = uuid.UUID(tenant_id)
    since = datetime.now(timezone.utc) - timedelta(days=days)

    query = (
        select(
            LifecycleEvent.to_stage,
            func.count(LifecycleEvent.id).label("count"),
        )
        .where(
            LifecycleEvent.tenant_id == tenant_uuid,
            LifecycleEvent.created_at >= since,
        )
        .group_by(LifecycleEvent.to_stage)
        .order_by(func.count(LifecycleEvent.id).desc())
    )
    result = await session.execute(query)
    rows = result.all()

    return {
        "funnel": [{"stage": row.to_stage, "entries": row.count} for row in rows],
        "period_days": days,
    }


# ---------------------------------------------------------------------------
# Sales Bridge — called by Sales service
# ---------------------------------------------------------------------------

@app.post("/lifecycle/from-sale")
async def record_sale_bridge(
    data: SaleBridgeCreate,
    session: AsyncSession = Depends(get_session),
):
    """Sales service notifies lifecycle when deal closes."""
    tenant_uuid = uuid.UUID(data.tenant_id)
    customer_id = uuid.UUID(data.customer_id)
    now = datetime.now(timezone.utc)

    # Create/update lifecycle record
    result = await session.execute(
        select(CustomerLifecycle).where(
            CustomerLifecycle.customer_id == customer_id,
            CustomerLifecycle.tenant_id == tenant_uuid,
        )
    )
    lc = result.scalar_one_or_none()

    if lc:
        lc.current_stage = "Converted"
        lc.converted_at = now
        lc.first_payment_at = now
        lc.last_payment_at = now
        lc.current_plan = data.plan
        lc.monthly_recurring_revenue = Decimal(str(data.monthly_recurring_revenue))
        lc.last_activity_at = now
        lc.health_score = 75  # New customer default
        lc.originating_deal_id = uuid.UUID(data.deal_id)
        if data.lead_id:
            lc.originating_lead_id = uuid.UUID(data.lead_id)
        if data.agent_id:
            lc.assigned_sales_agent_id = uuid.UUID(data.agent_id)
    else:
        lc = CustomerLifecycle(
            tenant_id=tenant_uuid,
            customer_id=customer_id,
            current_stage="Converted",
            converted_at=now,
            first_contact_at=now,
            first_payment_at=now,
            last_payment_at=now,
            last_activity_at=now,
            current_plan=data.plan,
            monthly_recurring_revenue=Decimal(str(data.monthly_recurring_revenue)),
            health_score=75,
            originating_deal_id=uuid.UUID(data.deal_id),
            originating_lead_id=uuid.UUID(data.lead_id) if data.lead_id else None,
            assigned_sales_agent_id=uuid.UUID(data.agent_id) if data.agent_id else None,
        )
        session.add(lc)

    # Record event
    event = LifecycleEvent(
        tenant_id=tenant_uuid,
        customer_id=customer_id,
        from_stage="Proposal",
        to_stage="Converted",
        trigger_source="sale",
        trigger_id=uuid.UUID(data.deal_id),
        reason=f"Deal closed: {data.plan}",
        metadata_={"mrr": data.monthly_recurring_revenue, "agent_id": data.agent_id},
    )
    session.add(event)

    return {
        "customer_id": str(customer_id),
        "stage": "Converted",
        "message": "Lifecycle updated from sale",
    }


# ---------------------------------------------------------------------------
# Journey Bridge — called by Journey Engine
# ---------------------------------------------------------------------------

@app.post("/lifecycle/from-journey")
async def record_journey_bridge(
    data: JourneyBridgeCreate,
    session: AsyncSession = Depends(get_session),
):
    """Journey Engine notifies lifecycle of cancel/save outcome."""
    tenant_uuid = uuid.UUID(data.tenant_id)
    customer_id = uuid.UUID(data.customer_id)
    now = datetime.now(timezone.utc)

    result = await session.execute(
        select(CustomerLifecycle).where(
            CustomerLifecycle.customer_id == customer_id,
            CustomerLifecycle.tenant_id == tenant_uuid,
        )
    )
    lc = result.scalar_one_or_none()

    if not lc:
        return {"customer_id": str(customer_id), "message": "No lifecycle record"}

    from_stage = lc.current_stage

    if data.outcome == "rejected":
        # Customer declined retention offer → churn
        lc.current_stage = "Churned"
        lc.churned_at = now
        lc.is_at_risk = False
        lc.churn_probability = Decimal("100.00")
        lc.risk_reason = data.reason or "Declined retention offer"
    elif data.outcome == "expired":
        # Offer timed out → escalate risk
        lc.current_stage = "At Risk"
        lc.is_at_risk = True
        lc.risk_reason = data.reason or "Retention offer expired"
        lc.churn_probability = Decimal("75.00")
    elif data.outcome == "accepted":
        # Customer saved → back to active
        lc.current_stage = "Active"
        lc.is_at_risk = False
        lc.risk_reason = None
        lc.churn_probability = Decimal("10.00")
        lc.health_score = min(100, lc.health_score + 15)
        lc.last_journey_event_id = uuid.UUID(data.cancel_event_id)

    lc.last_activity_at = now

    # Record event
    event = LifecycleEvent(
        tenant_id=tenant_uuid,
        customer_id=customer_id,
        from_stage=from_stage,
        to_stage=lc.current_stage,
        trigger_source="journey_engine",
        trigger_id=uuid.UUID(data.cancel_event_id),
        reason=data.reason,
        metadata_={
            "journey_id": data.journey_id,
            "offer_id": data.offer_id,
            "outcome": data.outcome,
        },
    )
    session.add(event)

    await session.flush()
    return {
        "customer_id": str(customer_id),
        "stage": lc.current_stage,
        "message": f"Journey outcome recorded: {data.outcome}",
    }


# ---------------------------------------------------------------------------
# Context — full customer context for portal/CRM
# ---------------------------------------------------------------------------

@app.get("/lifecycle/context/{customer_id}")
async def get_context(
    customer_id: str,
    tenant_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Full lifecycle context + recent events for a customer."""
    tenant_uuid = uuid.UUID(tenant_id)
    cid = uuid.UUID(customer_id)

    # Lifecycle state
    lc_result = await session.execute(
        select(CustomerLifecycle).where(
            CustomerLifecycle.customer_id == cid,
            CustomerLifecycle.tenant_id == tenant_uuid,
        )
    )
    lc = lc_result.scalar_one_or_none()

    # Recent transitions
    events_result = await session.execute(
        select(LifecycleEvent)
        .where(
            LifecycleEvent.customer_id == cid,
            LifecycleEvent.tenant_id == tenant_uuid,
        )
        .order_by(LifecycleEvent.created_at.desc())
        .limit(10)
    )
    events = events_result.scalars().all()

    # Available stages for this tenant
    stages_result = await session.execute(
        select(LifecycleStage)
        .where(
            LifecycleStage.tenant_id == tenant_uuid,
            LifecycleStage.is_active == True,
        )
        .order_by(LifecycleStage.sort_order)
    )
    stages = stages_result.scalars().all()

    return {
        "lifecycle": _lc_to_dict(lc) if lc else None,
        "recent_events": [_event_to_dict(e) for e in events],
        "available_stages": [_stage_to_dict(s) for s in stages],
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _stage_to_dict(stage):
    return {
        "id": str(stage.id),
        "name": stage.name,
        "category": stage.category,
        "color": stage.color,
        "sort_order": stage.sort_order,
        "is_default": stage.is_default,
        "is_active": stage.is_active,
        "on_enter_actions": stage.on_enter_actions,
    }


def _event_to_dict(event):
    return {
        "id": str(event.id),
        "customer_id": str(event.customer_id),
        "from_stage": event.from_stage,
        "to_stage": event.to_stage,
        "trigger_source": event.trigger_source,
        "trigger_id": str(event.trigger_id) if event.trigger_id else None,
        "reason": event.reason,
        "metadata": event.metadata_,
        "created_at": event.created_at.isoformat() if event.created_at else None,
    }


def _lc_to_dict(lc):
    return {
        "id": str(lc.id),
        "customer_id": str(lc.customer_id),
        "current_stage": lc.current_stage,
        "is_at_risk": lc.is_at_risk,
        "health_score": lc.health_score,
        "churn_probability": float(lc.churn_probability) if lc.churn_probability else None,
        "risk_reason": lc.risk_reason,
        "monthly_recurring_revenue": float(lc.monthly_recurring_revenue),
        "current_plan": lc.current_plan,
        "first_contact_at": lc.first_contact_at.isoformat() if lc.first_contact_at else None,
        "converted_at": lc.converted_at.isoformat() if lc.converted_at else None,
        "churned_at": lc.churned_at.isoformat() if lc.churned_at else None,
        "originating_lead_id": str(lc.originating_lead_id) if lc.originating_lead_id else None,
        "originating_deal_id": str(lc.originating_deal_id) if lc.originating_deal_id else None,
        "assigned_sales_agent_id": str(lc.assigned_sales_agent_id) if lc.assigned_sales_agent_id else None,
        "updated_at": lc.updated_at.isoformat() if lc.updated_at else None,
    }


@app.get("/")
async def root():
    return {
        "service": "OmniDome Lifecycle Service",
        "version": "1.0.0",
        "status": "active",
        "flow": "Lead → Qualified → Proposal → Converted → Active → At Risk → Churned → Reactivated",
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8018)
