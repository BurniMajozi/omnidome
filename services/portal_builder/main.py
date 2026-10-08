"""
Portal Builder Service — Main FastAPI Application
Rapid landing page builder, campaign push engine, and SEO management.
Port: 8026 | Module: portal_builder

Security model: authenticated routes use the signed tenant identity plus role tiers (access.py);
the only unauthenticated routes are GET /public/{slug}, GET /shared/{token} and POST /submissions,
which are rate limited, serve sanitised published/shared content only, and never serve custom JS.
"""

import asyncio
import logging
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any
from urllib.parse import urlsplit

from fastapi import FastAPI, Depends, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Index, Integer, Numeric,
    String, Text, func, literal, select, update,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from services.common.entitlements import EntitlementGuard
from services.common.auth import AuthContext, get_auth_context
from services.common.db import Base, session_scope
from services.common.http_client import service_get, service_post
from services.common.middleware import add_exception_handlers
from services.common.rate_limiter import RateLimiter
from services.common import suppression
from services.portal_builder import fetcher, security, seo
from services.portal_builder.access import require_tier
from services.portal_builder.builder_ux import router as builder_ux_router
from services.portal_builder.design import router as design_router
from services.portal_builder.wordpress import router as wordpress_router

logger = logging.getLogger("portal_builder")

# ── App ────────────────────────────────────────────────────────────────

app = FastAPI(
    title="OmniDome Portal Builder",
    description="Rapid landing page builder, campaign push engine, and SEO management",
    version="2.0.0",
)

guard = EntitlementGuard(
    module_id="portal-builder",
    public_paths={"/health", "/docs", "/openapi.json", "/api/v1/portal/public", "/api/v1/portal/submissions"},
    public_prefixes=("/api/v1/portal/public", "/api/v1/portal/shared"),
)

add_exception_handlers(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:3000").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(builder_ux_router)
app.include_router(design_router)
app.include_router(wordpress_router)

# ── Rate limiters / caps (per process; tune via env) ───────────────────

def _int_env(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, default))
    except ValueError:
        return default


SUBMISSION_MAX_BYTES = _int_env("PORTAL_SUBMISSION_MAX_BYTES", 16 * 1024)
_public_limiter = RateLimiter(max_requests=_int_env("PORTAL_PUBLIC_RATE", 120), window_seconds=60)
_submit_limiter = RateLimiter(max_requests=_int_env("PORTAL_SUBMIT_RATE", 5), window_seconds=60)
_shared_limiter = RateLimiter(max_requests=_int_env("PORTAL_SHARED_RATE", 30), window_seconds=60)
_share_create_limiter = RateLimiter(max_requests=_int_env("PORTAL_SHARE_CREATE_RATE", 30), window_seconds=3600)
_fetch_limiter = RateLimiter(max_requests=_int_env("PORTAL_FETCH_RATE", 20), window_seconds=600)


@app.on_event("startup")
async def startup() -> None:
    guard.ensure_startup()
    if os.getenv("PORTAL_RUN_MIGRATIONS", "true").strip().lower() not in {"0", "false", "no", "off"}:
        from services.portal_builder.migrations import run_migrations
        await asyncio.to_thread(run_migrations)


@app.middleware("http")
async def entitlement_middleware(request, call_next):
    return await guard.middleware(request, call_next)


@app.get("/health")
async def health_check():
    return {"service": "portal-builder", "status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}


# ── Models ─────────────────────────────────────────────────────────────

class PortalPage(Base):
    __tablename__ = "portal_pages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    slug: Mapped[str] = mapped_column(String(200), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    page_type: Mapped[str] = mapped_column(String(30), nullable=False, default="landing")  # landing, campaign, product, seo
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")  # draft, published, archived
    content: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)  # page builder JSON blocks
    theme: Mapped[dict] = mapped_column(JSONB, nullable=True)  # colors, fonts, layout
    seo_meta: Mapped[dict] = mapped_column(JSONB, nullable=True)  # title, description, keywords, og tags, schema
    custom_css: Mapped[str] = mapped_column(Text, nullable=True)
    custom_js: Mapped[str] = mapped_column(Text, nullable=True)
    parent_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("portal_pages.id"), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    views: Mapped[int] = mapped_column(Integer, default=0)
    conversions: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    updated_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=True)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    unpublished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    published_version: Mapped[int] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_portal_pages_tenant_slug", "tenant_id", "slug", unique=True),
        Index("ix_portal_pages_tenant_type", "tenant_id", "page_type"),
        Index("ix_portal_pages_tenant_status", "tenant_id", "status"),
    )


class PortalPageVersion(Base):
    __tablename__ = "portal_page_versions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    page_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("portal_pages.id", ondelete="CASCADE"), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[dict] = mapped_column(JSONB, nullable=False)
    theme: Mapped[dict] = mapped_column(JSONB, nullable=True)
    seo_meta: Mapped[dict] = mapped_column(JSONB, nullable=True)
    reason: Mapped[str] = mapped_column(String(30), nullable=True)  # edit, publish
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_portal_page_versions_page", "page_id", "version_number"),
    )


class PortalSubmission(Base):
    __tablename__ = "portal_submissions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    page_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("portal_pages.id", ondelete="CASCADE"), nullable=False)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    form_data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    utm_source: Mapped[str] = mapped_column(String(100), nullable=True)
    utm_medium: Mapped[str] = mapped_column(String(100), nullable=True)
    utm_campaign: Mapped[str] = mapped_column(String(200), nullable=True)
    referrer: Mapped[str] = mapped_column(Text, nullable=True)
    ip_hash: Mapped[str] = mapped_column(String(64), nullable=True)  # hashed for POPIA
    converted: Mapped[bool] = mapped_column(Boolean, default=False)
    consent_given: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    consent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    consent_text: Mapped[str] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_portal_submissions_page", "page_id", "created_at"),
        Index("ix_portal_submissions_tenant_utm", "tenant_id", "utm_campaign"),
    )


