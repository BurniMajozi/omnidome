"""
SQLAlchemy async database setup and ORM models for the Marketing Service.

Covers:
  - Legacy marketing tables (campaigns, email batches, templates, segments, etc.)
  - Social media accounts, posts, inbox, analytics
  - WhatsApp contacts and broadcasts
  - Ad campaigns and comment automation
  - Social webhook events
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import datetime, date
from decimal import Decimal
from typing import Any, AsyncGenerator, Dict, List, Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from services.common.db import get_async_engine


# ---------------------------------------------------------------------------
# Session factory
# ---------------------------------------------------------------------------

_async_session_factory: async_sessionmaker | None = None


def _get_async_session_factory() -> async_sessionmaker:
    global _async_session_factory
    if _async_session_factory is None:
        engine = get_async_engine()
        _async_session_factory = async_sessionmaker(engine, expire_on_commit=False)
    return _async_session_factory


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield a transactional async DB session and commit on success."""
    factory = _get_async_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

SOCIAL_MEDIA_PLATFORM = SAEnum(
    "twitter", "instagram", "facebook", "linkedin", "tiktok",
    "whatsapp", "youtube", "pinterest", "threads", "bluesky",
    "telegram", "snapchat", "googlebusiness",
    name="social_media_platform", create_type=False,
)

SOCIAL_ACCOUNT_STATUS = SAEnum(
    "ACTIVE", "EXPIRED", "DISCONNECTED",
    name="social_account_status", create_type=False,
)

SOCIAL_POST_STATUS = SAEnum(
    "DRAFT", "SCHEDULED", "PUBLISHED", "FAILED",
    name="social_post_status", create_type=False,
)

SOCIAL_INBOX_MESSAGE_TYPE = SAEnum(
    "COMMENT", "DM", "MENTION", "REVIEW",
    name="social_inbox_message_type", create_type=False,
)

SOCIAL_INBOX_STATUS = SAEnum(
    "UNREAD", "READ", "REPLIED", "ARCHIVED",
    name="social_inbox_status", create_type=False,
)

SOCIAL_INBOX_SENTIMENT = SAEnum(
    "POSITIVE", "NEUTRAL", "NEGATIVE",
    name="social_inbox_sentiment", create_type=False,
)

WHATSAPP_BROADCAST_STATUS = SAEnum(
    "DRAFT", "QUEUED", "SENDING", "SENT", "FAILED",
    name="whatsapp_broadcast_status", create_type=False,
)

WHATSAPP_RECIPIENT_STATUS = SAEnum(
    "PENDING", "SENT", "DELIVERED", "READ", "FAILED",
    name="whatsapp_recipient_status", create_type=False,
)

AD_CAMPAIGN_OBJECTIVE = SAEnum(
    "AWARENESS", "TRAFFIC", "CONVERSIONS", "LEADS",
    name="ad_campaign_objective", create_type=False,
)

AD_CAMPAIGN_STATUS = SAEnum(
    "DRAFT", "ACTIVE", "PAUSED", "COMPLETED",
    name="ad_campaign_status", create_type=False,
)

COMMENT_AUTOMATION_TRIGGER = SAEnum(
    "KEYWORD", "ALL_COMMENTS", "FIRST_COMMENT",
    name="comment_automation_trigger", create_type=False,
)


# ===========================================================================
# 1. MarketingCampaign  (marketing_campaigns)
# ===========================================================================

