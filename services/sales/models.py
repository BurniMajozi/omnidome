"""SQLAlchemy async models for the Sales service.

Tables: pipelines, deal_stages, deals, quotes, commissions, targets
"""

import uuid
from datetime import datetime, date
from decimal import Decimal

from sqlalchemy import (
    Boolean, Column, Date, DateTime, ForeignKey, Integer, Numeric,
    String, Text, text as sa_text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()


class Pipeline(Base):
    __tablename__ = "pipelines"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    name = Column(String(255), nullable=False, default="Default Pipeline")
    is_default = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime)

    stages = relationship("DealStage", back_populates="pipeline", cascade="all, delete-orphan")


class DealStage(Base):
    __tablename__ = "deal_stages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pipeline_id = Column(UUID(as_uuid=True), ForeignKey("pipelines.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(100), nullable=False)
    probability = Column(Integer, nullable=False, default=10)
    sort_order = Column(Integer, nullable=False, default=0)

    pipeline = relationship("Pipeline", back_populates="stages")
    deals = relationship("Deal", back_populates="stage")


class Deal(Base):
    __tablename__ = "deals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    contact_id = Column(UUID(as_uuid=True), nullable=False)  # customer_id in the old schema
    lead_id = Column(UUID(as_uuid=True))
    agent_id = Column(UUID(as_uuid=True), index=True)
    stage_id = Column(UUID(as_uuid=True), ForeignKey("deal_stages.id"))
    package_id = Column(UUID(as_uuid=True))
    name = Column(String(500), nullable=False)
    amount = Column(Numeric(14, 2))  # legacy alias for value_zar
    value_zar = Column(Numeric(14, 2), nullable=False, default=0)
    status = Column(String(20), nullable=False, default="OPEN")
    close_date = Column(Date)
    closed_at = Column(DateTime)
    close_reason = Column(Text)
    notes = Column(Text)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime)

    stage = relationship("DealStage", back_populates="deals")
    commissions = relationship("Commission", back_populates="deal", cascade="all, delete-orphan")
    quotes = relationship("Quote", back_populates="deal")


class Quote(Base):
    __tablename__ = "quotes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    deal_id = Column(UUID(as_uuid=True), ForeignKey("deals.id"))
    customer_id = Column(UUID(as_uuid=True), nullable=False)
    lead_id = Column(UUID(as_uuid=True))
    agent_id = Column(UUID(as_uuid=True))
    package_id = Column(UUID(as_uuid=True))
    items = Column(JSONB)
    total_monthly = Column(Numeric(14, 2), nullable=False, default=0)
    total_once_off = Column(Numeric(14, 2), nullable=False, default=0)
    term_months = Column(Integer, nullable=False, default=12)
    valid_until = Column(Date)
    status = Column(String(20), nullable=False, default="DRAFT")
    terms = Column(Text)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    sent_at = Column(DateTime)
    accepted_at = Column(DateTime)

    deal = relationship("Deal", back_populates="quotes")


class Commission(Base):
    __tablename__ = "commissions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    deal_id = Column(UUID(as_uuid=True), ForeignKey("deals.id", ondelete="CASCADE"), nullable=False)
    agent_id = Column(UUID(as_uuid=True), nullable=False)
    amount_zar = Column(Numeric(14, 2), nullable=False)
    rate_percent = Column(Numeric(5, 2))
    status = Column(String(20), nullable=False, default="PENDING")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime)

    deal = relationship("Deal", back_populates="commissions")


class Target(Base):
    __tablename__ = "targets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    agent_id = Column(UUID(as_uuid=True), index=True)
    team_id = Column(UUID(as_uuid=True))
    period_type = Column(String(20), nullable=False, default="MONTHLY")
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)
    target_value_zar = Column(Numeric(14, 2), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime)
