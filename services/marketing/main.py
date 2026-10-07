"""
OmniDome Marketing Service
===========================
Campaign management · Email delivery · Lead scoring · Automation · Attribution
Social Media · WhatsApp · Ad Campaigns · Comment Automation · Webhooks

Port: 8014
"""

from datetime import datetime, timedelta, date, timezone
from decimal import Decimal
import asyncio
import json
import logging
import os
import httpx
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional
import uuid

from fastapi import Body, Depends, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text, select, insert, update, delete, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from services.common import agentmail as agentmail_client
from services.common.auth import AuthContext, get_auth_context, get_current_tenant_id
from services.common.db import get_engine, get_async_session, run_with_db_retry
from services.common.entitlements import EntitlementGuard
from services.common.middleware import configure_production
from services.common import suppression as suppression_lib
from services.common.background_tasks import schedule_background
from services.marketing import security as sec
from services.marketing import zernio_posts as _zp
from services.marketing.zernio_client import _guess_media_type
from services.marketing.security import require_marketing_admin, require_marketing_write
from services.marketing.database import (
    get_session,
    init_tables,
    SocialMediaAccount,
    SocialPost,
    SocialInboxMessage,
    SocialAnalytics,
    WhatsAppContact,
    WhatsAppBroadcast,
    WhatsAppBroadcastRecipient,
    AdCampaign,
    CommentAutomation,
    SocialWebhookEvent,
    TraditionalMediaCampaign,
)

logger = logging.getLogger("marketing")

app = FastAPI(title="OmniDome Marketing Service", version="2.0.0")
# NOTE: /social/webhooks/zernio/inbound is public at the middleware layer
# because Zernio (external) cannot send X-User-Id. Its authentication is the
# X-Zernio-Signature HMAC check inside the route itself (Sep 2026).
guard = EntitlementGuard(
    module_id="marketing",
    public_paths={"/social/webhooks/zernio/inbound", "/email/webhook", "/email/unsubscribe"},
)

configure_production(app)


@asynccontextmanager
async def lifespan(app: FastAPI):
    guard.ensure_startup()
    import anyio
    await run_with_db_retry(
        lambda: anyio.to_thread.run_sync(init_tables),
        logger=logger,
    )
    try:
        await anyio.to_thread.run_sync(lambda: _ensure_marketing_tables(get_engine()))
    except Exception as exc:  # noqa: BLE001 - lazy per-request ensure still runs
        logger.warning("marketing schema ensure at startup failed: %s", exc)
    logger.info("Marketing service started — tables initialized")
    yield
    logger.info("Marketing service shutting down")


app.router.lifespan_context = lifespan


@app.middleware("http")
async def entitlement_middleware(request, call_next):
    return await guard.middleware(request, call_next)


# ─────────────────────────────── Pydantic Models ───────────────────────────────


def _blank_to_none(v):
    """'' / whitespace from a form field means "not provided"."""
    if isinstance(v, str) and not v.strip():
        return None
    return v


class CampaignCreate(BaseModel):
    """Empty-string dates/ids from the Create Campaign form are normalised to null (they used to
    422 on datetime parsing). `audience_id` is an alias of `audience_segment_id`: the audience
    (segment) whose members the campaign's sends are addressed to."""
    name: str
    channel: str = Field(..., description="email | social | search | display | sms | whatsapp")
    description: Optional[str] = None
    budget_zar: Decimal = Decimal("0")
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    audience_segment_id: Optional[uuid.UUID] = None
    audience_id: Optional[uuid.UUID] = None

    @field_validator("start_date", "end_date", "audience_segment_id", "audience_id", "description", mode="before")
    @classmethod
    def _blank_none(cls, v):
        return _blank_to_none(v)

    @field_validator("budget_zar", mode="before")
    @classmethod
    def _blank_budget(cls, v):
        v = _blank_to_none(v)
        return Decimal("0") if v is None else v

    @field_validator("budget_zar")
    @classmethod
    def _budget_nonneg(cls, v):
        if v < 0:
            raise ValueError("budget_zar must be >= 0")
        return v


class CampaignUpdate(BaseModel):
    name: Optional[str] = None
    channel: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    budget_zar: Optional[Decimal] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    audience_segment_id: Optional[uuid.UUID] = None
    audience_id: Optional[uuid.UUID] = None

    @field_validator("start_date", "end_date", "audience_segment_id", "audience_id", "budget_zar", mode="before")
    @classmethod
    def _blank_none(cls, v):
        return _blank_to_none(v)


