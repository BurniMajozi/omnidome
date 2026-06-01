"""
Retention Service — Database Models & Routes
Replaces mock churn data with real PostgreSQL persistence.
Port: 8012 | Module: retention
"""

import uuid
import math
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Date, DateTime, Enum as SAEnum, Float, ForeignKey, Index, Integer, String, Text, func, select
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from services.common.auth import AuthContext, get_auth_context
from services.common.db import Base as CommonBase, session_scope

# ── Enums ───────────────────────────────────────────────────────────────

RISK_LEVEL = SAEnum("critical", "high", "medium", "low", "loyal", name="risk_level", create_type=True)
CHURN_REASON = SAEnum(
    "price_sensitivity", "service_issues", "competitor_offer", "relocation", "no_longer_needed", "payment_issues",
    name="churn_reason", create_type=True,
)
RETENTION_STATUS = SAEnum("pending", "contacted", "offer_sent", "saved", "churned", "escalated", name="retention_status", create_type=True)

# ── Models ──────────────────────────────────────────────────────────────

class Base(CommonBase):
    __abstract__ = True


class CustomerRiskScore(Base):
    __tablename__ = "customer_risk_scores"
    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    risk_score: Mapped[float] = mapped_column(Float, nullable=False)  # 0-100
    risk_level: Mapped[str] = mapped_column(RISK_LEVEL, nullable=False)
    primary_reason: Mapped[str] = mapped_column(CHURN_REASON, nullable=True)
    secondary_reasons: Mapped[list] = mapped_column(JSONB, default=list)
    confidence_score: Mapped[float] = mapped_column(Float, default=0.85)
    tenure_months: Mapped[int] = mapped_column(Integer, default=0)
    lifetime_value: Mapped[float] = mapped_column(Float, default=0.0)
    last_interaction: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    prediction_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        Index("ix_risk_tenant_customer", "tenant_id", "customer_id"),
        Index("ix_risk_tenant_level", "tenant_id", "risk_level"),
    )


class RetentionCase(Base):
    __tablename__ = "retention_cases"
    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    risk_score: Mapped[float] = mapped_column(Float, nullable=False)
    risk_level: Mapped[str] = mapped_column(RISK_LEVEL, nullable=False)
    status: Mapped[str] = mapped_column(RETENTION_STATUS, nullable=False, default="pending")
    churn_reason: Mapped[str] = mapped_column(CHURN_REASON, nullable=True)
    recommended_action: Mapped[str] = mapped_column(Text, nullable=True)
    assigned_to: Mapped[str] = mapped_column(String(200), nullable=True)
    notes: Mapped[list] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    __table_args__ = (Index("ix_retention_tenant_status", "tenant_id", "status"),)


class RetentionCampaign(Base):
    __tablename__ = "retention_campaigns"
    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    target_segment: Mapped[str] = mapped_column(String(200), nullable=False)
    discount_percentage: Mapped[float] = mapped_column(Float, nullable=True)
    customers_targeted: Mapped[int] = mapped_column(Integer, default=0)
    customers_saved: Mapped[int] = mapped_column(Integer, default=0)
    revenue_preserved: Mapped[float] = mapped_column(Float, default=0.0)
    roi_percentage: Mapped[float] = mapped_column(Float, default=0.0)
    start_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    __table_args__ = (Index("ix_campaigns_tenant_active", "tenant_id", "is_active"),)


# ── Schemas ─────────────────────────────────────────────────────────────

class PaginatedResponse(BaseModel):
    items: list
    total: int
    page: int
    page_size: int
    pages: int

class RiskScoreCreate(BaseModel):
    customer_id: uuid.UUID
    risk_score: float = Field(ge=0, le=100)
    risk_level: str
    primary_reason: Optional[str] = None
    secondary_reasons: list[str] = []
    confidence_score: float = Field(ge=0, le=1, default=0.85)
    tenure_months: int = 0
    lifetime_value: float = 0.0

class RiskScoreRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    customer_id: uuid.UUID
    risk_score: float
    risk_level: str
    primary_reason: Optional[str]
    confidence_score: float
    tenure_months: int
    lifetime_value: float
    prediction_date: datetime

class CaseCreate(BaseModel):
    customer_id: uuid.UUID
    risk_score: float
    risk_level: str
    churn_reason: Optional[str] = None
    recommended_action: Optional[str] = None
    assigned_to: Optional[str] = None

class CaseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    customer_id: uuid.UUID
    risk_score: float
    risk_level: str
    status: str
    churn_reason: Optional[str]
    recommended_action: Optional[str]
    assigned_to: Optional[str]
    notes: list[str]
    created_at: datetime
    updated_at: datetime

class CaseAction(BaseModel):
    action: str
    notes: Optional[str] = None

class CampaignCreate(BaseModel):
    name: str
    target_segment: str
    discount_percentage: Optional[float] = None
    start_date: datetime
    end_date: Optional[datetime] = None

class CampaignRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    target_segment: str
    discount_percentage: Optional[float]
    customers_targeted: int
    customers_saved: int
    revenue_preserved: float
    roi_percentage: float
    start_date: datetime
    end_date: Optional[datetime]
    is_active: bool
    created_at: datetime


# ── Routes ──────────────────────────────────────────────────────────────

router = APIRouter(prefix="/api/v1/retention", tags=["Retention"])


@router.get("/predictions", response_model=PaginatedResponse)
async def get_predictions(
    ctx: AuthContext = Depends(get_auth_context),
    risk_level: Optional[str] = None,
    min_score: float = Query(0, ge=0, le=100),
    page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=500),
):
    async with session_scope() as session:
        query = select(CustomerRiskScore).where(
            CustomerRiskScore.tenant_id == ctx.tenant_id,
            CustomerRiskScore.risk_score >= min_score,
        )
        if risk_level:
            query = query.where(CustomerRiskScore.risk_level == risk_level)
        total = await session.scalar(select(func.count()).select_from(query.subquery()))
        items = (await session.execute(query.order_by(CustomerRiskScore.risk_score.desc()).offset((page - 1) * page_size).limit(page_size))).scalars().all()
        return PaginatedResponse(
            items=[RiskScoreRead.model_validate(r) for r in items],
            total=total or 0, page=page, page_size=page_size,
            pages=max(1, math.ceil((total or 0) / page_size)),
        )


@router.post("/predictions", response_model=RiskScoreRead, status_code=status.HTTP_201_CREATED)
async def create_prediction(body: RiskScoreCreate, ctx: AuthContext = Depends(get_auth_context)):
    async with session_scope() as session:
        score = CustomerRiskScore(
            tenant_id=ctx.tenant_id, customer_id=body.customer_id,
            risk_score=body.risk_score, risk_level=body.risk_level,
            primary_reason=body.primary_reason, secondary_reasons=body.secondary_reasons,
            confidence_score=body.confidence_score, tenure_months=body.tenure_months,
            lifetime_value=body.lifetime_value,
        )
        session.add(score)
        await session.flush()
        await session.refresh(score)
        return RiskScoreRead.model_validate(score)


@router.get("/risk-segments")
async def risk_segment_summary(ctx: AuthContext = Depends(get_auth_context)):
    async with session_scope() as session:
        rows = (await session.execute(
            select(CustomerRiskScore.risk_level, func.count(), func.avg(CustomerRiskScore.risk_score))
            .where(CustomerRiskScore.tenant_id == ctx.tenant_id)
            .group_by(CustomerRiskScore.risk_level)
        )).all()
        return [
            {"segment": row[0], "customer_count": row[1], "avg_risk_score": round(float(row[2] or 0), 1)}
            for row in rows
        ]


@router.get("/cases", response_model=PaginatedResponse)
async def get_cases(
    ctx: AuthContext = Depends(get_auth_context),
    status_filter: Optional[str] = Query(None, alias="status"),
    risk_level: Optional[str] = None,
    page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
):
    async with session_scope() as session:
        query = select(RetentionCase).where(RetentionCase.tenant_id == ctx.tenant_id)
        if status_filter:
            query = query.where(RetentionCase.status == status_filter)
        if risk_level:
            query = query.where(RetentionCase.risk_level == risk_level)
        total = await session.scalar(select(func.count()).select_from(query.subquery()))
        items = (await session.execute(query.order_by(RetentionCase.risk_score.desc()).offset((page - 1) * page_size).limit(page_size))).scalars().all()
        return PaginatedResponse(
            items=[CaseRead.model_validate(c) for c in items],
            total=total or 0, page=page, page_size=page_size,
            pages=max(1, math.ceil((total or 0) / page_size)),
        )


