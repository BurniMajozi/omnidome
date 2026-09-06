"""FNO Intelligence Service — browser automation, data extraction, competitive intelligence.

Owns tables:
  - fno_portal_sessions: active browser sessions per FNO portal
  - fno_automation_jobs: automation job tracking with full audit trail
  - fno_automation_steps: individual step execution within jobs
  - fno_automation_templates: reusable workflow templates
  - fno_screenshots: screenshots captured during automation
  - fno_network_coverage: extracted coverage data from FNO portals
  - fno_network_status: network status announcements from FNO portals
  - fno_promotions: competitive promotion tracking
  - fno_pricing: competitive package/pricing tracking
  - fno_new_areas: new area build announcements
  - fno_leads: leads generated from FNO portal data
  - fno_reports: automated report generation
  - fno_operational_tasks: operational automation tasks (cancel, ticket, migrate, pause)

Port: 8024
"""

import uuid
from datetime import datetime, date
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean, Date, DateTime, Enum as SAEnum, ForeignKey,
    Index, Integer, Numeric, String, Text, UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from services.common.db import register_tenant_scoped_base


# ════════════════════════════════════════════════════════════════════════
# ENUMS
# ════════════════════════════════════════════════════════════════════════

FNO_PORTAL = SAEnum(
    "vumatel_active", "vumatel_passive", "openserve", "frogfoot",
    "octotel", "metrofibre", "liquid", "other",
    name="fno_portal", create_type=False,
)

AUTOMATION_STATUS = SAEnum(
    "queued", "running", "waiting_captcha", "waiting_2fa",
    "completed", "failed", "retrying", "cancelled", "manual_intervention",
    name="automation_status", create_type=False,
)

AUTOMATION_ACTION = SAEnum(
    "login", "navigate", "fill_form", "submit", "screenshot",
    "extract_data", "click", "wait", "scroll", "download", "upload",
    "record_start", "record_stop", "playback",
    name="automation_action", create_type=False,
)

JOB_TYPE = SAEnum(
    # Operational
    "cancellation", "ticket_logging", "migration", "pause_service",
    "resume_service", "status_check", "provisioning",
    # Intelligence
    "coverage_extraction", "promotion_scraping", "pricing_extraction",
    "new_area_detection", "network_status_check",
    # Reporting
    "report_generation", "bulk_data_extraction",
    name="job_type", create_type=False,
)

LEAD_SOURCE = SAEnum(
    "fno_coverage_map", "fno_promotion_page", "fno_new_area",
    "fno_network_status", "fno_pricing_page", "fno_deactivation_list",
    name="lead_source", create_type=False,
)

LEAD_STATUS = SAEnum(
    "new", "qualified", "contacted", "converted", "disqualified",
    name="lead_status", create_type=False,
)

REPORT_TYPE = SAEnum(
    "competitive_pricing", "coverage_comparison", "promotion_tracker",
    "new_area_alert", "network_uptime", "lead_pipeline",
    "operational_summary", "fno_sla_compliance",
    name="report_type", create_type=False,
)


# ════════════════════════════════════════════════════════════════════════
# BASE
# ════════════════════════════════════════════════════════════════════════

class Base(DeclarativeBase):
    pass


# Every model below carries tenant_id; opt this Base into the automatic
# tenant filter in services.common.db so a missed manual .where() clause
# can no longer leak rows across tenants.
register_tenant_scoped_base(Base)


# ════════════════════════════════════════════════════════════════════════
# 1. BROWSER SESSION & AUTOMATION ENGINE
# ════════════════════════════════════════════════════════════════════════

class FNOPortalSession(Base):
    """Active browser session for FNO portal automation.
    
    Manages the browser instance, cookies, and session state
    for each FNO portal. Supports screen recording.
    """
    __tablename__ = "fno_portal_sessions"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)

    session_id: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    fno_portal: Mapped[str] = mapped_column(FNO_PORTAL, nullable=False)
    browser_type: Mapped[str] = mapped_column(String(50), default="headless_chrome")

    # Session state
    status: Mapped[str] = mapped_column(String(20), default="active")
    # active, idle, recording, closed, error

    # Current page context
    current_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    current_page_title: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)

    # Screen recording
    is_recording: Mapped[bool] = mapped_column(Boolean, default=False)
    recording_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    recording_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Linked job
    active_job_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)

    # Credentials (encrypted reference)
    credential_vault_key: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    # Timing
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_activity_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_fno_sess_tenant", "tenant_id", "status"),
        Index("ix_fno_sess_portal", "fno_portal", "status"),
        Index("ix_fno_sess_job", "active_job_id"),
    )


