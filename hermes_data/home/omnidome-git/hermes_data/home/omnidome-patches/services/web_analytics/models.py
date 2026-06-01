"""Page view and session tracking for portal web analytics."""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase


class PageAnalyticsBase(DeclarativeBase):
    __abstract__ = True


class PageView(PageAnalyticsBase):
    __tablename__ = "page_views"

    id: uuid.UUID = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: str = Column(String(64), nullable=False, index=True)
    visitor_id: str = Column(String(64), nullable=False, index=True)
    tenant_id: Optional[uuid.UUID] = Column(UUID(as_uuid=True), nullable=True, index=True)

    # Page info
    url: str = Column(Text, nullable=False)
    path: str = Column(String(500), nullable=False)
    title: Optional[str] = Column(String(300), nullable=True)
    referrer: Optional[str] = Column(Text, nullable=True)

    # Device / Browser
    user_agent: Optional[str] = Column(Text, nullable=True)
    device_type: Optional[str] = Column(String(20), nullable=True)  # desktop, mobile, tablet
    browser: Optional[str] = Column(String(50), nullable=True)
    browser_version: Optional[str] = Column(String(20), nullable=True)
    os: Optional[str] = Column(String(50), nullable=True)
    os_version: Optional[str] = Column(String(20), nullable=True)
    screen_width: Optional[int] = Column(Integer, nullable=True)
    screen_height: Optional[int] = Column(Integer, nullable=True)

    # Location (from IP or geo headers)
    ip_hash: Optional[str] = Column(String(64), nullable=True)  # hashed for privacy
    country: Optional[str] = Column(String(2), nullable=True)  # ISO code
    country_name: Optional[str] = Column(String(100), nullable=True)
    region: Optional[str] = Column(String(100), nullable=True)
    city: Optional[str] = Column(String(100), nullable=True)
    latitude: Optional[float] = Column(Float, nullable=True)
    longitude: Optional[float] = Column(Float, nullable=True)

    # Engagement
    time_on_page: Optional[int] = Column(Integer, nullable=True)  # seconds
    scroll_depth: Optional[int] = Column(Integer, nullable=True)  # percentage

    # Timestamp
    created_at: datetime = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_page_views_created_at", "created_at"),
        Index("ix_page_views_path_created", "path", "created_at"),
    )


class ClickEvent(PageAnalyticsBase):
    __tablename__ = "click_events"

    id: uuid.UUID = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: str = Column(String(64), nullable=False, index=True)
    visitor_id: str = Column(String(64), nullable=False, index=True)
    page_view_id: Optional[uuid.UUID] = Column(
        UUID(as_uuid=True), ForeignKey("page_views.id", ondelete="SET NULL"), nullable=True
    )

    # Click details
    element_tag: Optional[str] = Column(String(50), nullable=True)  # button, a, input, etc.
    element_id: Optional[str] = Column(String(200), nullable=True)
    element_class: Optional[str] = Column(String(300), nullable=True)
    element_text: Optional[str] = Column(String(200), nullable=True)
    href: Optional[str] = Column(Text, nullable=True)

    # Position
    x: Optional[int] = Column(Integer, nullable=True)
    y: Optional[int] = Column(Integer, nullable=True)

    # Page context
    path: str = Column(String(500), nullable=False)

    created_at: datetime = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_click_events_created_at", "created_at"),
        Index("ix_click_events_path", "path"),
    )


class FormEvent(PageAnalyticsBase):
    __tablename__ = "form_events"

    id: uuid.UUID = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: str = Column(String(64), nullable=False, index=True)
    visitor_id: str = Column(String(64), nullable=False, index=True)
    page_view_id: Optional[uuid.UUID] = Column(
        UUID(as_uuid=True), ForeignKey("page_views.id", ondelete="SET NULL"), nullable=True
    )

    # Form details
    form_id: Optional[str] = Column(String(200), nullable=True)
    form_name: Optional[str] = Column(String(200), nullable=True)
    form_action: Optional[str] = Column(Text, nullable=True)

    # Event type: view, start, submit, abandon, validation_error
    event_type: str = Column(String(20), nullable=False)

    # Field-level tracking (which fields were interacted with)
    fields_interacted: Optional[list] = Column(JSONB, nullable=True)
    fields_count: Optional[int] = Column(Integer, nullable=True)

    # Time to complete (for submit events)
    time_to_complete: Optional[int] = Column(Integer, nullable=True)  # seconds

    # Error info
    validation_errors: Optional[list] = Column(JSONB, nullable=True)

    # Page context
    path: str = Column(String(500), nullable=False)

    created_at: datetime = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_form_events_created_at", "created_at"),
        Index("ix_form_events_event_type", "event_type"),
        Index("ix_form_events_path", "path"),
    )


class SessionTracking(PageAnalyticsBase):
    __tablename__ = "session_tracking"

    id: uuid.UUID = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: str = Column(String(64), nullable=False, unique=True, index=True)
    visitor_id: str = Column(String(64), nullable=False, index=True)
    tenant_id: Optional[uuid.UUID] = Column(UUID(as_uuid=True), nullable=True, index=True)

    # First touch
    landing_page: str = Column(Text, nullable=False)
    referrer: Optional[str] = Column(Text, nullable=True)
    utm_source: Optional[str] = Column(String(200), nullable=True)
    utm_medium: Optional[str] = Column(String(200), nullable=True)
    utm_campaign: Optional[str] = Column(String(200), nullable=True)
    utm_term: Optional[str] = Column(String(200), nullable=True)
    utm_content: Optional[str] = Column(String(200), nullable=True)

    # Device snapshot
    device_type: Optional[str] = Column(String(20), nullable=True)
    browser: Optional[str] = Column(String(50), nullable=True)
    os: Optional[str] = Column(String(50), nullable=True)
    country: Optional[str] = Column(String(2), nullable=True)
    country_name: Optional[str] = Column(String(100), nullable=True)

    # Engagement summary
    pageviews_count: int = Column(Integer, nullable=False, default=0)
    events_count: int = Column(Integer, nullable=False, default=0)
    duration_seconds: Optional[int] = Column(Integer, nullable=True)
    is_bounce: bool = Column(Boolean, nullable=False, default=True)

    # Timestamps
    started_at: datetime = Column(DateTime(timezone=True), nullable=False)
    ended_at: Optional[datetime] = Column(DateTime(timezone=True), nullable=True)
    created_at: datetime = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_session_tracking_visitor", "visitor_id"),
        Index("ix_session_tracking_started", "started_at"),
    )
