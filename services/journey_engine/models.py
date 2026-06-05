"""SQLAlchemy models for Retention Journey Engine.

This service manages the full cancel-to-save lifecycle:
- Journey definitions with rule-based targeting
- Offer templates with discount/upgrade/pause options
- Cancel events triggered by the customer portal
- Journey execution tracking (which journey fired, what offer was shown)
- Outcome recording (accepted/rejected/churned) for ML feedback
"""

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Enum as SAEnum,
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


class JourneyBase(DeclarativeBase):
    __abstract__ = True


# ---------------------------------------------------------------------------
# Retention Journey — defines a complete cancel-save flow
# ---------------------------------------------------------------------------

class RetentionJourney(JourneyBase):
    __tablename__ = "retention_journeys"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Trigger condition: what starts this journey
    # Currently: "cancel_initiated" (customer clicks cancel)
    # Future: "usage_drop", "payment_failed", "competitor_mention"
    trigger_event: Mapped[str] = mapped_column(
        String(50), nullable=False, default="cancel_initiated"
    )

    # Journey status: draft, active, paused, archived
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="draft"
    )

    # Priority when multiple journeys match (higher = first)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # The offer to present (linked)
    offer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("retention_offers.id", ondelete="SET NULL"),
        nullable=True
    )

    # Fallback offer if primary is not applicable
    fallback_offer_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("retention_offers.id", ondelete="SET NULL"),
        nullable=True
    )

    # Channel for outreach: portal, email, sms, phone, agent
    channel: Mapped[str] = mapped_column(
        String(20), nullable=False, default="portal"
    )

    # A/B test config (optional)
    ab_test_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    ab_test_config: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # Stats (updated by triggers)
    times_triggered: Mapped[int] = mapped_column(Integer, default=0)
    times_shown: Mapped[int] = mapped_column(Integer, default=0)
    times_accepted: Mapped[int] = mapped_column(Integer, default=0)
    times_rejected: Mapped[int] = mapped_column(Integer, default=0)
    revenue_preserved: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00")
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_journeys_tenant_status", "tenant_id", "status"),
        Index("ix_journeys_tenant_trigger", "tenant_id", "trigger_event"),
    )


# ---------------------------------------------------------------------------
# Journey Rules — conditional targeting rules for a journey
# ---------------------------------------------------------------------------
# Rules are evaluated top-to-bottom. ALL rules in a rule group must
# match (AND logic). Rule groups are OR'd together by default.

class JourneyRule(JourneyBase):
    __tablename__ = "journey_rules"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    journey_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("retention_journeys.id", ondelete="CASCADE"),
        nullable=False, index=True
    )

    # Logical group for this rule (rules in same group = AND)
    rule_group: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # The customer attribute to evaluate
    # risk_score, segment, tenure_months, monthly_spend, payment_days_overdue,
    # num_support_tickets, plan_type, region, usage_trend, competitor_mention
    attribute: Mapped[str] = mapped_column(String(50), nullable=False)

    # Operator: eq, ne, gt, gte, lt, lte, in, not_in, between, contains
    operator: Mapped[str] = mapped_column(String(20), nullable=False)

    # Comparison value (can be scalar or array depending on operator)
    value: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # Examples:
    #   {"value": 70, "type": "number"}            -> gt 70
    #   {"values": ["Premium", "Enterprise"], "type": "array"} -> in [...]
    #   {"min": 50, "max": 80, "type": "range"}   -> between 50 and 80
    #   {"value": "Standard", "type": "string"}    -> eq "Standard"

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Ordering within the rule group
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index("ix_journey_rules_journey", "journey_id", "rule_group"),
    )


# ---------------------------------------------------------------------------
# Move House Request
# ---------------------------------------------------------------------------

MOVE_HOUSE_STATUS = SAEnum(
    "pending", "coverage_check", "covered", "not_covered",
    "installation_scheduled", "completed", "cancelled",
    name="move_house_status", create_type=True,
)


