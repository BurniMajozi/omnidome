"""OmniDome Sales Service — async SQLAlchemy version.

Manages pipeline, deals, quotes, commissions, and sales targets.

Port: 8002 (configurable via PORT env)
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
import os
import uuid
from typing import Any, Dict, List, Optional

import httpx
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update, and_, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from services.sales.database import get_db, init_tables
from services.sales.models import (
    Pipeline, DealStage, Deal, Quote, Commission, Target, Contact, Lead,
)
from services.common.auth import get_current_tenant_id

app = FastAPI(title="OmniDome Sales Service", version="2.0.0")


# ── Pydantic Schemas ──────────────────────────────────────────────────

class PipelineStage(BaseModel):
    id: uuid.UUID
    name: str
    probability: int
    sort_order: int


class PipelineStageCreate(BaseModel):
    name: str
    probability: int = 10
    sort_order: Optional[int] = None


class PipelineOverviewStage(BaseModel):
    id: uuid.UUID
    name: str
    probability: int
    sort_order: int
    deal_count: int
    total_value_zar: Decimal


class DealCreate(BaseModel):
    name: str
    customer_id: uuid.UUID
    lead_id: Optional[uuid.UUID] = None
    agent_id: Optional[uuid.UUID] = None
    stage_id: Optional[uuid.UUID] = None
    stage_name: Optional[str] = None
    package_id: Optional[uuid.UUID] = None
    value_zar: Decimal
    close_date: Optional[date] = None
    notes: Optional[str] = None


class DealUpdate(BaseModel):
    name: Optional[str] = None
    value_zar: Optional[Decimal] = None
    agent_id: Optional[uuid.UUID] = None
    package_id: Optional[uuid.UUID] = None
    stage_id: Optional[uuid.UUID] = None
    stage_name: Optional[str] = None
    close_date: Optional[date] = None
    notes: Optional[str] = None


class DealStageUpdate(BaseModel):
    stage_id: Optional[uuid.UUID] = None
    stage_name: Optional[str] = None
    direction: Optional[str] = Field(default=None, description="next or previous")


class DealResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    customer_id: uuid.UUID
    lead_id: Optional[uuid.UUID]
    agent_id: Optional[uuid.UUID]
    stage_id: Optional[uuid.UUID]
    stage_name: Optional[str]
    package_id: Optional[uuid.UUID]
    value_zar: Decimal
    status: str
    close_date: Optional[date]
    closed_at: Optional[datetime]
    close_reason: Optional[str]
    notes: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime]


class QuoteItem(BaseModel):
    description: str
    quantity: int = 1
    unit_price_zar: Decimal
    charge_type: str = "monthly"


class QuoteCreate(BaseModel):
    customer_id: uuid.UUID
    deal_id: Optional[uuid.UUID] = None
    lead_id: Optional[uuid.UUID] = None
    agent_id: Optional[uuid.UUID] = None
    package_id: Optional[uuid.UUID] = None
    items: Optional[List[QuoteItem]] = None
    total_monthly: Optional[Decimal] = None
    total_once_off: Optional[Decimal] = None
    term_months: int = 12
    valid_days: int = 14
    discount_percent: Optional[Decimal] = None
    terms: Optional[str] = None


class QuoteResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    deal_id: Optional[uuid.UUID]
    customer_id: uuid.UUID
    lead_id: Optional[uuid.UUID]
    agent_id: Optional[uuid.UUID]
    package_id: Optional[uuid.UUID]
    items: Optional[List[QuoteItem]]
    total_monthly: Decimal
    total_once_off: Decimal
    term_months: int
    valid_until: date
    status: str
    terms: Optional[str]
    created_at: datetime
    sent_at: Optional[datetime]
    accepted_at: Optional[datetime]


class QuoteSend(BaseModel):
    channel: str = "email"
    recipient: Optional[str] = None


class QuoteAccept(BaseModel):
    create_deal: bool = True
    stage_name: Optional[str] = None


class CommissionResponse(BaseModel):
    id: uuid.UUID
    deal_id: uuid.UUID
    agent_id: uuid.UUID
    amount_zar: Decimal
    rate_percent: Optional[Decimal]
    status: str
    created_at: datetime
    updated_at: Optional[datetime]


class CommissionReportEntry(BaseModel):
    agent_id: uuid.UUID
    total_amount_zar: Decimal
    deals_count: int
    pending: int
    approved: int
    paid: int
    clawback: int


class TargetCreate(BaseModel):
    agent_id: Optional[uuid.UUID] = None
    team_id: Optional[uuid.UUID] = None
    period_type: str = "MONTHLY"
    period_start: date
    period_end: date
    target_value_zar: Decimal


class TargetPerformanceEntry(BaseModel):
    target_id: uuid.UUID
    agent_id: Optional[uuid.UUID]
    team_id: Optional[uuid.UUID]
    period_start: date
    period_end: date
    target_value_zar: Decimal
    actual_value_zar: Decimal
    variance_zar: Decimal


# ── Lead Schemas ──────────────────────────────────────────────────────

class LeadCreate(BaseModel):
    first_name: str
    last_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    source: str = "FIELD_VISIT"
    interest_level: int = Field(default=3, ge=1, le=5)
    notes: Optional[str] = None
    agent_id: Optional[uuid.UUID] = None


class LeadUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    source: Optional[str] = None
    interest_level: Optional[int] = Field(None, ge=1, le=5)
    status: Optional[str] = None
    notes: Optional[str] = None
    agent_id: Optional[uuid.UUID] = None


class LeadResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    contact_id: Optional[uuid.UUID]
    agent_id: Optional[uuid.UUID]
    first_name: str
    last_name: str
    email: Optional[str]
    phone: Optional[str]
    address: Optional[str]
    source: str
    interest_level: int
    status: str
    notes: Optional[str]
    converted_at: Optional[datetime]
    created_at: datetime
    updated_at: Optional[datetime]




class LeadConvert(BaseModel):
    name: Optional[str] = Field(None, description="Deal name (defaults to lead name)")
    value_zar: Decimal = Field(default=Decimal("0"), ge=0)
    agent_id: Optional[uuid.UUID] = None

# ── Contact Schemas ───────────────────────────────────────────────────

class ContactCreate(BaseModel):
    first_name: str
    last_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    physical_address: Optional[str] = None
    postal_code: Optional[str] = None
    city: Optional[str] = None
    province: Optional[str] = None
    rica_id_number: Optional[str] = None


class ContactUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    physical_address: Optional[str] = None
    postal_code: Optional[str] = None
    city: Optional[str] = None
    province: Optional[str] = None
    rica_id_number: Optional[str] = None
    status: Optional[str] = None
    lifecycle_stage: Optional[str] = None
    nps_score: Optional[int] = None


class ContactResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    first_name: str
    last_name: str
    email: Optional[str]
    phone: Optional[str]
    physical_address: Optional[str]
    city: Optional[str]
    province: Optional[str]
    rica_verified: bool
    status: str
    lifecycle_stage: str
    nps_score: Optional[int]
    created_at: datetime
    updated_at: Optional[datetime]


class Customer360Response(BaseModel):
    contact: ContactResponse
    deals: List[DealResponse]
    quotes: List[QuoteResponse]
    invoices: List[dict]
    total_revenue: float
    open_deals_value: float

DEFAULT_STAGES = [
    {"name": "Prospecting", "probability": 10, "sort_order": 1},
    {"name": "Qualified", "probability": 25, "sort_order": 2},
    {"name": "Proposal", "probability": 40, "sort_order": 3},
    {"name": "Negotiation", "probability": 60, "sort_order": 4},
    {"name": "Closed Won", "probability": 100, "sort_order": 5},
    {"name": "Closed Lost", "probability": 0, "sort_order": 6},
]

# ── Webhook config ────────────────────────────────────────────────────

BILLING_WEBHOOK_URL = os.getenv("BILLING_WEBHOOK_URL")
NETWORK_WEBHOOK_URL = os.getenv("NETWORK_WEBHOOK_URL")
PROVISIONING_WEBHOOKS = [
    url.strip()
    for url in os.getenv("SALES_PROVISIONING_WEBHOOKS", "").split(",")
    if url.strip()
]

LIFECYCLE_URL = os.getenv("LIFECYCLE_SERVICE_URL", "http://lifecycle:8018")


# ── Helpers ───────────────────────────────────────────────────────────

async def _ensure_default_pipeline(db: AsyncSession, tenant_id: uuid.UUID) -> uuid.UUID:
    result = await db.execute(
        select(Pipeline).where(
            Pipeline.tenant_id == tenant_id,
            Pipeline.is_default == True,  # noqa: E712
        )
    )
    pipeline = result.scalar_one_or_none()
    if pipeline:
        return pipeline.id

    pipeline_id = uuid.uuid4()
    pipeline = Pipeline(
        id=pipeline_id, tenant_id=tenant_id, name="Default Pipeline", is_default=True,
    )
    db.add(pipeline)
    await db.flush()

    # Create default stages
    for stage_def in DEFAULT_STAGES:
        stage = DealStage(
            id=uuid.uuid4(),
            pipeline_id=pipeline_id,
            name=stage_def["name"],
            probability=stage_def["probability"],
            sort_order=stage_def["sort_order"],
        )
        db.add(stage)
    await db.flush()
    return pipeline_id


async def _get_stages(db: AsyncSession, pipeline_id: uuid.UUID) -> List[DealStage]:
    result = await db.execute(
        select(DealStage)
        .where(DealStage.pipeline_id == pipeline_id)
        .order_by(DealStage.sort_order)
    )
    return list(result.scalars().all())


async def _resolve_stage_id(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    stage_id: Optional[uuid.UUID],
    stage_name: Optional[str],
) -> uuid.UUID:
    pipeline_id = await _ensure_default_pipeline(db, tenant_id)
    if stage_id:
        return stage_id
    if stage_name:
        result = await db.execute(
            select(DealStage.id).where(
                DealStage.pipeline_id == pipeline_id,
                func.lower(DealStage.name) == stage_name.lower(),
            )
        )
        row = result.scalar_one_or_none()
        if row:
            return row
    stages = await _get_stages(db, pipeline_id)
    if not stages:
        raise HTTPException(status_code=500, detail="Pipeline stages missing")
    return stages[0].id


async def _get_closed_stage_id(
    db: AsyncSession, tenant_id: uuid.UUID, name: str,
) -> Optional[uuid.UUID]:
    pipeline_id = await _ensure_default_pipeline(db, tenant_id)
    result = await db.execute(
        select(DealStage.id).where(
            DealStage.pipeline_id == pipeline_id,
            func.lower(DealStage.name) == name.lower(),
        )
    )
    return result.scalar_one_or_none()


async def _notify_lifecycle_won(db: AsyncSession, deal: Deal, tenant_id: uuid.UUID):
    """When a deal is closed-won, notify the lifecycle service."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(
                f"{LIFECYCLE_URL}/events",
                json={
                    "customer_id": str(deal.contact_id),
                    "event_type": "sale_closed_won",
                    "source": "sales",
                    "metadata": {
                        "deal_id": str(deal.id),
                        "deal_value_zar": float(deal.value_zar or 0),
                        "tenant_id": str(tenant_id),
                    },
                },
            )
    except Exception:
        pass  # non-blocking


