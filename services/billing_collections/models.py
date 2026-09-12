"""Billing Collections service — the full financial collection journey for ISP billing.

Owns tables:
  - debit_order_mandates: customer bank mandates for debit orders & stop orders
  - eft_payments: electronic fund transfer tracking
  - billing_batch_runs: scheduled/adhoc billing batch execution
  - invoice_movements: audit trail of every invoice status change
  - network_provisioning_queue: provisioning triggers from billing events
  - product_movements: hardware/product assignment lifecycle events
  - reference_cleanups: reference number normalization log
  - collection_events: unified collection activity feed

Port: 8023
"""

import uuid
from datetime import datetime, date
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean, Date, DateTime, Enum as SAEnum, ForeignKey,
    Index, Integer, Numeric, String, Text, UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from services.common.db import register_tenant_scoped_base


# ════════════════════════════════════════════════════════════════════════
# ENUMS
# ════════════════════════════════════════════════════════════════════════

MANDATE_TYPE = SAEnum(
    "debit_order", "stop_order",
    name="mandate_type", create_type=True,
)

MANDATE_STATUS = SAEnum(
    "pending_signature", "active", "suspended", "cancelled", "expired",
    name="mandate_status", create_type=True,
)

INSTRUMENT_TYPE = SAEnum(
    "debit_order", "stop_order", "eft", "card", "cash",
    name="instrument_type", create_type=True,
)

BATCH_FREQUENCY = SAEnum(
    "daily", "weekly", "monthly", "adhoc",
    name="batch_frequency", create_type=True,
)

BATCH_STATUS = SAEnum(
    "scheduled", "running", "completed", "failed", "cancelled",
    name="batch_status", create_type=True,
)

BATCH_RUN_TYPE = SAEnum(
    "initial", "rerun", "reversal", "adhoc",
    name="batch_run_type", create_type=True,
)

PROVISIONING_ACTION = SAEnum(
    "activate", "suspend", "unsuspend", "cancel", "upgrade", "downgrade", "move",
    name="provisioning_action", create_type=True,
)

PROVISIONING_STATUS = SAEnum(
    "pending", "in_progress", "completed", "failed", "retrying", "cancelled",
    name="provisioning_status", create_type=True,
)

PRODUCT_MOVEMENT_TYPE = SAEnum(
    "assigned", "delivered", "installed", "returned", "swapped", "recovered",
    name="product_movement_type", create_type=True,
)

PRODUCT_CONDITION = SAEnum(
    "new", "good", "fair", "damaged", "dead_on_arrival", "missing_parts",
    name="product_condition", create_type=True,
)


# ════════════════════════════════════════════════════════════════════════
# BASE
# ════════════════════════════════════════════════════════════════════════

class Base(DeclarativeBase):
    pass


# Every model below carries tenant_id; opt this Base into the automatic
# tenant filter in services.common.db so a missed manual .where() clause
# can no longer leak rows across tenants.
register_tenant_scoped_base(Base)


# ════════════════════════════════════════════════════════════════════════
# 1. SUBSCRIPTION PAYMENT METHODS (extends billing subscriptions)
# ════════════════════════════════════════════════════════════════════════

class SubscriptionPaymentMethod(Base):
    """Links a subscription to its payment instrument(s).
    
    A subscription can have multiple payment methods (primary + fallback).
    Supports debit order, stop order, EFT, and card.
    """
    __tablename__ = "subscription_payment_methods"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    subscription_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)

    # Payment instrument
    instrument_type: Mapped[str] = mapped_column(INSTRUMENT_TYPE, nullable=False, default="debit_order")
    mandate_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)  # FK to debit_order_mandates
    payment_method_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)  # FK to customer_journey.payment_methods

    # Priority
    priority: Mapped[int] = mapped_column(Integer, default=1)  # 1=primary, 2=fallback
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Restrictions
    max_debit_amount_zar: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)  # cap per debit
    allowed_debit_days: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True, default=list)  # e.g. [1, 15, 25]

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_sub_pm_tenant_customer", "tenant_id", "customer_id"),
        Index("ix_sub_pm_subscription", "subscription_id"),
        Index("ix_sub_pm_active", "tenant_id", "is_active"),
    )


# ════════════════════════════════════════════════════════════════════════
# 2. DEBIT ORDER / STOP ORDER MANDATES
# ════════════════════════════════════════════════════════════════════════

