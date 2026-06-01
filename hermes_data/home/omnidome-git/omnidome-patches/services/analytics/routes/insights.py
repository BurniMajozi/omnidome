"""Analytics models, database, and routes — all-in-one for compactness."""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import DateTime, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from services.common.auth import AuthContext, get_auth_context
from services.common.db import Base as CommonBase, session_scope
from services.common.http_client import service_call
from analytics.database import session_scope

router = APIRouter(tags=["Analytics"])
Base = CommonBase


class AnalyticsReport(Base):
    __tablename__ = "analytics_reports"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    report_type: Mapped[str] = mapped_column(String(100), nullable=False)
    period: Mapped[str] = mapped_column(String(20), nullable=False)
    data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    generated_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    __table_args__ = (Index("ix_analytics_tenant_type", "tenant_id", "report_type"),)


class ReportCreate(BaseModel):
    report_type: str
    period: str = "monthly"


class ReportRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    report_type: str
    period: str
    data: Dict[str, Any]
    generated_at: datetime


# ── Routes ─────────────────────────────────────────────────────────────

@router.get("/executive-summary")
async def executive_summary(ctx: AuthContext = Depends(get_auth_context)):
    """Aggregate data from retention, billing, network, call_center, sales."""
    results = {}
    # Best-effort parallel aggregation
    import asyncio
    async def safe_call(service, path):
        try:
            return await service_call(service, "GET", path, tenant_id=str(ctx.tenant_id), user_id=str(ctx.user_id), timeout=5.0)
        except Exception as e:
            return {"error": str(e)}

    retention, billing, network, calls, sales = await asyncio.gather(
        safe_call("retention", "/api/metrics"),
        safe_call("billing", "/api/reports/revenue?months=3"),
        safe_call("network", "/api/health"),
        safe_call("call_center", "/api/reports/intelligence"),
        safe_call("sales", "/api/pipeline"),
    )
    return {
        "generated_at": datetime.utcnow().isoformat(),
        "retention_metrics": retention,
        "billing_summary": billing,
        "network_health": network,
        "call_center": calls,
        "sales_pipeline": sales,
    }


@router.get("/revenue-trend")
async def revenue_trend(months: int = Query(6, ge=1, le=24), ctx: AuthContext = Depends(get_auth_context)):
    return await service_call("billing", "GET", f"/api/reports/revenue?months={months}", tenant_id=str(ctx.tenant_id), user_id=str(ctx.user_id))


@router.get("/churn-analysis")
async def churn_analysis(ctx: AuthContext = Depends(get_auth_context)):
    predictions = await service_call("retention", "GET", "/api/predictions?limit=100", tenant_id=str(ctx.tenant_id), user_id=str(ctx.user_id))
    risk_segments = await service_call("retention", "GET", "/api/risk-segments", tenant_id=str(ctx.tenant_id), user_id=str(ctx.user_id))
    return {"predictions": predictions, "risk_segments": risk_segments}


@router.get("/usage-billing-sync")
async def usage_billing_sync(ctx: AuthContext = Depends(get_auth_context)):
    return {"accounts_synced": 0, "usage_variance_detected": "0%", "orphaned_radius_accounts": 0, "status": "stub"}


@router.get("/network-health")
async def network_health(ctx: AuthContext = Depends(get_auth_context)):
    return await service_call("network", "GET", "/api/health", tenant_id=str(ctx.tenant_id), user_id=str(ctx.user_id))


@router.post("/reports", response_model=ReportRead)
async def create_report(body: ReportCreate, ctx: AuthContext = Depends(get_auth_context)):
    report_data = {}
    if body.report_type == "revenue":
        report_data = await service_call("billing", "GET", f"/api/reports/revenue?months=6", tenant_id=str(ctx.tenant_id), user_id=str(ctx.user_id))
    elif body.report_type == "churn":
        report_data = await service_call("retention", "GET", "/api/metrics", tenant_id=str(ctx.tenant_id), user_id=str(ctx.user_id))
    async with session_scope() as session:
        report = AnalyticsReport(tenant_id=ctx.tenant_id, report_type=body.report_type, period=body.period, data=report_data, generated_by=ctx.user_id)
        session.add(report)
        await session.flush()
        await session.refresh(report)
        return ReportRead.model_validate(report)


@router.get("/reports")
async def list_reports(ctx: AuthContext = Depends(get_auth_context), limit: int = Query(50, le=200)):
    async with session_scope() as session:
        from sqlalchemy import select
        items = (await session.execute(select(AnalyticsReport).where(AnalyticsReport.tenant_id == ctx.tenant_id).order_by(AnalyticsReport.generated_at.desc()).limit(limit))).scalars().all()
        return [ReportRead.model_validate(r) for r in items]