class PortalSeoProfile(Base):
    __tablename__ = "portal_seo_profiles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    target_keywords: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    sitemap_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    robots_txt: Mapped[str] = mapped_column(Text, nullable=True)
    structured_data: Mapped[dict] = mapped_column(JSONB, nullable=True)  # JSON-LD
    analytics_id: Mapped[str] = mapped_column(String(100), nullable=True)
    search_console_id: Mapped[str] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_portal_seo_tenant", "tenant_id"),
    )


class PortalCampaign(Base):
    __tablename__ = "portal_campaigns"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    page_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("portal_pages.id"), nullable=True)
    campaign_type: Mapped[str] = mapped_column(String(30), nullable=False, default="email")  # email, social, paid, mixed
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    target_segment: Mapped[dict] = mapped_column(JSONB, nullable=True)  # audience filters
    schedule: Mapped[dict] = mapped_column(JSONB, nullable=True)  # send time, recurrence
    content: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)  # emails, ads, social posts
    stats: Mapped[dict] = mapped_column(JSONB, nullable=True)  # sends, opens, clicks, conversions, revenue
    budget_zar: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    spent_zar: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_portal_campaigns_tenant", "tenant_id", "status"),
        Index("ix_portal_campaigns_page", "page_id"),
    )


class PortalPageView(Base):
    """One row per public page view (real analytics source; IPs are stored only as keyed hashes)."""
    __tablename__ = "portal_page_views"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    page_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("portal_pages.id", ondelete="CASCADE"), nullable=False)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    ip_hash: Mapped[str] = mapped_column(String(64), nullable=True)
    referrer_host: Mapped[str] = mapped_column(String(200), nullable=True)
    utm_source: Mapped[str] = mapped_column(String(100), nullable=True)
    utm_medium: Mapped[str] = mapped_column(String(100), nullable=True)
    utm_campaign: Mapped[str] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_portal_page_views_tenant_created", "tenant_id", "created_at"),
        Index("ix_portal_page_views_page_created", "page_id", "created_at"),
    )


class PortalPageShare(Base):
    """Expiring, revocable read-only preview link. Only the SHA-256 of the token is stored."""
    __tablename__ = "portal_page_shares"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    page_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("portal_pages.id", ondelete="CASCADE"), nullable=False)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    recipient_email: Mapped[str] = mapped_column(String(320), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    email_status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")  # pending, sent, failed, suppressed, no_mailbox
    message_id: Mapped[str] = mapped_column(String(200), nullable=True)
    view_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_viewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_portal_page_shares_page", "page_id", "created_at"),
    )


# ── Schemas ────────────────────────────────────────────────────────────

class PageCreate(BaseModel):
    slug: str = Field(..., min_length=1, max_length=100, description="URL slug, lowercase a-z 0-9 and hyphens, e.g. 'fibre-promo-q3'")
    title: str = Field(..., min_length=1, max_length=300)
    description: Optional[str] = Field(None, max_length=2000)
    page_type: str = "landing"
    content: Dict[str, Any] = Field(default_factory=dict)
    theme: Optional[Dict[str, Any]] = None
    seo_meta: Optional[Dict[str, Any]] = None


class PageUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    content: Optional[Dict[str, Any]] = None
    theme: Optional[Dict[str, Any]] = None
    seo_meta: Optional[Dict[str, Any]] = None
    custom_css: Optional[str] = None
    custom_js: Optional[str] = None
    status: Optional[str] = None


class PageRead(BaseModel):
    class Config:
        from_attributes = True
    id: uuid.UUID
    tenant_id: uuid.UUID
    slug: str
    title: str
    description: Optional[str]
    page_type: str
    status: str
    content: Dict[str, Any]
    theme: Optional[Dict[str, Any]]
    seo_meta: Optional[Dict[str, Any]]
    views: int
    conversions: int
    sort_order: int
    custom_css: Optional[str] = None
    published_version: Optional[int] = None
    published_at: Optional[datetime]
    unpublished_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class PageListItem(BaseModel):
    class Config:
        from_attributes = True
    id: uuid.UUID
    slug: str
    title: str
    page_type: str
    status: str
    views: int
    conversions: int
    updated_at: datetime


class CampaignCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=300)
    page_id: Optional[uuid.UUID] = None
    campaign_type: str = "email"
    target_segment: Optional[Dict[str, Any]] = None
    schedule: Optional[Dict[str, Any]] = None
    content: Dict[str, Any] = Field(default_factory=dict)
    budget_zar: float = Field(0, ge=0, allow_inf_nan=False)


class CampaignUpdate(BaseModel):
    name: Optional[str] = None
    content: Optional[Dict[str, Any]] = None
    target_segment: Optional[Dict[str, Any]] = None
    schedule: Optional[Dict[str, Any]] = None
    status: Optional[str] = None
    budget_zar: Optional[float] = None


class CampaignRead(BaseModel):
    class Config:
        from_attributes = True
    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    page_id: Optional[uuid.UUID]
    campaign_type: str
    status: str
    stats: Optional[Dict[str, Any]]
    budget_zar: float
    spent_zar: float
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    created_at: datetime


class SeoProfileCreate(BaseModel):
    name: str
    target_keywords: List[str] = Field(default_factory=list)
    sitemap_enabled: bool = True
    robots_txt: Optional[str] = None
    structured_data: Optional[Dict[str, Any]] = None
    analytics_id: Optional[str] = None


class SeoProfileRead(BaseModel):
    class Config:
        from_attributes = True
    id: uuid.UUID
    name: str
    target_keywords: List[str]
    sitemap_enabled: bool
    robots_txt: Optional[str]
    structured_data: Optional[Dict[str, Any]]
    analytics_id: Optional[str]
    updated_at: datetime


class SubmissionCreate(BaseModel):
    page_id: Optional[uuid.UUID] = None
    slug: Optional[str] = Field(None, max_length=100)
    form_data: Dict[str, Any] = Field(default_factory=dict)
    consent: bool = False
    consent_text: Optional[str] = Field(None, max_length=500)
    website: Optional[str] = Field(None, max_length=500, description="Honeypot: real users leave this empty")
    utm_source: Optional[str] = Field(None, max_length=100)
    utm_medium: Optional[str] = Field(None, max_length=100)
    utm_campaign: Optional[str] = Field(None, max_length=200)
    referrer: Optional[str] = Field(None, max_length=1000)


