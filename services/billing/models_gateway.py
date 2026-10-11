"""Payment-gateway tables: per-tenant Paystack subaccount settings and the per-charge commission ledger.

billing_gateway_settings   one row per tenant: the settlement bank (only the last 4 digits of the account are
                           stored; the full number goes to Paystack once and is never kept) and the Paystack
                           subaccount code. `commission_tiers` is a negotiated per-tenant override (null = default).
billing_gateway_charges    one row per charge started through a subaccount: gross, commission fixed at initialise
                           time, the tenant's month volume at that moment, and (from the webhook) Paystack's
                           real fee so the true margin (commission - fee) is reportable.
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from services.billing.models import Base


class GatewaySettings(Base):
    __tablename__ = "billing_gateway_settings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")  # active|suspended
    business_name: Mapped[str] = mapped_column(String(200), nullable=False)
    settlement_bank_code: Mapped[str] = mapped_column(String(20), nullable=False)
    settlement_bank_name: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    account_last4: Mapped[str] = mapped_column(String(4), nullable=False)
    subaccount_code: Mapped[str] = mapped_column(String(60), nullable=False)  # ACCT_xxx
    commission_tiers: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    # A change to the settlement account after first setup is only a *request*: a second Paystack subaccount
    # is created for the new details (so the account number is never stored here) and charges keep using
    # `subaccount_code` until a different platform admin approves the swap.
    pending_subaccount_code: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    pending_business_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    pending_bank_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    pending_account_last4: Mapped[Optional[str]] = mapped_column(String(4), nullable=True)
    pending_requested_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    pending_requested_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class GatewayChangeEvent(Base):
    """Append-only audit trail of who set up or changed a tenant's settlement account."""
    __tablename__ = "billing_gateway_change_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    event: Mapped[str] = mapped_column(String(24), nullable=False)  # setup|change_requested|change_approved|change_rejected
    actor_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    detail: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GatewayCharge(Base):
    __tablename__ = "billing_gateway_charges"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    reference: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    invoice_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="invoice")  # invoice|renewal|payroll_funding|...
    subaccount_code: Mapped[str] = mapped_column(String(60), nullable=False)
    period: Mapped[str] = mapped_column(String(7), nullable=False)  # YYYY-MM (SAST)
    gross_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    commission_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    volume_before_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    paystack_fee_cents: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="initialized")  # initialized|succeeded
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    settled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_gateway_charges_tenant_period", "tenant_id", "period", "status"),
    )