class FNOAutomationJob(Base):
    """Automation job — the core unit of work.
    
    Covers both operational tasks (cancellations, tickets, migrations)
    and intelligence tasks (coverage extraction, promotion scraping).
    """
    __tablename__ = "fno_automation_jobs"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    customer_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True, index=True)

    # Job classification
    job_type: Mapped[str] = mapped_column(JOB_TYPE, nullable=False)
    fno_portal: Mapped[str] = mapped_column(FNO_PORTAL, nullable=False)
    fno_name: Mapped[str] = mapped_column(String(100), nullable=False)

    # Operational context (for operational jobs)
    fno_account_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    fno_reference: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    cancellation_request_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    ticket_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)

    # Status
    status: Mapped[str] = mapped_column(AUTOMATION_STATUS, nullable=False, default="queued")
    priority: Mapped[int] = mapped_column(Integer, default=5)

    # Browser session
    session_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("fno_portal_sessions.id"), nullable=True)

    # Execution
    scheduled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Retry
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, default=3)
    next_retry_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Result
    result_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    confirmation_number: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Manual intervention
    requires_manual: Mapped[bool] = mapped_column(Boolean, default=False)
    manual_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    assigned_to: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)

    # Screen recording
    screen_recording_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_fno_job_tenant_status", "tenant_id", "status"),
        Index("ix_fno_job_type", "tenant_id", "job_type"),
        Index("ix_fno_job_portal", "fno_portal", "status"),
        Index("ix_fno_job_customer", "tenant_id", "customer_id"),
        Index("ix_fno_job_scheduled", "scheduled_at"),
        Index("ix_fno_job_priority", "priority", "status"),
    )


class FNOAutomationStep(Base):
    """Individual step within an automation job.
    
    Each step captures: action, target, result, screenshot, timing.
    Steps can be recorded and played back.
    """
    __tablename__ = "fno_automation_steps"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("fno_automation_jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)

    step_number: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(AUTOMATION_ACTION, nullable=False)

    # Target
    target_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    target_selector: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    target_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Mouse/click coordinates (for screen recording playback)
    mouse_x: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    mouse_y: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Result
    status: Mapped[str] = mapped_column(String(20), default="pending")
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    extracted_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_fno_step_job", "job_id", "step_number"),
    )


class FNOAutomationTemplate(Base):
    """Reusable automation template for common FNO portal workflows.
    
    Templates define the step sequence, selectors, and expected outcomes.
    Used for both operational and intelligence workflows.
    """
    __tablename__ = "fno_automation_templates"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    fno_portal: Mapped[str] = mapped_column(FNO_PORTAL, nullable=False)
    job_type: Mapped[str] = mapped_column(JOB_TYPE, nullable=False)

    # Template steps (JSON array)
    steps_template: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    # CSS/XPath selectors for portal elements
    selectors: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True, default=dict)

    # Success tracking
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    success_rate: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2), nullable=True)
    total_runs: Mapped[int] = mapped_column(Integer, default=0)
    successful_runs: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_fno_tmpl_portal_type", "fno_portal", "job_type"),
        Index("ix_fno_tmpl_active", "tenant_id", "is_active"),
    )


class FNOScreenshot(Base):
    """Screenshots captured during automation.
    
    Linked to jobs and steps. Used for audit, debugging,
    and as evidence for operational tasks.
    """
    __tablename__ = "fno_screenshots"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    job_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("fno_automation_jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    step_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("fno_automation_steps.id"), nullable=True)

    # Screenshot details
    screenshot_path: Mapped[str] = mapped_column(String(500), nullable=False)
    thumbnail_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    caption: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Context
    page_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    page_title: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)

    # OCR extracted text
    extracted_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_fno_ss_job", "job_id", "created_at"),
    )


# ════════════════════════════════════════════════════════════════════════
# 2. NETWORK INTELLIGENCE (Coverage, Status, Promotions, Pricing)
# ════════════════════════════════════════════════════════════════════════

