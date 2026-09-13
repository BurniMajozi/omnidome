"""
OmniDome Marketing Service
===========================
Campaign management · Email delivery · Lead scoring · Automation · Attribution
Social Media · WhatsApp · Ad Campaigns · Comment Automation · Webhooks

Port: 8014
"""

from datetime import datetime, timedelta, date, timezone
from decimal import Decimal
import logging
import os
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional
import uuid

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import text, select, insert, update, delete, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from services.common.auth import AuthContext, get_auth_context, get_current_tenant_id
from services.common.db import get_engine, get_async_session, run_with_db_retry
from services.common.entitlements import EntitlementGuard
from services.common.middleware import configure_production
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
    public_paths={"/social/webhooks/zernio/inbound"},
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
    logger.info("Marketing service started — tables initialized")
    yield
    logger.info("Marketing service shutting down")


app.router.lifespan_context = lifespan


@app.middleware("http")
async def entitlement_middleware(request, call_next):
    return await guard.middleware(request, call_next)


# ─────────────────────────────── Pydantic Models ───────────────────────────────


class CampaignCreate(BaseModel):
    name: str
    channel: str = Field(..., description="email | social | search | display | sms")
    description: Optional[str] = None
    budget_zar: Decimal = Decimal("0")
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    audience_segment_id: Optional[uuid.UUID] = None


class CampaignUpdate(BaseModel):
    name: Optional[str] = None
    channel: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    budget_zar: Optional[Decimal] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None


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
    total_sent: int
    total_delivered: int
    total_opened: int
    total_clicked: int
    total_conversions: int
    created_at: datetime


class EmailSendRequest(BaseModel):
    campaign_id: uuid.UUID
    template_id: Optional[uuid.UUID] = None
    subject: str
    body_html: str
    recipients: List[str] = Field(..., description="List of email addresses")
    from_name: Optional[str] = "OmniDome"
    from_email: Optional[str] = None
    reply_to: Optional[str] = None
    tags: List[str] = Field(default_factory=list)


class EmailSendResponse(BaseModel):
    batch_id: uuid.UUID
    campaign_id: uuid.UUID
    total_queued: int
    status: str


class LeadScoreUpdate(BaseModel):
    contact_id: uuid.UUID
    score_delta: int = Field(..., description="Points to add (positive) or remove (negative)")
    reason: str


class AudienceSegmentCreate(BaseModel):
    name: str
    description: Optional[str] = None
    rules: Dict[str, Any] = Field(default_factory=dict, description="JSON filter rules")


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


class TokenRefreshResponse(BaseModel):
    status: str
    expires_at: Optional[datetime] = None


# -- Social Post --
class SocialPostCreate(BaseModel):
    account_id: uuid.UUID
    campaign_id: Optional[uuid.UUID] = None
    content: Optional[str] = None
    media_urls: Optional[List[str]] = None
    platforms: Optional[List[str]] = None
    status: str = "DRAFT"
    scheduled_for: Optional[datetime] = None


