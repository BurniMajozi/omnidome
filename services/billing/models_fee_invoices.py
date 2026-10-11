"""OmniDome's monthly tax invoice to a tenant for the fees OmniDome charged (gateway commission, payout fees).

billing_fee_invoices          one immutable, sequentially numbered document per (tenant, month). Supplier and customer details are
                              snapshotted at issue, so a later change of either never rewrites an issued invoice.
billing_fee_invoice_sequences the per-year serial (ODF-2026-000001): SARS requires unique, sequential tax invoice numbers.
"""

import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from services.billing.models import Base


class FeeInvoice(Base):
    __tablename__ = "billing_fee_invoices"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    period: Mapped[str] = mapped_column(String(7), nullable=False)               # YYYY-MM the invoice is issued for
    number: Mapped[str] = mapped_column(String(30), nullable=False, unique=True)
    issue_date: Mapped[date] = mapped_column(Date, nullable=False)
    doc_type: Mapped[str] = mapped_column(String(20), nullable=False)             # Tax invoice | Invoice | Pro forma invoice
    complete: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)  # carries everything SARS requires of a tax invoice
    supplier: Mapped[dict] = mapped_column(JSONB, nullable=False)
    customer: Mapped[dict] = mapped_column(JSONB, nullable=False)
    lines: Mapped[list] = mapped_column(JSONB, nullable=False)
    subtotal_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    vat_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("tenant_id", "period", name="uq_fee_invoice_tenant_period"),)


class FeeInvoiceSequence(Base):
    __tablename__ = "billing_fee_invoice_sequences"

    year: Mapped[int] = mapped_column(Integer, primary_key=True)
    last_number: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