class FNONetworkCoverage(Base):
    """Extracted coverage data from FNO portals.
    
    Tracks which areas/suburbs each FNO covers, enabling
    competitive coverage analysis and lead generation.
    """
    __tablename__ = "fno_network_coverage"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)

    fno_name: Mapped[str] = mapped_column(String(100), nullable=False)
    fno_portal: Mapped[str] = mapped_column(FNO_PORTAL, nullable=False)

    # Location
    area_name: Mapped[str] = mapped_column(String(200), nullable=False)
    suburb: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    province: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    postal_code: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    gps_lat: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 8), nullable=True)
    gps_lng: Mapped[Optional[Decimal]] = mapped_column(Numeric(11, 8), nullable=True)

    # Coverage details
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    # available, coming_soon, under_construction, planned
    technology: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    # FTTH, FTTB, LTE, 5G, fixed_wireless
    max_speed_mbps: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Source
    source_job_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    source_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    first_detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_fno_cov_fno", "fno_name", "fno_portal"),
        Index("ix_fno_cov_location", "city", "suburb"),
        Index("ix_fno_cov_status", "status"),
        Index("ix_fno_cov_postal", "postal_code"),
    )


class FNONetworkStatus(Base):
    """Network status announcements from FNO portals.
    
    Tracks outages, maintenance windows, and service alerts.
    """
    __tablename__ = "fno_network_status"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)

    fno_name: Mapped[str] = mapped_column(String(100), nullable=False)
    fno_portal: Mapped[str] = mapped_column(FNO_PORTAL, nullable=False)

    # Status details
    status_type: Mapped[str] = mapped_column(String(30), nullable=False)
    # outage, maintenance, degradation, resolved, planned
    severity: Mapped[str] = mapped_column(String(20), default="info")
    # info, warning, critical

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Affected areas
    affected_areas: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True, default=list)
    affected_suburbs: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True, default=list)

    # Timing
    reported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expected_resolution: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Source
    source_job_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    source_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_fno_status_fno", "fno_name", "status_type"),
        Index("ix_fno_status_severity", "tenant_id", "severity"),
        Index("ix_fno_status_reported", "reported_at"),
    )


class FNOPromotion(Base):
    """Competitive promotion tracking from FNO portals."""
    __tablename__ = "fno_promotions"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)

    fno_name: Mapped[str] = mapped_column(String(100), nullable=False)
    fno_portal: Mapped[str] = mapped_column(FNO_PORTAL, nullable=False)

    # Promotion details
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    promo_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    # discount, free_months, free_installation, bundle, upgrade

    # Pricing
    original_price_zar: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    discounted_price_zar: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    discount_percentage: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2), nullable=True)

    # Validity
    valid_from: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    valid_until: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Applicable areas
    applicable_areas: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True, default=list)

    # Source
    source_job_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    source_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    first_detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_fno_promo_fno", "fno_name", "is_active"),
        Index("ix_fno_promo_valid", "valid_from", "valid_until"),
    )


class FNOPricing(Base):
    """Competitive package/pricing tracking from FNO portals."""
    __tablename__ = "fno_pricing"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)

    fno_name: Mapped[str] = mapped_column(String(100), nullable=False)
    fno_portal: Mapped[str] = mapped_column(FNO_PORTAL, nullable=False)

    # Package details
    package_name: Mapped[str] = mapped_column(String(200), nullable=False)
    speed_mbps: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    technology: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    # Pricing
    monthly_price_zar: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    installation_fee_zar: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    router_fee_zar: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    contract_months: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Features
    is_unlimited: Mapped[bool] = mapped_column(Boolean, default=True)
    has_static_ip: Mapped[bool] = mapped_column(Boolean, default=False)
    features: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True, default=list)

    # Source
    source_job_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    source_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    effective_date: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)

    __table_args__ = (
        Index("ix_fno_price_fno", "fno_name", "package_name"),
        Index("ix_fno_price_speed", "speed_mbps"),
        Index("ix_fno_price_effective", "effective_date"),
    )


class FNONewArea(Base):
    """New area build announcements from FNO portals."""
    __tablename__ = "fno_new_areas"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)

    fno_name: Mapped[str] = mapped_column(String(100), nullable=False)
    fno_portal: Mapped[str] = mapped_column(FNO_PORTAL, nullable=False)

    # Area details
    area_name: Mapped[str] = mapped_column(String(200), nullable=False)
    suburb: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    province: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Build status
    build_status: Mapped[str] = mapped_column(String(30), nullable=False)
    # announced, under_construction, coming_soon, available
    expected_available_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # Technology
    technology: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    max_speed_mbps: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Lead generation
    estimated_subscribers: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    leads_generated: Mapped[int] = mapped_column(Integer, default=0)

    # Source
    source_job_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    source_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    first_detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_fno_new_area_fno", "fno_name", "build_status"),
        Index("ix_fno_new_area_location", "city", "suburb"),
        Index("ix_fno_new_area_date", "expected_available_date"),
    )


