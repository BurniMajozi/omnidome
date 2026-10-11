"""Reconciliation tables: OmniDome's Paystack balance snapshots, a local copy of Paystack's balance ledger, the
settlements paid to OmniDome's own account, and an audit row per reconciliation run.

These are platform-level (OmniDome's own Paystack account), not per tenant, so they carry no tenant_id.
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from services.billing.models import Base


class PaystackBalanceSnapshot(Base):
    """OmniDome's Paystack balance next to what it owes the tenants' payout wallets.
    headroom = balance - wallets: negative means OmniDome could not pay every tenant's wallet out today."""
    __tablename__ = "billing_paystack_balance_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="ZAR")
    balance_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    wallets_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    liabilities_open_cents: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    headroom_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(8), nullable=False)  # ok | short
    taken_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class PaystackLedgerEntry(Base):
    """One row of Paystack's GET /balance/ledger (pay-ins and pay-outs on OmniDome's integration)."""
    __tablename__ = "billing_paystack_ledger"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    paystack_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="ZAR")
    balance_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)      # balance AFTER this entry
    difference_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)   # signed movement
    reason: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    category: Mapped[str] = mapped_column(String(16), nullable=False, default="other")
    model_responsible: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    model_row: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PaystackSettlement(Base):
    """A settlement Paystack paid to OmniDome's own bank account (GET /settlement). Tenant subaccount settlements
    go straight to the tenants' banks and are not listed here."""
    __tablename__ = "billing_paystack_settlements"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    paystack_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)
    status: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="ZAR")
    total_amount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    total_fees_cents: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    total_processed_cents: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    settled_on: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ReconRun(Base):
    __tablename__ = "billing_recon_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    triggered_by: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)   # worker | user:<id>
    summary: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (Index("ix_recon_runs_started", "started_at"),)