class DebitOrderMandate(Base):
    """Customer bank account mandate for debit orders and stop orders.
    
    Debit order: variable amount, bank-initiated collection.
    Stop order: fixed amount, customer-initiated standing instruction.
    """
    __tablename__ = "debit_order_mandates"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    account_number: Mapped[str] = mapped_column(String(50), nullable=False)

    # Mandate type
    mandate_type: Mapped[str] = mapped_column(MANDATE_TYPE, nullable=False, default="debit_order")

    # Bank details
    bank_name: Mapped[str] = mapped_column(String(100), nullable=True)
    branch_code: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    branch_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    account_holder: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    account_number_bank: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    account_type: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # cheque, savings, transmission

    # NACHA/NAEDO tracking
    nedbank_mandate_ref: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    universal_mandate_code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    naco_period_code: Mapped[Optional[str]] = mapped_column(String(5), nullable=True)  # M=monthly, W=weekly

    # Debit scheduling
    debit_day: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 1-31
    first_debit_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    last_debit_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    fixed_amount_zar: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    max_amount_zar: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)  # for variable debit orders

    # NAEDO tracking (New Early Debit Order)
    is_notedo: Mapped[bool] = mapped_column(Boolean, default=True)
    response_day_1: Mapped[Optional[date]] = mapped_column(Date, nullable=True)  # first response (approved/declined)
    response_day_2: Mapped[Optional[date]] = mapped_column(Date, nullable=True)  # second response (if day 1 declined)

    # Status
    status: Mapped[str] = mapped_column(MANDATE_STATUS, nullable=False, default="pending_signature")
    signature_method: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # digital, paper, voice
    signature_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    cancellation_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Metadata
    external_reference: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_mandate_tenant_customer", "tenant_id", "customer_id"),
        Index("ix_mandate_tenant_status", "tenant_id", "status"),
        Index("ix_mandate_account", "account_number"),
        Index("ix_mandate_type_status", "mandate_type", "status"),
        Index("ix_mandate_debit_day", "debit_day"),
        Index("ix_mandate_nedbank_ref", "nedbank_mandate_ref"),
    )


# ════════════════════════════════════════════════════════════════════════
# 3. EFT PAYMENTS
# ════════════════════════════════════════════════════════════════════════

class EFTPayment(Base):
    """Electronic Fund Transfer — bank deposit / manual payment tracking."""
    __tablename__ = "eft_payments"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    account_number: Mapped[str] = mapped_column(String(50), nullable=False)

    # Payment details
    amount_zar: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    bank_reference: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    customer_reference: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)  # cleaned reference

    # Bank info
    bank_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    branch_code: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)

    # Matching
    matched_invoice_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    matched_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    matched_by: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)  # user ID

    # Status
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="unmatched")
    # unmatched, matched, partially_matched, unmatched_returned

    # Dates
    payment_date: Mapped[date] = mapped_column(Date, nullable=False)
    received_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Notes
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_eft_tenant_customer", "tenant_id", "customer_id"),
        Index("ix_eft_tenant_status", "tenant_id", "status"),
        Index("ix_eft_reference", "bank_reference"),
        Index("ix_eft_cust_reference", "customer_reference"),
        Index("ix_eft_payment_date", "payment_date"),
        Index("ix_eft_matched_invoice", "matched_invoice_id"),
    )


# ════════════════════════════════════════════════════════════════════════
# 4. REFERENCE NUMBER CLEANING
# ════════════════════════════════════════════════════════════════════════

class ReferenceCleanup(Base):
    """Log of reference number normalization / cleaning operations.
    
    Bank references are often messy (spaces, dashes, prefixes, etc.).
    This table tracks every cleaning action for audit purposes.
    """
    __tablename__ = "reference_cleanups"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)

    # Source
    eft_payment_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    invoice_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)

    # Cleaning details
    original_reference: Mapped[str] = mapped_column(String(200), nullable=False)
    cleaned_reference: Mapped[str] = mapped_column(String(200), nullable=False)
    cleaning_method: Mapped[str] = mapped_column(String(50), nullable=False)
    # strip_spaces, strip_prefix, remove_dashes, account_number_extract, regex_match, manual

    # Match result
    matched_customer_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    matched_account_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    match_confidence: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # high, medium, low, none
    auto_matched: Mapped[bool] = mapped_column(Boolean, default=False)

    # Audit
    cleaned_by: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    cleaned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_ref_cleanup_tenant", "tenant_id", "cleaned_at"),
        Index("ix_ref_cleanup_eft", "eft_payment_id"),
        Index("ix_ref_cleanup_original", "original_reference"),
        Index("ix_ref_cleanup_cleaned", "cleaned_reference"),
        Index("ix_ref_cleanup_customer", "matched_customer_id"),
    )


