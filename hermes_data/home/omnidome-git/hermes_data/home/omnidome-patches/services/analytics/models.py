"""SQLAlchemy models for the Analytics Service."""

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Enum as SAEnum,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from services.common.db import Base as CommonBase


class Base(CommonBase):
    __abstract__ = True


# ── Enums ──────────────────────────────────────────────────────────────────

REPORT_TYPE = SAEnum(
    "executive_summary", "revenue_trend", "churn_analysis",
    "usage_billing_sync", "network_health", "custom",
    name="report_type", create_type=True,
)


# ── Analytics Report ───────────────────────────────────────────────────────

class AnalyticsReport(Base):
    __tablename__ = "analytics_reports"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    report_type: Mapped[str] = mapped_column(REPORT_TYPE, nullable=False)
    period: Mapped[str] = mapped_column(String(50), nullable=False, default="monthly")
    data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    generated_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_analytics_reports_tenant_type", "tenant_id", "report_type"),
        Index("ix_analytics_reports_generated", "tenant_id", "generated_at"),
    )
