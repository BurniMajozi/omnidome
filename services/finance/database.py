"""Finance service database layer — SQLAlchemy async models and session management.

Models:
    JournalEntry      — Header for a double-entry booking (date, reference, description)
    JournalEntryLine  — Individual debit/credit lines within a journal entry
    FinancialRecord   — Legacy flat records (kept for backward compatibility)
    BudgetScenario    — What-if scenario storage
"""

import uuid
from datetime import datetime
from typing import AsyncGenerator, Optional

import logging

from sqlalchemy import (
    Boolean, Date, DateTime, ForeignKey, Index, Integer, String, Text, Numeric, UniqueConstraint,
    select, text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from services.common.db import get_async_engine, SoftDeleteMixin


class Base(DeclarativeBase):
    pass


# ── Journal Entry (double-entry GL) ─────────────────────────────────────

class JournalEntry(Base, SoftDeleteMixin):
    __table_args__ = (
        # One entry per (tenant, source, source_id): makes system posting idempotent.
        Index(
            "uq_journal_entries_source", "tenant_id", "source", "source_id", unique=True,
            postgresql_where=text("source IS NOT NULL AND source_id IS NOT NULL AND deleted_at IS NULL"),
            sqlite_where=text("source IS NOT NULL AND source_id IS NOT NULL AND deleted_at IS NULL"),
        ),
    )
    """Header for a double-entry journal booking.

    Each journal entry has one or more JournalEntryLine rows.
    The sum of all debits must equal the sum of all credits (enforced at API level).
    """
    __tablename__ = "journal_entries"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False, index=True,
    )
    entry_date: Mapped[datetime] = mapped_column(
        Date, nullable=False, index=True,
    )
    reference: Mapped[Optional[str]] = mapped_column(String(100))
    description: Mapped[Optional[str]] = mapped_column(Text)
    source: Mapped[Optional[str]] = mapped_column(
        String(50), comment="e.g. BILLING, MANUAL, PAYROLL, ADJUSTMENT, INVENTORY, COGS, STOCK_ADJUSTMENT",
    )
    source_id: Mapped[Optional[str]] = mapped_column(
        String(100), comment="ID of the source document (invoice, payment, etc.)",
    )
    is_posted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow,
    )


class JournalEntryLine(Base):
    """Individual debit or credit line within a journal entry.

    account_code follows a chart of accounts:
        1xxx = Assets          (debit increases)
        2xxx = Liabilities     (credit increases)
        3xxx = Equity          (credit increases)
        4xxx = Revenue         (credit increases)
        5xxx = Cost of Service (debit increases)
        6xxx = Operating Exp   (debit increases)
        7xxx = Other Income    (credit increases)
        8xxx = Other Expense   (debit increases)
        9xxx = Tax             (debit increases)
    """
    __tablename__ = "journal_entry_lines"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    journal_entry_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("journal_entries.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False, index=True,
    )
    account_code: Mapped[str] = mapped_column(String(10), nullable=False)
    account_name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    debit: Mapped[Numeric] = mapped_column(Numeric(14, 2), default=0)
    credit: Mapped[Numeric] = mapped_column(Numeric(14, 2), default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow,
    )


class FinanceAccount(Base):
    """Per-tenant chart of accounts (structural default accounts are added on first use)."""
    __tablename__ = "finance_accounts"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_finance_accounts_tenant_code"),)

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(10), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class FinancePeriod(Base):
    """Accounting period lock. A period with no row is open."""
    __tablename__ = "finance_periods"
    __table_args__ = (UniqueConstraint("tenant_id", "period", name="uq_finance_periods_tenant_period"),)

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    period: Mapped[str] = mapped_column(String(7), nullable=False)  # YYYY-MM
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="open")  # open | closed
    closed_by: Mapped[Optional[str]] = mapped_column(String(64))
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


# ── Document numbering ───────────────────────────────────────────────────