class ShareCreate(BaseModel):
    recipient_email: str = Field(..., max_length=320)
    expires_in_hours: int = Field(168, ge=1, le=720)
    message: Optional[str] = Field(None, max_length=500)


class ImportSiteRequest(BaseModel):
    url: str = Field(..., min_length=8, max_length=2000)


class SeoAuditRequest(BaseModel):
    url: str = Field(..., min_length=8, max_length=2000)
    keyword: Optional[str] = Field(None, max_length=100)


class KeywordRequest(BaseModel):
    keywords: List[str] = Field(..., min_length=1, max_length=50)


class PageAnalytics(BaseModel):
    page_id: uuid.UUID
    views: int
    unique_visitors: int
    submissions: int
    conversions: int
    conversion_rate: float
    avg_time_on_page: float
    top_sources: Dict[str, int]
    top_keywords: Dict[str, int]
    daily_views: List[Dict[str, Any]]


# ── Helpers ────────────────────────────────────────────────────────────

PREFIX = "/api/v1/portal"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


async def _get_page(session, page_id: uuid.UUID, tenant_id: uuid.UUID, *, lock: bool = False) -> PortalPage:
    q = select(PortalPage).where(PortalPage.id == page_id, PortalPage.tenant_id == tenant_id)
    if lock:
        q = q.with_for_update()
    page = (await session.execute(q)).scalars().first()
    if not page:
        raise HTTPException(404, "Page not found")
    return page


async def _resolve_published(session, slug: str) -> Optional[PortalPage]:
    """Resolve a public slug. Published pages only; ambiguity (two tenants publishing the same slug
    from before the unique index existed) resolves to nothing rather than to an arbitrary tenant."""
    if not security.SLUG_RE.fullmatch(slug.lower()):
        return None
    rows = (await session.execute(
        select(PortalPage).where(func.lower(PortalPage.slug) == slug.lower(), PortalPage.status == "published").limit(2)
    )).scalars().all()
    return rows[0] if len(rows) == 1 else None


def _public_payload(page: PortalPage, *, preview: bool = False) -> dict:
    """The only shape ever served unauthenticated. custom_js is intentionally never included."""
    return {
        "id": str(page.id), "slug": page.slug, "title": page.title,
        "description": security.sanitize_html(page.description or "") or None,
        "page_type": page.page_type,
        "content": security.sanitize_content(page.content or {}),
        "theme": security.sanitize_content(page.theme) if page.theme else None,
        "seo_meta": security.sanitize_content(page.seo_meta) if page.seo_meta else None,
        "custom_css": security.sanitize_css(page.custom_css),
        "published_at": page.published_at.isoformat() if page.published_at else None,
        "preview": preview,
    }


async def _published_payload(session, page: PortalPage) -> dict:
    payload = _public_payload(page)
    if page.published_version is None:
        return payload  # legacy publication: freeze it on its next edit
    version = await session.scalar(select(PortalPageVersion).where(
        PortalPageVersion.page_id == page.id, PortalPageVersion.tenant_id == page.tenant_id,
        PortalPageVersion.version_number == page.published_version))
    if version is None:
        raise HTTPException(404, "Published version not found")
    content = dict(version.content or {})
    metadata = content.pop("_publication", None)
    payload.update(content=security.sanitize_content(content), theme=security.sanitize_content(version.theme),
                   seo_meta=security.sanitize_content(version.seo_meta))
    if isinstance(metadata, dict):
        payload.update(title=security.sanitize_html(metadata.get("title") or ""),
                       description=security.sanitize_html(metadata.get("description") or "") or None,
                       custom_css=security.sanitize_css(metadata.get("custom_css")))
    return payload


def _public_headers(*, noindex: bool = False) -> dict:
    h = {
        "Content-Security-Policy": security.PUBLIC_CSP,
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer" if noindex else "strict-origin-when-cross-origin",
        "Cache-Control": "no-store" if noindex else "no-cache",
    }
    if noindex:
        h["X-Robots-Tag"] = "noindex, nofollow"
    return h


def _validate_page_inputs(*, content=None, theme=None, seo_meta=None) -> None:
    import json
    for name, val in (("content", content), ("theme", theme), ("seo_meta", seo_meta)):
        if val is not None and len(json.dumps(val, default=str)) > security.MAX_CONTENT_BYTES:
            raise HTTPException(413, f"{name} is too large")


async def _next_version(session, page_id: uuid.UUID) -> int:
    current = await session.scalar(
        select(func.max(PortalPageVersion.version_number)).where(PortalPageVersion.page_id == page_id)
    )
    return (current or 0) + 1


async def _snapshot(session, page: PortalPage, user_id: uuid.UUID, reason: str) -> int:
    """Versioned snapshot. Callers hold the page row lock, so max()+1 cannot race."""
    n = await _next_version(session, page.id)
    session.add(PortalPageVersion(
        page_id=page.id, tenant_id=page.tenant_id, version_number=n,
        content={**(page.content or {}), "_publication": {"title": page.title, "description": page.description, "custom_css": page.custom_css}}, theme=page.theme,
        seo_meta=page.seo_meta, reason=reason, created_by=user_id,
    ))
    return n


# ── Page Builder Routes ────────────────────────────────────────────────

@app.post(f"{PREFIX}/pages", response_model=PageRead, status_code=status.HTTP_201_CREATED,
          dependencies=[Depends(require_tier("write"))])
