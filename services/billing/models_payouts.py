"""Funded payouts: the tenant's payout wallet, the batches/items sent as Paystack transfers, and card fundings.

Paystack transfers are paid out of OmniDome's own Paystack balance, so a tenant may only pay salaries or suppliers
with money it has already given us. The wallet is that money. `billing_payout_wallets.balance_cents` is the
authoritative running balance (row-locked for every change); `billing_payout_wallet_entries` is the append-only
audit trail, unique per (tenant, kind, ref) so every credit/debit is idempotent.
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from services.billing.models import Base


class PayoutWallet(Base):
    __tablename__ = "billing_payout_wallets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, unique=True)
    balance_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class PayoutWalletEntry(Base):
    __tablename__ = "billing_payout_wallet_entries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    # funding | manual_funding | payout | payout_fee | reversal | fee_reversal | liability_recovery
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)  # signed: credits positive, debits negative
    ref: Mapped[str] = mapped_column(String(120), nullable=False)
    note: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("tenant_id", "kind", "ref", name="uq_payout_wallet_entry"),)


class PayoutFunding(Base):
    """A card payment the tenant started to top up its payout wallet (no subaccount: the money stays with OmniDome)."""
    __tablename__ = "billing_payout_fundings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    reference: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="pending")  # pending|credited
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PayoutBatch(Base):
    __tablename__ = "billing_payout_batches"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(12), nullable=False)  # payroll|supplier|other
    source_id: Mapped[str] = mapped_column(String(80), nullable=False)  # payroll run id, purchase order id, ...
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    period: Mapped[str] = mapped_column(String(7), nullable=False)  # YYYY-MM (SAST), for the commission tier
    total_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    fee_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    fee_vat_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # VAT contained in the (VAT-inclusive) fee
    requested_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("tenant_id", "kind", "source_id", "attempt", name="uq_payout_batch_attempt"),
                      Index("ix_payout_batches_source", "tenant_id", "kind", "source_id"))


class PayoutItem(Base):
    __tablename__ = "billing_payout_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    batch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(12), nullable=False)
    item_ref: Mapped[str] = mapped_column(String(80), nullable=False)  # payslip id, supplier invoice id, ...
    recipient_code: Mapped[str] = mapped_column(String(60), nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    fee_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    fee_vat_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reference: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    reason: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="pending")  # pending|processing|success|failed
    transfer_code: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (Index("ix_payout_items_ref", "tenant_id", "kind", "item_ref"),)
