
from datetime import date, datetime, timedelta
from decimal import Decimal
import os
from typing import Any, Dict, List, Optional
import uuid

import httpx
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import bindparam, text

from services.common.auth import AuthContext, get_auth_context, get_current_tenant_id
from services.common.db import get_engine
from services.common.entitlements import EntitlementGuard

app = FastAPI(title="CoreConnect Sales Service", version="1.0.0")
guard = EntitlementGuard(module_id="sales")


@app.on_event("startup")
async def startup() -> None:
    guard.ensure_startup()


@app.middleware("http")
async def entitlement_middleware(request, call_next):
    return await guard.middleware(request, call_next)


DEFAULT_STAGES = [
    {"name": "Prospecting", "probability": 10, "sort_order": 1},
    {"name": "Qualified", "probability": 25, "sort_order": 2},
    {"name": "Proposal", "probability": 40, "sort_order": 3},
    {"name": "Negotiation", "probability": 60, "sort_order": 4},
    {"name": "Closed Won", "probability": 100, "sort_order": 5},
    {"name": "Closed Lost", "probability": 0, "sort_order": 6},
]

BILLING_WEBHOOK_URL = os.getenv("BILLING_WEBHOOK_URL")
NETWORK_WEBHOOK_URL = os.getenv("NETWORK_WEBHOOK_URL")
PROVISIONING_WEBHOOKS = [
    url.strip()
    for url in os.getenv("SALES_PROVISIONING_WEBHOOKS", "").split(",")
    if url.strip()
]


# ---- Pydantic Models ----
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
    charge_type: str = Field(default="monthly", description="monthly or once_off")


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
    channel: str = Field(default="email", description="email or sms")
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
    period_type: str = Field(default="MONTHLY", description="MONTHLY or QUARTERLY")
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


# ---- Helpers ----
def _get_engine():
    return get_engine()


def _ensure_default_pipeline(conn, tenant_id: uuid.UUID) -> uuid.UUID:
    row = conn.execute(
        text(
            """
            select id from pipelines
            where tenant_id = :tenant_id and is_default = true
            limit 1
            """
        ),
        {"tenant_id": str(tenant_id)},
    ).fetchone()

    if not row:
        pipeline_id = uuid.uuid4()
        conn.execute(
            text(
                """
                insert into pipelines (id, tenant_id, name, is_default)
                values (:id, :tenant_id, :name, true)
                """
            ),
            {"id": str(pipeline_id), "tenant_id": str(tenant_id), "name": "Default Pipeline"},
        )
    else:
        pipeline_id = row[0]

    stage_count = conn.execute(
        text("select count(*) from deal_stages where pipeline_id = :pipeline_id"),
        {"pipeline_id": str(pipeline_id)},
    ).scalar()

    if stage_count == 0:
        conn.execute(
            text(
                """
                insert into deal_stages (id, pipeline_id, name, probability, sort_order)
                values (:id, :pipeline_id, :name, :probability, :sort_order)
                """
            ),
            [
                {
                    "id": str(uuid.uuid4()),
                    "pipeline_id": str(pipeline_id),
                    "name": stage["name"],
                    "probability": stage["probability"],
                    "sort_order": stage["sort_order"],
                }
                for stage in DEFAULT_STAGES
            ],
        )

    return pipeline_id


def _get_stages(conn, pipeline_id: uuid.UUID) -> List[Dict[str, Any]]:
    rows = conn.execute(
        text(
            """
            select id, name, probability, sort_order
            from deal_stages
            where pipeline_id = :pipeline_id
            order by sort_order
            """
        ),
        {"pipeline_id": str(pipeline_id)},
    ).mappings().all()
    return list(rows)


def _resolve_stage_id(
    conn,
    tenant_id: uuid.UUID,
    stage_id: Optional[uuid.UUID],
    stage_name: Optional[str],
) -> uuid.UUID:
    pipeline_id = _ensure_default_pipeline(conn, tenant_id)
    if stage_id:
        return stage_id
    if stage_name:
        row = conn.execute(
            text(
                """
                select id from deal_stages
                where pipeline_id = :pipeline_id and lower(name) = lower(:name)
                """
            ),
            {"pipeline_id": str(pipeline_id), "name": stage_name},
        ).fetchone()
        if row:
            return row[0]
    stages = _get_stages(conn, pipeline_id)
    if not stages:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Pipeline stages missing")
    return stages[0]["id"]


def _get_closed_stage_id(conn, tenant_id: uuid.UUID, name: str) -> Optional[uuid.UUID]:
    pipeline_id = _ensure_default_pipeline(conn, tenant_id)
    row = conn.execute(
        text(
            """
            select id from deal_stages
            where pipeline_id = :pipeline_id and lower(name) = lower(:name)
            limit 1
            """
        ),
        {"pipeline_id": str(pipeline_id), "name": name},
    ).fetchone()
    return row[0] if row else None


