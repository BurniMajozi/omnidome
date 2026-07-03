"""Call Center service database layer — SQLAlchemy async models and session management."""

import uuid
from datetime import datetime
from typing import AsyncGenerator, Optional

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, Numeric, JSON
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


class Agent(Base):
    __tablename__ = "call_center_agents"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    extension: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="IDLE")
    daily_sales: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    mttr_minutes: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    csat_score: Mapped[float] = mapped_column(Numeric(3, 2), default=0)
    skills: Mapped[Optional[str]] = mapped_column(JSON, default=list)  # ["sales", "support", "billing"]
    max_concurrent_calls: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


class Script(Base):
    __tablename__ = "call_center_scripts"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


class CallSession(Base):
    __tablename__ = "call_sessions"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    agent_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("call_center_agents.id", ondelete="CASCADE"))
    customer_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True))
    direction: Mapped[str] = mapped_column(String(10), default="INBOUND")  # INBOUND, OUTBOUND
    queue_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True))
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[int] = mapped_column(Integer, default=0)
    sentiment_score: Mapped[Optional[float]] = mapped_column(Numeric(4, 2))
    recording_url: Mapped[Optional[str]] = mapped_column(String(500))
    transcript: Mapped[Optional[str]] = mapped_column(Text)
    # Whisper AI live transcription
    live_transcript: Mapped[Optional[str]] = mapped_column(Text)
    # Call outcome
    outcome: Mapped[Optional[str]] = mapped_column(String(50))  # RESOLVED, ESCALATED, CALLBACK, SALE, NO_ANSWER, ABANDONED
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


# ── Call Queue ──────────────────────────────────────────────────────────

class CallQueue(Base):
    __tablename__ = "call_queues"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)  # INBOUND, OUTBOUND
    category: Mapped[str] = mapped_column(String(50), nullable=False)  # SALES, SUPPORT, BILLING, GENERAL
    # Routing
    routing_strategy: Mapped[str] = mapped_column(String(30), default="ROUND_ROBIN")  # ROUND_ROBIN, SKILL_BASED, LEAST_BUSY, PRIORITY
    priority: Mapped[int] = mapped_column(Integer, default=5)  # 1=highest, 10=lowest
    max_wait_seconds: Mapped[int] = mapped_column(Integer, default=300)
    # Skills required for this queue
    required_skills: Mapped[Optional[str]] = mapped_column(JSON, default=list)
    # Stats (updated in real-time)
    active_calls: Mapped[int] = mapped_column(Integer, default=0)
    queued_calls: Mapped[int] = mapped_column(Integer, default=0)
    avg_wait_seconds: Mapped[int] = mapped_column(Integer, default=0)
    abandoned_count: Mapped[int] = mapped_column(Integer, default=0)
    # Status
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")  # ACTIVE, PAUSED, CLOSED
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


# ── Whisper AI Session ──────────────────────────────────────────────────

class WhisperSession(Base):
    __tablename__ = "whisper_sessions"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    call_session_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("call_sessions.id", ondelete="CASCADE"))
    agent_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("call_center_agents.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")  # ACTIVE, PAUSED, STOPPED
    language: Mapped[str] = mapped_column(String(10), default="en")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    stopped_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


# ── Voice Agent Deployment ──────────────────────────────────────────────

class VoiceAgentDeployment(Base):
    __tablename__ = "voice_agent_deployments"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    agent_name: Mapped[str] = mapped_column(String(200), nullable=False, default="Voice Agent")
    system_prompt: Mapped[Optional[str]] = mapped_column(Text)
    stt_model: Mapped[str] = mapped_column(String(50), default="whisper-large-v3")
    tts_voice: Mapped[str] = mapped_column(String(50), default="voicebox-nova")
    llm_provider: Mapped[str] = mapped_column(String(30), default="anthropic")
    mode: Mapped[str] = mapped_column(String(10), nullable=False)  # "inbound" | "outbound"
    phone_number: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active")  # "active" | "stopped"
    call_session_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True))
    deployed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    stopped_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


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
