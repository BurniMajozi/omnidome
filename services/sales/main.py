"""OmniDome Sales Service — async SQLAlchemy ORM.

Manages pipelines, deals, quotes, commissions, targets, leads, contacts.

Port: 8002. Entrypoint: services.sales.main:app (Dockerfile CMD).

Merged 2026-09-12 from main.py (raw-SQL, production) + main_async.py (ORM):
- ORM throughout (AsyncSession via services.sales.database.get_db)
- contact auto-create on create_deal (FK deals_contact_id_fkey — commit 5d215915)
- finance GL bridge on close-won (POST {FINANCE_URL}/journal-entries, verified live)
- lifecycle close-won bridge (POST {LIFECYCLE_URL}/lifecycle/from-sale, verified live)
- lifecycle close-lost bridge (POST {LIFECYCLE_URL}/lifecycle/transition?tenant_id=, verified live)
- quote -> deal uses FULL contract value (monthly*term + once-off), links quote.deal_id
- tenant-configurable commission tiers (commission_tiers, fallback 5/7/10%)
- GET /quotes list (field-sales mobile listQuotes calls it; neither impl had it)
- Lead list supports agent_id + min_interest filters (main.py had them)
- commissions list defaults agent to caller (main.py behaviour, web quick-stats relies on it)
- DealResponse/DealUpdate carry `name` (frontend Deal type requires it)
- QuoteItem accepts monthly_price/name/qty aliases (field-sales quote builder sends them)
- lifespan startup (guard + init_tables with run_with_db_retry) — NOT @app.on_event
- EntitlementGuard middleware; /health + /docs + /openapi.json public
"""

import logging
import os
import re
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import date, datetime, tzinfo, time as dt_time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from services.common.auth import AuthContext, get_auth_context, get_current_tenant_id
from services.common.background_tasks import schedule_background
from services.common.db import run_with_db_retry
from services.common.entitlements import EntitlementGuard
from services.common.event_bus import ensure_schema as ensure_bus_schema, notify
from services.common.middleware import configure_production
from services.common.rate_limiter import RateLimiter
from services.sales import access, lead_actions, lead_service
from services.sales.database import after_commit, get_db, get_session, init_tables
from services.sales.lead_service import Actor
from services.sales.lead_stages import (
    SALES_CHANNELS,
    STANDARD_FUNNEL_STAGES,
    StageChangeError,
    cohort_conversion,
    funnel_bucket,
    is_forward_move,
    normalize_channel,
    stage_key,
)
from services.sales.models import (
    Commission,
    CommissionTier,
    Contact,
    Deal,
    DealStage,
    Lead,
    LeadActivity,
    LeadTask,
    Pipeline,
    Quote,
    Target,
)
from services.sales.schema import ensure_lead_schema, ensure_pipeline_integrity

logger = logging.getLogger("sales")

# ---------------------------------------------------------------------------
# App + guard
# ---------------------------------------------------------------------------

app = FastAPI(title="OmniDome Sales Service", version="2.0.0")

guard = EntitlementGuard(module_id="sales")

configure_production(app)


@app.middleware("http")
async def entitlement_middleware(request, call_next):
    return await guard.middleware(request, call_next)


@asynccontextmanager
async def lifespan(app: FastAPI):
    guard.ensure_startup()
    await run_with_db_retry(init_tables, logger=logger)

    async def _lead_schema() -> None:
        async with get_session() as session:
            await ensure_bus_schema(session)  # sales publishes lead/deal events
            await ensure_lead_schema(session)
            await ensure_pipeline_integrity(session)

    await run_with_db_retry(_lead_schema, logger=logger)
    # Event consumer: lead emails (AgentMail) and campaign audiences (Marketing).
    lead_actions.consumer.start()
    logger.info("Sales service started — tables initialized")
    yield
    logger.info("Sales service shutting down")


app.router.lifespan_context = lifespan


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok", "service": "sales"}


# ---------------------------------------------------------------------------
# External bridges (env-driven; silent skip when unset so local dev works)
# ---------------------------------------------------------------------------

LIFECYCLE_URL = os.getenv("LIFECYCLE_SERVICE_URL", "http://lifecycle:8018")
FINANCE_URL = os.getenv("FINANCE_SERVICE_URL", "http://finance:8015")
BILLING_WEBHOOK_URL = os.getenv("BILLING_WEBHOOK_URL")
NETWORK_WEBHOOK_URL = os.getenv("NETWORK_WEBHOOK_URL")
PROVISIONING_WEBHOOKS = [
    url.strip()
    for url in os.getenv("SALES_PROVISIONING_WEBHOOKS", "").split(",")
    if url.strip()
]

DEFAULT_STAGES = [
    {"name": "Prospecting", "probability": 10, "sort_order": 1},
    {"name": "Qualified", "probability": 25, "sort_order": 2},
    {"name": "Proposal", "probability": 40, "sort_order": 3},
    {"name": "Negotiation", "probability": 60, "sort_order": 4},
    {"name": "Closed Won", "probability": 100, "sort_order": 5},
    {"name": "Closed Lost", "probability": 0, "sort_order": 6},
]


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

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
    # float, not Decimal: Pydantic v2 serializes Decimal as a JSON string,
    # which silently breaks numeric consumers (e.g. dashboard sums that
    # concatenate "0" + "19889.00" + ... instead of adding). Display total —
    # float precision is fine here.
    total_value_zar: float


class DealCreate(BaseModel):
    # value_zar is the deal's TOTAL CONTRACT VALUE (what close-won books as revenue and
    # what commission is paid on): a deal made from a quote is monthly x term + once-off
    # (deal_value_from_quote). A caller that sends a single monthly price (for example
    # R 799) therefore records a much smaller number than one that sends price x 12; the
    # value is stored as sent, not reinterpreted. Note the lifecycle bridge divides
    # value_zar by 12 to get monthly recurring revenue, which assumes an annual figure.
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
    name: str
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
    # From the linked lead, for board cards (SPEC-lead-lifecycle.md)
    lead_reference: Optional[str] = None
    owner_name: Optional[str] = None


class QuoteItem(BaseModel):
    # Canonical fields…
    description: Optional[str] = None
    quantity: Optional[int] = None
    unit_price_zar: Optional[Decimal] = None
    charge_type: str = Field(default="monthly")
    # …plus field-sales mobile aliases (mobile-field-sales-api createQuote
    # sends { product_id, name, monthly_price, qty }).
    name: Optional[str] = None
    product_id: Optional[str] = None
    qty: Optional[int] = None
    monthly_price: Optional[Decimal] = None

    def resolved_description(self) -> str:
        return self.description or self.name or self.product_id or "Item"

    def resolved_quantity(self) -> int:
        return self.quantity if self.quantity is not None else (self.qty or 1)

    def resolved_unit_price(self) -> Decimal:
        if self.unit_price_zar is not None:
            return self.unit_price_zar
        if self.monthly_price is not None:
            return self.monthly_price
        return Decimal("0")


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
    # Set by POST /quotes/{id}/send only: "email" (queued for delivery) or "marked_sent_only".
    delivery: Optional[str] = None


class QuoteSend(BaseModel):
    channel: str = Field(default="email", description="email (whatsapp/sms are not wired yet)")
    recipient: Optional[str] = None
    # Say so explicitly when you only want the quote flagged as sent (for example it was
    # handed over in person). Nothing is delivered and the response says so.
    mark_sent_only: bool = False


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


class DealSummary(BaseModel):
    """Totals computed in SQL (NUMERIC) over the same filters as GET /deals."""
    count: int
    total_value_zar: float
    won_count: int
    won_value_zar: float
    open_count: int
    open_value_zar: float
    lost_count: int
    lost_value_zar: float


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


class PipelinePlacement(BaseModel):
    """Put a new lead straight onto the pipeline board (SPEC-lead-lifecycle.md)."""
    stage_name: str = "Prospecting"
    value_zar: Decimal = Field(default=Decimal("0"), ge=0)
    deal_name: Optional[str] = None


class LeadCreate(BaseModel):
    first_name: str
    last_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    source: str = "FIELD_VISIT"
    source_channel: Optional[str] = None
    interest_level: int = Field(default=3, ge=1, le=5)
    notes: Optional[str] = None
    agent_id: Optional[uuid.UUID] = None
    owner_id: Optional[uuid.UUID] = None
    owner_name: Optional[str] = None
    priority: str = Field(default="normal", pattern="^(low|normal|high|urgent)$")
    pipeline: Optional[PipelinePlacement] = None


class LeadUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    source: Optional[str] = None
    source_channel: Optional[str] = None
    interest_level: Optional[int] = Field(None, ge=1, le=5)
    status: Optional[str] = None
    notes: Optional[str] = None
    agent_id: Optional[uuid.UUID] = None
    owner_id: Optional[uuid.UUID] = None
    owner_name: Optional[str] = None
    priority: Optional[str] = Field(None, pattern="^(low|normal|high|urgent)$")


class LeadResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    contact_id: Optional[uuid.UUID] = None
    agent_id: Optional[uuid.UUID] = None
    first_name: str
    last_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    source: str
    source_channel: Optional[str] = None
    interest_level: int
    status: str
    notes: Optional[str] = None
    converted_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    # Lead record + its place on the board (SPEC-lead-lifecycle.md)
    reference: Optional[str] = None
    owner_id: Optional[uuid.UUID] = None
    owner_name: Optional[str] = None
    priority: str = "normal"
    closed_at: Optional[datetime] = None
    close_reason: Optional[str] = None
    escalated_at: Optional[datetime] = None
    deal_id: Optional[uuid.UUID] = None
    deal_stage: Optional[str] = None
    deal_status: Optional[str] = None
    deal_value_zar: Optional[Decimal] = None
    open_tasks: int = 0


class FunnelStageItem(BaseModel):
    stage: str
    count: int
    pct_of_total: float = 0.0
    value_zar: Decimal = Decimal("0")
    # Cohort view (lead_stages.cohort_conversion): leads that reached this stage
    # or went further, and that cohort as a % of the previous stage's, clamped 0..100.
    # Only set for the open stages and Closed Won.
    cohort_count: Optional[int] = None
    conversion_from_previous_pct: Optional[float] = None


class ChannelFunnelItem(BaseModel):
    channel: str
    channel_label: str
    total_leads: int
    stage_counts: Dict[str, int]
    stage_values_zar: Dict[str, Decimal]
    won_count: int
    lost_count: int
    conversion_rate: float
    # OPEN pipeline only (won and lost excluded). Kept under its old name for the
    # web; open_value_zar is the same number under an unambiguous one.
    total_pipeline_value_zar: Decimal
    open_value_zar: Decimal = Decimal("0")
    won_value_zar: Decimal
    lost_value_zar: Decimal = Decimal("0")


class LeadFunnelResponse(BaseModel):
    channels: List[ChannelFunnelItem]
    overall_funnel: List[FunnelStageItem]
    totals: Dict[str, Any]
    period_days: Optional[int] = None


class LeadConvert(BaseModel):
    name: Optional[str] = Field(None, description="Deal name (defaults to lead name)")
    value_zar: Decimal = Field(default=Decimal("0"), ge=0)
    agent_id: Optional[uuid.UUID] = None
    stage_name: Optional[str] = Field(None, description="Board stage for the new deal (default: first stage)")


class LeadStageChange(BaseModel):
    """Either a lead-phase `status` or a board `stage_name` (SPEC-lead-lifecycle.md)."""
    status: Optional[str] = None
    stage_name: Optional[str] = None
    value_zar: Optional[Decimal] = Field(None, ge=0)
    deal_name: Optional[str] = None
    reason: Optional[str] = None


class LeadActivityResponse(BaseModel):
    id: uuid.UUID
    kind: str
    summary: str
    details: Dict[str, Any] = {}
    actor_id: Optional[uuid.UUID] = None
    actor_name: Optional[str] = None
    created_at: datetime


class LeadTaskResponse(BaseModel):
    id: uuid.UUID
    lead_id: uuid.UUID
    title: str
    kind: str
    due_at: Optional[datetime] = None
    assignee_id: Optional[uuid.UUID] = None
    assignee_name: Optional[str] = None
    status: str
    created_at: datetime
    completed_at: Optional[datetime] = None


class LeadDetailResponse(LeadResponse):
    activities: List[LeadActivityResponse] = []
    tasks: List[LeadTaskResponse] = []


class LeadAssign(BaseModel):
    owner_id: Optional[uuid.UUID] = None
    owner_name: Optional[str] = Field(None, max_length=200)


class LeadNote(BaseModel):
    body: str = Field(..., min_length=1, max_length=8000)
    # ai_draft: a message drafted by an automation for a person to review and send.
    # Only an automation caller keeps it (see add_lead_note); from anyone else it is
    # downgraded, so a person cannot post text that looks like it came from DomeBot.
    kind: str = Field("note", pattern="^(note|call|ai_draft)$")


class LeadEmail(BaseModel):
    subject: str = Field(..., min_length=1, max_length=200)
    body: str = Field(..., min_length=1, max_length=20000)


class LeadTaskCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    due_at: Optional[datetime] = None
    assignee_id: Optional[uuid.UUID] = None
    assignee_name: Optional[str] = Field(None, max_length=200)
    kind: str = Field("task", pattern="^(task|call)$")


class LeadTaskUpdate(BaseModel):
    status: str = Field(..., pattern="^(open|done)$")


