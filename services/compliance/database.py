"""Compliance service database layer — SQLAlchemy async models and session management.

Central entity: Contract — all contracts (FNO, supplier, customer, employee) are stored
and managed here. SLAs, ICASA lodgments, RICA requirements, and POPI data requests
are all linked to contracts.

Covers:
- Contract management (FNO, supplier, customer, employee, partner contracts)
- SLA management (tied to contracts, auto-breach detection)
- ICASA regulations (product/promotion lodgment, regulatory changes, announcements)
- POPI Act compliance (data subject access requests, anonymization, breach notification)
- RICA compliance (identity verification storage for regulatory purposes)
- ICASA web scraper (regulation changes, announcements, tariff filings)
"""

import uuid
from datetime import datetime, date
from typing import AsyncGenerator, Optional

from sqlalchemy import (
    Boolean, Date, DateTime, Decimal, Enum as SAEnum, ForeignKey, Index,
    Integer, Numeric, String, Text, UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from services.common.db import get_async_engine


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

CONTRACT_TYPE = SAEnum(
    "fno", "supplier", "customer", "employee", "partner", "service_level",
    "interconnect", "infrastructure", "maintenance", "other",
    name="contract_type", create_type=True,
)

CONTRACT_STATUS = SAEnum(
    "draft", "pending_review", "pending_approval", "active", "suspended",
    "expired", "terminated", "renewed", "cancelled",
    name="contract_status", create_type=True,
)

CONTRACT_PRIORITY = SAEnum(
    "critical", "high", "medium", "low",
    name="contract_priority", create_type=True,
)

SLA_STATUS = SAEnum(
    "active", "breached", "at_risk", "met", "expired", "pending",
    name="sla_status", create_type=True,
)

ICASA_DOCUMENT_TYPE = SAEnum(
    "regulation", "guideline", "notice", "tariff_filing", "license",
    "complaint_ruling", "market_review", "annual_report", "amendment",
    name="icasa_document_type", create_type=True,
)

ICASA_LODGE_STATUS = SAEnum(
    "draft", "submitted", "acknowledged", "approved", "rejected", "withdrawn",
    name="icasa_lodge_status", create_type=True,
)

POPI_REQUEST_TYPE = SAEnum(
    "access", "correction", "deletion", "objection", "consent_withdrawal",
    name="popi_request_type", create_type=True,
)

POPI_REQUEST_STATUS = SAEnum(
    "submitted", "acknowledged", "in_progress", "fulfilled", "rejected", "escalated",
    name="popi_request_status", create_type=True,
)

BREACH_STATUS = SAEnum(
    "detected", "assessed", "notified_icasa", "notified_subjects", "resolved", "closed",
    name="breach_status", create_type=True,
)

VERIFICATION_STATUS = SAEnum(
    "pending", "in_progress", "completed", "failed", "expired", "cancelled",
    name="verification_status", create_type=True,
)

CONSENT_STATUS = SAEnum(
    "granted", "denied", "withdrawn", "expired",
    name="consent_status", create_type=True,
)

RETENTION_POLICY = SAEnum(
    "rica_5year", "contract_life", "financial_7year", "popi_limited", "custom",
    name="retention_policy", create_type=True,
)


# ---------------------------------------------------------------------------
# 1. CONTRACTS (central entity)
# ---------------------------------------------------------------------------

class Contract(Base):
    """Central contract record — all contracts across OmniDome.

    Types:
    - fno: Fibre Network Operator agreements (Vumatel, Openserve, etc.)
    - supplier: Hardware/software suppliers
    - customer: Customer service agreements
    - employee: Employment contracts
    - partner: Partnership/reseller agreements
    - service_level: Internal SLA agreements
    - interconnect: Interconnection agreements
    - infrastructure: Infrastructure leases
    - maintenance: Maintenance contracts
    """

    __tablename__ = "contracts"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)

    # Contract identity
    contract_number: Mapped[str] = mapped_column(String(100), nullable=False)
    contract_type: Mapped[str] = mapped_column(CONTRACT_TYPE, nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(CONTRACT_STATUS, nullable=False, default="draft")
    priority: Mapped[str] = mapped_column(CONTRACT_PRIORITY, default="medium")

    # Counterparty
    counterparty_name: Mapped[str] = mapped_column(String(300), nullable=False)
    counterparty_registration: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    counterparty_contact_person: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    counterparty_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    counterparty_phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    # Internal owner
    internal_owner_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    internal_department: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Dates
    effective_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    expiry_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    renewal_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    termination_notice_days: Mapped[int] = mapped_column(Integer, default=30)
    auto_renew: Mapped[bool] = mapped_column(Boolean, default=False)

    # Financial
    contract_value_zar: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="ZAR")
    payment_terms: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    # "Net 30", "Net 60", "Monthly in advance"

    # ICASA compliance
    icasa_registration_required: Mapped[bool] = mapped_column(Boolean, default=False)
    icasa_registration_number: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    icasa_compliance_status: Mapped[str] = mapped_column(String(20), default="pending")
    # pending, compliant, non_compliant, exempt

    # RICA requirements
    rica_data_retention_required: Mapped[bool] = mapped_column(Boolean, default=True)
    rica_retention_years: Mapped[int] = mapped_column(Integer, default=5)
    rica_data_deletion_scheduled: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Document storage
    contract_document_path: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    supporting_documents: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    # [{"name": "signed_contract.pdf", "path": "/docs/...", "uploaded_at": "..."}]

    # Versioning
    version: Mapped[int] = mapped_column(Integer, default=1)
    parent_contract_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("contracts.id", ondelete="SET NULL"), nullable=True,
    )
    is_latest_version: Mapped[bool] = mapped_column(Boolean, default=True)

    # Notes
    internal_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    termination_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Audit
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    approved_by: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    slas = relationship("ContractSLA", back_populates="contract", cascade="all, delete-orphan")
    icasa_lodgments = relationship("IcasaLodgment", back_populates="contract", cascade="all, delete-orphan")
    popi_requests = relationship("PopiDataRequest", back_populates="contract", cascade="all, delete-orphan")
    verifications = relationship("RicaVerification", back_populates="contract", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_contract_tenant_type", "tenant_id", "contract_type"),
        Index("ix_contract_tenant_status", "tenant_id", "status"),
        Index("ix_contract_tenant_number", "tenant_id", "contract_number", unique=True),
        Index("ix_contract_expiry", "tenant_id", "expiry_date"),
        Index("ix_contract_counterparty", "tenant_id", "counterparty_name"),
        Index("ix_contract_icasa", "tenant_id", "icasa_compliance_status"),
        Index("ix_contract_rica", "tenant_id", "rica_data_deletion_scheduled"),
    )


