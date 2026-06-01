"""Analytics routes — executive summary, revenue, churn, usage/billing, network health, custom reports."""

import os
import uuid
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select

from services.analytics.models import REPORT_TYPE, AnalyticsReport
from services.analytics.schemas import (
    AnalyticsReportData,
    AnalyticsReportRead,
    ChurnBreakdown,
    ExecutiveSummary,
    NetworkHealth,
    PaginatedResponse,
    ReportCreate,
    RevenueTrend,
    UsageBillingVariance,
)
from services.common.auth import AuthContext, get_auth_context
from services.common.db import session_scope

router = APIRouter(prefix="/analytics", tags=["Analytics"])

# Internal service URLs (Docker Compose service names)
RETENTION_URL = os.getenv("RETENTION_SERVICE_URL", "http://retention:8012")
BILLING_URL = os.getenv("BILLING_SERVICE_URL", "http://billing:8003")
NETWORK_URL = os.getenv("NETWORK_SERVICE_URL", "http://network:8005")
CALL_CENTER_URL = os.getenv("CALL_CENTER_SERVICE_URL", "http://call_center:8007")


def _forward_headers(ctx: AuthContext) -> dict:
    return {
        "X-User-Id": str(ctx.user_id),
        "X-Tenant-Id": str(ctx.tenant_id),
    }