async def create_page(body: PageCreate, ctx: AuthContext = Depends(get_auth_context)):
    try:
        slug = security.normalize_slug(body.slug)
    except security.SlugError as exc:
        raise HTTPException(422, str(exc))
    if body.page_type not in security.PAGE_TYPES:
        raise HTTPException(422, f"page_type must be one of {sorted(security.PAGE_TYPES)}")
    _validate_page_inputs(content=body.content, theme=body.theme, seo_meta=body.seo_meta)
    async with session_scope() as session:
        exists = await session.scalar(select(func.count()).select_from(PortalPage).where(
            PortalPage.tenant_id == ctx.tenant_id, PortalPage.slug == slug))
        if exists:
            raise HTTPException(409, "A page with this slug already exists")
        page = PortalPage(
            tenant_id=ctx.tenant_id, slug=slug, title=body.title,
            description=body.description, page_type=body.page_type,
            content=security.sanitize_content(body.content),
            theme=security.sanitize_content(body.theme) if body.theme else None,
            seo_meta=security.sanitize_content(body.seo_meta) if body.seo_meta else None,
            created_by=ctx.user_id,
        )
        session.add(page)
        try:
            await session.flush()
        except IntegrityError:
            raise HTTPException(409, "A page with this slug already exists")
        await session.refresh(page)
        return PageRead.model_validate(page)


@app.get(f"{PREFIX}/pages")
async def list_pages(
    ctx: AuthContext = Depends(get_auth_context),
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    page_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None, max_length=100),
):
    async with session_scope() as session:
        query = select(PortalPage).where(PortalPage.tenant_id == ctx.tenant_id)
        if page_type:
            query = query.where(PortalPage.page_type == page_type)
        if status:
            query = query.where(PortalPage.status == status)
        if search:
            like = "%" + search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            query = query.where(
                PortalPage.title.ilike(like, escape="\\") | PortalPage.slug.ilike(like, escape="\\")
            )
        total = await session.scalar(select(func.count()).select_from(query.subquery()))
        items = (await session.execute(
            query.order_by(PortalPage.updated_at.desc()).offset((page - 1) * page_size).limit(page_size)
        )).scalars().all()
        return {
            "items": [PageListItem.model_validate(i) for i in items],
            "total": total or 0, "page": page, "page_size": page_size,
            "pages": max(1, ((total or 0) + page_size - 1) // page_size),
        }


@app.get(f"{PREFIX}/pages/{{page_id}}", response_model=PageRead)
async def get_page(page_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context)):
    async with session_scope() as session:
        page = await _get_page(session, page_id, ctx.tenant_id)
        return PageRead.model_validate(page)


@app.get(f"{PREFIX}/public/{{slug}}")
async def get_public_page(slug: str, request: Request):
    """Serve a published page publicly (no auth): sanitised JSON, strict CSP, no custom JS."""
    ip = security.client_ip(request)
    _public_limiter.check_key("pub:" + ip)
    async with session_scope() as session:
        page = await _resolve_published(session, slug)
        if not page:
            raise HTTPException(404, "Page not found")
        q = request.query_params
        ref_host = (urlsplit(request.headers.get("referer") or "").hostname or "")[:200] or None
        session.add(PortalPageView(
            page_id=page.id, tenant_id=page.tenant_id, ip_hash=security.hash_ip(ip), referrer_host=ref_host,
            utm_source=(q.get("utm_source") or None) and q.get("utm_source")[:100],
            utm_medium=(q.get("utm_medium") or None) and q.get("utm_medium")[:100],
            utm_campaign=(q.get("utm_campaign") or None) and q.get("utm_campaign")[:200],
            created_at=_now(),
        ))
        await session.execute(update(PortalPage).where(PortalPage.id == page.id).values(views=PortalPage.views + 1))
        payload = await _published_payload(session, page)
    return JSONResponse(payload, headers=_public_headers())


@app.put(f"{PREFIX}/pages/{{page_id}}", response_model=PageRead, dependencies=[Depends(require_tier("write"))])
async def update_page(page_id: uuid.UUID, body: PageUpdate, ctx: AuthContext = Depends(get_auth_context)):
    update_data = body.model_dump(exclude_unset=True)
    if update_data.get("custom_js"):
        raise HTTPException(422, "Custom JavaScript is not supported")
    update_data.pop("custom_js", None)
    new_status = update_data.pop("status", None)
    if new_status is not None and new_status not in ("draft", "archived"):
        raise HTTPException(422, "status can only be set to draft or archived here; use POST /pages/{id}/publish to publish")
    _validate_page_inputs(content=update_data.get("content"), theme=update_data.get("theme"),
                          seo_meta=update_data.get("seo_meta"))
    for key in ("title",):
        if key in update_data and not (update_data[key] or "").strip():
            raise HTTPException(422, f"{key} cannot be empty")
    async with session_scope() as session:
        page = await _get_page(session, page_id, ctx.tenant_id, lock=True)
        if page.status == "published":
            prior = await session.scalar(select(PortalPageVersion).where(
                PortalPageVersion.page_id == page.id, PortalPageVersion.tenant_id == page.tenant_id,
                PortalPageVersion.version_number == page.published_version)) if page.published_version is not None else None
            if prior is None or not isinstance((prior.content or {}).get("_publication"), dict):
                page.published_version = await _snapshot(session, page, ctx.user_id, "publish")
        for k, v in update_data.items():
            if k in ("content",):
                v = security.sanitize_content(v or {})
            elif k in ("theme", "seo_meta"):
                v = security.sanitize_content(v) if v else None
            elif k == "custom_css":
                v = security.sanitize_css(v) or None
            setattr(page, k, v)
        if new_status is not None and new_status != page.status:
            if page.status == "published":
                page.unpublished_at = _now()
            page.status = new_status
        page.updated_by = ctx.user_id
        await _snapshot(session, page, ctx.user_id, "edit")
        await session.flush()
        await session.refresh(page)
        return PageRead.model_validate(page)


@app.get(f"{PREFIX}/pages/{{page_id}}/versions")
async def list_versions(page_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context)):
    async with session_scope() as session:
        page = await _get_page(session, page_id, ctx.tenant_id)
        rows = (await session.execute(
            select(PortalPageVersion).where(PortalPageVersion.page_id == page.id)
            .order_by(PortalPageVersion.version_number.desc(), PortalPageVersion.created_at.desc()).limit(200)
        )).scalars().all()
        return {"published_version": page.published_version, "items": [
            {"id": str(v.id), "version_number": v.version_number, "reason": v.reason,
             "created_at": v.created_at.isoformat() if v.created_at else None} for v in rows]}