def _calculate_quote_totals(items: Optional[List[QuoteItem]]) -> Dict[str, Decimal]:
    total_m = Decimal("0")
    total_o = Decimal("0")
    if not items:
        return {"total_monthly": total_m, "total_once_off": total_o}
    for item in items:
        line = item.unit_price_zar * item.quantity
        if item.charge_type.lower() == "once_off":
            total_o += line
        else:
            total_m += line
    return {"total_monthly": total_m, "total_once_off": total_o}


def _apply_discount(value: Decimal, discount_pct: Optional[Decimal]) -> Decimal:
    if not discount_pct:
        return value
    return (value - value * discount_pct / Decimal("100")).quantize(Decimal("0.01"))


async def _commission_rate(db: AsyncSession, tenant_id: uuid.UUID, agent_id: uuid.UUID) -> Decimal:
    now = datetime.utcnow()
    period_start = date(now.year, now.month, 1)
    next_m = period_start + timedelta(days=32)
    period_end = date(next_m.year, next_m.month, 1)

    result = await db.execute(
        select(func.count(Deal.id)).where(
            Deal.tenant_id == tenant_id,
            Deal.agent_id == agent_id,
            Deal.status == "WON",
            Deal.closed_at >= period_start,
            Deal.closed_at < period_end,
        )
    )
    count = result.scalar() or 0

    # Look up tenant-specific commission tiers
    tier_result = await db.execute(
        text(
            """
            select rate_percent from commission_tiers
            where tenant_id = :tid and is_active = true
              and min_deals <= :count
              and (max_deals is null or max_deals >= :count)
            order by rate_percent desc
            limit 1
            """
        ),
        {"tid": str(tenant_id), "count": count},
    )
    row = tier_result.mappings().first()
    if row:
        return Decimal(str(row["rate_percent"]))

    # Fallback to default tiers
    if count >= 20:
        return Decimal("10.0")
    if count >= 10:
        return Decimal("7.0")
    return Decimal("5.0")


