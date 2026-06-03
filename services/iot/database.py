"""IoT service database layer — SQLAlchemy async models and session management."""

import uuid
from datetime import datetime
from typing import AsyncGenerator, Optional

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.future import select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from services.common.db import get_async_engine


class Base(DeclarativeBase):
    pass


class IoTDevice(Base):
    __tablename__ = "iot_devices"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    contact_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    device_name: Mapped[str] = mapped_column(String(255), nullable=False)
    device_type: Mapped[str] = mapped_column(String(50), nullable=False)
    mac_address: Mapped[Optional[str]] = mapped_column(String(17), unique=True)
    serial_number: Mapped[Optional[str]] = mapped_column(String(100), unique=True)
    status: Mapped[str] = mapped_column(String(20), default="OFFLINE")
    firmware_version: Mapped[Optional[str]] = mapped_column(String(50))
    last_seen: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default={})
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class SignalHistory(Base):
    __tablename__ = "ont_signal_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("iot_devices.id", ondelete="CASCADE"))
    rx_power_dbm: Mapped[float] = mapped_column(Numeric(5, 2))
    tx_power_dbm: Mapped[Optional[float]] = mapped_column(Numeric(5, 2))
    voltage_v: Mapped[Optional[float]] = mapped_column(Numeric(5, 2))
    bias_current_ma: Mapped[Optional[float]] = mapped_column(Numeric(5, 2))
    temperature_c: Mapped[Optional[float]] = mapped_column(Numeric(5, 2))
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class IoTCommand(Base):
    __tablename__ = "iot_commands"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    device_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("iot_devices.id", ondelete="CASCADE"))
    command_type: Mapped[str] = mapped_column(String(50), nullable=False)
    payload_: Mapped[Optional[dict]] = mapped_column("payload", JSONB)
    status: Mapped[str] = mapped_column(String(20), default="PENDING")
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