# ════════════════════════════════════════════════════════════════════════
# 5. BILLING BATCH RUNS
# ════════════════════════════════════════════════════════════════════════

class BillingBatchRun(Base):
    """Billing batch execution log.
    
    Supports different date billing batch runs (e.g., 1st, 15th, 25th of month).
    Each run captures which subscriptions were processed, success/failure counts.
    """
    __tablename__ = "billing_batch_runs"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)

    # Run identification
    batch_code: Mapped[str] = mapped_column(String(50), nullable=False)  # BATCH-2026-06-01-BATCH-1
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Batch configuration
    frequency: Mapped[str] = mapped_column(BATCH_FREQUENCY, nullable=False, default="monthly")
    run_type: Mapped[str] = mapped_column(BATCH_RUN_TYPE, nullable=False, default="initial")
    billing_day: Mapped[int] = mapped_column(Integer, nullable=False, default=1)  # 1-31

    # Date targets
    billing_period_start: Mapped[date] = mapped_column(Date, nullable=False)
    billing_period_end: Mapped[date] = mapped_column(Date, nullable=False)
    debit_date: Mapped[date] = mapped_column(Date, nullable=False)

    # Subscription filters
    payment_instruments: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True, default=list)  # ["debit_order", "stop_order", "eft"]
    subscription_segments: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True, default=list)  # ["residential", "business"]

    # Status
    status: Mapped[str] = mapped_column(BATCH_STATUS, nullable=False, default="scheduled")

    # Counts
    total_subscriptions: Mapped[int] = mapped_column(Integer, default=0)
    total_invoices_generated: Mapped[int] = mapped_column(Integer, default=0)
    total_amount_zar: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"))
    successful_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, default=0)

    # Execution
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    triggered_by: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)  # user who triggered
    error_log: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Output
    s3_report_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_batch_tenant_status", "tenant_id", "status"),
        Index("ix_batch_tenant_period", "tenant_id", "billing_period_start"),
        Index("ix_batch_debit_date", "debit_date"),
        Index("ix_batch_code", "batch_code", unique=True),
    )


class BillingBatchItem(Base):
    """Individual subscription processed within a batch run."""
    __tablename__ = "billing_batch_items"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    batch_run_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("billing_batch_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)

    # Target
    customer_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    subscription_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    account_number: Mapped[str] = mapped_column(String(50), nullable=False)

    # Processing
    payment_instrument: Mapped[str] = mapped_column(String(20), nullable=False)  # debit_order, stop_order, eft
    amount_zar: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    # Result
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    # pending, processed, failed, skipped
    invoice_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    mandate_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_batch_item_batch", "batch_run_id"),
        Index("ix_batch_item_customer", "tenant_id", "customer_id"),
        Index("ix_batch_item_status", "status"),
    )


# ════════════════════════════════════════════════════════════════════════
# 6. INVOICE STATUS MOVEMENT (audit trail)
# ════════════════════════════════════════════════════════════════════════

class InvoiceMovement(Base):
    """Every invoice status change is logged here for full audit trail.
    
    Captures: who changed it, from what status, to what status, when, and why.
    """
    __tablename__ = "invoice_movements"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    invoice_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)

    # Movement details
    action: Mapped[str] = mapped_column(String(30), nullable=False)
    # generated, sent, viewed, paid, partially_paid, payment_failed,
    # dunning_email, dunning_sms, dunning_call, suspended, unsuspended,
    # sent_to_collections, credit_note_issued, written_off, voided, disputed,
    # cancelled, refunded

    from_status: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    to_status: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)

    # Financial impact
    amount_zar: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    payment_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    credit_note_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)

    # Context
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    # batch_run, manual, system, payment_gateway, dunning_workflow, collection_agent

    # Actor
    actor_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    actor_type: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # user, system, batch

    # External references
    external_reference: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_inv_move_tenant", "tenant_id", "created_at"),
        Index("ix_inv_move_invoice", "invoice_id", "created_at"),
        Index("ix_inv_move_action", "tenant_id", "action"),
        Index("ix_inv_move_actor", "actor_id"),
        Index("ix_inv_move_source", "source"),
    )


# ════════════════════════════════════════════════════════════════════════
# 7. NETWORK PROVISIONING QUEUE
# ════════════════════════════════════════════════════════════════════════