@app.post(f"{PREFIX}/pages/{{page_id}}/publish", dependencies=[Depends(require_tier("manager"))])
async def publish_page(page_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context)):
    async with session_scope() as session:
        page = await _get_page(session, page_id, ctx.tenant_id, lock=True)
        clash = await session.scalar(select(func.count()).select_from(PortalPage).where(
            func.lower(PortalPage.slug) == page.slug.lower(), PortalPage.status == "published",
            PortalPage.id != page.id).execution_options(include_all_tenants=True))  # slugs are global: see across tenants
        if clash:
            raise HTTPException(409, "Another published page already uses this slug; choose a different slug")
        version = await _snapshot(session, page, ctx.user_id, "publish")
        page.status = "published"
        page.published_at = _now()
        page.unpublished_at = None
        page.published_version = version
        page.updated_by = ctx.user_id
        try:
            await session.flush()
        except IntegrityError:
            raise HTTPException(409, "Another published page already uses this slug; choose a different slug")
        return {"status": "published", "url": f"/portal/{page.slug}", "public_path": f"{PREFIX}/public/{page.slug}",
                "version": version, "published_at": page.published_at.isoformat()}


@app.post(f"{PREFIX}/pages/{{page_id}}/unpublish", dependencies=[Depends(require_tier("manager"))])
async def unpublish_page(page_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context)):
    async with session_scope() as session:
        page = await _get_page(session, page_id, ctx.tenant_id, lock=True)
        if page.status != "published":
            raise HTTPException(409, "Page is not published")
        page.status = "draft"
        page.unpublished_at = _now()
        page.updated_by = ctx.user_id
        await session.flush()
        return {"status": "draft", "unpublished_at": page.unpublished_at.isoformat()}


@app.delete(f"{PREFIX}/pages/{{page_id}}", dependencies=[Depends(require_tier("manager"))])
async def delete_page(page_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context)):
    async with session_scope() as session:
        page = await _get_page(session, page_id, ctx.tenant_id, lock=True)
        from services.portal_builder.wordpress import WordPressPageLink
        pending = await session.scalar(select(WordPressPageLink.id).where(
            WordPressPageLink.page_id == page_id, WordPressPageLink.tenant_id == ctx.tenant_id,
            WordPressPageLink.pending_job.is_not(None)))
        if pending:
            raise HTTPException(409, "Refresh pending WordPress publication status before deleting this page")
        await session.delete(page)
        try:
            await session.flush()
        except IntegrityError:
            raise HTTPException(409, "Page is referenced by campaigns or child pages; detach them first")
        return {"status": "deleted"}


# ── Share links ────────────────────────────────────────────────────────

def _share_url(token: str) -> str:
    base = os.getenv("PORTAL_BASE_URL", "https://omnidome.co.za").rstrip("/")
    return f"{base}/portal/shared/{token}"


async def _send_share_email(tenant_id, user_id, to: str, page: PortalPage, url: str, expires_at: datetime,
                            message: Optional[str]) -> tuple[str, Optional[str]]:
    """Send via the Communication service. Returns (email_status, message_id)."""
    try:
        mailboxes = await service_get("communication", "/api/v1/mail/mailboxes", tenant_id=tenant_id, user_id=user_id)
    except Exception:
        return "failed", None
    active = [m for m in mailboxes if m.get("is_active", True)] if isinstance(mailboxes, list) else []
    wanted = os.getenv("PORTAL_SHARE_MAILBOX_ID", "").strip()
    if wanted:
        active = [m for m in active if str(m.get("id")) == wanted]
    if len(active) != 1:
        return "no_mailbox", None
    lines = [f"A page preview has been shared with you: {page.title}", ""]
    if message:
        lines += [message, ""]
    lines += [f"View it here: {url}", "", f"This link is read-only and expires {expires_at.strftime('%Y-%m-%d %H:%M UTC')}."]
    body = {"mailbox_id": active[0]["id"], "to": [to], "subject": f"Preview: {page.title}"[:200],
            "body_text": "\n".join(lines)}
    try:
        delivery = await service_post("communication", "/api/v1/mail/send", json=body,
                                      tenant_id=tenant_id, user_id=user_id, timeout=30, retries=0)
    except Exception:
        return "failed", None
    if isinstance(delivery, dict) and delivery.get("status") == "sent":
        return "sent", str(delivery.get("message_id") or "")[:200] or None
    return "failed", None


@app.post(f"{PREFIX}/pages/{{page_id}}/share", status_code=status.HTTP_201_CREATED,
          dependencies=[Depends(require_tier("manager"))])
async def share_page(page_id: uuid.UUID, body: ShareCreate, ctx: AuthContext = Depends(get_auth_context)):
    email = suppression.normalize_email(body.recipient_email)
    if not security.EMAIL_RE.fullmatch(email) or len(email) > 320:
        raise HTTPException(422, "recipient_email is not a valid email address")
    _share_create_limiter.check_key(f"share:{ctx.user_id}")
    token = secrets.token_urlsafe(32)
    expires_at = _now() + timedelta(hours=body.expires_in_hours)
    async with session_scope() as session:
        page = await _get_page(session, page_id, ctx.tenant_id)
        allowed, suppressed = await suppression.filter_suppressed(session, ctx.tenant_id, [email])
        share = PortalPageShare(
            page_id=page.id, tenant_id=ctx.tenant_id, token_hash=security.hash_token(token),
            recipient_email=email, expires_at=expires_at, created_by=ctx.user_id,
            email_status="suppressed" if suppressed else "pending", view_count=0,
        )
        session.add(share)
        await session.commit()  # persist the link before any outbound I/O
        message_id = None
        if not suppressed:
            share.email_status, message_id = await _send_share_email(
                ctx.tenant_id, ctx.user_id, email, page, _share_url(token), expires_at, body.message)
            share.message_id = message_id
            await session.flush()
        return {"id": str(share.id), "page_id": str(page.id), "recipient_email": email,
                "expires_at": expires_at.isoformat(), "share_url": _share_url(token),
                "email_status": share.email_status, "message_id": message_id}


