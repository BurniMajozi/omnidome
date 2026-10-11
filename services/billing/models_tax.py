"""Per-tenant VAT position and its audit trail.

billing_tax_profiles       one row per tenant: country, whether it is a VAT vendor, its VAT number, rate, whether its prices include
                           VAT. A tenant with no row has not chosen yet (see services/billing/tax.py: legacy behaviour + a prompt).
billing_tax_profile_events append-only history of every change (who, when, before/after) because a VAT position is a compliance fact.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from services.billing.models import Base


class TaxProfileRow(Base):
    __tablename__ = "billing_tax_profiles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, unique=True)
    country: Mapped[str] = mapped_column(String(2), nullable=False, default="ZA")
    vat_registered: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    vat_number: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    rate_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=Decimal("0"))
    prices_include_vat: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    legal_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    registered_since: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    updated_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class TaxProfileEvent(Base):
    __tablename__ = "billing_tax_profile_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    actor_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    before: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    after: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
