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
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

import httpx
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import Integer, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.common.auth import AuthContext, get_auth_context, get_current_tenant_id
from services.common.db import run_with_db_retry
from services.common.entitlements import EntitlementGuard
from services.common.middleware import configure_production
from services.sales.database import get_db, init_tables
from services.sales.models import (
    Commission,
    CommissionTier,
    Contact,
    Deal,
    DealStage,
    Lead,
    Pipeline,
    Quote,
    Target,
)

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
    contact_id: Optional[uuid.UUID] = None
    agent_id: Optional[uuid.UUID] = None
    first_name: str
    last_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    source: str
    interest_level: int
    status: str
    notes: Optional[str] = None
    converted_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


class LeadConvert(BaseModel):
    name: Optional[str] = Field(None, description="Deal name (defaults to lead name)")
    value_zar: Decimal = Field(default=Decimal("0"), ge=0)
    agent_id: Optional[uuid.UUID] = None


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


async def _commission_rate(db: AsyncSession, tenant_id: uuid.UUID, agent_id: uuid.UUID) -> Decimal:
    """Tenant-configured tier wins; default 5/7/10% thresholds otherwise."""
    now = datetime.now(timezone.utc)
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
    tier_rate = tier_result.scalar_one_or_none()
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
    """Return an existing contact id, else insert one (satisfies FK)."""
    existing = await db.get(Contact, contact_id)
    if existing and existing.tenant_id == tenant_id:
        return contact_id
    hints = _parse_notes_contact(notes)
    db.add(Contact(
        id=contact_id, tenant_id=tenant_id,
        first_name=hints["first_name"] or "Walk-in",
        last_name=hints["last_name"] or "Customer",
        email=hints["email"], phone=hints["phone"],
        status="ACTIVE", lifecycle_stage="PROSPECT",
        created_at=now, updated_at=now,
    ))
    await db.flush()
    return contact_id