class SocialPostUpdate(BaseModel):
    content: Optional[str] = None
    media_urls: Optional[List[str]] = None
    status: Optional[str] = None
    scheduled_for: Optional[datetime] = None


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
    """
    with engine.begin() as conn:
        conn.execute(text(ddl))


# ─────────────────────────── Health ─────────────────────────


@app.get("/health")
async def health():
    return {"status": "ok", "service": "marketing"}


# ─────────────────────────── Campaigns ─────────────────────────


@app.get("/campaigns", response_model=List[CampaignOut])
async def list_campaigns(
    channel: Optional[str] = None,
    campaign_status: Optional[str] = Query(None, alias="status"),
    limit: int = 50,
    offset: int = 0,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    engine = get_engine()
    _ensure_marketing_tables(engine)
    filters = "WHERE tenant_id = :tid"
    params: Dict[str, Any] = {"tid": str(tenant_id), "lim": limit, "off": offset}
    if channel:
        filters += " AND channel = :ch"
        params["ch"] = channel
    if campaign_status:
        filters += " AND status = :st"
        params["st"] = campaign_status
    with engine.connect() as conn:
        rows = conn.execute(
            text(f"SELECT * FROM marketing_campaigns {filters} ORDER BY created_at DESC LIMIT :lim OFFSET :off"),
            params,
        ).mappings().all()
    return [dict(r) for r in rows]


@app.post("/campaigns", response_model=CampaignOut, status_code=201)
async def create_campaign(
    body: CampaignCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    engine = get_engine()
    _ensure_marketing_tables(engine)
    cid = uuid.uuid4()
    with engine.begin() as conn:
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
                "asid": str(body.audience_segment_id) if body.audience_segment_id else None,
            },
        )
        row = conn.execute(
            text("SELECT * FROM marketing_campaigns WHERE id = :id"), {"id": str(cid)}
        ).mappings().first()
    return dict(row)


@app.patch("/campaigns/{campaign_id}", response_model=CampaignOut)
async def update_campaign(
    campaign_id: uuid.UUID,
    body: CampaignUpdate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    engine = get_engine()
    sets = []
    params: Dict[str, Any] = {"cid": str(campaign_id), "tid": str(tenant_id)}
    for field, val in body.dict(exclude_unset=True).items():
        sets.append(f"{field} = :{field}")
        params[field] = float(val) if isinstance(val, Decimal) else val
    if not sets:
        raise HTTPException(400, "No fields to update")
    sets.append("updated_at = now()")
    with engine.begin() as conn:
        result = conn.execute(
            text(f"UPDATE marketing_campaigns SET {', '.join(sets)} WHERE id = :cid AND tenant_id = :tid RETURNING *"),
            params,
        ).mappings().first()
    if not result:
        raise HTTPException(404, "Campaign not found")
    return dict(result)


@app.delete("/campaigns/{campaign_id}", status_code=204)
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


@app.post("/email/send", response_model=EmailSendResponse, status_code=202)
async def send_email_batch(
    body: EmailSendRequest,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Queue a batch of emails for delivery (transactional or bulk)."""
    engine = get_engine()
    _ensure_marketing_tables(engine)
    batch_id = uuid.uuid4()
    total = len(body.recipients)
    with engine.begin() as conn:
        # Verify campaign exists
        camp = conn.execute(
            text("SELECT id FROM marketing_campaigns WHERE id = :cid AND tenant_id = :tid"),
            {"cid": str(body.campaign_id), "tid": str(tenant_id)},
        ).first()
        if not camp:
            raise HTTPException(404, "Campaign not found")

        conn.execute(
            text("""
                INSERT INTO marketing_email_batches
                    (id, tenant_id, campaign_id, subject, from_name, from_email, total_queued, status)
                VALUES (:bid, :tid, :cid, :subj, :fn, :fe, :tq, 'queued')
            """),
            {
                "bid": str(batch_id),
                "tid": str(tenant_id),
                "cid": str(body.campaign_id),
                "subj": body.subject,
                "fn": body.from_name,
                "fe": body.from_email,
                "tq": total,
            },
        )

        # Update campaign counters
        conn.execute(
            text("UPDATE marketing_campaigns SET total_sent = total_sent + :cnt, updated_at = now() WHERE id = :cid"),
            {"cnt": total, "cid": str(body.campaign_id)},
        )

    return EmailSendResponse(
        batch_id=batch_id,
        campaign_id=body.campaign_id,
        total_queued=total,
        status="queued",
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


@app.post("/email/webhook")
async def email_webhook(event: Dict[str, Any]):
    """Webhook endpoint for email provider callbacks (delivery, bounce, open, click)."""
    engine = get_engine()
    _ensure_marketing_tables(engine)
    event_type = event.get("event_type", "unknown")
    batch_id = event.get("batch_id")
    if not batch_id:
        raise HTTPException(400, "batch_id required")

    counter_map = {
        "delivered": "total_delivered",
        "bounced": "total_bounced",
        "opened": "total_opened",
        "clicked": "total_clicked",
    }
    col = counter_map.get(event_type)
    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO marketing_email_events (tenant_id, batch_id, recipient_email, event_type, event_data)
                SELECT tenant_id, id, :email, :etype, :edata::jsonb
                FROM marketing_email_batches WHERE id = :bid
            """),
            {
                "bid": batch_id,
                "email": event.get("email", ""),
                "etype": event_type,
                "edata": "{}",
            },
        )
        if col:
            conn.execute(
                text(f"UPDATE marketing_email_batches SET {col} = {col} + 1 WHERE id = :bid"),
                {"bid": batch_id},
            )
    return {"status": "accepted"}


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


@app.post("/templates", status_code=201)
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


# ──────────────────── Audience Segments ────────────────────────


@app.get("/segments")
async def list_segments(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    engine = get_engine()
    _ensure_marketing_tables(engine)
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT * FROM marketing_audience_segments WHERE tenant_id = :tid ORDER BY created_at DESC"),
            {"tid": str(tenant_id)},
        ).mappings().all()
    return [dict(r) for r in rows]


@app.post("/segments", status_code=201)
async def create_segment(
    body: AudienceSegmentCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    engine = get_engine()
    _ensure_marketing_tables(engine)
    sid = uuid.uuid4()
    import json

    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO marketing_audience_segments (id, tenant_id, name, description, rules)
                VALUES (:id, :tid, :name, :desc, :rules::jsonb)
            """),
            {
                "id": str(sid),
                "tid": str(tenant_id),
                "name": body.name,
                "desc": body.description,
                "rules": json.dumps(body.rules),
            },
        )
        row = conn.execute(
            text("SELECT * FROM marketing_audience_segments WHERE id = :id"), {"id": str(sid)}
        ).mappings().first()
    return dict(row)