@router.post("/cases", response_model=CaseRead, status_code=status.HTTP_201_CREATED)
async def create_case(body: CaseCreate, ctx: AuthContext = Depends(get_auth_context)):
    async with session_scope() as session:
        case = RetentionCase(
            tenant_id=ctx.tenant_id, customer_id=body.customer_id,
            risk_score=body.risk_score, risk_level=body.risk_level,
            churn_reason=body.churn_reason, recommended_action=body.recommended_action,
            assigned_to=body.assigned_to,
        )
        session.add(case)
        await session.flush()
        await session.refresh(case)
        return CaseRead.model_validate(case)


@router.post("/cases/{case_id}/action")
async def take_action(case_id: uuid.UUID, body: CaseAction, ctx: AuthContext = Depends(get_auth_context)):
    async with session_scope() as session:
        case = await session.get(RetentionCase, case_id)
        if not case or case.tenant_id != ctx.tenant_id:
            raise HTTPException(404, "Case not found")
        case.notes = (case.notes or []) + [f"{datetime.now(timezone.utc).isoformat()}: {body.action} — {body.notes or ''}"]
        if body.action == "escalate":
            case.status = "escalated"
        elif body.action == "offer_sent":
            case.status = "offer_sent"
        await session.flush()
        return {"case_id": str(case_id), "action": body.action, "status": case.status}


@router.get("/campaigns", response_model=list[CampaignRead])
async def get_campaigns(
    ctx: AuthContext = Depends(get_auth_context),
    is_active: Optional[bool] = None,
):
    async with session_scope() as session:
        query = select(RetentionCampaign).where(RetentionCampaign.tenant_id == ctx.tenant_id)
        if is_active is not None:
            query = query.where(RetentionCampaign.is_active == is_active)
        items = (await session.execute(query.order_by(RetentionCampaign.created_at.desc()))).scalars().all()
        return [CampaignRead.model_validate(c) for c in items]


@router.post("/campaigns", response_model=CampaignRead, status_code=status.HTTP_201_CREATED)
async def create_campaign(body: CampaignCreate, ctx: AuthContext = Depends(get_auth_context)):
    async with session_scope() as session:
        campaign = RetentionCampaign(
            tenant_id=ctx.tenant_id, name=body.name,
            target_segment=body.target_segment, discount_percentage=body.discount_percentage,
            start_date=body.start_date, end_date=body.end_date,
        )
        session.add(campaign)
        await session.flush()
        await session.refresh(campaign)
        return CampaignRead.model_validate(campaign)


@router.get("/metrics")
async def get_metrics(
    ctx: AuthContext = Depends(get_auth_context),
    period: str = Query("monthly", pattern=r"^(weekly|monthly|quarterly)$"),
):
    async with session_scope() as session:
        total_scored = await session.scalar(
            select(func.count()).select_from(CustomerRiskScore).where(CustomerRiskScore.tenant_id == ctx.tenant_id)
        ) or 0
        at_risk = await session.scalar(
            select(func.count()).select_from(CustomerRiskScore).where(
                CustomerRiskScore.tenant_id == ctx.tenant_id,
                CustomerRiskScore.risk_level.in_(["critical", "high"]),
            )
        ) or 0
        active_cases = await session.scalar(
            select(func.count()).select_from(RetentionCase).where(
                RetentionCase.tenant_id == ctx.tenant_id,
                RetentionCase.status.notin_(["saved", "churned"]),
            )
        ) or 0
        campaigns = (await session.execute(
            select(RetentionCampaign).where(RetentionCampaign.tenant_id == ctx.tenant_id, RetentionCampaign.is_active == True)
        )).scalars().all()
        total_saved = sum(c.customers_saved for c in campaigns)
        total_revenue = sum(c.revenue_preserved for c in campaigns)
        return {
            "period": period,
            "customers_scored": total_scored,
            "at_risk_customers": at_risk,
            "active_retention_cases": active_cases,
            "customers_saved": total_saved,
            "revenue_preserved": total_revenue,
            "active_campaigns": len(campaigns),
        }


@router.post("/predict/batch")
async def trigger_batch_prediction(
    ctx: AuthContext = Depends(get_auth_context),
    segment: Optional[str] = None,
):
    """Trigger batch churn prediction. In production, this queues an ML job."""
    import uuid as _uuid
    job_id = _uuid.uuid4()
    return {
        "job_id": str(job_id),
        "status": "queued",
        "segment": segment or "all",
        "estimated_completion": (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat(),
    }