class JournalEntrySequence(Base):
    """Per-tenant counter for auto-generated journal entry reference numbers.

    Mirrors services.billing.database.InvoiceSequence so GL references follow
    the same JE-<TENANT4>-<seq> convention billing already uses for invoices.
    """
    __tablename__ = "journal_entry_sequences"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False, unique=True, index=True,
    )
    last_number: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


# ── Legacy models (kept for backward compatibility) ─────────────────────

class FinancialRecord(Base):
    __tablename__ = "financial_records"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False, index=True,
    )
    record_type: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(500))
    amount: Mapped[Numeric] = mapped_column(Numeric(14, 2), nullable=False)
    period: Mapped[Optional[str]] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow,
    )


class BudgetScenario(Base):
    __tablename__ = "budget_scenarios"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False, index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    revenue_growth_pct: Mapped[Optional[Numeric]] = mapped_column(Numeric(5, 2))
    opex_change_pct: Mapped[Optional[Numeric]] = mapped_column(Numeric(5, 2))
    capex_change_pct: Mapped[Optional[Numeric]] = mapped_column(Numeric(5, 2))
    result_revenue: Mapped[Optional[Numeric]] = mapped_column(Numeric(14, 2))
    result_opex: Mapped[Optional[Numeric]] = mapped_column(Numeric(14, 2))
    result_ebita: Mapped[Optional[Numeric]] = mapped_column(Numeric(14, 2))
    result_ebit: Mapped[Optional[Numeric]] = mapped_column(Numeric(14, 2))
    result_fcf: Mapped[Optional[Numeric]] = mapped_column(Numeric(14, 2))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow,
    )


# ── Revenue recognition ──────────────────────────────────────────────────

class RevenueContract(Base):
    __tablename__ = "revenue_contracts"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    contract_reference: Mapped[str] = mapped_column(String(50), nullable=False)
    customer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    method: Mapped[str] = mapped_column(String(30), nullable=False, default="straight_line")
    total_contract_value: Mapped[Numeric] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    start_date: Mapped[datetime] = mapped_column(Date, nullable=False)
    end_date: Mapped[datetime] = mapped_column(Date, nullable=False)
    recognized_to_date: Mapped[Numeric] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    deferred_balance: Mapped[Numeric] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


# ── Expense governance ───────────────────────────────────────────────────

class ExpenseReceipt(Base):
    __tablename__ = "expense_receipts"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    vendor: Mapped[str] = mapped_column(String(255), nullable=False)
    amount: Mapped[Numeric] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    category: Mapped[Optional[str]] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="processed")
    ocr_confidence: Mapped[Optional[int]] = mapped_column(Integer)
    submitted_by: Mapped[Optional[str]] = mapped_column(String(255))
    receipt_date: Mapped[datetime] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class ApprovalRequest(Base):
    __tablename__ = "approval_requests"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    request: Mapped[str] = mapped_column(String(500), nullable=False)
    amount: Mapped[Numeric] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    owner: Mapped[Optional[str]] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    policy: Mapped[Optional[str]] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class FinancePurchaseOrder(Base):
    __tablename__ = "finance_purchase_orders"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    vendor: Mapped[str] = mapped_column(String(255), nullable=False)
    amount: Mapped[Numeric] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    approver: Mapped[Optional[str]] = mapped_column(String(255))
    due_date: Mapped[Optional[datetime]] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class FixedAsset(Base):
    __tablename__ = "fixed_assets"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    asset_name: Mapped[str] = mapped_column(String(255), nullable=False)
    location: Mapped[Optional[str]] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    cost: Mapped[Numeric] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    accumulated_depreciation: Mapped[Numeric] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    useful_life_years: Mapped[Optional[Numeric]] = mapped_column(Numeric(5, 1))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class RecurringPayment(Base):
    __tablename__ = "recurring_payments"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    vendor: Mapped[str] = mapped_column(String(255), nullable=False)
    amount: Mapped[Numeric] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    frequency: Mapped[str] = mapped_column(String(20), nullable=False, default="Monthly")
    next_run: Mapped[Optional[datetime]] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