class MoveHouseRequest(JourneyBase):
    __tablename__ = "move_house_requests"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    subscription_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("subscriptions.id", ondelete="SET NULL"), nullable=True)
    account_number: Mapped[str] = mapped_column(String(50), nullable=False)

    # Old address
    old_address: Mapped[dict] = mapped_column(JSONB, nullable=False)

    # New address
    new_address: Mapped[dict] = mapped_column(JSONB, nullable=False)
    new_address_line1: Mapped[str] = mapped_column(String(255), nullable=False)
    new_address_line2: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    new_city: Mapped[str] = mapped_column(String(100), nullable=False)
    new_postal_code: Mapped[str] = mapped_column(String(10), nullable=False)
    new_province: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    new_gps_lat: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 8), nullable=True)
    new_gps_lng: Mapped[Optional[Decimal]] = mapped_column(Numeric(11, 8), nullable=True)

    # Coverage check
    coverage_checked: Mapped[bool] = mapped_column(Boolean, default=False)
    coverage_available: Mapped[bool] = mapped_column(Boolean, default=False)
    recommended_package_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    fno_at_new_address: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Status
    status: Mapped[str] = mapped_column(MOVE_HOUSE_STATUS, nullable=False, default="pending")

    # Installation
    installation_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    technician_visit_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)

    # Effective date
    requested_date: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_move_house_tenant_status", "tenant_id", "status"),
        Index("ix_move_house_customer", "customer_id", "created_at"),
    )


# ---------------------------------------------------------------------------
# Service Pause Request
# ---------------------------------------------------------------------------

PAUSE_STATUS = SAEnum(
    "pending", "approved", "active", "expiring_soon", "reactivated", "cancelled",
    name="pause_status", create_type=True,
)


class ServicePauseRequest(JourneyBase):
    __tablename__ = "service_pause_requests"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    subscription_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("subscriptions.id", ondelete="SET NULL"), nullable=True)
    account_number: Mapped[str] = mapped_column(String(50), nullable=False)

    # Pause details
    reason: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    pause_start_date: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)
    pause_end_date: Mapped[date] = mapped_column(Date, nullable=False)
    max_pause_months: Mapped[int] = mapped_column(Integer, default=3)

    # Status
    status: Mapped[str] = mapped_column(PAUSE_STATUS, nullable=False, default="pending")

    # Minimum monthly fee during pause (if any)
    pause_monthly_fee_zar: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))

    # Actual dates
    paused_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    reactivated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_pause_tenant_status", "tenant_id", "status"),
        Index("ix_pause_customer", "customer_id", "created_at"),
        Index("ix_pause_end_date", "pause_end_date"),
    )


# ---------------------------------------------------------------------------
# Retention Offers — discount offers, upgrades, pauses, etc.
# ---------------------------------------------------------------------------

class RetentionOffer(JourneyBase):
    __tablename__ = "retention_offers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Offer type determines the action
    # percentage_discount — reduce monthly bill by X%
    # fixed_discount — reduce monthly bill by R X
    # plan_downgrade — move to cheaper plan (keep customer)
    # plan_upgrade — offer better plan at same/lower price
    # service_pause — pause service for N months (tenure preserved)
    # free_months — give N months free
    # loyalty_reward — add data/VAS at no charge
    # personal_outreach — flag for human agent call
    offer_type: Mapped[str] = mapped_column(String(30), nullable=False)

    # The offer parameters (type-specific JSON)
    # percentage_discount: {"percent": 15, "duration_months": 6}
    # fixed_discount: {"amount_zar": 99.00, "duration_months": 3}
    # plan_downgrade: {"target_plan_id": "...", "effective": "immediate"}
    # service_pause: {"duration_months": 3, "reactivate_auto": true}
    # free_months: {"months": 2}
    # loyalty_reward: {"data_gb": 50, "vas_product_id": "..."}
    # personal_outreach: {"priority": "high", "assign_team": "retention"}
    parameters: Mapped[dict] = mapped_column(JSONB, nullable=False)

    # Eligibility / caps
    max_per_customer: Mapped[int] = mapped_column(
        Integer, default=1  # how many times one customer can get this offer
    )
    max_total_redemptions: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True  # null = unlimited
    )
    total_redemptions: Mapped[int] = mapped_column(Integer, default=0)

    # Cost tracking
    estimated_cost_per_use: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(12, 2), nullable=True
    )

    # Status
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_offers_tenant_type", "tenant_id", "offer_type"),
        Index("ix_offers_tenant_status", "tenant_id", "status"),
    )


# ---------------------------------------------------------------------------
# Cancel Events — a customer initiated cancellation
# ---------------------------------------------------------------------------

