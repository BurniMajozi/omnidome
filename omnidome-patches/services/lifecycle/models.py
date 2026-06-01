"""Customer Lifecycle Service — tracks Lead → Customer → Active → At-Risk → Churned.

Models:
  LifecycleStage — configurable stages per tenant
  LifecycleEvent — audit trail of every state transition
  CustomerSegmentAssignment — tracks which segment a customer belongs to

Provides:
  - Automatic stage progression on sales close-won
  - Churn detection from journey engine outcomes
  - Cross-service lifecycle API for portal + other services
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class LifecycleBase(DeclarativeBase):
    __abstract__ = True


# ---------------------------------------------------------------------------
# Lifecycle Stage — defines the stages a customer goes through
# ---------------------------------------------------------------------------

class LifecycleStage(LifecycleBase):
    __tablename__ = "lifecycle_stages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )

    name: Mapped[str] = mapped_column(String(60), nullable=False)

    # Category: lead, prospect, customer, at_risk, churned, reactivated
    category: Mapped[str] = mapped_column(String(20), nullable=False, default="customer")

    # Ordering
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Color for UI
    color: Mapped[str] = mapped_column(String(7), default="#60a5fa")

    # Is this the default stage for new customers?
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)

    # Actions to auto-trigger on entering this stage
    # e.g., {"send_email": "welcome", "notify_team": "retention"}
    on_enter_actions: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_lifecycle_stage_name"),
        Index("ix_lifecycle_stages_tenant", "tenant_id", "category"),
    )


# ---------------------------------------------------------------------------
# Lifecycle Event — audit trail of every state transition
# ---------------------------------------------------------------------------

class LifecycleEvent(LifecycleBase):
    __tablename__ = "lifecycle_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )

    # Previous and new stage
    from_stage: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    to_stage: Mapped[str] = mapped_column(String(60), nullable=False)
    from_stage_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    to_stage_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)

    # What triggered this transition
    # "sale", "manual", "journey_engine", "payment_failure", "support_ticket", "bulk_import"
    trigger_source: Mapped[str] = mapped_column(String(30), nullable=False, default="manual")

    # Reference to the triggering entity
    trigger_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    # e.g., deal_id if from sale, cancel_event_id if from journey engine

    # Context
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index("ix_lifecycle_events_customer", "customer_id", "created_at"),
        Index("ix_lifecycle_events_tenant", "tenant_id", "created_at"),
    )


# ---------------------------------------------------------------------------
# Customer Lifecycle — current lifecycle state per customer
# ---------------------------------------------------------------------------

class CustomerLifecycle(LifecycleBase):
    __tablename__ = "customer_lifecycles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )

    # Unique per customer — one lifecycle record per customer
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, unique=True, index=True
    )

    # Current stage
    current_stage: Mapped[str] = mapped_column(String(60), nullable=False, default="lead")
    current_stage_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)

    # Lifecycle metrics
    first_contact_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    converted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    first_payment_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_payment_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_activity_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    churned_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    reactivated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Current plan/product info
    current_plan: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    monthly_recurring_revenue: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00")
    )

    # Health score (0-100, computed)
    health_score: Mapped[int] = mapped_column(Integer, default=50)
    health_factors: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # Risk flags
    is_at_risk: Mapped[bool] = mapped_column(Boolean, default=False)
    risk_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    churn_probability: Mapped[Optional[float]] = mapped_column(Numeric(5, 2), nullable=True)

    # Journey engine link
    last_journey_event_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )

    # Sales link
    originating_lead_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    originating_deal_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    assigned_sales_agent_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    assigned_cs_agent_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_customer_lifecycles_stage", "tenant_id", "current_stage"),
        Index("ix_customer_lifecycles_risk", "tenant_id", "is_at_risk"),
        Index("ix_customer_lifecycles_health", "tenant_id", "health_score"),
        Index("ix_customer_lifecycles_mrr", "tenant_id", "monthly_recurring_revenue"),
    )


# ---------------------------------------------------------------------------
# Segment Assignment — which segment(s) a customer belongs to
# ---------------------------------------------------------------------------

class CustomerSegmentAssignment(LifecycleBase):
    __tablename__ = "customer_segment_assignments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    segment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )

    # How they got into this segment: manual, rule, auto
    assignment_source: Mapped[str] = mapped_column(String(20), default="rule")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "customer_id", "segment_id", name="uq_customer_segment"),
    )


# ---------------------------------------------------------------------------
# Lifecycle Summary — aggregated metrics (for dashboards)
# ---------------------------------------------------------------------------

class LifecycleSummary(LifecycleBase):
    __tablename__ = "lifecycle_summaries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )

    # Period: daily, weekly, monthly
    period_type: Mapped[str] = mapped_column(String(10), nullable=False)
    period_date: Mapped[str] = mapped_column(String(10), nullable=False)  # YYYY-MM-DD

    # Counts by stage
    total_leads: Mapped[int] = mapped_column(Integer, default=0)
    total_prospects: Mapped[int] = mapped_column(Integer, default=0)
    total_customers: Mapped[int] = mapped_column(Integer, default=0)
    total_at_risk: Mapped[int] = mapped_column(Integer, default=0)
    total_churned: Mapped[int] = mapped_column(Integer, default=0)
    total_reactivated: Mapped[int] = mapped_column(Integer, default=0)

    # Transitions
    new_conversions: Mapped[int] = mapped_column(Integer, default=0)
    new_churns: Mapped[int] = mapped_column(Integer, default=0)
    new_reactivations: Mapped[int] = mapped_column(Integer, default=0)
    risk_escalations: Mapped[int] = mapped_column(Integer, default=0)

    # Revenue metrics
    mrr_at_start: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"))
    mrr_new: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"))
    mrr_churned: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"))
    mrr_reactivated: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"))
    mrr_at_end: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"))

    # Journey engine stats
    cancel_attempts: Mapped[int] = mapped_column(Integer, default=0)
    offers_shown: Mapped[int] = mapped_column(Integer, default=0)
    offers_accepted: Mapped[int] = mapped_column(Integer, default=0)
    revenue_preserved: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "period_type", "period_date", name="uq_lifecycle_summary"),
    )
