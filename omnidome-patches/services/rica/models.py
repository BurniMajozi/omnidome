"""SQLAlchemy models for the RICA Service."""

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime, Enum as SAEnum, ForeignKey, Index, JSON, String, Text, func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from services.common.db import Base as CommonBase


class Base(CommonBase):
    __abstract__ = True


RICA_VERIFICATION_TYPE = SAEnum(
    "smart_id", "basic_kyc", "enhanced_kyc",
    name="rica_verification_type", create_type=True,
)

RICA_STATUS = SAEnum(
    "pending", "in_progress", "verified", "failed", "expired",
    name="rica_status", create_type=True,
)


class RICAVerification(Base):
    __tablename__ = "rica_verifications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    id_number: Mapped[str] = mapped_column(String(13), nullable=False)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    verification_type: Mapped[str] = mapped_column(RICA_VERIFICATION_TYPE, nullable=False, default="basic_kyc")
    status: Mapped[str] = mapped_column(RICA_STATUS, nullable=False, default="pending")
    smile_id_job_id: Mapped[str] = mapped_column(String(100), nullable=True)
    result_code: Mapped[str] = mapped_column(String(50), nullable=True)
    result_text: Mapped[str] = mapped_column(Text, nullable=True)
    image_selfie_url: Mapped[str] = mapped_column(Text, nullable=True)
    image_id_url: Mapped[str] = mapped_column(Text, nullable=True)
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_rica_verifications_tenant_customer", "tenant_id", "customer_id"),
        Index("ix_rica_verifications_tenant_id_number", "tenant_id", "id_number"),
        Index("ix_rica_verifications_tenant_status", "tenant_id", "status"),
    )


class RICALog(Base):
    __tablename__ = "rica_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    verification_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rica_verifications.id", ondelete="CASCADE"), nullable=False,
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    details: Mapped[dict] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_rica_logs_verification", "verification_id", "created_at"),
        Index("ix_rica_logs_tenant", "tenant_id", "created_at"),
    )