@app.get(f"{PREFIX}/pages/{{page_id}}/shares", dependencies=[Depends(require_tier("manager"))])
async def list_shares(page_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context)):
    async with session_scope() as session:
        page = await _get_page(session, page_id, ctx.tenant_id)
        rows = (await session.execute(
            select(PortalPageShare).where(PortalPageShare.page_id == page.id, PortalPageShare.tenant_id == ctx.tenant_id)
            .order_by(PortalPageShare.created_at.desc()).limit(200))).scalars().all()
        now = _now()
        return {"items": [{
            "id": str(s.id), "recipient_email": s.recipient_email, "expires_at": s.expires_at.isoformat(),
            "revoked_at": s.revoked_at.isoformat() if s.revoked_at else None,
            "active": s.revoked_at is None and _aware(s.expires_at) > now,
            "email_status": s.email_status, "view_count": s.view_count,
            "last_viewed_at": s.last_viewed_at.isoformat() if s.last_viewed_at else None,
            "created_at": s.created_at.isoformat() if s.created_at else None} for s in rows]}


@app.post(f"{PREFIX}/shares/{{share_id}}/revoke", dependencies=[Depends(require_tier("manager"))])
async def revoke_share(share_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context)):
    async with session_scope() as session:
        share = (await session.execute(select(PortalPageShare).where(
            PortalPageShare.id == share_id, PortalPageShare.tenant_id == ctx.tenant_id))).scalars().first()
        if not share:
            raise HTTPException(404, "Share not found")
        if share.revoked_at is None:
            share.revoked_at = _now()
        await session.flush()
        return {"status": "revoked", "id": str(share.id), "revoked_at": share.revoked_at.isoformat()}


@app.get(f"{PREFIX}/shared/{{token}}")
async def get_shared_page(token: str, request: Request):
    """Read-only preview via an unguessable, expiring token. Works for drafts; never indexed."""
    _shared_limiter.check_key("shared:" + security.client_ip(request))
    if not (20 <= len(token) <= 128):
        raise HTTPException(404, "Link not found or expired")
    async with session_scope() as session:
        share = (await session.execute(select(PortalPageShare).where(
            PortalPageShare.token_hash == security.hash_token(token)))).scalars().first()
        if not share or share.revoked_at is not None or _aware(share.expires_at) <= _now():
            raise HTTPException(404, "Link not found or expired")
        page = await session.get(PortalPage, share.page_id)
        if not page or page.tenant_id != share.tenant_id:
            raise HTTPException(404, "Link not found or expired")
        share.view_count = (share.view_count or 0) + 1
        share.last_viewed_at = _now()
        payload = _public_payload(page, preview=True)
        payload["expires_at"] = share.expires_at.isoformat()
    return JSONResponse(payload, headers=_public_headers(noindex=True))


# ── Submissions ────────────────────────────────────────────────────────

def _clean_form_data(data: Dict[str, Any]) -> Dict[str, Any]:
    if len(data) > 40:
        raise HTTPException(422, "Too many form fields")
    out: Dict[str, Any] = {}
    for k, v in data.items():
        if not isinstance(k, str) or not k or len(k) > 64:
            raise HTTPException(422, "Invalid form field name")
        if isinstance(v, str):
            if len(v) > 2000:
                raise HTTPException(422, f"Field '{k[:30]}' is too long")
            v = security.sanitize_html(v)
        elif not (v is None or isinstance(v, (bool, int, float))):
            raise HTTPException(422, f"Field '{k[:30]}' must be a simple value")
        out[k] = v
    return out


async def _read_capped(request: Request, limit: int) -> bytes:
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > limit:
        raise HTTPException(413, "Request body too large")
    buf = bytearray()
    async for chunk in request.stream():
        buf.extend(chunk)
        if len(buf) > limit:
            raise HTTPException(413, "Request body too large")
    return bytes(buf)


@app.post(f"{PREFIX}/submissions")
async def submit_form(request: Request):
    """Public form submission (no auth). Rate limited per IP+page, size capped, consent required, honeypot."""
    ip = security.client_ip(request)
    raw = await _read_capped(request, SUBMISSION_MAX_BYTES)
    try:
        body = SubmissionCreate.model_validate_json(raw)
    except ValidationError:
        raise HTTPException(422, "Invalid submission")
    if not body.page_id and not body.slug:
        raise HTTPException(422, "page_id or slug is required")
    _submit_limiter.check_key(f"submit:{ip}:{body.page_id or (body.slug or '').lower()}")
    hp_names = ("website", "_hp", "hp", "url_confirm")
    if (body.website or "").strip() or any(str(body.form_data.get(n) or "").strip() for n in hp_names):
        return {"status": "submitted"}  # honeypot tripped: pretend success, store nothing
    if body.consent is not True:
        raise HTTPException(422, "Consent is required to submit this form")
    form_data = _clean_form_data({k: v for k, v in body.form_data.items() if k not in hp_names})
    async with session_scope() as session:
        if body.page_id:
            page = await session.get(PortalPage, body.page_id)
            if page is not None and page.status != "published":
                page = None
        else:
            page = await _resolve_published(session, body.slug or "")
        if not page:
            raise HTTPException(404, "Page not found")
        submission = PortalSubmission(
            page_id=page.id, tenant_id=page.tenant_id, form_data=form_data,
            utm_source=body.utm_source, utm_medium=body.utm_medium, utm_campaign=body.utm_campaign,
            referrer=body.referrer, ip_hash=security.hash_ip(ip), consent_given=True, consent_at=_now(),
            consent_text=body.consent_text,
        )
        session.add(submission)
        await session.execute(update(PortalPage).where(PortalPage.id == page.id).values(conversions=PortalPage.conversions + 1))
        await session.flush()
        return {"status": "submitted", "id": str(submission.id)}


