"""SQLAlchemy models for the Agent Orchestrator conversation store."""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# NOT registered with services.common.db.register_tenant_scoped_base:
# AgentMessage and AgentAction have no tenant_id column (they scope through
# their conversation's FK), and the automatic filter is applied
# unconditionally to every mapped subclass. Add tenant_id to those tables
# (needs a schema migration) before opting this Base in. Until then every
# query must keep its manual .where(tenant_id == ...) clause.


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

CONVERSATION_STATUS = SAEnum(
    "active", "completed", "escalated", "abandoned",
    name="conversation_status", create_type=True,
)

MESSAGE_ROLE = SAEnum(
    "system", "user", "assistant", "tool",
    name="message_role", create_type=True,
)

AGENT_TYPE = SAEnum(
    "customer_facing", "retention", "provisioning", "executive", "support",
    name="agent_type", create_type=True,
)

ACTION_STATUS = SAEnum(
    "success", "failure", "timeout",
    name="action_status", create_type=True,
)


# ---------------------------------------------------------------------------
# Agent Conversation
# ---------------------------------------------------------------------------

class AgentConversation(Base):
    __tablename__ = "agent_conversations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    agent_type: Mapped[str] = mapped_column(AGENT_TYPE, nullable=False)
    channel: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    external_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(
        CONVERSATION_STATUS, nullable=False, default="active"
    )
    context: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # relationships
    messages: Mapped[list["AgentMessage"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )
    actions: Mapped[list["AgentAction"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_agent_conversations_tenant", "tenant_id", "agent_type"),
        Index("ix_agent_conversations_external", "tenant_id", "channel", "external_id"),
    )


# ---------------------------------------------------------------------------
# Agent Message
# ---------------------------------------------------------------------------

class AgentMessage(Base):
    __tablename__ = "agent_messages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(MESSAGE_ROLE, nullable=False)
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tool_calls: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    tool_results: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # relationships
    conversation: Mapped["AgentConversation"] = relationship(back_populates="messages")

    __table_args__ = (
        Index("ix_agent_messages_conversation", "conversation_id", "created_at"),
    )


# ---------------------------------------------------------------------------
# Agent Action (audit trail)
# ---------------------------------------------------------------------------

class AgentAction(Base):
    __tablename__ = "agent_actions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    agent_type: Mapped[str] = mapped_column(String(60), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(255), nullable=False)
    tool_input: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    tool_output: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[Optional[int]] = mapped_column(
        String(20), nullable=True
    )  # Optional timing field
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # relationships
    conversation: Mapped["AgentConversation"] = relationship(back_populates="actions")

    __table_args__ = (
        Index("ix_agent_actions_conversation", "conversation_id", "created_at"),
        Index("ix_agent_actions_tool", "agent_type", "tool_name", "created_at"),
    )


# ---------------------------------------------------------------------------
# Chat Deployment (Task 7: per-agent deployable public chat)
# ---------------------------------------------------------------------------
# NOTE on audit: AgentAction.conversation_id is NON-NULLABLE, so a
# `chat.deployed` action row can only be written once a conversation exists.
# The deployment row itself (created_at/created_by) is the creation audit
# record, and every public message already yields guardrails.input/output
# action rows — so no chat.deployed row is written here.


class ChatDeployment(Base):
    __tablename__ = "chat_deployments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    # Plain String(60) like AgentAction.agent_type — avoids PG enum migration pain.
    agent_type: Mapped[str] = mapped_column(String(60), nullable=False)
    identifier: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    display_name: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    # sha256 hex of the access key, or None = public deployment. Never plaintext.
    access_key_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
