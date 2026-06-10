"""Compliance service database layer — SQLAlchemy async models and session management.

Covers:
- RICA identity verification (extended from existing)
- Contact management (customer PII, consent, data retention)
- POPI Act compliance (data subject access requests, anonymization, breach notification)
- ICASA regulations (product/promotion lodgment, regulatory changes, announcements)
- SLA management (internal + regulatory SLAs)
- ICASA web scraper (regulation changes, announcements, tariff filings)
"""

import uuid
from datetime import datetime, date
from typing import AsyncGenerator, Optional

from sqlalchemy import (
    Boolean, Date, DateTime, Enum as SAEnum, ForeignKey, Index,
    Integer, Numeric, String, Text, UniqueConstraint,
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

VERIFICATION_STATUS = SAEnum(
    "pending", "in_progress", "completed", "failed", "expired", "cancelled",
    name="verification_status", create_type=True,
)

CONSENT_STATUS = SAEnum(
    "granted", "denied", "withdrawn", "expired",
    name="consent_status", create_type=True,
)

CONSENT_PURPOSE = SAEnum(
    "rica_verification", "marketing", "credit_check", "data_sharing",
    "analytics", "service_delivery", "legal_compliance",
    name="consent_purpose", create_type=True,
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

BREACH_SEVERITY = SAEnum(
    "low", "medium", "high", "critical",
    name="breach_severity", create_type=True,
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

SLA_TYPE = SAEnum(
    "internal", "regulatory", "customer", "fno",
    name="sla_type", create_type=True,
)

SLA_STATUS = SAEnum(
    "active", "breached", "at_risk", "met", "expired",
    name="sla_status", create_type=True,
)

DATA_RETENTION_POLICY = SAEnum(
    "rica_5year", "popi_limited", "financial_7year", "marketing_3year",
    "support_2year", "network_1year", "custom",
    name="data_retention_policy", create_type=True,
)

ANONYMIZATION_METHOD = SAEnum(
    "pseudonymization", "generalization", "noise_addition", "k_anonymity",
    "full_deletion", "masking",
    name="anonymization_method", create_type=True,
)


# ---------------------------------------------------------------------------
# 1. Contact Management (extended RICA + PII)
# ---------------------------------------------------------------------------

class ComplianceContact(Base):
    """Extended contact record with full PII management for RICA + POPI compliance.

    Stores customer identity data with consent tracking, data retention policies,
    and anonymization status. This is the central record for all personal data
    held about a customer — used for RICA verification, POPI access requests,
    and data retention enforcement.
    """

    __tablename__ = "compliance_contacts"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    # Link to CRM customer

    # Identity (encrypted at rest in production)
    id_number: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    id_type: Mapped[str] = mapped_column(String(20), default="sa_id")
    # sa_id, passport, asylum_permit
    first_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    date_of_birth: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # Contact details
    phone_primary: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    phone_secondary: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Address (linked to CRM Property)
    property_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    address_line1: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    province: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    postal_code: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)

    # RICA status
    rica_status: Mapped[str] = mapped_column(String(20), default="unverified")
    # unverified, pending, verified, failed, expired
    rica_verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    rica_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # RICA verification expires — must re-verify per ICASA regulations

    # Data retention
    retention_policy: Mapped[str] = mapped_column(DATA_RETENTION_POLICY, default="rica_5year")
    retention_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    data_deletion_scheduled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Anonymization
    is_anonymized: Mapped[bool] = mapped_column(Boolean, default=False)
    anonymized_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    anonymization_method: Mapped[Optional[str]] = mapped_column(ANONYMIZATION_METHOD, nullable=True)

    # Access control
    last_accessed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_accessed_by: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    access_count: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    consents = relationship("ComplianceConsent", back_populates="contact", cascade="all, delete-orphan")
    popi_requests = relationship("PopiDataRequest", back_populates="contact", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_cc_tenant_customer", "tenant_id", "customer_id"),
        Index("ix_cc_tenant_rica", "tenant_id", "rica_status"),
        Index("ix_cc_id_number", "id_number"),
        Index("ix_cc_retention", "tenant_id", "retention_until"),
        Index("ix_cc_anonymized", "tenant_id", "is_anonymized"),
    )


# ---------------------------------------------------------------------------
# 2. Consent Management (POPI Act)
# ---------------------------------------------------------------------------

class ComplianceConsent(Base):
    """Tracks customer consent for data processing per POPI Act Section 11.

    Each consent record represents a specific purpose for which the customer
    has granted or withdrawn consent. Required for lawful processing of personal
    information under POPI.
    """

    __tablename__ = "compliance_consents"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    contact_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("compliance_contacts.id", ondelete="CASCADE"), nullable=False, index=True,
    )

    purpose: Mapped[str] = mapped_column(CONSENT_PURPOSE, nullable=False)
    status: Mapped[str] = mapped_column(CONSENT_STATUS, nullable=False, default="granted")

    # Consent details
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    withdrawn_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # How consent was collected
    collection_method: Mapped[str] = mapped_column(String(50), default="web_form")
    # web_form, phone, in_person, api, imported
    collection_context: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # "Customer signed up via web portal on 2024-01-15"

    # Proof
    consent_record_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    # Path to signed consent form / recording reference
    ip_address: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Versioning
    consent_version: Mapped[str] = mapped_column(String(20), default="1.0")
    privacy_policy_version: Mapped[str] = mapped_column(String(20), default="1.0")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    contact = relationship("ComplianceContact", back_populates="consents")

    __table_args__ = (
        Index("ix_consent_tenant_contact", "tenant_id", "contact_id"),
        Index("ix_consent_tenant_purpose", "tenant_id", "purpose"),
        Index("ix_consent_status", "tenant_id", "status"),
        Index("ix_consent_expires", "tenant_id", "expires_at"),
    )


# ---------------------------------------------------------------------------
# 3. POPI Data Subject Access Requests
# ---------------------------------------------------------------------------

class PopiDataRequest(Base):
    """Data Subject Access Requests (DSAR) per POPI Act Section 23-25.

    Tracks all requests from data subjects to access, correct, or delete
    their personal information. ICASA requires these be fulfilled within
    30 days (or 60 days with valid extension).
    """

    __tablename__ = "popi_data_requests"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    contact_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("compliance_contacts.id", ondelete="CASCADE"), nullable=False, index=True,
    )

    request_type: Mapped[str] = mapped_column(POPI_REQUEST_TYPE, nullable=False)
    status: Mapped[str] = mapped_column(POPI_REQUEST_STATUS, nullable=False, default="submitted")

    # Request details
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    requested_data_categories: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    # ["identity", "contact", "financial", "network_usage", "marketing"]

    # Timeline (POPI requires response within 30 days)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    due_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    fulfilled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Response
    response_method: Mapped[str] = mapped_column(String(30), default="secure_portal")
    # secure_portal, email, physical, api
    response_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # ICASA reporting
    reported_to_icasa: Mapped[bool] = mapped_column(Boolean, default=False)
    icasa_reference: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Assignment
    assigned_to: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    contact = relationship("ComplianceContact", back_populates="popi_requests")

    __table_args__ = (
        Index("ix_pdr_tenant_status", "tenant_id", "status"),
        Index("ix_pdr_tenant_due", "tenant_id", "due_date"),
        Index("ix_pdr_tenant_type", "tenant_id", "request_type"),
        Index("ix_pdr_overdue", "tenant_id", "status", "due_date"),
    )


