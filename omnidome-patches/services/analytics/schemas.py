"""Pydantic v2 schemas for the Analytics Service."""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


# ── Report Schemas ────────────────────────────────────────────────────────

class ReportCreate(BaseModel):
    report_type: str = "custom"
    period: str = "monthly"


class AnalyticsReportRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    report_type: str
    period: str
    data: Dict[str, Any]
    generated_at: datetime
    generated_by: uuid.UUID
    created_at: datetime
    updated_at: datetime


class AnalyticsReportData(BaseModel):
    id: uuid.UUID
    report_type: str
    period: str
    data: Dict[str, Any]
    generated_at: datetime


# ── Cross-Service Summary Schemas ─────────────────────────────────────────

class ExecutiveSummary(BaseModel):
    total_customers: int = 0
    active_customers: int = 0
    mrr: float = 0.0
    total_revenue: float = 0.0
    churn_rate: float = 0.0
    active_tickets: int = 0
    network_uptime_pct: float = 100.0
    avg_call_duration_seconds: float = 0.0
    usage_billing_variance_pct: float = 0.0


class RevenueTrendPoint(BaseModel):
    period: str
    revenue: float


class RevenueTrend(BaseModel):
    trend: List[RevenueTrendPoint]


class ChurnBreakdown(BaseModel):
    total_churned: int = 0
    by_reason: Dict[str, int] = Field(default_factory=dict)
    by_segment: Dict[str, int] = Field(default_factory=dict)
    monthly_rate: float = 0.0


class UsageBillingVariance(BaseModel):
    total_usage_value: float = 0.0
    total_billed: float = 0.0
    variance_pct: float = 0.0
    period: str = ""


class NetworkHealth(BaseModel):
    uptime_pct: float = 100.0
    active_incidents: int = 0
    avg_latency_ms: float = 0.0
    packet_loss_pct: float = 0.0


# ── Pagination ────────────────────────────────────────────────────────────

class PaginatedResponse(BaseModel):
    items: List[Any]
    total: int
    page: int
    page_size: int
    pages: int