# ---------------------------------------------------------------------------
# 2. CONTRACT SLAs
# ---------------------------------------------------------------------------

class ContractSLA(Base):
    """SLA clauses tied to contracts.

    Each contract can have multiple SLA metrics (uptime, response time,
    installation time, etc.) with targets and automated breach detection.
    """

    __tablename__ = "contract_slas"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    contract_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("contracts.id", ondelete="CASCADE"), nullable=False, index=True,
    )

    # SLA definition
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sla_type: Mapped[str] = mapped_column(String(30), nullable=False)
    # uptime, response_time, resolution_time, installation_time, availability

    # Target
    target_value: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    target_unit: Mapped[str] = mapped_column(String(20), nullable=False)
    # percent, hours, days, minutes

    # Thresholds
    warning_threshold_pct: Mapped[Optional[float]] = mapped_column(Numeric(5, 2), nullable=True)
    breach_threshold_pct: Mapped[Optional[float]] = mapped_column(Numeric(5, 2), nullable=True)

    # Measurement
    measurement_method: Mapped[str] = mapped_column(String(30), default="automatic")
    measurement_frequency: Mapped[str] = mapped_column(String(20), default="daily")

    # Status
    current_status: Mapped[str] = mapped_column(SLA_STATUS, default="pending")
    current_value: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)

    # Penalty
    penalty_clause: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    penalty_amount_zar: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)

    # Effective period
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    effective_to: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    contract = relationship("Contract", back_populates="slas")

    __table_args__ = (
        Index("ix_csla_tenant_contract", "tenant_id", "contract_id"),
        Index("ix_csla_tenant_status", "tenant_id", "current_status"),
        Index("ix_csla_breach", "tenant_id", "current_status", "contract_id"),
    )


class ContractSLAMeasurement(Base):
    """SLA measurement records per contract SLA."""

    __tablename__ = "contract_sla_measurements"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    sla_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("contract_slas.id", ondelete="CASCADE"), nullable=False, index=True,
    )

    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_type: Mapped[str] = mapped_column(String(10), nullable=False, default="daily")

    actual_value: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    target_value: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    is_breach: Mapped[bool] = mapped_column(Boolean, default=False)
    deviation_pct: Mapped[Optional[float]] = mapped_column(Numeric(8, 4), nullable=True)
    sample_count: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_cslam_tenant_sla", "tenant_id", "sla_id"),
        Index("ix_cslam_period", "tenant_id", "period_start"),
        Index("ix_cslam_breach", "tenant_id", "is_breach"),
    )