class CancelEvent(JourneyBase):
    __tablename__ = "cancel_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )

    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    account_number: Mapped[str] = mapped_column(String(50), nullable=False)

    # Customer snapshot at time of cancel (for rule evaluation)
    customer_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # {
    #   "segment": "Premium",
    #   "tenure_months": 14,
    #   "monthly_spend_zar": 799.00,
    #   "risk_score": 87.5,
    #   "num_support_tickets_30d": 3,
    #   "payment_days_overdue": 0,
    #   "plan_id": "...",
    #   "region": "Gauteng",
    #   "usage_trend": "declining"
    # }

    # Cancel reason (from customer)
    cancel_reason: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    cancel_reason_detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Channel where cancel was initiated
    source_channel: Mapped[str] = mapped_column(
        String(20), nullable=False, default="portal"
    )

    # Journey engine result
    matched_journey_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("retention_journeys.id", ondelete="SET NULL"),
        nullable=True
    )
    matched_offer_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("retention_offers.id", ondelete="SET NULL"),
        nullable=True
    )

    # Current state of this cancel event
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="pending"
    )
    # pending → offer_shown → accepted / rejected / expired / cancelled_proceeds

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        Index("ix_cancel_events_tenant_status", "tenant_id", "status"),
        Index("ix_cancel_events_customer", "customer_id", "created_at"),
    )


# ---------------------------------------------------------------------------
# Journey Outcomes — tracks what happened for ML feedback
# ---------------------------------------------------------------------------

class JourneyOutcome(JourneyBase):
    __tablename__ = "journey_outcomes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )

    cancel_event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cancel_events.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    journey_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("retention_journeys.id", ondelete="SET NULL"),
        nullable=True
    )
    offer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("retention_offers.id", ondelete="SET NULL"),
        nullable=True
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )

    # What was the outcome?
    # accepted — customer took the offer
    # rejected — customer declined and proceeded with cancel
    # expired — offer timed out (customer didn't respond)
    # bypassed — customer skipped the offer screen
    outcome: Mapped[str] = mapped_column(String(20), nullable=False)

    # Revenue impact
    monthly_revenue_before: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    monthly_revenue_after: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(12, 2), nullable=True
    )
    discount_cost_zar: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00")
    )

    # ML feedback — predicted retention flags
    # Did the customer actually stay for 90+ days after accepting?
    retained_90d: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    retained_180d: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)

    # Batch-job verified retention flags (ground truth)
    actual_retained_90d: Mapped[Optional[bool]] = mapped_column(
        Boolean, nullable=True,
        comment="Verified by batch job: customer still active 90 days after outcome",
    )
    actual_retained_180d: Mapped[Optional[bool]] = mapped_column(
        Boolean, nullable=True,
        comment="Verified by batch job: customer still active 180 days after outcome",
    )
    # Retention rate for this record (1.0 = fully retained, 0.0 = churned)
    retention_rate: Mapped[Optional[float]] = mapped_column(
        Numeric(5, 4), nullable=True,
        comment="Computed retention rate: 1.0 if retained_180d, 0.5 if retained_90d only, 0.0 if churned",
    )

    # Features at time of decision (snapshot for training)
    customer_features: Mapped[dict] = mapped_column(JSONB, nullable=False)

    # Time taken to respond (seconds from offer shown to decision)
    response_time_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index("ix_outcomes_tenant_outcome", "tenant_id", "outcome"),
        Index("ix_outcomes_journey", "journey_id"),
        Index("ix_outcomes_offer", "offer_id"),
        Index("ix_outcomes_customer", "customer_id"),
        Index("ix_outcomes_actual_retained_90d", "actual_retained_90d"),
        Index("ix_outcomes_actual_retained_180d", "actual_retained_180d"),
    )


# ---------------------------------------------------------------------------
# Customer Snapshot — CRM synced customer state for rule evaluation
# ---------------------------------------------------------------------------

class CustomerSnapshot(JourneyBase):
    __tablename__ = "customer_snapshots"

    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    account_number: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True
    )
    snapshot_data: Mapped[dict] = mapped_column(
        JSONB, nullable=False
    )
    source_event: Mapped[str] = mapped_column(
        String(50), nullable=False, default="status_change"
    )
    crm_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