def _calculate_quote_totals(items: Optional[List[QuoteItem]]) -> Dict[str, Decimal]:
    total_monthly = Decimal("0")
    total_once_off = Decimal("0")
    if not items:
        return {"total_monthly": total_monthly, "total_once_off": total_once_off}
    for item in items:
        line_total = item.unit_price_zar * item.quantity
        if item.charge_type.lower() == "once_off":
            total_once_off += line_total
        else:
            total_monthly += line_total
    return {"total_monthly": total_monthly, "total_once_off": total_once_off}


def _apply_discount(value: Decimal, discount_percent: Optional[Decimal]) -> Decimal:
    if not discount_percent:
        return value
    discount = value * (discount_percent / Decimal("100"))
    return (value - discount).quantize(Decimal("0.01"))


def _commission_rate_for_agent(conn, tenant_id: uuid.UUID, agent_id: uuid.UUID, now: datetime) -> Decimal:
    period_start = date(now.year, now.month, 1)
    next_month = period_start + timedelta(days=32)
    period_end = date(next_month.year, next_month.month, 1)

    count = conn.execute(
        text(
            """
            select count(*)
            from deals
            where tenant_id = :tenant_id
              and agent_id = :agent_id
              and status = 'WON'
              and closed_at >= :start_date
              and closed_at < :end_date
            """
        ),
        {
            "tenant_id": str(tenant_id),
            "agent_id": str(agent_id),
            "start_date": period_start,
            "end_date": period_end,
        },
    ).scalar() or 0

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
        return


def _dispatch_provisioning(background_tasks: BackgroundTasks, payload: Dict[str, Any]) -> None:
    urls = []
    if BILLING_WEBHOOK_URL:
        urls.append(BILLING_WEBHOOK_URL)
    if NETWORK_WEBHOOK_URL:
        urls.append(NETWORK_WEBHOOK_URL)
    urls.extend(PROVISIONING_WEBHOOKS)
    for url in urls:
        background_tasks.add_task(_emit_webhook, url, payload)


# ---- Routes ----
@app.get("/")
async def root():
    return {"message": "CoreConnect Sales Service is active"}


