"""Journey Engine Service — manages cancel-to-save retention journeys.

Endpoints:
  Journeys:
    GET    /journeys               — list journeys
    POST   /journeys               — create journey
    GET    /journeys/{id}          — get journey details
    PUT    /journeys/{id}          — update journey
    DELETE /journeys/{id}          — archive journey

  Rules:
    POST   /journeys/{id}/rules    — add rules to a journey
    DELETE /rules/{rule_id}        — remove a rule
    PUT    /rules/{rule_id}        — update a rule

  Offers:
    GET    /offers                 — list offers
    POST   /offers                 — create offer
    GET    /offers/{id}            — get offer details
    PUT    /offers/{id}            — update offer
    DELETE /offers/{id}            — archive offer

  Cancel Flow (the core integration):
    POST   /cancel/trigger          — customer cancels → returns best offer
    POST   /cancel/{id}/respond     — customer accepts/rejects the offer

  Analytics:
    GET    /analytics/funnel        — journey funnel stats
    GET    /analytics/outcomes      — outcome tracking & ML feedback
    GET    /analytics/roi           — return on investment by journey
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from services.journey_engine.database import get_db, init_tables
from services.journey_engine.journey_manager import (
    compute_outcome_result,
    process_cancel_event,
)
from services.journey_engine.batch_outcomes import get_outcome_stats, process_outcomes
from services.journey_engine.models import (
    CancelEvent,
    CustomerSnapshot,
    JourneyOutcome,
    JourneyRule,
    RetentionJourney,
    RetentionOffer,
)
from services.journey_engine.rule_engine import ATTRIBUTE_TYPES
from services.common.entitlements import EntitlementGuard
from services.common.middleware import configure_production
from services.journey_engine.lifecycle_routes import router as lifecycle_router
from services.journey_engine.routes.ab_testing import router as ab_testing_router

app = FastAPI(
    title="OmniDome Journey Engine",
    description="Retention Journey Engine — cancel-to-save lifecycle management",
    version="1.0.0",
)

guard = EntitlementGuard(module_id="journey_engine")

configure_production(app)


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok", "service": "journey_engine"}

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def entitlement_middleware(request, call_next):
    return await guard.middleware(request, call_next)

app.include_router(lifecycle_router)
app.include_router(ab_testing_router)

# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def startup():
    init_tables()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class JourneyCreate(BaseModel):
    name: str
    description: Optional[str] = None
    trigger_event: str = "cancel_initiated"
    priority: int = 0
    offer_id: Optional[str] = None
    fallback_offer_id: Optional[str] = None
    channel: str = "portal"
    tenant_id: str

class JourneyUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[int] = None
    offer_id: Optional[str] = None
    fallback_offer_id: Optional[str] = None
    channel: Optional[str] = None
    ab_test_enabled: Optional[bool] = None
    ab_test_config: Optional[dict] = None

class RuleCreate(BaseModel):
    rule_group: int = 0
    attribute: str
    operator: str
    value: dict
    is_active: bool = True
    sort_order: int = 0

class RuleUpdate(BaseModel):
    rule_group: Optional[int] = None
    attribute: Optional[str] = None
    operator: Optional[str] = None
    value: Optional[dict] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None

class OfferCreate(BaseModel):
    name: str
    description: Optional[str] = None
    offer_type: str
    parameters: dict
    max_per_customer: int = 1
    max_total_redemptions: Optional[int] = None
    estimated_cost_per_use: Optional[float] = None
    tenant_id: str

class OfferUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    parameters: Optional[dict] = None
    max_per_customer: Optional[int] = None
    max_total_redemptions: Optional[int] = None
    estimated_cost_per_use: Optional[float] = None
    status: Optional[str] = None

class CancelTrigger(BaseModel):
    customer_id: str
    account_number: str
    customer_snapshot: dict  # full customer data for rule evaluation
    cancel_reason: Optional[str] = None
    source_channel: str = "portal"

class CancelRespond(BaseModel):
    cancel_event_id: str
    decision: str  # "accept" or "reject"
    response_time_seconds: Optional[int] = None

class FunnelFilter(BaseModel):
    tenant_id: str
    journey_id: Optional[str] = None
    days: int = 30


class OutcomesProcessRequest(BaseModel):
    """Request body for POST /outcomes/process — trigger the retention batch job."""

    tenant_id: Optional[str] = Field(
        None, description="If provided, only process outcomes for this tenant"
    )
    dry_run: bool = Field(
        False, description="If true, compute results but don't persist changes"
    )


class OutcomesStatsResponse(BaseModel):
    """Response model for GET /outcome-stats."""

    total_outcomes: dict
    pending_90d_checks: int
    pending_180d_checks: int
    retention_rate_distribution: dict


# ---------------------------------------------------------------------------
# Journeys CRUD
# ---------------------------------------------------------------------------

@app.get("/journeys")
async def list_journeys(
    tenant_id: str,
    status: Optional[str] = None,
    trigger_event: Optional[str] = "cancel_initiated",
    session: AsyncSession = Depends(get_db),
):
    query = select(RetentionJourney).where(
        RetentionJourney.tenant_id == uuid.UUID(tenant_id)
    )
    if status:
        query = query.where(RetentionJourney.status == status)
    if trigger_event:
        query = query.where(RetentionJourney.trigger_event == trigger_event)
    query = query.order_by(RetentionJourney.priority.desc())

    result = await session.execute(query)
    journeys = result.scalars().all()
    return {"journeys": [_journey_to_dict(j) for j in journeys]}


@app.post("/journeys")
async def create_journey(
    data: JourneyCreate,
    session: AsyncSession = Depends(get_db),
):
    journey = RetentionJourney(
        tenant_id=uuid.UUID(data.tenant_id),
        name=data.name,
        description=data.description,
        trigger_event=data.trigger_event,
        priority=data.priority,
        offer_id=uuid.UUID(data.offer_id) if data.offer_id else None,
        fallback_offer_id=uuid.UUID(data.fallback_offer_id) if data.fallback_offer_id else None,
        channel=data.channel,
        status="draft",
    )
    session.add(journey)
    await session.flush()
    return {"journey": _journey_to_dict(journey), "status": "created"}


@app.get("/journeys/{journey_id}")
async def get_journey(
    journey_id: str,
    session: AsyncSession = Depends(get_db),
):
    query = (
        select(RetentionJourney)
        .where(RetentionJourney.id == uuid.UUID(journey_id))
        .options(selectinload(RetentionJourney.rules))
    )
    result = await session.execute(query)
    journey = result.scalar_one_or_none()
    if not journey:
        raise HTTPException(404, "Journey not found")
    return {"journey": _journey_to_dict(journey, include_rules=True)}


@app.put("/journeys/{journey_id}")
async def update_journey(
    journey_id: str,
    data: JourneyUpdate,
    session: AsyncSession = Depends(get_db),
):
    query = select(RetentionJourney).where(RetentionJourney.id == uuid.UUID(journey_id))
    result = await session.execute(query)
    journey = result.scalar_one_or_none()
    if not journey:
        raise HTTPException(404, "Journey not found")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        if key in ("offer_id", "fallback_offer_id") and value:
            value = uuid.UUID(value)
        setattr(journey, key, value)

    journey.updated_at = datetime.now(timezone.utc)
    return {"journey": _journey_to_dict(journey)}


@app.delete("/journeys/{journey_id}")
async def delete_journey(
    journey_id: str,
    session: AsyncSession = Depends(get_db),
):
    query = select(RetentionJourney).where(RetentionJourney.id == uuid.UUID(journey_id))
    result = await session.execute(query)
    journey = result.scalar_one_or_none()
    if not journey:
        raise HTTPException(404, "Journey not found")
    journey.status = "archived"
    return {"status": "archived"}


# ---------------------------------------------------------------------------
# Rules CRUD
# ---------------------------------------------------------------------------

@app.post("/journeys/{journey_id}/rules")
async def add_rules(
    journey_id: str,
    rules: list[RuleCreate],
    session: AsyncSession = Depends(get_db),
):
    created = []
    for rule_data in rules:
        rule = JourneyRule(
            tenant_id=(await _get_journey_tenant(journey_id, session)),
            journey_id=uuid.UUID(journey_id),
            rule_group=rule_data.rule_group,
            attribute=rule_data.attribute,
            operator=rule_data.operator,
            value=rule_data.value,
            is_active=rule_data.is_active,
            sort_order=rule_data.sort_order,
        )
        session.add(rule)
        created.append(rule)
    await session.flush()
    return {"rules": [_rule_to_dict(r) for r in created]}


@app.put("/rules/{rule_id}")
async def update_rule(
    rule_id: str,
    data: RuleUpdate,
    session: AsyncSession = Depends(get_db),
):
    query = select(JourneyRule).where(JourneyRule.id == uuid.UUID(rule_id))
    result = await session.execute(query)
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(404, "Rule not found")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(rule, key, value)

    return {"rule": _rule_to_dict(rule)}


@app.delete("/rules/{rule_id}")
async def delete_rule(
    rule_id: str,
    session: AsyncSession = Depends(get_db),
):
    query = select(JourneyRule).where(JourneyRule.id == uuid.UUID(rule_id))
    result = await session.execute(query)
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(404, "Rule not found")
    await session.delete(rule)
    return {"status": "deleted"}


# ---------------------------------------------------------------------------
# Offers CRUD
# ---------------------------------------------------------------------------

@app.get("/offers")
async def list_offers(
    tenant_id: str,
    offer_type: Optional[str] = None,
    status: Optional[str] = "active",
    session: AsyncSession = Depends(get_db),
):
    query = select(RetentionOffer).where(
        RetentionOffer.tenant_id == uuid.UUID(tenant_id)
    )
    if offer_type:
        query = query.where(RetentionOffer.offer_type == offer_type)
    if status:
        query = query.where(RetentionOffer.status == status)

    result = await session.execute(query)
    offers = result.scalars().all()
    return {"offers": [_offer_to_dict(o) for o in offers]}


@app.post("/offers")
async def create_offer(
    data: OfferCreate,
    session: AsyncSession = Depends(get_db),
):
    offer = RetentionOffer(
        tenant_id=uuid.UUID(data.tenant_id),
        name=data.name,
        description=data.description,
        offer_type=data.offer_type,
        parameters=data.parameters,
        max_per_customer=data.max_per_customer,
        max_total_redemptions=data.max_total_redemptions,
        estimated_cost_per_use=Decimal(str(data.estimated_cost_per_use)) if data.estimated_cost_per_use else None,
        status="active",
    )
    session.add(offer)
    await session.flush()
    return {"offer": _offer_to_dict(offer), "status": "created"}


@app.get("/offers/{offer_id}")
async def get_offer(
    offer_id: str,
    session: AsyncSession = Depends(get_db),
):
    query = select(RetentionOffer).where(RetentionOffer.id == uuid.UUID(offer_id))
    result = await session.execute(query)
    offer = result.scalar_one_or_none()
    if not offer:
        raise HTTPException(404, "Offer not found")
    return {"offer": _offer_to_dict(offer)}


@app.put("/offers/{offer_id}")
async def update_offer(
    offer_id: str,
    data: OfferUpdate,
    session: AsyncSession = Depends(get_db),
):
    query = select(RetentionOffer).where(RetentionOffer.id == uuid.UUID(offer_id))
    result = await session.execute(query)
    offer = result.scalar_one_or_none()
    if not offer:
        raise HTTPException(404, "Offer not found")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        if key == "estimated_cost_per_use" and value is not None:
            value = Decimal(str(value))
        setattr(offer, key, value)

    offer.updated_at = datetime.now(timezone.utc)
    return {"offer": _offer_to_dict(offer)}


@app.delete("/offers/{offer_id}")
async def delete_offer(
    offer_id: str,
    session: AsyncSession = Depends(get_db),
):
    query = select(RetentionOffer).where(RetentionOffer.id == uuid.UUID(offer_id))
    result = await session.execute(query)
    offer = result.scalar_one_or_none()
    if not offer:
        raise HTTPException(404, "Offer not found")
    offer.status = "archived"
    return {"status": "archived"}


# ---------------------------------------------------------------------------
# Cancel Flow — THE CORE INTEGRATION
# ---------------------------------------------------------------------------

@app.post("/cancel/trigger")
async def trigger_cancel(
    data: CancelTrigger,
    session: AsyncSession = Depends(get_db),
):
    """Customer initiates cancellation → find best journey + offer.

    Called by the portal when a customer clicks "Cancel Service".
    Returns the journey and offer to present to the customer.
    """
    tenant_id = data.customer_snapshot.get("tenant_id")
    if not tenant_id:
        raise HTTPException(400, "tenant_id required in customer_snapshot")

    # 1. Load active journeys for this tenant
    journey_query = (
        select(RetentionJourney)
        .where(
            RetentionJourney.tenant_id == uuid.UUID(tenant_id),
            RetentionJourney.status == "active",
        )
        .order_by(RetentionJourney.priority.desc())
    )
    journey_result = await session.execute(journey_query)
    journeys = journey_result.scalars().all()

    if not journeys:
        return {"matched": False, "message": "No active journeys configured"}

    # 2. Load rules for each journey
    rules_by_journey = {}
    for journey in journeys:
        rule_query = (
            select(JourneyRule)
            .where(
                JourneyRule.journey_id == journey.id,
                JourneyRule.is_active == True,
            )
            .order_by(JourneyRule.rule_group, JourneyRule.sort_order)
        )
        rule_result = await session.execute(rule_query)
        rules = rule_result.scalars().all()
        rules_by_journey[str(journey.id)] = [_rule_to_dict(r) for r in rules]

    # 3. Load all offers referenced by journeys
    offer_ids = set()
    for j in journeys:
        if j.offer_id:
            offer_ids.add(str(j.offer_id))
        if j.fallback_offer_id:
            offer_ids.add(str(j.fallback_offer_id))

    offers = {}
    if offer_ids:
        offer_query = select(RetentionOffer).where(
            RetentionOffer.id.in_([uuid.UUID(oid) for oid in offer_ids]),
            RetentionOffer.status == "active",
        )
        offer_result = await session.execute(offer_query)
        for offer in offer_result.scalars().all():
            offers[str(offer.id)] = _offer_to_dict(offer)

    # 4. Run the journey manager
    customer = data.customer_snapshot
    customer["churn_reason"] = (data.cancel_reason or "").lower()

    journey_dicts = [_journey_to_dict(j) for j in journeys]
    result = process_cancel_event(
        customer=customer,
        cancel_reason=data.cancel_reason,
        journeys=journey_dicts,
        rules_by_journey=rules_by_journey,
        offers=offers,
    )

    # 5. Create cancel event record
    cancel_event = CancelEvent(
        tenant_id=uuid.UUID(tenant_id),
        customer_id=uuid.UUID(data.customer_id),
        account_number=data.account_number,
        customer_snapshot=data.customer_snapshot,
        cancel_reason=data.cancel_reason,
        source_channel=data.source_channel,
        matched_journey_id=uuid.UUID(result["journey"]["id"]) if result.get("journey") else None,
        matched_offer_id=uuid.UUID(result["offer"]["id"]) if result.get("offer") else None,
        status="offer_shown" if result.get("offer") else "pending",
    )
    session.add(cancel_event)
    await session.flush()

    # 6. Update journey stats
    if result.get("journey"):
        await session.execute(
            update(RetentionJourney)
            .where(RetentionJourney.id == uuid.UUID(result["journey"]["id"]))
            .values(
                times_triggered=RetentionJourney.times_triggered + 1,
                times_shown=RetentionJourney.times_shown + 1,
            )
        )

    return {
        "cancel_event_id": str(cancel_event.id),
        "matched": result["matched"],
        "journey": result.get("journey"),
        "offer": result.get("offer"),
        "estimated_cost": float(result.get("cost", 0)),
    }


@app.post("/cancel/respond")
async def respond_to_offer(
    data: CancelRespond,
    session: AsyncSession = Depends(get_db),
):
    """Customer accepts or rejects the retention offer.

    Called by the portal when the customer clicks "Accept Offer" or "Proceed with Cancel".
    """
    # 1. Load the cancel event
    query = select(CancelEvent).where(
        CancelEvent.id == uuid.UUID(data.cancel_event_id)
    )
    result = await session.execute(query)
    cancel_event = result.scalar_one_or_none()
    if not cancel_event:
        raise HTTPException(404, "Cancel event not found")

    if cancel_event.status not in ("pending", "offer_shown"):
        raise HTTPException(400, f"Cannot respond to cancel event in status: {cancel_event.status}")

    # 2. Update cancel event
    now = datetime.now(timezone.utc)
    cancel_event.resolved_at = now

    if data.decision == "accept":
        cancel_event.status = "accepted"
    elif data.decision == "reject":
        cancel_event.status = "rejected"
    else:
        raise HTTPException(400, "Decision must be 'accept' or 'reject'")

    # 3. Load offer for cost calculation
    offer = None
    if cancel_event.matched_offer_id:
        offer_query = select(RetentionOffer).where(
            RetentionOffer.id == cancel_event.matched_offer_id
        )
        offer_result = await session.execute(offer_query)
        offer = offer_result.scalar_one_or_none()

    # 4. Compute outcome
    monthly_before = Decimal(
        str(cancel_event.customer_snapshot.get("monthly_spend_zar", "0"))
    )
    outcome_result = compute_outcome_result(
        outcome_type=cancel_event.status,
        offer=_offer_to_dict(offer) if offer else None,
        customer=cancel_event.customer_snapshot,
        monthly_revenue_before=monthly_before,
    )

    # 5. Record outcome
    outcome = JourneyOutcome(
        tenant_id=cancel_event.tenant_id,
        cancel_event_id=cancel_event.id,
        journey_id=cancel_event.matched_journey_id,
        offer_id=cancel_event.matched_offer_id,
        customer_id=cancel_event.customer_id,
        outcome=outcome_result["outcome"],
        monthly_revenue_before=monthly_before,
        monthly_revenue_after=Decimal(str(outcome_result["monthly_revenue_after"]))
            if outcome_result.get("monthly_revenue_after") is not None else None,
        discount_cost_zar=Decimal(str(outcome_result["discount_cost_zar"])),
        customer_features=cancel_event.customer_snapshot,
        response_time_seconds=data.response_time_seconds,
    )
    session.add(outcome)

    # 6. Update journey stats
    if cancel_event.matched_journey_id:
        if data.decision == "accept":
            await session.execute(
                update(RetentionJourney)
                .where(RetentionJourney.id == cancel_event.matched_journey_id)
                .values(
                    times_accepted=RetentionJourney.times_accepted + 1,
                    revenue_preserved=RetentionJourney.revenue_preserved + monthly_before,
                )
            )
        else:
            await session.execute(
                update(RetentionJourney)
                .where(RetentionJourney.id == cancel_event.matched_journey_id)
                .values(
                    times_rejected=RetentionJourney.times_rejected + 1,
                )
            )

    # 7. Update offer redemption count
    if offer and data.decision == "accept":
        offer.total_redemptions += 1

    return {
        "status": cancel_event.status,
        "outcome": outcome_result,
        "message": "Offer accepted — retention applied" if data.decision == "accept"
                  else "Offer rejected — cancellation proceeding",
    }


# ---------------------------------------------------------------------------
# Cancellation Workflow — triggered when customer rejects retention offer
# ---------------------------------------------------------------------------

from services.journey_engine.models import CancellationWorkflow


@app.post("/cancellation-workflows")
async def create_cancellation_workflow(
    data: CancelWorkflowCreate,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_db),
):
    """Create a cancellation workflow to terminate a service after retention failure."""
    # 1. Load the cancel event
    cancel_event = await session.get(CancelEvent, uuid.UUID(data.cancel_event_id))
    if not cancel_event:
        raise HTTPException(404, "Cancel event not found")

    # 2. Find the active network service for this customer
    from services.network.models import NetworkService
    svc_query = select(NetworkService).where(
        NetworkService.tenant_id == cancel_event.tenant_id,
        NetworkService.customer_id == cancel_event.customer_id,
        NetworkService.status.in_(("active", "provisioning")),
    ).order_by(NetworkService.created_at.desc())
    svc_result = await session.execute(svc_query)
    service = svc_result.scalar_one_or_none()
    if not service:
        raise HTTPException(404, "No active network service found for this customer")

    # 3. Find router device for return tracking
    from services.network.models import NetworkDevice
    dev_query = select(NetworkDevice).where(
        NetworkDevice.service_id == service.id,
        NetworkDevice.device_type.in_(("router", "gateway")),
    )
    dev_result = await session.execute(dev_query)
    router_device = dev_result.scalar_one_or_none()

    # 4. Create workflow
    workflow = CancellationWorkflow(
        tenant_id=cancel_event.tenant_id,
        customer_id=cancel_event.customer_id,
        cancel_event_id=cancel_event.id,
        service_id=service.id,
        fno_name=service.fno_provider,
        fno_account_number=service.fno_account_id,
        fno_service_reference=service.service_reference,
        status="pending",
        router_device_id=router_device.id if router_device else None,
        router_serial_number=router_device.serial_number if router_device else None,
        router_return_status="pending" if router_device else "not_required",
        cancellation_reason=cancel_event.cancel_reason_detail or cancel_event.cancel_reason,
    )
    session.add(workflow)
    await session.flush()

    # 5. Trigger FNO cancellation in background
    background_tasks.add_task(
        _execute_fno_cancellation,
        workflow.id,
        service.id,
        cancel_event.tenant_id,
    )

    return {
        "workflow_id": str(workflow.id),
        "service_id": str(service.id),
        "fno_name": service.fno_provider,
        "status": "pending",
        "router_return_required": router_device is not None,
    }


class CancelWorkflowCreate(BaseModel):
    cancel_event_id: str
    reason: Optional[str] = None


async def _execute_fno_cancellation(workflow_id: uuid.UUID, service_id: uuid.UUID, tenant_id: uuid.UUID):
    """Background task: submit FNO cancellation order and update workflow."""
    from services.journey_engine.database import get_session as _get_session
    from services.network.models import NetworkService, FNOOrder

    async with _get_session() as session:
        workflow = await session.get(CancellationWorkflow, workflow_id)
        service = await session.get(NetworkService, service_id)
        if not workflow or not service:
            return

        workflow.status = "fno_cancellation_submitted"
        workflow.fno_cancellation_submitted_at = datetime.now(timezone.utc)

        # Create FNO cancellation order
        fno_order = FNOOrder(
            tenant_id=tenant_id,
            service_id=service_id,
            fno_provider=service.fno_provider,
            order_type="cancellation",
            status="submitted",
            request_payload={
                "fno_account_id": service.fno_account_id,
                "service_reference": service.service_reference,
                "reason": workflow.cancellation_reason,
                "workflow_id": str(workflow_id),
            },
        )
        session.add(fno_order)
        await session.flush()

        workflow.fno_cancellation_order_id = fno_order.id
        await session.flush()

        # TODO: In production, call FNO adapter to submit cancellation
        # adapter = FNOFactory.get_adapter(service.fno_provider, config)
        # result = await adapter.cancel_order(service.fno_account_id)


@app.get("/cancellation-workflows")
async def list_cancellation_workflows(
    tenant_id: str = Query(...),
    status_filter: Optional[str] = Query(None, alias="status"),
    customer_id: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_db),
):
    """List cancellation workflows."""
    query = select(CancellationWorkflow).where(
        CancellationWorkflow.tenant_id == uuid.UUID(tenant_id)
    )
    if status_filter:
        query = query.where(CancellationWorkflow.status == status_filter)
    if customer_id:
        query = query.where(CancellationWorkflow.customer_id == uuid.UUID(customer_id))
    result = await session.execute(query.order_by(CancellationWorkflow.created_at.desc()))
    workflows = result.scalars().all()
    return [{
        "id": str(w.id), "customer_id": str(w.customer_id),
        "fno_name": w.fno_name, "status": w.status,
        "router_return_status": w.router_return_status,
        "created_at": w.created_at.isoformat(),
    } for w in workflows]


@app.get("/cancellation-workflows/{workflow_id}")
async def get_cancellation_workflow(
    workflow_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
):
    """Get cancellation workflow details."""
    workflow = await session.get(CancellationWorkflow, workflow_id)
    if not workflow:
        raise HTTPException(404, "Workflow not found")
    return {
        "id": str(workflow.id), "customer_id": str(workflow.customer_id),
        "service_id": str(workflow.service_id), "fno_name": workflow.fno_name,
        "status": workflow.status, "fno_cancellation_reference": workflow.fno_cancellation_reference,
        "router_return_status": workflow.router_return_status,
        "router_serial": workflow.router_serial_number,
        "early_termination_fee": float(workflow.early_termination_fee_zar) if workflow.early_termination_fee_zar else None,
        "created_at": workflow.created_at.isoformat(),
    }


@app.post("/cancellation-workflows/{workflow_id}/confirm-fno")
async def confirm_fno_cancellation(
    workflow_id: uuid.UUID,
    fno_reference: str = Query(...),
    session: AsyncSession = Depends(get_db),
):
    """Confirm FNO cancellation (called by FNO webhook or admin)."""
    workflow = await session.get(CancellationWorkflow, workflow_id)
    if not workflow:
        raise HTTPException(404, "Workflow not found")

    workflow.status = "fno_cancellation_confirmed"
    workflow.fno_cancellation_confirmed_at = datetime.now(timezone.utc)
    workflow.fno_cancellation_reference = fno_reference

    # Update FNO order status
    if workflow.fno_cancellation_order_id:
        order = await session.get(FNOOrder, workflow.fno_cancellation_order_id)
        if order:
            order.status = "completed"
            order.completed_date = datetime.now(timezone.utc)
            order.fno_reference = fno_reference

    await session.flush()
    return {"id": str(workflow.id), "status": workflow.status, "fno_reference": fno_reference}


@app.post("/cancellation-workflows/{workflow_id}/schedule-router-return")
async def schedule_router_return(
    workflow_id: uuid.UUID,
    scheduled_date: datetime = Query(...),
    notes: Optional[str] = None,
    session: AsyncSession = Depends(get_db),
):
    """Schedule a router/ONT collection."""
    workflow = await session.get(CancellationWorkflow, workflow_id)
    if not workflow:
        raise HTTPException(404, "Workflow not found")

    workflow.router_return_status = "scheduled"
    workflow.router_return_scheduled_date = scheduled_date
    if notes:
        workflow.router_return_notes = notes

    await session.flush()
    return {"id": str(workflow.id), "router_return_status": "scheduled", "scheduled_date": scheduled_date.isoformat()}


@app.post("/cancellation-workflows/{workflow_id}/complete-router-return")
async def complete_router_return(
    workflow_id: uuid.UUID,
    notes: Optional[str] = None,
    session: AsyncSession = Depends(get_db),
):
    """Mark router/ONT as returned and complete the workflow."""
    workflow = await session.get(CancellationWorkflow, workflow_id)
    if not workflow:
        raise HTTPException(404, "Workflow not found")

    now = datetime.now(timezone.utc)
    workflow.router_return_status = "returned"
    workflow.router_return_completed_at = now
    workflow.status = "router_return_completed"
    if notes:
        workflow.router_return_notes = notes

    # Terminate the network service
    from services.network.models import NetworkService, RadiusAccount
    service = await session.get(NetworkService, workflow.service_id)
    if service and service.status != "terminated":
        service.status = "terminated"
        service.terminated_at = now
        workflow.service_terminated_at = now

        # Disable RADIUS
        radius_query = select(RadiusAccount).where(RadiusAccount.service_id == workflow.service_id)
        radius_result = await session.execute(radius_query)
        radius = radius_result.scalar_one_or_none()
        if radius:
            radius.status = "disabled"

    # Check if workflow is fully complete
    if workflow.status == "router_return_completed" and workflow.service_terminated_at:
        workflow.status = "completed"
        workflow.workflow_completed_at = now

    await session.flush()
    return {
        "id": str(workflow.id),
        "router_return_status": "returned",
        "service_terminated": True,
        "workflow_status": workflow.status,
    }



# ---------------------------------------------------------------------------
# Customer Snapshot Sync (from CRM)
# ---------------------------------------------------------------------------

class CustomerSnapshotUpsert(BaseModel):
    customer_id: str
    tenant_id: str
    account_number: Optional[str] = None
    snapshot_data: dict = Field(default_factory=dict)
    source_event: str = "status_change"
    crm_updated_at: Optional[datetime] = None


@app.post("/customers/snapshot")
async def upsert_customer_snapshot(
    payload: CustomerSnapshotUpsert,
    db: AsyncSession = Depends(get_db),
):
    """Receive a customer snapshot push from CRM (on status change, churn risk, etc.)."""
    from services.journey_engine.models import CustomerSnapshot

    now = datetime.now(timezone.utc)

    stmt = pg_insert(CustomerSnapshot).values(
        tenant_id=uuid.UUID(payload.tenant_id),
        customer_id=uuid.UUID(payload.customer_id),
        account_number=payload.account_number,
        snapshot_data=payload.snapshot_data,
        source_event=payload.source_event,
        crm_updated_at=payload.crm_updated_at or now,
        updated_at=now,
    ).on_conflict_do_update(
        index_elements=["customer_id"],
        set_={
            "account_number": payload.account_number,
            "snapshot_data": payload.snapshot_data,
            "source_event": payload.source_event,
            "crm_updated_at": payload.crm_updated_at or now,
            "updated_at": now,
        },
    )
    await db.execute(stmt)
    return {"status": "ok", "customer_id": payload.customer_id, "source_event": payload.source_event}


@app.get("/snapshots")
async def list_snapshots(
    tenant_id: str,
    limit: int = 100,
    offset: int = 0,
    session: AsyncSession = Depends(get_db),
):
    """List customer snapshots for a tenant."""
    query = (
        select(CustomerSnapshot)
        .where(CustomerSnapshot.tenant_id == uuid.UUID(tenant_id))
        .order_by(CustomerSnapshot.updated_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(query)
    snapshots = result.scalars().all()
    return [
        {
            "customer_id": str(s.customer_id),
            "tenant_id": str(s.tenant_id),
            "account_number": s.account_number,
            "snapshot_data": s.snapshot_data,
            "source_event": s.source_event,
            "updated_at": s.updated_at.isoformat() if s.updated_at else None,
        }
        for s in snapshots
    ]


@app.get("/snapshots/{customer_id}")
async def get_snapshot(
    customer_id: str,
    tenant_id: str,
    session: AsyncSession = Depends(get_db),
):
    """Get a specific customer snapshot."""
    result = await session.execute(
        select(CustomerSnapshot).where(
            CustomerSnapshot.customer_id == uuid.UUID(customer_id),
            CustomerSnapshot.tenant_id == uuid.UUID(tenant_id),
        )
    )
    snap = result.scalar_one_or_none()
    if not snap:
        raise HTTPException(status_code=404, detail="Customer snapshot not found")
    return {
        "customer_id": str(snap.customer_id),
        "tenant_id": str(snap.tenant_id),
        "account_number": snap.account_number,
        "snapshot_data": snap.snapshot_data,
        "source_event": snap.source_event,
        "updated_at": snap.updated_at.isoformat() if snap.updated_at else None,
    }


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------

@app.get("/analytics/funnel")
async def get_funnel(
    tenant_id: str,
    journey_id: Optional[str] = None,
    days: int = 30,
    session: AsyncSession = Depends(get_db),
):
    """Get journey funnel: triggered → shown → accepted / rejected."""
    from datetime import timedelta

    since = datetime.now(timezone.utc) - timedelta(days=days)

    query = select(RetentionJourney).where(
        RetentionJourney.tenant_id == uuid.UUID(tenant_id),
    )
    if journey_id:
        query = query.where(RetentionJourney.id == uuid.UUID(journey_id))

    result = await session.execute(query)
    journeys = result.scalars().all()

    funnel = []
    for j in journeys:
        funnel.append({
            "journey_id": str(j.id),
            "journey_name": j.name,
            "triggered": j.times_triggered,
            "shown": j.times_shown,
            "accepted": j.times_accepted,
            "rejected": j.times_rejected,
            "acceptance_rate": round(j.times_accepted / j.times_shown * 100, 1)
                if j.times_shown > 0 else 0,
            "revenue_preserved": float(j.revenue_preserved),
        })

    return {"funnel": funnel, "period_days": days}


@app.get("/analytics/outcomes")
async def get_outcomes(
    tenant_id: str,
    journey_id: Optional[str] = None,
    outcome_type: Optional[str] = None,
    limit: int = 100,
    session: AsyncSession = Depends(get_db),
):
    """Get outcome records for ML feedback and analysis."""
    query = select(JourneyOutcome).where(
        JourneyOutcome.tenant_id == uuid.UUID(tenant_id),
    )
    if journey_id:
        query = query.where(JourneyOutcome.journey_id == uuid.UUID(journey_id))
    if outcome_type:
        query = query.where(JourneyOutcome.outcome == outcome_type)

    query = query.order_by(JourneyOutcome.created_at.desc()).limit(limit)
    result = await session.execute(query)
    outcomes = result.scalars().all()

    return {
        "outcomes": [_outcome_to_dict(o) for o in outcomes],
        "summary": {
            "total": len(outcomes),
            "accepted": sum(1 for o in outcomes if o.outcome == "accepted"),
            "rejected": sum(1 for o in outcomes if o.outcome == "rejected"),
            "total_discount_cost": float(sum(
                (o.discount_cost_zar or Decimal("0")) for o in outcomes
            )),
        },
    }


@app.get("/analytics/roi")
async def get_roi(
    tenant_id: str,
    days: int = 30,
    session: AsyncSession = Depends(get_db),
):
    """Get ROI analysis by journey and offer."""
    from datetime import timedelta

    since = datetime.now(timezone.utc) - timedelta(days=days)

    # Aggregate outcomes by journey
    query = (
        select(
            JourneyOutcome.journey_id,
            func.count(JourneyOutcome.id).label("total"),
            func.sum(
                case((JourneyOutcome.outcome == "accepted", 1), else_=0)
            ).label("accepted"),
            func.sum(JourneyOutcome.discount_cost_zar).label("total_cost"),
            func.sum(JourneyOutcome.monthly_revenue_before).label("revenue_at_risk"),
        )
        .where(
            JourneyOutcome.tenant_id == uuid.UUID(tenant_id),
            JourneyOutcome.created_at >= since,
        )
        .group_by(JourneyOutcome.journey_id)
    )
    result = await session.execute(query)
    rows = result.all()

    roi_data = []
    for row in rows:
        cost = float(row.total_cost or 0)
        revenue = float(row.revenue_at_risk or 0)
        roi_pct = round((revenue - cost) / cost * 100, 1) if cost > 0 else 0

        # Get journey name
        j_query = select(RetentionJourney.name).where(RetentionJourney.id == row.journey_id)
        j_result = await session.execute(j_query)
        j_name = j_result.scalar() or "Unknown"

        roi_data.append({
            "journey_id": str(row.journey_id) if row.journey_id else None,
            "journey_name": j_name,
            "total_events": row.total,
            "accepted": row.accepted,
            "acceptance_rate": round(row.accepted / row.total * 100, 1) if row.total > 0 else 0,
            "total_discount_cost": cost,
            "revenue_at_risk": revenue,
            "roi_percent": roi_pct,
        })

    return {"roi": roi_data, "period_days": days}


@app.get("/attributes")
async def list_attributes():
    """List available customer attributes for rule building."""
    return {
        "attributes": [
            {
                "name": name,
                "type": type_,
                "description": _attr_description(name),
            }
            for name, type_ in ATTRIBUTE_TYPES.items()
        ],
        "operators": [
            {"op": "eq", "label": "Equals", "types": ["string", "number", "boolean"]},
            {"op": "ne", "label": "Not equals", "types": ["string", "number", "boolean"]},
            {"op": "gt", "label": "Greater than", "types": ["number"]},
            {"op": "gte", "label": "Greater than or equal", "types": ["number"]},
            {"op": "lt", "label": "Less than", "types": ["number"]},
            {"op": "lte", "label": "Less than or equal", "types": ["number"]},
            {"op": "between", "label": "Between (range)", "types": ["number"]},
            {"op": "in", "label": "In list", "types": ["string", "number"]},
            {"op": "not_in", "label": "Not in list", "types": ["string"]},
            {"op": "contains", "label": "Contains", "types": ["string"]},
        ],
        "offer_types": [
            {"type": "percentage_discount", "label": "Percentage Discount", "params": {"percent": "number", "duration_months": "number"}},
            {"type": "fixed_discount", "label": "Fixed Amount Discount", "params": {"amount_zar": "number", "duration_months": "number"}},
            {"type": "plan_downgrade", "label": "Plan Downgrade", "params": {"target_plan_id": "string", "new_monthly_price_zar": "number"}},
            {"type": "service_pause", "label": "Service Pause", "params": {"duration_months": "number", "reactivate_auto": "boolean"}},
            {"type": "free_months", "label": "Free Months", "params": {"months": "number"}},
            {"type": "loyalty_reward", "label": "Loyalty Reward (Data/VAS)", "params": {"data_gb": "number", "vas_product_id": "string"}},
            {"type": "personal_outreach", "label": "Personal Outreach", "params": {"priority": "string", "assign_team": "string"}},
        ],
    }


# ---------------------------------------------------------------------------
# Outcome Batch Processing — retention flag checks
# ---------------------------------------------------------------------------


@app.post("/outcomes/process", tags=["Outcomes"])
@app.post("/outcomes/process/")
async def outcomes_process(
    data: OutcomesProcessRequest,
    session: AsyncSession = Depends(get_db),
):
    """Trigger the daily outcome batch job to check 90d/180d retention flags.

    Scans JourneyOutcome records for accepted offers and verifies whether
    customers are still active at the 90-day and 180-day marks by checking
    their latest CustomerSnapshot from CRM.

    Can be run on-demand or scheduled via cron. Use dry_run=true to preview
    results without persisting changes.
    """
    result = await process_outcomes(
        session=session,
        tenant_id=data.tenant_id,
        dry_run=data.dry_run,
    )
    return result


@app.get("/outcome-stats", tags=["Outcomes"])
@app.get("/outcome-stats/")
async def outcome_stats(
    session: AsyncSession = Depends(get_db),
):
    """Get current outcome statistics — pending checks and retention distribution."""
    stats = await get_outcome_stats(session)
    return stats


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _journey_to_dict(journey, include_rules=False):
    d = {
        "id": str(journey.id),
        "tenant_id": str(journey.tenant_id),
        "name": journey.name,
        "description": journey.description,
        "trigger_event": journey.trigger_event,
        "status": journey.status,
        "priority": journey.priority,
        "offer_id": str(journey.offer_id) if journey.offer_id else None,
        "fallback_offer_id": str(journey.fallback_offer_id) if journey.fallback_offer_id else None,
        "channel": journey.channel,
        "ab_test_enabled": journey.ab_test_enabled,
        "ab_test_config": journey.ab_test_config,
        "times_triggered": journey.times_triggered,
        "times_shown": journey.times_shown,
        "times_accepted": journey.times_accepted,
        "times_rejected": journey.times_rejected,
        "revenue_preserved": float(journey.revenue_preserved),
        "created_at": journey.created_at.isoformat() if journey.created_at else None,
        "updated_at": journey.updated_at.isoformat() if journey.updated_at else None,
    }
    if include_rules and hasattr(journey, "rules"):
        d["rules"] = [_rule_to_dict(r) for r in journey.rules]
    return d


def _rule_to_dict(rule):
    return {
        "id": str(rule.id),
        "journey_id": str(rule.journey_id),
        "rule_group": rule.rule_group,
        "attribute": rule.attribute,
        "operator": rule.operator,
        "value": rule.value,
        "is_active": rule.is_active,
        "sort_order": rule.sort_order,
    }


def _offer_to_dict(offer):
    if offer is None:
        return None
    return {
        "id": str(offer.id),
        "tenant_id": str(offer.tenant_id),
        "name": offer.name,
        "description": offer.description,
        "offer_type": offer.offer_type,
        "parameters": offer.parameters,
        "max_per_customer": offer.max_per_customer,
        "max_total_redemptions": offer.max_total_redemptions,
        "total_redemptions": offer.total_redemptions,
        "estimated_cost_per_use": float(offer.estimated_cost_per_use) if offer.estimated_cost_per_use else None,
        "status": offer.status,
        "created_at": offer.created_at.isoformat() if offer.created_at else None,
        "updated_at": offer.updated_at.isoformat() if offer.updated_at else None,
    }


def _outcome_to_dict(outcome):
    return {
        "id": str(outcome.id),
        "cancel_event_id": str(outcome.cancel_event_id),
        "journey_id": str(outcome.journey_id) if outcome.journey_id else None,
        "offer_id": str(outcome.offer_id) if outcome.offer_id else None,
        "customer_id": str(outcome.customer_id),
        "outcome": outcome.outcome,
        "monthly_revenue_before": float(outcome.monthly_revenue_before),
        "monthly_revenue_after": float(outcome.monthly_revenue_after) if outcome.monthly_revenue_after else None,
        "discount_cost_zar": float(outcome.discount_cost_zar),
        "retained_90d": outcome.retained_90d,
        "retained_180d": outcome.retained_180d,
        "response_time_seconds": outcome.response_time_seconds,
        "created_at": outcome.created_at.isoformat() if outcome.created_at else None,
    }


async def _get_journey_tenant(journey_id: str, session: AsyncSession) -> uuid.UUID:
    query = select(RetentionJourney.tenant_id).where(
        RetentionJourney.id == uuid.UUID(journey_id)
    )
    result = await session.execute(query)
    tenant_id = result.scalar_one_or_none()
    if not tenant_id:
        raise HTTPException(404, "Journey not found")
    return tenant_id


def _attr_description(name: str) -> str:
    descriptions = {
        "risk_score": "AI churn prediction score (0-100)",
        "segment": "Customer segment (Enterprise, Business, Premium, Standard, Basic)",
        "tenure_months": "Months as a customer",
        "monthly_spend_zar": "Monthly recurring revenue in ZAR",
        "payment_days_overdue": "Days since last successful payment",
        "num_support_tickets_30d": "Support tickets in last 30 days",
        "plan_type": "Current plan identifier",
        "region": "Geographic region",
        "usage_trend": "Bandwidth usage trend (declining, stable, growing)",
        "churn_reason": "Reason for cancellation (from customer)",
        "competitor_mention": "Whether customer mentioned a competitor",
        "autopay_enabled": "Whether autopay/debit order is active",
    }
    return descriptions.get(name, name)


@app.get("/")
async def root():
    return {
        "service": "OmniDome Journey Engine",
        "version": "1.0.0",
        "status": "active",
        "endpoints": {
            "journeys": "/journeys",
            "offers": "/offers",
            "cancel_trigger": "POST /cancel/trigger",
            "cancel_respond": "POST /cancel/respond",
            "funnel": "/analytics/funnel",
            "outcomes": "/analytics/outcomes",
            "roi": "/analytics/roi",
            "attributes": "/attributes",
        },
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8017)
