"""Early-termination / claw-back fee engine tables.

fee_policies             versioned, per-tenant policy (config JSON validated by fee_policies.PolicyIn).
                         Rows are immutable apart from effective_to / superseded_by / is_active:
                         editing a policy inserts a new version.
contract_fee_snapshots   immutable record of what a customer's contract cost to set up, written when the
                         subscription starts (or backfilled). Later price changes never touch it.
fee_calculations         immutable result of one engine run (inputs, hash, full breakdown). Only the
                         waiver / invoice / supersede bookkeeping columns ever change.
fee_audit_events         append-only audit trail for every state change above.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from services.billing.models import Base


class FeePolicy(Base):
    __tablename__ = "fee_policies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    policy_key: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, default=uuid.uuid4)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    superseded_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    trigger_types: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    applies_to_plans: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)  # plan ids or names; [] = all
    term_months: Mapped[int] = mapped_column(Integer, nullable=False, default=24)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_fee_policies_tenant_active", "tenant_id", "is_active"),
        Index("uq_fee_policies_key_version", "tenant_id", "policy_key", "version", unique=True),
    )


class ContractFeeSnapshot(Base):
    __tablename__ = "contract_fee_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    subscription_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=False)
    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)  # only mutable column
    policy_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    policy_version: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    term_start: Mapped[date] = mapped_column(Date, nullable=False)
    term_months: Mapped[int] = mapped_column(Integer, nullable=False)
    components: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)  # [{code,label,amount,discount}]
    monthly_rental_zar: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    discounts_zar: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    plan_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    plan_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    source: Mapped[str] = mapped_column(String(30), nullable=False, default="manual")  # auto_create|manual|backfill
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("uq_contract_fee_snapshot_version", "tenant_id", "subscription_id", "version", unique=True),
        Index("ix_contract_fee_snapshot_sub", "tenant_id", "subscription_id", "is_current"),
    )


class FeeCalculation(Base):
    __tablename__ = "fee_calculations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    subscription_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    snapshot_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    policy_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    policy_key: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    policy_version: Mapped[int] = mapped_column(Integer, nullable=False)
    trigger: Mapped[str] = mapped_column(String(60), nullable=False)
    subject_type: Mapped[str] = mapped_column(String(30), nullable=False, default="subscription")
    subject_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    cancellation_request_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    termination_fee_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    reason_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    inputs: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    inputs_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    breakdown: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    flags: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    fee_net_zar: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    fee_vat_zar: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    fee_total_zar: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    outstanding_balance_zar: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))

    # Mutable bookkeeping: waivers append, amount_due shrinks, status/invoice/supersede move forward.
    waivers: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    waived_total_zar: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    amount_due_zar: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))  # gross, after waivers
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="calculated")  # calculated|waived|invoiced|superseded
    superseded_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    invoice_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    invoice_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    legacy: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    auto_calculated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("uq_fee_calc_idempotency", "tenant_id", "trigger", "subject_type", "subject_id",
              "effective_date", "inputs_hash", unique=True),
        Index("ix_fee_calc_subject", "tenant_id", "subject_type", "subject_id"),
    )


class FeeAuditEvent(Base):
    __tablename__ = "fee_audit_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    actor_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (Index("ix_fee_audit_entity", "tenant_id", "entity_type", "entity_id"),)