# ---------------------------------------------------------------------------
# 4. Data Breach Register (POPI Act Section 22)
# ---------------------------------------------------------------------------

class DataBreachRecord(Base):
    """Data breach register per POPI Act Section 22.

    Records all personal data breaches. ICASA must be notified of breaches
    "as soon as reasonably possible" if it affects customer data.
    """

    __tablename__ = "data_breach_records"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)

    # Breach details
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    severity: Mapped[str] = mapped_column(BREACH_SEVERITY, nullable=False, default="medium")
    status: Mapped[str] = mapped_column(BREACH_STATUS, nullable=False, default="detected")

    # Impact assessment
    affected_contacts_count: Mapped[int] = mapped_column(Integer, default=0)
    affected_data_categories: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    # ["id_numbers", "contact_details", "financial", "network_usage"]
    data_volume_estimate: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Timeline
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    assessed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    icasa_notified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    subjects_notified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # ICASA notification
    icasa_notification_reference: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    icasa_response: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Remediation
    remediation_actions: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    root_cause: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    lessons_learned: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Assignment
    reported_by: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    handled_by: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_dbr_tenant_status", "tenant_id", "status"),
        Index("ix_dbr_tenant_severity", "tenant_id", "severity"),
        Index("ix_dbr_detected", "tenant_id", "detected_at"),
        Index("ix_dbr_icasa", "tenant_id", "icasa_notified_at"),
    )


