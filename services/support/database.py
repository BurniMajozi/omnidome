"""Support service database layer — SQLAlchemy async models and session management."""

import uuid
from datetime import datetime
from typing import AsyncGenerator, Optional

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from services.common.db import get_async_engine


class Base(DeclarativeBase):
    pass


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    priority: Mapped[str] = mapped_column(String(20), default="NORMAL")
    status: Mapped[str] = mapped_column(String(20), default="OPEN")
    category: Mapped[Optional[str]] = mapped_column(String(50))
    assigned_to: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True))
    external_fno_ref: Mapped[Optional[str]] = mapped_column(String(100))
    is_fcr: Mapped[bool] = mapped_column(Boolean, default=False)
    resolution_notes: Mapped[Optional[str]] = mapped_column(Text)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    # Product/hardware link
    # The physical FK is installed by the migration. Inventory uses separate
    # ORM metadata; declaring its table here breaks SQLAlchemy mapper flushes.
    product_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )
    serial_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Outcome of booking the job's recorded cost in finance (None = nothing was due / not attempted)
    finance_status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    finance_error: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)


class TicketReply(Base):
    __tablename__ = "ticket_replies"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticket_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("tickets.id", ondelete="CASCADE"))
    author_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True))
    author_type: Mapped[str] = mapped_column(String(20), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    is_private: Mapped[bool] = mapped_column(Boolean, default=False)
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


_SCHEMA_LOCK_KEY = 0x5_0_8_008

# create_all cannot be used: tickets.product_id references inventory_products (another service's
# table, created by config/master_schema.sql), so metadata alone raises NoReferencedTableError.
ADDITIVE_COLUMNS = (
    ("tickets", "resolution_notes", "TEXT"),
    ("tickets", "product_id", "UUID REFERENCES inventory_products(id) ON DELETE SET NULL"),
    ("tickets", "serial_number", "VARCHAR(100)"),
    ("tickets", "finance_status", "VARCHAR(20)"),
    ("tickets", "finance_error", "VARCHAR(500)"),
)


async def init_tables():
    """Add the columns this service introduced to the master-schema `tickets` table (idempotent,
    serialised across workers by a transaction advisory lock). Tables themselves come from
    config/master_schema.sql."""
    from sqlalchemy import text

    engine = get_async_engine()
    if engine.dialect.name != "postgresql":
        return
    async with engine.begin() as conn:
        await conn.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _SCHEMA_LOCK_KEY})
        for table, column, ddl in ADDITIVE_COLUMNS:
            exists = (await conn.execute(text("SELECT to_regclass(:t)"), {"t": table})).scalar()
            if exists is None:
                continue
            await conn.execute(text(f'ALTER TABLE "{table}" ADD COLUMN IF NOT EXISTS "{column}" {ddl}'))
