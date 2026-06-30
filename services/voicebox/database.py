"""SQLAlchemy models for the Voicebox service.

This service owns the tenant-scoped metadata layer (voice profiles,
personalities, agent/webchat bindings, generation history) and proxies
the actual ML work — cloning, synthesis, transcription — to the vendored
voicebox engine (see services/voicebox/engine) via engine_client.py.
"""

import uuid
from typing import AsyncGenerator, Optional

from sqlalchemy import ForeignKey, Index, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from services.common.db import Base as CommonBase, get_async_engine


class Base(CommonBase):
    __abstract__ = True


class VoiceProfile(Base):
    """A speaker voice — cloned from a sample, a preset stock voice, or
    text-designed. `engine_profile_id` is the id assigned by the voicebox
    engine itself; this row is the tenant-scoped pointer to it."""

    __tablename__ = "voicebox_profiles"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    language: Mapped[str] = mapped_column(String(10), default="en")
    voice_type: Mapped[str] = mapped_column(String(20), default="cloned")  # cloned, preset, designed
    engine: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # qwen, kokoro, chatterbox, ...
    engine_profile_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="ready")  # pending, ready, failed
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)

    __table_args__ = (
        Index("ix_voicebox_profiles_tenant", "tenant_id", "name"),
    )


class VoicePersonality(Base):
    """A reusable persona: a name/description plus a style prompt that
    drives in-character rewriting before synthesis (voicebox's "compose"
    feature). Optionally pinned to a default voice profile."""

    __tablename__ = "voicebox_personalities"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    style_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    default_voice_profile_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("voicebox_profiles.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        Index("ix_voicebox_personalities_tenant", "tenant_id", "name"),
    )


class AgentVoiceBinding(Base):
    """Maps a voice (+ optional personality) onto a consumer of this
    service — a call-center agent, an orchestrator agent type, or the
    webchat bot — without those services needing their own voice FKs."""

    __tablename__ = "voicebox_agent_bindings"

    scope: Mapped[str] = mapped_column(String(30), nullable=False)  # call_center_agent, orchestrator_agent_type, webchat_bot
    scope_ref: Mapped[str] = mapped_column(String(100), nullable=False)
    voice_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("voicebox_profiles.id", ondelete="CASCADE"), nullable=False
    )
    personality_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("voicebox_personalities.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        Index("ix_voicebox_bindings_scope", "tenant_id", "scope", "scope_ref", unique=True),
    )


class VoiceGeneration(Base):
    """Provenance log of synthesis calls — mirrors voicebox's own
    generation-history concept, scoped per tenant."""

    __tablename__ = "voicebox_generations"

    voice_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("voicebox_profiles.id", ondelete="CASCADE"), nullable=False
    )
    personality_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("voicebox_personalities.id", ondelete="SET NULL"), nullable=True
    )
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    engine_generation_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="completed")
    duration_seconds: Mapped[Optional[float]] = mapped_column(Numeric(8, 2), nullable=True)
    requested_by_service: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # call_center, agent_orchestrator, web

    __table_args__ = (
        Index("ix_voicebox_generations_tenant", "tenant_id", "created_at"),
    )


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