# ---------------------------------------------------------------------------
# 3. ICASA PRODUCT/PROMOTION LODGMENT
# ---------------------------------------------------------------------------

class IcasaLodgment(Base):
    """Tracks lodgment of new products and promotions with ICASA.

    Linked to the contract that governs the product/promotion.
    ICASA requires ISPs to lodge certain products and promotions.
    """

    __tablename__ = "icasa_lodgments"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    contract_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("contracts.id", ondelete="SET NULL"), nullable=True,
    )

    # Product info
    product_name: Mapped[str] = mapped_column(String(500), nullable=False)
    product_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # new_product, promotion, tariff_change, service_modification
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Link to inventory
    product_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)

    # Lodgment details
    status: Mapped[str] = mapped_column(ICASA_LODGE_STATUS, nullable=False, default="draft")
    icasa_reference: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    lodgment_method: Mapped[str] = mapped_column(String(30), default="portal")

    # Documents
    supporting_documents: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)

    # Timeline
    prepared_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Response
    icasa_feedback: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Assignment
    prepared_by: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    submitted_by: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    contract = relationship("Contract", back_populates="icasa_lodgments")

    __table_args__ = (
        Index("ix_il_tenant_status", "tenant_id", "status"),
        Index("ix_il_tenant_contract", "tenant_id", "contract_id"),
        Index("ix_il_tenant_product", "tenant_id", "product_id"),
    )


# ---------------------------------------------------------------------------
# 4. ICASA REGULATIONS (scraped)
# ---------------------------------------------------------------------------

class IcasaRegulation(Base):
    """ICASA regulations, guidelines, and announcements scraped from icasa.org.za."""

    __tablename__ = "icasa_regulations"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)

    document_type: Mapped[str] = mapped_column(ICASA_DOCUMENT_TYPE, nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    icasa_reference: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    source_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    document_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)

    published_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    effective_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    comment_deadline: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    scraped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    full_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    key_points: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    affected_areas: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    impact_level: Mapped[str] = mapped_column(String(20), default="unknown")
    impact_assessment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    required_actions: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)

    is_new: Mapped[bool] = mapped_column(Boolean, default=True)
    is_reviewed: Mapped[bool] = mapped_column(Boolean, default=False)
    reviewed_by: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_ir_tenant_type", "tenant_id", "document_type"),
        Index("ix_ir_tenant_new", "tenant_id", "is_new"),
        Index("ix_ir_tenant_impact", "tenant_id", "impact_level"),
        Index("ix_ir_effective", "effective_date"),
    )


# ---------------------------------------------------------------------------
# 5. ICASA SCRAPER LOG
# ---------------------------------------------------------------------------

class IcasaScrapeLog(Base):
    """Log of ICASA website scrapes."""

    __tablename__ = "icasa_scrape_logs"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)

    scrape_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="success")
    items_found: Mapped[int] = mapped_column(Integer, default=0)
    items_new: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_isl_tenant_type", "tenant_id", "scrape_type"),
        Index("ix_isl_tenant_status", "tenant_id", "status"),
    )


# ---------------------------------------------------------------------------
# 6. POPI DATA SUBJECT ACCESS REQUESTS
# ---------------------------------------------------------------------------

class PopiDataRequest(Base):
    """Data Subject Access Requests per POPI Act Section 23-25.

    Linked to the contract that governs the data processing.
    ICASA requires these be fulfilled within 30 days.
    """

    __tablename__ = "popi_data_requests"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    contract_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("contracts.id", ondelete="SET NULL"), nullable=True,
    )

    # Who made the request
    requested_by_customer_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    requested_by_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    request_type: Mapped[str] = mapped_column(POPI_REQUEST_TYPE, nullable=False)
    status: Mapped[str] = mapped_column(POPI_REQUEST_STATUS, nullable=False, default="submitted")

    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    requested_data_categories: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)

    # Timeline (POPI requires response within 30 days)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    due_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    fulfilled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    response_method: Mapped[str] = mapped_column(String(30), default="secure_portal")
    response_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    reported_to_icasa: Mapped[bool] = mapped_column(Boolean, default=False)
    icasa_reference: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    assigned_to: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    contract = relationship("Contract", back_populates="popi_requests")

    __table_args__ = (
        Index("ix_pdr_tenant_status", "tenant_id", "status"),
        Index("ix_pdr_tenant_due", "tenant_id", "due_date"),
        Index("ix_pdr_overdue", "tenant_id", "status", "due_date"),
    )


# ---------------------------------------------------------------------------
# 7. DATA BREACH REGISTER
# ---------------------------------------------------------------------------