# Pipeline Management
@app.get("/pipeline", response_model=List[PipelineOverviewStage])
async def get_pipeline_overview(tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    engine = _get_engine()
    with engine.begin() as conn:
        pipeline_id = _ensure_default_pipeline(conn, tenant_id)
        stages = _get_stages(conn, pipeline_id)
        stage_rows = conn.execute(
            text(
                """
                select d.stage_id, count(*) as deal_count, coalesce(sum(d.value_zar), 0) as total_value
                from deals d
                where d.tenant_id = :tenant_id
                group by d.stage_id
                """
            ),
            {"tenant_id": str(tenant_id)},
        ).fetchall()
        totals = {row[0]: {"deal_count": row[1], "total_value": row[2]} for row in stage_rows}

    overview: List[PipelineOverviewStage] = []
    for stage in stages:
        total = totals.get(stage["id"], {"deal_count": 0, "total_value": 0})
        overview.append(
            PipelineOverviewStage(
                id=stage["id"],
                name=stage["name"],
                probability=stage["probability"],
                sort_order=stage["sort_order"],
                deal_count=total["deal_count"],
                total_value_zar=Decimal(str(total["total_value"])),
            )
        )
    return overview


@app.get("/pipeline/stages", response_model=List[PipelineStage])
async def list_pipeline_stages(tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    engine = _get_engine()
    with engine.begin() as conn:
        pipeline_id = _ensure_default_pipeline(conn, tenant_id)
        stages = _get_stages(conn, pipeline_id)
    return [PipelineStage(**stage) for stage in stages]


@app.post("/pipeline/stages", response_model=PipelineStage, status_code=status.HTTP_201_CREATED)
async def create_pipeline_stage(
    payload: PipelineStageCreate, tenant_id: uuid.UUID = Depends(get_current_tenant_id)
):
    engine = _get_engine()
    stage_id = uuid.uuid4()
    with engine.begin() as conn:
        pipeline_id = _ensure_default_pipeline(conn, tenant_id)
        if payload.sort_order is None:
            max_sort = conn.execute(
                text("select coalesce(max(sort_order), 0) from deal_stages where pipeline_id = :pipeline_id"),
                {"pipeline_id": str(pipeline_id)},
            ).scalar()
            sort_order = int(max_sort or 0) + 1
        else:
            sort_order = payload.sort_order
        conn.execute(
            text(
                """
                insert into deal_stages (id, pipeline_id, name, probability, sort_order)
                values (:id, :pipeline_id, :name, :probability, :sort_order)
                """
            ),
            {
                "id": str(stage_id),
                "pipeline_id": str(pipeline_id),
                "name": payload.name,
                "probability": payload.probability,
                "sort_order": sort_order,
            },
        )
    return PipelineStage(
        id=stage_id,
        name=payload.name,
        probability=payload.probability,
        sort_order=sort_order,
    )


# Deal Management
@app.post("/deals", response_model=DealResponse, status_code=status.HTTP_201_CREATED)
async def create_deal(
    payload: DealCreate, tenant_id: uuid.UUID = Depends(get_current_tenant_id)
):
    engine = _get_engine()
    deal_id = uuid.uuid4()
    now = datetime.utcnow()
    with engine.begin() as conn:
        stage_id = _resolve_stage_id(conn, tenant_id, payload.stage_id, payload.stage_name)
        conn.execute(
            text(
                """
                insert into deals (
                    id, tenant_id, contact_id, lead_id, agent_id, stage_id, package_id,
                    name, amount, value_zar, status, close_date, notes, created_at, updated_at
                )
                values (
                    :id, :tenant_id, :contact_id, :lead_id, :agent_id, :stage_id, :package_id,
                    :name, :amount, :value_zar, :status, :close_date, :notes, :created_at, :updated_at
                )
                """
            ),
            {
                "id": str(deal_id),
                "tenant_id": str(tenant_id),
                "contact_id": str(payload.customer_id),
                "lead_id": str(payload.lead_id) if payload.lead_id else None,
                "agent_id": str(payload.agent_id) if payload.agent_id else None,
                "stage_id": str(stage_id),
                "package_id": str(payload.package_id) if payload.package_id else None,
                "name": payload.name,
                "amount": payload.value_zar,
                "value_zar": payload.value_zar,
                "status": "OPEN",
                "close_date": payload.close_date,
                "notes": payload.notes,
                "created_at": now,
                "updated_at": now,
            },
        )
        stage_name = conn.execute(
            text("select name from deal_stages where id = :stage_id"),
            {"stage_id": str(stage_id)},
        ).scalar()
    return DealResponse(
        id=deal_id,
        tenant_id=tenant_id,
        customer_id=payload.customer_id,
        lead_id=payload.lead_id,
        agent_id=payload.agent_id,
        stage_id=stage_id,
        stage_name=stage_name,
        package_id=payload.package_id,
        value_zar=payload.value_zar,
        status="OPEN",
        close_date=payload.close_date,
        closed_at=None,
        close_reason=None,
        notes=payload.notes,
        created_at=now,
        updated_at=now,
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
):
    conditions = ["d.tenant_id = :tenant_id"]
    params: Dict[str, Any] = {"tenant_id": str(tenant_id)}
    if stage_id:
        conditions.append("d.stage_id = :stage_id")
        params["stage_id"] = str(stage_id)
    if stage:
        conditions.append("lower(s.name) = lower(:stage_name)")
        params["stage_name"] = stage
    if agent_id:
        conditions.append("d.agent_id = :agent_id")
        params["agent_id"] = str(agent_id)
    if status_filter:
        conditions.append("d.status = :status")
        params["status"] = status_filter.upper()
    if start_date:
        conditions.append("d.created_at >= :start_date")
        params["start_date"] = start_date
    if end_date:
        conditions.append("d.created_at <= :end_date")
        params["end_date"] = end_date
    if min_value is not None:
        conditions.append("d.value_zar >= :min_value")
        params["min_value"] = min_value
    if max_value is not None:
        conditions.append("d.value_zar <= :max_value")
        params["max_value"] = max_value

    where_clause = " and ".join(conditions)
    engine = _get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                f"""
                select d.id, d.tenant_id, d.contact_id as customer_id, d.lead_id, d.agent_id,
                       d.stage_id, s.name as stage_name, d.package_id, d.value_zar, d.status,
                       d.close_date, d.closed_at, d.close_reason, d.notes, d.created_at, d.updated_at
                from deals d
                left join deal_stages s on s.id = d.stage_id
                where {where_clause}
                order by d.created_at desc
                """
            ),
            params,
        ).mappings().all()
    return [DealResponse(**row) for row in rows]


