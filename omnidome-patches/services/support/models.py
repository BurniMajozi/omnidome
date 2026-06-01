"""SQLAlchemy models for the Support Service."""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean, DateTime, Enum as SAEnum, ForeignKey, Index, Integer, String, Text, func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from services.common.db import Base as CommonBase


class Base(CommonBase):
    __abstract__ = True


TICKET_STATUS = SAEnum(
    "open", "in_progress", "waiting_on_customer", "resolved", "closed", "escalated",
    name="ticket_status", create_type=True,
)

TICKET_PRIORITY = SAEnum(
    "low", "normal", "high", "critical",
    name="ticket_priority", create_type=True,
)

TICKET_CATEGORY = SAEnum(
    "billing", "technical", "sales", "complaint", "general",
    name="ticket_category", create_type=True,
)


class SupportTicket(Base):
    __tablename__ = "support_tickets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    subject: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(TICKET_CATEGORY, nullable=False, default="general")
    priority: Mapped[str] = mapped_column(TICKET_PRIORITY, nullable=False, default="normal")
    status: Mapped[str] = mapped_column(TICKET_STATUS, nullable=False, default="open")
    assigned_to: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    sla_deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_notes: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_support_tickets_tenant_status", "tenant_id", "status"),
        Index("ix_support_tickets_tenant_assigned", "tenant_id", "assigned_to", "status"),
        Index("ix_support_tickets_sla", "tenant_id", "sla_deadline"),
    )


class SupportTicketNote(Base):
    __tablename__ = "support_ticket_notes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    ticket_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("support_tickets.id", ondelete="CASCADE"), nullable=False
    )
    author_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    is_internal: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_support_notes_ticket", "ticket_id", "created_at"),
    )