class NetworkProvisioningQueue(Base):
    """Network provisioning triggered by billing events.
    
    When an order is paid, when a cancellation completes, when a customer
    upgrades/downgrades — these trigger provisioning actions on the FNO network.
    """
    __tablename__ = "network_provisioning_queue"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    subscription_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)

    # Trigger
    action: Mapped[str] = mapped_column(PROVISIONING_ACTION, nullable=False)
    trigger_source: Mapped[str] = mapped_column(String(30), nullable=False)
    # order_paid, subscription_activated, subscription_cancelled,
    # upgrade, downgrade, move_house, fault_repaired, manual

    # Related entities
    order_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    technician_visit_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)

    # Network details
    fno_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    circuit_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    ont_serial: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    service_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # FNO service reference

    # Package
    old_package: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    new_package: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    old_speed_mbps: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    new_speed_mbps: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Status
    status: Mapped[str] = mapped_column(PROVISIONING_STATUS, nullable=False, default="pending")
    priority: Mapped[int] = mapped_column(Integer, default=5)  # 1=highest, 10=lowest
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, default=3)

    # Execution
    scheduled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # External
    fno_reference: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    fno_response: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_prov_tenant_status", "tenant_id", "status"),
        Index("ix_prov_customer", "tenant_id", "customer_id"),
        Index("ix_prov_subscription", "subscription_id"),
        Index("ix_prov_fno_circuit", "fno_name", "circuit_id"),
        Index("ix_prov_scheduled", "scheduled_at"),
        Index("ix_prov_action_status", "action", "status"),
    )


# ════════════════════════════════════════════════════════════════════════
# 8. PRODUCT MOVEMENT (hardware lifecycle)
# ════════════════════════════════════════════════════════════════════════

class ProductMovement(Base):
    """Hardware/product assignment and lifecycle tracking.
    
    Tracks every ONT/router/device movement from warehouse → customer → return.
    """
    __tablename__ = "product_movements"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)

    # Product
    product_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("inventory_products.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    product_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    serial_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    imei: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    asset_tag: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Movement details
    movement_type: Mapped[str] = mapped_column(PRODUCT_MOVEMENT_TYPE, nullable=False)
    from_location: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    to_location: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    from_status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    to_status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Condition
    condition: Mapped[Optional[str]] = mapped_column(PRODUCT_CONDITION, nullable=True)
    condition_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Related entities
    order_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("orders.id", ondelete="SET NULL"), nullable=True
    )
    delivery_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    technician_visit_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("technician_visits.id", ondelete="SET NULL"), nullable=True
    )
    return_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)

    # Financial
    unit_cost_zar: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    current_value_zar: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    depreciation_zar: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)

    # Tracking
    courier: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    tracking_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Actor
    performed_by: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    performed_by_type: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_prod_move_tenant", "tenant_id", "created_at"),
        Index("ix_prod_move_customer", "tenant_id", "customer_id"),
        Index("ix_prod_move_product", "product_id"),
        Index("ix_prod_move_serial", "serial_number"),
        Index("ix_prod_move_type", "movement_type"),
        Index("ix_prod_move_order", "order_id"),
    )


# ════════════════════════════════════════════════════════════════════════
# 9. COLLECTION EVENTS (unified feed)
# ════════════════════════════════════════════════════════════════════════

class CollectionEvent(Base):
    """Unified collection activity feed — every billing/collection event in one place."""
    __tablename__ = "collection_events"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    account_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Event
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # invoice_generated, debit_order_submitted, debit_order_failed, debit_order_success,
    # stop_order_failed, payment_received, payment_matched, payment_unmatched,
    # dunning_email_sent, dunning_sms_sent, service_suspended, service_unsuspended,
    # sent_to_collections, arrangement_created, arrangement_defaulted,
    # credit_note_issued, refund_processed

    severity: Mapped[str] = mapped_column(String(20), default="info")  # info, warning, critical

    # Content
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # Financial
    amount_zar: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="ZAR")

    # Related
    invoice_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    payment_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    batch_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)

    # Actor
    source: Mapped[str] = mapped_column(String(30), nullable=False)  # billing, batch, payment_gateway, manual
    actor_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_coll_event_tenant_customer", "tenant_id", "customer_id", "created_at"),
        Index("ix_coll_event_type", "tenant_id", "event_type"),
        Index("ix_coll_event_severity", "tenant_id", "severity"),
        Index("ix_coll_event_created", "tenant_id", "created_at"),
    )


# ════════════════════════════════════════════════════════════════════════
# FNO BROWSER AUTOMATION
# ════════════════════════════════════════════════════════════════════════

