"""SQLAlchemy models for the Billing service."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

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
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

INVOICE_STATUS = SAEnum(
    "draft", "sent", "paid", "partially_paid", "overdue", "voided",
    name="invoice_status", create_type=True,
)

PAYMENT_METHOD = SAEnum(
    "manual", "eft", "card", "debit_order",
    name="payment_method", create_type=True,
)

PAYMENT_STATUS = SAEnum(
    "pending", "completed", "failed", "refunded",
    name="payment_status", create_type=True,
)

DUNNING_ACTION_TYPE = SAEnum(
    "sms_reminder", "email_warning", "auto_suspend", "send_to_collections",
    name="dunning_action_type", create_type=True,
)

ARRANGEMENT_STATUS = SAEnum(
    "active", "completed", "defaulted", "cancelled",
    name="arrangement_status", create_type=True,
)

SUBSCRIPTION_STATUS = SAEnum(
    "active", "cancelled", "paused", "trial", "expired",
    name="subscription_status", create_type=True,
)

SUBSCRIPTION_BILLING_INTERVAL = SAEnum(
    "monthly", "quarterly", "semi_annual", "annual",
    name="subscription_billing_interval", create_type=True,
)


# ---------------------------------------------------------------------------
# Invoice
# ---------------------------------------------------------------------------

class Invoice(Base):
    __tablename__ = "invoices"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    subscription_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("subscriptions.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Billing account (for company/multi-property billing)
    billing_account_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("billing_accounts.id", ondelete="SET NULL"),
        nullable=True, index=True,
        comment="Links to BillingAccount — the entity responsible for payment"
    )

    # Property reference (which address this invoice is for)
    property_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True,
        comment="Links to CRM Property — the physical address being billed"
    )
    number: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(INVOICE_STATUS, nullable=False, default="draft")
    subtotal_zar: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    vat_zar: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    total_zar: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    amount_paid_zar: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    billing_period_start: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    billing_period_end: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    line_items: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True, default=list)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    credit_note_of: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    payments: Mapped[list["Payment"]] = relationship(back_populates="invoice", cascade="all, delete-orphan")
    dunning_actions: Mapped[list["DunningAction"]] = relationship(back_populates="invoice", cascade="all, delete-orphan")
    subscription: Mapped[Optional["Subscription"]] = relationship(back_populates="invoices")
    line_items: Mapped[list["InvoiceLine"]] = relationship(back_populates="invoice", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_invoices_tenant_status", "tenant_id", "status"),
        Index("ix_invoices_tenant_customer", "tenant_id", "customer_id"),
        Index("ix_invoices_tenant_number", "tenant_id", "number", unique=True),
        Index("ix_invoices_subscription", "subscription_id"),
        Index("ix_invoices_billing_account", "billing_account_id"),
        Index("ix_invoices_property", "property_id"),
    )


# ---------------------------------------------------------------------------
# Invoice Line Item (structured replacement for JSONB line_items)
# ---------------------------------------------------------------------------

class InvoiceLine(Base):
    __tablename__ = "invoice_lines"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)

    # Product reference
    product_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("inventory_products.id", ondelete="SET NULL"), nullable=True
    )
    product_sku: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    product_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Line details
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    unit_price_zar: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    discount_zar: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    vat_zar: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    total_zar: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    # Line type
    line_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="plan"
    )  # plan, hardware, installation, delivery, vas, discount

    # Period (for recurring charges)
    period_start: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    period_end: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    invoice: Mapped["Invoice"] = relationship(back_populates="line_items")

    __table_args__ = (
        Index("ix_invoice_lines_tenant", "tenant_id"),
        Index("ix_invoice_lines_product", "product_id"),
        Index("ix_invoice_lines_type", "tenant_id", "line_type"),
    )


# ---------------------------------------------------------------------------
# Invoice Sequence (for per-tenant sequential numbering)
# ---------------------------------------------------------------------------

class InvoiceSequence(Base):
    __tablename__ = "invoice_sequences"

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    last_number: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


# ---------------------------------------------------------------------------
# Billing Account (top-level billing entity)
# ---------------------------------------------------------------------------

class BillingAccount(Base):
    """Top-level billing entity that groups subscriptions and invoices.

    A BillingAccount can be owned by either:
    - A customer (individual or household)
    - A company (corporate account paying for employees)

    This decouples billing from the CRM Customer model, allowing:
    - Company billing: one BillingAccount for the company, with subscriptions
      for multiple employees at multiple properties
    - Multiple properties: one BillingAccount per customer, with subscriptions
      at different addresses
    - Account handover: BillingAccount transfers from one customer to another
      at the same property without losing billing history
    """
    __tablename__ = "billing_accounts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)

    # Ownership — exactly one of these should be set
    customer_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True,
        comment="Individual customer owner (mutually exclusive with company_id)"
    )
    company_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True,
        comment="Company owner for corporate billing (mutually exclusive with customer_id)"
    )

    # Display
    account_number: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    account_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    # "John Smith", "Acme Corp - Employee Accounts"

    # Billing settings
    billing_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    payment_method: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    payment_terms: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    # "Net 30", "Net 60", "Monthly in advance"
    credit_limit_zar: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2), nullable=True)
    auto_debit: Mapped[bool] = mapped_column(Boolean, default=False)

    # Status
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active"
    )
    # active, suspended, closed, collections

    # Dunning
    dunning_stage: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    # "none", "reminder", "warning", "pre_legal", "legal"
    last_dunning_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Metadata
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_billing_accounts_tenant", "tenant_id"),
        Index("ix_billing_accounts_tenant_customer", "tenant_id", "customer_id"),
        Index("ix_billing_accounts_tenant_company", "tenant_id", "company_id"),
        Index("ix_billing_accounts_tenant_status", "tenant_id", "status"),
        Index("ix_billing_accounts_number", "tenant_id", "account_number", unique=True),
    )


# ---------------------------------------------------------------------------
# Payment
# ---------------------------------------------------------------------------

class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    amount_zar: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    method: Mapped[str] = mapped_column(PAYMENT_METHOD, nullable=False)
    reference: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    paystack_ref: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(PAYMENT_STATUS, nullable=False, default="pending")
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    invoice: Mapped["Invoice"] = relationship(back_populates="payments")

    __table_args__ = (
        Index("ix_payments_tenant_customer", "tenant_id", "customer_id"),
    )


# ---------------------------------------------------------------------------
# Dunning Action
# ---------------------------------------------------------------------------

class DunningAction(Base):
    __tablename__ = "dunning_actions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    action_type: Mapped[str] = mapped_column(DUNNING_ACTION_TYPE, nullable=False)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    executed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    result: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    invoice: Mapped["Invoice"] = relationship(back_populates="dunning_actions")


# ---------------------------------------------------------------------------
# Payment Arrangement (collections)
# ---------------------------------------------------------------------------

class PaymentArrangement(Base):
    __tablename__ = "payment_arrangements"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    total_owed_zar: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    installment_zar: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    installments_count: Mapped[int] = mapped_column(Integer, nullable=False)
    installments_paid: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(ARRANGEMENT_STATUS, nullable=False, default="active")
    next_due_date: Mapped[date] = mapped_column(Date, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


# ---------------------------------------------------------------------------
# Subscription
# ---------------------------------------------------------------------------

class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)

    # Billing account (replaces direct customer billing for company/multi-property)
    billing_account_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("billing_accounts.id", ondelete="SET NULL"),
        nullable=True, index=True,
        comment="Links to BillingAccount for company/multi-property billing"
    )

    # Property reference (which address this subscription serves)
    property_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True,
        comment="Links to CRM Property — the physical address being serviced"
    )
    plan_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("plans.id", ondelete="SET NULL"), nullable=True
    )
    segment: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(SUBSCRIPTION_STATUS, nullable=False, default="active")
    billing_interval: Mapped[str] = mapped_column(
        SUBSCRIPTION_BILLING_INTERVAL, nullable=False, default="monthly"
    )
    base_price_zar: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    segment_pricing: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSONB, nullable=True, default=dict,
        comment="Per-segment price overrides, e.g. {'Enterprise': 1299.99, 'Premium': 899.99}",
    )
    billing_anchor: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)
    current_period_start: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    current_period_end: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    trial_ends_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    metadata_: Mapped[Optional[dict[str, Any]]] = mapped_column("metadata", JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    invoices: Mapped[list["Invoice"]] = relationship(back_populates="subscription")
    usage_records: Mapped[list["SubscriptionUsage"]] = relationship(back_populates="subscription", cascade="all, delete-orphan")
    billing_account: Mapped[Optional["BillingAccount"]] = relationship("BillingAccount")

    __table_args__ = (
        Index("ix_subscriptions_tenant_customer", "tenant_id", "customer_id"),
        Index("ix_subscriptions_tenant_status", "tenant_id", "status"),
        Index("ix_subscriptions_tenant_plan", "tenant_id", "plan"),
        Index("ix_subscriptions_plan_id", "plan_id"),
        Index("ix_subscriptions_billing_account", "billing_account_id"),
        Index("ix_subscriptions_property", "property_id"),
    )

    def get_segment_price(self, segment: str, base_price: Decimal) -> Decimal:
        """Return the price for a given segment, falling back to base_price."""
        if self.segment_pricing and segment in self.segment_pricing:
            return Decimal(str(self.segment_pricing[segment]))
        return base_price

    def is_in_trial(self) -> bool:
        """Return True if the subscription is still within its trial period."""
        if self.trial_ends_at is None:
            return False
        from datetime import timezone
        return datetime.now(tz=timezone.utc) < self.trial_ends_at

    def get_interval_months(self) -> int:
        """Return the number of months for the billing interval."""
        return {
            "monthly": 1,
            "quarterly": 3,
            "semi_annual": 6,
            "annual": 12,
        }.get(self.billing_interval, 1)


# ---------------------------------------------------------------------------
# Subscription Usage (usage-based billing)
# ---------------------------------------------------------------------------

class SubscriptionUsage(Base):
    __tablename__ = "subscription_usage"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    subscription_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    metric: Mapped[str] = mapped_column(String(100), nullable=False,
        comment="e.g. 'gb_overage', 'api_calls', 'devices'")
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False, default=Decimal("0.00"))
    unit_price_zar: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False, default=Decimal("0.0000"))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    billed_invoice_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="SET NULL"), nullable=True
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    subscription: Mapped["Subscription"] = relationship(back_populates="usage_records")

    __table_args__ = (
        Index("ix_subscription_usage_metric", "subscription_id", "metric"),
        Index("ix_subscription_usage_unbilled", "subscription_id", "billed_invoice_id"),
    )


# ---------------------------------------------------------------------------
# Subscription Transfer (tenant-to-tenant handover)
# ---------------------------------------------------------------------------

TRANSFER_STATUS = SAEnum(
    "pending", "in_progress", "approved", "completed", "cancelled", "disputed",
    name="transfer_status", create_type=True,
)

TRANSFER_TRIGGER = SAEnum(
    "tenant_move_out",      # Tenant leaving, new tenant moving in
    "lease_renewal",        # Same tenant, new lease term
    "owner_take_back",      # Owner reclaiming property
    "new_tenant",           # New tenant, no previous tenant
    "account_correction",   # Admin correction
    name="transfer_trigger", create_type=True,
)


class SubscriptionTransfer(Base):
    """Tracks the transfer of a subscription from one customer to another at a property.

    This is the billing-side counterpart to CRM's AccountHandover. It handles:
    - Prorated billing for the outgoing tenant (final invoice)
    - Prorated billing for the incoming tenant (first invoice)
    - Equipment transfer or return
    - Deposit transfer between tenants
    - Service continuity (no gap in service)

    Unlike cancellation + new signup, a transfer:
    - Preserves the subscription ID and service history
    - Keeps the same property/installation
    - Avoids re-installation costs
    - Maintains the FNO service reference
    """
    __tablename__ = "subscription_transfers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)

    # The subscription being transferred
    subscription_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("subscriptions.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    # Property reference
    property_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True,
        comment="Links to CRM Property"
    )

    # From / To customers
    from_customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True,
        comment="Outgoing customer (FK to CRM customers.id)"
    )
    to_customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True,
        comment="Incoming customer (FK to CRM customers.id)"
    )

    # Billing accounts
    from_billing_account_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("billing_accounts.id", ondelete="SET NULL"), nullable=True
    )
    to_billing_account_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("billing_accounts.id", ondelete="SET NULL"), nullable=True
    )

    # Transfer details
    status: Mapped[str] = mapped_column(TRANSFER_STATUS, nullable=False, default="pending")
    trigger: Mapped[str] = mapped_column(TRANSFER_TRIGGER, nullable=False, default="tenant_move_out")

    # Proration
    transfer_date: Mapped[date] = mapped_column(Date, nullable=False)
    # The date when the transfer takes effect
    from_prorated_amount_zar: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00"),
        comment="Final prorated charge for outgoing tenant"
    )
    to_prorated_amount_zar: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00"),
        comment="First prorated charge for incoming tenant"
    )

    # Equipment handling
    equipment_transfers: Mapped[bool] = mapped_column(Boolean, default=True)
    # If True, ONT/router stays (typical for fibre)
    # If False, equipment is returned (typical for LTE)
    equipment_condition: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    equipment_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Financial settlement
    deposit_transfer_zar: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    outstanding_balance_zar: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00"),
        comment="Outstanding balance settled before transfer"
    )
    settlement_invoice_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="SET NULL"), nullable=True,
        comment="Final invoice for outgoing tenant"
    )

    # FNO continuity
    fno_service_reference: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    # Preserved across transfer to avoid FNO re-provisioning

    # Actor
    initiated_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    initiated_by_type: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    # customer, landlord, agent, admin

    # Dates
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_sub_transfer_tenant_status", "tenant_id", "status"),
        Index("ix_sub_transfer_subscription", "subscription_id"),
        Index("ix_sub_transfer_from", "from_customer_id"),
        Index("ix_sub_transfer_to", "to_customer_id"),
        Index("ix_sub_transfer_property", "property_id"),
        Index("ix_sub_transfer_date", "transfer_date"),
    )

# ---------------------------------------------------------------------------
# Cancellation Request
# ---------------------------------------------------------------------------

CANCEL_TYPE = SAEnum(
    "voluntary", "move_house", "debt_collection", "death", "other",
    name="cancel_type", create_type=True,
)

CANCEL_STATUS = SAEnum(
    "pending", "retention_offered", "retention_accepted", "retention_rejected",
    "fno_submitted", "fno_confirmed", "completed", "cancelled",
    name="cancel_status", create_type=True,
)


class CancellationRequest(Base):
    __tablename__ = "cancellation_requests"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    subscription_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("subscriptions.id", ondelete="SET NULL"), nullable=True)
    account_number: Mapped[str] = mapped_column(String(50), nullable=False)

    cancel_type: Mapped[str] = mapped_column(CANCEL_TYPE, nullable=False, default="voluntary")
    cancel_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cancel_reason_detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Status tracking
    status: Mapped[str] = mapped_column(CANCEL_STATUS, nullable=False, default="pending")

    # Retention
    retention_offer_shown: Mapped[bool] = mapped_column(Boolean, default=False)
    retention_offer_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    retention_accepted: Mapped[bool] = mapped_column(Boolean, default=False)

    # FNO
    fno_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    fno_cancellation_ref: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    fno_cancelled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Effective date
    effective_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_cancellation_tenant_status", "tenant_id", "status"),
        Index("ix_cancellation_customer", "customer_id", "created_at"),
    )


# ---------------------------------------------------------------------------
# Termination Fee Calculation
# ---------------------------------------------------------------------------

class TerminationFee(Base):
    __tablename__ = "termination_fees"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    cancellation_request_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cancellation_requests.id", ondelete="CASCADE"), nullable=False)
    subscription_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("subscriptions.id", ondelete="SET NULL"), nullable=True)

    # Contract details at time of cancellation
    monthly_rate_zar: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    remaining_months: Mapped[int] = mapped_column(Integer, nullable=False)
    penalty_percentage: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)

    # ETF breakdown
    contract_etf_zar: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    router_charge_zar: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    outstanding_balance_zar: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    total_etf_zar: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))

    # Router details
    router_product_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    router_serial_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    router_value_zar: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    router_depreciation_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0.00"))
    router_returned: Mapped[bool] = mapped_column(Boolean, default=False)
    router_returned_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Payment
    paid_zar: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    invoice_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="SET NULL"), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_termination_fees_tenant_customer", "tenant_id", "customer_id"),
        Index("ix_termination_fees_cancellation", "cancellation_request_id"),
    )


# ---------------------------------------------------------------------------
# Router Return (Reverse Logistics)
# ---------------------------------------------------------------------------

ROUTER_RETURN_STATUS = SAEnum(
    "pending", "courier_booked", "in_transit", "received", "inspected",
    "refund_issued", "completed", "written_off",
    name="router_return_status", create_type=True,
)

ROUTER_CONDITION = SAEnum(
    "new", "good", "fair", "damaged", "missing_parts",
    name="router_condition", create_type=True,
)


class RouterReturn(Base):
    __tablename__ = "router_returns"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    cancellation_request_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cancellation_requests.id", ondelete="CASCADE"), nullable=False)
    termination_fee_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("termination_fees.id", ondelete="SET NULL"), nullable=True)

    # Router identification
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    serial_number: Mapped[str] = mapped_column(String(100), nullable=False)
    imei: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    # Return logistics
    status: Mapped[str] = mapped_column(ROUTER_RETURN_STATUS, nullable=False, default="pending")
    courier: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    tracking_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    pickup_address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    booked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    received_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Inspection
    condition: Mapped[Optional[str]] = mapped_column(ROUTER_CONDITION, nullable=True)
    condition_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    refund_amount_zar: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    inspected_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    inspected_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)

    # Refund
    refund_issued_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    refund_reference: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_router_returns_tenant_status", "tenant_id", "status"),
        Index("ix_router_returns_customer", "customer_id"),
        Index("ix_router_returns_cancellation", "cancellation_request_id"),
        Index("ix_router_returns_serial", "serial_number"),
    )


# ---------------------------------------------------------------------------
# FNO Cancellation Tracking
# ---------------------------------------------------------------------------

FNO_CANCELLATION_METHOD = SAEnum(
    "api", "browser_automation", "manual", "email", "phone",
    name="fno_cancellation_method", create_type=True,
)

FNO_CANCELLATION_STATUS = SAEnum(
    "pending", "in_progress", "submitted", "confirmed", "failed", "retrying",
    name="fno_cancellation_status", create_type=True,
)


class FNOCancellation(Base):
    __tablename__ = "fno_cancellations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    cancellation_request_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cancellation_requests.id", ondelete="CASCADE"), nullable=False)
    subscription_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("subscriptions.id", ondelete="SET NULL"), nullable=True)

    # FNO details
    fno_name: Mapped[str] = mapped_column(String(100), nullable=False)
    fno_account_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    fno_reference: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Method & status
    method: Mapped[str] = mapped_column(FNO_CANCELLATION_METHOD, nullable=False, default="browser_automation")
    status: Mapped[str] = mapped_column(FNO_CANCELLATION_STATUS, nullable=False, default="pending")

    # Browser automation tracking
    automation_job_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    automation_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    automation_completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    automation_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    screenshot_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Confirmation
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmation_reference: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Retry tracking
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    last_retry_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_fno_cancellation_tenant_status", "tenant_id", "status"),
        Index("ix_fno_cancellation_customer", "customer_id"),
        Index("ix_fno_cancellation_request", "cancellation_request_id"),
        Index("ix_fno_cancellation_job", "automation_job_id"),
    )