# ════════════════════════════════════════════════════════════════════════
# 3. LEAD GENERATION & MARKETING
# ════════════════════════════════════════════════════════════════════════

class FNOLead(Base):
    """Leads generated from FNO portal data.
    
    When FNO data reveals opportunities (new areas, deactivations,
    coverage gaps), leads are created for the sales team.
    """
    __tablename__ = "fno_leads"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)

    # Lead source
    lead_source: Mapped[str] = mapped_column(LEAD_SOURCE, nullable=False)
    source_job_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    source_fno: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Contact info
    first_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    # Location
    address_line1: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    suburb: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    postal_code: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    gps_lat: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 8), nullable=True)
    gps_lng: Mapped[Optional[Decimal]] = mapped_column(Numeric(11, 8), nullable=True)

    # Qualification
    status: Mapped[str] = mapped_column(LEAD_STATUS, nullable=False, default="new")
    score: Mapped[int] = mapped_column(Integer, default=0)  # 0-100
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Marketing context
    current_fno: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    current_package: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    interest_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # "FNO outage in area", "New FNO area build", "Better pricing available"

    # Conversion
    converted_to_customer_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    converted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_fno_lead_tenant_status", "tenant_id", "status"),
        Index("ix_fno_lead_source", "lead_source", "status"),
        Index("ix_fno_lead_score", "tenant_id", "score"),
        Index("ix_fno_lead_location", "city", "suburb"),
        Index("ix_fno_lead_fno", "source_fno"),
    )


# ════════════════════════════════════════════════════════════════════════
# 4. OPERATIONAL AUTOMATION
# ════════════════════════════════════════════════════════════════════════

class FNOOperationalTask(Base):
    """Operational automation tasks executed through FNO portal UI.
    
    Covers: cancellations, ticket logging, migrations, pause/resume,
    status checks, provisioning — all automated through the browser.
    """
    __tablename__ = "fno_operational_tasks"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)

    # Task classification
    task_type: Mapped[str] = mapped_column(JOB_TYPE, nullable=False)
    fno_portal: Mapped[str] = mapped_column(FNO_PORTAL, nullable=False)
    fno_name: Mapped[str] = mapped_column(String(100), nullable=False)

    # FNO account context
    fno_account_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    fno_reference: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Related entities
    cancellation_request_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    ticket_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    order_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    subscription_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)

    # Task details
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    payload: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    # Task-specific data: cancellation reason, ticket details, move address, etc.

    # Automation job link
    automation_job_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("fno_automation_jobs.id"), nullable=True)

    # Status
    status: Mapped[str] = mapped_column(String(20), default="pending")
    # pending, in_progress, completed, failed, cancelled

    # Result
    result_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    confirmation_number: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Evidence
    screenshot_before_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    screenshot_after_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    screen_recording_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Timing
    scheduled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_fno_op_tenant_status", "tenant_id", "status"),
        Index("ix_fno_op_customer", "tenant_id", "customer_id"),
        Index("ix_fno_op_type", "task_type", "status"),
        Index("ix_fno_op_fno", "fno_name", "fno_portal"),
        Index("ix_fno_op_scheduled", "scheduled_at"),
    )


# ════════════════════════════════════════════════════════════════════════
# 5. REPORTING & ANALYTICS
# ════════════════════════════════════════════════════════════════════════

class FNOReport(Base):
    """Automated reports generated from FNO intelligence data."""
    __tablename__ = "fno_reports"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)

    report_type: Mapped[str] = mapped_column(REPORT_TYPE, nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Report data
    report_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    chart_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # Output
    pdf_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    csv_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Generation
    generated_by_job_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    period_start: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    period_end: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # Scheduling
    is_scheduled: Mapped[bool] = mapped_column(Boolean, default=False)
    schedule_cron: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    last_generated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    next_scheduled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_fno_report_tenant_type", "tenant_id", "report_type"),
        Index("ix_fno_report_scheduled", "is_scheduled", "next_scheduled_at"),
    )


# ════════════════════════════════════════════════════════════════════════
# 6. KML COVERAGE IMPORT
# ════════════════════════════════════════════════════════════════════════