async def _fetch_json(url: str, headers: dict) -> dict:
    """Fetch JSON from a sibling service; return empty dict on failure."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 200:
                return resp.json()
    except Exception:
        pass
    return {}


# ---------------------------------------------------------------------------
# GET /analytics/executive-summary
# ---------------------------------------------------------------------------

@router.get("/executive-summary", response_model=ExecutiveSummary)
async def executive_summary(
    ctx: AuthContext = Depends(get_auth_context),
):
    headers = _forward_headers(ctx)

    # Fetch data from multiple services concurrently (best-effort)
    retention_data, billing_data, network_data, call_center_data = {}, {}, {}, {}
    try:
        retention_data = await _fetch_json(f"{RETENTION_URL}/api/v1/retention/summary", headers)
    except Exception:
        pass
    try:
        billing_data = await _fetch_json(f"{BILLING_URL}/api/v1/billing/summary", headers)
    except Exception:
        pass
    try:
        network_data = await _fetch_json(f"{NETWORK_URL}/api/v1/network/health", headers)
    except Exception:
        pass
    try:
        call_center_data = await _fetch_json(f"{CALL_CENTER_URL}/api/v1/call-center/metrics", headers)
    except Exception:
        pass

    return ExecutiveSummary(
        total_customers=retention_data.get("total_customers", 0),
        active_customers=retention_data.get("active_customers", 0),
        mrr=billing_data.get("mrr", 0.0),
        total_revenue=billing_data.get("total_revenue", 0.0),
        churn_rate=retention_data.get("churn_rate", 0.0),
        active_tickets=retention_data.get("active_tickets", 0),
        network_uptime_pct=network_data.get("uptime_pct", 100.0),
        avg_call_duration_seconds=call_center_data.get("avg_call_duration_seconds", 0.0),
        usage_billing_variance_pct=billing_data.get("usage_billing_variance_pct", 0.0),
    )


# ---------------------------------------------------------------------------
# GET /analytics/revenue-trend
# ---------------------------------------------------------------------------

@router.get("/revenue-trend", response_model=RevenueTrend)
async def revenue_trend(
    ctx: AuthContext = Depends(get_auth_context),
    period: str = Query("monthly", description="Period granularity: daily, weekly, monthly"),
    months: int = Query(12, ge=1, le=36),
):
    headers = _forward_headers(ctx)
    billing_data = await _fetch_json(
        f"{BILLING_URL}/api/v1/billing/revenue-trend?period={period}&months={months}",
        headers,
    )

    trend_points = billing_data.get("trend", [])
    return RevenueTrend(trend=trend_points)


# ---------------------------------------------------------------------------
# GET /analytics/churn-analysis
# ---------------------------------------------------------------------------

@router.get("/churn-analysis", response_model=ChurnBreakdown)
async def churn_analysis(
    ctx: AuthContext = Depends(get_auth_context),
):
    headers = _forward_headers(ctx)
    retention_data = await _fetch_json(f"{RETENTION_URL}/api/v1/retention/churn-analysis", headers)

    return ChurnBreakdown(
        total_churned=retention_data.get("total_churned", 0),
        by_reason=retention_data.get("by_reason", {}),
        by_segment=retention_data.get("by_segment", {}),
        monthly_rate=retention_data.get("monthly_rate", 0.0),
    )


# ---------------------------------------------------------------------------
# GET /analytics/usage-billing-sync
# ---------------------------------------------------------------------------

@router.get("/usage-billing-sync", response_model=UsageBillingVariance)
async def usage_billing_sync(
    ctx: AuthContext = Depends(get_auth_context),
    period: Optional[str] = Query(None, description="Period filter, e.g. 2024-01"),
):
    headers = _forward_headers(ctx)
    url = f"{BILLING_URL}/api/v1/billing/usage-billing-variance"
    if period:
        url += f"?period={period}"
    billing_data = await _fetch_json(url, headers)

    return UsageBillingVariance(
        total_usage_value=billing_data.get("total_usage_value", 0.0),
        total_billed=billing_data.get("total_billed", 0.0),
        variance_pct=billing_data.get("variance_pct", 0.0),
        period=billing_data.get("period", period or ""),
    )


# ---------------------------------------------------------------------------
# GET /analytics/network-health
# ---------------------------------------------------------------------------

@router.get("/network-health", response_model=NetworkHealth)
async def network_health(
    ctx: AuthContext = Depends(get_auth_context),
):
    headers = _forward_headers(ctx)
    network_data = await _fetch_json(f"{NETWORK_URL}/api/v1/network/health", headers)

    return NetworkHealth(
        uptime_pct=network_data.get("uptime_pct", 100.0),
        active_incidents=network_data.get("active_incidents", 0),
        avg_latency_ms=network_data.get("avg_latency_ms", 0.0),
        packet_loss_pct=network_data.get("packet_loss_pct", 0.0),
    )


# ---------------------------------------------------------------------------
# POST /analytics/reports — Generate custom report
# ---------------------------------------------------------------------------

@router.post("/reports", response_model=AnalyticsReportRead, status_code=status.HTTP_201_CREATED)
async def generate_report(
    body: ReportCreate,
    ctx: AuthContext = Depends(get_auth_context),
):
    headers = _forward_headers(ctx)

    # Aggregate data from sibling services for the custom report
    report_data = {
        "generated_by": str(ctx.user_id),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "period": body.period,
    }

    # Best-effort data collection
    if body.report_type in ("executive_summary", "custom"):
        retention = await _fetch_json(f"{RETENTION_URL}/api/v1/retention/summary", headers)
        billing = await _fetch_json(f"{BILLING_URL}/api/v1/billing/summary", headers)
        report_data["retention"] = retention
        report_data["billing"] = billing

    if body.report_type in ("revenue_trend", "custom"):
        billing_trend = await _fetch_json(
            f"{BILLING_URL}/api/v1/billing/revenue-trend?period={body.period}", headers
        )
        report_data["revenue_trend"] = billing_trend

    if body.report_type in ("churn_analysis", "custom"):
        churn = await _fetch_json(f"{RETENTION_URL}/api/v1/retention/churn-analysis", headers)
        report_data["churn"] = churn

    if body.report_type in ("network_health", "custom"):
        network = await _fetch_json(f"{NETWORK_URL}/api/v1/network/health", headers)
        report_data["network"] = network

    async with session_scope() as session:
        report = AnalyticsReport(
            tenant_id=ctx.tenant_id,
            report_type=body.report_type,
            period=body.period,
            data=report_data,
            generated_by=ctx.user_id,
        )
        session.add(report)
        await session.flush()
        await session.refresh(report)
        return report


# ---------------------------------------------------------------------------
# GET /analytics/reports — List generated reports
# ---------------------------------------------------------------------------

@router.get("/reports", response_model=PaginatedResponse)
async def list_reports(
    ctx: AuthContext = Depends(get_auth_context),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    report_type: Optional[str] = Query(None),
):
    async with session_scope() as session:
        stmt = select(AnalyticsReport).where(AnalyticsReport.tenant_id == ctx.tenant_id)

        if report_type:
            stmt = stmt.where(AnalyticsReport.report_type == report_type)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total_result = await session.execute(count_stmt)
        total = total_result.scalar_one()

        stmt = (
            stmt.order_by(AnalyticsReport.generated_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await session.execute(stmt)
        items = result.scalars().all()

    pages = max(1, (total + page_size - 1) // page_size)
    return PaginatedResponse(
        items=[AnalyticsReportRead.model_validate(r) for r in items],
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


# ---------------------------------------------------------------------------
# GET /analytics/reports/{report_id} — Get report data
# ---------------------------------------------------------------------------

@router.get("/reports/{report_id}", response_model=AnalyticsReportData)
async def get_report(
    report_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    async with session_scope() as session:
        stmt = select(AnalyticsReport).where(
            AnalyticsReport.id == report_id,
            AnalyticsReport.tenant_id == ctx.tenant_id,
        )
        result = await session.execute(stmt)
        report = result.scalar_one_or_none()
        if not report:
            raise HTTPException(status_code=404, detail="Report not found")

        return AnalyticsReportData(
            id=report.id,
            report_type=report.report_type,
            period=report.period,
            data=report.data,
            generated_at=report.generated_at,
        )