# ── Bank reconciliation ───────────────────────────────────────────────────

class BankStatementItem(Base):
    __tablename__ = "bank_statement_items"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    item_date: Mapped[datetime] = mapped_column(Date, nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    amount: Mapped[Numeric] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="unmatched")
    source: Mapped[Optional[str]] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


# ── Session factory ────────────────────────────────────────────────────

_session_factory: Optional[async_sessionmaker] = None


def _get_session_factory() -> async_sessionmaker:
    global _session_factory
    if _session_factory is None:
        engine = get_async_engine()
        _session_factory = async_sessionmaker(engine, expire_on_commit=False)
    return _session_factory


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    factory = _get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


logger = logging.getLogger("finance.db")
_SCHEMA_LOCK_KEY = 0x0F1A4CE  # serialises startup DDL across workers

_UNIQUE_SOURCE_DUPES_SQL = (
    "SELECT count(*) FROM (SELECT 1 FROM journal_entries WHERE source IS NOT NULL AND source_id IS NOT NULL "
    "AND deleted_at IS NULL GROUP BY tenant_id, source, source_id HAVING count(*) > 1) d"
)
_UNIQUE_SOURCE_INDEX_SQL = (
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_journal_entries_source ON journal_entries (tenant_id, source, source_id) "
    "WHERE source IS NOT NULL AND source_id IS NOT NULL AND deleted_at IS NULL"
)


async def init_tables():
    """create_all never ALTERs: new tables come from it, the unique (tenant, source, source_id)
    index on the existing journal_entries table is added here under an advisory lock. Existing
    duplicates are never deleted: the index is skipped with a warning (the API still dedupes)."""
    engine = get_async_engine()
    async with engine.begin() as conn:
        is_pg = conn.dialect.name == "postgresql"
        if is_pg:
            await conn.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _SCHEMA_LOCK_KEY})
        await conn.run_sync(Base.metadata.create_all)
        if is_pg:
            await conn.execute(text("ALTER TABLE journal_entries ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP WITHOUT TIME ZONE"))
            dupes = (await conn.execute(text(_UNIQUE_SOURCE_DUPES_SQL))).scalar() or 0
            if dupes:
                logger.warning("journal_entries has %s duplicated (tenant, source, source_id) keys; "
                               "unique index NOT created until they are resolved by hand", dupes)
            else:
                await conn.execute(text(_UNIQUE_SOURCE_INDEX_SQL))


async def next_journal_reference(db: AsyncSession, tenant_id: uuid.UUID) -> str:
    """Generate the next sequential journal entry reference for a tenant.

    Mirrors services.billing.database.next_invoice_number: a `FOR UPDATE`
    lock on the per-tenant sequence row prevents duplicates under concurrent
    creation. Format: JE-<TENANT4>-<seq:06d>.
    """
    if db.get_bind().dialect.name == "postgresql":
        # Serialize first-row creation as well as subsequent increments.
        import hashlib
        from sqlalchemy import text
        key = int.from_bytes(hashlib.sha256(f"finance-sequence:{tenant_id}".encode()).digest()[:8], "big", signed=True)
        await db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})
    result = await db.execute(
        select(JournalEntrySequence)
        .where(JournalEntrySequence.tenant_id == tenant_id)
        .with_for_update()
    )
    seq = result.scalar_one_or_none()
    if seq is None:
        seq = JournalEntrySequence(tenant_id=tenant_id, last_number=0)
        db.add(seq)
        await db.flush()

    seq.last_number += 1
    await db.flush()

    short_tenant = str(tenant_id).split("-")[0].upper()[:4]
    return f"JE-{short_tenant}-{seq.last_number:06d}"
