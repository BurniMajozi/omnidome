"""RICA service database layer — SQLAlchemy async models and session management."""

import uuid
from datetime import datetime
from typing import AsyncGenerator, Optional

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, JSON
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from services.common.db import get_async_engine, register_tenant_scoped_base


class Base(DeclarativeBase):
    pass


# Every model below carries tenant_id; opt this Base into the automatic
# tenant filter in services.common.db so a missed manual .where() clause
# can no longer leak rows across tenants.
register_tenant_scoped_base(Base)


class RicaVerification(Base):
    __tablename__ = "rica_verifications"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    contact_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    job_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    smile_job_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    verification_type: Mapped[str] = mapped_column(String(30), default="DOCUMENT_VERIFICATION")
    status: Mapped[str] = mapped_column(String(20), default="PENDING")
    result_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    result_message: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    full_response: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    id_number: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


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


async def init_tables():
    engine = get_async_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