def _deal_to_response(deal: Deal, stage_name: Optional[str]) -> DealResponse:
    return DealResponse(
        id=deal.id, tenant_id=deal.tenant_id, name=deal.name,
        customer_id=deal.contact_id,
        lead_id=deal.lead_id, agent_id=deal.agent_id, stage_id=deal.stage_id,
        stage_name=stage_name, package_id=deal.package_id,
        value_zar=deal.value_zar, status=deal.status, close_date=deal.close_date,
        closed_at=deal.closed_at, close_reason=deal.close_reason, notes=deal.notes,
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
    return [PipelineStage(id=s.id, name=s.name, probability=s.probability, sort_order=s.sort_order)
            for s in stages]


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
    return PipelineStage(id=stage.id, name=stage.name, probability=stage.probability,
                         sort_order=stage.sort_order)


# ── Deals ────────────────────────────────────────────────────────────────

@app.post("/deals", response_model=DealResponse, status_code=201)
async def create_deal(
    payload: DealCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    stage_id = await _resolve_stage_id(db, tenant_id, payload.stage_id, payload.stage_name)
    deal_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

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
    return [
        _deal_to_response(row.Deal, row.stage_name)
        for row in result.all()
    ]


@app.get("/deals/{deal_id}", response_model=DealResponse)
async def get_deal(
    deal_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Deal, DealStage.name.label("stage_name"))
        .outerjoin(DealStage, Deal.stage_id == DealStage.id)
        .where(Deal.id == deal_id, Deal.tenant_id == tenant_id)
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="Deal not found")
    return _deal_to_response(row.Deal, row.stage_name)


@app.delete("/deals/{deal_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_deal(
    deal_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    deal = await db.get(Deal, deal_id)
    if not deal or deal.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Deal not found")
    await db.delete(deal)


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

    now = datetime.now(timezone.utc)
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
    return _deal_to_response(deal, stage.name if stage else None)


@app.put("/deals/{deal_id}/stage", response_model=DealResponse)
async def move_deal_stage(
    deal_id: uuid.UUID,
    payload: DealStageUpdate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    deal = await db.get(Deal, deal_id)
    if not deal or deal.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Deal not found")

    now = datetime.now(timezone.utc)
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
    return _deal_to_response(deal, stage.name if stage else None)


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

    now = datetime.now(timezone.utc)
    closed_stage_id = await _get_closed_stage_id(db, tenant_id, "Closed Won")
    deal.status = "WON"
    deal.closed_at = now
    deal.updated_at = now
    if closed_stage_id:
        deal.stage_id = closed_stage_id

    # Commission per agent tier.
    if deal.agent_id:
        rate = await _commission_rate(db, tenant_id, deal.agent_id)
        amount = ((deal.value_zar or Decimal("0")) * rate / Decimal("100")).quantize(Decimal("0.01"))
        db.add(Commission(
            id=uuid.uuid4(), tenant_id=tenant_id, deal_id=deal_id,
            agent_id=deal.agent_id, amount_zar=amount, rate_percent=rate,
            status="PENDING", created_at=now, updated_at=now,
        ))

    await db.flush()

    # Bridges — non-blocking, never fail the sale.
    await _notify_lifecycle_won(deal, tenant_id)
    await _notify_finance_won(deal, tenant_id, now)
    background_tasks.add_task(_dispatch_provisioning_bg, {
        "event": "deal.closed_won", "deal_id": str(deal_id),
        "tenant_id": str(tenant_id), "customer_id": str(deal.contact_id),
        "agent_id": str(deal.agent_id) if deal.agent_id else None,
        "package_id": str(deal.package_id) if deal.package_id else None,
        "value_zar": float(deal.value_zar or 0), "closed_at": now.isoformat(),
    })

    stage = await db.get(DealStage, deal.stage_id) if deal.stage_id else None
    return _deal_to_response(deal, stage.name if stage else "Closed Won")


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

    now = datetime.now(timezone.utc)
    closed_stage_id = await _get_closed_stage_id(db, tenant_id, "Closed Lost")
    deal.status = "LOST"
    deal.closed_at = now
    deal.close_reason = reason
    deal.updated_at = now
    if closed_stage_id:
        deal.stage_id = closed_stage_id
    await db.flush()

    # Lifecycle bridge — non-blocking.
    await _notify_lifecycle_lost(deal, tenant_id, reason)

    stage = await db.get(DealStage, deal.stage_id) if deal.stage_id else None
    return _deal_to_response(deal, stage.name if stage else "Closed Lost")


# ── Quotes ───────────────────────────────────────────────────────────────

@app.post("/quotes", response_model=QuoteResponse, status_code=201)
async def create_quote(
    payload: QuoteCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    quote_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

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
    quote.sent_at = datetime.now(timezone.utc)
    await db.flush()
    return QuoteResponse(
        id=quote.id, tenant_id=quote.tenant_id, deal_id=quote.deal_id,
        customer_id=quote.customer_id, lead_id=quote.lead_id, agent_id=quote.agent_id,
        package_id=quote.package_id, items=deserialize_items(quote.items),
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

    now = datetime.now(timezone.utc)
    quote.status = "ACCEPTED"
    quote.accepted_at = now

    if payload.create_deal:
        contract_value = deal_value_from_quote(
            quote.total_monthly or Decimal("0"),
            quote.total_once_off or Decimal("0"),
            quote.term_months or 12,
        )
        stage_id = await _resolve_stage_id(db, tenant_id, None, payload.stage_name or "Proposal")
        if quote.deal_id:
            deal = await db.get(Deal, quote.deal_id)
            if deal and deal.tenant_id == tenant_id:
                deal.value_zar = contract_value
                deal.amount = contract_value
                deal.status = "OPEN"
                deal.closed_at = None
                deal.close_reason = None
                deal.stage_id = stage_id
                deal.updated_at = now
        else:
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
    return QuoteResponse(
        id=quote.id, tenant_id=quote.tenant_id, deal_id=quote.deal_id,
        customer_id=quote.customer_id, lead_id=quote.lead_id, agent_id=quote.agent_id,
        package_id=quote.package_id, items=deserialize_items(quote.items),
        total_monthly=quote.total_monthly, total_once_off=quote.total_once_off,
        term_months=quote.term_months, valid_until=quote.valid_until,
        status=quote.status, terms=quote.terms, created_at=quote.created_at,
        sent_at=quote.sent_at, accepted_at=quote.accepted_at,
    )


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
    # see their own commissions (web quick-stats relies on this).
    if agent_id is None:
        agent_id = ctx.user_id

    q = select(Commission).where(
        Commission.tenant_id == ctx.tenant_id,
        Commission.agent_id == agent_id,
    )
    if deal_id:
        q = q.where(Commission.deal_id == deal_id)
    if status_filter:
        q = q.where(Commission.status == status_filter.upper())
    if start_date:
        q = q.where(Commission.created_at >= start_date)
    if end_date:
        q = q.where(Commission.created_at <= end_date)
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


@app.get("/commissions/report", response_model=List[CommissionReportEntry])
async def commission_report(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    today = date.today()
    if not start_date:
        start_date = date(today.year, today.month, 1)
    if not end_date:
        next_month = start_date + timedelta(days=32)
        end_date = date(next_month.year, next_month.month, 1) - timedelta(days=1)
    end_exclusive = end_date + timedelta(days=1)

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
        .where(
            Commission.tenant_id == tenant_id,
            Commission.created_at >= start_date,
            Commission.created_at < end_exclusive,
        )
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


# ── Targets ──────────────────────────────────────────────────────────────

@app.post("/targets", response_model=TargetPerformanceEntry, status_code=status.HTTP_201_CREATED)
async def create_target(
    payload: TargetCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
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
                Deal.closed_at >= target.period_start,
                Deal.closed_at < target.period_end + timedelta(days=1),
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


# ── Leads ────────────────────────────────────────────────────────────────

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
    return [
        LeadResponse(
            id=l.id, tenant_id=l.tenant_id, contact_id=l.contact_id,
            agent_id=l.agent_id, first_name=l.first_name, last_name=l.last_name,
            email=l.email, phone=l.phone, address=l.address, source=l.source,
            interest_level=l.interest_level, status=l.status, notes=l.notes,
            converted_at=l.converted_at, created_at=l.created_at, updated_at=l.updated_at,
        ) for l in result.scalars().all()
    ]


@app.post("/leads", response_model=LeadResponse, status_code=201)
async def create_lead(
    payload: LeadCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    now = datetime.now(timezone.utc)
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
    update_data = payload.model_dump(exclude_unset=True)
    if "status" in update_data and update_data["status"]:
        update_data["status"] = update_data["status"].upper()
    for key, value in update_data.items():
        setattr(lead, key, value)
    lead.updated_at = datetime.now(timezone.utc)
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
    now = datetime.now(timezone.utc)

    # Create contact from lead details when none linked yet.
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

    deal_name = payload.name or f"{lead.first_name} {lead.last_name} - New Deal"
    agent_id = payload.agent_id or lead.agent_id
    stage_id = await _resolve_stage_id(db, tenant_id, None, "Prospecting")
    deal = Deal(
        id=uuid.uuid4(), tenant_id=tenant_id, contact_id=contact_id,
        lead_id=lead.id, agent_id=agent_id, stage_id=stage_id,
        name=deal_name, amount=payload.value_zar, value_zar=payload.value_zar,
        status="OPEN", created_at=now, updated_at=now,
    )
    db.add(deal)

    lead.status = "CONVERTED"
    lead.converted_at = now
    lead.updated_at = now
    await db.flush()

    return {"deal_id": str(deal.id), "contact_id": str(contact_id), "message": "Lead converted"}


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
    now = datetime.now(timezone.utc)
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
    contact.updated_at = datetime.now(timezone.utc)
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