@app.get(f"{PREFIX}/pages/{{page_id}}/submissions", dependencies=[Depends(require_tier("write"))])
async def get_submissions(
    page_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context),
    page_num: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
):
    async with session_scope() as session:
        query = select(PortalSubmission).where(
            PortalSubmission.page_id == page_id, PortalSubmission.tenant_id == ctx.tenant_id
        )
        total = await session.scalar(select(func.count()).select_from(query.subquery()))
        items = (await session.execute(
            query.order_by(PortalSubmission.created_at.desc()).offset((page_num - 1) * page_size).limit(page_size)
        )).scalars().all()
        return {
            "items": [{"id": str(s.id), "form_data": s.form_data, "utm": {"source": s.utm_source, "medium": s.utm_medium, "campaign": s.utm_campaign}, "converted": s.converted, "consent_given": s.consent_given, "created_at": s.created_at.isoformat()} for s in items],
            "total": total or 0,
        }


# ── Site import / SEO audit (SSRF-safe fetch) ──────────────────────────

async def _safe_fetch(url: str, ctx: AuthContext) -> "fetcher.FetchResult":
    _fetch_limiter.check_key(f"fetch:{ctx.user_id}")
    try:
        return await fetcher.fetch_html(url)
    except fetcher.FetchError as exc:
        raise HTTPException(exc.status_code, exc.message)


@app.post(f"{PREFIX}/import/site", dependencies=[Depends(require_tier("write"))])
async def import_site(body: ImportSiteRequest, ctx: AuthContext = Depends(get_auth_context)):
    """Fetch a public page and return sanitised, structured content (no raw HTML or script). Nothing is saved."""
    res = await _safe_fetch(body.url, ctx)
    structured = fetcher.to_structured(fetcher.extract(res.html), res.final_url)
    return {
        "source_url": res.requested_url, "final_url": res.final_url,
        "fetch": {"status_code": res.status_code, "content_type": res.content_type, "truncated": res.truncated,
                  "redirects": res.redirects, "elapsed_ms": res.elapsed_ms},
        "content": structured,
        "suggested_page": {"title": structured["title"][:300], "description": structured["description"][:2000],
                           "content": {"blocks": structured["blocks"]}},
    }


@app.post(f"{PREFIX}/seo/audit", dependencies=[Depends(require_tier("write"))])
async def seo_audit(body: SeoAuditRequest, ctx: AuthContext = Depends(get_auth_context)):
    res = await _safe_fetch(body.url, ctx)
    result = seo.audit(fetcher.extract(res.html), res.final_url, body.keyword)
    result["fetch"] = {"status_code": res.status_code, "truncated": res.truncated, "redirects": res.redirects,
                       "elapsed_ms": res.elapsed_ms}
    return result


@app.post(f"{PREFIX}/seo/keywords", dependencies=[Depends(require_tier("write"))])
async def seo_keywords(body: KeywordRequest, ctx: AuthContext = Depends(get_auth_context)):
    """Volume/CPC only when SEO_PROVIDER_API_KEY is configured; otherwise {provider_configured: false}."""
    kws = [k.strip() for k in body.keywords if k and k.strip()][:50]
    return await seo.keyword_metrics(kws)


# ── Analytics (real counts from views/submissions) ─────────────────────

@app.get(f"{PREFIX}/analytics/summary")
async def analytics_summary(ctx: AuthContext = Depends(get_auth_context), days: int = Query(30, ge=1, le=365)):
    since = _now() - timedelta(days=days)
    tid = ctx.tenant_id
    async with session_scope() as session:
        status_rows = (await session.execute(
            select(PortalPage.status, func.count()).where(PortalPage.tenant_id == tid).group_by(PortalPage.status)
        )).all()
        by_status = {s: c for s, c in status_rows}
        views, unique = (await session.execute(
            select(func.count(), func.count(func.distinct(PortalPageView.ip_hash))).where(
                PortalPageView.tenant_id == tid, PortalPageView.created_at >= since))).one()
        subs = await session.scalar(select(func.count()).select_from(PortalSubmission).where(
            PortalSubmission.tenant_id == tid, PortalSubmission.created_at >= since)) or 0

        day_views = {str(d): c for d, c in (await session.execute(
            select(func.date(PortalPageView.created_at), func.count()).where(
                PortalPageView.tenant_id == tid, PortalPageView.created_at >= since)
            .group_by(func.date(PortalPageView.created_at)))).all()}
        day_subs = {str(d): c for d, c in (await session.execute(
            select(func.date(PortalSubmission.created_at), func.count()).where(
                PortalSubmission.tenant_id == tid, PortalSubmission.created_at >= since)
            .group_by(func.date(PortalSubmission.created_at)))).all()}
        daily = []
        start = since.date()
        for i in range(days + 1):
            d = str(start + timedelta(days=i))
            daily.append({"date": d, "views": day_views.get(d, 0), "submissions": day_subs.get(d, 0)})

        top_pages = (await session.execute(
            select(PortalPage.id, PortalPage.slug, PortalPage.title, func.count(PortalPageView.id).label("v"))
            .join(PortalPageView, PortalPageView.page_id == PortalPage.id)
            .where(PortalPageView.tenant_id == tid, PortalPageView.created_at >= since)
            .group_by(PortalPage.id, PortalPage.slug, PortalPage.title)
            .order_by(func.count(PortalPageView.id).desc()).limit(5))).all()
        src_expr = func.coalesce(PortalPageView.utm_source, PortalPageView.referrer_host, "direct")
        sources = (await session.execute(
            select(src_expr, func.count()).where(PortalPageView.tenant_id == tid, PortalPageView.created_at >= since)
            .group_by(src_expr).order_by(func.count().desc()).limit(10))).all()
        campaigns = (await session.execute(
            select(PortalCampaign.status, func.count()).where(PortalCampaign.tenant_id == tid)
            .group_by(PortalCampaign.status))).all()
        camp = {s: c for s, c in campaigns}
    return {
        "period_days": days, "since": since.isoformat(),
        "pages": {"total": sum(by_status.values()), "published": by_status.get("published", 0),
                  "draft": by_status.get("draft", 0), "archived": by_status.get("archived", 0)},
        "views": views, "unique_visitors": unique, "submissions": subs,
        "conversion_rate": round(subs / views * 100, 2) if views else 0.0,
        "daily": daily,
        "top_pages": [{"page_id": str(i), "slug": s, "title": t, "views": v} for i, s, t, v in top_pages],
        "top_sources": [{"source": s, "views": c} for s, c in sources],
        "campaigns": {"total": sum(camp.values()), "running": camp.get("running", 0)},
    }