class LeadEscalate(BaseModel):
    reason: str = Field(..., min_length=3, max_length=1000)


class LeadOutbound(BaseModel):
    notes: Optional[str] = Field(None, max_length=2000)


class LeadCampaign(BaseModel):
    campaign_id: str = Field(..., min_length=1, max_length=100)
    campaign_name: str = Field(..., min_length=1, max_length=200)


class AutomationContact(BaseModel):
    first_name: Optional[str] = Field(None, max_length=100)
    last_name: Optional[str] = Field(None, max_length=100)
    company: Optional[str] = Field(None, max_length=200)
    email: Optional[str] = Field(None, max_length=255)
    phone: Optional[str] = Field(None, max_length=20)
    address: Optional[str] = None


class AutomationLeadEvent(BaseModel):
    """Called by orchestrator workflows (SPEC-lead-automations.md)."""
    event_type: str = Field(..., max_length=120)
    event_id: Optional[str] = Field(None, max_length=100)
    contact: AutomationContact
    source: str = "PORTAL_WEBSITE"
    target_status: Optional[str] = None
    target_stage: Optional[str] = None
    value_zar: Optional[Decimal] = Field(None, ge=0)
    note: Optional[str] = Field(None, max_length=2000)
    interest_level: int = Field(4, ge=1, le=5)


class AutomationLeadResponse(LeadResponse):
    created: bool = False
    stage_applied: bool = False
    duplicate_event: bool = False


class OwnerResponse(BaseModel):
    id: uuid.UUID
    name: str
    department: Optional[str] = None
    job_title: Optional[str] = None
    email: Optional[str] = None


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


# ---------------------------------------------------------------------------
# Pure helpers (unit-testable without a DB)
# ---------------------------------------------------------------------------

def calculate_quote_totals(items: Optional[List[QuoteItem]]) -> Dict[str, Decimal]:
    """Sum quote line items into monthly / once-off totals."""
    total_monthly = Decimal("0")
    total_once_off = Decimal("0")
    if not items:
        return {"total_monthly": total_monthly, "total_once_off": total_once_off}
    for item in items:
        line_total = item.resolved_unit_price() * item.resolved_quantity()
        if item.charge_type.lower() == "once_off":
            total_once_off += line_total
        else:
            total_monthly += line_total
    return {"total_monthly": total_monthly, "total_once_off": total_once_off}


def apply_discount(value: Decimal, discount_percent: Optional[Decimal]) -> Decimal:
    """Apply a percentage discount; None/0 returns the value unchanged."""
    if not discount_percent:
        return value
    try:
        pct = Decimal(str(discount_percent))
    except (InvalidOperation, ValueError, TypeError):
        return value
    if pct <= 0:
        return value
    return (value - value * pct / Decimal("100")).quantize(Decimal("0.01"))


def deal_value_from_quote(total_monthly: Decimal, total_once_off: Decimal, term_months: int) -> Decimal:
    """Full contract value: monthly * term + once-off (production main.py rule)."""
    return (total_monthly * Decimal(term_months or 12) + total_once_off).quantize(Decimal("0.01"))


def fallback_commission_rate(won_deals_this_month: int) -> Decimal:
    """Default 5/7/10% tiers when no tenant commission_tiers row matches."""
    if won_deals_this_month >= 20:
        return Decimal("10.0")
    if won_deals_this_month >= 10:
        return Decimal("7.0")
    return Decimal("5.0")


def serialize_items(items: Optional[List[QuoteItem]]) -> Optional[List[Dict[str, Any]]]:
    if not items:
        return None
    return [
        {
            "description": item.resolved_description(),
            "quantity": item.resolved_quantity(),
            "unit_price_zar": float(item.resolved_unit_price()),
            "charge_type": item.charge_type,
        }
        for item in items
    ]


def deserialize_items(items: Optional[List[Dict[str, Any]]]) -> Optional[List[QuoteItem]]:
    """Rebuild QuoteItems from stored JSON; tolerant of the mobile alias shape."""
    if not items:
        return None
    rebuilt: List[QuoteItem] = []
    for raw in items:
        data = dict(raw)
        if "description" not in data and "name" in data:
            data["description"] = data["name"]
        if "quantity" not in data and "qty" in data:
            data["quantity"] = data["qty"]
        if "unit_price_zar" not in data and "monthly_price" in data:
            data["unit_price_zar"] = data["monthly_price"]
        rebuilt.append(QuoteItem(**data))
    return rebuilt


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _resolve_tz(tz: Optional[str]) -> Optional[tzinfo]:
    """IANA zone for day-bucketing date filters. None/'UTC' keeps the historic UTC-day
    behaviour; an unknown name is a client error (422)."""
    if tz is None or tz.strip() == "" or tz.strip().upper() == "UTC":
        return None
    try:
        return ZoneInfo(tz.strip())
    except (ZoneInfoNotFoundError, ValueError, OSError):
        raise HTTPException(status_code=422, detail=f"Unknown timezone: {tz}")


def _local_midnight_utc(d: date, zone: Optional[tzinfo]) -> datetime:
    """Midnight of calendar day `d` in `zone`, as a naive UTC instant (the DB stores naive UTC)."""
    naive = datetime.combine(d, dt_time.min)
    if zone is None:
        return naive
    return naive.replace(tzinfo=zone).astimezone(timezone.utc).replace(tzinfo=None)


def _day_start(d: date, zone: Optional[tzinfo] = None) -> datetime:
    return _local_midnight_utc(d, zone)


def _next_day_start(d: date, zone: Optional[tzinfo] = None) -> datetime:
    """Exclusive upper bound for an inclusive end DATE: compare `< next_day_start(end)`,
    so rows stamped during the end day (after midnight) are included."""
    return _local_midnight_utc(d + timedelta(days=1), zone)


async def _ensure_default_pipeline(db: AsyncSession, tenant_id: uuid.UUID) -> uuid.UUID:
    """The tenant's default pipeline, created on first use.

    Creation is serialised per tenant with a transaction-scoped advisory lock (the
    board fires /deals and /pipeline/stages at the same moment on a fresh tenant)
    and backed by the uq_pipelines_one_default partial unique index. Lookups use
    .first() with a fixed order so a tenant that already holds two defaults gets a
    deterministic one instead of a 500."""
    async def _find() -> Optional[uuid.UUID]:
        return (await db.execute(
            select(Pipeline.id).where(Pipeline.tenant_id == tenant_id, Pipeline.is_default == True)  # noqa: E712
            .order_by(Pipeline.id).limit(1)
        )).scalars().first()

    found = await _find()
    if found:
        return found
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": f"sales_pipeline:{tenant_id}"})
    found = await _find()  # another request may have created it while we waited for the lock
    if found:
        return found

    pipeline_id = uuid.uuid4()
    db.add(Pipeline(id=pipeline_id, tenant_id=tenant_id, name="Default Pipeline", is_default=True))
    await db.flush()
    for stage_def in DEFAULT_STAGES:
        db.add(DealStage(
            id=uuid.uuid4(),
            pipeline_id=pipeline_id,
            name=stage_def["name"],
            probability=stage_def["probability"],
            sort_order=stage_def["sort_order"],
        ))
    await db.flush()
    return pipeline_id


async def _get_stages(db: AsyncSession, pipeline_id: uuid.UUID) -> List[DealStage]:
    result = await db.execute(
        select(DealStage)
        .where(DealStage.pipeline_id == pipeline_id)
        .order_by(DealStage.sort_order, DealStage.id)
    )
    return list(result.scalars().all())


async def _tenant_stage(db: AsyncSession, tenant_id: uuid.UUID, stage_id: uuid.UUID) -> DealStage:
    """A stage of one of THIS tenant's pipelines, else 404 (a foreign stage id must
    neither leak its name nor be writable onto a deal)."""
    stage = (await db.execute(
        select(DealStage).join(Pipeline, Pipeline.id == DealStage.pipeline_id)
        .where(DealStage.id == stage_id, Pipeline.tenant_id == tenant_id)
    )).scalars().first()
    if stage is None:
        raise HTTPException(status_code=404, detail="Stage not found")
    return stage


async def _resolve_stage_id(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    stage_id: Optional[uuid.UUID],
    stage_name: Optional[str],
) -> uuid.UUID:
    pipeline_id = await _ensure_default_pipeline(db, tenant_id)
    if stage_id:
        return (await _tenant_stage(db, tenant_id, stage_id)).id
    if stage_name:
        row = (await db.execute(
            select(DealStage.id).where(
                DealStage.pipeline_id == pipeline_id,
                func.lower(DealStage.name) == stage_name.strip().lower(),
            ).order_by(DealStage.sort_order, DealStage.id).limit(1)
        )).scalars().first()
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
    return (await db.execute(
        select(DealStage.id).where(
            DealStage.pipeline_id == pipeline_id,
            func.lower(DealStage.name) == name.lower(),
        ).order_by(DealStage.sort_order, DealStage.id).limit(1)
    )).scalars().first()


# -- client-supplied foreign ids must belong to the caller's tenant ------------

async def _require_lead(db: AsyncSession, tenant_id: uuid.UUID, lead_id: Optional[uuid.UUID]) -> None:
    if lead_id is None:
        return
    found = (await db.execute(
        select(Lead.id).where(Lead.id == lead_id, Lead.tenant_id == tenant_id)
    )).first()
    if not found:
        raise HTTPException(status_code=404, detail="Lead not found")


async def _tenant_row_exists(db: AsyncSession, sql: str, tenant_id: uuid.UUID, row_id: uuid.UUID) -> Optional[bool]:
    """True/False when the lookup ran, None when its table does not exist here."""
    try:
        async with db.begin_nested():
            return (await db.execute(text(sql), {"i": row_id, "t": tenant_id})).first() is not None
    except Exception:  # noqa: BLE001 - table not installed in this deployment
        return None


async def _require_agent(
    db: AsyncSession, tenant_id: uuid.UUID, agent_id: Optional[uuid.UUID], caller: Optional[uuid.UUID] = None,
) -> None:
    """An agent is a login user (users) or an HR employee (employees) of this tenant."""
    if agent_id is None or agent_id == caller:
        return
    for sql in ("SELECT 1 FROM users WHERE id = :i AND tenant_id = :t",
                "SELECT 1 FROM employees WHERE id = :i AND tenant_id = :t"):
        if await _tenant_row_exists(db, sql, tenant_id, agent_id):
            return
    raise HTTPException(status_code=404, detail="Agent not found")


async def _require_package(db: AsyncSession, tenant_id: uuid.UUID, package_id: Optional[uuid.UUID]) -> None:
    if package_id is None:
        return
    found = await _tenant_row_exists(db, "SELECT 1 FROM products WHERE id = :i AND tenant_id = :t",
                                     tenant_id, package_id)
    if found is False:  # no products table at all (None) is not evidence of a foreign id
        raise HTTPException(status_code=404, detail="Package not found")


async def _require_contact(db: AsyncSession, tenant_id: uuid.UUID, contact_id: uuid.UUID) -> None:
    found = (await db.execute(
        select(Contact.id).where(Contact.id == contact_id, Contact.tenant_id == tenant_id)
    )).first()
    if not found:
        raise HTTPException(status_code=404, detail="Customer not found")


async def _require_deal(db: AsyncSession, tenant_id: uuid.UUID, deal_id: Optional[uuid.UUID]) -> None:
    if deal_id is None:
        return
    found = (await db.execute(
        select(Deal.id).where(Deal.id == deal_id, Deal.tenant_id == tenant_id)
    )).first()
    if not found:
        raise HTTPException(status_code=404, detail="Deal not found")


