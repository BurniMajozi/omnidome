"""Invoicing-suite tables: item catalog, templates, invoice metadata, quotes, share links, delivery events.

All tables are NEW (created by Base.metadata.create_all in database.init_tables); nothing here ALTERs an
existing table. The ``invoices`` table itself is untouched: per-invoice extras that the invoice shape has
no column for (issue date, PO number, source, created_by, bill-to snapshot, quote link) live in
``invoice_meta`` keyed by invoice id.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, func, text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from services.billing.models import Base

QUOTE_STATUSES = ("draft", "sent", "viewed", "accepted", "declined", "expired", "converted")


class InvoiceItem(Base):
    """Reusable catalog element a user can drop onto an invoice or quote."""
    __tablename__ = "invoice_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    unit_price_zar: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=Decimal("15.00"))
    category: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (Index("ix_invoice_items_tenant_cat", "tenant_id", "category"),)


class InvoiceTemplate(Base):
    """Branding + which sections a rendered document shows. One per tenant is the default."""
    __tablename__ = "invoice_templates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    company_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    company_address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    vat_number: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    logo_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    accent_colour: Mapped[str] = mapped_column(String(7), nullable=False, default="#1d4ed8")
    footer: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    payment_details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    default_terms: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    default_due_days: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    # {"description": true, "quantity": true, "unit_price": true, "discount": true, "tax": true, "line_total": true}
    show_columns: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    show_payment_details: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    show_terms: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    # exactly-one-default per tenant is enforced in code (templates router, under a row lock).


class InvoiceMeta(Base):
    """Extras for an invoice (any invoice may have one; manual/quote-derived invoices always do)."""
    __tablename__ = "invoice_meta"

    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="CASCADE"), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    issue_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    po_number: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    source_type: Mapped[str] = mapped_column(String(30), nullable=False, default="manual")
    created_by: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    terms: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    discount_total_zar: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    template_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    bill_to: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)  # {name,email,phone,address}
    quote_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("uq_invoice_meta_quote", "quote_id", unique=True, postgresql_where=text("quote_id IS NOT NULL")),
    )


class QuoteSequence(Base):
    __tablename__ = "quote_sequences"

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    last_number: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class Quote(Base):
    __tablename__ = "quotes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    number: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="draft")
    customer_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    prospect_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    prospect_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    prospect_phone: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    prospect_address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    issue_date: Mapped[date] = mapped_column(Date, nullable=False)
    valid_until: Mapped[date] = mapped_column(Date, nullable=False)
    subtotal_zar: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    discount_total_zar: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    vat_zar: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    total_zar: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    terms: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    po_number: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    source: Mapped[str] = mapped_column(String(30), nullable=False, default="web")  # field_sales|technician|web
    created_by: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    template_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    converted_invoice_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    viewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    declined_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    converted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_note: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    lines: Mapped[list["QuoteLine"]] = relationship(
        back_populates="quote", cascade="all, delete-orphan", order_by="QuoteLine.position")

    __table_args__ = (
        Index("ix_quotes_tenant_number", "tenant_id", "number", unique=True),
        Index("ix_quotes_tenant_status", "tenant_id", "status"),
    )


class QuoteLine(Base):
    __tablename__ = "quote_lines"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    quote_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quotes.id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    catalog_item_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False, default=Decimal("1"))
    unit_price_zar: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    discount_zar: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=Decimal("15.00"))
    net_zar: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    vat_zar: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    total_zar: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))

    quote: Mapped["Quote"] = relationship(back_populates="lines")


class DocumentShareLink(Base):
    """Unguessable public link. Only the SHA-256 of the token is stored."""
    __tablename__ = "document_share_links"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    doc_type: Mapped[str] = mapped_column(String(10), nullable=False)  # invoice|quote
    doc_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    view_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_viewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DocumentDeliveryEvent(Base):
    """One row per delivery fact about an emailed document.

    A send attempt creates a ``queued`` row (the claim; it carries the idempotency key). It becomes
    ``sent`` (message_id stored), or ``failed`` with the key cleared on a DEFINITE failure, or stays
    ``queued`` with detail.ambiguous=true when delivery could not be confirmed (blocks another send
    until reconciled). Provider callbacks append ``delivered`` / ``bounced`` / ``complained`` / ``replied``
    rows; the public view link appends ``viewed``; ``suppressed`` records a blocked recipient.
    """
    __tablename__ = "document_delivery_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    doc_type: Mapped[str] = mapped_column(String(10), nullable=False)
    doc_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(12), nullable=False)
    kind: Mapped[str] = mapped_column(String(12), nullable=False, default="document")  # document|reminder
    recipient: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # comma-joined lower-case to+cc
    subject: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    message_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    actor: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    detail: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("uq_doc_delivery_idem", "tenant_id", "idempotency_key", unique=True,
              postgresql_where=text("idempotency_key IS NOT NULL")),
        Index("ix_doc_delivery_doc", "tenant_id", "doc_type", "doc_id"),
    )
