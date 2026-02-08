"""SQLAlchemy models for the Billing service."""

import uuid
from datetime import date, datetime
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
    number: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(INVOICE_STATUS, nullable=False, default="draft")
    subtotal_zar: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    vat_zar: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    total_zar: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    amount_paid_zar: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    line_items: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True, default=list)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    credit_note_of: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    payments: Mapped[list["Payment"]] = relationship(back_populates="invoice", cascade="all, delete-orphan")
    dunning_actions: Mapped[list["DunningAction"]] = relationship(back_populates="invoice", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_invoices_tenant_status", "tenant_id", "status"),
        Index("ix_invoices_tenant_customer", "tenant_id", "customer_id"),
        Index("ix_invoices_tenant_number", "tenant_id", "number", unique=True),
    )


# ---------------------------------------------------------------------------
# Invoice Sequence (for per-tenant sequential numbering)
# ---------------------------------------------------------------------------

class InvoiceSequence(Base):
    __tablename__ = "invoice_sequences"

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    last_number: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


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