@app.put("/deals/{deal_id}", response_model=DealResponse)
async def update_deal(
    deal_id: uuid.UUID,
    payload: DealUpdate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    engine = _get_engine()
    now = datetime.utcnow()
    updates: Dict[str, Any] = {}
    if payload.name is not None:
        updates["name"] = payload.name
    if payload.value_zar is not None:
        updates["value_zar"] = payload.value_zar
        updates["amount"] = payload.value_zar
    if payload.agent_id is not None:
        updates["agent_id"] = str(payload.agent_id)
    if payload.package_id is not None:
        updates["package_id"] = str(payload.package_id)
    if payload.close_date is not None:
        updates["close_date"] = payload.close_date
    if payload.notes is not None:
        updates["notes"] = payload.notes

    with engine.begin() as conn:
        if payload.stage_id or payload.stage_name:
            updates["stage_id"] = str(
                _resolve_stage_id(conn, tenant_id, payload.stage_id, payload.stage_name)
            )
        if not updates:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No updates provided")
        set_clause = ", ".join([f"{key} = :{key}" for key in updates.keys()])
        updates["deal_id"] = str(deal_id)
        updates["tenant_id"] = str(tenant_id)
        updates["updated_at"] = now
        row = conn.execute(
            text(
                f"""
                update deals
                set {set_clause}, updated_at = :updated_at
                where id = :deal_id and tenant_id = :tenant_id
                returning id, tenant_id, contact_id as customer_id, lead_id, agent_id,
                          stage_id, package_id, value_zar, status, close_date, closed_at,
                          close_reason, notes, created_at, updated_at
                """
            ),
            updates,
        ).mappings().one_or_none()
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deal not found")
        stage_name = conn.execute(
            text("select name from deal_stages where id = :stage_id"),
            {"stage_id": str(row["stage_id"])},
        ).scalar()
    return DealResponse(**row, stage_name=stage_name)


@app.put("/deals/{deal_id}/stage", response_model=DealResponse)
async def move_deal_stage(
    deal_id: uuid.UUID,
    payload: DealStageUpdate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    engine = _get_engine()
    now = datetime.utcnow()
    with engine.begin() as conn:
        deal = conn.execute(
            text(
                """
                select d.id, d.stage_id, s.pipeline_id
                from deals d
                join deal_stages s on s.id = d.stage_id
                where d.id = :deal_id and d.tenant_id = :tenant_id
                """
            ),
            {"deal_id": str(deal_id), "tenant_id": str(tenant_id)},
        ).mappings().one_or_none()
        if not deal:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deal not found")

        stage_id = payload.stage_id
        if not stage_id and payload.stage_name:
            stage_id = _resolve_stage_id(conn, tenant_id, None, payload.stage_name)
        if not stage_id and payload.direction:
            stages = _get_stages(conn, deal["pipeline_id"])
            stage_ids = [stage["id"] for stage in stages]
            try:
                idx = stage_ids.index(deal["stage_id"])
            except ValueError:
                idx = 0
            if payload.direction.lower() == "next" and idx + 1 < len(stage_ids):
                stage_id = stage_ids[idx + 1]
            elif payload.direction.lower() == "previous" and idx - 1 >= 0:
                stage_id = stage_ids[idx - 1]

        if not stage_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No stage specified")

        row = conn.execute(
            text(
                """
                update deals
                set stage_id = :stage_id, updated_at = :updated_at
                where id = :deal_id and tenant_id = :tenant_id
                returning id, tenant_id, contact_id as customer_id, lead_id, agent_id,
                          stage_id, package_id, value_zar, status, close_date, closed_at,
                          close_reason, notes, created_at, updated_at
                """
            ),
            {
                "stage_id": str(stage_id),
                "updated_at": now,
                "deal_id": str(deal_id),
                "tenant_id": str(tenant_id),
            },
        ).mappings().one_or_none()
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deal not found")
        stage_name = conn.execute(
            text("select name from deal_stages where id = :stage_id"),
            {"stage_id": str(row["stage_id"])},
        ).scalar()
    return DealResponse(**row, stage_name=stage_name)

@app.post("/deals/{deal_id}/close-won", response_model=DealResponse)
async def close_deal_won(
    deal_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    engine = _get_engine()
    now = datetime.utcnow()
    with engine.begin() as conn:
        deal = conn.execute(
            text(
                """
                select d.*, s.name as stage_name
                from deals d
                left join deal_stages s on s.id = d.stage_id
                where d.id = :deal_id and d.tenant_id = :tenant_id
                """
            ),
            {"deal_id": str(deal_id), "tenant_id": str(tenant_id)},
        ).mappings().one_or_none()
        if not deal:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deal not found")

        closed_stage_id = _get_closed_stage_id(conn, tenant_id, "Closed Won")
        conn.execute(
            text(
                """
                update deals
                set status = 'WON',
                    closed_at = :closed_at,
                    stage_id = coalesce(:stage_id, stage_id),
                    updated_at = :updated_at
                where id = :deal_id and tenant_id = :tenant_id
                """
            ),
            {
                "closed_at": now,
                "stage_id": str(closed_stage_id) if closed_stage_id else None,
                "updated_at": now,
                "deal_id": str(deal_id),
                "tenant_id": str(tenant_id),
            },
        )

        if deal["agent_id"]:
            rate = _commission_rate_for_agent(conn, tenant_id, deal["agent_id"], now)
            amount_zar = (Decimal(str(deal["value_zar"] or 0)) * rate / Decimal("100")).quantize(
                Decimal("0.01")
            )
            conn.execute(
                text(
                    """
                    insert into commissions (id, tenant_id, deal_id, agent_id, amount_zar, rate_percent, status, created_at, updated_at)
                    values (:id, :tenant_id, :deal_id, :agent_id, :amount_zar, :rate_percent, 'PENDING', :created_at, :updated_at)
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "tenant_id": str(tenant_id),
                    "deal_id": str(deal_id),
                    "agent_id": str(deal["agent_id"]),
                    "amount_zar": amount_zar,
                    "rate_percent": rate,
                    "created_at": now,
                    "updated_at": now,
                },
            )

        stage_name = "Closed Won" if closed_stage_id else deal["stage_name"]

    payload = {
        "event": "deal.closed_won",
        "deal_id": str(deal_id),
        "tenant_id": str(tenant_id),
        "customer_id": str(deal["contact_id"]),
        "agent_id": str(deal["agent_id"]) if deal["agent_id"] else None,
        "package_id": str(deal["package_id"]) if deal["package_id"] else None,
        "value_zar": float(deal["value_zar"] or 0),
        "closed_at": now.isoformat(),
    }
    _dispatch_provisioning(background_tasks, payload)

    return DealResponse(
        id=deal_id,
        tenant_id=tenant_id,
        customer_id=deal["contact_id"],
        lead_id=deal["lead_id"],
        agent_id=deal["agent_id"],
        stage_id=closed_stage_id or deal["stage_id"],
        stage_name=stage_name,
        package_id=deal["package_id"],
        value_zar=Decimal(str(deal["value_zar"] or 0)),
        status="WON",
        close_date=deal["close_date"],
        closed_at=now,
        close_reason=deal["close_reason"],
        notes=deal["notes"],
        created_at=deal["created_at"],
        updated_at=now,
    )


@app.post("/deals/{deal_id}/close-lost", response_model=DealResponse)
async def close_deal_lost(
    deal_id: uuid.UUID,
    reason: str = Query(..., min_length=3),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    engine = _get_engine()
    now = datetime.utcnow()
    with engine.begin() as conn:
        deal = conn.execute(
            text(
                """
                select d.*, s.name as stage_name
                from deals d
                left join deal_stages s on s.id = d.stage_id
                where d.id = :deal_id and d.tenant_id = :tenant_id
                """
            ),
            {"deal_id": str(deal_id), "tenant_id": str(tenant_id)},
        ).mappings().one_or_none()
        if not deal:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deal not found")

        closed_stage_id = _get_closed_stage_id(conn, tenant_id, "Closed Lost")
        conn.execute(
            text(
                """
                update deals
                set status = 'LOST',
                    closed_at = :closed_at,
                    close_reason = :close_reason,
                    stage_id = coalesce(:stage_id, stage_id),
                    updated_at = :updated_at
                where id = :deal_id and tenant_id = :tenant_id
                """
            ),
            {
                "closed_at": now,
                "close_reason": reason,
                "stage_id": str(closed_stage_id) if closed_stage_id else None,
                "updated_at": now,
                "deal_id": str(deal_id),
                "tenant_id": str(tenant_id),
            },
        )

        stage_name = "Closed Lost" if closed_stage_id else deal["stage_name"]

    return DealResponse(
        id=deal_id,
        tenant_id=tenant_id,
        customer_id=deal["contact_id"],
        lead_id=deal["lead_id"],
        agent_id=deal["agent_id"],
        stage_id=closed_stage_id or deal["stage_id"],
        stage_name=stage_name,
        package_id=deal["package_id"],
        value_zar=Decimal(str(deal["value_zar"] or 0)),
        status="LOST",
        close_date=deal["close_date"],
        closed_at=now,
        close_reason=reason,
        notes=deal["notes"],
        created_at=deal["created_at"],
        updated_at=now,
    )


# Quotes
def _serialize_items(items: Optional[List[QuoteItem]]) -> Optional[List[Dict[str, Any]]]:
    if not items:
        return None
    return [
        {
            "description": item.description,
            "quantity": item.quantity,
            "unit_price_zar": float(item.unit_price_zar),
            "charge_type": item.charge_type,
        }
        for item in items
    ]


def _deserialize_items(items: Optional[List[Dict[str, Any]]]) -> Optional[List[QuoteItem]]:
    if not items:
        return None
    return [QuoteItem(**item) for item in items]


def _deal_value_from_quote(total_monthly: Decimal, total_once_off: Decimal, term_months: int) -> Decimal:
    return (total_monthly * Decimal(term_months) + total_once_off).quantize(Decimal("0.01"))


@app.post("/quotes", response_model=QuoteResponse, status_code=status.HTTP_201_CREATED)
async def create_quote(
    payload: QuoteCreate, tenant_id: uuid.UUID = Depends(get_current_tenant_id)
):
    engine = _get_engine()
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
    items_json = _serialize_items(payload.items)

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                insert into quotes (
                    id, tenant_id, deal_id, customer_id, lead_id, agent_id, package_id,
                    items, total_monthly, total_once_off, term_months, valid_until, status,
                    terms, created_at
                )
                values (
                    :id, :tenant_id, :deal_id, :customer_id, :lead_id, :agent_id, :package_id,
                    :items, :total_monthly, :total_once_off, :term_months, :valid_until, :status,
                    :terms, :created_at
                )
                """
            ),
            {
                "id": str(quote_id),
                "tenant_id": str(tenant_id),
                "deal_id": str(payload.deal_id) if payload.deal_id else None,
                "customer_id": str(payload.customer_id),
                "lead_id": str(payload.lead_id) if payload.lead_id else None,
                "agent_id": str(payload.agent_id) if payload.agent_id else None,
                "package_id": str(payload.package_id) if payload.package_id else None,
                "items": items_json,
                "total_monthly": total_monthly,
                "total_once_off": total_once_off,
                "term_months": payload.term_months,
                "valid_until": valid_until,
                "status": "DRAFT",
                "terms": payload.terms,
                "created_at": now,
            },
        )

    return QuoteResponse(
        id=quote_id,
        tenant_id=tenant_id,
        deal_id=payload.deal_id,
        customer_id=payload.customer_id,
        lead_id=payload.lead_id,
        agent_id=payload.agent_id,
        package_id=payload.package_id,
        items=payload.items,
        total_monthly=total_monthly,
        total_once_off=total_once_off,
        term_months=payload.term_months,
        valid_until=valid_until,
        status="DRAFT",
        terms=payload.terms,
        created_at=now,
        sent_at=None,
        accepted_at=None,
    )


@app.get("/quotes/{quote_id}", response_model=QuoteResponse)
async def get_quote(
    quote_id: uuid.UUID, tenant_id: uuid.UUID = Depends(get_current_tenant_id)
):
    engine = _get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                select id, tenant_id, deal_id, customer_id, lead_id, agent_id, package_id,
                       items, total_monthly, total_once_off, term_months, valid_until,
                       status, terms, created_at, sent_at, accepted_at
                from quotes
                where id = :quote_id and tenant_id = :tenant_id
                """
            ),
            {"quote_id": str(quote_id), "tenant_id": str(tenant_id)},
        ).mappings().one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quote not found")

    return QuoteResponse(
        id=row["id"],
        tenant_id=row["tenant_id"],
        deal_id=row["deal_id"],
        customer_id=row["customer_id"],
        lead_id=row["lead_id"],
        agent_id=row["agent_id"],
        package_id=row["package_id"],
        items=_deserialize_items(row["items"]),
        total_monthly=Decimal(str(row["total_monthly"] or 0)),
        total_once_off=Decimal(str(row["total_once_off"] or 0)),
        term_months=row["term_months"],
        valid_until=row["valid_until"],
        status=row["status"],
        terms=row["terms"],
        created_at=row["created_at"],
        sent_at=row["sent_at"],
        accepted_at=row["accepted_at"],
    )


@app.post("/quotes/{quote_id}/send", response_model=QuoteResponse)
async def send_quote(
    quote_id: uuid.UUID,
    payload: QuoteSend,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    engine = _get_engine()
    now = datetime.utcnow()
    with engine.begin() as conn:
        row = conn.execute(
            text(
                """
                update quotes
                set status = 'SENT',
                    sent_at = :sent_at
                where id = :quote_id and tenant_id = :tenant_id
                returning id, tenant_id, deal_id, customer_id, lead_id, agent_id, package_id,
                          items, total_monthly, total_once_off, term_months, valid_until,
                          status, terms, created_at, sent_at, accepted_at
                """
            ),
            {"quote_id": str(quote_id), "tenant_id": str(tenant_id), "sent_at": now},
        ).mappings().one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quote not found")

    return QuoteResponse(
        id=row["id"],
        tenant_id=row["tenant_id"],
        deal_id=row["deal_id"],
        customer_id=row["customer_id"],
        lead_id=row["lead_id"],
        agent_id=row["agent_id"],
        package_id=row["package_id"],
        items=_deserialize_items(row["items"]),
        total_monthly=Decimal(str(row["total_monthly"] or 0)),
        total_once_off=Decimal(str(row["total_once_off"] or 0)),
        term_months=row["term_months"],
        valid_until=row["valid_until"],
        status=row["status"],
        terms=row["terms"],
        created_at=row["created_at"],
        sent_at=row["sent_at"],
        accepted_at=row["accepted_at"],
    )


@app.post("/quotes/{quote_id}/accept", response_model=QuoteResponse)
async def accept_quote(
    quote_id: uuid.UUID,
    payload: QuoteAccept,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    engine = _get_engine()
    now = datetime.utcnow()
    with engine.begin() as conn:
        quote = conn.execute(
            text(
                """
                select id, tenant_id, deal_id, customer_id, lead_id, agent_id, package_id,
                       items, total_monthly, total_once_off, term_months, valid_until,
                       status, terms, created_at, sent_at, accepted_at
                from quotes
                where id = :quote_id and tenant_id = :tenant_id
                """
            ),
            {"quote_id": str(quote_id), "tenant_id": str(tenant_id)},
        ).mappings().one_or_none()

        if not quote:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quote not found")

        deal_id = quote["deal_id"]
        if payload.create_deal:
            total_monthly = Decimal(str(quote["total_monthly"] or 0))
            total_once_off = Decimal(str(quote["total_once_off"] or 0))
            contract_value = _deal_value_from_quote(total_monthly, total_once_off, quote["term_months"] or 12)
            stage_id = None
            if payload.stage_name:
                stage_id = _resolve_stage_id(conn, tenant_id, None, payload.stage_name)

            if deal_id:
                conn.execute(
                    text(
                        """
                        update deals
                        set value_zar = :value_zar,
                            amount = :amount,
                            status = 'OPEN',
                            closed_at = null,
                            close_reason = null,
                            stage_id = coalesce(:stage_id, stage_id),
                            updated_at = :updated_at
                        where id = :deal_id and tenant_id = :tenant_id
                        """
                    ),
                    {
                        "value_zar": contract_value,
                        "amount": contract_value,
                        "stage_id": str(stage_id) if stage_id else None,
                        "updated_at": now,
                        "deal_id": str(deal_id),
                        "tenant_id": str(tenant_id),
                    },
                )
            else:
                stage_id = stage_id or _resolve_stage_id(conn, tenant_id, None, None)
                deal_id = uuid.uuid4()
                conn.execute(
                    text(
                        """
                        insert into deals (
                            id, tenant_id, contact_id, lead_id, agent_id, stage_id, package_id,
                            name, amount, value_zar, status, created_at, updated_at
                        )
                        values (
                            :id, :tenant_id, :contact_id, :lead_id, :agent_id, :stage_id, :package_id,
                            :name, :amount, :value_zar, :status, :created_at, :updated_at
                        )
                        """
                    ),
                    {
                        "id": str(deal_id),
                        "tenant_id": str(tenant_id),
                        "contact_id": str(quote["customer_id"]),
                        "lead_id": str(quote["lead_id"]) if quote["lead_id"] else None,
                        "agent_id": str(quote["agent_id"]) if quote["agent_id"] else None,
                        "stage_id": str(stage_id),
                        "package_id": str(quote["package_id"]) if quote["package_id"] else None,
                        "name": f"Quote {quote_id}",
                        "amount": contract_value,
                        "value_zar": contract_value,
                        "status": "OPEN",
                        "created_at": now,
                        "updated_at": now,
                    },
                )

        row = conn.execute(
            text(
                """
                update quotes
                set status = 'ACCEPTED',
                    accepted_at = :accepted_at,
                    deal_id = :deal_id
                where id = :quote_id and tenant_id = :tenant_id
                returning id, tenant_id, deal_id, customer_id, lead_id, agent_id, package_id,
                          items, total_monthly, total_once_off, term_months, valid_until,
                          status, terms, created_at, sent_at, accepted_at
                """
            ),
            {
                "quote_id": str(quote_id),
                "tenant_id": str(tenant_id),
                "accepted_at": now,
                "deal_id": str(deal_id) if deal_id else None,
            },
        ).mappings().one_or_none()

    return QuoteResponse(
        id=row["id"],
        tenant_id=row["tenant_id"],
        deal_id=row["deal_id"],
        customer_id=row["customer_id"],
        lead_id=row["lead_id"],
        agent_id=row["agent_id"],
        package_id=row["package_id"],
        items=_deserialize_items(row["items"]),
        total_monthly=Decimal(str(row["total_monthly"] or 0)),
        total_once_off=Decimal(str(row["total_once_off"] or 0)),
        term_months=row["term_months"],
        valid_until=row["valid_until"],
        status=row["status"],
        terms=row["terms"],
        created_at=row["created_at"],
        sent_at=row["sent_at"],
        accepted_at=row["accepted_at"],
    )


# Commissions
@app.get("/commissions", response_model=List[CommissionResponse])
async def list_commissions(
    agent_id: Optional[uuid.UUID] = None,
    status_filter: Optional[str] = Query(default=None, alias="status"),
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    ctx: AuthContext = Depends(get_auth_context),
):
    tenant_id = ctx.tenant_id
    if agent_id is None:
        agent_id = ctx.user_id

    conditions = ["tenant_id = :tenant_id", "agent_id = :agent_id"]
    params: Dict[str, Any] = {
        "tenant_id": str(tenant_id),
        "agent_id": str(agent_id),
    }
    if status_filter:
        conditions.append("status = :status")
        params["status"] = status_filter.upper()
    if start_date:
        conditions.append("created_at >= :start_date")
        params["start_date"] = start_date
    if end_date:
        conditions.append("created_at <= :end_date")
        params["end_date"] = end_date

    where_clause = " and ".join(conditions)
    engine = _get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                f"""
                select id, deal_id, agent_id, amount_zar, rate_percent, status,
                       created_at, updated_at
                from commissions
                where {where_clause}
                order by created_at desc
                """
            ),
            params,
        ).mappings().all()
    return [
        CommissionResponse(
            id=row["id"],
            deal_id=row["deal_id"],
            agent_id=row["agent_id"],
            amount_zar=Decimal(str(row["amount_zar"] or 0)),
            rate_percent=row["rate_percent"],
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
        for row in rows
    ]


@app.get("/commissions/report", response_model=List[CommissionReportEntry])
async def commission_report(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    today = date.today()
    if not start_date:
        start_date = date(today.year, today.month, 1)
    if not end_date:
        next_month = start_date + timedelta(days=32)
        end_date = date(next_month.year, next_month.month, 1) - timedelta(days=1)
    end_exclusive = end_date + timedelta(days=1)

    engine = _get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                select agent_id,
                       coalesce(sum(amount_zar), 0) as total_amount,
                       count(*) as deals_count,
                       sum(case when status = 'PENDING' then 1 else 0 end) as pending,
                       sum(case when status = 'APPROVED' then 1 else 0 end) as approved,
                       sum(case when status = 'PAID' then 1 else 0 end) as paid,
                       sum(case when status = 'CLAWBACK' then 1 else 0 end) as clawback
                from commissions
                where tenant_id = :tenant_id
                  and created_at >= :start_date
                  and created_at < :end_exclusive
                group by agent_id
                order by total_amount desc
                """
            ),
            {
                "tenant_id": str(tenant_id),
                "start_date": start_date,
                "end_exclusive": end_exclusive,
            },
        ).mappings().all()

    return [
        CommissionReportEntry(
            agent_id=row["agent_id"],
            total_amount_zar=Decimal(str(row["total_amount"] or 0)),
            deals_count=row["deals_count"],
            pending=row["pending"],
            approved=row["approved"],
            paid=row["paid"],
            clawback=row["clawback"],
        )
        for row in rows
    ]


# Targets
@app.post("/targets", response_model=TargetPerformanceEntry, status_code=status.HTTP_201_CREATED)
async def create_target(
    payload: TargetCreate, tenant_id: uuid.UUID = Depends(get_current_tenant_id)
):
    if payload.period_end < payload.period_start:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="period_end must be after period_start")

    target_id = uuid.uuid4()
    engine = _get_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                insert into sales_targets (
                    id, tenant_id, agent_id, team_id, period_type, period_start, period_end, target_value_zar
                )
                values (
                    :id, :tenant_id, :agent_id, :team_id, :period_type, :period_start, :period_end, :target_value_zar
                )
                """
            ),
            {
                "id": str(target_id),
                "tenant_id": str(tenant_id),
                "agent_id": str(payload.agent_id) if payload.agent_id else None,
                "team_id": str(payload.team_id) if payload.team_id else None,
                "period_type": payload.period_type,
                "period_start": payload.period_start,
                "period_end": payload.period_end,
                "target_value_zar": payload.target_value_zar,
            },
        )

    return TargetPerformanceEntry(
        target_id=target_id,
        agent_id=payload.agent_id,
        team_id=payload.team_id,
        period_start=payload.period_start,
        period_end=payload.period_end,
        target_value_zar=payload.target_value_zar,
        actual_value_zar=Decimal("0.00"),
        variance_zar=(Decimal("0.00") - payload.target_value_zar).quantize(Decimal("0.01")),
    )


@app.get("/targets/performance", response_model=List[TargetPerformanceEntry])
async def target_performance(
    period_start: Optional[date] = None,
    period_end: Optional[date] = None,
    agent_id: Optional[uuid.UUID] = None,
    team_id: Optional[uuid.UUID] = None,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    conditions = ["tenant_id = :tenant_id"]
    params: Dict[str, Any] = {"tenant_id": str(tenant_id)}
    if agent_id:
        conditions.append("agent_id = :agent_id")
        params["agent_id"] = str(agent_id)
    if team_id:
        conditions.append("team_id = :team_id")
        params["team_id"] = str(team_id)
    if period_start:
        conditions.append("period_start >= :period_start")
        params["period_start"] = period_start
    if period_end:
        conditions.append("period_end <= :period_end")
        params["period_end"] = period_end

    where_clause = " and ".join(conditions)
    engine = _get_engine()
    with engine.connect() as conn:
        targets = conn.execute(
            text(
                f"""
                select id, agent_id, team_id, period_start, period_end, target_value_zar
                from sales_targets
                where {where_clause}
                order by period_start desc
                """
            ),
            params,
        ).mappings().all()

        results: List[TargetPerformanceEntry] = []
        for target in targets:
            end_exclusive = target["period_end"] + timedelta(days=1)
            if target["agent_id"]:
                total = conn.execute(
                    text(
                        """
                        select coalesce(sum(value_zar), 0) as total_value
                        from deals
                        where tenant_id = :tenant_id
                          and agent_id = :agent_id
                          and status = 'WON'
                          and closed_at >= :start_date
                          and closed_at < :end_exclusive
                        """
                    ),
                    {
                        "tenant_id": str(tenant_id),
                        "agent_id": str(target["agent_id"]),
                        "start_date": target["period_start"],
                        "end_exclusive": end_exclusive,
                    },
                ).scalar()
            else:
                total = conn.execute(
                    text(
                        """
                        select coalesce(sum(value_zar), 0) as total_value
                        from deals
                        where tenant_id = :tenant_id
                          and status = 'WON'
                          and closed_at >= :start_date
                          and closed_at < :end_exclusive
                        """
                    ),
                    {
                        "tenant_id": str(tenant_id),
                        "start_date": target["period_start"],
                        "end_exclusive": end_exclusive,
                    },
                ).scalar()

            actual_value = Decimal(str(total or 0))
            target_value = Decimal(str(target["target_value_zar"] or 0))
            results.append(
                TargetPerformanceEntry(
                    target_id=target["id"],
                    agent_id=target["agent_id"],
                    team_id=target["team_id"],
                    period_start=target["period_start"],
                    period_end=target["period_end"],
                    target_value_zar=target_value,
                    actual_value_zar=actual_value,
                    variance_zar=(actual_value - target_value).quantize(Decimal("0.01")),
                )
            )

    return results


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8002)