# ──────────────────── Lead Scoring ─────────────────────────────


@app.post("/leads/score")
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


@app.post("/automations", status_code=201)
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


@app.post("/ab-tests", status_code=201)
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


@app.post("/social/accounts", status_code=201, response_model=Dict[str, Any])
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


@app.put("/social/accounts/{account_id}", response_model=Dict[str, Any])
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


@app.delete("/social/accounts/{account_id}", status_code=204)
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
    redirect_url: Optional[str] = None,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Get the OAuth connect URL for a platform via Zernio's hosted flow, scoped
    to THIS tenant's profile (auto-created on first connect). The account then
    lands in the customer's own profile — the profile-per-customer model.
    """
    client = get_zernio_client()
    if client is None:
        raise HTTPException(status_code=503, detail="Zernio not configured (ZERNIO_API_KEY missing)")
    profile_id = await _ensure_tenant_profile(tenant_id)
    if not profile_id:
        raise HTTPException(status_code=503, detail="Could not resolve a Zernio profile for this tenant")
    try:
        auth_url = await client.get_connect_url(platform.lower(), profile_id=profile_id, redirect_url=redirect_url)
    except Exception as e:  # noqa: BLE001
        logger.error(f"Zernio connect URL failed for {platform}: {e}")
        raise HTTPException(status_code=502, detail=f"Zernio upstream error: {e}")
    if not auth_url:
        raise HTTPException(
            status_code=502,
            detail=f"Zernio returned no connect URL for '{platform}' (unsupported platform?)",
        )
    return OAuthUrlResponse(platform=platform, auth_url=auth_url)


@app.post("/social/accounts/{account_id}/refresh", response_model=TokenRefreshResponse)
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


@app.get("/social/posts", response_model=List[Dict[str, Any]])
async def list_social_posts(
    post_status: Optional[str] = Query(None, alias="status"),
    account_id: Optional[uuid.UUID] = None,
    campaign_id: Optional[uuid.UUID] = None,
    limit: int = 50,
    offset: int = 0,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """List social media posts with optional filters."""
    async with get_session() as session:
        stmt = select(SocialPost).where(SocialPost.tenant_id == tenant_id)
        if post_status:
            stmt = stmt.where(SocialPost.status == post_status)
        if account_id:
            stmt = stmt.where(SocialPost.account_id == account_id)
        if campaign_id:
            stmt = stmt.where(SocialPost.campaign_id == campaign_id)
        stmt = stmt.order_by(SocialPost.created_at.desc()).limit(limit).offset(offset)
        result = await session.execute(stmt)
        posts = result.scalars().all()
    return [
        {
            "id": p.id,
            "tenant_id": p.tenant_id,
            "account_id": p.account_id,
            "campaign_id": p.campaign_id,
            "content": p.content,
            "media_urls": p.media_urls,
            "platforms": p.platforms,
            "status": p.status,
            "scheduled_for": p.scheduled_for,
            "published_at": p.published_at,
            "platform_post_ids": p.platform_post_ids,
            "engagement_data": p.engagement_data,
            "created_at": p.created_at,
            "updated_at": p.updated_at,
        }
        for p in posts
    ]


@app.post("/social/posts", status_code=201, response_model=Dict[str, Any])
async def create_social_post(
    body: SocialPostCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Create a social media post (draft, schedule, or publish)."""
    async with get_session() as session:
        post = SocialPost(
            tenant_id=tenant_id,
            account_id=body.account_id,
            campaign_id=body.campaign_id,
            content=body.content,
            media_urls=body.media_urls,
            platforms=body.platforms or [],
            status=body.status,
            scheduled_for=body.scheduled_for,
        )
        session.add(post)
        await session.flush()
        await session.refresh(post)
        return {
            "id": post.id,
            "tenant_id": post.tenant_id,
            "account_id": post.account_id,
            "campaign_id": post.campaign_id,
            "content": post.content,
            "media_urls": post.media_urls,
            "platforms": post.platforms,
            "status": post.status,
            "scheduled_for": post.scheduled_for,
            "published_at": post.published_at,
            "created_at": post.created_at,
            "updated_at": post.updated_at,
        }


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
    return {
        "id": post.id,
        "tenant_id": post.tenant_id,
        "account_id": post.account_id,
        "campaign_id": post.campaign_id,
        "content": post.content,
        "media_urls": post.media_urls,
        "platforms": post.platforms,
        "status": post.status,
        "scheduled_for": post.scheduled_for,
        "published_at": post.published_at,
        "platform_post_ids": post.platform_post_ids,
        "engagement_data": post.engagement_data,
        "created_at": post.created_at,
        "updated_at": post.updated_at,
    }