async def _commission_rate(db: AsyncSession, tenant_id: uuid.UUID, agent_id: uuid.UUID) -> Decimal:
    """Tenant-configured tier wins; default 5/7/10% thresholds otherwise.

    The tier is chosen by the agent's WON deals this month INCLUDING the deal being
    closed: the caller flushes the WON status first, so the count does not depend
    on session autoflush (closing the 10th deal of the month earns the 10-deal tier)."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    period_start = date(now.year, now.month, 1)
    next_m = period_start + timedelta(days=32)
    period_end = date(next_m.year, next_m.month, 1)

    result = await db.execute(
        select(func.count(Deal.id)).where(
            Deal.tenant_id == tenant_id,
            Deal.agent_id == agent_id,
            Deal.status == "WON",
            Deal.closed_at >= _day_start(period_start),
            Deal.closed_at < _day_start(period_end),
        )
    )
    count = result.scalar() or 0

    tier_result = await db.execute(
        select(CommissionTier.rate_percent).where(
            CommissionTier.tenant_id == tenant_id,
            CommissionTier.is_active == True,  # noqa: E712
            CommissionTier.min_deals <= count,
            (CommissionTier.max_deals.is_(None) | (CommissionTier.max_deals >= count)),
        )
        .order_by(CommissionTier.rate_percent.desc())
        .limit(1)
    )
    tier_rate = tier_result.scalars().first()
    if tier_rate is not None:
        return Decimal(str(tier_rate))
    return fallback_commission_rate(count)


def _parse_notes_contact(notes: Optional[str]) -> Dict[str, Optional[str]]:
    """Extract contact hints the frontend embeds in deal notes.

    create_deal historically received a random customer_id UUID plus
    'Contact: <name> | Email: <e> | Phone: <p>' inside notes (commit
    5d215915). Preserved so auto-created contacts carry real details.
    """
    out: Dict[str, Optional[str]] = {"first_name": "Walk-in", "last_name": "Customer",
                                     "email": None, "phone": None}
    if not notes:
        return out
    try:
        if "Contact: " in notes:
            c_part = notes.split("Contact: ")[1].split("|")[0].strip()
            tokens = c_part.split(" ")
            if tokens and tokens[0]:
                out["first_name"] = tokens[0]
                out["last_name"] = " ".join(tokens[1:]) if len(tokens) > 1 else "Customer"
        if "Email: " in notes:
            out["email"] = notes.split("Email: ")[1].split("|")[0].strip() or None
        if "Phone: " in notes:
            out["phone"] = notes.split("Phone: ")[1].split("|")[0].strip() or None
    except Exception:
        pass
    return out


async def _ensure_contact(
    db: AsyncSession, tenant_id: uuid.UUID, contact_id: uuid.UUID,
    notes: Optional[str], now: datetime,
) -> uuid.UUID:
    """Return an existing contact id of this tenant, else insert one (satisfies FK).

    An id that belongs to ANOTHER tenant is a clean 404 (it used to be a primary-key
    error, a 500). The insert is ON CONFLICT DO NOTHING so two requests creating the
    same new id cannot 500 each other; ownership is re-checked afterwards."""
    hints = _parse_notes_contact(notes)
    await db.execute(
        pg_insert(Contact).values(
            id=contact_id, tenant_id=tenant_id,
            first_name=hints["first_name"] or "Walk-in",
            last_name=hints["last_name"] or "Customer",
            email=hints["email"], phone=hints["phone"],
            status="ACTIVE", lifecycle_stage="PROSPECT", rica_verified=False,
            created_at=now, updated_at=now,
        ).on_conflict_do_nothing(index_elements=[Contact.id])
    )
    await _require_contact(db, tenant_id, contact_id)
    return contact_id


def _utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Naive datetimes here are UTC (deals.closed_at is timestamptz; a value still in memory after a
    close is naive while one read back is aware): always answer with an aware UTC value."""
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _deal_to_response(deal: Deal, stage_name: Optional[str], lead: Optional[Lead] = None) -> DealResponse:
    return DealResponse(
        lead_reference=lead_service.format_reference(lead.ref_no) if lead else None,
        owner_name=lead.owner_name if lead else None,
        id=deal.id, tenant_id=deal.tenant_id, name=deal.name,
        customer_id=deal.contact_id,
        lead_id=deal.lead_id, agent_id=deal.agent_id, stage_id=deal.stage_id,
        stage_name=stage_name, package_id=deal.package_id,
        value_zar=deal.value_zar, status=deal.status, close_date=deal.close_date,
        closed_at=_utc(deal.closed_at), close_reason=deal.close_reason, notes=deal.notes,
        created_at=deal.created_at, updated_at=deal.updated_at,
    )


def _emit_webhook(url: str, payload: Dict[str, Any]) -> None:
    try:
        with httpx.Client(timeout=10) as client:
            client.post(url, json=payload)
    except Exception:
        return


async def _dispatch_provisioning_bg(payload: Dict[str, Any]) -> None:
    urls = []
    if BILLING_WEBHOOK_URL:
        urls.append(BILLING_WEBHOOK_URL)
    if NETWORK_WEBHOOK_URL:
        urls.append(NETWORK_WEBHOOK_URL)
    urls.extend(PROVISIONING_WEBHOOKS)
    # This background task previously never ran at all (BackgroundTasks bug,
    # see services/common/background_tasks.py) with nothing logged either
    # way -- log unconditionally, even with zero configured webhooks, so a
    # future silent regression here is actually observable next time.
    logger.info(
        "Dispatching deal.closed_won provisioning webhooks: deal_id=%s urls=%d",
        payload.get("deal_id"), len(urls),
    )
    for url in urls:
        _emit_webhook(url, payload)


async def _notify_lifecycle_won(deal: Deal, tenant_id: uuid.UUID) -> None:
    """POST /lifecycle/from-sale — verified live contract (SaleBridgeCreate)."""
    if not LIFECYCLE_URL:
        return
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(
                f"{LIFECYCLE_URL}/lifecycle/from-sale",
                json={
                    "tenant_id": str(tenant_id),
                    "customer_id": str(deal.contact_id),
                    "deal_id": str(deal.id),
                    "agent_id": str(deal.agent_id) if deal.agent_id else None,
                    "plan": str(deal.package_id) if deal.package_id else None,
                    "monthly_recurring_revenue": float(deal.value_zar or 0) / 12,
                    "lead_id": str(deal.lead_id) if deal.lead_id else None,
                },
                headers={"X-Tenant-Id": str(tenant_id)},
            )
    except Exception:
        pass  # Don't fail the sale if lifecycle is down


async def _notify_lifecycle_lost(deal: Deal, tenant_id: uuid.UUID, reason: str) -> None:
    """POST /lifecycle/transition?tenant_id= — verified live contract."""
    if not LIFECYCLE_URL:
        return
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(
                f"{LIFECYCLE_URL}/lifecycle/transition",
                params={"tenant_id": str(tenant_id)},
                json={
                    "customer_id": str(deal.contact_id),
                    "to_stage": "Closed Lost",
                    "reason": reason,
                    "trigger_source": "sale",
                    "trigger_id": str(deal.id),
                },
                headers={"X-Tenant-Id": str(tenant_id)},
            )
    except Exception:
        pass


async def _notify_finance_won(deal: Deal, tenant_id: uuid.UUID, now: datetime) -> None:
    """POST /journal-entries — verified live contract (double-entry, balanced)."""
    if not FINANCE_URL:
        return
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(
                f"{FINANCE_URL}/journal-entries",
                json={
                    "entry_date": now.strftime("%Y-%m-%d"),
                    "reference": f"DEAL-{str(deal.id)[:8]}",
                    "description": f"Won deal - {deal.contact_id}",
                    "source": "SALES",
                    "source_id": str(deal.id),
                    "lines": [
                        {
                            "account_code": "1100",
                            "account_name": "Accounts Receivable",
                            "description": f"AR - Customer {str(deal.contact_id)[:8]}",
                            "debit": float(deal.value_zar or 0),
                            "credit": 0,
                        },
                        {
                            "account_code": "4000",
                            "account_name": "Revenue - FTTH Subscriptions",
                            "description": f"Revenue - Deal {str(deal.id)[:8]}",
                            "debit": 0,
                            "credit": float(deal.value_zar or 0),
                        },
                    ],
                },
                headers={"X-Tenant-Id": str(tenant_id)},
            )
    except Exception:
        pass  # Don't fail the sale if finance is down


def _actor(ctx: Optional[AuthContext]) -> Actor:
    return Actor(id=ctx.user_id if ctx else None)


def _closed_deal_decision(deal_status: Optional[str], target: str) -> str:
    """Closed deals are terminal. `target` is "WON" or "LOST".

    Returns "proceed" for an open deal and "noop" when the deal is ALREADY closed
    the same way (repeating a close is idempotent: 200, no side effects). Closing it
    the other way is a 409; reversing a closed deal is not supported."""
    current = (deal_status or "OPEN").upper()
    if current not in ("WON", "LOST"):
        return "proceed"
    if current == target:
        return "noop"
    if current == "WON":
        raise HTTPException(status_code=409, detail="Deal is already won; a won deal cannot be closed as lost "
                            "(its commission and journal entry are already booked)")
    raise HTTPException(status_code=409, detail="Deal is already lost; a lost deal cannot be closed as won "
                        "(create a new deal instead)")


async def _lock_deal(db: AsyncSession, tenant_id: uuid.UUID, deal_id: uuid.UUID) -> Deal:
    """Load the tenant's deal under SELECT ... FOR UPDATE, fresh from the database.

    The status check that follows happens while holding the row lock, so two
    concurrent closes are serialised: the second sees WON/LOST and books nothing."""
    deal = (await db.execute(
        select(Deal).where(Deal.id == deal_id, Deal.tenant_id == tenant_id)
        .with_for_update().execution_options(populate_existing=True)
    )).scalars().first()
    if deal is None:
        raise HTTPException(status_code=404, detail="Deal not found")
    return deal


async def _close_won(db: AsyncSession, tenant_id: uuid.UUID, deal: Deal) -> None:
    """Close a deal as won: Closed Won stage, commission, then (after the commit)
    finance + lifecycle bridges and provisioning webhooks. Shared by the board and
    the lead table. Idempotent: an already-won deal does nothing; a lost one is a 409.

    Everything here is DB work in the caller's transaction; the calls to other
    services are queued with after_commit(), so a rolled-back close posts nothing
    and a committed one posts exactly once."""
    if _closed_deal_decision(deal.status, "WON") == "noop":
        return
    await db.flush()  # keep pending edits, then re-read the row under its lock
    await db.refresh(deal, with_for_update=True)
    if _closed_deal_decision(deal.status, "WON") == "noop":
        return
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    closed_stage_id = await _get_closed_stage_id(db, tenant_id, "Closed Won")
    deal.status = "WON"
    deal.closed_at = now
    deal.updated_at = now
    if closed_stage_id:
        deal.stage_id = closed_stage_id
    await db.flush()  # the commission tier counts this deal as won

    # Commission per agent tier, one per deal.
    if deal.agent_id:
        already = (await db.execute(
            select(Commission.id).where(Commission.deal_id == deal.id, Commission.status != "CLAWBACK").limit(1)
        )).first()
        if not already:
            rate = await _commission_rate(db, tenant_id, deal.agent_id)
            amount = ((deal.value_zar or Decimal("0")) * rate / Decimal("100")).quantize(Decimal("0.01"))
            db.add(Commission(
                id=uuid.uuid4(), tenant_id=tenant_id, deal_id=deal.id,
                agent_id=deal.agent_id, amount_zar=amount, rate_percent=rate,
                status="PENDING", created_at=now, updated_at=now,
            ))
    await db.flush()

    # Bridges: queued for after the commit, non-blocking, never fail the sale.
    payload = {
        "event": "deal.closed_won", "deal_id": str(deal.id),
        "tenant_id": str(tenant_id), "customer_id": str(deal.contact_id),
        "agent_id": str(deal.agent_id) if deal.agent_id else None,
        "package_id": str(deal.package_id) if deal.package_id else None,
        "value_zar": float(deal.value_zar or 0), "closed_at": now.isoformat(),
    }

    async def _bridges() -> None:
        await _notify_lifecycle_won(deal, tenant_id)
        await _notify_finance_won(deal, tenant_id, now)
        schedule_background(_dispatch_provisioning_bg(payload))

    after_commit(db, _bridges)


async def _close_lost(db: AsyncSession, tenant_id: uuid.UUID, deal: Deal, reason: str) -> None:
    if _closed_deal_decision(deal.status, "LOST") == "noop":
        return
    await db.flush()
    await db.refresh(deal, with_for_update=True)
    if _closed_deal_decision(deal.status, "LOST") == "noop":
        return
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    closed_stage_id = await _get_closed_stage_id(db, tenant_id, "Closed Lost")
    deal.status = "LOST"
    deal.closed_at = now
    deal.close_reason = reason
    deal.updated_at = now
    if closed_stage_id:
        deal.stage_id = closed_stage_id
    await db.flush()

    async def _bridges() -> None:
        await _notify_lifecycle_lost(deal, tenant_id, reason)

    after_commit(db, _bridges)


async def _set_deal_stage(
    db: AsyncSession, tenant_id: uuid.UUID, deal: Deal, stage_id: uuid.UUID, ctx: Optional[AuthContext],
) -> Optional[DealStage]:
    """Board move. Closed Won runs the full close-won path; Closed Lost needs the
    close-lost route (reason); closed deals don't move. Mirrors onto the lead.
    The stage must belong to this tenant (404 otherwise)."""
    stage = await _tenant_stage(db, tenant_id, stage_id)
    if deal.status in ("WON", "LOST"):
        raise HTTPException(status_code=409, detail=f"Deal is already closed ({deal.status.lower()})")
    if stage.name.lower() == "closed lost":
        raise HTTPException(status_code=400, detail="Use close-lost with a reason to close a deal as lost")
    if stage.name.lower() == "closed won":
        await _close_won(db, tenant_id, deal)
    else:
        deal.stage_id = stage_id
        deal.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        await db.flush()
    await lead_service.sync_lead_from_deal(db, deal, stage.name, _actor(ctx))
    await lead_service.publish_deal_event(db, deal, stage.name)
    return stage


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/")
async def root():
    return {"message": "OmniDome Sales Service v2.0 (async) is active"}


# ── Pipeline ─────────────────────────────────────────────────────────────

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
    totals = {row.stage_id: {"deal_count": row.deal_count, "total_value": row.total_value}
              for row in result.all()}

    overview = []
    for stage in stages:
        t = totals.get(stage.id, {"deal_count": 0, "total_value": 0})
        overview.append(PipelineOverviewStage(
            id=stage.id, name=stage.name, probability=stage.probability,
            sort_order=stage.sort_order, deal_count=t["deal_count"],
            total_value_zar=float(t["total_value"] or 0),
        ))
    return overview