def _emit_webhook(url: str, payload: Dict[str, Any]) -> None:
    try:
        with httpx.Client(timeout=10) as client:
            client.post(url, json=payload)
    except Exception:
        pass


async def _dispatch_provisioning_bg(payload: Dict[str, Any]) -> None:
    urls = []
    if BILLING_WEBHOOK_URL:
        urls.append(BILLING_WEBHOOK_URL)
    if NETWORK_WEBHOOK_URL:
        urls.append(NETWORK_WEBHOOK_URL)
    urls.extend(PROVISIONING_WEBHOOKS)
    for url in urls:
        _emit_webhook(url, payload)


# ── Routes ────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    init_tables()


@app.get("/")
async def root():
    return {"message": "OmniDome Sales Service v2.0 (async) is active"}


# ── Pipeline ─────────────────────────────────────────────────────────

@app.get("/pipeline", response_model=List[PipelineOverviewStage])
async def get_pipeline_overview(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    pipeline_id = await _ensure_default_pipeline(db, tenant_id)
    stages = await _get_stages(db, pipeline_id)

    result = await db.execute(
        select(
            Deal.stage_id,
            func.count(Deal.id).label("deal_count"),
            func.coalesce(func.sum(Deal.value_zar), 0).label("total_value"),
        )
        .where(Deal.tenant_id == tenant_id)
        .group_by(Deal.stage_id)
    )
    totals = {row.stage_id: {"deal_count": row.deal_count, "total_value": row.total_value} for row in result.all()}

    overview = []
    for stage in stages:
        t = totals.get(stage.id, {"deal_count": 0, "total_value": 0})
        overview.append(PipelineOverviewStage(
            id=stage.id, name=stage.name, probability=stage.probability,
            sort_order=stage.sort_order, deal_count=t["deal_count"],
            total_value_zar=Decimal(str(t["total_value"])),
        ))
    return overview


@app.get("/pipeline/stages", response_model=List[PipelineStage])
async def list_pipeline_stages(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    pipeline_id = await _ensure_default_pipeline(db, tenant_id)
    stages = await _get_stages(db, pipeline_id)
    return [PipelineStage(id=s.id, name=s.name, probability=s.probability, sort_order=s.sort_order) for s in stages]


@app.post("/pipeline/stages", response_model=PipelineStage, status_code=201)
async def create_pipeline_stage(
    payload: PipelineStageCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    pipeline_id = await _ensure_default_pipeline(db, tenant_id)
    sort_order = payload.sort_order
    if sort_order is None:
        result = await db.execute(
            select(func.coalesce(func.max(DealStage.sort_order), 0))
            .where(DealStage.pipeline_id == pipeline_id)
        )
        sort_order = (result.scalar() or 0) + 1

    stage = DealStage(
        id=uuid.uuid4(), pipeline_id=pipeline_id, name=payload.name,
        probability=payload.probability, sort_order=sort_order,
    )
    db.add(stage)
    await db.flush()
    return PipelineStage(id=stage.id, name=stage.name, probability=stage.probability, sort_order=stage.sort_order)


# ── Deals ─────────────────────────────────────────────────────────────

@app.post("/deals", response_model=DealResponse, status_code=201)
async def create_deal(
    payload: DealCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    stage_id = await _resolve_stage_id(db, tenant_id, payload.stage_id, payload.stage_name)
    deal_id = uuid.uuid4()
    now = datetime.utcnow()

    deal = Deal(
        id=deal_id, tenant_id=tenant_id, contact_id=payload.customer_id,
        lead_id=payload.lead_id, agent_id=payload.agent_id, stage_id=stage_id,
        package_id=payload.package_id, name=payload.name, amount=payload.value_zar,
        value_zar=payload.value_zar, status="OPEN", close_date=payload.close_date,
        notes=payload.notes, created_at=now, updated_at=now,
    )
    db.add(deal)
    await db.flush()

    stage = await db.get(DealStage, stage_id)
    return DealResponse(
        id=deal_id, tenant_id=tenant_id, customer_id=payload.customer_id,
        lead_id=payload.lead_id, agent_id=payload.agent_id, stage_id=stage_id,
        stage_name=stage.name if stage else None, package_id=payload.package_id,
        value_zar=payload.value_zar, status="OPEN", close_date=payload.close_date,
        closed_at=None, close_reason=None, notes=payload.notes,
        created_at=now, updated_at=now,
    )


@app.get("/deals", response_model=List[DealResponse])
async def list_deals(
    stage_id: Optional[uuid.UUID] = None,
    stage: Optional[str] = None,
    agent_id: Optional[uuid.UUID] = None,
    status_filter: Optional[str] = Query(default=None, alias="status"),
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    min_value: Optional[Decimal] = None,
    max_value: Optional[Decimal] = None,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    q = (
        select(Deal, DealStage.name.label("stage_name"))
        .outerjoin(DealStage, DealStage.id == Deal.stage_id)
        .where(Deal.tenant_id == tenant_id)
    )
    if stage_id:
        q = q.where(Deal.stage_id == stage_id)
    if stage:
        q = q.where(func.lower(DealStage.name) == stage.lower())
    if agent_id:
        q = q.where(Deal.agent_id == agent_id)
    if status_filter:
        q = q.where(Deal.status == status_filter.upper())
    if start_date:
        q = q.where(Deal.created_at >= start_date)
    if end_date:
        q = q.where(Deal.created_at <= end_date)
    if min_value is not None:
        q = q.where(Deal.value_zar >= min_value)
    if max_value is not None:
        q = q.where(Deal.value_zar <= max_value)
    q = q.order_by(Deal.created_at.desc())

    result = await db.execute(q)
    rows = result.all()
    return [
        DealResponse(
            id=row.Deal.id, tenant_id=row.Deal.tenant_id, customer_id=row.Deal.contact_id,
            lead_id=row.Deal.lead_id, agent_id=row.Deal.agent_id, stage_id=row.Deal.stage_id,
            stage_name=row.stage_name, package_id=row.Deal.package_id,
            value_zar=row.Deal.value_zar, status=row.Deal.status,
            close_date=row.Deal.close_date, closed_at=row.Deal.closed_at,
            close_reason=row.Deal.close_reason, notes=row.Deal.notes,
            created_at=row.Deal.created_at, updated_at=row.Deal.updated_at,
        )
        for row in rows
    ]


@app.put("/deals/{deal_id}", response_model=DealResponse)
async def update_deal(
    deal_id: uuid.UUID,
    payload: DealUpdate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    deal = await db.get(Deal, deal_id)
    if not deal or deal.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Deal not found")

    now = datetime.utcnow()
    if payload.name is not None:
        deal.name = payload.name
    if payload.value_zar is not None:
        deal.value_zar = payload.value_zar
        deal.amount = payload.value_zar
    if payload.agent_id is not None:
        deal.agent_id = payload.agent_id
    if payload.package_id is not None:
        deal.package_id = payload.package_id
    if payload.close_date is not None:
        deal.close_date = payload.close_date
    if payload.notes is not None:
        deal.notes = payload.notes
    if payload.stage_id or payload.stage_name:
        deal.stage_id = await _resolve_stage_id(db, tenant_id, payload.stage_id, payload.stage_name)

    deal.updated_at = now
    await db.flush()

    stage = await db.get(DealStage, deal.stage_id) if deal.stage_id else None
    return DealResponse(
        id=deal.id, tenant_id=deal.tenant_id, customer_id=deal.contact_id,
        lead_id=deal.lead_id, agent_id=deal.agent_id, stage_id=deal.stage_id,
        stage_name=stage.name if stage else None, package_id=deal.package_id,
        value_zar=deal.value_zar, status=deal.status, close_date=deal.close_date,
        closed_at=deal.closed_at, close_reason=deal.close_reason, notes=deal.notes,
        created_at=deal.created_at, updated_at=deal.updated_at,
    )


@app.put("/deals/{deal_id}/stage", response_model=DealResponse)
async def move_deal_stage(
    deal_id: uuid.UUID,
    payload: DealStageUpdate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    deal = await db.get(Deal, deal_id)
    if not deal or deal.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Deal not result")

    now = datetime.utcnow()
    stage_id = payload.stage_id
    if not stage_id and payload.stage_name:
        stage_id = await _resolve_stage_id(db, tenant_id, None, payload.stage_name)
    if not stage_id and payload.direction:
        pipeline_id = await _ensure_default_pipeline(db, tenant_id)
        stages = await _get_stages(db, pipeline_id)
        stage_ids = [s.id for s in stages]
        try:
            idx = stage_ids.index(deal.stage_id)
        except (ValueError, TypeError):
            idx = 0
        if payload.direction.lower() == "next" and idx + 1 < len(stage_ids):
            stage_id = stage_ids[idx + 1]
        elif payload.direction.lower() == "previous" and idx - 1 >= 0:
            stage_id = stage_ids[idx - 1]

    if not stage_id:
        raise HTTPException(status_code=400, detail="No stage specified")

    deal.stage_id = stage_id
    deal.updated_at = now
    await db.flush()

    stage = await db.get(DealStage, stage_id)
    return DealResponse(
        id=deal.id, tenant_id=deal.tenant_id, customer_id=deal.contact_id,
        lead_id=deal.lead_id, agent_id=deal.agent_id, stage_id=deal.stage_id,
        stage_name=stage.name if stage else None, package_id=deal.package_id,
        value_zar=deal.value_zar, status=deal.status, close_date=deal.close_date,
        closed_at=deal.closed_at, close_reason=deal.close_reason, notes=deal.notes,
        created_at=deal.created_at, updated_at=deal.updated_at,
    )


@app.post("/deals/{deal_id}/close-won", response_model=DealResponse)
async def close_deal_won(
    deal_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    deal = await db.get(Deal, deal_id)
    if not deal or deal.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Deal not found")

    now = datetime.utcnow()
    closed_stage_id = await _get_closed_stage_id(db, tenant_id, "Closed Won")
    deal.status = "WON"
    deal.closed_at = now
    deal.updated_at = now
    if closed_stage_id:
        deal.stage_id = closed_stage_id

    # Create commission
    if deal.agent_id:
        rate = await _commission_rate(db, tenant_id, deal.agent_id)
        amount = ((deal.value_zar or Decimal("0")) * rate / Decimal("100")).quantize(Decimal("0.01"))
        commission = Commission(
            id=uuid.uuid4(), tenant_id=tenant_id, deal_id=deal_id,
            agent_id=deal.agent_id, amount_zar=amount, rate_percent=rate,
            status="PENDING", created_at=now, updated_at=now,
        )
        db.add(commission)

    await db.flush()

    # Notify lifecycle service (non-blocking)
    await _notify_lifecycle_won(db, deal, tenant_id)

    # Dispatch provisioning webhooks
    payload = {
        "event": "deal.closed_won", "deal_id": str(deal_id),
        "tenant_id": str(tenant_id), "customer_id": str(deal.contact_id),
        "agent_id": str(deal.agent_id) if deal.agent_id else None,
        "package_id": str(deal.package_id) if deal.package_id else None,
        "value_zar": float(deal.value_zar or 0), "closed_at": now.isoformat(),
    }
    background_tasks.add_task(_dispatch_provisioning_bg, payload)

    stage = await db.get(DealStage, deal.stage_id) if deal.stage_id else None
    return DealResponse(
        id=deal.id, tenant_id=deal.tenant_id, customer_id=deal.contact_id,
        lead_id=deal.lead_id, agent_id=deal.agent_id, stage_id=deal.stage_id,
        stage_name=stage.name if stage else "Closed Won", package_id=deal.package_id,
        value_zar=deal.value_zar, status="WON", close_date=deal.close_date,
        closed_at=now, close_reason=deal.close_reason, notes=deal.notes,
        created_at=deal.created_at, updated_at=now,
    )


@app.post("/deals/{deal_id}/close-lost", response_model=DealResponse)
async def close_deal_lost(
    deal_id: uuid.UUID,
    reason: str = Query(..., min_length=3),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    deal = await db.get(Deal, deal_id)
    if not deal or deal.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Deal not found")

    now = datetime.utcnow()
    closed_stage_id = await _get_closed_stage_id(db, tenant_id, "Closed Lost")
    deal.status = "LOST"
    deal.closed_at = now
    deal.close_reason = reason
    deal.updated_at = now
    if closed_stage_id:
        deal.stage_id = closed_stage_id
    await db.flush()

    stage = await db.get(DealStage, deal.stage_id) if deal.stage_id else None
    return DealResponse(
        id=deal.id, tenant_id=deal.tenant_id, customer_id=deal.contact_id,
        lead_id=deal.lead_id, agent_id=deal.agent_id, stage_id=deal.stage_id,
        stage_name=stage.name if stage else "Closed Lost", package_id=deal.package_id,
        value_zar=deal.value_zar, status="LOST", close_date=deal.close_date,
        closed_at=now, close_reason=reason, notes=deal.notes,
        created_at=deal.created_at, updated_at=now,
    )


# ── Quotes ────────────────────────────────────────────────────────────

def _serialize_items(items: Optional[List[QuoteItem]]) -> Optional[List[Dict]]:
    if not items:
        return None
    return [
        {"description": i.description, "quantity": i.quantity,
         "unit_price_zar": float(i.unit_price_zar), "charge_type": i.charge_type}
        for i in items
    ]


def _deserialize_items(items: Optional[List[Dict]]) -> Optional[List[QuoteItem]]:
    if not items:
        return None
    return [QuoteItem(**i) for i in items]


@app.post("/quotes", response_model=QuoteResponse, status_code=201)
async def create_quote(
    payload: QuoteCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    quote_id = uuid.uuid4()
    now = datetime.utcnow()

    if payload.items:
        totals = _calculate_quote_totals(payload.items)
        total_monthly = totals["total_monthly"]
        total_once_off = totals["total_once_off"]
    else:
        total_monthly = payload.total_monthly or Decimal("0")
        total_once_off = payload.total_once_off or Decimal("0")

    total_monthly = _apply_discount(total_monthly, payload.discount_percent).quantize(Decimal("0.01"))
    total_once_off = _apply_discount(total_once_off, payload.discount_percent).quantize(Decimal("0.01"))
    valid_until = date.today() + timedelta(days=payload.valid_days)

    quote = Quote(
        id=quote_id, tenant_id=tenant_id, deal_id=payload.deal_id,
        customer_id=payload.customer_id, lead_id=payload.lead_id,
        agent_id=payload.agent_id, package_id=payload.package_id,
        items=_serialize_items(payload.items), total_monthly=total_monthly,
        total_once_off=total_once_off, term_months=payload.term_months,
        valid_until=valid_until, status="DRAFT", terms=payload.terms,
        created_at=now,
    )
    db.add(quote)
    await db.flush()

    return QuoteResponse(
        id=quote_id, tenant_id=tenant_id, deal_id=payload.deal_id,
        customer_id=payload.customer_id, lead_id=payload.lead_id,
        agent_id=payload.agent_id, package_id=payload.package_id,
        items=payload.items, total_monthly=total_monthly,
        total_once_off=total_once_off, term_months=payload.term_months,
        valid_until=valid_until, status="DRAFT", terms=payload.terms,
        created_at=now, sent_at=None, accepted_at=None,
    )


@app.get("/quotes/{quote_id}", response_model=QuoteResponse)
async def get_quote(
    quote_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    quote = await db.get(Quote, quote_id)
    if not quote or quote.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Quote not found")
    return QuoteResponse(
        id=quote.id, tenant_id=quote.tenant_id, deal_id=quote.deal_id,
        customer_id=quote.customer_id, lead_id=quote.lead_id, agent_id=quote.agent_id,
        package_id=quote.package_id, items=_deserialize_items(quote.items),
        total_monthly=quote.total_monthly, total_once_off=quote.total_once_off,
        term_months=quote.term_months, valid_until=quote.valid_until,
        status=quote.status, terms=quote.terms, created_at=quote.created_at,
        sent_at=quote.sent_at, accepted_at=quote.accepted_at,
    )


@app.post("/quotes/{quote_id}/send", response_model=QuoteResponse)
async def send_quote(
    quote_id: uuid.UUID,
    payload: QuoteSend,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    quote = await db.get(Quote, quote_id)
    if not quote or quote.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Quote not found")
    quote.status = "SENT"
    quote.sent_at = datetime.utcnow()
    await db.flush()
    return QuoteResponse(
        id=quote.id, tenant_id=quote.tenant_id, deal_id=quote.deal_id,
        customer_id=quote.customer_id, lead_id=quote.lead_id, agent_id=quote.agent_id,
        package_id=quote.package_id, items=_deserialize_items(quote.items),
        total_monthly=quote.total_monthly, total_once_off=quote.total_once_off,
        term_months=quote.term_months, valid_until=quote.valid_until,
        status=quote.status, terms=quote.terms, created_at=quote.created_at,
        sent_at=quote.sent_at, accepted_at=quote.accepted_at,
    )


@app.post("/quotes/{quote_id}/accept", response_model=QuoteResponse)
async def accept_quote(
    quote_id: uuid.UUID,
    payload: QuoteAccept,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    quote = await db.get(Quote, quote_id)
    if not quote or quote.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Quote not found")

    quote.status = "ACCEPTED"
    quote.accepted_at = datetime.utcnow()

    if payload.create_deal:
        stage_id = await _resolve_stage_id(db, tenant_id, None, payload.stage_name or "Proposal")
        deal = Deal(
            id=uuid.uuid4(), tenant_id=tenant_id, contact_id=quote.customer_id,
            lead_id=quote.lead_id, agent_id=quote.agent_id, stage_id=stage_id,
            package_id=quote.package_id, name=f"Quote {quote.id} deal",
            amount=quote.total_monthly, value_zar=quote.total_monthly,
            status="OPEN", created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
        )
        db.add(deal)

    await db.flush()
    return QuoteResponse(
        id=quote.id, tenant_id=quote.tenant_id, deal_id=quote.deal_id,
        customer_id=quote.customer_id, lead_id=quote.lead_id, agent_id=quote.agent_id,
        package_id=quote.package_id, items=_deserialize_items(quote.items),
        total_monthly=quote.total_monthly, total_once_off=quote.total_once_off,
        term_months=quote.term_months, valid_until=quote.valid_until,
        status=quote.status, terms=quote.terms, created_at=quote.created_at,
        sent_at=quote.sent_at, accepted_at=quote.accepted_at,
    )


# ── Commissions ──────────────────────────────────────────────────────

@app.get("/commissions", response_model=List[CommissionResponse])
async def list_commissions(
    agent_id: Optional[uuid.UUID] = None,
    deal_id: Optional[uuid.UUID] = None,
    status_filter: Optional[str] = Query(default=None, alias="status"),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    q = select(Commission).where(Commission.tenant_id == tenant_id)
    if agent_id:
        q = q.where(Commission.agent_id == agent_id)
    if deal_id:
        q = q.where(Commission.deal_id == deal_id)
    if status_filter:
        q = q.where(Commission.status == status_filter.upper())
    q = q.order_by(Commission.created_at.desc())
    result = await db.execute(q)
    commissions = result.scalars().all()
    return [
        CommissionResponse(
            id=c.id, deal_id=c.deal_id, agent_id=c.agent_id,
            amount_zar=c.amount_zar, rate_percent=c.rate_percent,
            status=c.status, created_at=c.created_at, updated_at=c.updated_at,
        )
        for c in commissions
    ]


@app.get("/commissions/report", response_model=List[CommissionReportEntry])
async def commission_report(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(
            Commission.agent_id,
            func.sum(Commission.amount_zar).label("total_amount"),
            func.count(Commission.id).label("deals_count"),
            func.sum(func.cast((Commission.status == "PENDING").int, Integer)).label("pending"),
            func.sum(func.cast((Commission.status == "APPROVED").int, Integer)).label("approved"),
            func.sum(func.cast((Commission.status == "PAID").int, Integer)).label("paid"),
            func.sum(func.cast((Commission.status == "CLAWBACK").int, Integer)).label("clawback"),
        )
        .where(Commission.tenant_id == tenant_id)
        .group_by(Commission.agent_id)
    )
    return [
        CommissionReportEntry(
            agent_id=row.agent_id, total_amount_zar=Decimal(str(row.total_amount or 0)),
            deals_count=row.deals_count, pending=row.pending or 0,
            approved=row.approved or 0, paid=row.paid or 0, clawback=row.clawback or 0,
        )
        for row in result.all()
    ]


# ── Targets ───────────────────────────────────────────────────────────

@app.post("/targets", status_code=201)
async def create_target(
    payload: TargetCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    target = Target(
        id=uuid.uuid4(), tenant_id=tenant_id, agent_id=payload.agent_id,
        team_id=payload.team_id, period_type=payload.period_type,
        period_start=payload.period_start, period_end=payload.period_end,
        target_value_zar=payload.target_value_zar,
    )
    db.add(target)
    await db.flush()
    return {"id": str(target.id), "message": "Target created"}


@app.get("/targets/performance", response_model=List[TargetPerformanceEntry])
async def target_performance(
    period_start: date, period_end: date,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    targets_result = await db.execute(
        select(Target).where(
            Target.tenant_id == tenant_id,
            Target.period_start <= period_end,
            Target.period_end >= period_start,
        )
    )
    targets = targets_result.scalars().all()

    entries = []
    for t in targets:
        actual_result = await db.execute(
            select(func.coalesce(func.sum(Deal.value_zar), 0)).where(
                Deal.tenant_id == tenant_id,
                Deal.status == "WON",
                Deal.agent_id == t.agent_id if t.agent_id else Deal.agent_id != None,  # noqa: E711
                Deal.closed_at >= t.period_start,
                Deal.closed_at <= t.period_end,
            )
        )
        actual = Decimal(str(actual_result.scalar() or 0))
        variance = actual - t.target_value_zar
        entries.append(TargetPerformanceEntry(
            target_id=t.id, agent_id=t.agent_id, team_id=t.team_id,
            period_start=t.period_start, period_end=t.period_end,
            target_value_zar=t.target_value_zar, actual_value_zar=actual,
            variance_zar=variance,
        ))
    return entries


# ── Leads ─────────────────────────────────────────────────────────────

@app.get("/leads", response_model=List[LeadResponse])
async def list_leads(
    status: Optional[str] = None,
    agent_id: Optional[uuid.UUID] = None,
    source: Optional[str] = None,
    min_interest: Optional[int] = Query(None, ge=1, le=5),
    limit: int = Query(50, ge=1, le=200),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    q = select(Lead).where(Lead.tenant_id == tenant_id)
    if status:
        q = q.where(Lead.status == status.upper())
    if agent_id:
        q = q.where(Lead.agent_id == agent_id)
    if source:
        q = q.where(Lead.source == source)
    if min_interest:
        q = q.where(Lead.interest_level >= min_interest)
    q = q.order_by(Lead.created_at.desc()).limit(limit)
    result = await db.execute(q)
    leads = result.scalars().all()
    return [
        LeadResponse(
            id=l.id, tenant_id=l.tenant_id, contact_id=l.contact_id,
            agent_id=l.agent_id, first_name=l.first_name, last_name=l.last_name,
            email=l.email, phone=l.phone, address=l.address, source=l.source,
            interest_level=l.interest_level, status=l.status, notes=l.notes,
            converted_at=l.converted_at, created_at=l.created_at, updated_at=l.updated_at,
        ) for l in leads
    ]


@app.post("/leads", response_model=LeadResponse, status_code=201)
async def create_lead(
    payload: LeadCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    now = datetime.utcnow()
    lead = Lead(
        id=uuid.uuid4(), tenant_id=tenant_id,
        first_name=payload.first_name, last_name=payload.last_name,
        email=payload.email, phone=payload.phone, address=payload.address,
        source=payload.source, interest_level=payload.interest_level,
        notes=payload.notes, agent_id=payload.agent_id,
        status="NEW", created_at=now, updated_at=now,
    )
    db.add(lead)
    await db.flush()
    return LeadResponse(
        id=lead.id, tenant_id=lead.tenant_id, contact_id=lead.contact_id,
        agent_id=lead.agent_id, first_name=lead.first_name, last_name=lead.last_name,
        email=lead.email, phone=lead.phone, address=lead.address, source=lead.source,
        interest_level=lead.interest_level, status=lead.status, notes=lead.notes,
        converted_at=lead.converted_at, created_at=lead.created_at, updated_at=lead.updated_at,
    )


@app.put("/leads/{lead_id}", response_model=LeadResponse)
async def update_lead(
    lead_id: uuid.UUID,
    payload: LeadUpdate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    lead = await db.get(Lead, lead_id)
    if not lead or lead.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Lead not found")
    now = datetime.utcnow()
    update_data = payload.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(lead, key, value)
    lead.updated_at = now
    await db.flush()
    return LeadResponse(
        id=lead.id, tenant_id=lead.tenant_id, contact_id=lead.contact_id,
        agent_id=lead.agent_id, first_name=lead.first_name, last_name=lead.last_name,
        email=lead.email, phone=lead.phone, address=lead.address, source=lead.source,
        interest_level=lead.interest_level, status=lead.status, notes=lead.notes,
        converted_at=lead.converted_at, created_at=lead.created_at, updated_at=lead.updated_at,
    )


@app.post("/leads/{lead_id}/convert", response_model=dict)
async def convert_lead(
    lead_id: uuid.UUID,
    payload: LeadConvert,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    lead = await db.get(Lead, lead_id)
    if not lead or lead.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Lead not found")
    now = datetime.utcnow()

    # Create or find contact
    contact_id = lead.contact_id
    if not contact_id:
        contact = Contact(
            id=uuid.uuid4(), tenant_id=tenant_id,
            first_name=lead.first_name, last_name=lead.last_name,
            email=lead.email, phone=lead.phone,
            physical_address=lead.address,
            status="ACTIVE", lifecycle_stage="QUALIFIED",
            created_at=now, updated_at=now,
        )
        db.add(contact)
        await db.flush()
        contact_id = contact.id
        lead.contact_id = contact_id

    # Create deal
    deal_name = payload.name or f"{lead.first_name} {lead.last_name} - New Deal"
    deal_value = payload.value_zar
    agent_id = payload.agent_id or lead.agent_id
    stage_id = await _resolve_stage_id(db, tenant_id, None, "Prospecting")
    deal = Deal(
        id=uuid.uuid4(), tenant_id=tenant_id, contact_id=contact_id,
        lead_id=lead.id, agent_id=agent_id, stage_id=stage_id,
        name=deal_name, value_zar=deal_value, status="OPEN",
        created_at=now, updated_at=now,
    )
    db.add(deal)

    # Mark lead as converted
    lead.status = "CONVERTED"
    lead.converted_at = now
    lead.updated_at = now
    await db.flush()

    return {"deal_id": str(deal.id), "contact_id": str(contact_id), "message": "Lead converted"}


# ── Contacts ──────────────────────────────────────────────────────────

@app.get("/contacts", response_model=List[ContactResponse])
async def list_contacts(
    search: Optional[str] = None,
    status: Optional[str] = None,
    lifecycle_stage: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    q = select(Contact).where(Contact.tenant_id == tenant_id)
    if status:
        q = q.where(Contact.status == status.upper())
    if lifecycle_stage:
        q = q.where(Contact.lifecycle_stage == lifecycle_stage)
    if search:
        term = f"%{search}%"
        q = q.where(
            Contact.first_name.ilike(term) | Contact.last_name.ilike(term) |
            Contact.email.ilike(term) | Contact.phone.ilike(term)
        )
    q = q.order_by(Contact.created_at.desc()).limit(limit)
    result = await db.execute(q)
    contacts = result.scalars().all()
    return [
        ContactResponse(
            id=c.id, tenant_id=c.tenant_id, first_name=c.first_name,
            last_name=c.last_name, email=c.email, phone=c.phone,
            physical_address=c.physical_address, city=c.city,
            province=c.province, rica_verified=c.rica_verified,
            status=c.status, lifecycle_stage=c.lifecycle_stage,
            nps_score=c.nps_score, created_at=c.created_at, updated_at=c.updated_at,
        ) for c in contacts
    ]


@app.get("/contacts/{contact_id}", response_model=ContactResponse)
async def get_contact(
    contact_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    contact = await db.get(Contact, contact_id)
    if not contact or contact.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Contact not found")
    return ContactResponse(
        id=contact.id, tenant_id=contact.tenant_id, first_name=contact.first_name,
        last_name=contact.last_name, email=contact.email, phone=contact.phone,
        physical_address=contact.physical_address, city=contact.city,
        province=contact.province, rica_verified=contact.rica_verified,
        status=contact.status, lifecycle_stage=contact.lifecycle_stage,
        nps_score=contact.nps_score, created_at=contact.created_at, updated_at=contact.updated_at,
    )


@app.post("/contacts", response_model=ContactResponse, status_code=201)
async def create_contact(
    payload: ContactCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    now = datetime.utcnow()
    contact = Contact(
        id=uuid.uuid4(), tenant_id=tenant_id,
        first_name=payload.first_name, last_name=payload.last_name,
        email=payload.email, phone=payload.phone,
        physical_address=payload.physical_address,
        postal_code=payload.postal_code, city=payload.city,
        province=payload.province, rica_id_number=payload.rica_id_number,
        status="ACTIVE", lifecycle_stage="PROSPECT",
        created_at=now, updated_at=now,
    )
    db.add(contact)
    await db.flush()
    return ContactResponse(
        id=contact.id, tenant_id=contact.tenant_id, first_name=contact.first_name,
        last_name=contact.last_name, email=contact.email, phone=contact.phone,
        physical_address=contact.physical_address, city=contact.city,
        province=contact.province, rica_verified=contact.rica_verified,
        status=contact.status, lifecycle_stage=contact.lifecycle_stage,
        nps_score=contact.nps_score, created_at=contact.created_at, updated_at=contact.updated_at,
    )


@app.put("/contacts/{contact_id}", response_model=ContactResponse)
async def update_contact(
    contact_id: uuid.UUID,
    payload: ContactUpdate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    contact = await db.get(Contact, contact_id)
    if not contact or contact.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Contact not found")
    now = datetime.utcnow()
    update_data = payload.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(contact, key, value)
    contact.updated_at = now
    await db.flush()
    return ContactResponse(
        id=contact.id, tenant_id=contact.tenant_id, first_name=contact.first_name,
        last_name=contact.last_name, email=contact.email, phone=contact.phone,
        physical_address=contact.physical_address, city=contact.city,
        province=contact.province, rica_verified=contact.rica_verified,
        status=contact.status, lifecycle_stage=contact.lifecycle_stage,
        nps_score=contact.nps_score, created_at=contact.created_at, updated_at=contact.updated_at,
    )


# ── Customer 360 ──────────────────────────────────────────────────────

@app.get("/contacts/{contact_id}/360", response_model=Customer360Response)
async def get_customer_360(
    contact_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    contact = await db.get(Contact, contact_id)
    if not contact or contact.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Contact not found")

    # Get deals for this contact
    deals_result = await db.execute(
        select(Deal, DealStage.name.label("stage_name"))
        .outerjoin(DealStage, DealStage.id == Deal.stage_id)
        .where(Deal.tenant_id == tenant_id, Deal.contact_id == contact_id)
        .order_by(Deal.created_at.desc())
    )
    deals = []
    total_revenue = Decimal("0")
    open_deals_value = Decimal("0")
    for row in deals_result.all():
        d = row.Deal
        deals.append(DealResponse(
            id=d.id, tenant_id=d.tenant_id, customer_id=d.contact_id,
            lead_id=d.lead_id, agent_id=d.agent_id, stage_id=d.stage_id,
            stage_name=row.stage_name, package_id=d.package_id,
            value_zar=d.value_zar, status=d.status, close_date=d.close_date,
            closed_at=d.closed_at, close_reason=d.close_reason, notes=d.notes,
            created_at=d.created_at, updated_at=d.updated_at,
        ))
        if d.status == "WON":
            total_revenue += d.value_zar or Decimal("0")
        elif d.status == "OPEN":
            open_deals_value += d.value_zar or Decimal("0")

    # Get quotes for this contact
    quotes_result = await db.execute(
        select(Quote).where(Quote.tenant_id == tenant_id, Quote.customer_id == contact_id)
        .order_by(Quote.created_at.desc()).limit(20)
    )
    quotes = []
    for q in quotes_result.scalars().all():
        quotes.append(QuoteResponse(
            id=q.id, tenant_id=q.tenant_id, deal_id=q.deal_id,
            customer_id=q.customer_id, lead_id=q.lead_id, agent_id=q.agent_id,
            package_id=q.package_id, items=q.items, total_monthly=q.total_monthly,
            total_once_off=q.total_once_off, term_months=q.term_months,
            valid_until=q.valid_until, status=q.status, terms=q.terms,
            created_at=q.created_at, sent_at=q.sent_at, accepted_at=q.accepted_at,
        ))

    return Customer360Response(
        contact=ContactResponse(
            id=contact.id, tenant_id=contact.tenant_id,
            first_name=contact.first_name, last_name=contact.last_name,
            email=contact.email, phone=contact.phone,
            physical_address=contact.physical_address, city=contact.city,
            province=contact.province, rica_verified=contact.rica_verified,
            status=contact.status, lifecycle_stage=contact.lifecycle_stage,
            nps_score=contact.nps_score, created_at=contact.created_at,
            updated_at=contact.updated_at,
        ),
        deals=deals,
        quotes=quotes,
        invoices=[],  # Populated from billing service when available
        total_revenue=float(total_revenue),
        open_deals_value=float(open_deals_value),
    )


# ── Entrypoint ────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8002"))
    uvicorn.run(app, host="0.0.0.0", port=port)