# ---------------------------------------------------------------------------
# 5. ICASA Regulations & Announcements (scraped)
# ---------------------------------------------------------------------------

class IcasaRegulation(Base):
    """ICASA regulations, guidelines, and announcements scraped from icasa.org.za.

    Tracks regulatory changes that affect ISP operations including:
    - Type approval requirements
    - Numbering regulations
    - Consumer protection rules
    - Tariff filing requirements
    - License conditions
    """

    __tablename__ = "icasa_regulations"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)

    # Document info
    document_type: Mapped[str] = mapped_column(ICASA_DOCUMENT_TYPE, nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    icasa_reference: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    # ICASA reference number

    # Source
    source_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    document_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    # Link to PDF/document on ICASA website

    # Dates
    published_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    effective_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    comment_deadline: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    scraped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Content
    full_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    key_points: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    # ["Point 1", "Point 2"]
    affected_areas: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    # ["type_approval", "numbering", "consumer_protection", "tariffs"]

    # Impact assessment
    impact_level: Mapped[str] = mapped_column(String(20), default="unknown")
    # critical, high, medium, low, none, unknown
    impact_assessment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    required_actions: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)

    # Status
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
        Index("ix_ir_scraped", "tenant_id", "scraped_at"),
    )


# ---------------------------------------------------------------------------
# 6. ICASA Product/Promotion Lodgment
# ---------------------------------------------------------------------------

class IcasaProductLodgment(Base):
    """Tracks lodgment of new products and promotions with ICASA.

    ICASA requires ISPs to lodge certain products and promotions before
    they can be offered to consumers. This tracks the lodgment process.
    """

    __tablename__ = "icasa_product_lodgments"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)

    # Product info
    product_name: Mapped[str] = mapped_column(String(500), nullable=False)
    product_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # new_product, promotion, tariff_change, service_modification
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Link to inventory
    product_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    # Link to inventory_products

    # Lodgment details
    status: Mapped[str] = mapped_column(ICASA_LODGE_STATUS, nullable=False, default="draft")
    icasa_reference: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    lodgment_method: Mapped[str] = mapped_column(String(30), default="portal")
    # portal, email, physical

    # Documents
    supporting_documents: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    # [{"name": "tariff_sheet.pdf", "path": "/docs/..."}, ...]

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

    __table_args__ = (
        Index("ix_ipl_tenant_status", "tenant_id", "status"),
        Index("ix_ipl_tenant_type", "tenant_id", "product_type"),
        Index("ix_ipl_tenant_product", "tenant_id", "product_id"),
        Index("ix_ipl_submitted", "tenant_id", "submitted_at"),
    )


# ---------------------------------------------------------------------------
# 7. SLA Management (internal + regulatory)
# ---------------------------------------------------------------------------

class ComplianceSLA(Base):
    """SLA management for both internal operations and regulatory requirements.

    Covers:
    - Internal SLAs (ticket response, installation times)
    - Regulatory SLAs (ICASA complaint handling, POPI response times)
    - Customer SLAs (service uptime, support response)
    - FNO SLAs (provisioning times, fault repair)
    """

    __tablename__ = "compliance_slas"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)

    name: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sla_type: Mapped[str] = mapped_column(SLA_TYPE, nullable=False)

    # Target
    target_value: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    target_unit: Mapped[str] = mapped_column(String(20), nullable=False)
    # hours, days, percent, minutes

    # Measurement
    measurement_method: Mapped[str] = mapped_column(String(50), default="automatic")
    # automatic, manual, hybrid
    measurement_frequency: Mapped[str] = mapped_column(String(20), default="daily")
    # real_time, hourly, daily, weekly, monthly

    # Thresholds
    warning_threshold: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    # e.g. 80% of target = warning
    breach_threshold: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    # e.g. 100% of target = breach

    # Status
    current_status: Mapped[str] = mapped_column(SLA_STATUS, default="active")
    current_value: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)

    # Regulatory reference
    regulatory_reference: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    # "ICASA Code of Conduct Regulation 12", "POPI Act Section 23"

    # Effective period
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    effective_to: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_csla_tenant_type", "tenant_id", "sla_type"),
        Index("ix_csla_tenant_status", "tenant_id", "current_status"),
        Index("ix_csla_tenant_active", "tenant_id", "is_active"),
        Index("ix_csla_effective", "tenant_id", "effective_from"),
    )