class DataBreachRecord(Base):
    """Data breach register per POPI Act Section 22."""

    __tablename__ = "data_breach_records"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    contract_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("contracts.id", ondelete="SET NULL"), nullable=True,
    )

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    severity: Mapped[str] = mapped_column(String(20), default="medium")
    status: Mapped[str] = mapped_column(BREACH_STATUS, nullable=False, default="detected")

    affected_data_subjects_count: Mapped[int] = mapped_column(Integer, default=0)
    affected_data_categories: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)

    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    assessed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    icasa_notified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    subjects_notified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    icasa_notification_reference: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    remediation_actions: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    root_cause: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    reported_by: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    handled_by: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_dbr_tenant_status", "tenant_id", "status"),
        Index("ix_dbr_tenant_severity", "tenant_id", "severity"),
    )


# ---------------------------------------------------------------------------
# 8. RICA VERIFICATION STORAGE
# ---------------------------------------------------------------------------

class RicaVerification(Base):
    """RICA identity verification storage for regulatory compliance.

    NOTE: We do NOT use the RICA database directly. We store verification
    results for our own regulatory compliance purposes only.
    Per ICASA regulations, RICA data must be retained for 5 years minimum.
    """

    __tablename__ = "rica_verifications"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    contract_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("contracts.id", ondelete="SET NULL"), nullable=True,
    )
    customer_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)

    # Verification
    job_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    smile_job_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    verification_type: Mapped[str] = mapped_column(String(30), default="DOCUMENT_VERIFICATION")
    status: Mapped[str] = mapped_column(VERIFICATION_STATUS, default="pending")
    result_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    result_message: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    full_response: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # Identity (stored for regulatory compliance only)
    id_number: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    id_type: Mapped[str] = mapped_column(String(20), default="sa_id")
    first_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    date_of_birth: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # ICASA compliance
    icasa_registration_required: Mapped[bool] = mapped_column(Boolean, default=True)
    icasa_registration_status: Mapped[str] = mapped_column(String(20), default="pending")
    re_verification_required: Mapped[bool] = mapped_column(Boolean, default=False)
    re_verification_due: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Data retention (ICASA requires 5 years minimum)
    retention_policy: Mapped[str] = mapped_column(RETENTION_POLICY, default="rica_5year")
    retention_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    data_deletion_scheduled: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Anonymization (POPI compliance when retention expires)
    is_anonymized: Mapped[bool] = mapped_column(Boolean, default=False)
    anonymized_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Audit
    verified_by: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    contract = relationship("Contract", back_populates="verifications")

    __table_args__ = (
        Index("ix_rv_tenant_contract", "tenant_id", "contract_id"),
        Index("ix_rv_tenant_customer", "tenant_id", "customer_id"),
        Index("ix_rv_tenant_status", "tenant_id", "status"),
        Index("ix_rv_job_id", "job_id"),
        Index("ix_rv_retention", "tenant_id", "retention_until"),
        Index("ix_rv_reverify", "tenant_id", "re_verification_due"),
    )


# ---------------------------------------------------------------------------
# 9. CONTRACT DOCUMENTS
# ---------------------------------------------------------------------------

class ContractDocument(Base):
    """Documents attached to contracts — signed copies, amendments, etc."""

    __tablename__ = "contract_documents"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    contract_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("contracts.id", ondelete="CASCADE"), nullable=False, index=True,
    )

    document_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # signed_contract, amendment, renewal, termination_notice, icasa_filing, sla_report
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Optional[str] = mapped_column(Text, nullable=True)
    file_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    file_size_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    mime_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Versioning
    version: Mapped[int] = mapped_column(Integer, default=1)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)

    # Audit
    uploaded_by: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_cd_tenant_contract", "tenant_id", "contract_id"),
        Index("ix_cd_tenant_type", "tenant_id", "document_type"),
    )


# ---------------------------------------------------------------------------
# 10. CONTRACT NOTES / AUDIT LOG
# ---------------------------------------------------------------------------

class ContractAuditLog(Base):
    """Audit trail for all contract changes."""

    __tablename__ = "contract_audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    contract_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("contracts.id", ondelete="CASCADE"), nullable=False, index=True,
    )

    action: Mapped[str] = mapped_column(String(50), nullable=False)
    # created, updated, status_changed, approved, terminated, renewed, sla_breach, icasa_lodged
    field_changed: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    old_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    new_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    performed_by: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_cal_tenant_contract", "tenant_id", "contract_id"),
        Index("ix_cal_tenant_action", "tenant_id", "action"),
        Index("ix_cal_created", "tenant_id", "created_at"),
    )


# ---------------------------------------------------------------------------
# Session factory
# ---------------------------------------------------------------------------

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