KML_IMPORT_STATUS = SAEnum(
    "uploaded", "parsing", "imported", "failed", "partial",
    name="kml_import_status", create_type=False,
)


class FNOKMLImport(Base):
    """Tracks KML/KMZ file uploads from FNOs for coverage area bulk import."""

    __tablename__ = "fno_kml_imports"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    fno_name: Mapped[str] = mapped_column(String(100), nullable=False)
    fno_portal: Mapped[str] = mapped_column(FNO_PORTAL, nullable=False)

    # File info
    file_name: Mapped[str] = mapped_column(String(500), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    file_path: Mapped[str] = mapped_column(String(1000), nullable=False)

    # Processing
    status: Mapped[str] = mapped_column(KML_IMPORT_STATUS, nullable=False, default="uploaded")
    total_features: Mapped[int] = mapped_column(Integer, default=0)
    imported_features: Mapped[int] = mapped_column(Integer, default=0)
    skipped_features: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Bounding box from KML
    bbox_north: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 8), nullable=True)
    bbox_south: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 8), nullable=True)
    bbox_east: Mapped[Optional[Decimal]] = mapped_column(Numeric(11, 8), nullable=True)
    bbox_west: Mapped[Optional[Decimal]] = mapped_column(Numeric(11, 8), nullable=True)

    # Who uploaded
    uploaded_by: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_fno_kml_tenant_fno", "tenant_id", "fno_name"),
        Index("ix_fno_kml_status", "tenant_id", "status"),
    )


# ════════════════════════════════════════════════════════════════════════
# 7. FAULT REPORTING
# ════════════════════════════════════════════════════════════════════════

FAULT_STATUS = SAEnum(
    "submitted", "acknowledged", "investigating", "escalated",
    "resolved", "closed", "rejected",
    name="fault_status", create_type=False,
)

FAULT_SEVERITY = SAEnum(
    "low", "medium", "high", "critical",
    name="fault_severity", create_type=False,
)

FAULT_SOURCE = SAEnum(
    "customer", "fno_portal", "network_monitor", "field_tech", "system",
    name="fault_source", create_type=False,
)


class NetworkFaultReport(Base):
    """Fault reports linked to FNO, area, and optionally a specific service."""

    __tablename__ = "network_fault_reports"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)

    # Who reported
    source: Mapped[str] = mapped_column(FAULT_SOURCE, nullable=False)
    reported_by_customer_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    reported_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)

    # FNO context
    fno_name: Mapped[str] = mapped_column(String(100), nullable=False)
    fno_portal: Mapped[Optional[str]] = mapped_column(FNO_PORTAL, nullable=True)
    fno_account_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Affected service (if known). References the `网络` service's NetworkService
    # (services/网络/models.py) — resolved in Python at query time, not via a
    # cross-service FK, so this is a plain UUID column.
    service_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )

    # Location
    area_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    suburb: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    province: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    postal_code: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    gps_lat: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 8), nullable=True)
    gps_lng: Mapped[Optional[Decimal]] = mapped_column(Numeric(11, 8), nullable=True)

    # Fault details
    fault_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # outage, slow_speed, intermittent, no_signal, hardware, other
    severity: Mapped[str] = mapped_column(FAULT_SEVERITY, nullable=False, default="medium")
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Status tracking
    status: Mapped[str] = mapped_column(FAULT_STATUS, nullable=False, default="submitted")
    fno_ticket_reference: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    internal_ticket_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)

    # Resolution
    resolution_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)

    # Timestamps
    fault_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_nfr_tenant_status", "tenant_id", "status"),
        Index("ix_nfr_tenant_fno", "tenant_id", "fno_name"),
        Index("ix_nfr_tenant_severity", "tenant_id", "severity"),
        Index("ix_nfr_service", "service_id"),
        Index("ix_nfr_area", "tenant_id", "city", "suburb"),
        Index("ix_nfr_postal", "postal_code"),
    )


class NetworkFaultUpdate(Base):
    """Updates/comments on a fault report (audit trail)."""

    __tablename__ = "network_fault_updates"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fault_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("network_fault_reports.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)

    update_type: Mapped[str] = mapped_column(String(30), nullable=False)
    # status_change, comment, escalation, fno_response, resolution
    message: Mapped[str] = mapped_column(Text, nullable=False)
    old_status: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    new_status: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)

    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_nfu_fault", "fault_id", "created_at"),
    )
