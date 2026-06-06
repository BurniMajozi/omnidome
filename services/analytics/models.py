"""SQLAlchemy models for the Analytics service."""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase


class AnalyticsBase(DeclarativeBase):
    __abstract__ = True


class Dashboard(AnalyticsBase):
    __tablename__ = "dashboards"

    id: uuid.UUID = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: uuid.UUID = Column(UUID(as_uuid=True), nullable=False, index=True)
    name: str = Column(String(200), nullable=False)
    description: Optional[str] = Column(Text, nullable=True)
    widget_config: dict = Column(JSONB, nullable=False, default=dict)
    is_template: bool = Column(Boolean, nullable=False, default=False)
    created_at: datetime = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: datetime = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_dashboards_tenant_template", "tenant_id", "is_template"),
    )