class MarketingCampaign(Base):
    __tablename__ = "marketing_campaigns"
    __table_args__ = (
        Index("idx_marketing_campaigns_tenant_id", "tenant_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    channel: Mapped[str] = mapped_column(String(50), nullable=False, default="email")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="draft")
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    budget_zar: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    start_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    end_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    audience_segment_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True,
    )
    total_sent: Mapped[int] = mapped_column(Integer, default=0)
    total_delivered: Mapped[int] = mapped_column(Integer, default=0)
    total_opened: Mapped[int] = mapped_column(Integer, default=0)
    total_clicked: Mapped[int] = mapped_column(Integer, default=0)
    total_conversions: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    email_batches: Mapped[List["MarketingEmailBatch"]] = relationship(back_populates="campaign", lazy="selectin")
    ab_tests: Mapped[List["MarketingABTest"]] = relationship(back_populates="campaign", lazy="selectin")
    social_posts: Mapped[List["SocialPost"]] = relationship(back_populates="campaign", lazy="selectin")


# ===========================================================================
# 2. MarketingEmailBatch  (marketing_email_batches)
# ===========================================================================

class MarketingEmailBatch(Base):
    __tablename__ = "marketing_email_batches"
    __table_args__ = (
        Index("idx_marketing_email_batches_tenant_id", "tenant_id"),
        Index("idx_marketing_email_batches_campaign_id", "campaign_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("marketing_campaigns.id"), nullable=False,
    )
    subject: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    from_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    from_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    total_queued: Mapped[int] = mapped_column(Integer, default=0)
    total_sent: Mapped[int] = mapped_column(Integer, default=0)
    total_delivered: Mapped[int] = mapped_column(Integer, default=0)
    total_bounced: Mapped[int] = mapped_column(Integer, default=0)
    total_opened: Mapped[int] = mapped_column(Integer, default=0)
    total_clicked: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(30), default="queued")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    campaign: Mapped["MarketingCampaign"] = relationship(back_populates="email_batches", lazy="selectin")
    events: Mapped[List["MarketingEmailEvent"]] = relationship(back_populates="batch", lazy="selectin")


# ===========================================================================
# 3. MarketingEmailEvent  (marketing_email_events)
# ===========================================================================

class MarketingEmailEvent(Base):
    __tablename__ = "marketing_email_events"
    __table_args__ = (
        Index("idx_marketing_email_events_tenant_id", "tenant_id"),
        Index("idx_marketing_email_events_batch_id", "batch_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    batch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("marketing_email_batches.id"), nullable=False,
    )
    recipient_email: Mapped[Optional[str]] = mapped_column(String(320), nullable=True)
    event_type: Mapped[str] = mapped_column(String(30), nullable=False)
    event_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, default={})
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    batch: Mapped["MarketingEmailBatch"] = relationship(back_populates="events", lazy="selectin")


# ===========================================================================
# 4. MarketingTemplate  (marketing_templates)
# ===========================================================================

class MarketingTemplate(Base):
    __tablename__ = "marketing_templates"
    __table_args__ = (
        Index("idx_marketing_templates_tenant_id", "tenant_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    body_html: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(50), default="promotional")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


# ===========================================================================
# 5. MarketingAudienceSegment  (marketing_audience_segments)
# ===========================================================================

class MarketingAudienceSegment(Base):
    __tablename__ = "marketing_audience_segments"
    __table_args__ = (
        Index("idx_marketing_audience_segments_tenant_id", "tenant_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    rules: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, default={})
    member_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ===========================================================================
# 6. MarketingLeadScore  (marketing_lead_scores)
# ===========================================================================

class MarketingLeadScore(Base):
    __tablename__ = "marketing_lead_scores"
    __table_args__ = (
        Index("idx_marketing_lead_scores_tenant_id_contact_id", "tenant_id", "contact_id", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    contact_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    score: Mapped[int] = mapped_column(Integer, default=0)
    last_scored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ===========================================================================
# 7. MarketingAutomation  (marketing_automations)
# ===========================================================================

class MarketingAutomation(Base):
    __tablename__ = "marketing_automations"
    __table_args__ = (
        Index("idx_marketing_automations_tenant_id", "tenant_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    trigger_type: Mapped[str] = mapped_column(String(50), nullable=False)
    trigger_config: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, default={})
    actions: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(JSONB, default=[])
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    total_triggered: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ===========================================================================
# 8. MarketingABTest  (marketing_ab_tests)
# ===========================================================================

class MarketingABTest(Base):
    __tablename__ = "marketing_ab_tests"
    __table_args__ = (
        Index("idx_marketing_ab_tests_tenant_id", "tenant_id"),
        Index("idx_marketing_ab_tests_campaign_id", "campaign_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("marketing_campaigns.id"), nullable=False,
    )
    variant_a: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False)
    variant_b: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False)
    split_pct: Mapped[int] = mapped_column(Integer, default=50)
    metric: Mapped[str] = mapped_column(String(30), default="open_rate")
    duration_hours: Mapped[int] = mapped_column(Integer, default=24)
    status: Mapped[str] = mapped_column(String(30), default="running")
    winner: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    campaign: Mapped["MarketingCampaign"] = relationship(back_populates="ab_tests", lazy="selectin")


# ===========================================================================
# 9. SocialMediaAccount  (social_media_accounts)
# ===========================================================================

class SocialMediaAccount(Base):
    __tablename__ = "social_media_accounts"
    __table_args__ = (
        Index("idx_social_media_accounts_tenant_id", "tenant_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    platform: Mapped[str] = mapped_column(String(50), nullable=False)
    account_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    account_handle: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    access_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    refresh_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    token_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="ACTIVE")
    profile_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    posts: Mapped[List["SocialPost"]] = relationship(back_populates="account", lazy="selectin")
    inbox_messages: Mapped[List["SocialInboxMessage"]] = relationship(back_populates="account", lazy="selectin")
    analytics: Mapped[List["SocialAnalytics"]] = relationship(back_populates="account", lazy="selectin")
    comment_automations: Mapped[List["CommentAutomation"]] = relationship(back_populates="account", lazy="selectin")


# ===========================================================================
# 10. SocialPost  (social_posts)
# ===========================================================================

class SocialPost(Base):
    __tablename__ = "social_posts"
    __table_args__ = (
        Index("idx_social_posts_tenant_id", "tenant_id"),
        Index("idx_social_posts_account_id", "account_id"),
        Index("idx_social_posts_campaign_id", "campaign_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("social_media_accounts.id"), nullable=False,
    )
    campaign_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("marketing_campaigns.id"), nullable=True,
    )
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    media_urls: Mapped[Optional[List[str]]] = mapped_column(JSONB, nullable=True)
    platforms: Mapped[Optional[List[str]]] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="DRAFT")
    scheduled_for: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    platform_post_ids: Mapped[Optional[Dict[str, str]]] = mapped_column(JSONB, nullable=True)
    engagement_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    account: Mapped["SocialMediaAccount"] = relationship(back_populates="posts", lazy="selectin")
    campaign: Mapped[Optional["MarketingCampaign"]] = relationship(back_populates="social_posts", lazy="selectin")


# ===========================================================================
# 11. SocialInboxMessage  (social_inbox_messages)
# ===========================================================================

class SocialInboxMessage(Base):
    __tablename__ = "social_inbox_messages"
    __table_args__ = (
        Index("idx_social_inbox_messages_tenant_id", "tenant_id"),
        Index("idx_social_inbox_messages_account_id", "account_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("social_media_accounts.id"), nullable=False,
    )
    platform: Mapped[str] = mapped_column(String(50), nullable=False)
    message_type: Mapped[str] = mapped_column(String(20), nullable=False)
    external_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    sender_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    sender_handle: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    sender_profile_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    parent_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="UNREAD")
    sentiment: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    replied_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    account: Mapped["SocialMediaAccount"] = relationship(back_populates="inbox_messages", lazy="selectin")


# ===========================================================================
# 12. SocialAnalytics  (social_analytics)
# ===========================================================================

class SocialAnalytics(Base):
    __tablename__ = "social_analytics"
    __table_args__ = (
        Index("idx_social_analytics_tenant_id", "tenant_id"),
        Index("idx_social_analytics_account_id", "account_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("social_media_accounts.id"), nullable=False,
    )
    platform: Mapped[str] = mapped_column(String(50), nullable=False)
    metric_date: Mapped[date] = mapped_column(Date, nullable=False)
    followers: Mapped[int] = mapped_column(Integer, default=0)
    following: Mapped[int] = mapped_column(Integer, default=0)
    posts_count: Mapped[int] = mapped_column(Integer, default=0)
    impressions: Mapped[int] = mapped_column(Integer, default=0)
    reach: Mapped[int] = mapped_column(Integer, default=0)
    engagement_rate: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 4), nullable=True)
    likes_total: Mapped[int] = mapped_column(Integer, default=0)
    comments_total: Mapped[int] = mapped_column(Integer, default=0)
    shares_total: Mapped[int] = mapped_column(Integer, default=0)
    profile_views: Mapped[int] = mapped_column(Integer, default=0)
    website_clicks: Mapped[int] = mapped_column(Integer, default=0)
    best_post_time: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    demographics: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    account: Mapped["SocialMediaAccount"] = relationship(back_populates="analytics", lazy="selectin")


# ===========================================================================
# 13. WhatsAppContact  (whatsapp_contacts)
# ===========================================================================

class WhatsAppContact(Base):
    __tablename__ = "whatsapp_contacts"
    __table_args__ = (
        Index("idx_whatsapp_contacts_tenant_id", "tenant_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    phone_number: Mapped[str] = mapped_column(String(20), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    tags: Mapped[Optional[List[str]]] = mapped_column(JSONB, nullable=True)
    custom_fields: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    opt_in_status: Mapped[bool] = mapped_column(Boolean, default=False)
    opt_in_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_interaction_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    broadcast_recipients: Mapped[List["WhatsAppBroadcastRecipient"]] = relationship(back_populates="contact", lazy="selectin")


# ===========================================================================
# 14. WhatsAppBroadcast  (whatsapp_broadcasts)
# ===========================================================================

class WhatsAppBroadcast(Base):
    __tablename__ = "whatsapp_broadcasts"
    __table_args__ = (
        Index("idx_whatsapp_broadcasts_tenant_id", "tenant_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    template_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    media_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    recipient_count: Mapped[int] = mapped_column(Integer, default=0)
    sent_count: Mapped[int] = mapped_column(Integer, default=0)
    delivered_count: Mapped[int] = mapped_column(Integer, default=0)
    read_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="DRAFT")
    scheduled_for: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    recipients: Mapped[List["WhatsAppBroadcastRecipient"]] = relationship(back_populates="broadcast", lazy="selectin")


# ===========================================================================
# 15. WhatsAppBroadcastRecipient  (whatsapp_broadcast_recipients)
# ===========================================================================

class WhatsAppBroadcastRecipient(Base):
    __tablename__ = "whatsapp_broadcast_recipients"
    __table_args__ = (
        Index("idx_whatsapp_broadcast_recipients_tenant_id", "tenant_id"),
        Index("idx_whatsapp_broadcast_recipients_broadcast_id", "broadcast_id"),
        Index("idx_whatsapp_broadcast_recipients_contact_id", "contact_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    broadcast_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("whatsapp_broadcasts.id"), nullable=False,
    )
    contact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("whatsapp_contacts.id"), nullable=False,
    )
    phone_number: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="PENDING")
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    broadcast: Mapped["WhatsAppBroadcast"] = relationship(back_populates="recipients", lazy="selectin")
    contact: Mapped["WhatsAppContact"] = relationship(back_populates="broadcast_recipients", lazy="selectin")


# ===========================================================================
# 16. AdCampaign  (ad_campaigns)
# ===========================================================================

class AdCampaign(Base):
    __tablename__ = "ad_campaigns"
    __table_args__ = (
        Index("idx_ad_campaigns_tenant_id", "tenant_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    platform: Mapped[str] = mapped_column(String(50), nullable=False)
    objective: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="DRAFT")
    budget_zar: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    daily_budget_zar: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    start_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    end_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    targeting: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    creative: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    impressions: Mapped[int] = mapped_column(Integer, default=0)
    clicks: Mapped[int] = mapped_column(Integer, default=0)
    conversions: Mapped[int] = mapped_column(Integer, default=0)
    spend_zar: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    roas: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


# ===========================================================================
# 17. CommentAutomation  (comment_automations)
# ===========================================================================

class CommentAutomation(Base):
    __tablename__ = "comment_automations"
    __table_args__ = (
        Index("idx_comment_automations_tenant_id", "tenant_id"),
        Index("idx_comment_automations_account_id", "account_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("social_media_accounts.id"), nullable=False,
    )
    trigger_type: Mapped[str] = mapped_column(String(30), nullable=False)
    trigger_keywords: Mapped[Optional[List[str]]] = mapped_column(JSONB, nullable=True)
    response_template: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    total_triggered: Mapped[int] = mapped_column(Integer, default=0)
    total_replied: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    account: Mapped["SocialMediaAccount"] = relationship(back_populates="comment_automations", lazy="selectin")


# ===========================================================================
# 18. SocialWebhookEvent  (social_webhook_events)
# ===========================================================================

class SocialWebhookEvent(Base):
    __tablename__ = "social_webhook_events"
    __table_args__ = (
        Index("idx_social_webhook_events_tenant_id", "tenant_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    platform: Mapped[str] = mapped_column(String(50), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    processed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ===========================================================================
# 19. TraditionalMediaCampaign  (traditional_media_campaigns)
# ===========================================================================

class TraditionalMediaCampaign(Base):
    """Offline media buys: radio, billboards, airport/OOH screens."""

    __tablename__ = "traditional_media_campaigns"
    __table_args__ = (
        Index("idx_traditional_media_campaigns_tenant_id", "tenant_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    medium: Mapped[str] = mapped_column(String(30), nullable=False)  # radio, billboard, ooh_screen
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # National/Regional/Community, etc.
    reach: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # free-text: "1.2M listeners", "Western Cape"
    spots_booked: Mapped[int] = mapped_column(Integer, default=0)
    impressions: Mapped[int] = mapped_column(Integer, default=0)
    spend_zar: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    leads_generated: Mapped[int] = mapped_column(Integer, default=0)
    metrics: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)  # ctr, dwell_time, brand_recall, etc.
    period_month: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ---------------------------------------------------------------------------
# init_tables
# ---------------------------------------------------------------------------

def init_tables() -> None:
    """Create all marketing tables if they don't exist (dev convenience)."""
    from services.common.db import get_engine as _get_sync_engine

    engine = _get_sync_engine()
    Base.metadata.create_all(bind=engine)
