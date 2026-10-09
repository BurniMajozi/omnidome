"""Tables for the 'Analytics & AI' area (research, competitor analysis, campaign analysis,
Firecrawl credit accounting). All rows are tenant scoped.

Column types are portable (Uuid / JSON with a JSONB variant) so the unit tests can run the
real queries against in-memory SQLite. New tables only: create_all never ALTERs, so any later
column change needs an explicit migration.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, Uuid, func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from services.fno_intelligence.models import Base

JSONType = JSON().with_variant(JSONB(), "postgresql")


def _id():
    return mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)


def _tenant():
    return mapped_column(Uuid(as_uuid=True), nullable=False, index=True)


def _ts():
    return mapped_column(DateTime(timezone=True), server_default=func.now())


# ── D. credit accounting ──────────────────────────────────────────────────

class AiCreditLedger(Base):
    """One row per metered Firecrawl call (credits are estimates from Firecrawl's published costs)."""
    __tablename__ = "analytics_credit_ledger"

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = _tenant()
    endpoint: Mapped[str] = mapped_column(String(40), nullable=False)  # search|scrape|scrape_json|map|crawl|extract
    credits: Mapped[int] = mapped_column(Integer, nullable=False)
    feature: Mapped[str] = mapped_column(String(30), nullable=False, default="")  # research|competitor|campaign
    ref_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid(as_uuid=True), nullable=True)
    note: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = _ts()

    __table_args__ = (Index("ix_analytics_credit_ledger_tenant_created", "tenant_id", "created_at"),)


class AiCreditLimit(Base):
    """Per-tenant override of the platform default caps (admin adjustable)."""
    __tablename__ = "analytics_credit_limits"

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    monthly_cap: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    daily_cap: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    updated_by: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid(as_uuid=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ── A. research ───────────────────────────────────────────────────────────

class AiResearchRun(Base):
    __tablename__ = "analytics_research_runs"

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = _tenant()
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid(as_uuid=True), nullable=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    depth: Mapped[str] = mapped_column(String(10), nullable=False, default="standard")
    params: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="queued")  # queued|running|done|failed
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    report: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)
    sources: Mapped[Optional[list]] = mapped_column(JSONType, nullable=True)
    credits_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    model_used: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = _ts()


# ── B. competitors ────────────────────────────────────────────────────────

class AiCompetitor(Base):
    __tablename__ = "analytics_competitors"

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = _tenant()
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    website: Mapped[str] = mapped_column(Text, nullable=False)
    pricing_page_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    promo_page_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    social_urls: Mapped[Optional[list]] = mapped_column(JSONType, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    scan_status: Mapped[str] = mapped_column(String(15), nullable=False, default="never")  # never|scanning|ok|no_data|failed
    scan_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_scanned_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Auto-scan scheduler (added by migration in database.init_tables; NULL interval = manual only)
    scan_interval_hours: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 12|24|168|720
    schedule_frequency: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)  # 12h|daily|weekly|monthly; NULL = manual only
    schedule_time: Mapped[Optional[str]] = mapped_column(String(5), nullable=True)  # HH:MM Africa/Johannesburg
    schedule_weekday: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 0=Mon..6=Sun (weekly)
    schedule_day_of_month: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 1-28 (monthly)
    next_scan_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_status: Mapped[Optional[str]] = mapped_column(String(12), nullable=True)  # queued|scanning|ok|capped|failed|blocked
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)  # tenant-level "seen" mark
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_analytics_competitor_tenant_name"),)


class AiCompetitorSnapshot(Base):
    """Immutable: never updated after insert."""
    __tablename__ = "analytics_competitor_snapshots"

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = _tenant()
    competitor_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("analytics_competitors.id", ondelete="CASCADE"), nullable=False, index=True)
    scanned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    pages: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)  # provenance per page
    plans: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    promotions: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    extraction_method: Mapped[str] = mapped_column(String(30), nullable=False, default="firecrawl_json")


class AiCompetitorChange(Base):
    __tablename__ = "analytics_competitor_changes"

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = _tenant()
    competitor_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("analytics_competitors.id", ondelete="CASCADE"), nullable=False, index=True)
    snapshot_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    previous_snapshot_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    change_type: Mapped[str] = mapped_column(String(30), nullable=False)
    subject: Mapped[str] = mapped_column(String(300), nullable=False)
    old_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    new_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    abs_change: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    pct_change: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    currency: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    detected_at: Mapped[datetime] = _ts()


# ── C. campaign analysis ──────────────────────────────────────────────────

class AiCampaignAnalysis(Base):
    __tablename__ = "analytics_campaign_analyses"

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = _tenant()
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid(as_uuid=True), nullable=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    subject: Mapped[str] = mapped_column(String(300), nullable=False)
    own_campaign_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid(as_uuid=True), nullable=True)
    competitor_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid(as_uuid=True), nullable=True)
    keywords: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    source_urls: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)  # empty = auto
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="queued")
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    aggregate: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)
    limitations: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    item_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    credits_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    run_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = _ts()


class AiCampaignItem(Base):
    __tablename__ = "analytics_campaign_items"

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = _tenant()
    analysis_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("analytics_campaign_analyses.id", ondelete="CASCADE"), nullable=False, index=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    domain: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    source_type: Mapped[str] = mapped_column(String(20), nullable=False, default="other")
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    rating: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    item_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    sentiment: Mapped[str] = mapped_column(String(10), nullable=False, default="neutral")
    sentiment_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    themes: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (UniqueConstraint("analysis_id", "url", "content_hash", name="uq_analytics_item_dedup"),)


ANALYTICS_TABLES = [
    AiCreditLedger.__table__, AiCreditLimit.__table__, AiResearchRun.__table__, AiCompetitor.__table__,
    AiCompetitorSnapshot.__table__, AiCompetitorChange.__table__, AiCampaignAnalysis.__table__,
    AiCampaignItem.__table__,
]