@app.put("/social/posts/{post_id}", response_model=Dict[str, Any])
async def update_social_post(
    post_id: uuid.UUID,
    body: SocialPostUpdate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Update a social media post."""
    async with get_session() as session:
        stmt = select(SocialPost).where(
            SocialPost.id == post_id,
            SocialPost.tenant_id == tenant_id,
        )
        result = await session.execute(stmt)
        post = result.scalar_one_or_none()
        if not post:
            raise HTTPException(status_code=404, detail="Post not found")
        if post.status == "PUBLISHED":
            raise HTTPException(status_code=400, detail="Cannot update a published post")

        update_data = body.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(post, field, value)
        await session.flush()
        await session.refresh(post)
        return {
            "id": post.id,
            "tenant_id": post.tenant_id,
            "account_id": post.account_id,
            "campaign_id": post.campaign_id,
            "content": post.content,
            "media_urls": post.media_urls,
            "platforms": post.platforms,
            "status": post.status,
            "scheduled_for": post.scheduled_for,
            "published_at": post.published_at,
            "platform_post_ids": post.platform_post_ids,
            "engagement_data": post.engagement_data,
            "created_at": post.created_at,
            "updated_at": post.updated_at,
        }


@app.delete("/social/posts/{post_id}", status_code=204)
async def delete_social_post(
    post_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Delete a social media post."""
    async with get_session() as session:
        stmt = select(SocialPost).where(
            SocialPost.id == post_id,
            SocialPost.tenant_id == tenant_id,
        )
        result = await session.execute(stmt)
        post = result.scalar_one_or_none()
        if not post:
            raise HTTPException(status_code=404, detail="Post not found")
        await session.delete(post)
    return None


@app.post("/social/posts/{post_id}/publish", response_model=Dict[str, Any])
async def publish_post(
    post_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Publish a social media post immediately."""
    async with get_session() as session:
        stmt = select(SocialPost).where(
            SocialPost.id == post_id,
            SocialPost.tenant_id == tenant_id,
        )
        result = await session.execute(stmt)
        post = result.scalar_one_or_none()
        if not post:
            raise HTTPException(status_code=404, detail="Post not found")
        if post.status == "PUBLISHED":
            raise HTTPException(status_code=400, detail="Post is already published")

        # In production, this would call the platform's publishing API
        post.status = "PUBLISHED"
        post.published_at = datetime.utcnow()
        post.platform_post_ids = {"platform": f"ext_{uuid.uuid4().hex[:12]}"}
        await session.flush()
        await session.refresh(post)
        return {
            "id": post.id,
            "status": post.status,
            "published_at": post.published_at,
            "platform_post_ids": post.platform_post_ids,
        }


@app.post("/social/posts/{post_id}/schedule", response_model=Dict[str, Any])
async def schedule_post(
    post_id: uuid.UUID,
    scheduled_for: datetime,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Schedule a social media post for later."""
    if scheduled_for <= datetime.utcnow():
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
        if post.status == "PUBLISHED":
            raise HTTPException(status_code=400, detail="Post is already published")

        post.status = "SCHEDULED"
        post.scheduled_for = scheduled_for
        await session.flush()
        await session.refresh(post)
        return {
            "id": post.id,
            "status": post.status,
            "scheduled_for": post.scheduled_for,
        }


@app.post("/social/posts/cross-post", response_model=CrossPostResponse)
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


@app.post("/social/inbox/{message_id}/reply", response_model=Dict[str, Any])
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


@app.put("/social/inbox/{message_id}/read", response_model=Dict[str, Any])
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


@app.put("/social/inbox/{message_id}/archive", response_model=Dict[str, Any])
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


@app.post("/whatsapp/contacts", status_code=201, response_model=Dict[str, Any])
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


@app.post("/whatsapp/contacts/bulk-import", response_model=BulkImportResponse)
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


@app.post("/whatsapp/broadcasts", status_code=201, response_model=Dict[str, Any])
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


@app.post("/whatsapp/broadcasts/{broadcast_id}/send", response_model=BroadcastSendResponse)
async def send_whatsapp_broadcast(
    broadcast_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Send a WhatsApp broadcast to all recipients."""
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

        # In production, this would queue messages via WhatsApp Business API
        broadcast.status = "SENDING"
        broadcast.sent_at = datetime.utcnow()

        # Update recipient statuses
        recipient_stmt = select(WhatsAppBroadcastRecipient).where(
            WhatsAppBroadcastRecipient.broadcast_id == broadcast_id,
        )
        recipient_result = await session.execute(recipient_stmt)
        recipients = recipient_result.scalars().all()
        for r in recipients:
            r.status = "SENT"
            r.sent_at = datetime.utcnow()

        broadcast.sent_count = len(recipients)
        broadcast.status = "SENT"
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


@app.post("/ads/campaigns", status_code=201, response_model=Dict[str, Any])
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


@app.put("/ads/campaigns/{campaign_id}", response_model=Dict[str, Any])
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


@app.delete("/ads/campaigns/{campaign_id}", status_code=204)
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


@app.post("/social/automations", status_code=201)
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


@app.put("/social/automations/{automation_id}")
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


@app.delete("/social/automations/{automation_id}", status_code=204)
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
    {"id": "snapchat", "label": "Snapchat", "category": "Social", "coming_soon": True},
    {"id": "telegram", "label": "Telegram", "category": "Messaging"},
    {"id": "whatsapp", "label": "WhatsApp", "category": "Messaging"},
    {"id": "shopify", "label": "Shopify", "category": "Commerce"},
]


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
        p = str(acct["platform"] or "").lower()
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
# ═══════════════════════════════════════════════════════════════════════════

_METRIC_COLS = ["impressions", "reach", "likes", "comments", "shares", "saves", "clicks", "views"]


class TenantProfileIn(BaseModel):
    zernio_profile_id: str


@app.put("/social/analytics/profile", response_model=Dict[str, Any])
async def set_tenant_profile(
    body: TenantProfileIn,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Map this tenant (customer) to its Zernio profile — the id the sync
    worker filters every analytics pull on."""
    engine = get_engine()
    _ensure_marketing_tables(engine)
    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO marketing_tenant_profiles (tenant_id, zernio_profile_id)
                VALUES (:tid, :pid)
                ON CONFLICT (tenant_id)
                DO UPDATE SET zernio_profile_id = EXCLUDED.zernio_profile_id, updated_at = now()
            """),
            {"tid": str(tenant_id), "pid": body.zernio_profile_id},
        )
    return {"tenant_id": str(tenant_id), "zernio_profile_id": body.zernio_profile_id}


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
    """Read the tenant's Zernio profile id (no creation). Falls back to the
    shared ZERNIO_PROFILE_ID env for single-profile setups."""
    engine = get_engine()
    _ensure_marketing_tables(engine)
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT zernio_profile_id FROM marketing_tenant_profiles WHERE tenant_id = :tid"),
            {"tid": str(tenant_id)},
        ).first()
    if row:
        return row[0]
    return os.getenv("ZERNIO_PROFILE_ID") or None


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


@app.post("/social/profile/ensure", response_model=Dict[str, Any])
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
        raise HTTPException(status_code=502, detail=f"Zernio upstream error: {e}")
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
    try:
        usage = await client.get_usage(range_="cycle", group_by="profile")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Zernio upstream error: {e}")
    groups = ((usage or {}).get("attribution") or {}).get("groups") or []
    mine = next((g for g in groups if g.get("profileId") == profile_id or g.get("id") == profile_id), None)
    return {"profile_id": profile_id, "usage": mine, "restricted": ((usage or {}).get("attribution") or {}).get("restricted", False)}


class ScopedKeyIn(BaseModel):
    name: str
    permission: Optional[str] = None  # "read" for read-only
    disabled_resource_groups: Optional[List[str]] = None
    expires_in: Optional[int] = None  # days


@app.post("/social/api-keys", response_model=Dict[str, Any])
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
        raise HTTPException(status_code=502, detail=f"Zernio upstream error: {e}")
    return result


@app.post("/social/profile/offboard", response_model=Dict[str, Any])
async def offboard_profile(tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    """Disconnect the tenant's accounts, then delete its Zernio profile, then
    clear local rows. Active accounts block profile deletion, so they go first."""
    client = get_zernio_client()
    if client is None:
        raise HTTPException(status_code=503, detail="Zernio not configured (ZERNIO_API_KEY missing)")
    profile_id = _get_tenant_profile(tenant_id)
    if not profile_id:
        return {"status": "nothing_to_offboard"}
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
        raise HTTPException(status_code=502, detail=f"Profile delete failed (disconnect accounts first?): {e}")
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
            text("SELECT scheduled_for FROM social_posts WHERE tenant_id = :tid AND status = 'scheduled' AND scheduled_for IS NOT NULL"),
            {"tid": str(tenant_id)},
        ).all()
    out = set()
    for r in rows:
        v = r[0]
        if v is not None:
            iso = v.isoformat() if hasattr(v, "isoformat") else str(v)
            out.add(iso)
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


@app.post("/social/queues", status_code=201, response_model=Dict[str, Any])
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


@app.patch("/social/queues/{queue_id}", response_model=Dict[str, Any])
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


@app.delete("/social/queues/{queue_id}", status_code=204)
async def delete_queue(queue_id: uuid.UUID, tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    engine = get_engine()
    _ensure_marketing_tables(engine)
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM marketing_post_queues WHERE id = :id AND tenant_id = :tid"),
            {"id": str(queue_id), "tid": str(tenant_id)},
        )
    return None


@app.post("/social/queues/{queue_id}/enqueue", status_code=201, response_model=Dict[str, Any])
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
    async with get_session() as session:
        post = SocialPost(
            tenant_id=tenant_id, account_id=body.account_id, content=body.content,
            media_urls=body.media_urls, platforms=body.platforms or [],
            status="scheduled", scheduled_for=slot_dt,
        )
        session.add(post)
        await session.flush()
        await session.refresh(post)
        return {"id": str(post.id), "status": post.status, "scheduled_for": post.scheduled_for.isoformat() if post.scheduled_for else slot, "queue_id": str(queue_id)}


@app.get("/social/zernio/accounts", response_model=List[Dict[str, Any]])
async def zernio_accounts(
    platform: Optional[str] = None,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Live connected accounts from Zernio (proxied, not stored)."""
    client = get_zernio_client()
    if client is None:
        raise HTTPException(status_code=503, detail="Zernio not configured (ZERNIO_API_KEY missing)")
    try:
        return await client.list_accounts(platform=platform)
    except Exception as e:
        logger.error(f"Zernio list_accounts failed: {e}")
        raise HTTPException(status_code=502, detail=f"Zernio upstream error: {e}")


@app.get("/social/zernio/conversations", response_model=Dict[str, Any])
async def zernio_conversations(
    platform: Optional[str] = None,
    status_filter: Optional[str] = Query(default=None, alias="status"),
    limit: int = Query(20, ge=1, le=100),
    account_id: Optional[str] = None,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Live inbox conversations from Zernio (proxied, not stored)."""
    client = get_zernio_client()
    if client is None:
        raise HTTPException(status_code=503, detail="Zernio not configured (ZERNIO_API_KEY missing)")
    try:
        return await client.list_conversations(
            platform=platform, status=status_filter, limit=limit,
            account_id=account_id,
        )
    except Exception as e:
        logger.error(f"Zernio list_conversations failed: {e}")
        raise HTTPException(status_code=502, detail=f"Zernio upstream error: {e}")


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


@app.post("/social/webhooks/{platform}")
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
            event_type=payload.get("event_type", "unknown"),
            payload=payload,
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
    raw_body = await request.body()
    signature = request.headers.get("X-Zernio-Signature", "")
    zernio_event = request.headers.get("X-Zernio-Event", "")
    zernio_event_id = request.headers.get("X-Zernio-Event-Id", "")

    secret = os.getenv("ZERNIO_WEBHOOK_SECRET", "")
    if secret:
        import hashlib
        import hmac
        expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            # Debug aid (never logs the secret): distinguishes proxy-stripped
            # headers from genuine secret mismatch on the next delivery.
            logger.warning(
                "Zernio signature mismatch: sig_present=%s sig_len=%d "
                "expected_len=%d body_len=%d event=%s event_id_present=%s",
                bool(signature), len(signature), len(expected), len(raw_body),
                zernio_event or "missing", bool(zernio_event_id),
            )
            raise HTTPException(status_code=401, detail="Invalid webhook signature")
    else:
        logger.warning("ZERNIO_WEBHOOK_SECRET not set — accepting unsigned webhook")

    try:
        import json
        payload = json.loads(raw_body)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    # Real Zernio payload keys the event as "event" and nests platform under
    # "message"; read both through the shared extractor.
    from services.marketing.chat_webhooks import extract_event_meta
    event_type, platform = extract_event_meta(payload)

    header_tenant = request.headers.get("X-Tenant-Id", "")

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
        if acct_id:
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
            payload=payload,
            processed=False,
        )
        session.add(event)
        await session.flush()
        event_id = event.id

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


@app.post("/social/inbox/{message_id}/create-ticket", response_model=CreateTicketResponse)
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


@app.post("/traditional-campaigns", status_code=201, response_model=Dict[str, Any])
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)