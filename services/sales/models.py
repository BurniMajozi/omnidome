"""SQLAlchemy async models for the Sales service.

Tables (authoritative DDL: config/master_schema.sql): pipelines, deal_stages,
deals, quotes, commissions, commission_tiers, sales_targets, leads; plus
lead_activities and lead_tasks (services/sales/schema.py).

NOTE: contacts live in master_schema too, but the sales service reads/writes
them via its own Contact model (CRM also owns the same table). No cross-service
SQLAlchemy FKs — FKs only reference integrity the DB enforces at runtime.
Cross-service references are plain UUID columns (package_id in particular:
main.py previously declared FKs to inventory_products which inventory does NOT
own — inventory only owns the `products` table).
"""

import uuid
from datetime import datetime, date
from decimal import Decimal

from sqlalchemy import (
    Boolean, Column, Date, DateTime, ForeignKey, Integer, Numeric,
    String, Text,
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
    contact_id = Column(UUID(as_uuid=True), nullable=False)
    lead_id = Column(UUID(as_uuid=True))
    agent_id = Column(UUID(as_uuid=True), index=True)
    stage_id = Column(UUID(as_uuid=True), ForeignKey("deal_stages.id"))
    package_id = Column(UUID(as_uuid=True))
    name = Column(String(500), nullable=False)
    amount = Column(Numeric(14, 2))
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


class CommissionTier(Base):
    """Tenant-configurable commission tiers (master_schema.commission_tiers)."""

    __tablename__ = "commission_tiers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    tier_name = Column(String(255), nullable=False, default="Standard")
    min_deals = Column(Integer, nullable=False, default=0)
    max_deals = Column(Integer)
    rate_percent = Column(Numeric(5, 2), nullable=False, default=5.00)
    is_active = Column(Boolean, nullable=False, default=True)
    sort_order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime)


class Target(Base):
    # master_schema table is `sales_targets` (NOT `targets`).
    __tablename__ = "sales_targets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    agent_id = Column(UUID(as_uuid=True), index=True)
    team_id = Column(UUID(as_uuid=True))
    period_type = Column(String(20), nullable=False, default="MONTHLY")
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)
    target_value_zar = Column(Numeric(14, 2), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class Contact(Base):
    __tablename__ = "contacts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    email = Column(String(255))
    phone = Column(String(20))
    physical_address = Column(Text)
    postal_code = Column(String(10))
    city = Column(String(100))
    province = Column(String(100))
    rica_verified = Column(Boolean, nullable=False, default=False)
    rica_id_number = Column(String(20))
    status = Column(String(20), nullable=False, default="ACTIVE")
    lifecycle_stage = Column(String(50), default="PROSPECT")
    nps_score = Column(Integer)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime)


class Lead(Base):
    __tablename__ = "leads"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    contact_id = Column(UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="SET NULL"))
    agent_id = Column(UUID(as_uuid=True), index=True)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    email = Column(String(255))
    phone = Column(String(20))
    address = Column(Text)
    source = Column(String(50), default="FIELD_VISIT")
    interest_level = Column(Integer, default=3)
    status = Column(String(20), nullable=False, default="NEW")
    notes = Column(Text)
    converted_at = Column(DateTime)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime)
    # Lead record (SPEC-lead-lifecycle.md; columns added by schema.ensure_lead_schema).
    ref_no = Column(Integer)              # shown as LD-000042, unique per tenant
    # Owner = an HR employee (no FK: employees are not login users; agent_id
    # references users and stays the logged-in sales agent).
    owner_id = Column(UUID(as_uuid=True))
    owner_name = Column(String(200))
    priority = Column(String(10), nullable=False, default="normal")
    closed_at = Column(DateTime(timezone=True))
    close_reason = Column(Text)
    escalated_at = Column(DateTime(timezone=True))

    contact = relationship("Contact")


class LeadActivity(Base):
    """Timeline entry on a lead: stage changes, notes, emails, tasks, escalations."""

    __tablename__ = "lead_activities"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    lead_id = Column(UUID(as_uuid=True), ForeignKey("leads.id", ondelete="CASCADE"), nullable=False)
    kind = Column(String(40), nullable=False)
    summary = Column(String(300), nullable=False)
    details = Column(JSONB, nullable=False, default=dict)
    actor_id = Column(UUID(as_uuid=True))
    actor_name = Column(String(200))
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


class LeadTask(Base):
    """Follow-up on a lead; kind "call" + assignee "Outbound queue" = outbound call."""

    __tablename__ = "lead_tasks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    lead_id = Column(UUID(as_uuid=True), ForeignKey("leads.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(200), nullable=False)
    kind = Column(String(20), nullable=False, default="task")
    due_at = Column(DateTime(timezone=True))
    assignee_id = Column(UUID(as_uuid=True))
    assignee_name = Column(String(200))
    status = Column(String(20), nullable=False, default="open")
    created_by = Column(UUID(as_uuid=True))
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    completed_at = Column(DateTime(timezone=True))