FNO_PORTAL = SAEnum(
    "vumatel_active", "vumatel_passive", "openserve", "frogfoot", "octotel", "other",
    name="fno_portal", create_type=True,
)

AUTOMATION_STATUS = SAEnum(
    "queued", "running", "waiting_captcha", "waiting_2fa", "completed",
    "failed", "retrying", "cancelled", "manual_intervention",
    name="automation_status", create_type=True,
)

AUTOMATION_ACTION = SAEnum(
    "login", "navigate", "fill_form", "submit", "screenshot", "extract_data",
    "click", "wait", "scroll", "download", "upload",
    name="automation_action", create_type=True,
)


class FNOAutomationJob(Base):
    """Browser automation job for FNO portal interactions.
    
    Tracks the full lifecycle of an automated browser session
    interacting with an FNO portal (Vumatel, Openserve, etc.)
    for cancellations, provisioning, or data extraction.
    """
    __tablename__ = "fno_automation_jobs"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)

    # FNO details
    fno_name: Mapped[str] = mapped_column(String(100), nullable=False)
    fno_portal: Mapped[str] = mapped_column(FNO_PORTAL, nullable=False)
    fno_account_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    fno_reference: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Related entity
    cancellation_request_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    provisioning_queue_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)

    # Automation details
    action_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # cancellation, provisioning, status_check, data_extraction
    status: Mapped[str] = mapped_column(AUTOMATION_STATUS, nullable=False, default="queued")

    # Browser session
    browser_session_id: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    browser_profile: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    # chrome, firefox, headless_chrome

    # Portal credentials (encrypted reference only)
    credential_vault_key: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    # Execution
    priority: Mapped[int] = mapped_column(Integer, default=5)
    scheduled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Retry
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, default=3)
    next_retry_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Result
    result_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    confirmation_number: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_screenshot_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Screenshots
    screenshot_paths: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True, default=list)

    # Manual intervention
    requires_manual: Mapped[bool] = mapped_column(Boolean, default=False)
    manual_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    assigned_to: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_fno_auto_tenant_status", "tenant_id", "status"),
        Index("ix_fno_auto_fno", "fno_name", "fno_portal"),
        Index("ix_fno_auto_customer", "tenant_id", "customer_id"),
        Index("ix_fno_auto_cancellation", "cancellation_request_id"),
        Index("ix_fno_auto_scheduled", "scheduled_at"),
        Index("ix_fno_auto_priority", "priority", "status"),
    )


class FNOAutomationStep(Base):
    """Individual step within an automation job."""
    __tablename__ = "fno_automation_steps"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("fno_automation_jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)

    step_number: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(AUTOMATION_ACTION, nullable=False)

    # Target
    target_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    target_selector: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    target_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Result
    status: Mapped[str] = mapped_column(String(20), default="pending")
    # pending, running, completed, failed, skipped
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    screenshot_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    extracted_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # Timing
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_fno_step_job", "job_id", "step_number"),
    )


class FNOAutomationTemplate(Base):
    """Reusable automation template for common FNO portal workflows."""
    __tablename__ = "fno_automation_templates"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    fno_portal: Mapped[str] = mapped_column(FNO_PORTAL, nullable=False)
    action_type: Mapped[str] = mapped_column(String(50), nullable=False)

    # Template steps (JSON array of step definitions)
    steps_template: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    # Each step: {"action": "login", "target_url": "...", "target_selector": "...", "target_value": "..."}

    # Selectors (CSS/XPath for portal elements)
    selectors: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True, default=dict)
    # e.g. {"username_field": "#username", "password_field": "#password", "login_button": "button[type=submit]"}

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    success_rate: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2), nullable=True)
    total_runs: Mapped[int] = mapped_column(Integer, default=0)
    successful_runs: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_fno_template_portal", "fno_portal", "action_type"),
        Index("ix_fno_template_active", "tenant_id", "is_active"),
    )


class FNOBrowserSession(Base):
    """Active browser session for FNO portal automation."""
    __tablename__ = "fno_browser_sessions"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)

    # Session
    session_id: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    fno_portal: Mapped[str] = mapped_column(FNO_PORTAL, nullable=False)
    browser_type: Mapped[str] = mapped_column(String(50), default="headless_chrome")

    # Status
    status: Mapped[str] = mapped_column(String(20), default="active")
    # active, idle, closed, error

    # Current page
    current_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    current_page_title: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)

    # Linked job
    active_job_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)

    # Timing
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_activity_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_fno_session_tenant", "tenant_id", "status"),
        Index("ix_fno_session_active_job", "active_job_id"),
    )