class CampaignOut(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    channel: str
    status: str
    description: Optional[str]
    budget_zar: Decimal
    start_date: Optional[datetime]
    end_date: Optional[datetime]
    audience_segment_id: Optional[uuid.UUID] = None
    audience_id: Optional[uuid.UUID] = None
    audience_name: Optional[str] = None
    audience_size: Optional[int] = None
    total_sent: int
    total_delivered: int
    total_opened: int
    total_clicked: int
    total_conversions: int
    created_at: datetime


def _campaign_out(row) -> Dict[str, Any]:
    d = dict(row)
    d["audience_id"] = d.get("audience_segment_id")
    return d


class EmailSendRequest(BaseModel):
    campaign_id: Optional[uuid.UUID] = None
    template_id: Optional[uuid.UUID] = None
    subject: str = Field(..., min_length=1, max_length=500, pattern=r"^[^\r\n]*$")
    body_html: str = Field(..., max_length=500_000)
    recipients: List[str] = Field(default_factory=list, max_length=5000,
                                  description="Email addresses. Omit (with campaign_id) to send to the campaign's audience")
    from_name: Optional[str] = "OmniDome"
    from_email: Optional[str] = None
    reply_to: Optional[str] = None
    tags: List[str] = Field(default_factory=list)


class EmailSendResponse(BaseModel):
    batch_id: uuid.UUID
    campaign_id: Optional[uuid.UUID] = None
    total_queued: int
    status: str
    total_suppressed: int = 0
    total_invalid: int = 0


class AgentMailSignUpRequest(BaseModel):
    human_email: str
    username: str


class AgentMailVerifyRequest(BaseModel):
    otp_code: str


class AgentMailConfigRequest(BaseModel):
    api_key: Optional[str] = None
    inbox_id: Optional[str] = None


class LeadScoreUpdate(BaseModel):
    contact_id: uuid.UUID
    score_delta: int = Field(..., description="Points to add (positive) or remove (negative)")
    reason: str


_SEGMENT_TYPES = {"homes", "businesses", "custom"}
_SEGMENT_PLATFORMS = {"google_ads", "meta", "linkedin", "custom"}


class AudienceSegmentCreate(BaseModel):
    """rules: {type, source, source_id, source_name, platform, areas | businesses | regions}
    (SPEC-marketing-audiences.md). Homes audiences carry areas only, never addresses."""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    rules: Dict[str, Any] = Field(default_factory=dict, description="JSON audience definition")
    member_count: Optional[int] = Field(None, ge=0)


class AutomationCreate(BaseModel):
    name: str
    trigger_type: str = Field(..., description="event | schedule | lead_score")
    trigger_config: Dict[str, Any] = Field(default_factory=dict)
    actions: List[Dict[str, Any]] = Field(default_factory=list)
    is_active: bool = True


class TemplateCreate(BaseModel):
    name: str
    subject: str
    body_html: str
    category: str = "promotional"


class TemplateUpdate(BaseModel):
    name: Optional[str] = None
    subject: Optional[str] = None
    body_html: Optional[str] = None
    category: Optional[str] = None


class JourneyCreate(BaseModel):
    name: str
    description: Optional[str] = None
    trigger_type: str = "signup"
    status: str = "draft"
    steps: List[Dict[str, Any]] = Field(default_factory=list)


class JourneyUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    trigger_type: Optional[str] = None
    status: Optional[str] = None
    steps: Optional[List[Dict[str, Any]]] = None


class ABTestCreate(BaseModel):
    campaign_id: uuid.UUID
    variant_a: Dict[str, Any] = Field(..., description="Subject/body for variant A")
    variant_b: Dict[str, Any] = Field(..., description="Subject/body for variant B")
    split_pct: int = Field(50, ge=10, le=90)
    metric: str = Field("open_rate", description="open_rate | ctr | conversions")
    duration_hours: int = 24


class DashboardMetrics(BaseModel):
    active_campaigns: int
    email_delivery_rate: float
    lead_conversion_rate: float
    marketing_roi: float
    total_leads: int
    total_mql: int
    total_sql: int
    emails_sent_mtd: int
    emails_delivered_mtd: int
    emails_opened_mtd: int
    bounce_rate: float
    open_rate: float


# ──────────────── New Pydantic Models for Social/WhatsApp/Ads ────────────────


# -- Social Media Account --
class SocialAccountCreate(BaseModel):
    platform: str
    account_name: Optional[str] = None
    account_handle: Optional[str] = None
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    token_expires_at: Optional[datetime] = None
    profile_data: Optional[Dict[str, Any]] = None


class SocialAccountUpdate(BaseModel):
    account_name: Optional[str] = None
    account_handle: Optional[str] = None
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    token_expires_at: Optional[datetime] = None
    status: Optional[str] = None
    profile_data: Optional[Dict[str, Any]] = None


class SocialAccountOut(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    platform: str
    account_name: Optional[str]
    account_handle: Optional[str]
    status: str
    profile_data: Optional[Dict[str, Any]]
    created_at: datetime
    updated_at: datetime


class OAuthUrlResponse(BaseModel):
    platform: str
    auth_url: str
    state: Optional[str] = None  # signed connection state; echoed back by the callback page
    expires_in: Optional[int] = None


class TokenRefreshResponse(BaseModel):
    status: str
    expires_at: Optional[datetime] = None


# -- Social Post --
class SocialPostCreate(BaseModel):
    """Create/schedule/queue/draft/publish a social post.

    `status` keeps the legacy values the UI sends (draft | scheduled | published); intent is
    derived: published -> publish now, scheduled -> schedule (or queue when queue_id is set),
    draft -> saved in OmniDome only (set provider_draft=true to also store it as a provider draft).
    `account_id` (legacy credentials-table id) is now OPTIONAL: provider accounts are resolved from
    `account_ids` (Zernio account ids of THIS tenant) or by `platforms`.
    """
    account_id: Optional[uuid.UUID] = None
    account_ids: Optional[List[str]] = None
    campaign_id: Optional[uuid.UUID] = None
    content: Optional[str] = None
    media_urls: Optional[List[str]] = None
    media_items: Optional[List[Dict[str, Any]]] = None
    platforms: Optional[List[str]] = None
    status: str = "draft"
    scheduled_for: Optional[datetime] = None
    timezone: Optional[str] = None
    queue_id: Optional[uuid.UUID] = None
    provider_draft: bool = False

    @field_validator("account_id", "campaign_id", "scheduled_for", "queue_id", "timezone", "content", mode="before")
    @classmethod
    def _blank_to_none(cls, v):  # '' from a form field must mean "not provided", not a 422
        from services.marketing.zernio_posts import blank_to_none
        return blank_to_none(v)

    @field_validator("status", mode="before")
    @classmethod
    def _norm_status(cls, v):
        from services.marketing.zernio_posts import norm_status
        return norm_status(v if v is not None else "draft")


class SocialPostUpdate(BaseModel):
    content: Optional[str] = None
    media_urls: Optional[List[str]] = None
    status: Optional[str] = None
    scheduled_for: Optional[datetime] = None

    @field_validator("scheduled_for", mode="before")
    @classmethod
    def _blank_to_none(cls, v):
        from services.marketing.zernio_posts import blank_to_none
        return blank_to_none(v)

    @field_validator("status", mode="before")
    @classmethod
    def _norm_status(cls, v):
        if v is None:
            return v
        from services.marketing.zernio_posts import norm_status
        return norm_status(v)


class SocialPostOut(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    account_id: uuid.UUID
    campaign_id: Optional[uuid.UUID]
    content: Optional[str]
    media_urls: Optional[List[str]]
    platforms: Optional[List[str]]
    status: str
    scheduled_for: Optional[datetime]
    published_at: Optional[datetime]
    platform_post_ids: Optional[Dict[str, str]]
    engagement_data: Optional[Dict[str, Any]]
    created_at: datetime
    updated_at: datetime


class CrossPostRequest(BaseModel):
    account_ids: List[uuid.UUID]
    content: Optional[str] = None
    media_urls: Optional[List[str]] = None
    scheduled_for: Optional[datetime] = None


class CrossPostResponse(BaseModel):
    posts: List[SocialPostOut]
    total_created: int


# -- Social Inbox --
class InboxReplyRequest(BaseModel):
    content: str


class InboxMessageOut(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    account_id: uuid.UUID
    platform: str
    message_type: str
    external_id: Optional[str]
    sender_name: Optional[str]
    sender_handle: Optional[str]
    content: Optional[str]
    status: str
    sentiment: Optional[str]
    created_at: datetime


class UnreadCountResponse(BaseModel):
    unread_count: int


# -- Social Analytics --
class AccountAnalyticsOut(BaseModel):
    account_id: uuid.UUID
    platform: str
    metric_date: date
    followers: int
    following: int
    posts_count: int
    impressions: int
    reach: int
    engagement_rate: Optional[Decimal]
    likes_total: int
    comments_total: int
    shares_total: int
    profile_views: int
    website_clicks: int


class PlatformAnalyticsOut(BaseModel):
    platform: str
    total_followers: int
    total_impressions: int
    total_reach: int
    avg_engagement_rate: Optional[Decimal]
    total_likes: int
    total_comments: int
    total_shares: int


class EngagementSummaryOut(BaseModel):
    total_impressions: int
    total_reach: int
    total_likes: int
    total_comments: int
    total_shares: int
    avg_engagement_rate: Optional[Decimal]
    period_start: Optional[date]
    period_end: Optional[date]


class BestTimeToPostOut(BaseModel):
    platform: str
    best_day: Optional[str]
    best_hour: Optional[int]
    recommendations: Optional[Dict[str, Any]]


# -- WhatsApp --
class WhatsAppContactCreate(BaseModel):
    name: Optional[str] = None
    phone_number: str
    email: Optional[str] = None
    tags: Optional[List[str]] = None
    custom_fields: Optional[Dict[str, Any]] = None
    opt_in_status: bool = False


class WhatsAppContactOut(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    name: Optional[str]
    phone_number: str
    email: Optional[str]
    tags: Optional[List[str]]
    opt_in_status: bool
    created_at: datetime


class BulkImportRequest(BaseModel):
    contacts: List[WhatsAppContactCreate]


class BulkImportResponse(BaseModel):
    imported: int
    errors: List[Dict[str, Any]]


class WhatsAppBroadcastCreate(BaseModel):
    name: Optional[str] = None
    template_name: Optional[str] = None
    content: Optional[str] = None
    media_url: Optional[str] = None
    contact_ids: List[uuid.UUID] = Field(default_factory=list)
    scheduled_for: Optional[datetime] = None


class WhatsAppBroadcastOut(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    name: Optional[str]
    template_name: Optional[str]
    content: Optional[str]
    recipient_count: int
    sent_count: int
    delivered_count: int
    read_count: int
    failed_count: int
    status: str
    created_at: datetime


class BroadcastSendResponse(BaseModel):
    broadcast_id: uuid.UUID
    status: str
    recipient_count: int


class BroadcastStatsOut(BaseModel):
    broadcast_id: uuid.UUID
    name: Optional[str]
    recipient_count: int
    sent_count: int
    delivered_count: int
    read_count: int
    failed_count: int
    delivery_rate: float
    read_rate: float


# -- Ad Campaigns --
class AdCampaignCreate(BaseModel):
    name: str
    platform: str
    objective: str
    budget_zar: Decimal = Decimal("0")
    daily_budget_zar: Optional[Decimal] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    targeting: Optional[Dict[str, Any]] = None
    creative: Optional[Dict[str, Any]] = None


class TraditionalCampaignCreate(BaseModel):
    medium: str  # radio, billboard, ooh_screen
    name: str
    category: Optional[str] = None
    reach: Optional[str] = None
    spots_booked: int = 0
    impressions: int = 0
    spend_zar: Decimal = Decimal("0")
    leads_generated: int = 0
    metrics: Optional[Dict[str, Any]] = None
    period_month: Optional[date] = None


class AdCampaignUpdate(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = None
    budget_zar: Optional[Decimal] = None
    daily_budget_zar: Optional[Decimal] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    targeting: Optional[Dict[str, Any]] = None
    creative: Optional[Dict[str, Any]] = None


class AdCampaignOut(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    platform: str
    objective: str
    status: str
    budget_zar: Decimal
    daily_budget_zar: Optional[Decimal]
    start_date: Optional[datetime]
    end_date: Optional[datetime]
    impressions: int
    clicks: int
    conversions: int
    spend_zar: Decimal
    roas: Optional[Decimal]
    created_at: datetime
    updated_at: datetime


class AdAnalyticsOut(BaseModel):
    campaign_id: uuid.UUID
    name: str
    platform: str
    impressions: int
    clicks: int
    conversions: int
    spend_zar: Decimal
    ctr: float
    cpc: Optional[Decimal]
    roas: Optional[Decimal]


# -- Comment Automation --
class CommentAutomationCreate(BaseModel):
    name: str
    account_id: uuid.UUID
    trigger_type: str
    trigger_keywords: Optional[List[str]] = None
    response_template: Optional[str] = None
    is_active: bool = True


class CommentAutomationUpdate(BaseModel):
    name: Optional[str] = None
    trigger_type: Optional[str] = None
    trigger_keywords: Optional[List[str]] = None
    response_template: Optional[str] = None
    is_active: Optional[bool] = None


class CommentAutomationOut(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    account_id: uuid.UUID
    trigger_type: str
    trigger_keywords: Optional[List[str]]
    response_template: Optional[str]
    is_active: bool
    total_triggered: int
    total_replied: int
    created_at: datetime
    updated_at: datetime


# -- Webhook --
class WebhookResponse(BaseModel):
    status: str
    event_id: Optional[uuid.UUID] = None


# -- Call Centre Integration --
class Customer360Out(BaseModel):
    customer_id: uuid.UUID
    recent_interactions: List[Dict[str, Any]]
    sentiment_summary: Dict[str, int]
    total_interactions: int


class CreateTicketRequest(BaseModel):
    subject: Optional[str] = None
    priority: str = "medium"
    assignee_id: Optional[uuid.UUID] = None


class CreateTicketResponse(BaseModel):
    ticket_id: Optional[str] = None
    status: str
    message: str


# ─────────────────────────── Helper ───────────────────────────


def _ensure_marketing_tables(engine) -> None:
    """Create marketing tables if they don't exist (idempotent)."""
    ddl = """
    CREATE TABLE IF NOT EXISTS marketing_campaigns (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        tenant_id UUID NOT NULL REFERENCES tenants(id),
        name VARCHAR(255) NOT NULL,
        channel VARCHAR(50) NOT NULL DEFAULT 'email',
        status VARCHAR(30) NOT NULL DEFAULT 'draft',
        description TEXT,
        budget_zar NUMERIC(14,2) DEFAULT 0,
        start_date TIMESTAMPTZ,
        end_date TIMESTAMPTZ,
        audience_segment_id UUID,
        total_sent INT DEFAULT 0,
        total_delivered INT DEFAULT 0,
        total_opened INT DEFAULT 0,
        total_clicked INT DEFAULT 0,
        total_conversions INT DEFAULT 0,
        created_at TIMESTAMPTZ DEFAULT now(),
        updated_at TIMESTAMPTZ DEFAULT now()
    );

    CREATE TABLE IF NOT EXISTS marketing_email_batches (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        tenant_id UUID NOT NULL REFERENCES tenants(id),
        campaign_id UUID NOT NULL REFERENCES marketing_campaigns(id),
        subject VARCHAR(500),
        from_name VARCHAR(255),
        from_email VARCHAR(255),
        total_queued INT DEFAULT 0,
        total_sent INT DEFAULT 0,
        total_delivered INT DEFAULT 0,
        total_bounced INT DEFAULT 0,
        total_opened INT DEFAULT 0,
        total_clicked INT DEFAULT 0,
        status VARCHAR(30) DEFAULT 'queued',
        created_at TIMESTAMPTZ DEFAULT now()
    );

    CREATE TABLE IF NOT EXISTS marketing_email_events (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        tenant_id UUID NOT NULL REFERENCES tenants(id),
        batch_id UUID NOT NULL REFERENCES marketing_email_batches(id),
        recipient_email VARCHAR(320),
        event_type VARCHAR(30) NOT NULL,
        event_data JSONB DEFAULT '{}',
        created_at TIMESTAMPTZ DEFAULT now()
    );

    CREATE TABLE IF NOT EXISTS marketing_templates (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        tenant_id UUID NOT NULL REFERENCES tenants(id),
        name VARCHAR(255) NOT NULL,
        subject VARCHAR(500),
        body_html TEXT,
        category VARCHAR(50) DEFAULT 'promotional',
        created_at TIMESTAMPTZ DEFAULT now(),
        updated_at TIMESTAMPTZ DEFAULT now()
    );

    CREATE TABLE IF NOT EXISTS marketing_email_journeys (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        tenant_id UUID NOT NULL REFERENCES tenants(id),
        name VARCHAR(255) NOT NULL,
        description TEXT,
        trigger_type VARCHAR(100) DEFAULT 'signup',
        status VARCHAR(50) DEFAULT 'draft',
        steps JSONB DEFAULT '[]',
        total_enrolled INT DEFAULT 0,
        total_completed INT DEFAULT 0,
        created_at TIMESTAMPTZ DEFAULT now(),
        updated_at TIMESTAMPTZ DEFAULT now()
    );

    CREATE TABLE IF NOT EXISTS marketing_audience_segments (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        tenant_id UUID NOT NULL REFERENCES tenants(id),
        name VARCHAR(255) NOT NULL,
        description TEXT,
        rules JSONB DEFAULT '{}',
        member_count INT DEFAULT 0,
        created_at TIMESTAMPTZ DEFAULT now()
    );

    CREATE TABLE IF NOT EXISTS marketing_lead_scores (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        tenant_id UUID NOT NULL REFERENCES tenants(id),
        contact_id UUID NOT NULL,
        score INT DEFAULT 0,
        last_scored_at TIMESTAMPTZ DEFAULT now(),
        UNIQUE (tenant_id, contact_id)
    );

    CREATE TABLE IF NOT EXISTS marketing_automations (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        tenant_id UUID NOT NULL REFERENCES tenants(id),
        name VARCHAR(255) NOT NULL,
        trigger_type VARCHAR(50) NOT NULL,
        trigger_config JSONB DEFAULT '{}',
        actions JSONB DEFAULT '[]',
        is_active BOOLEAN DEFAULT TRUE,
        total_triggered INT DEFAULT 0,
        created_at TIMESTAMPTZ DEFAULT now()
    );

    CREATE TABLE IF NOT EXISTS marketing_ab_tests (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        tenant_id UUID NOT NULL REFERENCES tenants(id),
        campaign_id UUID NOT NULL REFERENCES marketing_campaigns(id),
        variant_a JSONB NOT NULL,
        variant_b JSONB NOT NULL,
        split_pct INT DEFAULT 50,
        metric VARCHAR(30) DEFAULT 'open_rate',
        duration_hours INT DEFAULT 24,
        status VARCHAR(30) DEFAULT 'running',
        winner VARCHAR(10),
        created_at TIMESTAMPTZ DEFAULT now()
    );

    -- ── Zernio analytics (DB-backed dashboards, filled by the sync worker) ──
    -- Maps each tenant (customer) to its Zernio profile. The worker iterates
    -- rows here; dashboards read the tables below and never call Zernio live.
    CREATE TABLE IF NOT EXISTS marketing_tenant_profiles (
        tenant_id UUID PRIMARY KEY REFERENCES tenants(id),
        zernio_profile_id VARCHAR(64) NOT NULL,
        created_at TIMESTAMPTZ DEFAULT now(),
        updated_at TIMESTAMPTZ DEFAULT now()
    );

    -- Posting queues (recurring weekly slots a post drops into). Slots are a
    -- JSONB array of {day:0-6 (0=Sun), time:"HH:MM"}; times are in `timezone`.
    CREATE TABLE IF NOT EXISTS marketing_post_queues (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        tenant_id UUID NOT NULL REFERENCES tenants(id),
        profile_id VARCHAR(64),
        name VARCHAR(200) NOT NULL,
        description TEXT,
        status VARCHAR(20) NOT NULL DEFAULT 'active',
        timezone VARCHAR(64) DEFAULT 'UTC',
        slots JSONB DEFAULT '[]',
        created_at TIMESTAMPTZ DEFAULT now(),
        updated_at TIMESTAMPTZ DEFAULT now()
    );

    -- Account → tenant map (the mapping webhooks route on). Written by the
    -- connect flow and by account.connected / account.disconnected events.
    CREATE TABLE IF NOT EXISTS marketing_connected_accounts (
        account_id VARCHAR(128) PRIMARY KEY,
        tenant_id UUID NOT NULL REFERENCES tenants(id),
        profile_id VARCHAR(64) NOT NULL,
        platform VARCHAR(40),
        username VARCHAR(255),
        status VARCHAR(20) DEFAULT 'connected',
        issues JSONB DEFAULT '[]',
        connected_at TIMESTAMPTZ DEFAULT now(),
        disconnected_at TIMESTAMPTZ,
        updated_at TIMESTAMPTZ DEFAULT now()
    );

    CREATE TABLE IF NOT EXISTS marketing_post_analytics (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        tenant_id UUID NOT NULL REFERENCES tenants(id),
        profile_id VARCHAR(64) NOT NULL,
        post_id VARCHAR(128) NOT NULL,
        platform VARCHAR(40) NOT NULL,
        published_at TIMESTAMPTZ,
        platform_post_url TEXT,
        source VARCHAR(20) DEFAULT 'all',
        likes INT DEFAULT 0,
        comments INT DEFAULT 0,
        impressions INT DEFAULT 0,
        reach INT DEFAULT 0,
        shares INT DEFAULT 0,
        saves INT DEFAULT 0,
        clicks INT DEFAULT 0,
        views INT DEFAULT 0,
        sync_status VARCHAR(20) DEFAULT 'synced',
        raw JSONB DEFAULT '{}',
        last_updated TIMESTAMPTZ DEFAULT now(),
        UNIQUE (tenant_id, post_id, platform)
    );

    CREATE TABLE IF NOT EXISTS marketing_daily_metrics (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        tenant_id UUID NOT NULL REFERENCES tenants(id),
        profile_id VARCHAR(64) NOT NULL,
        metric_date DATE NOT NULL,
        attribution VARCHAR(10) NOT NULL DEFAULT 'publish',
        platform VARCHAR(40) NOT NULL DEFAULT 'all',
        post_count INT DEFAULT 0,
        impressions INT DEFAULT 0,
        reach INT DEFAULT 0,
        likes INT DEFAULT 0,
        comments INT DEFAULT 0,
        shares INT DEFAULT 0,
        saves INT DEFAULT 0,
        clicks INT DEFAULT 0,
        views INT DEFAULT 0,
        updated_at TIMESTAMPTZ DEFAULT now(),
        UNIQUE (tenant_id, metric_date, attribution, platform)
    );

    CREATE TABLE IF NOT EXISTS marketing_follower_stats (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        tenant_id UUID NOT NULL REFERENCES tenants(id),
        profile_id VARCHAR(64) NOT NULL,
        account_id VARCHAR(128) NOT NULL,
        platform VARCHAR(40),
        stat_date DATE NOT NULL,
        granularity VARCHAR(10) NOT NULL DEFAULT 'daily',
        followers INT DEFAULT 0,
        growth INT DEFAULT 0,
        updated_at TIMESTAMPTZ DEFAULT now(),
        UNIQUE (tenant_id, account_id, stat_date, granularity)
    );

    CREATE TABLE IF NOT EXISTS marketing_analytics_sync_state (
        tenant_id UUID PRIMARY KEY REFERENCES tenants(id),
        profile_id VARCHAR(64) NOT NULL,
        last_hot_sync TIMESTAMPTZ,
        last_longtail_sync TIMESTAMPTZ,
        last_follower_sync TIMESTAMPTZ,
        backfilled_at TIMESTAMPTZ,
        last_error TEXT,
        updated_at TIMESTAMPTZ DEFAULT now()
    );

    CREATE INDEX IF NOT EXISTS idx_mkt_campaigns_tenant ON marketing_campaigns(tenant_id);
    CREATE INDEX IF NOT EXISTS idx_mkt_batches_campaign ON marketing_email_batches(campaign_id);
    CREATE INDEX IF NOT EXISTS idx_mkt_events_batch ON marketing_email_events(batch_id);
    CREATE INDEX IF NOT EXISTS idx_mkt_lead_scores_tenant ON marketing_lead_scores(tenant_id, contact_id);
    CREATE INDEX IF NOT EXISTS idx_mkt_post_analytics_tenant ON marketing_post_analytics(tenant_id, published_at DESC);
    CREATE INDEX IF NOT EXISTS idx_mkt_daily_metrics_tenant ON marketing_daily_metrics(tenant_id, attribution, metric_date);
    CREATE INDEX IF NOT EXISTS idx_mkt_follower_stats_tenant ON marketing_follower_stats(tenant_id, granularity, stat_date);
    CREATE INDEX IF NOT EXISTS idx_mkt_conn_accounts_tenant ON marketing_connected_accounts(tenant_id);
    CREATE INDEX IF NOT EXISTS idx_mkt_conn_accounts_profile ON marketing_connected_accounts(profile_id);
    CREATE INDEX IF NOT EXISTS idx_mkt_queues_tenant ON marketing_post_queues(tenant_id);
    ALTER TABLE marketing_audience_segments ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT now();
    """
    with engine.begin() as conn:
        conn.execute(text(ddl))
    sec.ensure_hardening_schema(engine)


# ─────────────────────────── Health ─────────────────────────


@app.get("/health")
async def health():
    return {"status": "ok", "service": "marketing"}


# ─────────────────────────── Campaigns ─────────────────────────


def _audience_for_tenant(conn, tenant_id: uuid.UUID, audience_id: uuid.UUID):
    row = conn.execute(
        text("SELECT id, name, rules, member_count FROM marketing_audience_segments WHERE id = :id AND tenant_id = :tid"),
        {"id": str(audience_id), "tid": str(tenant_id)},
    ).mappings().first()
    if not row:
        raise HTTPException(422, "Audience not found in this workspace")
    return row


def _check_dates(start, end) -> None:
    if start and end and end < start:
        raise HTTPException(422, "end_date must be on or after start_date")


@app.get("/campaigns", response_model=List[CampaignOut])
async def list_campaigns(
    channel: Optional[str] = None,
    campaign_status: Optional[str] = Query(None, alias="status"),
    audience_id: Optional[uuid.UUID] = None,
    limit: int = 50,
    offset: int = 0,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    engine = get_engine()
    _ensure_marketing_tables(engine)
    filters = "WHERE c.tenant_id = :tid"
    params: Dict[str, Any] = {"tid": str(tenant_id), "lim": limit, "off": offset}
    if channel:
        filters += " AND c.channel = :ch"
        params["ch"] = channel
    if campaign_status:
        filters += " AND c.status = :st"
        params["st"] = campaign_status
    if audience_id:
        filters += " AND c.audience_segment_id = :aid"
        params["aid"] = str(audience_id)
    with engine.connect() as conn:
        rows = conn.execute(
            text(f"""SELECT c.*, s.name AS audience_name, s.member_count AS audience_size
                       FROM marketing_campaigns c
                       LEFT JOIN marketing_audience_segments s ON s.id = c.audience_segment_id AND s.tenant_id = c.tenant_id
                       {filters} ORDER BY c.created_at DESC LIMIT :lim OFFSET :off"""),
            params,
        ).mappings().all()
    return [_campaign_out(r) for r in rows]


@app.post("/campaigns", response_model=CampaignOut, status_code=201, dependencies=[Depends(require_marketing_write)])
async def create_campaign(
    body: CampaignCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    if body.channel not in sec.CAMPAIGN_CHANNELS:
        raise HTTPException(422, f"channel must be one of {sorted(sec.CAMPAIGN_CHANNELS)}")
    _check_dates(body.start_date, body.end_date)
    audience = body.audience_segment_id or body.audience_id
    engine = get_engine()
    _ensure_marketing_tables(engine)
    cid = uuid.uuid4()
    with engine.begin() as conn:
        if audience:
            _audience_for_tenant(conn, tenant_id, audience)
        conn.execute(
            text("""
                INSERT INTO marketing_campaigns
                    (id, tenant_id, name, channel, status, description, budget_zar, start_date, end_date, audience_segment_id)
                VALUES
                    (:id, :tid, :name, :ch, :status, :desc, :budget, :sd, :ed, :asid)
            """),
            {
                "id": str(cid),
                "tid": str(tenant_id),
                "name": body.name,
                "ch": body.channel,
                "status": "draft",
                "desc": body.description,
                "budget": float(body.budget_zar) if body.budget_zar is not None else 0.0,
                "sd": body.start_date,
                "ed": body.end_date,
                "asid": str(audience) if audience else None,
            },
        )
        row = conn.execute(
            text("""SELECT c.*, s.name AS audience_name, s.member_count AS audience_size
                      FROM marketing_campaigns c
                      LEFT JOIN marketing_audience_segments s ON s.id = c.audience_segment_id AND s.tenant_id = c.tenant_id
                     WHERE c.id = :id AND c.tenant_id = :tid"""),
            {"id": str(cid), "tid": str(tenant_id)},
        ).mappings().first()
    return _campaign_out(row)


@app.patch("/campaigns/{campaign_id}", response_model=CampaignOut, dependencies=[Depends(require_marketing_write)])
async def update_campaign(
    campaign_id: uuid.UUID,
    body: CampaignUpdate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    engine = get_engine()
    sets = []
    params: Dict[str, Any] = {"cid": str(campaign_id), "tid": str(tenant_id)}
    changes = body.model_dump(exclude_unset=True)
    # audience_id is an alias for audience_segment_id; either may be set to null to clear the audience
    if "audience_id" in changes:
        aid = changes.pop("audience_id")
        changes.setdefault("audience_segment_id", aid)
    if changes.get("channel") is not None and changes["channel"] not in sec.CAMPAIGN_CHANNELS:
        raise HTTPException(422, f"channel must be one of {sorted(sec.CAMPAIGN_CHANNELS)}")
    if "status" in changes and changes["status"] not in sec.CAMPAIGN_STATUSES:
        raise HTTPException(422, f"status must be one of {sorted(sec.CAMPAIGN_STATUSES)}")
    _check_dates(changes.get("start_date"), changes.get("end_date"))
    for field, val in changes.items():
        sets.append(f"{field} = :{field}")
        if field == "audience_segment_id":
            params[field] = str(val) if val else None
        else:
            params[field] = float(val) if isinstance(val, Decimal) else val
    if not sets:
        raise HTTPException(400, "No fields to update")
    sets.append("updated_at = now()")
    where = "id = :cid AND tenant_id = :tid"
    with engine.begin() as conn:
        if changes.get("audience_segment_id"):
            _audience_for_tenant(conn, tenant_id, changes["audience_segment_id"])
        if "status" in changes:
            cur = conn.execute(
                text("SELECT status FROM marketing_campaigns WHERE id = :cid AND tenant_id = :tid FOR UPDATE"),
                {"cid": params["cid"], "tid": params["tid"]},
            ).first()
            if not cur:
                raise HTTPException(404, "Campaign not found")
            if not sec.transition_allowed(str(cur[0]), changes["status"]):
                raise HTTPException(409, f"Invalid status transition {cur[0]} -> {changes['status']}")
        result = conn.execute(
            text(f"UPDATE marketing_campaigns SET {', '.join(sets)} WHERE {where} RETURNING *"),
            params,
        ).mappings().first()
    if not result:
        raise HTTPException(404, "Campaign not found")
    return _campaign_out(result)


@app.get("/campaigns/{campaign_id}/audience", response_model=Dict[str, Any])
async def get_campaign_audience(
    campaign_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """The audience a campaign targets and how many contactable members it resolves to right now
    (emails for email sends, phones for SMS/WhatsApp). Homes audiences hold areas only and resolve to 0."""
    from services.marketing import audience_members as am

    engine = get_engine()
    _ensure_marketing_tables(engine)
    with engine.connect() as conn:
        camp = conn.execute(
            text("SELECT id, channel, audience_segment_id FROM marketing_campaigns WHERE id = :cid AND tenant_id = :tid"),
            {"cid": str(campaign_id), "tid": str(tenant_id)},
        ).mappings().first()
        if not camp:
            raise HTTPException(404, "Campaign not found")
        if not camp["audience_segment_id"]:
            return {"campaign_id": str(campaign_id), "audience": None, "emails": 0, "phones": 0, "note": "No audience selected"}
        seg = _audience_for_tenant(conn, tenant_id, camp["audience_segment_id"])
    members = am.resolve_members(seg["rules"] or {})
    return {
        "campaign_id": str(campaign_id),
        "audience": {"id": str(seg["id"]), "name": seg["name"], "type": (seg["rules"] or {}).get("type", "custom")},
        "emails": len(members["emails"]),
        "phones": len(members["phones"]),
        "skipped_without_contact": members["skipped"],
        "note": members["note"],
    }


@app.delete("/campaigns/{campaign_id}", status_code=204, dependencies=[Depends(require_marketing_write)])
async def delete_campaign(
    campaign_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM marketing_campaigns WHERE id = :cid AND tenant_id = :tid"),
            {"cid": str(campaign_id), "tid": str(tenant_id)},
        )


# ─────────────────────── Email Delivery ───────────────────────


def _tenant_agentmail_creds(tenant_id: Optional[uuid.UUID]):
    """Tenant's own AgentMail credentials (encrypted table) or None -> platform env default."""
    if not tenant_id:
        return None
    try:
        with get_engine().begin() as conn:
            return agentmail_client.load_creds_sync(conn, tenant_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("tenant AgentMail creds lookup failed (using platform default): %s", exc)
        return None


def _email_provider_configured(tenant_id: Optional[uuid.UUID] = None) -> bool:
    """AgentMail is the configured ESP: tenant key first, else platform env."""
    return agentmail_client.is_configured(_tenant_agentmail_creds(tenant_id))


async def _send_one_email(
    *,
    to_email: str,
    subject: str,
    body_html: str,
    from_name: Optional[str],
    from_email: Optional[str],
    reply_to: Optional[str],
    tenant_id: Optional[uuid.UUID] = None,
    headers: Optional[Dict[str, str]] = None,
) -> str:
    """Send one email via AgentMail. Returns the provider message id. Raises on failure.

    AgentMail sends from the inbox itself, so `from_email`/`from_name` are advisory
    (used only as an optional reply-to hint) - the visible sender is the inbox address.
    """
    creds = _tenant_agentmail_creds(tenant_id)
    try:
        return await agentmail_client.send_email(
            to_email, subject, body_html, reply_to=reply_to, creds=creds, headers=headers)
    except agentmail_client.EmailNotConfigured:
        raise HTTPException(503, "Email provider not configured - set AGENTMAIL_API_KEY")


def _record_email_event(tenant_id: uuid.UUID, batch_id: uuid.UUID, email: str, event_type: str, event_data: str) -> None:
    with get_engine().begin() as conn:
        conn.execute(
            text("""
                INSERT INTO marketing_email_events
                    (tenant_id, batch_id, recipient_email, event_type, event_data)
                VALUES (:tid, :bid, :email, :etype, CAST(:edata AS jsonb))
            """),
            {"tid": str(tenant_id), "bid": str(batch_id), "email": email, "etype": event_type, "edata": event_data},
        )


def _finalize_email_batch(conn, tenant_id: uuid.UUID, batch_id: uuid.UUID, cid: Optional[str],
                          sent: int, failed: int) -> str:
    """Write the final tallies. Send failures count as total_failed, NOT total_bounced
    (bounces only come from provider webhooks). Every statement is tenant-scoped."""
    final_status = "sent" if failed == 0 else ("failed" if sent == 0 else "partial")
    conn.execute(
        text("""
            UPDATE marketing_email_batches
               SET total_sent = :sent, total_failed = :failed, status = :st
             WHERE id = :bid AND tenant_id = :tid
        """),
        {"sent": sent, "failed": failed, "st": final_status, "bid": str(batch_id), "tid": str(tenant_id)},
    )
    if cid:
        conn.execute(
            text("UPDATE marketing_campaigns SET total_sent = total_sent + :cnt, updated_at = now() "
                 "WHERE id = :cid AND tenant_id = :tid"),
            {"cnt": sent, "cid": cid, "tid": str(tenant_id)},
        )
    return final_status


async def _run_email_batch(
    *,
    tenant_id: uuid.UUID,
    batch_id: uuid.UUID,
    cid: Optional[str],
    recipients: List[str],
    subject: str,
    body_html: str,
    from_name: Optional[str],
    from_email: Optional[str],
    reply_to: Optional[str],
) -> None:
    """Background delivery. Opens its own DB connections (never the request's) and always
    leaves the batch in a terminal status."""
    sent = failed = 0
    try:
        for to_email in recipients:
            try:
                url = sec.unsubscribe_url(tenant_id, to_email)
                provider_id = await _send_one_email(
                    to_email=to_email,
                    subject=subject,
                    body_html=sec.with_unsubscribe_footer(body_html, url),
                    from_name=from_name,
                    from_email=from_email,
                    reply_to=reply_to,
                    tenant_id=tenant_id,
                    headers=sec.unsubscribe_headers(url),
                )
                sent += 1
                event_type, event_data = "sent", json.dumps({"message_id": provider_id})
            except Exception as e:  # noqa: BLE001 - record the failure, continue the batch
                failed += 1
                event_type, event_data = "failed", json.dumps({"error": str(e)[:500]})
                logger.warning("email send failed in batch %s: %s", batch_id, e)
            await asyncio.to_thread(_record_email_event, tenant_id, batch_id, to_email, event_type, event_data)
    except Exception:  # noqa: BLE001
        logger.exception("email batch %s crashed", batch_id)
        failed += max(0, len(recipients) - sent - failed)
    try:
        def _fin():
            with get_engine().begin() as conn:
                return _finalize_email_batch(conn, tenant_id, batch_id, cid, sent, failed)
        await asyncio.to_thread(_fin)
    except Exception:  # noqa: BLE001
        logger.exception("email batch %s finalize failed", batch_id)


def _campaign_audience_emails(tenant_id: uuid.UUID, campaign_id: uuid.UUID):
    """Email addresses of the campaign's audience members (tenant scoped); 422 with a reason when there are none."""
    from services.marketing import audience_members as am

    engine = get_engine()
    _ensure_marketing_tables(engine)
    with engine.connect() as conn:
        camp = conn.execute(
            text("SELECT audience_segment_id FROM marketing_campaigns WHERE id = :cid AND tenant_id = :tid"),
            {"cid": str(campaign_id), "tid": str(tenant_id)},
        ).first()
        if not camp:
            raise HTTPException(404, "Campaign not found")
        if not camp[0]:
            raise HTTPException(422, "Campaign has no audience; pass recipients or select an audience")
        seg = _audience_for_tenant(conn, tenant_id, camp[0])
        members = am.resolve_members(seg["rules"] or {})
        if not members["emails"]:
            raise HTTPException(422, members["note"] or f"Audience '{seg['name']}' has no members with an email address")
        conn.execute(
            text("UPDATE marketing_campaigns SET audience_member_count = :n, last_audience_send_at = now() "
                 "WHERE id = :cid AND tenant_id = :tid"),
            {"n": len(members["emails"]), "cid": str(campaign_id), "tid": str(tenant_id)},
        )
    return members["emails"], seg["name"]


@app.post("/email/send", response_model=EmailSendResponse, status_code=202,
          dependencies=[Depends(require_marketing_write)])
async def send_email_batch(
    body: EmailSendRequest,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Queue a batch of emails for delivery via AgentMail and return 202 immediately.

    Recipients are validated, de-duplicated, capped (EMAIL_MAX_RECIPIENTS), filtered against
    the tenant suppression list, and every message carries an unsubscribe link +
    List-Unsubscribe header. Poll GET /email/batches/{batch_id} for progress.
    """
    if not _email_provider_configured(tenant_id):
        raise HTTPException(503, "Email provider not configured — set AGENTMAIL_API_KEY")
    try:
        sec.unsubscribe_url(tenant_id, "probe@example.com")  # fail closed without unsubscribe support
    except sec.UnsubscribeNotConfigured as exc:
        logger.error("email send blocked: %s", exc)
        raise HTTPException(503, "Unsubscribe links not configured (EMAIL_UNSUBSCRIBE_SECRET / EMAIL_UNSUBSCRIBE_BASE_URL)")
    sec.check_email_rate(tenant_id)
    recipients = list(body.recipients or [])
    audience_name: Optional[str] = None
    if not recipients:
        if not body.campaign_id:
            raise HTTPException(422, "recipients is required (or pass campaign_id to send to the campaign's audience)")
        recipients, audience_name = _campaign_audience_emails(tenant_id, body.campaign_id)
    valid, invalid = sec.clean_recipients(recipients)
    if not valid:
        raise HTTPException(422, "No valid recipient addresses" + (f" in audience '{audience_name}'" if audience_name else ""))

    engine = get_engine()
    _ensure_marketing_tables(engine)
    batch_id = uuid.uuid4()

    with engine.begin() as conn:
        cid_str = None
        if body.campaign_id:
            camp = conn.execute(
                text("SELECT id FROM marketing_campaigns WHERE id = :cid AND tenant_id = :tid"),
                {"cid": str(body.campaign_id), "tid": str(tenant_id)},
            ).first()
            if not camp:
                raise HTTPException(404, "Campaign not found")
            cid_str = str(body.campaign_id)
        allowed, suppressed = suppression_lib.filter_suppressed_sync(conn, tenant_id, valid)
        conn.execute(
            text("""
                INSERT INTO marketing_email_batches
                    (id, tenant_id, campaign_id, subject, from_name, from_email, total_queued, total_suppressed, status)
                VALUES (:bid, :tid, :cid, :subj, :fn, :fe, :tq, :ts, :st)
            """),
            {
                "bid": str(batch_id), "tid": str(tenant_id), "cid": cid_str, "subj": body.subject,
                "fn": body.from_name, "fe": body.from_email, "tq": len(allowed), "ts": len(suppressed),
                "st": "sending" if allowed else "failed",
            },
        )

    if allowed:
        schedule_background(_run_email_batch(
            tenant_id=tenant_id, batch_id=batch_id, cid=cid_str, recipients=allowed,
            subject=body.subject, body_html=body.body_html, from_name=body.from_name,
            from_email=body.from_email, reply_to=body.reply_to,
        ))

    return EmailSendResponse(
        batch_id=batch_id,
        campaign_id=body.campaign_id,
        total_queued=len(allowed),
        status="sending" if allowed else "failed",
        total_suppressed=len(suppressed),
        total_invalid=len(invalid),
    )


@app.get("/email/batches/{batch_id}")
async def get_email_batch(
    batch_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT * FROM marketing_email_batches WHERE id = :bid AND tenant_id = :tid"),
            {"bid": str(batch_id), "tid": str(tenant_id)},
        ).mappings().first()
    if not row:
        raise HTTPException(404, "Batch not found")
    return dict(row)


# ─────────────────────── AgentMail Onboarding & Management ─────

_AGENTMAIL_STATUS: Dict[str, Any] = {}  # per-tenant OTP verification state (in-memory; keyed by tenant id)


def _require_agentmail_admin(auth: AuthContext) -> None:
    roles = {r.lower() for r in (auth.roles or [])}
    if not (auth.is_platform_admin or roles & {"admin", "owner", "tenant_admin", "super_admin"}):
        raise HTTPException(status_code=403, detail="Admin role required")


def _mask_key(key: str) -> str:
    return f"****{key[-4:]}" if key else ""


def _save_tenant_agentmail(tenant_id: uuid.UUID, **fields: Any) -> None:
    """Encrypted per-tenant storage; refuses (503) when SECRETS_ENCRYPTION_KEY is unset."""
    try:
        with get_engine().begin() as conn:
            agentmail_client.save_creds_sync(conn, tenant_id, **fields)
    except agentmail_client.SecretsUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@app.get("/email/agentmail/status")
async def get_agentmail_status(tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    creds = _tenant_agentmail_creds(tenant_id)
    configured = agentmail_client.is_configured(creds)
    return {
        "configured": configured,
        "inbox_id": creds.inbox if creds else agentmail_client.inbox_address(),
        "is_verified": _AGENTMAIL_STATUS.get(str(tenant_id), configured),
        "base_url": agentmail_client.base_url(),
        "provider": "agentmail",
        "credentials_source": "tenant" if creds else ("env" if configured else None),
    }


@app.post("/email/agentmail/signup", dependencies=[Depends(require_marketing_admin)])
async def agentmail_signup(
    body: AgentMailSignUpRequest,
    auth: AuthContext = Depends(get_auth_context),
):
    """Programmatically onboard AI agent to AgentMail (no console access needed)."""
    _require_agentmail_admin(auth)
    if not os.getenv("SECRETS_ENCRYPTION_KEY"):
        # fail before creating an AgentMail account whose key we could not store
        raise HTTPException(status_code=503, detail="SECRETS_ENCRYPTION_KEY is not set; cannot store tenant secrets")
    payload = {
        "human_email": body.human_email,
        "username": body.username,
    }
    inbox_id = f"{body.username}@agentmail.to"

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(f"{agentmail_client.base_url()}/agent/sign-up", json=payload)
    except Exception as e:
        logger.warning("AgentMail live sign-up call failed: %s", e)
        raise HTTPException(status_code=502, detail="AgentMail sign-up service unreachable")
    if resp.status_code >= 400:
        logger.warning("AgentMail sign-up returned %s: %s", resp.status_code, resp.text)
        raise HTTPException(status_code=502, detail=f"AgentMail sign-up failed ({resp.status_code})")
    data = resp.json()
    api_key = data.get("api_key") or data.get("apiKey") or ""
    inbox_id = data.get("inbox_id") or data.get("inboxId") or inbox_id
    if not api_key:
        raise HTTPException(status_code=502, detail="AgentMail sign-up did not return an API key")

    _save_tenant_agentmail(auth.tenant_id, api_key=api_key, inbox=inbox_id)
    _AGENTMAIL_STATUS[str(auth.tenant_id)] = False

    return {
        "status": "success",
        "api_key": _mask_key(api_key),
        "inbox_id": inbox_id,
        "message": f"6-digit OTP code sent to {body.human_email}. Verify OTP to unlock sending to external recipients.",
    }


@app.post("/email/agentmail/verify", dependencies=[Depends(require_marketing_admin)])
async def agentmail_verify(
    body: AgentMailVerifyRequest,
    auth: AuthContext = Depends(get_auth_context),
):
    """Verify 6-digit OTP code with AgentMail to unlock full permissions (admin only)."""
    _require_agentmail_admin(auth)
    creds = _tenant_agentmail_creds(auth.tenant_id) or agentmail_client.env_creds()
    success = False
    detail_msg = "AgentMail verified successfully. External sending is now enabled."

    if not creds:
        detail_msg = "AgentMail is not configured (no API key)."
    else:
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    f"{agentmail_client.base_url()}/agent/verify",
                    headers={"Authorization": f"Bearer {creds.api_key}"},
                    json={"otp_code": body.otp_code},
                )
                if resp.status_code < 400:
                    success = True
                else:
                    detail_msg = f"AgentMail verification failed: {resp.text[:200]}"
        except Exception as e:
            logger.warning("AgentMail live verify call: %s", e)
            detail_msg = "AgentMail verification request failed."

    _AGENTMAIL_STATUS[str(auth.tenant_id)] = success
    return {
        "status": "verified" if success else "failed",
        "success": success,
        "inbox_id": creds.inbox if creds else agentmail_client.inbox_address(),
        "is_verified": success,
        "message": detail_msg,
    }


@app.post("/email/agentmail/config", dependencies=[Depends(require_marketing_admin)])
async def agentmail_configure(
    body: AgentMailConfigRequest,
    auth: AuthContext = Depends(get_auth_context),
):
    """Configure this tenant's AgentMail API key / inbox (stored encrypted per tenant)."""
    _require_agentmail_admin(auth)
    if body.api_key or body.inbox_id:
        _save_tenant_agentmail(auth.tenant_id, api_key=body.api_key or None, inbox=body.inbox_id or None)
    creds = _tenant_agentmail_creds(auth.tenant_id)
    return {
        "status": "configured",
        "inbox_id": creds.inbox if creds else agentmail_client.inbox_address(),
        "configured": agentmail_client.is_configured(creds),
        "api_key": _mask_key(creds.api_key if creds else os.getenv("AGENTMAIL_API_KEY", "")),
    }


def _svix_msg_id(headers: Any) -> str:
    return str(headers.get("svix-id") or headers.get("webhook-id") or "")[:256]


def _bounce_is_hard(event: Dict[str, Any]) -> bool:
    """Suppress permanent bounces only; transient/undetermined ones may recover."""
    info = event.get("bounce") or {}
    btype = str(info.get("type") or info.get("bounce_type") or "").strip().lower()
    return btype not in {"transient", "undetermined", "soft", "temporary"}


@app.post("/email/webhook")
async def email_webhook(request: Request):
    """AgentMail delivery events (Svix-signed: svix-id/svix-timestamp/svix-signature).

    Batches are matched by the provider message_id stored on the 'sent' event. Idempotent on
    svix-id (marketing_webhook_events, provider='agentmail'); permanent bounces and complaints
    add the recipient to the tenant suppression list.
    """
    # Cheap pre-checks first: no DB / decryption for unsigned, stale or oversized requests.
    if not agentmail_client.webhook_headers_ok(request.headers):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")
    try:
        raw_body = await agentmail_client.read_body_capped(request)
    except agentmail_client.BodyTooLarge:
        raise HTTPException(status_code=413, detail="Webhook body too large")
    try:
        event = json.loads(raw_body)
    except ValueError:
        raise HTTPException(400, "Invalid JSON")
    if not isinstance(event, dict):
        raise HTTPException(400, "Invalid payload")

    event_type = str(event.get("event_type") or event.get("type") or "unknown")
    counter_map = {
        "message.delivered": "total_delivered",
        "message.bounced": "total_bounced",
        "message.complained": "total_complained",
    }
    col = counter_map.get(event_type)
    msg = event.get("message") or event.get("bounce") or event.get("complaint") or {}
    mid = str(msg.get("message_id") or "")
    if not col or not mid:
        return {"status": "ignored", "event": event_type}  # e.g. message.received belongs to communication

    engine = get_engine()
    _ensure_marketing_tables(engine)
    with engine.begin() as conn:
        hit = conn.execute(
            text("SELECT tenant_id, batch_id, recipient_email FROM marketing_email_events "
                 "WHERE event_type = 'sent' AND event_data->>'message_id' = :mid LIMIT 1"),
            {"mid": mid},
        ).mappings().first()
        if not hit:
            return {"status": "ignored", "reason": "unknown message"}
        # Verify against ONLY the tenant that owns the batch (plus the platform secret if that
        # tenant has no AgentMail account of its own); never another tenant's secret.
        try:
            secrets = agentmail_client.owner_webhook_secrets_sync(conn, hit["tenant_id"])
        except Exception as exc:  # noqa: BLE001
            logger.warning("tenant webhook secrets unavailable: %s", exc)
            secrets = []
        if not secrets or not agentmail_client.verify_svix(raw_body, request.headers, secrets):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")
        # Idempotency (only after the signature is verified): same svix-id => no side effects.
        if not sec.record_webhook_event(conn, "agentmail", _svix_msg_id(request.headers)):
            return {"status": "duplicate"}
        conn.execute(
            text("""
                INSERT INTO marketing_email_events (tenant_id, batch_id, recipient_email, event_type, event_data)
                VALUES (:tid, :bid, :email, :etype, CAST(:edata AS jsonb))
            """),
            {"tid": str(hit["tenant_id"]), "bid": str(hit["batch_id"]), "email": hit["recipient_email"],
             "etype": event_type.split(".", 1)[-1], "edata": json.dumps(sec.bound_payload(event, event_type))},
        )
        conn.execute(
            text(f"UPDATE marketing_email_batches SET {col} = COALESCE({col}, 0) + 1 "
                 "WHERE id = :bid AND tenant_id = :tid"),
            {"bid": str(hit["batch_id"]), "tid": str(hit["tenant_id"])},
        )
        if event_type == "message.complained" or (event_type == "message.bounced" and _bounce_is_hard(event)):
            suppression_lib.add_suppression_sync(
                conn, hit["tenant_id"], hit["recipient_email"],
                "complaint" if event_type == "message.complained" else "bounce",
                f"agentmail:{event_type}",
            )
    return {"status": "accepted"}


# ─────────────────── Unsubscribe + suppression management ───────────────────


def _unsub_page(title: str, body: str, form_token: Optional[str] = None, status_code: int = 200) -> Response:
    import html as _html
    form = ""
    if form_token:
        form = (f'<form method="post" action="?t={_html.escape(form_token, quote=True)}">'
                f'<button type="submit">Confirm unsubscribe</button></form>')
    page = (f"<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width'>"
            f"<title>{_html.escape(title)}</title></head><body style='font-family:sans-serif;max-width:480px;"
            f"margin:10vh auto;padding:0 16px'><h2>{_html.escape(title)}</h2><p>{_html.escape(body)}</p>{form}</body></html>")
    return Response(content=page, media_type="text/html", status_code=status_code)


def _token_or_error(t: Optional[str]):
    """(tenant_id, email) or an error Response."""
    if not t:
        return None, _unsub_page("Invalid link", "This unsubscribe link is invalid.", status_code=400)
    try:
        return sec.verify_unsubscribe_token(t), None
    except sec.UnsubscribeNotConfigured:
        return None, _unsub_page("Unavailable", "Unsubscribe is temporarily unavailable.", status_code=503)
    except sec.BadUnsubscribeToken:
        return None, _unsub_page("Invalid link", "This unsubscribe link is invalid or has expired.", status_code=400)


@app.get("/email/unsubscribe")
async def unsubscribe_confirm(t: Optional[str] = Query(None)):
    """Public. Shows a confirm button; mail scanners that prefetch links cannot unsubscribe anyone."""
    ident, err = _token_or_error(t)
    if err is not None:
        return err
    return _unsub_page("Unsubscribe", f"Stop receiving marketing email at {ident[1]}?", form_token=t)


@app.post("/email/unsubscribe")
async def unsubscribe_apply(request: Request, t: Optional[str] = Query(None)):
    """Public. Also the RFC 8058 one-click target (POST with List-Unsubscribe=One-Click)."""
    ident, err = _token_or_error(t)
    if err is not None:
        return err
    tenant_uuid, email = ident
    engine = get_engine()
    _ensure_marketing_tables(engine)
    with engine.begin() as conn:
        suppression_lib.add_suppression_sync(conn, tenant_uuid, email, "unsubscribe", "unsubscribe-link")
    return _unsub_page("Unsubscribed", f"{email} will no longer receive marketing email from us.")


class SuppressionIn(BaseModel):
    email: str = Field(..., max_length=254)
    reason: str = "manual"


@app.get("/email/suppressions")
async def list_email_suppressions(
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    engine = get_engine()
    _ensure_marketing_tables(engine)
    with engine.begin() as conn:
        return {"suppressions": suppression_lib.list_suppressions_sync(conn, tenant_id, limit, offset)}


@app.post("/email/suppressions", status_code=201, dependencies=[Depends(require_marketing_admin)])
async def add_email_suppression(body: SuppressionIn, tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    email = body.email.strip().lower()
    if not sec.valid_email(email):
        raise HTTPException(422, "Invalid email address")
    if body.reason not in suppression_lib.REASONS:
        raise HTTPException(422, f"reason must be one of {list(suppression_lib.REASONS)}")
    engine = get_engine()
    _ensure_marketing_tables(engine)
    with engine.begin() as conn:
        created = suppression_lib.add_suppression_sync(conn, tenant_id, email, body.reason, "manual-api")
    return {"email": email, "reason": body.reason, "created": created}


@app.delete("/email/suppressions", dependencies=[Depends(require_marketing_admin)])
async def remove_email_suppression(email: str = Query(..., max_length=254), tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    engine = get_engine()
    _ensure_marketing_tables(engine)
    with engine.begin() as conn:
        removed = suppression_lib.remove_suppression_sync(conn, tenant_id, email)
    if not removed:
        raise HTTPException(404, "Address not suppressed")
    return {"email": email.strip().lower(), "removed": True}


# ──────────────────── Templates ──────────────────────────────


@app.get("/templates")
async def list_templates(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    engine = get_engine()
    _ensure_marketing_tables(engine)
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT * FROM marketing_templates WHERE tenant_id = :tid ORDER BY created_at DESC"),
            {"tid": str(tenant_id)},
        ).mappings().all()
    return [dict(r) for r in rows]


@app.post("/templates", status_code=201, dependencies=[Depends(require_marketing_write)])
async def create_template(
    body: TemplateCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    engine = get_engine()
    _ensure_marketing_tables(engine)
    tid = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO marketing_templates (id, tenant_id, name, subject, body_html, category)
                VALUES (:id, :tid, :name, :subj, :body, :cat)
            """),
            {
                "id": str(tid),
                "tid": str(tenant_id),
                "name": body.name,
                "subj": body.subject,
                "body": body.body_html,
                "cat": body.category,
            },
        )
        row = conn.execute(text("SELECT * FROM marketing_templates WHERE id = :id"), {"id": str(tid)}).mappings().first()
    return dict(row)


@app.get("/templates/{template_id}")
async def get_template(
    template_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    engine = get_engine()
    _ensure_marketing_tables(engine)
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT * FROM marketing_templates WHERE id = :id AND tenant_id = :tid"),
            {"id": str(template_id), "tid": str(tenant_id)},
        ).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Template not found")
    return dict(row)


@app.put("/templates/{template_id}", dependencies=[Depends(require_marketing_write)])
async def update_template(
    template_id: uuid.UUID,
    body: TemplateUpdate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    engine = get_engine()
    _ensure_marketing_tables(engine)
    updates = []
    params: Dict[str, Any] = {"id": str(template_id), "tid": str(tenant_id)}
    if body.name is not None:
        updates.append("name = :name")
        params["name"] = body.name
    if body.subject is not None:
        updates.append("subject = :subject")
        params["subject"] = body.subject
    if body.body_html is not None:
        updates.append("body_html = :body_html")
        params["body_html"] = body.body_html
    if body.category is not None:
        updates.append("category = :category")
        params["category"] = body.category
    updates.append("updated_at = now()")

    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    sql = f"UPDATE marketing_templates SET {', '.join(updates)} WHERE id = :id AND tenant_id = :tid RETURNING *"
    with engine.begin() as conn:
        row = conn.execute(text(sql), params).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Template not found")
    return dict(row)


@app.delete("/templates/{template_id}", status_code=204, dependencies=[Depends(require_marketing_write)])
async def delete_template(
    template_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    engine = get_engine()
    _ensure_marketing_tables(engine)
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM marketing_templates WHERE id = :id AND tenant_id = :tid"),
            {"id": str(template_id), "tid": str(tenant_id)},
        )
    return None


# ──────────────────── Templates Journey (Email Automations) ───────

_EMAIL_JOURNEYS: Dict[str, List[Dict[str, Any]]] = {}

def _journey_out(item: Dict[str, Any]) -> Dict[str, Any]:
    """Journey enrolment is not tracked anywhere (no enrolment table / step executor), so never
    report enrolment or completion figures: mark the row untracked and null the counters."""
    out = dict(item)
    out["total_enrolled"] = None
    out["total_completed"] = None
    out["enrollment_tracked"] = False
    return out


@app.get("/email/journeys")
async def list_email_journeys(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    tkey = str(tenant_id)
    try:
        engine = get_engine()
        _ensure_marketing_tables(engine)
        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT * FROM marketing_email_journeys WHERE tenant_id = :tid ORDER BY created_at DESC"),
                {"tid": tkey},
            ).mappings().all()
            if rows:
                return [_journey_out(dict(r)) for r in rows]
    except Exception as e:
        logger.warning("DB journey query fallback: %s", e)

    return [_journey_out(x) for x in _EMAIL_JOURNEYS.get(tkey, [])]


@app.post("/email/journeys", status_code=201, dependencies=[Depends(require_marketing_write)])
async def create_email_journey(
    body: JourneyCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    tkey = str(tenant_id)
    jid = str(uuid.uuid4())
    now_str = datetime.now(timezone.utc).isoformat()
    record = {
        "id": jid,
        "tenant_id": tkey,
        "name": body.name,
        "description": body.description,
        "trigger_type": body.trigger_type,
        "status": body.status,
        "steps": body.steps,
        "total_enrolled": 0,
        "total_completed": 0,
        "created_at": now_str,
        "updated_at": now_str,
    }

    try:
        engine = get_engine()
        _ensure_marketing_tables(engine)
        with engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO marketing_email_journeys 
                    (id, tenant_id, name, description, trigger_type, status, steps, total_enrolled, total_completed)
                    VALUES (:id, :tid, :name, :desc, :ttype, :status, CAST(:steps AS jsonb), 0, 0)
                """),
                {
                    "id": jid,
                    "tid": tkey,
                    "name": body.name,
                    "desc": body.description,
                    "ttype": body.trigger_type,
                    "status": body.status,
                    "steps": json.dumps(body.steps),
                },
            )
            row = conn.execute(text("SELECT * FROM marketing_email_journeys WHERE id = :id"), {"id": jid}).mappings().first()
            if row:
                return _journey_out(dict(row))
    except Exception as e:
        logger.warning("DB journey insert fallback: %s", e)
    _EMAIL_JOURNEYS.setdefault(tkey, []).insert(0, record)
    return _journey_out(record)


@app.get("/email/journeys/{journey_id}")
async def get_email_journey(
    journey_id: str,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    tkey = str(tenant_id)
    try:
        engine = get_engine()
        _ensure_marketing_tables(engine)
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM marketing_email_journeys WHERE id = :id AND tenant_id = :tid"),
                {"id": journey_id, "tid": tkey},
            ).mappings().first()
            if row:
                return _journey_out(dict(row))
    except Exception as e:
        logger.warning("DB journey fetch fallback: %s", e)
    for item in _EMAIL_JOURNEYS.get(tkey, []):
        if item["id"] == journey_id:
            return _journey_out(item)
    raise HTTPException(status_code=404, detail="Journey not found")


@app.put("/email/journeys/{journey_id}", dependencies=[Depends(require_marketing_write)])
async def update_email_journey(
    journey_id: str,
    body: JourneyUpdate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    tkey = str(tenant_id)
    try:
        engine = get_engine()
        _ensure_marketing_tables(engine)
        updates = []
        params: Dict[str, Any] = {"id": journey_id, "tid": tkey}
        if body.name is not None:
            updates.append("name = :name")
            params["name"] = body.name
        if body.description is not None:
            updates.append("description = :desc")
            params["desc"] = body.description
        if body.trigger_type is not None:
            updates.append("trigger_type = :ttype")
            params["ttype"] = body.trigger_type
        if body.status is not None:
            updates.append("status = :status")
            params["status"] = body.status
        if body.steps is not None:
            updates.append("steps = CAST(:steps AS jsonb)")
            params["steps"] = json.dumps(body.steps)
        updates.append("updated_at = now()")

        if updates:
            sql = f"UPDATE marketing_email_journeys SET {', '.join(updates)} WHERE id = :id AND tenant_id = :tid RETURNING *"
            with engine.begin() as conn:
                row = conn.execute(text(sql), params).mappings().first()
                if row:
                    return _journey_out(dict(row))
    except Exception as e:
        logger.warning("DB journey update fallback: %s", e)
    for item in _EMAIL_JOURNEYS.get(tkey, []):
        if item["id"] == journey_id:
            if body.name is not None: item["name"] = body.name
            if body.description is not None: item["description"] = body.description
            if body.trigger_type is not None: item["trigger_type"] = body.trigger_type
            if body.status is not None: item["status"] = body.status
            if body.steps is not None: item["steps"] = body.steps
            item["updated_at"] = datetime.now(timezone.utc).isoformat()
            return _journey_out(item)
    raise HTTPException(status_code=404, detail="Journey not found")


@app.delete("/email/journeys/{journey_id}", status_code=204, dependencies=[Depends(require_marketing_write)])
async def delete_email_journey(
    journey_id: str,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    tkey = str(tenant_id)
    try:
        engine = get_engine()
        _ensure_marketing_tables(engine)
        with engine.begin() as conn:
            conn.execute(
                text("DELETE FROM marketing_email_journeys WHERE id = :id AND tenant_id = :tid"),
                {"id": journey_id, "tid": tkey},
            )
    except Exception as e:
        logger.warning("DB journey delete fallback: %s", e)

    if tkey in _EMAIL_JOURNEYS:
        _EMAIL_JOURNEYS[tkey] = [x for x in _EMAIL_JOURNEYS[tkey] if x["id"] != journey_id]
    return None


@app.post("/email/journeys/{journey_id}/trigger", dependencies=[Depends(require_marketing_write)])
async def trigger_email_journey(
    journey_id: str,
    body: Dict[str, Any] = Body(default_factory=dict),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Journey enrolment is not implemented: there is no enrolment table or step executor, so
    nothing here could honestly start a journey. Returns 501 rather than a fake success."""
    raise HTTPException(status_code=501, detail="Journey enrolment is not implemented")


# ──────────────────── Audience Segments ────────────────────────


def _segment_row(row) -> Dict[str, Any]:
    data = dict(row)
    rules = data.get("rules") or {}
    data["type"] = rules.get("type", "custom")
    data["platform"] = rules.get("platform", "custom")
    return data


@app.get("/segments")
async def list_segments(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    type: Optional[str] = Query(None, description="homes | businesses | custom"),
):
    engine = get_engine()
    _ensure_marketing_tables(engine)
    sql = "SELECT * FROM marketing_audience_segments WHERE tenant_id = :tid"
    params: Dict[str, Any] = {"tid": str(tenant_id)}
    if type:
        sql += " AND COALESCE(rules->>'type', 'custom') = :type"
        params["type"] = type
    with engine.connect() as conn:
        rows = conn.execute(text(sql + " ORDER BY COALESCE(updated_at, created_at) DESC"), params).mappings().all()
    return [_segment_row(r) for r in rows]


@app.post("/segments", status_code=201, dependencies=[Depends(require_marketing_write)])
async def create_segment(
    body: AudienceSegmentCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Create an audience. Pushing the same source again (same rules.source +
    rules.source_id) updates that audience instead of duplicating it."""
    rules = dict(body.rules or {})
    rules.setdefault("type", "custom")
    rules.setdefault("platform", "custom")
    if rules["type"] not in _SEGMENT_TYPES:
        raise HTTPException(422, f"rules.type must be one of {sorted(_SEGMENT_TYPES)}")
    if rules["platform"] not in _SEGMENT_PLATFORMS:
        raise HTTPException(422, f"rules.platform must be one of {sorted(_SEGMENT_PLATFORMS)}")
    if rules["type"] == "homes":
        # Areas only: never let individual addresses into an ad audience.
        rules.pop("addresses", None)
    # Server truth: any client-supplied member_count is ignored.
    member_count = (
        sum(int(a.get("homes") or 0) for a in rules.get("areas") or [])
        if rules["type"] == "homes"
        else len(rules.get("businesses") or [])
    )

    engine = get_engine()
    _ensure_marketing_tables(engine)
    params = {
        "tid": str(tenant_id), "name": body.name.strip(), "desc": body.description,
        "rules": json.dumps(rules), "count": member_count,
    }
    with engine.begin() as conn:
        existing = None
        if rules.get("source") and rules.get("source_id"):
            existing = conn.execute(text(
                "SELECT id FROM marketing_audience_segments WHERE tenant_id = :tid "
                "AND rules->>'source' = :src AND rules->>'source_id' = :sid"
            ), {"tid": str(tenant_id), "src": str(rules["source"]), "sid": str(rules["source_id"])}).first()
        if existing:
            conn.execute(text("""
                UPDATE marketing_audience_segments
                   SET name = :name, description = :desc, rules = CAST(:rules AS jsonb),
                       member_count = :count, updated_at = now()
                 WHERE id = :id AND tenant_id = :tid
            """), {**params, "id": str(existing[0])})
            sid = existing[0]
        else:
            sid = uuid.uuid4()
            conn.execute(text("""
                INSERT INTO marketing_audience_segments (id, tenant_id, name, description, rules, member_count, updated_at)
                VALUES (:id, :tid, :name, :desc, CAST(:rules AS jsonb), :count, now())
            """), {**params, "id": str(sid)})
        row = conn.execute(
            text("SELECT * FROM marketing_audience_segments WHERE id = :id"), {"id": str(sid)}
        ).mappings().first()
    data = {**_segment_row(row), "updated": bool(existing)}
    if existing:
        return JSONResponse(status_code=200, content=json.loads(json.dumps(data, default=str)))
    return data


@app.get("/segments/{segment_id}")
async def get_segment(
    segment_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    engine = get_engine()
    _ensure_marketing_tables(engine)
    with engine.connect() as conn:
        row = conn.execute(text(
            "SELECT * FROM marketing_audience_segments WHERE id = :id AND tenant_id = :tid"
        ), {"id": str(segment_id), "tid": str(tenant_id)}).mappings().first()
    if row is None:
        raise HTTPException(404, "Audience not found")
    return _segment_row(row)


@app.delete("/segments/{segment_id}", status_code=204, dependencies=[Depends(require_marketing_write)])
async def delete_segment(
    segment_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    engine = get_engine()
    _ensure_marketing_tables(engine)
    with engine.begin() as conn:
        deleted = conn.execute(text(
            "DELETE FROM marketing_audience_segments WHERE id = :id AND tenant_id = :tid"
        ), {"id": str(segment_id), "tid": str(tenant_id)}).rowcount
    if not deleted:
        raise HTTPException(404, "Audience not found")
    return Response(status_code=204)


# ──────────────────── Lead Scoring ─────────────────────────────


@app.post("/leads/score", dependencies=[Depends(require_marketing_write)])
async def update_lead_score(
    body: LeadScoreUpdate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    engine = get_engine()
    _ensure_marketing_tables(engine)
    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO marketing_lead_scores (tenant_id, contact_id, score, last_scored_at)
                VALUES (:tid, :cid, :delta, now())
                ON CONFLICT (tenant_id, contact_id)
                DO UPDATE SET score = marketing_lead_scores.score + :delta, last_scored_at = now()
            """),
            {"tid": str(tenant_id), "cid": str(body.contact_id), "delta": body.score_delta},
        )
        row = conn.execute(
            text("SELECT * FROM marketing_lead_scores WHERE tenant_id = :tid AND contact_id = :cid"),
            {"tid": str(tenant_id), "cid": str(body.contact_id)},
        ).mappings().first()
    return dict(row)


@app.get("/leads/scores")
async def list_lead_scores(
    min_score: int = 0,
    limit: int = 50,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    engine = get_engine()
    _ensure_marketing_tables(engine)
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT * FROM marketing_lead_scores
                WHERE tenant_id = :tid AND score >= :ms
                ORDER BY score DESC LIMIT :lim
            """),
            {"tid": str(tenant_id), "ms": min_score, "lim": limit},
        ).mappings().all()
    return [dict(r) for r in rows]


# ──────────────────── Automations ──────────────────────────────


@app.get("/automations")
async def list_automations(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    engine = get_engine()
    _ensure_marketing_tables(engine)
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT * FROM marketing_automations WHERE tenant_id = :tid ORDER BY created_at DESC"),
            {"tid": str(tenant_id)},
        ).mappings().all()
    return [dict(r) for r in rows]


@app.post("/automations", status_code=201, dependencies=[Depends(require_marketing_write)])
async def create_automation(
    body: AutomationCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    engine = get_engine()
    _ensure_marketing_tables(engine)
    import json

    aid = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO marketing_automations
                    (id, tenant_id, name, trigger_type, trigger_config, actions, is_active)
                VALUES (:id, :tid, :name, :tt, :tc::jsonb, :acts::jsonb, :active)
            """),
            {
                "id": str(aid),
                "tid": str(tenant_id),
                "name": body.name,
                "tt": body.trigger_type,
                "tc": json.dumps(body.trigger_config),
                "acts": json.dumps(body.actions),
                "active": body.is_active,
            },
        )
        row = conn.execute(
            text("SELECT * FROM marketing_automations WHERE id = :id"), {"id": str(aid)}
        ).mappings().first()
    return dict(row)


# ──────────────────── A/B Testing ──────────────────────────────


@app.post("/ab-tests", status_code=201, dependencies=[Depends(require_marketing_write)])
async def create_ab_test(
    body: ABTestCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    engine = get_engine()
    _ensure_marketing_tables(engine)
    import json

    tid = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO marketing_ab_tests
                    (id, tenant_id, campaign_id, variant_a, variant_b, split_pct, metric, duration_hours)
                VALUES (:id, :tid, :cid, :va::jsonb, :vb::jsonb, :sp, :met, :dur)
            """),
            {
                "id": str(tid),
                "tid": str(tenant_id),
                "cid": str(body.campaign_id),
                "va": json.dumps(body.variant_a),
                "vb": json.dumps(body.variant_b),
                "sp": body.split_pct,
                "met": body.metric,
                "dur": body.duration_hours,
            },
        )
        row = conn.execute(
            text("SELECT * FROM marketing_ab_tests WHERE id = :id"), {"id": str(tid)}
        ).mappings().first()
    return dict(row)


@app.get("/ab-tests")
async def list_ab_tests(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    engine = get_engine()
    _ensure_marketing_tables(engine)
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT * FROM marketing_ab_tests WHERE tenant_id = :tid ORDER BY created_at DESC"),
            {"tid": str(tenant_id)},
        ).mappings().all()
    return [dict(r) for r in rows]


# ──────────────────── Dashboard Metrics ────────────────────────


@app.get("/dashboard", response_model=DashboardMetrics)
async def dashboard_metrics(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    engine = get_engine()
    _ensure_marketing_tables(engine)
    with engine.connect() as conn:
        camp = conn.execute(
            text("""
                SELECT
                    COUNT(*) FILTER (WHERE status IN ('active','running')) AS active,
                    COALESCE(SUM(total_sent), 0) AS sent,
                    COALESCE(SUM(total_delivered), 0) AS delivered,
                    COALESCE(SUM(total_opened), 0) AS opened,
                    COALESCE(SUM(total_conversions), 0) AS conversions,
                    COALESCE(SUM(budget_zar), 0) AS budget
                FROM marketing_campaigns
                WHERE tenant_id = :tid
            """),
            {"tid": str(tenant_id)},
        ).mappings().first()

        leads_row = conn.execute(
            text("""
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE score >= 50) AS mql,
                    COUNT(*) FILTER (WHERE score >= 80) AS sql_q
                FROM marketing_lead_scores
                WHERE tenant_id = :tid
            """),
            {"tid": str(tenant_id)},
        ).mappings().first()

    sent = int(camp["sent"]) if camp["sent"] else 0
    delivered = int(camp["delivered"]) if camp["delivered"] else 0
    opened = int(camp["opened"]) if camp["opened"] else 0
    conversions = int(camp["conversions"]) if camp["conversions"] else 0
    budget = float(camp["budget"]) if camp["budget"] else 0
    total_leads = int(leads_row["total"]) if leads_row else 0

    delivery_rate = (delivered / sent * 100) if sent > 0 else 0
    open_rate = (opened / delivered * 100) if delivered > 0 else 0
    bounce_rate = ((sent - delivered) / sent * 100) if sent > 0 else 0
    conversion_rate = (conversions / sent * 100) if sent > 0 else 0
    roi = (conversions * 500 / budget) if budget > 0 else 0  # Simplified

    return DashboardMetrics(
        active_campaigns=int(camp["active"]) if camp["active"] else 0,
        email_delivery_rate=round(delivery_rate, 2),
        lead_conversion_rate=round(conversion_rate, 2),
        marketing_roi=round(roi, 2),
        total_leads=total_leads,
        total_mql=int(leads_row["mql"]) if leads_row else 0,
        total_sql=int(leads_row["sql_q"]) if leads_row else 0,
        emails_sent_mtd=sent,
        emails_delivered_mtd=delivered,
        emails_opened_mtd=opened,
        bounce_rate=round(bounce_rate, 2),
        open_rate=round(open_rate, 2),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# SOCIAL MEDIA ROUTES
# ═══════════════════════════════════════════════════════════════════════════════


# ──────────────────── Social Media Accounts ────────────────────────


@app.get("/social/accounts", response_model=List[Dict[str, Any]])
async def list_social_accounts(
    platform: Optional[str] = None,
    account_status: Optional[str] = Query(None, alias="status"),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """List social media accounts, optionally filtered by platform and status."""
    async with get_session() as session:
        stmt = select(SocialMediaAccount).where(SocialMediaAccount.tenant_id == tenant_id)
        if platform:
            stmt = stmt.where(SocialMediaAccount.platform == platform)
        if account_status:
            stmt = stmt.where(SocialMediaAccount.status == account_status)
        stmt = stmt.order_by(SocialMediaAccount.created_at.desc())
        result = await session.execute(stmt)
        accounts = result.scalars().all()
    return [
        {
            "id": a.id,
            "tenant_id": a.tenant_id,
            "platform": a.platform,
            "account_name": a.account_name,
            "account_handle": a.account_handle,
            "status": a.status,
            "profile_data": a.profile_data,
            "token_expires_at": a.token_expires_at,
            "created_at": a.created_at,
            "updated_at": a.updated_at,
        }
        for a in accounts
    ]


@app.post("/social/accounts", status_code=201, response_model=Dict[str, Any], dependencies=[Depends(require_marketing_admin)])
async def create_social_account(
    body: SocialAccountCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Connect a new social media account."""
    async with get_session() as session:
        account = SocialMediaAccount(
            tenant_id=tenant_id,
            platform=body.platform,
            account_name=body.account_name,
            account_handle=body.account_handle,
            access_token=body.access_token,
            refresh_token=body.refresh_token,
            token_expires_at=body.token_expires_at,
            profile_data=body.profile_data,
            status="ACTIVE",
        )
        session.add(account)
        await session.flush()
        await session.refresh(account)
        return {
            "id": account.id,
            "tenant_id": account.tenant_id,
            "platform": account.platform,
            "account_name": account.account_name,
            "account_handle": account.account_handle,
            "status": account.status,
            "profile_data": account.profile_data,
            "created_at": account.created_at,
            "updated_at": account.updated_at,
        }


@app.get("/social/accounts/{account_id}", response_model=Dict[str, Any])
async def get_social_account(
    account_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Get a specific social media account."""
    async with get_session() as session:
        stmt = select(SocialMediaAccount).where(
            SocialMediaAccount.id == account_id,
            SocialMediaAccount.tenant_id == tenant_id,
        )
        result = await session.execute(stmt)
        account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Social media account not found")
    return {
        "id": account.id,
        "tenant_id": account.tenant_id,
        "platform": account.platform,
        "account_name": account.account_name,
        "account_handle": account.account_handle,
        "status": account.status,
        "profile_data": account.profile_data,
        "token_expires_at": account.token_expires_at,
        "created_at": account.created_at,
        "updated_at": account.updated_at,
    }


@app.put("/social/accounts/{account_id}", response_model=Dict[str, Any], dependencies=[Depends(require_marketing_admin)])
async def update_social_account(
    account_id: uuid.UUID,
    body: SocialAccountUpdate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Update a social media account."""
    async with get_session() as session:
        stmt = select(SocialMediaAccount).where(
            SocialMediaAccount.id == account_id,
            SocialMediaAccount.tenant_id == tenant_id,
        )
        result = await session.execute(stmt)
        account = result.scalar_one_or_none()
        if not account:
            raise HTTPException(status_code=404, detail="Social media account not found")

        update_data = body.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(account, field, value)
        await session.flush()
        await session.refresh(account)
        return {
            "id": account.id,
            "tenant_id": account.tenant_id,
            "platform": account.platform,
            "account_name": account.account_name,
            "account_handle": account.account_handle,
            "status": account.status,
            "profile_data": account.profile_data,
            "token_expires_at": account.token_expires_at,
            "created_at": account.created_at,
            "updated_at": account.updated_at,
        }


@app.delete("/social/accounts/{account_id}", status_code=204, dependencies=[Depends(require_marketing_admin)])
async def delete_social_account(
    account_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Disconnect a social media account."""
    async with get_session() as session:
        stmt = select(SocialMediaAccount).where(
            SocialMediaAccount.id == account_id,
            SocialMediaAccount.tenant_id == tenant_id,
        )
        result = await session.execute(stmt)
        account = result.scalar_one_or_none()
        if not account:
            raise HTTPException(status_code=404, detail="Social media account not found")
        await session.delete(account)
    return None


@app.get("/social/accounts/connect/{platform}", response_model=OAuthUrlResponse)
async def get_oauth_url(
    platform: str,
    redirect_url: Optional[str] = None,  # ignored: callbacks are server-configured (see zernio_connect)
    category: str = Query("social", description="social | ads"),
    return_to: Optional[str] = None,
    auth: AuthContext = Depends(require_marketing_admin),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Legacy entrypoint, kept for the existing UI: returns {platform, auth_url}.

    It now delegates to the OmniDome-hosted flow (POST /social/connect/start): the provider is
    given an OmniDome redirect (so the user is never sent to zernio.com) and the response also
    carries the signed `state`. A caller-supplied `redirect_url` is deliberately ignored: only a
    server-configured callback may receive the OAuth hand-off.
    """
    from services.marketing import zernio_connect as zc

    res = await zc._start(
        zc.ConnectStartIn(platform=platform, category=category, return_to=return_to), auth, tenant_id,
    )
    if res.get("status") != "redirect":
        return JSONResponse(status_code=200, content=res)
    return OAuthUrlResponse(platform=platform, auth_url=res["auth_url"], state=res.get("state"),
                            expires_in=res.get("expires_in"))


@app.post("/social/accounts/{account_id}/refresh", response_model=TokenRefreshResponse, dependencies=[Depends(require_marketing_admin)])
async def refresh_social_token(
    account_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Refresh the OAuth token for a social media account."""
    async with get_session() as session:
        stmt = select(SocialMediaAccount).where(
            SocialMediaAccount.id == account_id,
            SocialMediaAccount.tenant_id == tenant_id,
        )
        result = await session.execute(stmt)
        account = result.scalar_one_or_none()
        if not account:
            raise HTTPException(status_code=404, detail="Social media account not found")
        if not account.refresh_token:
            raise HTTPException(status_code=400, detail="No refresh token available for this account")

        # In production, this would call the platform's token refresh endpoint
        # For now, simulate a successful refresh
        new_expires_at = datetime.utcnow() + timedelta(hours=1)
        account.token_expires_at = new_expires_at
        # In production: account.access_token = new_access_token
        await session.flush()
        return TokenRefreshResponse(status="refreshed", expires_at=new_expires_at)


# ──────────────────── Social Posts ────────────────────────


def _detail_text(exc: HTTPException) -> str:
    d = exc.detail
    if isinstance(d, dict):
        return str(d.get("message") or d.get("error") or "request failed")[:1000]
    return str(d)[:1000]


def _post_dict(p) -> Dict[str, Any]:
    return {
        "id": p.id,
        "tenant_id": p.tenant_id,
        "account_id": p.account_id,
        "campaign_id": p.campaign_id,
        "content": p.content,
        "media_urls": p.media_urls,
        "platforms": p.platforms,
        "status": str(p.status or "draft").lower(),
        "scheduled_for": p.scheduled_for,
        "published_at": p.published_at,
        "platform_post_ids": p.platform_post_ids,
        "engagement_data": p.engagement_data,
        "publish_error": getattr(p, "publish_error", None),
        "queue_id": getattr(p, "queue_id", None),
        "zernio_post_id": getattr(p, "zernio_post_id", None),
        "timezone": getattr(p, "timezone", None),
        "created_at": p.created_at,
        "updated_at": p.updated_at,
    }


def _apply_post_filters(stmt, tenant_id, post_status, account_id, campaign_id, platform, queued, from_date, to_date):
    """Shared by the list and scheduled endpoints. Status is compared case-insensitively
    and may be a comma list ('scheduled,draft'); 'queued' = scheduled through a queue."""
    from services.marketing import zernio_posts as zp

    stmt = stmt.where(SocialPost.tenant_id == tenant_id)
    statuses, queued_only = zp.parse_status_filter(post_status)
    if statuses:
        stmt = stmt.where(func.lower(SocialPost.status).in_(statuses))
    if queued or queued_only:
        stmt = stmt.where(SocialPost.queue_id.is_not(None))
    if account_id:
        stmt = stmt.where(SocialPost.account_id == account_id)
    if campaign_id:
        stmt = stmt.where(SocialPost.campaign_id == campaign_id)
    if platform:
        stmt = stmt.where(SocialPost.platforms.contains([zp.norm_platform(platform)]))
    if from_date:
        stmt = stmt.where(SocialPost.scheduled_for >= zp.to_utc(from_date))
    if to_date:
        stmt = stmt.where(SocialPost.scheduled_for <= zp.to_utc(to_date))
    return stmt


def _sort_posts(stmt, sort: str):
    if sort == "scheduled_asc":
        return stmt.order_by(SocialPost.scheduled_for.asc().nulls_last(), SocialPost.created_at.desc())
    if sort == "scheduled_desc":
        return stmt.order_by(SocialPost.scheduled_for.desc().nulls_last(), SocialPost.created_at.desc())
    if sort == "created_asc":
        return stmt.order_by(SocialPost.created_at.asc())
    return stmt.order_by(SocialPost.created_at.desc())


@app.get("/social/posts", response_model=List[Dict[str, Any]])
async def list_social_posts(
    response: Response,
    post_status: Optional[str] = Query(None, alias="status", description="draft|scheduled|queued|published|failed|... (comma list, case-insensitive)"),
    account_id: Optional[uuid.UUID] = None,
    campaign_id: Optional[uuid.UUID] = None,
    platform: Optional[str] = None,
    queued: Optional[bool] = None,
    from_date: Optional[datetime] = Query(None, alias="from"),
    to_date: Optional[datetime] = Query(None, alias="to"),
    sort: str = Query("created_desc", pattern="^(created_desc|created_asc|scheduled_asc|scheduled_desc)$"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """List social media posts. Total row count (ignoring limit/offset) is in X-Total-Count."""
    async with get_session() as session:
        base = _apply_post_filters(select(SocialPost), tenant_id, post_status, account_id, campaign_id, platform, queued, from_date, to_date)
        total = (await session.execute(select(func.count()).select_from(base.subquery()))).scalar() or 0
        stmt = _sort_posts(base, sort).limit(limit).offset(offset)
        posts = (await session.execute(stmt)).scalars().all()
    response.headers["X-Total-Count"] = str(total)
    return [_post_dict(p) for p in posts]


def _provider_post_view(zp_: Dict[str, Any]) -> Dict[str, Any]:
    plats = [pl for pl in (zp_.get("platforms") or []) if isinstance(pl, dict)]
    published = [pl.get("publishedAt") for pl in plats if pl.get("publishedAt")]
    return {
        "id": zp_.get("_id"),
        "source": "provider",
        "zernio_post_id": zp_.get("_id"),
        "content": zp_.get("content"),
        "media_urls": [m.get("url") for m in (zp_.get("mediaItems") or []) if isinstance(m, dict) and m.get("url")],
        "platforms": [str(pl.get("platform")) for pl in plats],
        "account_ids": [str(pl.get("accountId")) for pl in plats if pl.get("accountId")],
        "status": str(zp_.get("status") or "").lower(),
        "scheduled_for": zp_.get("scheduledFor"),
        "published_at": min(published) if published else None,
        "queued": bool(zp_.get("queuedFromProfile")),
        "queue_id": zp_.get("queueId"),
        "timezone": zp_.get("timezone"),
        "publish_error": "; ".join(_zp.platform_errors(zp_)) or None,
        "platform_urls": [pl.get("platformPostUrl") for pl in plats if pl.get("platformPostUrl")],
        "created_at": zp_.get("createdAt"),
    }


async def _provider_posts_for_tenant(tenant_id: uuid.UUID, status_: Optional[str], page: int, limit: int,
                                     platform: Optional[str] = None, sort_by: Optional[str] = None) -> Dict[str, Any]:
    """Live provider posts for THIS tenant's profile, with every entry re-checked against the
    tenant's own account ids (fail closed: a post touching a foreign account is dropped)."""
    from services.marketing.zernio_errors import provider_error

    client = get_zernio_client()
    if client is None:
        raise HTTPException(status_code=503, detail="Zernio not configured (ZERNIO_API_KEY missing)")
    profile_id = _get_tenant_profile(tenant_id)
    if not profile_id:
        return {"posts": [], "pagination": {"page": page, "limit": limit, "total": 0, "pages": 0}}
    try:
        data = await client.list_posts(status=status_, limit=limit, profile_id=profile_id, page=page,
                                       platform=platform, sort_by=sort_by)
    except Exception as exc:  # noqa: BLE001
        raise provider_error("list posts", exc)
    mine = _tenant_account_ids(tenant_id)
    posts = []
    for zpost in (data or {}).get("posts") or []:
        accts = {str(pl.get("accountId")) for pl in (zpost.get("platforms") or []) if isinstance(pl, dict)}
        if accts and accts <= mine:
            posts.append(_provider_post_view(zpost))
    return {"posts": posts, "pagination": (data or {}).get("pagination") or {}}


@app.get("/social/posts/scheduled", response_model=Dict[str, Any])
async def list_scheduled_posts(
    include_provider: bool = Query(False, description="also merge posts that exist only at the provider (created elsewhere)"),
    platform: Optional[str] = None,
    queued: Optional[bool] = None,
    from_date: Optional[datetime] = Query(None, alias="from"),
    to_date: Optional[datetime] = Query(None, alias="to"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Everything waiting to go out: scheduled + queued posts, soonest first. This is what the
    Scheduled view should call. With include_provider=true, posts that exist at the provider but
    not in OmniDome are appended (flagged source='provider')."""
    async with get_session() as session:
        base = _apply_post_filters(select(SocialPost), tenant_id, "scheduled", None, None, platform, queued, from_date, to_date)
        total = (await session.execute(select(func.count()).select_from(base.subquery()))).scalar() or 0
        rows = (await session.execute(_sort_posts(base, "scheduled_asc").limit(limit).offset(offset))).scalars().all()
    posts = [{**_post_dict(p), "source": "local"} for p in rows]
    provider_error_msg = None
    if include_provider:
        known = {p["zernio_post_id"] for p in posts if p.get("zernio_post_id")}
        try:
            prov = await _provider_posts_for_tenant(tenant_id, "scheduled", 1, 100, platform, "scheduled-asc")
            extra = [p for p in prov["posts"] if p["zernio_post_id"] not in known]
            posts.extend(extra)
            total += len(extra)
        except HTTPException as exc:  # the local list is still valid; say why the merge is missing
            provider_error_msg = _detail_text(exc)
    out: Dict[str, Any] = {"posts": posts, "total": total, "limit": limit, "offset": offset}
    if provider_error_msg:
        out["provider_error"] = provider_error_msg
    return out


@app.get("/social/posts/provider", response_model=Dict[str, Any])
async def list_provider_posts(
    post_status: Optional[str] = Query(None, alias="status"),
    platform: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Live posts from the provider for this tenant's profile (draft|scheduled|publishing|published|
    partial|failed|cancelled), paginated by the provider."""
    from services.marketing import zernio_posts as zp
    statuses, _ = zp.parse_status_filter(post_status)
    return await _provider_posts_for_tenant(tenant_id, statuses[0] if statuses else None, page, limit, platform)


@app.post("/social/posts/sync", response_model=Dict[str, Any], dependencies=[Depends(require_marketing_write)])
async def sync_post_statuses(tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    """Refresh the status of OmniDome posts that exist at the provider (scheduled -> published/failed...)."""
    from services.marketing import zernio_posts as zp

    updated = 0
    for st in ("scheduled", "publishing", "published", "partial", "failed"):
        data = await _provider_posts_for_tenant(tenant_id, st, 1, 100)
        for zpost in data["posts"]:
            zid = zpost["zernio_post_id"]
            if not zid:
                continue
            async with get_session() as session:
                row = (await session.execute(select(SocialPost).where(
                    SocialPost.tenant_id == tenant_id, SocialPost.zernio_post_id == zid))).scalar_one_or_none()
                if row is None:
                    continue
                new = zp.norm_status(zpost["status"], default=row.status)
                if new != str(row.status).lower() or (zpost.get("publish_error") or None) != row.publish_error:
                    row.status = new
                    row.publish_error = zpost.get("publish_error")
                    if new in ("published", "partial") and not row.published_at:
                        row.published_at = datetime.now(timezone.utc)
                    updated += 1
    return {"updated": updated}


def _tenant_account_rows(tenant_id: uuid.UUID) -> List[Dict[str, Any]]:
    engine = get_engine()
    _ensure_marketing_tables(engine)
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT account_id, platform, status FROM marketing_connected_accounts WHERE tenant_id = :tid"),
            {"tid": str(tenant_id)},
        ).mappings().all()
    return [dict(r) for r in rows]


async def _push_post(post, tenant_id: uuid.UUID, intent: str, *, account_ids: Optional[List[str]] = None,
                     media_items: Optional[List[Dict[str, Any]]] = None, provider_draft: bool = False) -> None:
    """Send a SocialPost to the provider according to `intent` (now | schedule | queue | draft) and
    copy the provider's real answer (status, per-platform errors, ids) onto the row. Raises
    HTTPException for prerequisites (no provider key, no connected account, provider rejection).
    Nothing is invented: a provider rejection never leaves the post looking published/scheduled."""
    from services.marketing import zernio_posts as zp
    from services.marketing.zernio_errors import provider_error

    if intent == "draft" and not provider_draft:
        post.status = "draft"
        return
    client = get_zernio_client()
    if client is None:
        raise HTTPException(status_code=503, detail="Zernio not configured (ZERNIO_API_KEY missing)")
    _require_tenant_profile(tenant_id)
    targets, missing = zp.build_targets(post.platforms or [], account_ids, _tenant_account_rows(tenant_id))
    if account_ids and missing:
        raise HTTPException(status_code=403, detail="One or more account_ids do not belong to this workspace")
    if missing or not targets:
        raise HTTPException(
            status_code=400,
            detail="No connected account for: " + ", ".join(missing or ["any selected platform"]) + " - connect it under Connections first",
        )
    kwargs: Dict[str, Any] = {"idempotency_key": f"omnidome-post-{post.id}-{intent}"}
    if post.timezone:
        kwargs["timezone"] = post.timezone
    if media_items:
        kwargs["media_items"] = media_items
    if intent == "now":
        kwargs["publish_now"] = True
    elif intent in ("schedule", "queue"):
        if not post.scheduled_for:
            raise HTTPException(status_code=422, detail="scheduled_for is required to schedule a post")
        try:
            when = zp.check_schedule_time(post.scheduled_for)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        kwargs.update(publish_now=False, schedule_date=zp.iso_z(when))
    else:  # provider draft
        kwargs.update(publish_now=False, is_draft=True)
    try:
        zpost = await client.publish_content(
            content=post.content or "", platforms=targets, media_urls=post.media_urls or None, **kwargs,
        )
    except Exception as exc:  # noqa: BLE001
        raise provider_error("publish post", exc)
    fields = zp.result_fields(zpost, "draft" if kwargs.get("is_draft") else intent)
    post.status = fields["status"]
    post.publish_error = fields["publish_error"]
    post.zernio_post_id = fields["zernio_post_id"]
    post.platform_post_ids = {"zernio_post_id": fields["zernio_post_id"], "platforms": fields["platforms_info"]}
    if fields.get("published_at") and not post.published_at:
        post.published_at = fields["published_at"]


async def _legacy_account(session, tenant_id: uuid.UUID, account_id: Optional[uuid.UUID], platform_hint: str):
    """SocialPost.account_id is a NOT NULL FK to the legacy credentials table. Use the id the client
    sent when it is this tenant's row, otherwise the tenant's stub row for the platform."""
    if account_id:
        acct = (await session.execute(select(SocialMediaAccount).where(
            SocialMediaAccount.id == account_id, SocialMediaAccount.tenant_id == tenant_id))).scalar_one_or_none()
        if acct:
            return acct
    return await _resolve_inbox_account(session, tenant_id, platform_hint or "social")


async def _create_post_core(body: "SocialPostCreate", tenant_id: uuid.UUID) -> Dict[str, Any]:
    from services.marketing import zernio_posts as zp

    intent = zp.derive_intent(body.status, body.scheduled_for, body.queue_id)
    platforms = [zp.norm_platform(p) for p in (body.platforms or []) if p]
    media_urls = list(body.media_urls or [])
    media_items = [m for m in (body.media_items or []) if isinstance(m, dict) and m.get("url")]
    for m in media_items:
        if m["url"] not in media_urls:
            media_urls.append(m["url"])
    if intent in ("schedule", "queue"):
        if not body.scheduled_for:
            raise HTTPException(status_code=422, detail="scheduled_for is required when status is 'scheduled'")
        try:
            zp.check_schedule_time(body.scheduled_for)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
    if intent != "draft":
        if not platforms and not body.account_ids:
            raise HTTPException(status_code=422, detail="Select at least one platform")
        if not (body.content or media_urls):
            raise HTTPException(status_code=422, detail="Post needs text or media")

    initial = {"now": "publishing", "schedule": "scheduled", "queue": "scheduled", "draft": "draft"}[intent]
    async with get_session() as session:
        account = await _legacy_account(session, tenant_id, body.account_id, platforms[0] if platforms else "social")
        post = SocialPost(
            tenant_id=tenant_id,
            account_id=account.id,
            campaign_id=body.campaign_id,
            content=body.content,
            media_urls=media_urls or None,
            platforms=platforms,
            status=initial,
            scheduled_for=zp.to_utc(body.scheduled_for) if body.scheduled_for else None,
            queue_id=body.queue_id,
            timezone=body.timezone,
        )
        session.add(post)
        await session.flush()

        publish_error: Optional[str] = None
        try:
            await _push_post(post, tenant_id, intent, account_ids=body.account_ids, media_items=media_items,
                             provider_draft=body.provider_draft)
        except HTTPException as e:
            publish_error = _detail_text(e)
            post.status = "failed"
            post.publish_error = publish_error

        await session.flush()
        await session.refresh(post)
        out = _post_dict(post)
        out["publish_error"] = publish_error or out.get("publish_error")
        return out


@app.post("/social/posts", status_code=201, response_model=Dict[str, Any], dependencies=[Depends(require_marketing_write)])
async def create_social_post(
    body: SocialPostCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Create a social post.

    status=draft      saved in OmniDome (provider_draft=true also stores a provider draft)
    status=scheduled  scheduled at the provider for scheduled_for (UTC ISO; must be >= 30s ahead)
    status=scheduled + queue_id   same, at the next open slot (prefer POST /social/queues/{id}/enqueue)
    status=published  published now
    A provider rejection is reported (status 'failed' + publish_error), never faked as success."""
    return await _create_post_core(body, tenant_id)


@app.get("/social/posts/{post_id}", response_model=Dict[str, Any])
async def get_social_post(
    post_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Get a specific social media post."""
    async with get_session() as session:
        stmt = select(SocialPost).where(
            SocialPost.id == post_id,
            SocialPost.tenant_id == tenant_id,
        )
        result = await session.execute(stmt)
        post = result.scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    return _post_dict(post)


@app.put("/social/posts/{post_id}", response_model=Dict[str, Any], dependencies=[Depends(require_marketing_write)])
async def update_social_post(
    post_id: uuid.UUID,
    body: SocialPostUpdate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Update a social media post (content / media / schedule). A post already at the provider is
    updated there first, so the edit really changes what will be published."""
    from services.marketing import zernio_posts as zp
    from services.marketing.zernio_errors import provider_error

    async with get_session() as session:
        stmt = select(SocialPost).where(
            SocialPost.id == post_id,
            SocialPost.tenant_id == tenant_id,
        )
        result = await session.execute(stmt)
        post = result.scalar_one_or_none()
        if not post:
            raise HTTPException(status_code=404, detail="Post not found")
        if str(post.status).lower() in ("published", "publishing"):
            raise HTTPException(status_code=400, detail="Cannot update a published post")

        update_data = body.model_dump(exclude_unset=True)
        if "scheduled_for" in update_data and update_data["scheduled_for"] is not None:
            try:
                update_data["scheduled_for"] = zp.check_schedule_time(update_data["scheduled_for"])
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc))
        if post.zernio_post_id and str(post.status).lower() in ("scheduled", "draft", "failed", "partial"):
            client = get_zernio_client()
            if client is None:
                raise HTTPException(status_code=503, detail="Zernio not configured (ZERNIO_API_KEY missing)")
            patch: Dict[str, Any] = {}
            if "content" in update_data:
                patch["content"] = update_data["content"] or ""
            if update_data.get("scheduled_for"):
                patch["scheduledFor"] = zp.iso_z(update_data["scheduled_for"])
                patch["isDraft"] = False
            if "media_urls" in update_data and update_data["media_urls"] is not None:
                patch["mediaItems"] = [{"type": _guess_media_type(u), "url": u} for u in update_data["media_urls"]]
            if patch:
                try:
                    await client._request("PUT", f"/posts/{post.zernio_post_id}", json_data=patch)
                except Exception as exc:  # noqa: BLE001
                    raise provider_error("update post", exc)
        for field, value in update_data.items():
            setattr(post, field, value)
        await session.flush()
        await session.refresh(post)
        return _post_dict(post)


@app.delete("/social/posts/{post_id}", status_code=204, dependencies=[Depends(require_marketing_write)])
async def delete_social_post(
    post_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Delete a post. A scheduled/draft post at the provider is deleted there FIRST (otherwise it
    would still publish); published posts only disappear from OmniDome (use the platform to remove them)."""
    from services.marketing.zernio_client import ZernioError
    from services.marketing.zernio_errors import provider_error

    async with get_session() as session:
        stmt = select(SocialPost).where(
            SocialPost.id == post_id,
            SocialPost.tenant_id == tenant_id,
        )
        result = await session.execute(stmt)
        post = result.scalar_one_or_none()
        if not post:
            raise HTTPException(status_code=404, detail="Post not found")
        if post.zernio_post_id and str(post.status).lower() != "published":
            client = get_zernio_client()
            if client is not None:
                try:
                    await client.delete_post(post.zernio_post_id)
                except ZernioError as exc:
                    if exc.status != 404:  # already gone at the provider is fine
                        raise provider_error("delete post", exc)
                except Exception as exc:  # noqa: BLE001
                    raise provider_error("delete post", exc)
        await session.delete(post)
    return None


@app.post("/social/posts/{post_id}/publish", response_model=Dict[str, Any], dependencies=[Depends(require_marketing_write)])
async def publish_post(
    post_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Publish a stored post immediately."""
    async with get_session() as session:
        stmt = select(SocialPost).where(
            SocialPost.id == post_id,
            SocialPost.tenant_id == tenant_id,
        )
        result = await session.execute(stmt)
        post = result.scalar_one_or_none()
        if not post:
            raise HTTPException(status_code=404, detail="Post not found")
        if str(post.status).lower() == "published":
            raise HTTPException(status_code=400, detail="Post is already published")

        if post.zernio_post_id:
            # exists at the provider (draft / scheduled / failed): promote it instead of creating a duplicate
            client = get_zernio_client()
            if client is None:
                raise HTTPException(status_code=503, detail="Zernio not configured (ZERNIO_API_KEY missing)")
            from services.marketing import zernio_posts as zp
            from services.marketing.zernio_errors import provider_error
            try:
                zpost = await client._request("PUT", f"/posts/{post.zernio_post_id}", json_data={"isDraft": False, "publishNow": True})
            except Exception as exc:  # noqa: BLE001
                raise provider_error("publish post", exc)
            fields = zp.result_fields((zpost or {}).get("post", zpost) if isinstance(zpost, dict) else {}, "now")
            post.status, post.publish_error = fields["status"], fields["publish_error"]
            if fields.get("published_at"):
                post.published_at = fields["published_at"]
        else:
            await _push_post(post, tenant_id, "now")
        await session.flush()
        await session.refresh(post)
        return {
            "id": post.id,
            "status": str(post.status).lower(),
            "published_at": post.published_at,
            "platform_post_ids": post.platform_post_ids,
            "publish_error": post.publish_error,
        }


def _to_utc(dt: datetime) -> datetime:
    """Naive input is taken as UTC; aware input is converted to UTC."""
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


@app.post("/social/posts/{post_id}/schedule", response_model=Dict[str, Any], dependencies=[Depends(require_marketing_write)])
async def schedule_post(
    post_id: uuid.UUID,
    scheduled_for: datetime,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Schedule a stored post for later at the provider (it used to only flip a local flag)."""
    scheduled_for = _to_utc(scheduled_for)
    if scheduled_for <= datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Scheduled time must be in the future")

    async with get_session() as session:
        stmt = select(SocialPost).where(
            SocialPost.id == post_id,
            SocialPost.tenant_id == tenant_id,
        )
        result = await session.execute(stmt)
        post = result.scalar_one_or_none()
        if not post:
            raise HTTPException(status_code=404, detail="Post not found")
        if str(post.status).lower() in ("published", "publishing"):
            raise HTTPException(status_code=400, detail="Post is already published")

        post.scheduled_for = scheduled_for
        if post.zernio_post_id:
            client = get_zernio_client()
            if client is None:
                raise HTTPException(status_code=503, detail="Zernio not configured (ZERNIO_API_KEY missing)")
            from services.marketing import zernio_posts as zp
            from services.marketing.zernio_errors import provider_error
            try:
                zpost = await client._request("PUT", f"/posts/{post.zernio_post_id}",
                                              json_data={"isDraft": False, "scheduledFor": zp.iso_z(scheduled_for)})
            except Exception as exc:  # noqa: BLE001
                raise provider_error("schedule post", exc)
            fields = zp.result_fields((zpost or {}).get("post", zpost) if isinstance(zpost, dict) else {}, "schedule")
            post.status, post.publish_error = fields["status"], fields["publish_error"]
        else:
            await _push_post(post, tenant_id, "schedule")
        await session.flush()
        await session.refresh(post)
        return {
            "id": post.id,
            "status": str(post.status).lower(),
            "scheduled_for": post.scheduled_for,
            "publish_error": post.publish_error,
        }


# ──────────────────── Media upload (posts + ads) ────────────────────

_MEDIA_TYPES = {
    "image/jpeg", "image/jpg", "image/png", "image/webp", "image/gif",
    "video/mp4", "video/mpeg", "video/quicktime", "video/avi", "video/x-msvideo", "video/webm", "video/x-m4v",
    "application/pdf",
}
_MEDIA_MAX_BYTES = int(os.getenv("MARKETING_MEDIA_MAX_BYTES", str(100 * 1024 * 1024)))


class MediaPresignIn(BaseModel):
    filename: str = Field(..., min_length=1, max_length=200)
    content_type: str
    size: Optional[int] = Field(None, ge=1)

    @field_validator("filename")
    @classmethod
    def _clean_name(cls, v: str) -> str:
        import re as _re
        base = v.replace("\\", "/").rsplit("/", 1)[-1]
        base = _re.sub(r"[^A-Za-z0-9._\- ]", "_", base).strip(" .")
        if not base:
            raise ValueError("invalid filename")
        return base[:150]


@app.post("/social/media/presign", response_model=Dict[str, Any], dependencies=[Depends(require_marketing_write)])
async def presign_media(body: MediaPresignIn, tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    """Browser-direct upload: returns {upload_url, public_url, key, expires_in}. The browser PUTs the
    file to upload_url (Content-Type header = content_type, no auth), then uses public_url as a
    media_urls entry on posts or as image_url / video_url on ads. Up to the provider's 5 GB limit."""
    from services.marketing.zernio_errors import provider_error

    ct = body.content_type.strip().lower()
    if ct not in _MEDIA_TYPES:
        raise HTTPException(status_code=422, detail=f"Unsupported media type '{ct}'. Allowed: {sorted(_MEDIA_TYPES)}")
    client = get_zernio_client()
    if client is None:
        raise HTTPException(status_code=503, detail="Zernio not configured (ZERNIO_API_KEY missing)")
    try:
        res = await client.presign_media(body.filename, ct, body.size)
    except Exception as exc:  # noqa: BLE001
        raise provider_error("media presign", exc)
    return {"upload_url": res.get("uploadUrl"), "public_url": res.get("publicUrl"), "key": res.get("key"),
            "expires_in": res.get("expiresIn", 3600), "content_type": ct}


class MediaBase64In(BaseModel):
    filename: str = Field(..., min_length=1, max_length=200)
    content_type: str
    data_base64: str = Field(..., min_length=4, description="Raw base64 (a data: URL prefix is tolerated)")

    @field_validator("filename")
    @classmethod
    def _clean_name(cls, v: str) -> str:
        return MediaPresignIn(filename=v, content_type="image/png").filename


@app.post("/social/media/upload-base64", status_code=201, response_model=Dict[str, Any], dependencies=[Depends(require_marketing_write)])
async def upload_media_base64(body: MediaBase64In, tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    """Upload through the JSON-only /svc proxy (which forwards bodies as text, so multipart/binary is not
    safe through it). Same result as /social/media/upload; ~33% bigger on the wire, so keep to a few MB."""
    import base64
    import binascii
    from services.marketing.zernio_errors import provider_error

    ct = body.content_type.strip().lower()
    if ct not in _MEDIA_TYPES:
        raise HTTPException(status_code=422, detail=f"Unsupported media type '{ct}'. Allowed: {sorted(_MEDIA_TYPES)}")
    raw = body.data_base64.split(",", 1)[1] if body.data_base64.startswith("data:") and "," in body.data_base64 else body.data_base64
    try:
        data = base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(status_code=422, detail="data_base64 is not valid base64")
    if not data:
        raise HTTPException(status_code=422, detail="Empty file")
    if len(data) > _MEDIA_MAX_BYTES:
        raise HTTPException(status_code=413, detail=f"File too large (max {_MEDIA_MAX_BYTES // (1024 * 1024)} MB); use /social/media/presign")
    client = get_zernio_client()
    if client is None:
        raise HTTPException(status_code=503, detail="Zernio not configured (ZERNIO_API_KEY missing)")
    try:
        res = await client.presign_media(body.filename, ct, len(data))
        await client.put_presigned(res["uploadUrl"], data, ct)
    except Exception as exc:  # noqa: BLE001
        raise provider_error("media upload", exc)
    return {"public_url": res.get("publicUrl"), "key": res.get("key"), "content_type": ct, "size": len(data),
            "type": _guess_media_type(body.filename)}


@app.post("/social/media/upload", status_code=201, response_model=Dict[str, Any], dependencies=[Depends(require_marketing_write)])
async def upload_media(request: Request, tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    """Server-side upload (multipart/form-data, field `file`, up to MARKETING_MEDIA_MAX_BYTES, default
    100 MB): the file is pushed to the provider's media storage and {public_url, ...} is returned.
    Use /social/media/presign instead for larger files."""
    from services.marketing.zernio_errors import provider_error

    form = await request.form()
    up = form.get("file")
    if up is None or not hasattr(up, "read"):
        raise HTTPException(status_code=422, detail="multipart field 'file' is required")
    ct = (getattr(up, "content_type", "") or "").lower()
    if ct not in _MEDIA_TYPES:
        raise HTTPException(status_code=422, detail=f"Unsupported media type '{ct}'. Allowed: {sorted(_MEDIA_TYPES)}")
    data = await up.read(_MEDIA_MAX_BYTES + 1)
    if len(data) > _MEDIA_MAX_BYTES:
        raise HTTPException(status_code=413, detail=f"File too large (max {_MEDIA_MAX_BYTES // (1024 * 1024)} MB); use /social/media/presign")
    if not data:
        raise HTTPException(status_code=422, detail="Empty file")
    name = MediaPresignIn(filename=getattr(up, "filename", None) or "upload", content_type=ct).filename
    client = get_zernio_client()
    if client is None:
        raise HTTPException(status_code=503, detail="Zernio not configured (ZERNIO_API_KEY missing)")
    try:
        res = await client.presign_media(name, ct, len(data))
        await client.put_presigned(res["uploadUrl"], data, ct)
    except Exception as exc:  # noqa: BLE001
        raise provider_error("media upload", exc)
    return {"public_url": res.get("publicUrl"), "key": res.get("key"), "content_type": ct, "size": len(data),
            "type": _guess_media_type(name)}


@app.post("/social/posts/cross-post", response_model=CrossPostResponse, dependencies=[Depends(require_marketing_write)])
async def cross_post(
    body: CrossPostRequest,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Post the same content to multiple social media accounts/platforms."""
    if not body.account_ids:
        raise HTTPException(status_code=400, detail="At least one account_id is required")

    created_posts = []
    async with get_session() as session:
        for account_id in body.account_ids:
            post = SocialPost(
                tenant_id=tenant_id,
                account_id=account_id,
                content=body.content,
                media_urls=body.media_urls,
                platforms=[],
                status="DRAFT",
                scheduled_for=body.scheduled_for,
            )
            session.add(post)
            await session.flush()
            await session.refresh(post)
            created_posts.append(
                SocialPostOut(
                    id=post.id,
                    tenant_id=post.tenant_id,
                    account_id=post.account_id,
                    campaign_id=post.campaign_id,
                    content=post.content,
                    media_urls=post.media_urls,
                    platforms=post.platforms,
                    status=post.status,
                    scheduled_for=post.scheduled_for,
                    published_at=post.published_at,
                    platform_post_ids=post.platform_post_ids,
                    engagement_data=post.engagement_data,
                    created_at=post.created_at,
                    updated_at=post.updated_at,
                )
            )
    return CrossPostResponse(posts=created_posts, total_created=len(created_posts))


@app.get("/social/posts/{post_id}/analytics", response_model=Dict[str, Any])
async def get_post_analytics(
    post_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Get engagement data for a specific post."""
    async with get_session() as session:
        stmt = select(SocialPost).where(
            SocialPost.id == post_id,
            SocialPost.tenant_id == tenant_id,
        )
        result = await session.execute(stmt)
        post = result.scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    return {
        "post_id": post.id,
        "engagement_data": post.engagement_data or {},
        "platform_post_ids": post.platform_post_ids or {},
        "status": post.status,
        "published_at": post.published_at,
    }


# ──────────────────── Social Inbox ────────────────────────


@app.get("/social/inbox", response_model=List[Dict[str, Any]])
async def list_inbox_messages(
    inbox_status: Optional[str] = Query(None, alias="status"),
    platform: Optional[str] = None,
    message_type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """List social inbox messages with optional filters."""
    async with get_session() as session:
        stmt = select(SocialInboxMessage).where(SocialInboxMessage.tenant_id == tenant_id)
        if inbox_status:
            stmt = stmt.where(SocialInboxMessage.status == inbox_status)
        if platform:
            stmt = stmt.where(SocialInboxMessage.platform == platform)
        if message_type:
            stmt = stmt.where(SocialInboxMessage.message_type == message_type)
        stmt = stmt.order_by(SocialInboxMessage.created_at.desc()).limit(limit).offset(offset)
        result = await session.execute(stmt)
        messages = result.scalars().all()
    return [
        {
            "id": m.id,
            "tenant_id": m.tenant_id,
            "account_id": m.account_id,
            "platform": m.platform,
            "message_type": m.message_type,
            "external_id": m.external_id,
            "sender_name": m.sender_name,
            "sender_handle": m.sender_handle,
            "content": m.content,
            "status": m.status,
            "sentiment": m.sentiment,
            "replied_at": m.replied_at,
            "created_at": m.created_at,
        }
        for m in messages
    ]


@app.get("/social/inbox/unread-count", response_model=UnreadCountResponse)
async def get_unread_count(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Get the count of unread inbox messages."""
    async with get_session() as session:
        stmt = select(func.count(SocialInboxMessage.id)).where(
            SocialInboxMessage.tenant_id == tenant_id,
            SocialInboxMessage.status == "UNREAD",
        )
        result = await session.execute(stmt)
        count = result.scalar()
    return UnreadCountResponse(unread_count=count or 0)


@app.get("/social/inbox/{message_id}", response_model=Dict[str, Any])
async def get_inbox_message(
    message_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Get a specific inbox message."""
    async with get_session() as session:
        stmt = select(SocialInboxMessage).where(
            SocialInboxMessage.id == message_id,
            SocialInboxMessage.tenant_id == tenant_id,
        )
        result = await session.execute(stmt)
        msg = result.scalar_one_or_none()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    return {
        "id": msg.id,
        "tenant_id": msg.tenant_id,
        "account_id": msg.account_id,
        "platform": msg.platform,
        "message_type": msg.message_type,
        "external_id": msg.external_id,
        "sender_name": msg.sender_name,
        "sender_handle": msg.sender_handle,
        "sender_profile_url": msg.sender_profile_url,
        "content": msg.content,
        "parent_id": msg.parent_id,
        "status": msg.status,
        "sentiment": msg.sentiment,
        "replied_at": msg.replied_at,
        "created_at": msg.created_at,
    }


@app.post("/social/inbox/{message_id}/reply", response_model=Dict[str, Any], dependencies=[Depends(require_marketing_write)])
async def reply_to_message(
    message_id: uuid.UUID,
    body: InboxReplyRequest,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Reply to a social inbox message — via Zernio when configured.

    Needs the Zernio conversation_id, which the webhook stores on the
    SocialWebhookEvent payload (payload.conversation_id) matched by
    external_id. Without a key or conversation match, the reply is recorded
    locally with sent_via="local" so the agent UI stays truthful.
    """
    async with get_session() as session:
        stmt = select(SocialInboxMessage).where(
            SocialInboxMessage.id == message_id,
            SocialInboxMessage.tenant_id == tenant_id,
        )
        result = await session.execute(stmt)
        msg = result.scalar_one_or_none()
        if not msg:
            raise HTTPException(status_code=404, detail="Message not found")

        sent_via = "local"
        conversation_id: Optional[str] = None
        evt_stmt = select(SocialWebhookEvent).where(
            SocialWebhookEvent.tenant_id == tenant_id,
            SocialWebhookEvent.payload["external_id"].astext == (msg.external_id or ""),
        ).order_by(SocialWebhookEvent.created_at.desc()).limit(1) if msg.external_id else None
        if evt_stmt is not None:
            evt_result = await session.execute(evt_stmt)
            evt = evt_result.scalar_one_or_none()
            if evt and isinstance(evt.payload, dict):
                conversation_id = evt.payload.get("conversation_id")

        client = get_zernio_client()
        if client is not None and conversation_id:
            try:
                await client.send_inbox_message(
                    conversation_id=conversation_id,
                    content=body.content,
                )
                sent_via = "zernio"
            except Exception as e:
                logger.error(f"Zernio reply failed, recording locally: {e}")

        msg.status = "REPLIED"
        msg.replied_at = datetime.now(timezone.utc)
        await session.flush()
        return {
            "id": msg.id,
            "status": msg.status,
            "replied_at": msg.replied_at,
            "reply_content": body.content,
            "sent_via": sent_via,
        }


@app.put("/social/inbox/{message_id}/read", response_model=Dict[str, Any], dependencies=[Depends(require_marketing_write)])
async def mark_message_read(
    message_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Mark an inbox message as read."""
    async with get_session() as session:
        stmt = select(SocialInboxMessage).where(
            SocialInboxMessage.id == message_id,
            SocialInboxMessage.tenant_id == tenant_id,
        )
        result = await session.execute(stmt)
        msg = result.scalar_one_or_none()
        if not msg:
            raise HTTPException(status_code=404, detail="Message not found")
        msg.status = "READ"
        await session.flush()
        return {"id": msg.id, "status": msg.status}


@app.put("/social/inbox/{message_id}/archive", response_model=Dict[str, Any], dependencies=[Depends(require_marketing_write)])
async def archive_message(
    message_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Archive an inbox message."""
    async with get_session() as session:
        stmt = select(SocialInboxMessage).where(
            SocialInboxMessage.id == message_id,
            SocialInboxMessage.tenant_id == tenant_id,
        )
        result = await session.execute(stmt)
        msg = result.scalar_one_or_none()
        if not msg:
            raise HTTPException(status_code=404, detail="Message not found")
        msg.status = "ARCHIVED"
        await session.flush()
        return {"id": msg.id, "status": msg.status}


# ──────────────────── Social Analytics ────────────────────────


@app.get("/social/analytics/account/{account_id}", response_model=List[Dict[str, Any]])
async def get_account_analytics(
    account_id: uuid.UUID,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Get account-level analytics."""
    async with get_session() as session:
        # Verify account belongs to tenant
        acct_stmt = select(SocialMediaAccount).where(
            SocialMediaAccount.id == account_id,
            SocialMediaAccount.tenant_id == tenant_id,
        )
        acct_result = await session.execute(acct_stmt)
        if not acct_result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Account not found")

        stmt = select(SocialAnalytics).where(
            SocialAnalytics.account_id == account_id,
            SocialAnalytics.tenant_id == tenant_id,
        )
        if start_date:
            stmt = stmt.where(SocialAnalytics.metric_date >= start_date)
        if end_date:
            stmt = stmt.where(SocialAnalytics.metric_date <= end_date)
        stmt = stmt.order_by(SocialAnalytics.metric_date.desc())
        result = await session.execute(stmt)
        analytics = result.scalars().all()
    return [
        {
            "id": a.id,
            "account_id": a.account_id,
            "platform": a.platform,
            "metric_date": a.metric_date,
            "followers": a.followers,
            "following": a.following,
            "posts_count": a.posts_count,
            "impressions": a.impressions,
            "reach": a.reach,
            "engagement_rate": float(a.engagement_rate) if a.engagement_rate else None,
            "likes_total": a.likes_total,
            "comments_total": a.comments_total,
            "shares_total": a.shares_total,
            "profile_views": a.profile_views,
            "website_clicks": a.website_clicks,
            "best_post_time": a.best_post_time,
            "demographics": a.demographics,
        }
        for a in analytics
    ]


@app.get("/social/analytics/platform/{platform}", response_model=PlatformAnalyticsOut)
async def get_platform_analytics(
    platform: str,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Get aggregated analytics for a platform across all accounts."""
    async with get_session() as session:
        stmt = select(
            func.sum(SocialAnalytics.followers).label("total_followers"),
            func.sum(SocialAnalytics.impressions).label("total_impressions"),
            func.sum(SocialAnalytics.reach).label("total_reach"),
            func.avg(SocialAnalytics.engagement_rate).label("avg_engagement_rate"),
            func.sum(SocialAnalytics.likes_total).label("total_likes"),
            func.sum(SocialAnalytics.comments_total).label("total_comments"),
            func.sum(SocialAnalytics.shares_total).label("total_shares"),
        ).where(
            SocialAnalytics.tenant_id == tenant_id,
            SocialAnalytics.platform == platform,
        )
        result = await session.execute(stmt)
        row = result.one()
    return PlatformAnalyticsOut(
        platform=platform,
        total_followers=row.total_followers or 0,
        total_impressions=row.total_impressions or 0,
        total_reach=row.total_reach or 0,
        avg_engagement_rate=row.avg_engagement_rate,
        total_likes=row.total_likes or 0,
        total_comments=row.total_comments or 0,
        total_shares=row.total_shares or 0,
    )


@app.get("/social/analytics/engagement", response_model=EngagementSummaryOut)
async def get_engagement_summary(
    platform: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Get engagement summary across all social accounts."""
    async with get_session() as session:
        stmt = select(
            func.sum(SocialAnalytics.impressions).label("total_impressions"),
            func.sum(SocialAnalytics.reach).label("total_reach"),
            func.sum(SocialAnalytics.likes_total).label("total_likes"),
            func.sum(SocialAnalytics.comments_total).label("total_comments"),
            func.sum(SocialAnalytics.shares_total).label("total_shares"),
            func.avg(SocialAnalytics.engagement_rate).label("avg_engagement_rate"),
            func.min(SocialAnalytics.metric_date).label("period_start"),
            func.max(SocialAnalytics.metric_date).label("period_end"),
        ).where(SocialAnalytics.tenant_id == tenant_id)
        if platform:
            stmt = stmt.where(SocialAnalytics.platform == platform)
        if start_date:
            stmt = stmt.where(SocialAnalytics.metric_date >= start_date)
        if end_date:
            stmt = stmt.where(SocialAnalytics.metric_date <= end_date)
        result = await session.execute(stmt)
        row = result.one()
    return EngagementSummaryOut(
        total_impressions=row.total_impressions or 0,
        total_reach=row.total_reach or 0,
        total_likes=row.total_likes or 0,
        total_comments=row.total_comments or 0,
        total_shares=row.total_shares or 0,
        avg_engagement_rate=row.avg_engagement_rate,
        period_start=row.period_start,
        period_end=row.period_end,
    )


@app.get("/social/analytics/best-time", response_model=BestTimeToPostOut)
async def get_best_time_to_post(
    platform: Optional[str] = None,
    account_id: Optional[uuid.UUID] = None,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Get the best time to post based on historical analytics."""
    async with get_session() as session:
        stmt = select(SocialAnalytics.best_post_time).where(
            SocialAnalytics.tenant_id == tenant_id,
        )
        if platform:
            stmt = stmt.where(SocialAnalytics.platform == platform)
        if account_id:
            stmt = stmt.where(SocialAnalytics.account_id == account_id)
        stmt = stmt.order_by(SocialAnalytics.metric_date.desc()).limit(1)
        result = await session.execute(stmt)
        row = result.scalar_one_or_none()

    if row:
        return BestTimeToPostOut(
            platform=platform or "all",
            best_day=row.get("best_day") if isinstance(row, dict) else None,
            best_hour=row.get("best_hour") if isinstance(row, dict) else None,
            recommendations=row if isinstance(row, dict) else None,
        )
    # Default recommendations
    return BestTimeToPostOut(
        platform=platform or "all",
        best_day="Tuesday",
        best_hour=10,
        recommendations={
            "weekdays": ["Tuesday", "Wednesday", "Thursday"],
            "peak_hours": [9, 10, 11, 14, 15],
            "note": "Default recommendations based on industry averages",
        },
    )


# ═══════════════════════════════════════════════════════════════════════════════
# WHATSAPP ROUTES
# ═══════════════════════════════════════════════════════════════════════════════


@app.get("/whatsapp/contacts", response_model=List[Dict[str, Any]])
async def list_whatsapp_contacts(
    search: Optional[str] = None,
    tag: Optional[str] = None,
    opt_in: Optional[bool] = None,
    limit: int = 50,
    offset: int = 0,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """List WhatsApp contacts with optional filters."""
    async with get_session() as session:
        stmt = select(WhatsAppContact).where(WhatsAppContact.tenant_id == tenant_id)
        if search:
            stmt = stmt.where(
                WhatsAppContact.name.ilike(f"%{search}%")
                | WhatsAppContact.phone_number.ilike(f"%{search}%")
            )
        if opt_in is not None:
            stmt = stmt.where(WhatsAppContact.opt_in_status == opt_in)
        stmt = stmt.order_by(WhatsAppContact.created_at.desc()).limit(limit).offset(offset)
        result = await session.execute(stmt)
        contacts = result.scalars().all()
    return [
        {
            "id": c.id,
            "tenant_id": c.tenant_id,
            "name": c.name,
            "phone_number": c.phone_number,
            "email": c.email,
            "tags": c.tags,
            "opt_in_status": c.opt_in_status,
            "opt_in_date": c.opt_in_date,
            "last_interaction_at": c.last_interaction_at,
            "created_at": c.created_at,
            "updated_at": c.updated_at,
        }
        for c in contacts
    ]


@app.post("/whatsapp/contacts", status_code=201, response_model=Dict[str, Any], dependencies=[Depends(require_marketing_write)])
async def create_whatsapp_contact(
    body: WhatsAppContactCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Create a new WhatsApp contact."""
    async with get_session() as session:
        contact = WhatsAppContact(
            tenant_id=tenant_id,
            name=body.name,
            phone_number=body.phone_number,
            email=body.email,
            tags=body.tags,
            custom_fields=body.custom_fields,
            opt_in_status=body.opt_in_status,
            opt_in_date=datetime.utcnow() if body.opt_in_status else None,
        )
        session.add(contact)
        await session.flush()
        await session.refresh(contact)
        return {
            "id": contact.id,
            "tenant_id": contact.tenant_id,
            "name": contact.name,
            "phone_number": contact.phone_number,
            "email": contact.email,
            "tags": contact.tags,
            "opt_in_status": contact.opt_in_status,
            "created_at": contact.created_at,
        }


@app.post("/whatsapp/contacts/bulk-import", response_model=BulkImportResponse, dependencies=[Depends(require_marketing_write)])
async def bulk_import_contacts(
    body: BulkImportRequest,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Bulk import WhatsApp contacts."""
    imported = 0
    errors: List[Dict[str, Any]] = []
    async with get_session() as session:
        for i, contact_data in enumerate(body.contacts):
            try:
                contact = WhatsAppContact(
                    tenant_id=tenant_id,
                    name=contact_data.name,
                    phone_number=contact_data.phone_number,
                    email=contact_data.email,
                    tags=contact_data.tags,
                    custom_fields=contact_data.custom_fields,
                    opt_in_status=contact_data.opt_in_status,
                    opt_in_date=datetime.utcnow() if contact_data.opt_in_status else None,
                )
                session.add(contact)
                imported += 1
            except Exception as e:
                errors.append({"index": i, "error": str(e)})
        await session.flush()
    return BulkImportResponse(imported=imported, errors=errors)


@app.get("/whatsapp/broadcasts", response_model=List[Dict[str, Any]])
async def list_whatsapp_broadcasts(
    broadcast_status: Optional[str] = Query(None, alias="status"),
    limit: int = 50,
    offset: int = 0,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """List WhatsApp broadcasts."""
    async with get_session() as session:
        stmt = select(WhatsAppBroadcast).where(WhatsAppBroadcast.tenant_id == tenant_id)
        if broadcast_status:
            stmt = stmt.where(WhatsAppBroadcast.status == broadcast_status)
        stmt = stmt.order_by(WhatsAppBroadcast.created_at.desc()).limit(limit).offset(offset)
        result = await session.execute(stmt)
        broadcasts = result.scalars().all()
    return [
        {
            "id": b.id,
            "tenant_id": b.tenant_id,
            "name": b.name,
            "template_name": b.template_name,
            "content": b.content,
            "recipient_count": b.recipient_count,
            "sent_count": b.sent_count,
            "delivered_count": b.delivered_count,
            "read_count": b.read_count,
            "failed_count": b.failed_count,
            "status": b.status,
            "scheduled_for": b.scheduled_for,
            "sent_at": b.sent_at,
            "created_at": b.created_at,
            "updated_at": b.updated_at,
        }
        for b in broadcasts
    ]


@app.post("/whatsapp/broadcasts", status_code=201, response_model=Dict[str, Any], dependencies=[Depends(require_marketing_write)])
async def create_whatsapp_broadcast(
    body: WhatsAppBroadcastCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Create a new WhatsApp broadcast."""
    async with get_session() as session:
        broadcast = WhatsAppBroadcast(
            tenant_id=tenant_id,
            name=body.name,
            template_name=body.template_name,
            content=body.content,
            media_url=body.media_url,
            recipient_count=len(body.contact_ids),
            status="DRAFT",
            scheduled_for=body.scheduled_for,
        )
        session.add(broadcast)
        await session.flush()

        # Create recipients
        for contact_id in body.contact_ids:
            # Fetch contact phone number
            contact_stmt = select(WhatsAppContact).where(
                WhatsAppContact.id == contact_id,
                WhatsAppContact.tenant_id == tenant_id,
            )
            contact_result = await session.execute(contact_stmt)
            contact = contact_result.scalar_one_or_none()
            if contact:
                recipient = WhatsAppBroadcastRecipient(
                    tenant_id=tenant_id,
                    broadcast_id=broadcast.id,
                    contact_id=contact_id,
                    phone_number=contact.phone_number,
                    status="PENDING",
                )
                session.add(recipient)

        await session.refresh(broadcast)
        return {
            "id": broadcast.id,
            "tenant_id": broadcast.tenant_id,
            "name": broadcast.name,
            "template_name": broadcast.template_name,
            "content": broadcast.content,
            "recipient_count": broadcast.recipient_count,
            "status": broadcast.status,
            "scheduled_for": broadcast.scheduled_for,
            "created_at": broadcast.created_at,
        }


@app.post("/whatsapp/broadcasts/{broadcast_id}/send", response_model=BroadcastSendResponse, dependencies=[Depends(require_marketing_write)])
async def send_whatsapp_broadcast(
    broadcast_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Send a WhatsApp broadcast via Zernio's WhatsApp Business API.

    Real flow (no stub): resolve the tenant's Zernio profile + connected WhatsApp
    account, create a Zernio broadcast draft with the Meta-approved template, add
    the local recipients' phone numbers, then trigger the send. Zernio requires a
    connected WhatsApp Business Account (WABA) and an approved template.
    """
    client = get_zernio_client()
    if client is None:
        raise HTTPException(503, "Zernio not configured (ZERNIO_API_KEY missing)")

    profile_id = _require_tenant_profile(tenant_id)

    # Resolve the tenant's connected WhatsApp account.
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT account_id FROM marketing_connected_accounts "
                "WHERE tenant_id = :tid AND lower(platform) = 'whatsapp' AND status <> 'disconnected' "
                "LIMIT 1"
            ),
            {"tid": str(tenant_id)},
        ).first()
    if not row:
        raise HTTPException(
            400,
            "No connected WhatsApp account — connect a WhatsApp Business number under Connections first",
        )
    account_id = row[0]

    async with get_session() as session:
        stmt = select(WhatsAppBroadcast).where(
            WhatsAppBroadcast.id == broadcast_id,
            WhatsAppBroadcast.tenant_id == tenant_id,
        )
        result = await session.execute(stmt)
        broadcast = result.scalar_one_or_none()
        if not broadcast:
            raise HTTPException(status_code=404, detail="Broadcast not found")
        if broadcast.status not in ("DRAFT", "QUEUED"):
            raise HTTPException(status_code=400, detail=f"Cannot send broadcast with status: {broadcast.status}")
        if not broadcast.template_name:
            raise HTTPException(
                400,
                "WhatsApp broadcasts require a Meta-approved template — set template_name on the broadcast",
            )

        recipient_stmt = select(WhatsAppBroadcastRecipient).where(
            WhatsAppBroadcastRecipient.broadcast_id == broadcast_id,
        )
        recipient_result = await session.execute(recipient_stmt)
        recipients = recipient_result.scalars().all()
        phones = [r.phone_number for r in recipients if r.phone_number]
        if not phones:
            raise HTTPException(400, "Broadcast has no recipients")

        template = {
            "name": broadcast.template_name,
            "language": os.getenv("ZERNIO_WHATSAPP_TEMPLATE_LANG", "en_US"),
        }

        broadcast.status = "SENDING"
        broadcast.sent_at = datetime.utcnow()
        await session.flush()

        try:
            zbroadcast = await client.create_broadcast(
                profile_id=profile_id,
                account_id=account_id,
                platform="whatsapp",
                name=broadcast.name or f"Broadcast {broadcast.id}",
                description=None,
                template=template,
            )
            zbid = (zbroadcast or {}).get("id") or (zbroadcast or {}).get("_id")
            if not zbid:
                raise RuntimeError(f"Zernio did not return a broadcast id: {zbroadcast}")
            add_resp = await client.add_broadcast_recipients(zbid, phones=phones)
            send_resp = await client.send_broadcast(zbid)
        except HTTPException:
            raise
        except Exception as e:  # noqa: BLE001
            broadcast.status = "FAILED"
            for r in recipients:
                r.status = "FAILED"
                r.error_message = str(e)[:1000]
            broadcast.failed_count = len(recipients)
            await session.flush()
            raise _upstream_error("zernio whatsapp broadcast", e)

        added = int((add_resp or {}).get("added") or 0)
        skipped = int((add_resp or {}).get("skipped") or 0)
        sent = int((send_resp or {}).get("sent") or 0) or added or len(phones)
        failed = int((send_resp or {}).get("failed") or 0) or skipped
        zstatus = str((send_resp or {}).get("status") or "sending").lower()

        # Recipients were submitted to Zernio; final delivery/read arrive via webhook.
        for r in recipients:
            r.status = "SENT"
            r.sent_at = datetime.utcnow()
            r.error_message = None

        broadcast.sent_count = sent
        broadcast.failed_count = failed
        if zstatus in ("sending", "queued", "scheduled"):
            broadcast.status = "SENDING"
        else:
            broadcast.status = "SENT" if failed == 0 else ("FAILED" if sent == 0 else "PARTIAL")
        await session.flush()
        return BroadcastSendResponse(
            broadcast_id=broadcast.id,
            status=broadcast.status,
            recipient_count=broadcast.recipient_count,
        )


@app.get("/whatsapp/broadcasts/{broadcast_id}/stats", response_model=BroadcastStatsOut)
async def get_broadcast_stats(
    broadcast_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Get statistics for a WhatsApp broadcast."""
    async with get_session() as session:
        stmt = select(WhatsAppBroadcast).where(
            WhatsAppBroadcast.id == broadcast_id,
            WhatsAppBroadcast.tenant_id == tenant_id,
        )
        result = await session.execute(stmt)
        broadcast = result.scalar_one_or_none()
    if not broadcast:
        raise HTTPException(status_code=404, detail="Broadcast not found")

    total = broadcast.recipient_count
    delivery_rate = (broadcast.delivered_count / total * 100) if total > 0 else 0
    read_rate = (broadcast.read_count / total * 100) if total > 0 else 0

    return BroadcastStatsOut(
        broadcast_id=broadcast.id,
        name=broadcast.name,
        recipient_count=total,
        sent_count=broadcast.sent_count,
        delivered_count=broadcast.delivered_count,
        read_count=broadcast.read_count,
        failed_count=broadcast.failed_count,
        delivery_rate=round(delivery_rate, 2),
        read_rate=round(read_rate, 2),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# AD CAMPAIGNS ROUTES
# ═══════════════════════════════════════════════════════════════════════════════


@app.get("/ads/campaigns", response_model=List[Dict[str, Any]])
async def list_ad_campaigns(
    ad_status: Optional[str] = Query(None, alias="status"),
    platform: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """List ad campaigns with optional filters."""
    async with get_session() as session:
        stmt = select(AdCampaign).where(AdCampaign.tenant_id == tenant_id)
        if ad_status:
            stmt = stmt.where(AdCampaign.status == ad_status)
        if platform:
            stmt = stmt.where(AdCampaign.platform == platform)
        stmt = stmt.order_by(AdCampaign.created_at.desc()).limit(limit).offset(offset)
        result = await session.execute(stmt)
        campaigns = result.scalars().all()
    return [
        {
            "id": c.id,
            "tenant_id": c.tenant_id,
            "name": c.name,
            "platform": c.platform,
            "objective": c.objective,
            "status": c.status,
            "budget_zar": float(c.budget_zar),
            "daily_budget_zar": float(c.daily_budget_zar) if c.daily_budget_zar else None,
            "start_date": c.start_date,
            "end_date": c.end_date,
            "targeting": c.targeting,
            "creative": c.creative,
            "impressions": c.impressions,
            "clicks": c.clicks,
            "conversions": c.conversions,
            "spend_zar": float(c.spend_zar),
            "roas": float(c.roas) if c.roas else None,
            "created_at": c.created_at,
            "updated_at": c.updated_at,
        }
        for c in campaigns
    ]


@app.post("/ads/campaigns", status_code=201, response_model=Dict[str, Any], dependencies=[Depends(require_marketing_write)])
async def create_ad_campaign(
    body: AdCampaignCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Create a new ad campaign."""
    async with get_session() as session:
        campaign = AdCampaign(
            tenant_id=tenant_id,
            name=body.name,
            platform=body.platform,
            objective=body.objective,
            status="DRAFT",
            budget_zar=body.budget_zar,
            daily_budget_zar=body.daily_budget_zar,
            start_date=body.start_date,
            end_date=body.end_date,
            targeting=body.targeting,
            creative=body.creative,
        )
        session.add(campaign)
        await session.flush()
        await session.refresh(campaign)
        return {
            "id": campaign.id,
            "tenant_id": campaign.tenant_id,
            "name": campaign.name,
            "platform": campaign.platform,
            "objective": campaign.objective,
            "status": campaign.status,
            "budget_zar": float(campaign.budget_zar),
            "daily_budget_zar": float(campaign.daily_budget_zar) if campaign.daily_budget_zar else None,
            "start_date": campaign.start_date,
            "end_date": campaign.end_date,
            "targeting": campaign.targeting,
            "creative": campaign.creative,
            "impressions": campaign.impressions,
            "clicks": campaign.clicks,
            "conversions": campaign.conversions,
            "spend_zar": float(campaign.spend_zar),
            "roas": float(campaign.roas) if campaign.roas else None,
            "created_at": campaign.created_at,
            "updated_at": campaign.updated_at,
        }


@app.get("/ads/campaigns/{campaign_id}", response_model=Dict[str, Any])
async def get_ad_campaign(
    campaign_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Get a specific ad campaign."""
    async with get_session() as session:
        stmt = select(AdCampaign).where(
            AdCampaign.id == campaign_id,
            AdCampaign.tenant_id == tenant_id,
        )
        result = await session.execute(stmt)
        campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Ad campaign not found")
    return {
        "id": campaign.id,
        "tenant_id": campaign.tenant_id,
        "name": campaign.name,
        "platform": campaign.platform,
        "objective": campaign.objective,
        "status": campaign.status,
        "budget_zar": float(campaign.budget_zar),
        "daily_budget_zar": float(campaign.daily_budget_zar) if campaign.daily_budget_zar else None,
        "start_date": campaign.start_date,
        "end_date": campaign.end_date,
        "targeting": campaign.targeting,
        "creative": campaign.creative,
        "impressions": campaign.impressions,
        "clicks": campaign.clicks,
        "conversions": campaign.conversions,
        "spend_zar": float(campaign.spend_zar),
        "roas": float(campaign.roas) if campaign.roas else None,
        "created_at": campaign.created_at,
        "updated_at": campaign.updated_at,
    }


@app.put("/ads/campaigns/{campaign_id}", response_model=Dict[str, Any], dependencies=[Depends(require_marketing_write)])
async def update_ad_campaign(
    campaign_id: uuid.UUID,
    body: AdCampaignUpdate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Update an ad campaign."""
    async with get_session() as session:
        stmt = select(AdCampaign).where(
            AdCampaign.id == campaign_id,
            AdCampaign.tenant_id == tenant_id,
        )
        result = await session.execute(stmt)
        campaign = result.scalar_one_or_none()
        if not campaign:
            raise HTTPException(status_code=404, detail="Ad campaign not found")

        update_data = body.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(campaign, field, value)
        await session.flush()
        await session.refresh(campaign)
        return {
            "id": campaign.id,
            "tenant_id": campaign.tenant_id,
            "name": campaign.name,
            "platform": campaign.platform,
            "objective": campaign.objective,
            "status": campaign.status,
            "budget_zar": float(campaign.budget_zar),
            "daily_budget_zar": float(campaign.daily_budget_zar) if campaign.daily_budget_zar else None,
            "start_date": campaign.start_date,
            "end_date": campaign.end_date,
            "targeting": campaign.targeting,
            "creative": campaign.creative,
            "impressions": campaign.impressions,
            "clicks": campaign.clicks,
            "conversions": campaign.conversions,
            "spend_zar": float(campaign.spend_zar),
            "roas": float(campaign.roas) if campaign.roas else None,
            "created_at": campaign.created_at,
            "updated_at": campaign.updated_at,
        }


@app.delete("/ads/campaigns/{campaign_id}", status_code=204, dependencies=[Depends(require_marketing_write)])
async def delete_ad_campaign(
    campaign_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Delete an ad campaign."""
    async with get_session() as session:
        stmt = select(AdCampaign).where(
            AdCampaign.id == campaign_id,
            AdCampaign.tenant_id == tenant_id,
        )
        result = await session.execute(stmt)
        campaign = result.scalar_one_or_none()
        if not campaign:
            raise HTTPException(status_code=404, detail="Ad campaign not found")
        await session.delete(campaign)
    return None


@app.get("/ads/campaigns/{campaign_id}/analytics", response_model=AdAnalyticsOut)
async def get_ad_campaign_analytics(
    campaign_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Get analytics for a specific ad campaign."""
    async with get_session() as session:
        stmt = select(AdCampaign).where(
            AdCampaign.id == campaign_id,
            AdCampaign.tenant_id == tenant_id,
        )
        result = await session.execute(stmt)
        campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Ad campaign not found")

    ctr = (campaign.clicks / campaign.impressions * 100) if campaign.impressions > 0 else 0
    cpc = (campaign.spend_zar / campaign.clicks) if campaign.clicks > 0 else None

    return AdAnalyticsOut(
        campaign_id=campaign.id,
        name=campaign.name,
        platform=campaign.platform,
        impressions=campaign.impressions,
        clicks=campaign.clicks,
        conversions=campaign.conversions,
        spend_zar=campaign.spend_zar,
        ctr=round(ctr, 2),
        cpc=cpc,
        roas=campaign.roas,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# COMMENT AUTOMATION ROUTES
# ═══════════════════════════════════════════════════════════════════════════════


@app.get("/social/automations", response_model=List[Dict[str, Any]])
async def list_comment_automations(
    account_id: Optional[uuid.UUID] = None,
    is_active: Optional[bool] = None,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """List comment automations."""
    async with get_session() as session:
        stmt = select(CommentAutomation).where(CommentAutomation.tenant_id == tenant_id)
        if account_id:
            stmt = stmt.where(CommentAutomation.account_id == account_id)
        if is_active is not None:
            stmt = stmt.where(CommentAutomation.is_active == is_active)
        stmt = stmt.order_by(CommentAutomation.created_at.desc())
        result = await session.execute(stmt)
        automations = result.scalars().all()
    return [
        {
            "id": a.id, "name": a.name, "account_id": a.account_id,
            "trigger_type": a.trigger_type, "trigger_keywords": a.trigger_keywords,
            "response_template": a.response_template, "is_active": a.is_active,
            "total_triggered": a.total_triggered, "total_replied": a.total_replied,
            "created_at": a.created_at,
        }
        for a in automations
    ]


@app.post("/social/automations", status_code=201, dependencies=[Depends(require_marketing_write)])
async def create_comment_automation(
    body: CommentAutomationCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Create a comment automation rule."""
    async with get_session() as session:
        automation = CommentAutomation(
            tenant_id=tenant_id,
            name=body.name,
            account_id=body.account_id,
            trigger_type=body.trigger_type,
            trigger_keywords=body.trigger_keywords,
            response_template=body.response_template,
            is_active=body.is_active,
        )
        session.add(automation)
        await session.flush()
        await session.refresh(automation)
    return {
        "id": automation.id, "name": automation.name,
        "trigger_type": automation.trigger_type, "is_active": automation.is_active,
    }


@app.put("/social/automations/{automation_id}", dependencies=[Depends(require_marketing_write)])
async def update_comment_automation(
    automation_id: uuid.UUID,
    body: CommentAutomationUpdate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Update a comment automation rule."""
    async with get_session() as session:
        stmt = select(CommentAutomation).where(
            CommentAutomation.id == automation_id,
            CommentAutomation.tenant_id == tenant_id,
        )
        result = await session.execute(stmt)
        automation = result.scalar_one_or_none()
        if not automation:
            raise HTTPException(status_code=404, detail="Automation not found")
        for field, value in body.dict(exclude_unset=True).items():
            setattr(automation, field, value)
        await session.flush()
        await session.refresh(automation)
    return {"id": automation.id, "name": automation.name, "is_active": automation.is_active}


@app.delete("/social/automations/{automation_id}", status_code=204, dependencies=[Depends(require_marketing_write)])
async def delete_comment_automation(
    automation_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Delete a comment automation rule."""
    async with get_session() as session:
        stmt = select(CommentAutomation).where(
            CommentAutomation.id == automation_id,
            CommentAutomation.tenant_id == tenant_id,
        )
        result = await session.execute(stmt)
        automation = result.scalar_one_or_none()
        if not automation:
            raise HTTPException(status_code=404, detail="Automation not found")
        await session.delete(automation)
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# SOCIAL WEBHOOKS
# ═══════════════════════════════════════════════════════════════════════════════

# Lazy Zernio client — only constructed when ZERNIO_API_KEY is set, so local
# dev and Railway (pre-key) boot and serve everything else untouched.
_zernio_client = None


def _upstream_error(context: str, exc: BaseException, status_code: int = 502) -> HTTPException:
    """Log the upstream failure server-side; clients only get a generic message + a reference id."""
    ref = uuid.uuid4().hex[:12]
    logger.error("upstream error [%s] %s: %s", ref, context, exc)
    return HTTPException(status_code=status_code, detail=f"Upstream service error (ref {ref})")


def get_zernio_client():
    """Return a ZernioClient, or None when no API key is configured."""
    global _zernio_client
    if _zernio_client is not None:
        return _zernio_client
    if not os.getenv("ZERNIO_API_KEY"):
        return None
    from services.marketing.zernio_client import ZernioClient
    _zernio_client = ZernioClient()
    return _zernio_client


@app.get("/social/zernio/status", response_model=Dict[str, Any])
async def zernio_status():
    """Zernio integration status — configured flag only, never the key."""
    return {
        "configured": bool(os.getenv("ZERNIO_API_KEY")),
        "webhook_secret_set": bool(os.getenv("ZERNIO_WEBHOOK_SECRET")),
        "profile_ready": bool(os.getenv("ZERNIO_PROFILE_ID")),
        "webhook_unsigned_allowed": sec._truthy("ZERNIO_WEBHOOK_ALLOW_UNSIGNED"),
        "base_url": os.getenv("ZERNIO_BASE_URL", "https://zernio.com/api/v1"),
    }


# Catalog of Zernio-supported platforms — drives the Connections UI. Zernio
# owns each platform's OAuth app; connecting one goes through its hosted flow.
ZERNIO_CONNECTORS: List[Dict[str, Any]] = [
    {"id": "tiktok", "label": "TikTok", "category": "Social"},
    {"id": "instagram", "label": "Instagram", "category": "Social"},
    {"id": "facebook", "label": "Facebook", "category": "Social"},
    {"id": "youtube", "label": "YouTube", "category": "Social"},
    {"id": "linkedin", "label": "LinkedIn", "category": "Social"},
    {"id": "twitter", "label": "Twitter/X", "category": "Social"},
    {"id": "threads", "label": "Threads", "category": "Social"},
    {"id": "bluesky", "label": "Bluesky", "category": "Social"},
    {"id": "pinterest", "label": "Pinterest", "category": "Social"},
    {"id": "reddit", "label": "Reddit", "category": "Social"},
    {"id": "googlebusiness", "label": "Google Business", "category": "Social"},
    {"id": "snapchat", "label": "Snapchat", "category": "Social"},
    {"id": "telegram", "label": "Telegram", "category": "Messaging"},
    {"id": "whatsapp", "label": "WhatsApp", "category": "Messaging"},
    {"id": "shopify", "label": "Shopify", "category": "Commerce", "coming_soon": True},  # needs the merchant's shop domain: not in the in-app flow yet
    # Ads connections are separate provider accounts (platform metaads / googleads / ...). The `id`s are the
    # ids accepted by POST /social/connect/start with category="ads".
    {"id": "meta_ads", "label": "Meta Ads", "category": "Ads", "kind": "ads"},
    {"id": "google_ads", "label": "Google Ads", "category": "Ads", "kind": "ads"},
    {"id": "tiktok_ads", "label": "TikTok Ads", "category": "Ads", "kind": "ads"},
    {"id": "linkedin_ads", "label": "LinkedIn Ads", "category": "Ads", "kind": "ads"},
    {"id": "pinterest_ads", "label": "Pinterest Ads", "category": "Ads", "kind": "ads"},
    {"id": "x_ads", "label": "X Ads", "category": "Ads", "kind": "ads"},
]
# provider account platform -> connector id (ads accounts are reported as e.g. "metaads")
_ADS_PLATFORM_TO_CONNECTOR = {"metaads": "meta_ads", "googleads": "google_ads", "tiktokads": "tiktok_ads",
                              "linkedinads": "linkedin_ads", "pinterestads": "pinterest_ads", "xads": "x_ads"}


@app.get("/social/zernio/connectors", response_model=Dict[str, Any])
async def zernio_connectors(tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    """Platform catalog + this tenant's connected state, for the Connections UI.

    Connected state comes from THIS tenant's account map (per-customer), not the
    team-wide account list — each customer sees only their own connections.
    """
    engine = get_engine()
    _ensure_marketing_tables(engine)
    connected_by_platform: Dict[str, List[Dict[str, Any]]] = {}
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT account_id, platform, username, status FROM marketing_connected_accounts
                WHERE tenant_id = :tid AND status <> 'disconnected'
            """),
            {"tid": str(tenant_id)},
        ).mappings().all()
    for acct in rows:
        p = _ADS_PLATFORM_TO_CONNECTOR.get(str(acct["platform"] or "").lower(), str(acct["platform"] or "").lower())
        connected_by_platform.setdefault(p, []).append({
            "id": acct["account_id"], "name": acct["username"], "username": acct["username"],
            "status": acct["status"],
        })

    client = get_zernio_client()
    configured = client is not None
    # A tenant is connectable once Zernio is configured — its profile is created
    # on demand at connect time, so we no longer require a preset profile env.
    profile_ready = bool(_get_tenant_profile(tenant_id)) or configured
    connectors = [
        {
            **c,
            "connected": bool(connected_by_platform.get(c["id"])),
            "accounts": connected_by_platform.get(c["id"], []),
        }
        for c in ZERNIO_CONNECTORS
    ]
    return {
        "configured": configured,
        "profile_ready": profile_ready,
        "connectable": configured and profile_ready,
        "connectors": connectors,
    }


# ═══════════════════════════════════════════════════════════════════════════
# DB-BACKED ANALYTICS  — dashboards read here; the sync worker fills the tables.
# These endpoints NEVER call Zernio (per the profile-per-customer model).
#
# The sync worker is a SIBLING service, not part of this package: it lives at
# services/analytics_worker/ (image `omnidome-analytics_worker`, docker-compose
# service `analytics_worker`). It runs APScheduler and periodically calls Zernio's
# analytics endpoints to populate marketing_post_analytics / marketing_daily_metrics
# / marketing_follower_stats / marketing_analytics_sync_state. It is intentionally
# out-of-process so a slow analytics pull can't block the request path here.
# ═══════════════════════════════════════════════════════════════════════════

_METRIC_COLS = ["impressions", "reach", "likes", "comments", "shares", "saves", "clicks", "views"]


class TenantProfileIn(BaseModel):
    zernio_profile_id: str


@app.put("/social/analytics/profile", response_model=Dict[str, Any], dependencies=[Depends(require_marketing_admin)])
async def set_tenant_profile(
    body: TenantProfileIn,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Admin only. Re-map this tenant to a Zernio profile the platform key can PROVE is its own
    (auto-provisioned profiles are named after the tenant id). Anything else is rejected, so a
    tenant can never adopt another customer's profile."""
    pid = (body.zernio_profile_id or "").strip()
    if not pid or len(pid) > 64:
        raise HTTPException(status_code=422, detail="Invalid zernio_profile_id")
    client = get_zernio_client()
    if client is None:
        raise HTTPException(status_code=503, detail="Zernio not configured (ZERNIO_API_KEY missing)")
    try:
        profiles = await client.list_profiles()
    except Exception as e:  # noqa: BLE001
        raise _upstream_error("zernio list_profiles", e)
    match = next((p for p in profiles or [] if isinstance(p, dict) and str(p.get("_id") or p.get("id")) == pid), None)
    if not match or str(match.get("name") or "") != str(tenant_id):
        raise HTTPException(status_code=403, detail="Profile does not belong to this tenant")
    owner = _tenant_for_profile(pid)
    if owner and owner != str(tenant_id):
        raise HTTPException(status_code=409, detail="Profile is already mapped to another tenant")
    engine = get_engine()
    _ensure_marketing_tables(engine)
    try:
        with engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO marketing_tenant_profiles (tenant_id, zernio_profile_id)
                    VALUES (:tid, :pid)
                    ON CONFLICT (tenant_id)
                    DO UPDATE SET zernio_profile_id = EXCLUDED.zernio_profile_id, updated_at = now()
                """),
                {"tid": str(tenant_id), "pid": pid},
            )
    except Exception as e:  # noqa: BLE001 - unique index on zernio_profile_id
        if "uq_mkt_tenant_profiles_profile" in str(e) or "unique" in str(e).lower():
            raise HTTPException(status_code=409, detail="Profile is already mapped to another tenant")
        raise
    return {"tenant_id": str(tenant_id), "zernio_profile_id": pid}


@app.get("/social/analytics/overview", response_model=Dict[str, Any])
async def analytics_overview(tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    engine = get_engine()
    _ensure_marketing_tables(engine)
    with engine.connect() as conn:
        t = conn.execute(
            text("""
                SELECT COUNT(*) AS total_posts,
                       COALESCE(SUM(likes),0) AS likes, COALESCE(SUM(comments),0) AS comments,
                       COALESCE(SUM(impressions),0) AS impressions, COALESCE(SUM(reach),0) AS reach,
                       COALESCE(SUM(shares),0) AS shares, COALESCE(SUM(clicks),0) AS clicks,
                       COUNT(*) FILTER (WHERE sync_status = 'pending') AS pending_count
                FROM marketing_post_analytics WHERE tenant_id = :tid
            """),
            {"tid": str(tenant_id)},
        ).mappings().first() or {}
        state = conn.execute(
            text("SELECT * FROM marketing_analytics_sync_state WHERE tenant_id = :tid"),
            {"tid": str(tenant_id)},
        ).mappings().first()
    last_sync = state.get("last_hot_sync") if state else None
    return {
        "overview": {
            "totalPosts": int(t.get("total_posts", 0)),
            "likes": int(t.get("likes", 0)),
            "comments": int(t.get("comments", 0)),
            "impressions": int(t.get("impressions", 0)),
            "reach": int(t.get("reach", 0)),
            "shares": int(t.get("shares", 0)),
            "clicks": int(t.get("clicks", 0)),
            "lastSync": last_sync.isoformat() if last_sync else None,
            "dataStaleness": {"pendingCount": int(t.get("pending_count", 0))},
            "lastError": state.get("last_error") if state else None,
        }
    }


@app.get("/social/analytics/daily", response_model=Dict[str, Any])
async def analytics_daily(
    attribution: str = Query("publish"),
    days: int = Query(30, ge=1, le=366),
    platform: Optional[str] = None,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    engine = get_engine()
    _ensure_marketing_tables(engine)
    plat = platform or "all"
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT metric_date, post_count, impressions, reach, likes, comments, shares, saves, clicks, views
                FROM marketing_daily_metrics
                WHERE tenant_id = :tid AND attribution = :attr AND platform = :plat
                  AND metric_date >= (CURRENT_DATE - make_interval(days => :days))
                ORDER BY metric_date
            """),
            {"tid": str(tenant_id), "attr": attribution, "plat": plat, "days": days},
        ).mappings().all()
    return {
        "attribution": attribution,
        "platform": plat,
        "dailyData": [
            {
                "date": r["metric_date"].isoformat(),
                "postCount": r["post_count"],
                "metrics": {k: r[k] for k in _METRIC_COLS},
            }
            for r in rows
        ],
    }


@app.get("/social/analytics/posts", response_model=Dict[str, Any])
async def analytics_posts(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    platform: Optional[str] = None,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    engine = get_engine()
    _ensure_marketing_tables(engine)
    where = "tenant_id = :tid"
    params: Dict[str, Any] = {"tid": str(tenant_id), "limit": limit, "offset": (page - 1) * limit}
    if platform:
        where += " AND platform = :plat"
        params["plat"] = platform
    with engine.connect() as conn:
        total = conn.execute(text(f"SELECT COUNT(*) FROM marketing_post_analytics WHERE {where}"), params).scalar() or 0
        rows = conn.execute(
            text(f"""
                SELECT post_id, platform, published_at, platform_post_url, sync_status, last_updated,
                       likes, comments, impressions, reach, shares, saves, clicks, views
                FROM marketing_post_analytics WHERE {where}
                ORDER BY published_at DESC NULLS LAST
                LIMIT :limit OFFSET :offset
            """),
            params,
        ).mappings().all()
    return {
        "posts": [
            {
                "postId": r["post_id"],
                "platform": r["platform"],
                "publishedAt": r["published_at"].isoformat() if r["published_at"] else None,
                "url": r["platform_post_url"],
                "syncStatus": r["sync_status"],
                "lastUpdated": r["last_updated"].isoformat() if r["last_updated"] else None,
                "analytics": {k: r[k] for k in ["likes", "comments", "impressions", "reach", "shares", "saves", "clicks", "views"]},
            }
            for r in rows
        ],
        "pagination": {
            "page": page,
            "limit": limit,
            "total": int(total),
            "pages": max(1, (int(total) + limit - 1) // limit),
        },
    }


@app.get("/social/analytics/followers", response_model=Dict[str, Any])
async def analytics_followers(
    granularity: str = Query("daily"),
    days: int = Query(90, ge=1, le=366),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    engine = get_engine()
    _ensure_marketing_tables(engine)
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT stat_date, platform, followers, growth
                FROM marketing_follower_stats
                WHERE tenant_id = :tid AND granularity = :g
                  AND stat_date >= (CURRENT_DATE - make_interval(days => :days))
                ORDER BY stat_date
            """),
            {"tid": str(tenant_id), "g": granularity, "days": days},
        ).mappings().all()
    return {
        "granularity": granularity,
        "series": [
            {"date": r["stat_date"].isoformat(), "platform": r["platform"], "followers": r["followers"], "growth": r["growth"]}
            for r in rows
        ],
    }


# ═══════════════════════════════════════════════════════════════════════════
# PLATFORM  — one Zernio profile per tenant, account→tenant map, health,
# usage/cost per customer, scoped keys, offboarding. (Zernio "Build a Platform")
# ═══════════════════════════════════════════════════════════════════════════


def _get_tenant_profile(tenant_id: uuid.UUID) -> Optional[str]:
    """Read the tenant's OWN Zernio profile id (no creation). Never falls back to the shared
    platform profile (ZERNIO_PROFILE_ID): a tenant without a profile sees/changes nothing."""
    engine = get_engine()
    _ensure_marketing_tables(engine)
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT zernio_profile_id FROM marketing_tenant_profiles WHERE tenant_id = :tid"),
            {"tid": str(tenant_id)},
        ).first()
    return row[0] if row else None


def _require_tenant_profile(tenant_id: uuid.UUID) -> str:
    """Write/destructive paths: the tenant must already have its own provisioned profile."""
    pid = _get_tenant_profile(tenant_id)
    if not pid:
        raise HTTPException(status_code=409, detail="tenant profile not provisioned")
    return pid


async def _ensure_tenant_profile(tenant_id: uuid.UUID) -> Optional[str]:
    """Get-or-create the tenant's Zernio profile. On a 409 name conflict, reuse
    details.existingProfileId. Returns None when Zernio isn't configured."""
    import json as _json
    engine = get_engine()
    _ensure_marketing_tables(engine)
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT zernio_profile_id FROM marketing_tenant_profiles WHERE tenant_id = :tid"),
            {"tid": str(tenant_id)},
        ).first()
    if row:
        return row[0]

    client = get_zernio_client()
    if client is None:
        return None
    from services.marketing.zernio_client import ZernioError

    profile_id: Optional[str] = None
    try:
        created = await client.create_profile(name=str(tenant_id), description=f"OmniDome tenant {tenant_id}")
        profile_id = ((created or {}).get("profile") or {}).get("_id") or (created or {}).get("_id")
    except ZernioError as e:
        if e.status == 409:
            try:
                profile_id = (_json.loads(e.message).get("details") or {}).get("existingProfileId")
            except Exception:  # noqa: BLE001
                profile_id = None
        if not profile_id:
            raise
    if not profile_id:
        return None
    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO marketing_tenant_profiles (tenant_id, zernio_profile_id)
                VALUES (:tid, :pid)
                ON CONFLICT (tenant_id) DO UPDATE SET zernio_profile_id = EXCLUDED.zernio_profile_id, updated_at = now()
            """),
            {"tid": str(tenant_id), "pid": profile_id},
        )
    return profile_id


def _upsert_connected_account(tenant_id: str, profile_id: str, acct: Dict[str, Any], status: str = "connected") -> None:
    """Write/refresh the account→tenant map row (from connect, webhook or health)."""
    import json as _json
    account_id = str(acct.get("accountId") or acct.get("_id") or acct.get("id") or "")
    if not account_id:
        return
    engine = get_engine()
    disconnected = status == "disconnected"
    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO marketing_connected_accounts
                    (account_id, tenant_id, profile_id, platform, username, status, issues, disconnected_at, updated_at)
                VALUES (:aid, :tid, :pid, :platform, :username, :status, :issues,
                        CASE WHEN :disc THEN now() ELSE NULL END, now())
                ON CONFLICT (account_id) DO UPDATE SET
                    tenant_id = EXCLUDED.tenant_id, profile_id = EXCLUDED.profile_id,
                    platform = COALESCE(EXCLUDED.platform, marketing_connected_accounts.platform),
                    username = COALESCE(EXCLUDED.username, marketing_connected_accounts.username),
                    status = EXCLUDED.status, issues = EXCLUDED.issues,
                    disconnected_at = CASE WHEN :disc THEN now() ELSE NULL END, updated_at = now()
            """),
            {
                "aid": account_id, "tid": tenant_id, "pid": profile_id,
                "platform": acct.get("platform"), "username": acct.get("username"),
                "status": status, "issues": _json.dumps(acct.get("issues") or []), "disc": disconnected,
            },
        )


def _tenant_for_account(account_id: str) -> Optional[str]:
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT tenant_id FROM marketing_connected_accounts WHERE account_id = :aid"),
            {"aid": account_id},
        ).first()
    return str(row[0]) if row else None


def _tenant_for_profile(profile_id: str) -> Optional[str]:
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT tenant_id FROM marketing_tenant_profiles WHERE zernio_profile_id = :pid"),
            {"pid": profile_id},
        ).first()
    return str(row[0]) if row else None


@app.post("/social/profile/ensure", response_model=Dict[str, Any], dependencies=[Depends(require_marketing_write)])
async def ensure_profile(tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    """Create this tenant's Zernio profile if it doesn't have one yet, and
    return the id. Idempotent; safe to call on every login/onboarding."""
    pid = await _ensure_tenant_profile(tenant_id)
    if not pid:
        raise HTTPException(status_code=503, detail="Zernio not configured (ZERNIO_API_KEY missing)")
    return {"tenant_id": str(tenant_id), "zernio_profile_id": pid}


@app.get("/social/connected-accounts", response_model=Dict[str, Any])
async def list_connected_accounts(tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    """Accounts connected into this tenant's profile (from the map)."""
    engine = get_engine()
    _ensure_marketing_tables(engine)
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT account_id, profile_id, platform, username, status, issues, connected_at
                FROM marketing_connected_accounts WHERE tenant_id = :tid
                ORDER BY connected_at DESC
            """),
            {"tid": str(tenant_id)},
        ).mappings().all()
    return {"accounts": [dict(r) for r in rows]}


@app.get("/social/accounts-health", response_model=Dict[str, Any])
async def accounts_health(
    status_filter: Optional[str] = Query(None, alias="status"),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Live token health for the tenant's accounts. Refreshes the map's status
    so the dashboard can prompt reconnection."""
    client = get_zernio_client()
    if client is None:
        raise HTTPException(status_code=503, detail="Zernio not configured (ZERNIO_API_KEY missing)")
    profile_id = _get_tenant_profile(tenant_id)
    if not profile_id:
        return {"summary": {"total": 0, "needsReconnect": 0}, "accounts": []}
    try:
        health = await client.get_accounts_health(profile_id, status=status_filter)
    except Exception as e:  # noqa: BLE001
        logger.error(f"Zernio accounts health failed: {e}")
        raise _upstream_error("zernio", e)
    for acct in (health or {}).get("accounts", []):
        st = "error" if acct.get("needsReconnect") else acct.get("status", "connected")
        _upsert_connected_account(str(tenant_id), profile_id, acct, status=st)
    return health


@app.get("/social/usage", response_model=Dict[str, Any])
async def social_usage(tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    """This tenant's slice of the Zernio bill for the current cycle — the
    attribution group for its profile."""
    client = get_zernio_client()
    if client is None:
        raise HTTPException(status_code=503, detail="Zernio not configured (ZERNIO_API_KEY missing)")
    profile_id = _get_tenant_profile(tenant_id)
    if not profile_id:
        return {"profile_id": None, "usage": None, "restricted": False}
    try:
        usage = await client.get_usage(range_="cycle", group_by="profile")
    except Exception as e:  # noqa: BLE001
        raise _upstream_error("zernio", e)
    groups = ((usage or {}).get("attribution") or {}).get("groups") or []
    mine = next((g for g in groups if g.get("profileId") == profile_id or g.get("id") == profile_id), None)
    return {"profile_id": profile_id, "usage": mine, "restricted": ((usage or {}).get("attribution") or {}).get("restricted", False)}


class ScopedKeyIn(BaseModel):
    name: str
    permission: Optional[str] = None  # "read" for read-only
    disabled_resource_groups: Optional[List[str]] = None
    expires_in: Optional[int] = None  # days


@app.post("/social/api-keys", response_model=Dict[str, Any], dependencies=[Depends(require_marketing_admin)])
async def create_scoped_key(
    body: ScopedKeyIn,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Mint a Zernio API key scoped to this tenant's profile (access control;
    the rate limit still belongs to the team)."""
    client = get_zernio_client()
    if client is None:
        raise HTTPException(status_code=503, detail="Zernio not configured (ZERNIO_API_KEY missing)")
    profile_id = await _ensure_tenant_profile(tenant_id)
    if not profile_id:
        raise HTTPException(status_code=503, detail="Could not resolve a Zernio profile for this tenant")
    try:
        result = await client.create_api_key(
            name=body.name, scope="profiles", profile_ids=[profile_id],
            permission=body.permission, disabled_resource_groups=body.disabled_resource_groups,
            expires_in=body.expires_in,
        )
    except Exception as e:  # noqa: BLE001
        raise _upstream_error("zernio", e)
    return result


@app.post("/social/profile/offboard", response_model=Dict[str, Any], dependencies=[Depends(require_marketing_admin)])
async def offboard_profile(tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    """Disconnect the tenant's accounts, then delete its Zernio profile, then
    clear local rows. Active accounts block profile deletion, so they go first."""
    client = get_zernio_client()
    if client is None:
        raise HTTPException(status_code=503, detail="Zernio not configured (ZERNIO_API_KEY missing)")
    profile_id = _require_tenant_profile(tenant_id)
    engine = get_engine()
    with engine.connect() as conn:
        account_ids = [
            r[0] for r in conn.execute(
                text("SELECT account_id FROM marketing_connected_accounts WHERE tenant_id = :tid AND status <> 'disconnected'"),
                {"tid": str(tenant_id)},
            ).all()
        ]
    disconnected = 0
    for aid in account_ids:
        try:
            await client.disconnect_account(aid)
            disconnected += 1
        except Exception as e:  # noqa: BLE001
            logger.warning(f"offboard: disconnect {aid} failed: {e}")
    try:
        await client.delete_profile(profile_id)
    except Exception as e:  # noqa: BLE001
        raise _upstream_error("zernio profile delete", e)
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM marketing_connected_accounts WHERE tenant_id = :tid"), {"tid": str(tenant_id)})
        conn.execute(text("DELETE FROM marketing_tenant_profiles WHERE tenant_id = :tid"), {"tid": str(tenant_id)})
    return {"status": "offboarded", "disconnected_accounts": disconnected, "profile_id": profile_id}


# ═══════════════════════════════════════════════════════════════════════════
# POSTING QUEUES — recurring weekly slots; a post drops into the next open slot
# ═══════════════════════════════════════════════════════════════════════════


def _queue_next_slot(slots: List[Dict[str, Any]], tz_name: str, taken_iso: set) -> Optional[str]:
    """Soonest future slot (in the queue's timezone) not already occupied by a
    scheduled post. Slots: [{day:0-6 (0=Sun), time:'HH:MM'}]. Returns ISO UTC."""
    if not slots:
        return None
    from datetime import datetime as _dt, timedelta as _td
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(tz_name or "UTC")
    except Exception:  # noqa: BLE001
        from datetime import timezone as _tzmod
        tz = _tzmod.utc
    now = _dt.now(tz)
    candidates: List[_dt] = []
    for offset in range(0, 15):  # look ~2 weeks ahead
        day = now + _td(days=offset)
        # Python weekday(): Mon=0..Sun=6 → convert to Sun=0..Sat=6
        dow = (day.weekday() + 1) % 7
        for slot in slots:
            if int(slot.get("day", -1)) != dow:
                continue
            try:
                hh, mm = str(slot.get("time", "09:00")).split(":")[:2]
                cand = day.replace(hour=int(hh), minute=int(mm), second=0, microsecond=0)
            except Exception:  # noqa: BLE001
                continue
            if cand <= now:
                continue
            iso = cand.astimezone(__import__("datetime").timezone.utc).isoformat()
            if iso in taken_iso:
                continue
            candidates.append(cand)
    if not candidates:
        return None
    return min(candidates).astimezone(__import__("datetime").timezone.utc).isoformat()


def _taken_slot_isos(engine, tenant_id: uuid.UUID) -> set:
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT scheduled_for FROM social_posts WHERE tenant_id = :tid AND lower(status) = 'scheduled' AND scheduled_for IS NOT NULL"),
            {"tid": str(tenant_id)},
        ).all()
    out = set()
    for r in rows:
        v = r[0]
        if v is not None:
            if hasattr(v, "astimezone"):
                v = _zp.to_utc(v)
            out.add(v.isoformat() if hasattr(v, "isoformat") else str(v))
    return out


class QueueSlot(BaseModel):
    day: int   # 0=Sun .. 6=Sat
    time: str  # "HH:MM"


class QueueCreate(BaseModel):
    name: str
    description: Optional[str] = None
    timezone: str = "UTC"
    status: str = "active"
    slots: List[QueueSlot] = []


class QueueUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    timezone: Optional[str] = None
    status: Optional[str] = None
    slots: Optional[List[QueueSlot]] = None


def _serialize_queue(row, next_slot: Optional[str]) -> Dict[str, Any]:
    return {
        "id": str(row["id"]),
        "name": row["name"],
        "description": row["description"],
        "status": row["status"],
        "timezone": row["timezone"],
        "slots": row["slots"] or [],
        "next_slot": next_slot,
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
    }


@app.get("/social/queues", response_model=Dict[str, Any])
async def list_queues(tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    engine = get_engine()
    _ensure_marketing_tables(engine)
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT * FROM marketing_post_queues WHERE tenant_id = :tid ORDER BY created_at DESC"),
            {"tid": str(tenant_id)},
        ).mappings().all()
    taken = _taken_slot_isos(engine, tenant_id)
    return {"queues": [
        _serialize_queue(r, _queue_next_slot(r["slots"] or [], r["timezone"], taken) if r["status"] == "active" else None)
        for r in rows
    ]}


@app.post("/social/queues", status_code=201, response_model=Dict[str, Any], dependencies=[Depends(require_marketing_write)])
async def create_queue(body: QueueCreate, tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    import json as _json
    engine = get_engine()
    _ensure_marketing_tables(engine)
    qid = uuid.uuid4()
    slots = [s.dict() for s in body.slots]
    profile_id = _get_tenant_profile(tenant_id)
    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO marketing_post_queues (id, tenant_id, profile_id, name, description, status, timezone, slots)
                VALUES (:id, :tid, :pid, :name, :desc, :status, :tz, CAST(:slots AS jsonb))
            """),
            {"id": str(qid), "tid": str(tenant_id), "pid": profile_id, "name": body.name,
             "desc": body.description, "status": body.status, "tz": body.timezone, "slots": _json.dumps(slots)},
        )
    return {"id": str(qid), "name": body.name, "status": body.status, "timezone": body.timezone, "slots": slots}


@app.patch("/social/queues/{queue_id}", response_model=Dict[str, Any], dependencies=[Depends(require_marketing_write)])
async def update_queue(queue_id: uuid.UUID, body: QueueUpdate, tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    import json as _json
    engine = get_engine()
    _ensure_marketing_tables(engine)
    sets, params = [], {"id": str(queue_id), "tid": str(tenant_id)}
    if body.name is not None:
        sets.append("name = :name"); params["name"] = body.name
    if body.description is not None:
        sets.append("description = :desc"); params["desc"] = body.description
    if body.timezone is not None:
        sets.append("timezone = :tz"); params["tz"] = body.timezone
    if body.status is not None:
        sets.append("status = :status"); params["status"] = body.status
    if body.slots is not None:
        sets.append("slots = CAST(:slots AS jsonb)"); params["slots"] = _json.dumps([s.dict() for s in body.slots])
    if not sets:
        raise HTTPException(status_code=400, detail="No fields to update")
    sets.append("updated_at = now()")
    with engine.begin() as conn:
        res = conn.execute(
            text(f"UPDATE marketing_post_queues SET {', '.join(sets)} WHERE id = :id AND tenant_id = :tid"),
            params,
        )
        if res.rowcount == 0:
            raise HTTPException(status_code=404, detail="Queue not found")
    return {"id": str(queue_id), "updated": True}


@app.delete("/social/queues/{queue_id}", status_code=204, dependencies=[Depends(require_marketing_write)])
async def delete_queue(queue_id: uuid.UUID, tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    engine = get_engine()
    _ensure_marketing_tables(engine)
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM marketing_post_queues WHERE id = :id AND tenant_id = :tid"),
            {"id": str(queue_id), "tid": str(tenant_id)},
        )
    return None


@app.post("/social/queues/{queue_id}/enqueue", status_code=201, response_model=Dict[str, Any], dependencies=[Depends(require_marketing_write)])
async def enqueue_post(
    queue_id: uuid.UUID,
    body: SocialPostCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Drop a post into the queue's next open slot (creates a scheduled post)."""
    engine = get_engine()
    _ensure_marketing_tables(engine)
    with engine.connect() as conn:
        q = conn.execute(
            text("SELECT * FROM marketing_post_queues WHERE id = :id AND tenant_id = :tid"),
            {"id": str(queue_id), "tid": str(tenant_id)},
        ).mappings().first()
    if not q:
        raise HTTPException(status_code=404, detail="Queue not found")
    if q["status"] != "active":
        raise HTTPException(status_code=400, detail="Queue is paused")
    slot = _queue_next_slot(q["slots"] or [], q["timezone"], _taken_slot_isos(engine, tenant_id))
    if not slot:
        raise HTTPException(status_code=400, detail="Queue has no available slots — add slots first")
    slot_dt = datetime.fromisoformat(slot)
    # The slot is computed from OmniDome's queue definition and the post is scheduled at the provider
    # for exactly that time (previously the row was saved locally and never sent anywhere).
    core = body.model_copy(update={"status": "scheduled", "scheduled_for": slot_dt, "queue_id": queue_id})
    created = await _create_post_core(core, tenant_id)
    return {
        "id": str(created["id"]),
        "status": created["status"],
        "scheduled_for": created["scheduled_for"].isoformat() if created.get("scheduled_for") else slot,
        "queue_id": str(queue_id),
        "publish_error": created.get("publish_error"),
        "zernio_post_id": created.get("zernio_post_id"),
    }


def _tenant_account_ids(tenant_id: uuid.UUID) -> set:
    engine = get_engine()
    _ensure_marketing_tables(engine)
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT account_id FROM marketing_connected_accounts WHERE tenant_id = :tid AND status <> 'disconnected'"),
            {"tid": str(tenant_id)},
        ).all()
    return {str(r[0]) for r in rows}


def _filter_conversations(data: Any, mine: set) -> Any:
    """Keep only conversations whose account belongs to the tenant; items with no identifiable
    account are dropped (fail closed)."""
    def acct(item: Any) -> str:
        if not isinstance(item, dict):
            return ""
        a = item.get("account") if isinstance(item.get("account"), dict) else {}
        return str(item.get("accountId") or a.get("id") or a.get("_id") or item.get("account_id") or "")

    if isinstance(data, list):
        return [i for i in data if acct(i) in mine]
    if isinstance(data, dict):
        out = dict(data)
        for key in ("conversations", "data", "items"):
            if isinstance(out.get(key), list):
                out[key] = [i for i in out[key] if acct(i) in mine]
        return out
    return data


@app.get("/social/zernio/accounts", response_model=List[Dict[str, Any]])
async def zernio_accounts(
    platform: Optional[str] = None,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Live connected accounts from Zernio (proxied, not stored), restricted to THIS tenant's accounts."""
    client = get_zernio_client()
    if client is None:
        raise HTTPException(status_code=503, detail="Zernio not configured (ZERNIO_API_KEY missing)")
    mine = _tenant_account_ids(tenant_id)
    if not mine:
        return []
    try:
        accounts = await client.list_accounts(platform=platform)
        return [a for a in (accounts or []) if isinstance(a, dict)
                and str(a.get("_id") or a.get("id") or a.get("accountId") or "") in mine]
    except Exception as e:
        logger.error(f"Zernio list_accounts failed: {e}")
        raise _upstream_error("zernio", e)


@app.get("/social/zernio/conversations", response_model=Dict[str, Any])
async def zernio_conversations(
    platform: Optional[str] = None,
    status_filter: Optional[str] = Query(default=None, alias="status"),
    limit: int = Query(20, ge=1, le=100),
    account_id: Optional[str] = None,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Live inbox conversations from Zernio (proxied, not stored), restricted to THIS tenant's accounts."""
    client = get_zernio_client()
    if client is None:
        raise HTTPException(status_code=503, detail="Zernio not configured (ZERNIO_API_KEY missing)")
    mine = _tenant_account_ids(tenant_id)
    if account_id and account_id not in mine:
        raise HTTPException(status_code=403, detail="Account does not belong to this tenant")
    if not mine:
        return {"conversations": []}
    try:
        data = await client.list_conversations(
            platform=platform, status=status_filter, limit=limit,
            account_id=account_id,
        )
        return _filter_conversations(data, mine)
    except Exception as e:
        logger.error(f"Zernio list_conversations failed: {e}")
        raise _upstream_error("zernio", e)


async def _resolve_inbox_account(session, tenant_id: uuid.UUID, platform: str):
    """Find the tenant's account row for a platform, or create a stub one.

    SocialInboxMessage.account_id is a non-nullable FK, so webhook ingestion
    must resolve an account first. A stub row (no tokens) is created on first
    webhook per platform; connecting real credentials happens via the
    /social/accounts endpoints or Zernio OAuth.
    """
    stmt = select(SocialMediaAccount).where(
        SocialMediaAccount.tenant_id == tenant_id,
        SocialMediaAccount.platform == platform,
    ).order_by(SocialMediaAccount.created_at.desc()).limit(1)
    result = await session.execute(stmt)
    account = result.scalar_one_or_none()
    if account:
        return account
    account = SocialMediaAccount(
        tenant_id=tenant_id,
        platform=platform,
        account_name=f"{platform} (via Zernio)",
        status="ACTIVE",
    )
    session.add(account)
    await session.flush()
    return account


@app.post("/social/webhooks/{platform}", dependencies=[Depends(require_marketing_write)])
async def receive_social_webhook(
    platform: str,
    payload: Dict[str, Any],
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Receive webhooks from social media platforms (Facebook, Instagram, etc.)."""
    async with get_session() as session:
        event = SocialWebhookEvent(
            tenant_id=tenant_id,
            platform=platform,
            event_type=str(payload.get("event_type", "unknown"))[:100],
            payload=sec.bound_payload(payload, str(payload.get("event_type", "unknown"))),
            processed=False,
        )
        session.add(event)
        await session.flush()
    # In production, this would trigger async processing (auto-reply, inbox creation, etc.)
    return {"status": "received", "event_id": str(event.id)}


@app.post("/social/webhooks/zernio/inbound")
async def receive_zernio_webhook(
    request: Request,
):
    """Zernio webhook receiver: HMAC verify -> store event -> normalize to
    inbox -> comment automations (auto-reply via Zernio) -> support escalation.

    AUTH: HMAC-signed, NOT user-authenticated. External providers (Zernio)
    cannot send X-User-Id, so this route takes NO auth Depends() — the
    X-Zernio-Signature check IS the authentication. Tenant comes from the
    X-Tenant-Id header configured in the Zernio dashboard per subscription.

    Configure in the Zernio dashboard:
      URL: https://<marketing-host>/social/webhooks/zernio/inbound
      Header: X-Tenant-Id: <tenant uuid>  (tenant-scoped ingestion)
      Events: message.received, comment.received, mention.received
    """
    try:
        raw_body = await agentmail_client.read_body_capped(request, sec.WEBHOOK_MAX_BODY)
    except agentmail_client.BodyTooLarge:
        raise HTTPException(status_code=413, detail="Webhook body too large")
    # Fail closed: 503 when the secret is unset (unless ZERNIO_WEBHOOK_ALLOW_UNSIGNED=true),
    # 401 on a bad signature. Nothing below (storage, ChatEngine auto-reply) runs before this.
    sec.verify_zernio_signature(request.headers, raw_body)

    try:
        payload = json.loads(raw_body)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    # Real Zernio payload keys the event as "event" and nests platform under
    # "message"; read both through the shared extractor.
    from services.marketing.chat_webhooks import extract_event_meta
    event_type, platform = extract_event_meta(payload)

    # Replay/duplicate protection: the scheme carries no timestamp, so dedupe on the event id.
    event_key = sec.webhook_event_id(request.headers, payload, raw_body)
    engine = get_engine()
    _ensure_marketing_tables(engine)
    with engine.begin() as conn:
        is_new = sec.record_webhook_event(conn, "zernio", event_key)
    if not is_new:
        return {"status": "duplicate"}
    try:
        return await _process_zernio_event(payload, request.headers.get("X-Tenant-Id", ""), event_type, platform)
    except BaseException:
        # let the provider's retry be processed instead of being swallowed as a duplicate
        try:
            with engine.begin() as conn:
                sec.forget_webhook_event(conn, "zernio", event_key)
        except Exception:  # noqa: BLE001
            logger.warning("could not release webhook event id %s", event_key)
        raise


def _apply_post_event(tenant_id: str, zernio_post_id: str, status_: str, error: Optional[str]) -> None:
    with get_engine().begin() as conn:
        conn.execute(text("""
            UPDATE social_posts
               SET status = :st, publish_error = :err,
                   published_at = CASE WHEN :st IN ('published', 'partial') THEN COALESCE(published_at, now()) ELSE published_at END,
                   updated_at = now()
             WHERE tenant_id = :tid AND zernio_post_id = :zid
        """), {"st": status_, "err": error, "tid": tenant_id, "zid": zernio_post_id})


async def _mark_event_processed(event_id) -> None:
    async with get_session() as session:
        evt = await session.get(SocialWebhookEvent, event_id)
        if evt:
            evt.processed = True
            await session.flush()


async def _process_zernio_event(payload: Dict[str, Any], header_tenant: str, event_type: str, platform: str):
    """Runs only for verified, non-duplicate Zernio deliveries."""

    # ── Account lifecycle: keep the account→tenant map current, then return.
    # Routed by profileId (account events carry it), header as a fallback.
    if event_type in ("account.connected", "account.disconnected"):
        acct = payload.get("account") or {}
        pid = acct.get("profileId") or payload.get("profileId")
        atid = (_tenant_for_profile(str(pid)) if pid else None) or (header_tenant or None)
        if atid and pid:
            _upsert_connected_account(
                str(atid), str(pid), acct,
                status="disconnected" if event_type == "account.disconnected" else "connected",
            )
            return {"status": "received", "event": event_type,
                    "account_id": str(acct.get("accountId") or acct.get("_id") or "")}
        logger.warning("account event %s unrouted (profileId=%s)", event_type, pid)
        return {"status": "unrouted", "event": event_type}

    # ── Content events (message/comment/post): resolve the tenant. Prefer the
    # X-Tenant-Id header (per-subscription setups); otherwise map the accountId
    # in the payload back to a customer (per-team single-endpoint setups).
    tenant_id: Optional[uuid.UUID] = None
    if header_tenant:
        try:
            tenant_id = uuid.UUID(str(header_tenant))
        except (ValueError, AttributeError):
            tenant_id = None
    if tenant_id is None:
        msg = payload.get("message") or {}
        acct_id = (msg.get("account") or {}).get("id") or msg.get("accountId")
        if not acct_id:
            plats = payload.get("platforms") or (payload.get("post") or {}).get("platforms") or []
            if plats and isinstance(plats[0], dict):
                acct_id = plats[0].get("accountId")
        if not acct_id:
            # lead.* / ad.* / whatsapp.* events carry a top-level `account`
            top = payload.get("account") or {}
            acct_id = top.get("accountId") or top.get("id")
            if not acct_id and top.get("profileId"):
                by_profile = _tenant_for_profile(str(top["profileId"]))
                if by_profile:
                    tenant_id = uuid.UUID(by_profile)
        if acct_id and tenant_id is None:
            resolved = _tenant_for_account(str(acct_id))
            if resolved:
                tenant_id = uuid.UUID(resolved)
    if tenant_id is None:
        raise HTTPException(
            status_code=400,
            detail="Could not route webhook to a tenant (no X-Tenant-Id and no known accountId)",
        )

    # 1. Store raw event.
    async with get_session() as session:
        event = SocialWebhookEvent(
            tenant_id=tenant_id,
            platform=platform,
            event_type=event_type,
            payload=sec.bound_payload(payload, event_type),
            processed=False,
        )
        session.add(event)
        await session.flush()
        event_id = event.id

    # 1b. Post lifecycle: keep OmniDome's post rows in step with what the provider actually did.
    post_status = _zp.event_to_status(event_type)
    if post_status:
        zpost = payload.get("post") or {}
        zid = str(zpost.get("id") or zpost.get("_id") or "")
        err = None
        if post_status in ("failed", "partial"):
            err = "; ".join(_zp.platform_errors(zpost))[:1000] or f"provider reported {post_status}"
        if zid:
            await asyncio.to_thread(_apply_post_event, str(tenant_id), zid, post_status, err)
        await _mark_event_processed(event_id)
        return {"status": "received", "event": event_type, "post_id": zid or None, "post_status": post_status}

    # 1c. Meta Lead Ads: store the lead (idempotent on lead id; sync backfills anything missed).
    if event_type == "lead.received":
        from services.marketing import zernio_leads
        stored = await asyncio.to_thread(zernio_leads.ingest_lead_event, str(tenant_id), payload)
        await _mark_event_processed(event_id)
        return {"status": "received", "event": event_type, **stored}

    # 2. Reactions: log only, no inbox row.
    if event_type == "reaction.received":
        from services.marketing.chat_webhooks import ChatEngine
        engine = ChatEngine(get_session, get_zernio_client(), tenant_id=tenant_id)
        result = await engine.handle_reaction(payload)
        async with get_session() as session2:
            evt = await session2.get(SocialWebhookEvent, event_id)
            if evt:
                evt.processed = True
                await session2.flush()
        return {"status": "received", "event_id": str(event_id), "action": result["action"]}

    # 3. Normalize + store inbox message (resolve account row for the FK).
    from services.marketing.chat_webhooks import ChatEngine, normalize_webhook_event
    normalized = normalize_webhook_event(payload)
    message_id: Optional[uuid.UUID] = None
    async with get_session() as session:
        account = await _resolve_inbox_account(session, tenant_id, normalized.get("platform", platform))
        msg = SocialInboxMessage(
            tenant_id=tenant_id,
            account_id=account.id,
            platform=normalized.get("platform", platform),
            message_type=normalized.get("message_type", "DM"),
            external_id=normalized.get("external_id"),
            sender_name=normalized.get("sender_name"),
            sender_handle=normalized.get("sender_handle"),
            sender_profile_url=normalized.get("sender_profile_url"),
            content=normalized.get("content"),
            status="UNREAD",
            sentiment=normalized.get("sentiment"),
        )
        session.add(msg)
        await session.flush()
        message_id = msg.id
        evt = await session.get(SocialWebhookEvent, event_id)
        if evt:
            evt.processed = True
            await session.flush()

    # 4. Automations + escalation (never fail the webhook on downstream errors).
    action = "queued"
    ticket_id: Optional[str] = None
    try:
        engine = ChatEngine(get_session, get_zernio_client(), tenant_id=tenant_id)
        outcome = await engine.process_inbound_message(payload)
        action = outcome.get("action", "queued")
        ticket_id = outcome.get("ticket_id")
        if action == "auto_replied" and message_id:
            async with get_session() as session3:
                stored = await session3.get(SocialInboxMessage, message_id)
                if stored:
                    stored.status = "REPLIED"
                    stored.replied_at = datetime.now(timezone.utc)
                    await session3.flush()
    except Exception as e:
        logger.error(f"Zernio post-processing failed: {e}")

    return {
        "status": "received",
        "event_id": str(event_id),
        "message_id": str(message_id) if message_id else None,
        "action": action,
        "ticket_id": ticket_id,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# CALL CENTRE INTEGRATION
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/social/customer-360/{customer_id}", response_model=Customer360Out)
async def get_customer_social_360(
    customer_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Get social media data for a customer (for call centre 360 view)."""
    async with get_session() as session:
        # Get recent social inbox messages from this customer
        stmt = select(SocialInboxMessage).where(
            SocialInboxMessage.tenant_id == tenant_id,
        ).order_by(SocialInboxMessage.created_at.desc()).limit(20)
        result = await session.execute(stmt)
        messages = result.scalars().all()

    sentiment_counts = {"POSITIVE": 0, "NEUTRAL": 0, "NEGATIVE": 0}
    interactions = []
    for msg in messages:
        if msg.sentiment:
            sentiment_counts[msg.sentiment] = sentiment_counts.get(msg.sentiment, 0) + 1
        interactions.append({
            "platform": msg.platform,
            "type": msg.message_type,
            "content": msg.content[:200],
            "sentiment": msg.sentiment,
            "status": msg.status,
            "created_at": msg.created_at.isoformat() if msg.created_at else None,
        })

    return Customer360Out(
        customer_id=customer_id,
        recent_interactions=interactions,
        sentiment_summary=sentiment_counts,
        total_interactions=len(interactions),
    )


@app.post("/social/inbox/{message_id}/create-ticket", response_model=CreateTicketResponse, dependencies=[Depends(require_marketing_write)])
async def create_ticket_from_social(
    message_id: uuid.UUID,
    body: CreateTicketRequest,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Convert a social media message to a support ticket."""
    async with get_session() as session:
        stmt = select(SocialInboxMessage).where(
            SocialInboxMessage.id == message_id,
            SocialInboxMessage.tenant_id == tenant_id,
        )
        result = await session.execute(stmt)
        message = result.scalar_one_or_none()
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")

    # Bridge to support service
    support_url = os.getenv("SUPPORT_SERVICE_URL", "http://support:8008")
    ticket_id = None
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{support_url}/api/support/tickets",
                json={
                    "subject": body.subject or f"Social: {message.message_type} from {message.sender_name}",
                    "description": f"Platform: {message.platform}\nFrom: {message.sender_name} (@{message.sender_handle})\n\n{message.content}",
                    "priority": body.priority,
                    "source": "SOCIAL",
                    "source_id": str(message.id),
                    "assignee_id": str(body.assignee_id) if body.assignee_id else None,
                },
                headers={"x-tenant-id": str(tenant_id)},
            )
            if resp.status_code == 201:
                ticket_data = resp.json()
                ticket_id = ticket_data.get("id")
                # Mark message as replied
                async with get_session() as session2:
                    stmt2 = select(SocialInboxMessage).where(SocialInboxMessage.id == message_id)
                    result2 = await session2.execute(stmt2)
                    msg = result2.scalar_one_or_none()
                    if msg:
                        msg.status = "REPLIED"
                        msg.replied_at = datetime.utcnow()
                        await session2.flush()
    except Exception as e:
        logger.error(f"Support ticket creation failed: {e}")

    return CreateTicketResponse(
        ticket_id=ticket_id,
        status="created" if ticket_id else "failed",
        message=f"Ticket {'created' if ticket_id else 'creation failed'} from social message",
    )


# ──────────────── Traditional Media (Radio / OOH / Billboard) ────────────────


@app.get("/traditional-campaigns", response_model=List[Dict[str, Any]])
async def list_traditional_campaigns(
    medium: Optional[str] = None,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """List offline media buys (radio, billboard, OOH screens)."""
    async with get_session() as session:
        stmt = select(TraditionalMediaCampaign).where(TraditionalMediaCampaign.tenant_id == tenant_id)
        if medium:
            stmt = stmt.where(TraditionalMediaCampaign.medium == medium)
        stmt = stmt.order_by(TraditionalMediaCampaign.created_at.desc())
        result = await session.execute(stmt)
        campaigns = result.scalars().all()
    return [
        {
            "id": c.id,
            "tenant_id": c.tenant_id,
            "medium": c.medium,
            "name": c.name,
            "category": c.category,
            "reach": c.reach,
            "spots_booked": c.spots_booked,
            "impressions": c.impressions,
            "spend_zar": c.spend_zar,
            "leads_generated": c.leads_generated,
            "metrics": c.metrics,
            "period_month": c.period_month,
            "created_at": c.created_at,
        }
        for c in campaigns
    ]


@app.post("/traditional-campaigns", status_code=201, response_model=Dict[str, Any], dependencies=[Depends(require_marketing_write)])
async def create_traditional_campaign(
    body: TraditionalCampaignCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Record an offline media buy (radio, billboard, OOH screen)."""
    async with get_session() as session:
        campaign = TraditionalMediaCampaign(
            tenant_id=tenant_id,
            medium=body.medium,
            name=body.name,
            category=body.category,
            reach=body.reach,
            spots_booked=body.spots_booked,
            impressions=body.impressions,
            spend_zar=body.spend_zar,
            leads_generated=body.leads_generated,
            metrics=body.metrics,
            period_month=body.period_month,
        )
        session.add(campaign)
        await session.flush()
        await session.refresh(campaign)
        return {
            "id": campaign.id,
            "tenant_id": campaign.tenant_id,
            "medium": campaign.medium,
            "name": campaign.name,
            "category": campaign.category,
            "reach": campaign.reach,
            "spots_booked": campaign.spots_booked,
            "impressions": campaign.impressions,
            "spend_zar": campaign.spend_zar,
            "leads_generated": campaign.leads_generated,
            "metrics": campaign.metrics,
            "period_month": campaign.period_month,
            "created_at": campaign.created_at,
        }


# ─────────────────────────────────────────────────────────────────────────────
# WhatsApp Senders, Templates & Flows (Zernio-aligned WhatsApp Hub)
# ─────────────────────────────────────────────────────────────────────────────

# In-memory tenant store fallback for interactive WhatsApp assets (persisted within runtime)
_WHATSAPP_SENDERS: Dict[str, List[Dict[str, Any]]] = {}
_WHATSAPP_TEMPLATES: Dict[str, List[Dict[str, Any]]] = {}
_WHATSAPP_FLOWS: Dict[str, List[Dict[str, Any]]] = {}
_WHATSAPP_GROUPS: Dict[str, List[Dict[str, Any]]] = {}
_WHATSAPP_CONVERSIONS: Dict[str, List[Dict[str, Any]]] = {}


def _init_default_whatsapp(tenant_key: str):
    """Ensure empty per-tenant stores exist. Never inserts demo/seed rows:
    the WhatsApp tab shows only what the tenant actually created/connected."""
    for store in (_WHATSAPP_SENDERS, _WHATSAPP_TEMPLATES, _WHATSAPP_FLOWS,
                  _WHATSAPP_GROUPS, _WHATSAPP_CONVERSIONS):
        store.setdefault(tenant_key, [])


_NAME_REVIEW_LABELS = {
    "APPROVED": "Approved",
    "AVAILABLE_WITHOUT_REVIEW": "No review required",
    "PENDING_REVIEW": "Pending Meta review",
    "DECLINED": "Declined",
    "EXPIRED": "Expired",
    "NONE": "Not submitted",
}
_BIZ_VERIFICATION_LABELS = {
    "verified": "Verified",
    "not_verified": "Not verified",
    "pending": "Pending",
    "rejected": "Rejected",
    "failed": "Failed",
}


def whatsapp_sender_view(account_id: str, username: Optional[str], info: Optional[Dict[str, Any]], error: Optional[str]) -> Dict[str, Any]:
    """One senders-table row. `name_review` / `business_verification` come ONLY from Meta via the
    provider's number-info call (phone.name_status, waba.business_verification_status). When that
    call fails they are null (UI shows a dash) - never a placeholder value."""
    phone = (info or {}).get("phone") or {}
    waba = (info or {}).get("waba") or {}
    ns = phone.get("name_status")
    bv = waba.get("business_verification_status")
    raw_status = phone.get("status")
    return {
        "id": account_id,
        "account_id": account_id,
        "name": phone.get("verified_name") or waba.get("name") or username or "WhatsApp number",
        "number": phone.get("display_phone_number") or username,
        "type": "Business (Cloud API)" if phone.get("platform_type") in (None, "CLOUD_API") else str(phone.get("platform_type")),
        "name_review": _NAME_REVIEW_LABELS.get(str(ns).upper(), ns) if ns else None,
        "name_status": ns,
        "business_verification": _BIZ_VERIFICATION_LABELS.get(str(bv).lower(), bv) if bv else None,
        "business_verification_status": bv,
        "quality_rating": phone.get("quality_rating"),
        "messaging_limit_tier": phone.get("messaging_limit_tier"),
        "official_business_account": phone.get("is_official_business_account"),
        "status": ("LIVE" if str(raw_status).upper() == "CONNECTED" else str(raw_status).upper()) if raw_status else None,
        "live_data": info is not None,
        "status_error": error,
    }


@app.get("/whatsapp/senders", response_model=List[Dict[str, Any]])
async def list_whatsapp_senders(tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    """The tenant's connected WhatsApp numbers with LIVE Meta status (display-name review, business
    verification, quality, messaging tier) fetched through the provider per number."""
    from services.marketing.zernio_errors import provider_error

    engine = get_engine()
    _ensure_marketing_tables(engine)
    with engine.connect() as conn:
        rows = conn.execute(
            text("""SELECT account_id, username, connected_at FROM marketing_connected_accounts
                     WHERE tenant_id = :tid AND platform = 'whatsapp' AND status <> 'disconnected'
                     ORDER BY connected_at DESC"""),
            {"tid": str(tenant_id)},
        ).mappings().all()
    client = get_zernio_client()

    async def one(r) -> Dict[str, Any]:
        if client is None:
            return whatsapp_sender_view(r["account_id"], r["username"], None, "provider not configured")
        try:
            info = await client.whatsapp_number_info(r["account_id"])
            return whatsapp_sender_view(r["account_id"], r["username"], info, None)
        except Exception as exc:  # noqa: BLE001
            err = provider_error("whatsapp number-info", exc)
            msg = err.detail.get("message") if isinstance(err.detail, dict) else str(err.detail)
            return whatsapp_sender_view(r["account_id"], r["username"], None, msg)

    out = await asyncio.gather(*(one(r) for r in rows))
    for view, r in zip(out, rows):
        view["created_at"] = r["connected_at"].isoformat() if r.get("connected_at") else None
    return list(out)


class WhatsAppConnectNumberRequest(BaseModel):
    mode: str = Field(..., description="get_number | own_number")
    country_code: Optional[str] = "+27"
    phone_number: Optional[str] = None
    display_name: Optional[str] = "OmniDome WhatsApp"


@app.post("/whatsapp/senders/connect", status_code=201, response_model=Dict[str, Any], dependencies=[Depends(require_marketing_admin)])
async def connect_whatsapp_number(
    body: WhatsAppConnectNumberRequest,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Retired: this used to append a fabricated sender ('Pending Meta Review' / 'Verified' were
    hard-coded strings, and nothing was connected). Real connection runs through Meta Embedded
    Signup inside OmniDome: GET /social/connect/whatsapp/sdk-config, then
    POST /social/connect/whatsapp/embedded-signup (or .../credentials)."""
    if body.mode == "get_number":
        raise HTTPException(status_code=501, detail="Number provisioning is not implemented; connect your own number")
    raise HTTPException(status_code=422, detail={
        "error": "use_embedded_signup",
        "message": "Connect a WhatsApp number with Meta Embedded Signup.",
        "sdk_config_endpoint": "/social/connect/whatsapp/sdk-config",
        "complete_endpoint": "/social/connect/whatsapp/embedded-signup",
        "credentials_endpoint": "/social/connect/whatsapp/credentials",
    })


@app.get("/whatsapp/templates", response_model=List[Dict[str, Any]])
async def list_whatsapp_templates(tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    tkey = str(tenant_id)
    _init_default_whatsapp(tkey)
    return _WHATSAPP_TEMPLATES[tkey]


class WhatsAppTemplateCreate(BaseModel):
    name: str
    category: str = "MARKETING"
    language: str = "en_US"
    header: Optional[str] = None
    body: str
    footer: Optional[str] = None
    buttons: List[str] = Field(default_factory=list)


@app.post("/whatsapp/templates", status_code=201, response_model=Dict[str, Any], dependencies=[Depends(require_marketing_write)])
async def create_whatsapp_template(
    body: WhatsAppTemplateCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    tkey = str(tenant_id)
    _init_default_whatsapp(tkey)
    tpl = {
        "id": f"tpl-{uuid.uuid4().hex[:8]}",
        "name": body.name.strip().lower().replace(" ", "_"),
        "category": body.category,
        "language": body.language,
        "status": "APPROVED",
        "header": body.header,
        "body": body.body,
        "footer": body.footer,
        "buttons": body.buttons,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _WHATSAPP_TEMPLATES[tkey].append(tpl)
    return tpl


@app.get("/whatsapp/flows", response_model=List[Dict[str, Any]])
async def list_whatsapp_flows(tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    tkey = str(tenant_id)
    _init_default_whatsapp(tkey)
    return _WHATSAPP_FLOWS[tkey]


class WhatsAppFlowCreate(BaseModel):
    name: str
    trigger: str
    nodes: List[Dict[str, Any]] = Field(default_factory=list)


@app.post("/whatsapp/flows", status_code=201, response_model=Dict[str, Any], dependencies=[Depends(require_marketing_write)])
async def create_whatsapp_flow(
    body: WhatsAppFlowCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    tkey = str(tenant_id)
    _init_default_whatsapp(tkey)
    flow = {
        "id": f"flw-{uuid.uuid4().hex[:8]}",
        "name": body.name,
        "trigger": body.trigger,
        "status": "ACTIVE",
        "steps_count": len(body.nodes),
        "nodes": body.nodes,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _WHATSAPP_FLOWS[tkey].append(flow)
    return flow


@app.get("/whatsapp/groups", response_model=List[Dict[str, Any]])
async def list_whatsapp_groups(
    sender_id: Optional[str] = None,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    tkey = str(tenant_id)
    _init_default_whatsapp(tkey)
    groups = _WHATSAPP_GROUPS.get(tkey, [])
    if sender_id:
        groups = [g for g in groups if g.get("sender_id") == sender_id]
    return groups


class WhatsAppGroupCreate(BaseModel):
    name: str
    sender_id: Optional[str] = None
    invite_link: Optional[str] = None


@app.post("/whatsapp/groups", status_code=201, response_model=Dict[str, Any], dependencies=[Depends(require_marketing_write)])
async def create_whatsapp_group(
    body: WhatsAppGroupCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    tkey = str(tenant_id)
    _init_default_whatsapp(tkey)
    # Match sender info if available
    sender = next((s for s in _WHATSAPP_SENDERS.get(tkey, []) if s.get("id") == body.sender_id), None)
    group = {
        "id": f"grp-{uuid.uuid4().hex[:8]}",
        "sender_id": body.sender_id or (sender.get("id") if sender else None),
        "sender_name": sender.get("name") if sender else None,
        "sender_number": sender.get("number") if sender else None,
        "name": body.name,
        "participant_count": 1,
        "role": "admin",
        "invite_link": body.invite_link or f"https://chat.whatsapp.com/invite/{uuid.uuid4().hex[:10].upper()}",
        "is_active": True,
        "last_message_at": datetime.now(timezone.utc).isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _WHATSAPP_GROUPS[tkey].append(group)
    return group


@app.get("/whatsapp/conversions", response_model=List[Dict[str, Any]])
async def list_whatsapp_conversions(tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    tkey = str(tenant_id)
    _init_default_whatsapp(tkey)
    return _WHATSAPP_CONVERSIONS.get(tkey, [])


# ═══════════════════════════════════════════════════════════════════════════════
# SMS SENDER IDS & SENDING (Twilio / Provider Fallback)
# ═══════════════════════════════════════════════════════════════════════════════

_SMS_SENDERS: Dict[str, List[Dict[str, Any]]] = {}
_TEAM_MEMBERS: Dict[str, List[Dict[str, Any]]] = {}


def _init_default_sms_and_team(tkey: str):
    if tkey not in _SMS_SENDERS:
        _SMS_SENDERS[tkey] = [
            {
                "id": "sms-snd-1",
                "sender_id": "OmniDome",
                "status": "active",
                "type": "Alphanumeric (International)",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        ]
    if tkey not in _TEAM_MEMBERS:
        _TEAM_MEMBERS[tkey] = [
            {
                "id": "mem-1",
                "name": "Burni",
                "email": "burnibraai@gmail.com",
                "role": "Owner",
                "access": "Full access",
                "access_all_profiles": True,
                "profiles": ["All profiles"],
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        ]


class SmsSenderCreate(BaseModel):
    sender_id: str


@app.get("/sms/senders", response_model=List[Dict[str, Any]])
async def list_sms_senders(tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    tkey = str(tenant_id)
    _init_default_sms_and_team(tkey)
    return _SMS_SENDERS.get(tkey, [])


@app.post("/sms/senders", status_code=201, response_model=Dict[str, Any], dependencies=[Depends(require_marketing_write)])
async def create_sms_sender(
    body: SmsSenderCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    tkey = str(tenant_id)
    _init_default_sms_and_team(tkey)
    clean_id = body.sender_id.strip()
    if not clean_id or len(clean_id) > 11:
        raise HTTPException(status_code=400, detail="Sender ID must be between 1 and 11 alphanumeric characters.")
    sender = {
        "id": f"sms-snd-{uuid.uuid4().hex[:8]}",
        "sender_id": clean_id,
        "status": "active",
        "type": "Alphanumeric (International)",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _SMS_SENDERS[tkey].append(sender)
    return sender


@app.delete("/sms/senders/{sender_id}", status_code=200, dependencies=[Depends(require_marketing_write)])
async def delete_sms_sender(
    sender_id: str,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    tkey = str(tenant_id)
    _init_default_sms_and_team(tkey)
    _SMS_SENDERS[tkey] = [s for s in _SMS_SENDERS[tkey] if s["id"] != sender_id and s["sender_id"] != sender_id]
    return {"status": "deleted", "sender_id": sender_id}


class SmsSendRequest(BaseModel):
    sender_id: str
    to: str
    message: str


@app.post("/sms/send", status_code=200, response_model=Dict[str, Any], dependencies=[Depends(require_marketing_write)])
async def send_sms_message(
    body: SmsSendRequest,
    auth: AuthContext = Depends(get_auth_context),
):
    """Send one SMS through Twilio. Never reports success unless Twilio accepted the message.

    The repo has no per-tenant Twilio credential store, so only the PLATFORM Twilio account
    exists; it is usable by platform_admin only. Everyone else gets 501.
    """
    tenant_id = auth.tenant_id
    if not sec.valid_e164(body.to):
        raise HTTPException(status_code=422, detail="'to' must be an E.164 number, e.g. +27821234567")
    if not body.message or len(body.message) > 1600:
        raise HTTPException(status_code=422, detail="message must be 1-1600 characters")
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    if not (account_sid and auth_token) or not auth.is_platform_admin:
        raise HTTPException(status_code=501, detail="SMS provider not configured")
    sec.check_sms_rate(tenant_id)
    from_number = os.getenv("TWILIO_FROM_NUMBER", body.sender_id)
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            res = await client.post(
                f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json",
                auth=(account_sid, auth_token),
                data={"From": from_number, "To": body.to, "Body": body.message},
            )
    except Exception as err:  # noqa: BLE001
        raise _upstream_error("twilio", err)
    if res.status_code not in (200, 201):
        logger.error("twilio rejected SMS: status=%s", res.status_code)
        raise HTTPException(status_code=502, detail=f"SMS provider error (Twilio status {res.status_code})")
    data = res.json()
    return {"status": "sent", "provider": "twilio", "message_id": data.get("sid"), "to": body.to}


# ═══════════════════════════════════════════════════════════════════════════════
# TEAM & USERS MANAGEMENT (Zernio-aligned roles)
# ═══════════════════════════════════════════════════════════════════════════════

class TeamMemberInvite(BaseModel):
    emails: Optional[str] = None
    role: str = "Member"
    access_all_profiles: bool = True
    profile_ids: Optional[List[str]] = None


@app.get("/team/members", response_model=List[Dict[str, Any]])
async def list_team_members(tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    tkey = str(tenant_id)
    _init_default_sms_and_team(tkey)
    return _TEAM_MEMBERS.get(tkey, [])


@app.post("/team/members/invite", status_code=201, response_model=Dict[str, Any], dependencies=[Depends(require_marketing_admin)])
async def invite_team_member(
    body: TeamMemberInvite,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    tkey = str(tenant_id)
    _init_default_sms_and_team(tkey)

    invite_token = f"omni_inv_{uuid.uuid4().hex[:16]}"
    invite_link = f"https://app.omnidome.io/invite/join?token={invite_token}"

    invited_list = []
    if body.emails:
        email_items = [e.strip() for e in body.emails.split(",") if e.strip()]
        for email in email_items:
            name = email.split("@")[0].replace(".", " ").title()
            new_member = {
                "id": f"mem-{uuid.uuid4().hex[:8]}",
                "name": name,
                "email": email,
                "role": body.role,
                "access": "Full access" if body.access_all_profiles else f"Selected ({len(body.profile_ids or [])})",
                "access_all_profiles": body.access_all_profiles,
                "profiles": body.profile_ids or (["All profiles"] if body.access_all_profiles else []),
                "status": "invited",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            _TEAM_MEMBERS[tkey].append(new_member)
            invited_list.append(email)

    return {
        "invite_link": invite_link,
        "token": invite_token,
        "invited_emails": invited_list,
        "role": body.role,
        "access_all_profiles": body.access_all_profiles,
    }


@app.delete("/team/members/{member_id}", status_code=200, dependencies=[Depends(require_marketing_admin)])
async def delete_team_member(
    member_id: str,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    tkey = str(tenant_id)
    _init_default_sms_and_team(tkey)
    _TEAM_MEMBERS[tkey] = [m for m in _TEAM_MEMBERS[tkey] if m["id"] != member_id]
    return {"status": "deleted", "member_id": member_id}


# ═══════════════════════════════════════════════════════════════════════════════
# ZERNIO INTEGRATION ROUTERS (connect flow, ads, lead forms). Included last so the
# explicit routes above keep precedence; modules import this one lazily (no cycle).
# See docs/zernio-marketing-integration.md for the full contract.
# ═══════════════════════════════════════════════════════════════════════════════
from services.marketing import zernio_connect as _zernio_connect  # noqa: E402
from services.marketing import zernio_ads as _zernio_ads  # noqa: E402
from services.marketing import zernio_leads as _zernio_leads  # noqa: E402

app.include_router(_zernio_connect.router)
app.include_router(_zernio_ads.router)
app.include_router(_zernio_leads.router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