class ComplianceSLAMeasurement(Base):
    """SLA measurement records for tracking compliance over time."""

    __tablename__ = "compliance_sla_measurements"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    sla_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("compliance_slas.id", ondelete="CASCADE"), nullable=False, index=True,
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
# 8. Data Retention Schedule
# ---------------------------------------------------------------------------

class DataRetentionSchedule(Base):
    """Data retention schedules per POPI Act and ICASA requirements.

    POPI requires personal information only be kept as long as necessary
    for the purpose for which it was collected. ICASA has specific retention
    requirements for RICA data (5 years minimum).
    """

    __tablename__ = "data_retention_schedules"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)

    data_category: Mapped[str] = mapped_column(String(100), nullable=False)
    # rica_identity, call_records, billing, network_usage, marketing, support
    retention_period_months: Mapped[int] = mapped_column(Integer, nullable=False)
    legal_basis: Mapped[str] = mapped_column(String(200), nullable=False)
    # "ICASA Regulation 12(3)", "POPI Act Section 14", "Tax Act Section 29"

    # Enforcement
    auto_delete: Mapped[bool] = mapped_column(Boolean, default=False)
    anonymize_instead: Mapped[bool] = mapped_column(Boolean, default=True)
    anonymization_method: Mapped[Optional[str]] = mapped_column(ANONYMIZATION_METHOD, nullable=True)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_enforced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    records_affected: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_drs_tenant_category", "tenant_id", "data_category", unique=True),
        Index("ix_drs_tenant_active", "tenant_id", "is_active"),
    )


# ---------------------------------------------------------------------------
# 9. ICASA Scraper Log
# ---------------------------------------------------------------------------

class IcasaScrapeLog(Base):
    """Log of ICASA website scrapes for audit trail."""

    __tablename__ = "icasa_scrape_logs"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)

    scrape_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # regulations, announcements, tariffs, license_updates
    source_url: Mapped[str] = mapped_column(String(1000), nullable=False)

    # Results
    status: Mapped[str] = mapped_column(String(20), default="success")
    # success, partial, failed
    items_found: Mapped[int] = mapped_column(Integer, default=0)
    items_new: Mapped[int] = mapped_column(Integer, default=0)
    items_updated: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Timing
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_isl_tenant_type", "tenant_id", "scrape_type"),
        Index("ix_isl_tenant_status", "tenant_id", "status"),
        Index("ix_isl_started", "tenant_id", "started_at"),
    )


# ---------------------------------------------------------------------------
# 10. RICA Verification (extended from existing RicaVerification)
# ---------------------------------------------------------------------------

class RicaVerification(Base):
    """Extended RICA verification record with full audit trail.

    Replaces the existing RicaVerification in services/rica/database.py.
    Adds ICASA compliance fields, re-verification tracking, and
    cross-reference to compliance_contacts.
    """

    __tablename__ = "rica_verifications"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    contact_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("compliance_contacts.id", ondelete="SET NULL"), nullable=True
    )

    # Verification
    job_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    smile_job_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    verification_type: Mapped[str] = mapped_column(String(30), default="DOCUMENT_VERIFICATION")
    status: Mapped[str] = mapped_column(VERIFICATION_STATUS, default="pending")
    result_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    result_message: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    full_response: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # Identity data
    id_number: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # ICASA compliance
    icasa_registration_required: Mapped[bool] = mapped_column(Boolean, default=True)
    icasa_registration_status: Mapped[str] = mapped_column(String(20), default="pending")
    # pending, registered, failed
    re_verification_required: Mapped[bool] = mapped_column(Boolean, default=False)
    re_verification_due: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Audit
    verified_by: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_rv_tenant_contact", "tenant_id", "contact_id"),
        Index("ix_rv_tenant_status", "tenant_id", "status"),
        Index("ix_rv_job_id", "job_id"),
        Index("ix_rv_id_number", "id_number"),
        Index("ix_rv_reverify", "tenant_id", "re_verification_due"),
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