# ── Campaign Routes ────────────────────────────────────────────────────

@app.post("/api/v1/portal/campaigns", response_model=CampaignRead, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_tier("write"))])
async def create_campaign(body: CampaignCreate, ctx: AuthContext = Depends(get_auth_context)):
    async with session_scope() as session:
        if body.page_id:
            page = (await session.execute(select(PortalPage.id).where(
                PortalPage.id == body.page_id, PortalPage.tenant_id == ctx.tenant_id,
            ))).scalar_one_or_none()
            if not page:
                raise HTTPException(404, "Page not found")
        campaign = PortalCampaign(
            tenant_id=ctx.tenant_id, name=body.name, page_id=body.page_id,
            campaign_type=body.campaign_type, target_segment=body.target_segment,
            schedule=body.schedule, content=body.content, budget_zar=body.budget_zar,
            created_by=ctx.user_id,
        )
        session.add(campaign)
        await session.flush()
        await session.refresh(campaign)
        return CampaignRead.model_validate(campaign)


@app.get("/api/v1/portal/campaigns")
async def list_campaigns(
    ctx: AuthContext = Depends(get_auth_context),
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
):
    async with session_scope() as session:
        query = select(PortalCampaign).where(PortalCampaign.tenant_id == ctx.tenant_id)
        if status:
            query = query.where(PortalCampaign.status == status)
        total = await session.scalar(select(func.count()).select_from(query.subquery()))
        items = (await session.execute(
            query.order_by(PortalCampaign.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        )).scalars().all()
        return {
            "items": [CampaignRead.model_validate(c) for c in items],
            "total": total or 0, "page": page, "page_size": page_size,
            "pages": max(1, ((total or 0) + page_size - 1) // page_size),
        }


@app.post("/api/v1/portal/campaigns/{campaign_id}/launch", dependencies=[Depends(require_tier("manager"))])
async def launch_campaign(campaign_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context)):
    async with session_scope() as session:
        campaign = await session.get(PortalCampaign, campaign_id)
        if not campaign or campaign.tenant_id != ctx.tenant_id:
            raise HTTPException(404, "Campaign not found")
        campaign.status = "running"
        campaign.started_at = datetime.now(timezone.utc)
        await session.flush()
        return {"status": "launched", "campaign_id": str(campaign_id)}


@app.post("/api/v1/portal/campaigns/{campaign_id}/complete", dependencies=[Depends(require_tier("manager"))])
async def complete_campaign(campaign_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context)):
    async with session_scope() as session:
        campaign = await session.get(PortalCampaign, campaign_id)
        if not campaign or campaign.tenant_id != ctx.tenant_id:
            raise HTTPException(404, "Campaign not found")
        campaign.status = "completed"
        campaign.completed_at = datetime.now(timezone.utc)
        await session.flush()
        return CampaignRead.model_validate(campaign)


# ── SEO Routes ─────────────────────────────────────────────────────────

@app.post("/api/v1/portal/seo-profiles", response_model=SeoProfileRead, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_tier("write"))])
async def create_seo_profile(body: SeoProfileCreate, ctx: AuthContext = Depends(get_auth_context)):
    async with session_scope() as session:
        profile = PortalSeoProfile(
            tenant_id=ctx.tenant_id, name=body.name,
            target_keywords=body.target_keywords, sitemap_enabled=body.sitemap_enabled,
            robots_txt=body.robots_txt, structured_data=body.structured_data,
            analytics_id=body.analytics_id,
        )
        session.add(profile)
        await session.flush()
        await session.refresh(profile)
        return SeoProfileRead.model_validate(profile)


@app.get("/api/v1/portal/seo-profiles")
async def list_seo_profiles(ctx: AuthContext = Depends(get_auth_context)):
    async with session_scope() as session:
        items = (await session.execute(
            select(PortalSeoProfile).where(PortalSeoProfile.tenant_id == ctx.tenant_id)
        )).scalars().all()
        return [SeoProfileRead.model_validate(p) for p in items]


@app.get("/api/v1/portal/seo/sitemap")
async def generate_sitemap(ctx: AuthContext = Depends(get_auth_context)):
    """Generate XML sitemap for all published pages."""
    async with session_scope() as session:
        pages = (await session.execute(
            select(PortalPage).where(PortalPage.tenant_id == ctx.tenant_id, PortalPage.status == "published")
        )).scalars().all()
        urls = []
        for p in pages:
            urls.append({
                "loc": f"/portal/{p.slug}", "lastmod": p.updated_at.isoformat(),
                "priority": "1.0" if p.page_type == "landing" else "0.8",
                "changefreq": "weekly" if p.page_type == "campaign" else "monthly",
            })
        return {"base_url": os.getenv("PORTAL_BASE_URL", "https://omnidome.co.za"), "urls": urls}


@app.get("/api/v1/portal/analytics")
async def portal_analytics(ctx: AuthContext = Depends(get_auth_context)):
    """Aggregated analytics across all portal pages."""
    async with session_scope() as session:
        pages = (await session.execute(
            select(PortalPage).where(PortalPage.tenant_id == ctx.tenant_id)
        )).scalars().all()
        campaigns = (await session.execute(
            select(PortalCampaign).where(PortalCampaign.tenant_id == ctx.tenant_id)
        )).scalars().all()
        return {
            "total_pages": len(pages),
            "published_pages": sum(1 for p in pages if p.status == "published"),
            "total_views": sum(p.views for p in pages),
            "total_conversions": sum(p.conversions for p in pages),
            "conversion_rate": round(sum(p.conversions for p in pages) / max(sum(p.views for p in pages), 1) * 100, 2),
            "total_campaigns": len(campaigns),
            "active_campaigns": sum(1 for c in campaigns if c.status == "running"),
            "total_spend": float(sum(c.spent_zar or 0 for c in campaigns)),
            "top_pages": sorted([{"slug": p.slug, "title": p.title, "views": p.views, "conversions": p.conversions} for p in pages], key=lambda x: x["views"], reverse=True)[:5],
        }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8026)