@app.get("/pipeline/stages", response_model=List[PipelineStage])
async def list_pipeline_stages(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    pipeline_id = await _ensure_default_pipeline(db, tenant_id)
    stages = await _get_stages(db, pipeline_id)
    return [PipelineStage(id=s.id, name=s.name, probability=s.probability, sort_order=s.sort_order)
            for s in stages]


@app.post("/pipeline/stages", response_model=PipelineStage, status_code=201)
async def create_pipeline_stage(
    payload: PipelineStageCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
    _auth: AuthContext = Depends(access.require_tier("admin")),
):
    name = re.sub(r"\s+", " ", (payload.name or "").strip())
    if not name:
        raise HTTPException(status_code=422, detail="A stage needs a name")
    pipeline_id = await _ensure_default_pipeline(db, tenant_id)
    # Stage names are unique per pipeline, case-insensitively; in particular there
    # is exactly one Closed Won and one Closed Lost (the close paths look them up by name).
    clash = (await db.execute(
        select(DealStage.id).where(DealStage.pipeline_id == pipeline_id,
                                   func.lower(DealStage.name) == name.lower()).limit(1)
    )).first()
    if clash:
        raise HTTPException(status_code=409, detail=f"A stage named '{name}' already exists in this pipeline")
    sort_order = payload.sort_order
    if sort_order is None:
        result = await db.execute(
            select(func.coalesce(func.max(DealStage.sort_order), 0))
            .where(DealStage.pipeline_id == pipeline_id)
        )
        sort_order = (result.scalar() or 0) + 1

    stage = DealStage(
        id=uuid.uuid4(), pipeline_id=pipeline_id, name=name,
        probability=payload.probability, sort_order=sort_order,
    )
    db.add(stage)
    await db.flush()
    return PipelineStage(id=stage.id, name=stage.name, probability=stage.probability,
                         sort_order=stage.sort_order)


# ── Deals ────────────────────────────────────────────────────────────────

@app.post("/deals", response_model=DealResponse, status_code=201)
async def create_deal(
    payload: DealCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
):
    stage_id = await _resolve_stage_id(db, tenant_id, payload.stage_id, payload.stage_name)
    await _require_lead(db, tenant_id, payload.lead_id)
    await _require_agent(db, tenant_id, payload.agent_id, ctx.user_id)
    await _require_package(db, tenant_id, payload.package_id)
    deal_id = uuid.uuid4()
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    # Auto-create/resolve contact so deals_contact_id_fkey never fails.
    contact_id = await _ensure_contact(db, tenant_id, payload.customer_id, payload.notes, now)

    deal = Deal(
        id=deal_id, tenant_id=tenant_id, contact_id=contact_id,
        lead_id=payload.lead_id, agent_id=payload.agent_id, stage_id=stage_id,
        package_id=payload.package_id, name=payload.name, amount=payload.value_zar,
        value_zar=payload.value_zar, status="OPEN", close_date=payload.close_date,
        notes=payload.notes, created_at=now, updated_at=now,
    )
    db.add(deal)
    await db.flush()

    stage = await db.get(DealStage, stage_id)
    return _deal_to_response(deal, stage.name if stage else None)


def _deal_conditions(
    tenant_id: uuid.UUID, *, stage_id=None, stage=None, agent_id=None, status_filter=None,
    start_date=None, end_date=None, closed_from=None, closed_to=None, min_value=None, max_value=None,
    zone: Optional[tzinfo] = None,
) -> list:
    """WHERE conditions shared by GET /deals and GET /deals/summary. Date filters are
    inclusive DATES: an end date means the whole end day (< end + 1 day)."""
    conds: list = [Deal.tenant_id == tenant_id]
    if stage_id:
        conds.append(Deal.stage_id == stage_id)
    if stage:
        conds.append(func.lower(DealStage.name) == stage.lower())
    if agent_id:
        conds.append(Deal.agent_id == agent_id)
    if status_filter:
        conds.append(Deal.status == status_filter.upper())
    if start_date:
        conds.append(Deal.created_at >= _day_start(start_date))
    if end_date:
        conds.append(Deal.created_at < _next_day_start(end_date))
    if closed_from:
        conds.append(Deal.closed_at >= _day_start(closed_from, zone))
    if closed_to:
        conds.append(Deal.closed_at < _next_day_start(closed_to, zone))
    if min_value is not None:
        conds.append(Deal.value_zar >= min_value)
    if max_value is not None:
        conds.append(Deal.value_zar <= max_value)
    return conds


@app.get("/deals", response_model=List[DealResponse])
async def list_deals(
    response: Response,
    stage_id: Optional[uuid.UUID] = None,
    stage: Optional[str] = None,
    agent_id: Optional[uuid.UUID] = None,
    status_filter: Optional[str] = Query(default=None, alias="status"),
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    closed_from: Optional[date] = None,
    closed_to: Optional[date] = None,
    tz: Optional[str] = Query(default=None, description="IANA zone for closed_from/closed_to day boundaries (default UTC)"),
    min_value: Optional[Decimal] = None,
    max_value: Optional[Decimal] = None,
    limit: int = Query(500, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    """Deals, newest first. The body is still a bare list; the total matching the
    filters (before limit/offset) is in the X-Total-Count header. closed_from /
    closed_to filter on the close date (inclusive days), start_date / end_date
    on the creation date. For revenue totals use GET /deals/summary instead of summing rows."""
    conds = _deal_conditions(
        tenant_id, stage_id=stage_id, stage=stage, agent_id=agent_id, status_filter=status_filter,
        start_date=start_date, end_date=end_date, closed_from=closed_from, closed_to=closed_to,
        min_value=min_value, max_value=max_value, zone=_resolve_tz(tz))
    q = (
        select(Deal, DealStage.name.label("stage_name"), Lead)
        .outerjoin(DealStage, DealStage.id == Deal.stage_id)
        # tenant-scoped join: a foreign lead id on a deal must not surface that lead's reference/owner
        .outerjoin(Lead, and_(Lead.id == Deal.lead_id, Lead.tenant_id == Deal.tenant_id))
        .where(*conds)
        .order_by(Deal.created_at.desc(), Deal.id)
        .limit(limit).offset(offset)
    )
    total = (await db.execute(
        select(func.count(Deal.id)).select_from(Deal)
        .outerjoin(DealStage, DealStage.id == Deal.stage_id).where(*conds)
    )).scalar() or 0
    response.headers["X-Total-Count"] = str(total)
    response.headers["X-Limit"] = str(limit)
    response.headers["X-Offset"] = str(offset)
    result = await db.execute(q)
    return [
        _deal_to_response(row.Deal, row.stage_name, row.Lead)
        for row in result.all()
    ]


def _deal_summary_query(conds: list):
    """Every figure in one SQL statement over NUMERIC, never summed in Python floats."""
    def _sum(*extra):
        expr = func.sum(Deal.value_zar)
        if extra:
            expr = expr.filter(*extra)
        return func.coalesce(expr, 0)

    def _count(*extra):
        expr = func.count(Deal.id)
        return expr.filter(*extra) if extra else expr

    return (
        select(
            _count().label("count"), _sum().label("total_value"),
            _count(Deal.status == "WON").label("won_count"), _sum(Deal.status == "WON").label("won_value"),
            _count(Deal.status == "OPEN").label("open_count"), _sum(Deal.status == "OPEN").label("open_value"),
            _count(Deal.status == "LOST").label("lost_count"), _sum(Deal.status == "LOST").label("lost_value"),
        )
        .select_from(Deal).outerjoin(DealStage, DealStage.id == Deal.stage_id).where(*conds)
    )


def _money(value: Any) -> float:
    return float(Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


@app.get("/deals/summary", response_model=DealSummary)
async def deals_summary(
    stage_id: Optional[uuid.UUID] = None,
    stage: Optional[str] = None,
    agent_id: Optional[uuid.UUID] = None,
    status_filter: Optional[str] = Query(default=None, alias="status"),
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    closed_from: Optional[date] = None,
    closed_to: Optional[date] = None,
    tz: Optional[str] = Query(default=None, description="IANA zone for closed_from/closed_to day boundaries (default UTC)"),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    """Count and value (ZAR) of the deals matching the same filters as GET /deals,
    split by status, without pulling every row. Won revenue for a period:
    ?status=WON&closed_from=2026-09-01&closed_to=2026-09-30."""
    conds = _deal_conditions(
        tenant_id, stage_id=stage_id, stage=stage, agent_id=agent_id, status_filter=status_filter,
        start_date=start_date, end_date=end_date, closed_from=closed_from, closed_to=closed_to, zone=_resolve_tz(tz))
    row = (await db.execute(_deal_summary_query(conds))).one()
    return DealSummary(
        count=row.count, total_value_zar=_money(row.total_value),
        won_count=row.won_count, won_value_zar=_money(row.won_value),
        open_count=row.open_count, open_value_zar=_money(row.open_value),
        lost_count=row.lost_count, lost_value_zar=_money(row.lost_value),
    )


@app.get("/deals/{deal_id}", response_model=DealResponse)
async def get_deal(
    deal_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Deal, DealStage.name.label("stage_name"), Lead)
        .outerjoin(DealStage, Deal.stage_id == DealStage.id)
        .outerjoin(Lead, and_(Lead.id == Deal.lead_id, Lead.tenant_id == Deal.tenant_id))
        .where(Deal.id == deal_id, Deal.tenant_id == tenant_id)
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="Deal not found")
    return _deal_to_response(row.Deal, row.stage_name, row.Lead)


@app.delete("/deals/{deal_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_deal(
    deal_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
    _auth: AuthContext = Depends(access.require_tier("admin")),
):
    deal = await _lock_deal(db, tenant_id, deal_id)
    lead = await db.get(Lead, deal.lead_id) if deal.lead_id else None
    await db.delete(deal)
    await db.flush()
    if lead is not None and lead.tenant_id == tenant_id and lead.status == "CONVERTED":
        remaining = (await lead_service.deals_by_lead(db, [lead.id])).get(lead.id)
        if remaining is None:
            lead.status = "QUALIFIED"
            lead.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
            await lead_service.record_activity(
                db, tenant_id, lead.id, "stage_changed",
                "Deal deleted from the pipeline board; lead back to Qualified",
                {"deal_id": str(deal_id)})


@app.put("/deals/{deal_id}", response_model=DealResponse)
async def update_deal(
    deal_id: uuid.UUID,
    payload: DealUpdate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
):
    deal = await _lock_deal(db, tenant_id, deal_id)
    await _require_agent(db, tenant_id, payload.agent_id, ctx.user_id)
    await _require_package(db, tenant_id, payload.package_id)

    now = datetime.now(timezone.utc).replace(tzinfo=None)
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
    deal.updated_at = now
    if (payload.stage_id or payload.stage_name):
        target = await _resolve_stage_id(db, tenant_id, payload.stage_id, payload.stage_name)
        if target != deal.stage_id:
            await _set_deal_stage(db, tenant_id, deal, target, ctx)
    await db.flush()

    stage = await db.get(DealStage, deal.stage_id) if deal.stage_id else None
    return _deal_to_response(deal, stage.name if stage else None)


@app.put("/deals/{deal_id}/stage", response_model=DealResponse)
async def move_deal_stage(
    deal_id: uuid.UUID,
    payload: DealStageUpdate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
):
    deal = await _lock_deal(db, tenant_id, deal_id)

    now = datetime.now(timezone.utc).replace(tzinfo=None)
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

    stage = await _set_deal_stage(db, tenant_id, deal, stage_id, ctx)
    return _deal_to_response(deal, stage.name if stage else None)


@app.post("/deals/{deal_id}/close-won", response_model=DealResponse)
async def close_deal_won(
    deal_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
):
    deal = await _lock_deal(db, tenant_id, deal_id)  # row lock: concurrent closes are serialised
    if _closed_deal_decision(deal.status, "WON") == "proceed":  # 409 if lost; repeat of the same close is a no-op
        await _close_won(db, tenant_id, deal)
        await lead_service.sync_lead_from_deal(db, deal, "Closed Won", _actor(ctx))
        await lead_service.publish_deal_event(db, deal, "Closed Won")

    stage = await db.get(DealStage, deal.stage_id) if deal.stage_id else None
    return _deal_to_response(deal, stage.name if stage else "Closed Won")


@app.post("/deals/{deal_id}/close-lost", response_model=DealResponse)
async def close_deal_lost(
    deal_id: uuid.UUID,
    reason: str = Query(..., min_length=3),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
):
    deal = await _lock_deal(db, tenant_id, deal_id)
    if _closed_deal_decision(deal.status, "LOST") == "proceed":  # 409 if won; repeat is a no-op
        await _close_lost(db, tenant_id, deal, reason)
        await lead_service.sync_lead_from_deal(db, deal, "Closed Lost", _actor(ctx))
        await lead_service.publish_deal_event(db, deal, "Closed Lost")

    stage = await db.get(DealStage, deal.stage_id) if deal.stage_id else None
    return _deal_to_response(deal, stage.name if stage else "Closed Lost")


# ── Quotes ───────────────────────────────────────────────────────────────

@app.post("/quotes", response_model=QuoteResponse, status_code=201)
async def create_quote(
    payload: QuoteCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    await _require_contact(db, tenant_id, payload.customer_id)
    await _require_deal(db, tenant_id, payload.deal_id)
    await _require_lead(db, tenant_id, payload.lead_id)
    await _require_agent(db, tenant_id, payload.agent_id)
    await _require_package(db, tenant_id, payload.package_id)
    quote_id = uuid.uuid4()
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    if payload.items:
        totals = calculate_quote_totals(payload.items)
        total_monthly = totals["total_monthly"]
        total_once_off = totals["total_once_off"]
    else:
        total_monthly = payload.total_monthly or Decimal("0")
        total_once_off = payload.total_once_off or Decimal("0")

    total_monthly = apply_discount(total_monthly, payload.discount_percent).quantize(Decimal("0.01"))
    total_once_off = apply_discount(total_once_off, payload.discount_percent).quantize(Decimal("0.01"))
    valid_until = date.today() + timedelta(days=payload.valid_days)

    quote = Quote(
        id=quote_id, tenant_id=tenant_id, deal_id=payload.deal_id,
        customer_id=payload.customer_id, lead_id=payload.lead_id,
        agent_id=payload.agent_id, package_id=payload.package_id,
        items=serialize_items(payload.items), total_monthly=total_monthly,
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


@app.get("/quotes", response_model=List[QuoteResponse])
async def list_quotes(
    status_filter: Optional[str] = Query(default=None, alias="status"),
    customer_id: Optional[uuid.UUID] = None,
    deal_id: Optional[uuid.UUID] = None,
    limit: int = Query(50, ge=1, le=200),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    """Quote list — called by field-sales mobile listQuotes; no impl had it."""
    q = select(Quote).where(Quote.tenant_id == tenant_id)
    if status_filter:
        q = q.where(Quote.status == status_filter.upper())
    if customer_id:
        q = q.where(Quote.customer_id == customer_id)
    if deal_id:
        q = q.where(Quote.deal_id == deal_id)
    q = q.order_by(Quote.created_at.desc()).limit(limit)
    result = await db.execute(q)
    return [
        QuoteResponse(
            id=quote.id, tenant_id=quote.tenant_id, deal_id=quote.deal_id,
            customer_id=quote.customer_id, lead_id=quote.lead_id, agent_id=quote.agent_id,
            package_id=quote.package_id, items=deserialize_items(quote.items),
            total_monthly=quote.total_monthly, total_once_off=quote.total_once_off,
            term_months=quote.term_months, valid_until=quote.valid_until,
            status=quote.status, terms=quote.terms, created_at=quote.created_at,
            sent_at=quote.sent_at, accepted_at=quote.accepted_at,
        )
        for quote in result.scalars().all()
    ]


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
        package_id=quote.package_id, items=deserialize_items(quote.items),
        total_monthly=quote.total_monthly, total_once_off=quote.total_once_off,
        term_months=quote.term_months, valid_until=quote.valid_until,
        status=quote.status, terms=quote.terms, created_at=quote.created_at,
        sent_at=quote.sent_at, accepted_at=quote.accepted_at,
    )


def _quote_response(quote: Quote, delivery: Optional[str] = None) -> QuoteResponse:
    return QuoteResponse(
        id=quote.id, tenant_id=quote.tenant_id, deal_id=quote.deal_id,
        customer_id=quote.customer_id, lead_id=quote.lead_id, agent_id=quote.agent_id,
        package_id=quote.package_id, items=deserialize_items(quote.items),
        total_monthly=quote.total_monthly, total_once_off=quote.total_once_off,
        term_months=quote.term_months, valid_until=quote.valid_until,
        status=quote.status, terms=quote.terms, created_at=quote.created_at,
        sent_at=quote.sent_at, accepted_at=quote.accepted_at, delivery=delivery,
    )


def _quote_expired(quote: Quote, today: Optional[date] = None) -> bool:
    return bool(quote.valid_until and quote.valid_until < (today or date.today()))


def _quote_email_html(quote: Quote) -> str:
    lines = [
        "Thank you for your interest. Your quote:",
        f"Monthly: R {quote.total_monthly:,.2f}",
        f"Once-off: R {quote.total_once_off:,.2f}",
        f"Term: {quote.term_months} months",
        f"Valid until: {quote.valid_until:%d %b %Y}" if quote.valid_until else "",
        quote.terms or "",
    ]
    return lead_actions.email_html("\n".join(line for line in lines if line))


async def _lock_quote(db: AsyncSession, tenant_id: uuid.UUID, quote_id: uuid.UUID) -> Quote:
    quote = (await db.execute(
        select(Quote).where(Quote.id == quote_id, Quote.tenant_id == tenant_id)
        .with_for_update().execution_options(populate_existing=True)
    )).scalars().first()
    if quote is None:
        raise HTTPException(status_code=404, detail="Quote not found")
    return quote


@app.post("/quotes/{quote_id}/send", response_model=QuoteResponse)
async def send_quote(
    quote_id: uuid.UUID,
    payload: QuoteSend,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
    _auth: AuthContext = Depends(access.require_tier("agent")),
):
    """Deliver a quote by email, or (mark_sent_only=true) only flag it as sent.

    The quote is marked SENT only when something was actually sent, or when the
    caller asked for the flag alone. `delivery` in the response says which:
    "email" (handed to the mail provider) or "marked_sent_only" (nothing delivered).
    An opted-out address is never emailed. SMS / WhatsApp are not wired: 501."""
    quote = await _lock_quote(db, tenant_id, quote_id)
    if quote.status not in ("DRAFT", "SENT"):
        raise HTTPException(status_code=409, detail=f"A {quote.status.lower()} quote cannot be sent")
    if _quote_expired(quote):
        raise HTTPException(status_code=409, detail="This quote has expired; create a new one")
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    if payload.mark_sent_only:
        quote.status = "SENT"
        quote.sent_at = now
        await db.flush()
        return _quote_response(quote, delivery="marked_sent_only")

    if (payload.channel or "email").lower() != "email":
        raise HTTPException(status_code=501, detail=f"Sending by {payload.channel} is not available yet; "
                            "use channel=email, or mark_sent_only=true to record that it was handed over")
    recipient = (payload.recipient or "").strip()
    if not recipient:
        contact = await db.get(Contact, quote.customer_id)
        recipient = (contact.email or "").strip() if contact and contact.tenant_id == tenant_id else ""
    if not recipient:
        raise HTTPException(status_code=400, detail="No recipient: pass `recipient` or give the customer an email address")
    if await lead_actions.email_is_suppressed(db, tenant_id, recipient):
        raise HTTPException(status_code=409, detail="This address has opted out of email; the quote was not sent")
    try:
        await lead_actions.agentmail.send_email(recipient, "Your quote", _quote_email_html(quote))
    except lead_actions.agentmail.EmailNotConfigured as exc:
        raise HTTPException(status_code=501, detail="Email sending is not configured for this tenant; "
                            "use mark_sent_only=true to record a quote handed over another way") from exc
    except Exception as exc:  # noqa: BLE001
        logger.warning("Quote %s email failed: %s", quote_id, exc)
        raise HTTPException(status_code=502, detail="The mail provider did not accept the email; the quote was not sent") from exc
    quote.status = "SENT"
    quote.sent_at = now
    await db.flush()
    return _quote_response(quote, delivery="email")


@app.post("/quotes/{quote_id}/accept", response_model=QuoteResponse)
async def accept_quote(
    quote_id: uuid.UUID,
    payload: QuoteAccept,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    """Accept a SENT, unexpired quote. A deal that is already closed is never reopened
    or rewritten (409), and an accepted quote cannot be accepted twice."""
    quote = await _lock_quote(db, tenant_id, quote_id)
    if quote.status != "SENT":
        raise HTTPException(status_code=409, detail=f"Only a sent quote can be accepted (this one is {quote.status.lower()})")
    if _quote_expired(quote):
        raise HTTPException(status_code=409, detail="This quote has expired and cannot be accepted")

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    deal: Optional[Deal] = None
    if payload.create_deal and quote.deal_id:
        deal = await _lock_deal(db, tenant_id, quote.deal_id)
        if deal.status in ("WON", "LOST"):
            raise HTTPException(status_code=409, detail=f"The deal for this quote is already closed ({deal.status.lower()})")

    quote.status = "ACCEPTED"
    quote.accepted_at = now

    if payload.create_deal:
        contract_value = deal_value_from_quote(
            quote.total_monthly or Decimal("0"),
            quote.total_once_off or Decimal("0"),
            quote.term_months or 12,
        )
        if deal is not None:
            # Open deal: record the agreed contract value; its stage stays where the team put it.
            deal.value_zar = contract_value
            deal.amount = contract_value
            deal.updated_at = now
        else:
            stage_id = await _resolve_stage_id(db, tenant_id, None, payload.stage_name or "Proposal")
            # Quote customer is an existing contact (quotes.customer_id FKs contacts).
            deal = Deal(
                id=uuid.uuid4(), tenant_id=tenant_id, contact_id=quote.customer_id,
                lead_id=quote.lead_id, agent_id=quote.agent_id, stage_id=stage_id,
                package_id=quote.package_id, name=f"Quote {quote.id} deal",
                amount=contract_value, value_zar=contract_value,
                status="OPEN", created_at=now, updated_at=now,
            )
            db.add(deal)
            await db.flush()
            quote.deal_id = deal.id

    await db.flush()
    return _quote_response(quote)


# ── Commissions ──────────────────────────────────────────────────────────

@app.get("/commissions", response_model=List[CommissionResponse])
async def list_commissions(
    agent_id: Optional[uuid.UUID] = None,
    deal_id: Optional[uuid.UUID] = None,
    status_filter: Optional[str] = Query(default=None, alias="status"),
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    ctx: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    # Production behaviour: default the agent filter to the caller so agents
    # see their own commissions (web quick-stats relies on this). Reading another
    # agent's commissions needs a manager role.
    if agent_id is None:
        agent_id = ctx.user_id
    if agent_id != ctx.user_id:
        await access.require(ctx, db, "manager")

    q = select(Commission).where(
        Commission.tenant_id == ctx.tenant_id,
        Commission.agent_id == agent_id,
    )
    if deal_id:
        q = q.where(Commission.deal_id == deal_id)
    if status_filter:
        q = q.where(Commission.status == status_filter.upper())
    if start_date:
        q = q.where(Commission.created_at >= _day_start(start_date))
    if end_date:
        q = q.where(Commission.created_at < _next_day_start(end_date))
    q = q.order_by(Commission.created_at.desc())
    result = await db.execute(q)
    return [
        CommissionResponse(
            id=c.id, deal_id=c.deal_id, agent_id=c.agent_id,
            amount_zar=c.amount_zar, rate_percent=c.rate_percent,
            status=c.status, created_at=c.created_at, updated_at=c.updated_at,
        )
        for c in result.scalars().all()
    ]


def _commission_report_query(tenant_id: uuid.UUID, start: datetime, end_exclusive: datetime):
    """One row per agent. The per-status counts are COUNT(*) FILTER (WHERE status = ...),
    not a cast of a boolean expression (that form is not valid SQLAlchemy and 500ed)."""
    return (
        select(
            Commission.agent_id,
            func.coalesce(func.sum(Commission.amount_zar), 0).label("total_amount"),
            func.count(Commission.id).label("deals_count"),
            func.count(Commission.id).filter(Commission.status == "PENDING").label("pending"),
            func.count(Commission.id).filter(Commission.status == "APPROVED").label("approved"),
            func.count(Commission.id).filter(Commission.status == "PAID").label("paid"),
            func.count(Commission.id).filter(Commission.status == "CLAWBACK").label("clawback"),
        )
        .where(
            Commission.tenant_id == tenant_id,
            Commission.created_at >= start,
            Commission.created_at < end_exclusive,
        )
        .group_by(Commission.agent_id)
        .order_by(Commission.agent_id)
    )


@app.get("/commissions/report", response_model=List[CommissionReportEntry])
async def commission_report(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    tz: Optional[str] = Query(default=None, description="IANA zone for day boundaries (default UTC)"),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
    _auth: AuthContext = Depends(access.require_tier("manager")),
):
    zone = _resolve_tz(tz)
    today = datetime.now(zone or timezone.utc).date()
    if not start_date:
        start_date = date(today.year, today.month, 1)
    if not end_date:
        next_month = start_date + timedelta(days=32)
        end_date = date(next_month.year, next_month.month, 1) - timedelta(days=1)

    result = await db.execute(_commission_report_query(tenant_id, _day_start(start_date, zone), _next_day_start(end_date, zone)))
    return [
        CommissionReportEntry(
            agent_id=row.agent_id, total_amount_zar=Decimal(str(row.total_amount or 0)),
            deals_count=row.deals_count, pending=row.pending or 0,
            approved=row.approved or 0, paid=row.paid or 0, clawback=row.clawback or 0,
        )
        for row in result.all()
    ]


# ── Targets ──────────────────────────────────────────────────────────────

@app.post("/targets", response_model=TargetPerformanceEntry, status_code=status.HTTP_201_CREATED)
async def create_target(
    payload: TargetCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
    _auth: AuthContext = Depends(access.require_tier("admin")),
):
    if payload.period_end < payload.period_start:
        raise HTTPException(status_code=400, detail="period_end must be after period_start")

    target = Target(
        id=uuid.uuid4(), tenant_id=tenant_id, agent_id=payload.agent_id,
        team_id=payload.team_id, period_type=payload.period_type,
        period_start=payload.period_start, period_end=payload.period_end,
        target_value_zar=payload.target_value_zar,
    )
    db.add(target)
    await db.flush()

    # Production response shape: performance entry with zero actuals.
    return TargetPerformanceEntry(
        target_id=target.id, agent_id=payload.agent_id, team_id=payload.team_id,
        period_start=payload.period_start, period_end=payload.period_end,
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
    db: AsyncSession = Depends(get_db),
):
    q = select(Target).where(Target.tenant_id == tenant_id)
    if agent_id:
        q = q.where(Target.agent_id == agent_id)
    if team_id:
        q = q.where(Target.team_id == team_id)
    if period_start:
        q = q.where(Target.period_start >= period_start)
    if period_end:
        q = q.where(Target.period_end <= period_end)
    q = q.order_by(Target.period_start.desc())

    targets = (await db.execute(q)).scalars().all()

    results: List[TargetPerformanceEntry] = []
    for target in targets:
        total_result = await db.execute(
            select(func.coalesce(func.sum(Deal.value_zar), 0)).where(
                Deal.tenant_id == tenant_id,
                Deal.status == "WON",
                Deal.closed_at >= _day_start(target.period_start),
                Deal.closed_at < _next_day_start(target.period_end),
                *([Deal.agent_id == target.agent_id] if target.agent_id else []),
            )
        )
        actual_value = Decimal(str(total_result.scalar() or 0))
        target_value = Decimal(str(target.target_value_zar or 0))
        results.append(TargetPerformanceEntry(
            target_id=target.id, agent_id=target.agent_id, team_id=target.team_id,
            period_start=target.period_start, period_end=target.period_end,
            target_value_zar=target_value, actual_value_zar=actual_value,
            variance_zar=(actual_value - target_value).quantize(Decimal("0.01")),
        ))
    return results


# ── Leads (SPEC-lead-lifecycle.md) ────────────────────────────────────────

def _stage_http_error(exc: StageChangeError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=str(exc))


async def _get_lead(db: AsyncSession, tenant_id: uuid.UUID, lead_id: uuid.UUID) -> Lead:
    lead = await db.get(Lead, lead_id)
    if not lead or lead.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead


async def _change_stage(
    db: AsyncSession, tenant_id: uuid.UUID, lead: Lead, ctx: Optional[AuthContext], **kw: Any,
) -> tuple[Lead, Optional[Deal]]:
    await _ensure_default_pipeline(db, tenant_id)
    try:
        return await lead_service.apply_stage_change(
            db, lead, close_won=_close_won, close_lost=_close_lost, actor=_actor(ctx), **kw)
    except StageChangeError as exc:
        raise _stage_http_error(exc) from exc


def _source_label(source: Optional[str]) -> str:
    return (source or "manual entry").replace("_", " ").title()


CHANNEL_LABELS: Dict[str, str] = {
    "MARKETING": "Marketing Campaigns",
    "INBOUND_EMAIL": "Inbound Email",
    "CALL_CENTER_INBOUND": "Call Center Inbound",
    "CALL_CENTER_OUTBOUND": "Call Center Outbound",
    "PORTAL_WEBSITE": "Portal & Website",
    "FIELD_SALES": "Field Sales Team",
    "WALK_IN": "Walk-in Customers",
    "REFERRAL": "Partner Referral",
    "COMPANY_SEARCH": "Company Search",
    "TENDER": "Tenders & RFQs",
    "OTHER": "Direct / Other",
}


@app.get("/leads", response_model=List[LeadResponse])
async def list_leads(
    status: Optional[str] = None,
    agent_id: Optional[uuid.UUID] = None,
    source: Optional[str] = None,
    channel: Optional[str] = None,
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
    if channel:
        norm_ch = normalize_channel(channel)
        q = q.where((Lead.source_channel == norm_ch) | (Lead.source == channel))
    if min_interest:
        q = q.where(Lead.interest_level >= min_interest)
    q = q.order_by(Lead.created_at.desc()).limit(limit)
    leads = list((await db.execute(q)).scalars().all())
    ids = [lead.id for lead in leads]
    deals = await lead_service.deals_by_lead(db, ids)
    tasks = await lead_service.open_task_counts(db, ids)
    return [
        LeadResponse(**lead_service.lead_dict(lead, *deals.get(lead.id, (None, None)), tasks.get(lead.id, 0)))
        for lead in leads
    ]


@dataclass
class FunnelLead:
    """What the funnel needs to know about one lead (no ORM objects, so it is testable)."""
    lead_status: Optional[str]
    source_channel: Optional[str] = None
    source: Optional[str] = None
    notes: Optional[str] = None
    has_deal: bool = False
    deal_status: Optional[str] = None
    deal_stage: Optional[str] = None
    deal_value: Decimal = Decimal("0")


ZERO = Decimal("0.00")


def _new_channel_bucket(ch: str) -> Dict[str, Any]:
    return {
        "channel": ch,
        "channel_label": CHANNEL_LABELS.get(ch, ch.replace("_", " ").title()),
        "total_leads": 0,
        "stage_counts": {s: 0 for s in STANDARD_FUNNEL_STAGES},
        "stage_values_zar": {s: ZERO for s in STANDARD_FUNNEL_STAGES},
        "won_count": 0, "lost_count": 0,
        "open_value_zar": ZERO, "won_value_zar": ZERO, "lost_value_zar": ZERO,
    }


def compute_funnel(leads: List[FunnelLead]) -> Dict[str, Any]:
    """Bucket every lead exactly once (lead_stages.funnel_bucket), per channel and overall.

    Invariant, asserted in the tests: the overall counts and each channel's stage
    counts add up to the number of leads; a stage that is not in the standard list
    (a tenant-defined board stage) gets its own bucket instead of being dropped."""
    channels = {ch: _new_channel_bucket(ch) for ch in SALES_CHANNELS}
    labels = {stage_key(s): s for s in STANDARD_FUNNEL_STAGES}  # one label per case-insensitive stage
    overall_counts: Dict[str, int] = {s: 0 for s in STANDARD_FUNNEL_STAGES}
    overall_values: Dict[str, Decimal] = {s: ZERO for s in STANDARD_FUNNEL_STAGES}

    for lead in leads:
        ch = normalize_channel(lead.source_channel, lead.source, lead.notes)
        cd = channels[ch]
        bucket, is_won, is_lost = funnel_bucket(lead.lead_status, lead.deal_status, lead.deal_stage, lead.has_deal)
        bucket = labels.setdefault(stage_key(bucket), bucket)
        value = Decimal(str(lead.deal_value or 0)) if lead.has_deal else ZERO

        for counts, values in ((cd["stage_counts"], cd["stage_values_zar"]), (overall_counts, overall_values)):
            counts[bucket] = counts.get(bucket, 0) + 1
            values[bucket] = values.get(bucket, ZERO) + value
        cd["total_leads"] += 1
        if is_won:
            cd["won_count"] += 1
            cd["won_value_zar"] += value
        elif is_lost:
            cd["lost_count"] += 1
            cd["lost_value_zar"] += value
        else:
            cd["open_value_zar"] += value
    return {"channels": channels, "overall_counts": overall_counts, "overall_values": overall_values}


@app.get("/leads/funnel", response_model=LeadFunnelResponse)
async def get_lead_funnel(
    days: Optional[int] = Query(None, ge=1, le=730),
    channel: Optional[str] = None,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    """Funnel view of leads by channel across lead status and deal pipeline stages.

    Every lead is counted once, so the stage counts always add up to total_leads.
    total_pipeline_value_zar is the OPEN pipeline only (won and lost excluded);
    open_value_zar / won_value_zar / lost_value_zar split the value by outcome.
    All channels are returned (the web slices the list for display)."""
    q = select(Lead.id, Lead.status, Lead.source, Lead.source_channel, Lead.notes).where(Lead.tenant_id == tenant_id)
    if days:
        since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
        q = q.where(Lead.created_at >= since)
    if channel:
        norm_filter = normalize_channel(channel)
        q = q.where((Lead.source_channel == norm_filter) | (Lead.source == channel))

    rows = (await db.execute(q)).all()
    deals = await lead_service.deals_by_lead(db, [r.id for r in rows])  # chunked: no 32k-parameter IN
    funnel_leads = []
    for r in rows:
        deal, deal_stage = deals.get(r.id, (None, None))
        funnel_leads.append(FunnelLead(
            lead_status=r.status, source_channel=r.source_channel, source=r.source, notes=r.notes,
            has_deal=deal is not None, deal_status=deal.status if deal else None, deal_stage=deal_stage,
            deal_value=Decimal(str(deal.value_zar or 0)) if deal else ZERO,
        ))
    data = compute_funnel(funnel_leads)
    channel_data, overall_counts, overall_values = data["channels"], data["overall_counts"], data["overall_values"]

    total_leads_all = len(funnel_leads)
    total_won_all = sum(cd["won_count"] for cd in channel_data.values())
    total_lost_all = sum(cd["lost_count"] for cd in channel_data.values())
    total_open_val = sum((cd["open_value_zar"] for cd in channel_data.values()), ZERO)
    total_won_val = sum((cd["won_value_zar"] for cd in channel_data.values()), ZERO)
    total_lost_val = sum((cd["lost_value_zar"] for cd in channel_data.values()), ZERO)

    def pct(part: int, whole: int) -> float:
        return round(max(0.0, min(100.0, part / whole * 100.0)), 1) if whole > 0 else 0.0

    channels_res: List[ChannelFunnelItem] = []
    for ch in SALES_CHANNELS:
        cd = channel_data[ch]
        channels_res.append(ChannelFunnelItem(
            channel=cd["channel"], channel_label=cd["channel_label"], total_leads=cd["total_leads"],
            stage_counts=cd["stage_counts"], stage_values_zar=cd["stage_values_zar"],
            won_count=cd["won_count"], lost_count=cd["lost_count"],
            conversion_rate=pct(cd["won_count"], cd["total_leads"]),
            total_pipeline_value_zar=cd["open_value_zar"].quantize(Decimal("0.01")),
            open_value_zar=cd["open_value_zar"].quantize(Decimal("0.01")),
            won_value_zar=cd["won_value_zar"].quantize(Decimal("0.01")),
            lost_value_zar=cd["lost_value_zar"].quantize(Decimal("0.01")),
        ))
    # Sort so channels with active leads come first
    channels_res.sort(key=lambda c: (c.total_leads, c.total_pipeline_value_zar), reverse=True)

    cohorts = cohort_conversion(overall_counts)
    extra_stages = sorted((k for k in overall_counts if k not in STANDARD_FUNNEL_STAGES),
                          key=lambda k: (-overall_counts[k], k))
    overall_funnel = []
    for stage in [*STANDARD_FUNNEL_STAGES, *extra_stages]:
        cohort = cohorts.get(stage)
        overall_funnel.append(FunnelStageItem(
            stage=stage, count=overall_counts.get(stage, 0),
            pct_of_total=pct(overall_counts.get(stage, 0), total_leads_all),
            value_zar=overall_values.get(stage, ZERO).quantize(Decimal("0.01")),
            cohort_count=int(cohort["cohort"]) if cohort else None,
            conversion_from_previous_pct=cohort["conversion_from_previous_pct"] if cohort else None,
        ))

    top_channel = channels_res[0].channel_label if channels_res and channels_res[0].total_leads > 0 else "None"
    return LeadFunnelResponse(
        channels=channels_res,
        overall_funnel=overall_funnel,
        totals={
            "total_leads": total_leads_all,
            "stage_total": sum(overall_counts.values()),
            "won_leads": total_won_all,
            "lost_leads": total_lost_all,
            "open_leads": total_leads_all - total_won_all - total_lost_all,
            "conversion_rate": pct(total_won_all, total_leads_all),
            "total_pipeline_value_zar": float(total_open_val),  # open only
            "open_value_zar": float(total_open_val),
            "won_value_zar": float(total_won_val),
            "lost_value_zar": float(total_lost_val),
            "top_performing_channel": top_channel,
        },
        period_days=days,
    )


@app.post("/leads", response_model=LeadResponse, status_code=201)
async def create_lead(
    payload: LeadCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    source_channel = normalize_channel(payload.source_channel, payload.source, payload.notes)
    lead = Lead(
        id=uuid.uuid4(), tenant_id=tenant_id,
        first_name=payload.first_name, last_name=payload.last_name,
        email=payload.email, phone=payload.phone, address=payload.address,
        source=payload.source, source_channel=source_channel, interest_level=payload.interest_level,
        notes=payload.notes, agent_id=payload.agent_id, owner_id=payload.owner_id, owner_name=payload.owner_name,
        priority=payload.priority, ref_no=await lead_service.next_ref_no(db, tenant_id),
        status="NEW", created_at=now, updated_at=now,
    )
    db.add(lead)
    await db.flush()
    await lead_service.record_activity(
        db, tenant_id, lead.id, "created", f"Lead created from {_source_label(payload.source)}",
        {"source": payload.source, "source_channel": source_channel}, _actor(ctx))
    await lead_service.publish_lead_event(db, lead, "sales.lead.created")
    if payload.pipeline:
        await _change_stage(db, tenant_id, lead, ctx, target_stage=payload.pipeline.stage_name,
                            value_zar=payload.pipeline.value_zar, deal_name=payload.pipeline.deal_name)
    return LeadResponse(**await lead_service.lead_with_deal(db, lead))


@app.get("/leads/{lead_id}", response_model=LeadDetailResponse)
async def get_lead(
    lead_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    lead = await _get_lead(db, tenant_id, lead_id)
    activities = (await db.execute(
        select(LeadActivity).where(LeadActivity.lead_id == lead.id)
        .order_by(LeadActivity.created_at.desc()).limit(200)
    )).scalars().all()
    tasks = (await db.execute(
        select(LeadTask).where(LeadTask.lead_id == lead.id)
        .order_by(LeadTask.status, LeadTask.due_at.asc().nulls_last(), LeadTask.created_at.desc())
    )).scalars().all()
    return LeadDetailResponse(
        **await lead_service.lead_with_deal(db, lead),
        activities=[LeadActivityResponse(
            id=a.id, kind=a.kind, summary=a.summary, details=a.details or {},
            actor_id=a.actor_id, actor_name=a.actor_name, created_at=a.created_at) for a in activities],
        tasks=[_task_response(t) for t in tasks],
    )


def _task_response(t: LeadTask) -> LeadTaskResponse:
    return LeadTaskResponse(
        id=t.id, lead_id=t.lead_id, title=t.title, kind=t.kind, due_at=t.due_at,
        assignee_id=t.assignee_id, assignee_name=t.assignee_name, status=t.status,
        created_at=t.created_at, completed_at=t.completed_at)


@app.put("/leads/{lead_id}", response_model=LeadResponse)
async def update_lead(
    lead_id: uuid.UUID,
    payload: LeadUpdate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
):
    lead = await _get_lead(db, tenant_id, lead_id)
    update_data = payload.model_dump(exclude_unset=True)
    new_status = update_data.pop("status", None)
    if "source_channel" in update_data or "source" in update_data:
        lead.source_channel = normalize_channel(
            update_data.get("source_channel"),
            update_data.get("source", lead.source),
            update_data.get("notes", lead.notes),
        )
    changed = [k for k, v in update_data.items() if getattr(lead, k) != v]
    for key, value in update_data.items():
        setattr(lead, key, value)
    lead.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    await db.flush()
    if changed:
        await lead_service.record_activity(
            db, tenant_id, lead.id, "updated", "Updated " + ", ".join(k.replace("_", " ") for k in changed),
            {"fields": changed}, _actor(ctx))
    # A status goes through the one stage model (legacy values map onto it).
    if new_status and new_status.upper() != (lead.status or ""):
        await _change_stage(db, tenant_id, lead, ctx, target_status=new_status)
    return LeadResponse(**await lead_service.lead_with_deal(db, lead))


@app.post("/leads/{lead_id}/stage", response_model=LeadResponse)
async def change_lead_stage(
    lead_id: uuid.UUID,
    payload: LeadStageChange,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
):
    """Move a lead in the lead phase (status) or on the pipeline board (stage_name).
    Same rules as the board, so the lead table and the board never disagree."""
    lead = await _get_lead(db, tenant_id, lead_id)
    await _change_stage(db, tenant_id, lead, ctx, target_status=payload.status,
                        target_stage=payload.stage_name, value_zar=payload.value_zar,
                        deal_name=payload.deal_name, reason=payload.reason)
    return LeadResponse(**await lead_service.lead_with_deal(db, lead))


@app.post("/leads/{lead_id}/convert", response_model=dict)
async def convert_lead(
    lead_id: uuid.UUID,
    payload: LeadConvert,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
):
    """Put the lead on the pipeline board (field-sales app contract unchanged).
    Converting a lead that already has a deal returns that deal, never a second one."""
    lead = await _get_lead(db, tenant_id, lead_id)
    if payload.agent_id:
        lead.agent_id = payload.agent_id
    existing = (await lead_service.deals_by_lead(db, [lead.id])).get(lead.id)
    if existing:
        deal = existing[0]
    else:
        await _ensure_default_pipeline(db, tenant_id)
        names = await lead_service.stage_names(db, tenant_id)
        stage = payload.stage_name or (names[0] if names else "Prospecting")
        _, deal = await _change_stage(db, tenant_id, lead, ctx, target_stage=stage,
                                      value_zar=payload.value_zar, deal_name=payload.name)
    return {"deal_id": str(deal.id), "contact_id": str(lead.contact_id), "message": "Lead converted"}


@app.get("/owners", response_model=List[OwnerResponse])
async def list_owners(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    """People a lead can be assigned to: active HR employees of the tenant.
    Reads the shared `employees` table (HR owns it); empty when HR is not installed."""
    try:
        async with db.begin_nested():
            rows = (await db.execute(text("""
                SELECT id, full_name, department, job_title, email FROM employees
                 WHERE tenant_id = :t AND coalesce(upper(status), 'ACTIVE') = 'ACTIVE'
                 ORDER BY full_name
            """), {"t": str(tenant_id)})).all()
    except Exception:  # noqa: BLE001 - a missing HR table locally is not an error
        return []
    return [OwnerResponse(id=r[0], name=r[1], department=r[2], job_title=r[3], email=r[4]) for r in rows]


# ── Lead actions (SPEC-lead-actions.md) ─────────────────────────────────────
# Each action writes the lead timeline in the request's transaction. Anything
# that talks to another service is published on the event bus and done by the
# sales consumer (services/sales/lead_actions.py), so it never blocks the
# request and is retried if the other side is down.

def _ref(lead: Lead) -> str:
    return lead_service.format_reference(lead.ref_no) or "Lead"


async def _touch(db: AsyncSession, lead: Lead) -> None:
    lead.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    await db.flush()


@app.post("/leads/{lead_id}/assign", response_model=LeadResponse)
async def assign_lead(lead_id: uuid.UUID, payload: LeadAssign,
                      tenant_id: uuid.UUID = Depends(get_current_tenant_id),
                      db: AsyncSession = Depends(get_db), ctx: AuthContext = Depends(get_auth_context)):
    lead = await _get_lead(db, tenant_id, lead_id)
    lead.owner_id = payload.owner_id
    lead.owner_name = payload.owner_name
    await _touch(db, lead)
    who = payload.owner_name or "nobody"
    await lead_service.record_activity(db, tenant_id, lead.id, "assigned", f"Assigned to {who}",
                                       {"owner_id": str(payload.owner_id) if payload.owner_id else None}, _actor(ctx))
    if payload.owner_name:
        await notify(db, tenant_id, f"{_ref(lead)} assigned to {payload.owner_name}",
                     body=lead_service.full_name(lead), category="sales", source="sales",
                     subject=("lead", lead.id))
    await lead_service.publish_lead_event(db, lead, "sales.lead.assigned")
    return LeadResponse(**await lead_service.lead_with_deal(db, lead))


AI_DRAFT_ACTOR = "DomeBot (AI)"
AI_DRAFT_UNVERIFIED_ACTOR = "AI draft (unverified source)"


@dataclass(frozen=True)
class NoteKind:
    kind: str                       # stored lead_activities.kind
    actor_name: Optional[str] = None  # None = the signed-in user
    unverified: bool = False


def resolve_note_kind(requested: str, automation: bool) -> NoteKind:
    """A note's kind and attribution. "DomeBot (AI)" and the AI-draft notification belong
    to automations only (role automation/system/service/orchestrator, or an X-Automation-Run
    header). Anyone else asking for ai_draft gets a note that says its source is unverified
    (SALES_AI_DRAFT_STRICT=true downgrades it to a plain note instead)."""
    if requested == "call":
        return NoteKind("call_logged")
    if requested != "ai_draft":
        return NoteKind("note")
    if automation:
        return NoteKind("ai_draft", AI_DRAFT_ACTOR)
    if os.getenv("SALES_AI_DRAFT_STRICT", "false").strip().lower() in {"1", "true", "yes", "on"}:
        return NoteKind("note")
    return NoteKind("ai_draft", AI_DRAFT_UNVERIFIED_ACTOR, unverified=True)


@app.post("/leads/{lead_id}/notes", response_model=LeadActivityResponse, status_code=201)
async def add_lead_note(lead_id: uuid.UUID, payload: LeadNote, request: Request,
                        tenant_id: uuid.UUID = Depends(get_current_tenant_id),
                        db: AsyncSession = Depends(get_db), ctx: AuthContext = Depends(get_auth_context)):
    lead = await _get_lead(db, tenant_id, lead_id)
    await _touch(db, lead)
    kind = resolve_note_kind(payload.kind, access.is_automation_caller(ctx, request.headers))
    first_line = payload.body.strip().splitlines()[0][:240]
    summary = {"call_logged": f"Call: {first_line}",
               "ai_draft": "AI draft ready — review and send"}.get(kind.kind, first_line)
    actor = Actor(id=ctx.user_id, name=kind.actor_name) if kind.actor_name else _actor(ctx)
    a = await lead_service.record_activity(db, tenant_id, lead.id, kind.kind, summary,
                                           {"body": payload.body, **({"unverified_source": True} if kind.unverified else {})},
                                           actor)
    kind = kind.kind
    if kind == "ai_draft" and a.actor_name == AI_DRAFT_ACTOR:
        await notify(db, tenant_id, f"AI draft ready for {_ref(lead)} {lead_service.full_name(lead)}",
                     body=first_line, category="automation", source="sales", subject=("lead", lead.id))
    await db.flush()
    return LeadActivityResponse(id=a.id, kind=a.kind, summary=a.summary, details=a.details,
                                actor_id=a.actor_id, actor_name=a.actor_name, created_at=a.created_at)


LEAD_EMAIL_RATE_PER_MIN = int(os.getenv("LEAD_EMAIL_RATE_PER_MIN", "20"))
_lead_email_limiter = RateLimiter(max_requests=LEAD_EMAIL_RATE_PER_MIN, window_seconds=60.0)


def check_lead_email_rate(tenant_id: uuid.UUID) -> None:
    """Per-tenant cap on queued lead emails (LEAD_EMAIL_RATE_PER_MIN, default 20): 429 beyond it."""
    _lead_email_limiter.check_key(f"lead_email:{tenant_id}")


@app.post("/leads/{lead_id}/email", response_model=LeadActivityResponse, status_code=202)
async def email_lead(lead_id: uuid.UUID, payload: LeadEmail,
                     tenant_id: uuid.UUID = Depends(get_current_tenant_id),
                     db: AsyncSession = Depends(get_db), ctx: AuthContext = Depends(get_auth_context),
                     _role: AuthContext = Depends(access.require_tier("agent")),
                     idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key", max_length=100)):
    """Queue an email to the lead. Sent by the sales consumer via AgentMail (never to an
    opted-out address: the consumer records "email suppressed (opt-out)" instead); the
    timeline shows queued -> sent (or failed after retries). Needs a sales role and is
    rate limited per tenant. Repeat a request with the same Idempotency-Key header
    (for example after a timeout) and it is queued once."""
    lead = await _get_lead(db, tenant_id, lead_id)
    if not lead.email:
        raise HTTPException(status_code=400, detail="This lead has no email address")
    check_lead_email_rate(tenant_id)
    await _touch(db, lead)
    a = await lead_service.record_activity(db, tenant_id, lead.id, "email_queued", f"Email queued: {payload.subject}",
                                           {"to": lead.email, "subject": payload.subject, "body": payload.body},
                                           _actor(ctx),
                                           idempotency_key=f"queue:{idempotency_key}" if idempotency_key else None)
    if a in db.new:  # an existing row means this is a retry of a request that already queued the email
        await lead_service.publish_lead_event(db, lead, "sales.lead.email_requested",
                                              to=lead.email, subject=payload.subject, body=payload.body)
    await db.flush()
    return LeadActivityResponse(id=a.id, kind=a.kind, summary=a.summary, details=a.details,
                                actor_id=a.actor_id, actor_name=a.actor_name, created_at=a.created_at)


@app.get("/leads/{lead_id}/tasks", response_model=List[LeadTaskResponse])
async def list_lead_tasks(lead_id: uuid.UUID, tenant_id: uuid.UUID = Depends(get_current_tenant_id),
                          db: AsyncSession = Depends(get_db)):
    lead = await _get_lead(db, tenant_id, lead_id)
    rows = (await db.execute(
        select(LeadTask).where(LeadTask.lead_id == lead.id)
        .order_by(LeadTask.status, LeadTask.due_at.asc().nulls_last(), LeadTask.created_at.desc())
    )).scalars().all()
    return [_task_response(t) for t in rows]


async def _create_task(db: AsyncSession, tenant_id: uuid.UUID, lead: Lead, *, title: str, kind: str,
                       due_at: Optional[datetime], assignee_id: Optional[uuid.UUID],
                       assignee_name: Optional[str], ctx: Optional[AuthContext]) -> LeadTask:
    task = LeadTask(id=uuid.uuid4(), tenant_id=tenant_id, lead_id=lead.id, title=title, kind=kind,
                    due_at=due_at, assignee_id=assignee_id, assignee_name=assignee_name, status="open",
                    created_by=ctx.user_id if ctx else None, created_at=datetime.now(timezone.utc))
    db.add(task)
    await _touch(db, lead)
    when = f" (due {due_at:%d %b %Y %H:%M})" if due_at else ""
    await lead_service.record_activity(db, tenant_id, lead.id, "task_created",
                                       f"Task: {title}{when}" + (f" · {assignee_name}" if assignee_name else ""),
                                       {"task_id": str(task.id), "kind": kind}, _actor(ctx))
    return task


@app.post("/leads/{lead_id}/tasks", response_model=LeadTaskResponse, status_code=201)
async def create_lead_task(lead_id: uuid.UUID, payload: LeadTaskCreate,
                           tenant_id: uuid.UUID = Depends(get_current_tenant_id),
                           db: AsyncSession = Depends(get_db), ctx: AuthContext = Depends(get_auth_context)):
    lead = await _get_lead(db, tenant_id, lead_id)
    task = await _create_task(db, tenant_id, lead, title=payload.title, kind=payload.kind, due_at=payload.due_at,
                              assignee_id=payload.assignee_id, assignee_name=payload.assignee_name, ctx=ctx)
    if payload.assignee_name:
        await notify(db, tenant_id, f"New task for {payload.assignee_name}: {payload.title}",
                     body=f"{_ref(lead)} · {lead_service.full_name(lead)}", category="sales", source="sales",
                     subject=("lead", lead.id))
    await db.flush()
    return _task_response(task)


@app.patch("/lead-tasks/{task_id}", response_model=LeadTaskResponse)
async def update_lead_task(task_id: uuid.UUID, payload: LeadTaskUpdate,
                           tenant_id: uuid.UUID = Depends(get_current_tenant_id),
                           db: AsyncSession = Depends(get_db), ctx: AuthContext = Depends(get_auth_context)):
    task = await db.get(LeadTask, task_id)
    if not task or task.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.status != payload.status:
        task.status = payload.status
        task.completed_at = datetime.now(timezone.utc) if payload.status == "done" else None
        lead = await db.get(Lead, task.lead_id)
        if lead is not None:
            await _touch(db, lead)
        await lead_service.record_activity(
            db, tenant_id, task.lead_id, "task_done" if payload.status == "done" else "task_reopened",
            f"{'Done' if payload.status == 'done' else 'Reopened'}: {task.title}", {"task_id": str(task.id)},
            _actor(ctx))
    await db.flush()
    return _task_response(task)


@app.post("/leads/{lead_id}/escalate", response_model=LeadResponse)
async def escalate_lead(lead_id: uuid.UUID, payload: LeadEscalate,
                        tenant_id: uuid.UUID = Depends(get_current_tenant_id),
                        db: AsyncSession = Depends(get_db), ctx: AuthContext = Depends(get_auth_context)):
    lead = await _get_lead(db, tenant_id, lead_id)
    lead.priority = "urgent"
    lead.escalated_at = datetime.now(timezone.utc)
    await _touch(db, lead)
    await lead_service.record_activity(db, tenant_id, lead.id, "escalated", f"Escalated: {payload.reason[:250]}",
                                       {"reason": payload.reason}, _actor(ctx))
    await notify(db, tenant_id, f"Escalated: {_ref(lead)} {lead_service.full_name(lead)}", body=payload.reason,
                 category="sales", severity="critical", source="sales", subject=("lead", lead.id))
    await lead_service.publish_lead_event(db, lead, "sales.lead.escalated", reason=payload.reason)
    return LeadResponse(**await lead_service.lead_with_deal(db, lead))


@app.post("/leads/{lead_id}/outbound", response_model=LeadTaskResponse, status_code=201)
async def send_lead_to_outbound(lead_id: uuid.UUID, payload: LeadOutbound,
                                tenant_id: uuid.UUID = Depends(get_current_tenant_id),
                                db: AsyncSession = Depends(get_db), ctx: AuthContext = Depends(get_auth_context)):
    """Queue the lead for an outbound call: a call task in the Outbound queue, and
    sales.lead.outbound_requested for any orchestrator workflow (e.g. an AI voice agent)."""
    lead = await _get_lead(db, tenant_id, lead_id)
    if not lead.phone:
        raise HTTPException(status_code=400, detail="This lead has no phone number")
    task = await _create_task(db, tenant_id, lead, title=f"Call {lead_service.full_name(lead)} ({lead.phone})",
                              kind="call", due_at=datetime.now(timezone.utc), assignee_id=None,
                              assignee_name=lead_actions.OUTBOUND_QUEUE, ctx=ctx)
    await lead_service.record_activity(db, tenant_id, lead.id, "sent_to_outbound", "Sent to the outbound call queue",
                                       {"task_id": str(task.id), "notes": payload.notes}, _actor(ctx))
    await notify(db, tenant_id, f"{_ref(lead)} queued for an outbound call", body=payload.notes or lead.phone,
                 category="call_center", source="sales", subject=("lead", lead.id))
    await lead_service.publish_lead_event(db, lead, "sales.lead.outbound_requested", task_id=str(task.id),
                                          notes=payload.notes)
    await db.flush()
    return _task_response(task)


@app.post("/leads/{lead_id}/campaign", response_model=LeadActivityResponse, status_code=202)
async def send_lead_to_campaign(lead_id: uuid.UUID, payload: LeadCampaign,
                                tenant_id: uuid.UUID = Depends(get_current_tenant_id),
                                db: AsyncSession = Depends(get_db), ctx: AuthContext = Depends(get_auth_context)):
    """Add the lead to a Marketing campaign's audience. Returns at once; the sales
    consumer updates the "Sales leads · <campaign>" audience in Marketing."""
    lead = await _get_lead(db, tenant_id, lead_id)
    await _touch(db, lead)
    a = await lead_service.record_activity(db, tenant_id, lead.id, "campaign_requested",
                                           f"Sent to marketing campaign '{payload.campaign_name}'",
                                           {"campaign_id": payload.campaign_id,
                                            "campaign_name": payload.campaign_name}, _actor(ctx))
    await lead_service.publish_lead_event(db, lead, "sales.lead.campaign_requested",
                                          campaign_id=payload.campaign_id, campaign_name=payload.campaign_name)
    await db.flush()
    return LeadActivityResponse(id=a.id, kind=a.kind, summary=a.summary, details=a.details,
                                actor_id=a.actor_id, actor_name=a.actor_name, created_at=a.created_at)



# ── Automations (SPEC-lead-automations.md) ──────────────────────────────────

AUTOMATION_ACTOR = Actor(name="Automation")


def _event_label(event_type: str) -> str:
    return {
        "portal.cart.abandoned": "Abandoned basket",
        "portal.quote.requested": "Quote requested",
        "portal.registration.inactive": "Registration inactive",
    }.get(event_type, event_type)


@app.post("/automation/lead-events", response_model=AutomationLeadResponse)
async def automation_lead_event(
    payload: AutomationLeadEvent,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
):
    """Find or create the lead for a customer event and move it forward.
    Matches by email (by phone only when the event has no email). Never moves a lead backwards or reopens a
    closed one (lead_stages.is_forward_move). Idempotent per event_id."""
    c = payload.contact
    email = (c.email or "").strip().lower() or None
    phone = "".join((c.phone or "").split()) or None
    if not email and not phone:
        raise HTTPException(status_code=422, detail="The event contact needs an email or a phone number")

    lead: Optional[Lead] = None
    if email:
        lead = (await db.execute(select(Lead).where(Lead.tenant_id == tenant_id, func.lower(Lead.email) == email)
                                 .order_by(Lead.created_at.desc()).limit(1))).scalar_one_or_none()
    # Phone only when the event has no email: a different email with a shared
    # phone (switchboard, family, reception) is a different person, and merging
    # two people is worse than a duplicate lead.
    if lead is None and phone and not email:
        lead = (await db.execute(select(Lead).where(Lead.tenant_id == tenant_id,
                                                    func.replace(Lead.phone, " ", "") == phone)
                                 .order_by(Lead.created_at.desc()).limit(1))).scalar_one_or_none()

    if lead is not None and payload.event_id:
        seen = (await db.execute(select(LeadActivity.id).where(
            LeadActivity.lead_id == lead.id, LeadActivity.kind == "automation",
            LeadActivity.details["event_id"].astext == payload.event_id))).first()
        if seen:
            return AutomationLeadResponse(**await lead_service.lead_with_deal(db, lead), duplicate_event=True)

    created = False
    label = _event_label(payload.event_type)
    if lead is None:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        first = (c.first_name or c.company or "Portal").strip()
        last = (c.last_name or ("" if c.first_name or c.company else "customer")).strip()
        lead = Lead(
            id=uuid.uuid4(), tenant_id=tenant_id, first_name=first, last_name=last,
            email=c.email, phone=c.phone, address=c.address, source=payload.source,
            interest_level=payload.interest_level, notes=payload.note,
            ref_no=await lead_service.next_ref_no(db, tenant_id), status="NEW",
            created_at=now, updated_at=now,
        )
        db.add(lead)
        await db.flush()
        created = True
        await lead_service.record_activity(db, tenant_id, lead.id, "created",
                                           f"Lead created by automation: {label}",
                                           {"event_type": payload.event_type}, AUTOMATION_ACTOR)
        await lead_service.publish_lead_event(db, lead, "sales.lead.created", via="automation")

    stage_applied = False
    if payload.target_status or payload.target_stage:
        await _ensure_default_pipeline(db, tenant_id)
        deal, deal_stage = (await lead_service.deals_by_lead(db, [lead.id])).get(lead.id, (None, None))
        names = await lead_service.stage_names(db, tenant_id)
        if is_forward_move(current_status=lead.status, deal_stage=deal_stage if deal else None,
                           stage_names=names, target_status=payload.target_status,
                           target_stage=payload.target_stage):
            try:
                await lead_service.apply_stage_change(
                    db, lead, close_won=_close_won, close_lost=_close_lost, actor=AUTOMATION_ACTOR,
                    target_status=payload.target_status, target_stage=payload.target_stage,
                    value_zar=payload.value_zar, deal_name=f"{lead_service.full_name(lead)} - {label}")
                stage_applied = True
            except StageChangeError as exc:
                raise _stage_http_error(exc) from exc

    lead.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    await lead_service.record_activity(
        db, tenant_id, lead.id, "automation",
        f"{label}" + (f": {payload.note}" if payload.note else "")
        + ("" if stage_applied or not (payload.target_status or payload.target_stage) else " (stage unchanged: already further along or closed)"),
        {"event_type": payload.event_type, "event_id": payload.event_id, "stage_applied": stage_applied},
        AUTOMATION_ACTOR)
    await db.flush()
    return AutomationLeadResponse(**await lead_service.lead_with_deal(db, lead), created=created,
                                  stage_applied=stage_applied)


# ── Contacts ─────────────────────────────────────────────────────────────

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
    return [
        ContactResponse(
            id=c.id, tenant_id=c.tenant_id, first_name=c.first_name,
            last_name=c.last_name, email=c.email, phone=c.phone,
            physical_address=c.physical_address, city=c.city,
            province=c.province, rica_verified=c.rica_verified,
            status=c.status, lifecycle_stage=c.lifecycle_stage,
            nps_score=c.nps_score, created_at=c.created_at, updated_at=c.updated_at,
        ) for c in result.scalars().all()
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
    now = datetime.now(timezone.utc).replace(tzinfo=None)
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
    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(contact, key, value)
    contact.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    await db.flush()
    return ContactResponse(
        id=contact.id, tenant_id=contact.tenant_id, first_name=contact.first_name,
        last_name=contact.last_name, email=contact.email, phone=contact.phone,
        physical_address=contact.physical_address, city=contact.city,
        province=contact.province, rica_verified=contact.rica_verified,
        status=contact.status, lifecycle_stage=contact.lifecycle_stage,
        nps_score=contact.nps_score, created_at=contact.created_at, updated_at=contact.updated_at,
    )


# ── Customer 360 ─────────────────────────────────────────────────────────

@app.get("/contacts/{contact_id}/360", response_model=Customer360Response)
async def get_customer_360(
    contact_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    contact = await db.get(Contact, contact_id)
    if not contact or contact.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Contact not found")

    deals_result = await db.execute(
        select(Deal, DealStage.name.label("stage_name"))
        .outerjoin(DealStage, DealStage.id == Deal.stage_id)
        .where(Deal.tenant_id == tenant_id, Deal.contact_id == contact_id)
        .order_by(Deal.created_at.desc())
    )
    deals: List[DealResponse] = []
    total_revenue = Decimal("0")
    open_deals_value = Decimal("0")
    for row in deals_result.all():
        d = row.Deal
        deals.append(_deal_to_response(d, row.stage_name))
        if d.status == "WON":
            total_revenue += d.value_zar or Decimal("0")
        elif d.status == "OPEN":
            open_deals_value += d.value_zar or Decimal("0")

    quotes_result = await db.execute(
        select(Quote).where(Quote.tenant_id == tenant_id, Quote.customer_id == contact_id)
        .order_by(Quote.created_at.desc()).limit(20)
    )
    quotes = [
        QuoteResponse(
            id=q.id, tenant_id=q.tenant_id, deal_id=q.deal_id,
            customer_id=q.customer_id, lead_id=q.lead_id, agent_id=q.agent_id,
            package_id=q.package_id, items=deserialize_items(q.items),
            total_monthly=q.total_monthly, total_once_off=q.total_once_off,
            term_months=q.term_months, valid_until=q.valid_until,
            status=q.status, terms=q.terms, created_at=q.created_at,
            sent_at=q.sent_at, accepted_at=q.accepted_at,
        )
        for q in quotes_result.scalars().all()
    ]

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


# ── Entrypoint ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8002"))
    host = os.getenv("UVICORN_HOST", "0.0.0.0")
    uvicorn.run(app, host=host, port=port)
