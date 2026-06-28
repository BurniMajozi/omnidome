"""
Portal Builder Service — Main FastAPI Application
Rapid landing page builder, campaign push engine, and SEO management.
Port: 8026 | Module: portal_builder
"""

import os
import uuid
import json
import hashlib
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, Depends, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Index, Integer, Numeric,
    String, Text, func, select,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from services.common.entitlements import EntitlementGuard
from services.common.auth import AuthContext, get_auth_context
from services.common.db import Base, session_scope
from services.common.middleware import add_exception_handlers
from services.portal_builder.builder_ux import router as builder_ux_router

# ── App ────────────────────────────────────────────────────────────────

app = FastAPI(
    title="OmniDome Portal Builder",
    description="Rapid landing page builder, campaign push engine, and SEO management",
    version="1.0.0",
)

guard = EntitlementGuard(
    module_id="portal-builder",
    public_paths={"/health", "/docs", "/openapi.json", "/api/v1/portal/public"},
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


@app.on_event("startup")
async def startup() -> None:
    guard.ensure_startup()
    if os.getenv("AUTO_CREATE_TABLES", "false").lower() == "true":
        from services.portal_builder.database import init_tables
        init_tables()


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


# ── Schemas ────────────────────────────────────────────────────────────

class PageCreate(BaseModel):
    slug: str = Field(..., min_length=1, max_length=200, description="URL slug, e.g. 'fibre-promo-q3'")
    title: str = Field(..., min_length=1, max_length=300)
    description: Optional[str] = None
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
    published_at: Optional[datetime]
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
    budget_zar: float = 0


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
    page_id: uuid.UUID
    form_data: Dict[str, Any] = Field(default_factory=dict)
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None
    referrer: Optional[str] = None


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


# ── Page Builder Routes ────────────────────────────────────────────────

@app.post("/api/v1/portal/pages", response_model=PageRead, status_code=status.HTTP_201_CREATED)
async def create_page(body: PageCreate, ctx: AuthContext = Depends(get_auth_context)):
    async with session_scope() as session:
        page = PortalPage(
            tenant_id=ctx.tenant_id, slug=body.slug, title=body.title,
            description=body.description, page_type=body.page_type,
            content=body.content, theme=body.theme, seo_meta=body.seo_meta,
            created_by=ctx.user_id,
        )
        session.add(page)
        await session.flush()
        await session.refresh(page)
        return PageRead.model_validate(page)


@app.get("/api/v1/portal/pages")
async def list_pages(
    ctx: AuthContext = Depends(get_auth_context),
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    page_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
):
    async with session_scope() as session:
        query = select(PortalPage).where(PortalPage.tenant_id == ctx.tenant_id)
        if page_type:
            query = query.where(PortalPage.page_type == page_type)
        if status:
            query = query.where(PortalPage.status == status)
        if search:
            query = query.where(
                PortalPage.title.ilike(f"%{search}%") | PortalPage.slug.ilike(f"%{search}%")
            )
        total = await session.scalar(select(func.count()).select_from(query.subquery()))
        items = (await session.execute(
            query.order_by(PortalPage.updated_at.desc()).offset((page - 1) * page_size).limit(page_size)
        )).scalars().all()
        return {
            "items": [PageListItem.model_validate(i) for i in items],
            "total": total or 0, "page": page, "page_size": page_size,
            "pages": max(1, (total or 0 + page_size - 1) // page_size),
        }


@app.get("/api/v1/portal/pages/{page_id}", response_model=PageRead)
async def get_page(page_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context)):
    async with session_scope() as session:
        page = await session.get(PortalPage, page_id)
        if not page or page.tenant_id != ctx.tenant_id:
            raise HTTPException(404, "Page not found")
        return PageRead.model_validate(page)


@app.get("/api/v1/portal/public/{slug}")
async def get_public_page(slug: str):
    """Serve a published page publicly (no auth)."""
    async with session_scope() as session:
        page = (await session.execute(
            select(PortalPage).where(PortalPage.slug == slug, PortalPage.status == "published")
        )).scalars().first()
        if not page:
            raise HTTPException(404, "Page not found")
        # Increment views
        page.views += 1
        await session.flush()
        return {
            "slug": page.slug, "title": page.title, "description": page.description,
            "content": page.content, "theme": page.theme, "seo_meta": page.seo_meta,
            "custom_css": page.custom_css, "custom_js": page.custom_js,
        }


@app.put("/api/v1/portal/pages/{page_id}", response_model=PageRead)
async def update_page(page_id: uuid.UUID, body: PageUpdate, ctx: AuthContext = Depends(get_auth_context)):
    async with session_scope() as session:
        page = await session.get(PortalPage, page_id)
        if not page or page.tenant_id != ctx.tenant_id:
            raise HTTPException(404, "Page not found")
        update = body.model_dump(exclude_unset=True)
        for k, v in update.items():
            setattr(page, k, v)
        page.updated_by = ctx.user_id
        # Save version snapshot
        version = PortalPageVersion(
            page_id=page.id,
            version_number=await session.scalar(
                select(func.count()).select_from(PortalPageVersion).where(PortalPageVersion.page_id == page.id)
            ) or 0 + 1,
            content=page.content, theme=page.theme, seo_meta=page.seo_meta,
            created_by=ctx.user_id,
        )
        session.add(version)
        await session.flush()
        await session.refresh(page)
        return PageRead.model_validate(page)


@app.post("/api/v1/portal/pages/{page_id}/publish")
async def publish_page(page_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context)):
    async with session_scope() as session:
        page = await session.get(PortalPage, page_id)
        if not page or page.tenant_id != ctx.tenant_id:
            raise HTTPException(404, "Page not found")
        page.status = "published"
        page.published_at = datetime.now(timezone.utc)
        page.updated_by = ctx.user_id
        await session.flush()
        return {"status": "published", "url": f"/portal/{page.slug}"}


@app.delete("/api/v1/portal/pages/{page_id}")
async def delete_page(page_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context)):
    async with session_scope() as session:
        page = await session.get(PortalPage, page_id)
        if not page or page.tenant_id != ctx.tenant_id:
            raise HTTPException(404, "Page not found")
        await session.delete(page)
        return {"status": "deleted"}


# ── Submissions ────────────────────────────────────────────────────────

@app.post("/api/v1/portal/submissions")
async def submit_form(body: SubmissionCreate, ctx: Optional[AuthContext] = Depends(get_auth_context)):
    """Public form submission endpoint. Auth optional."""
    async with session_scope() as session:
        page = await session.get(PortalPage, body.page_id)
        if not page or page.status != "published":
            raise HTTPException(404, "Page not found")
        submission = PortalSubmission(
            page_id=body.page_id, tenant_id=page.tenant_id,
            form_data=body.form_data, utm_source=body.utm_source,
            utm_medium=body.utm_medium, utm_campaign=body.utm_campaign,
            referrer=body.referrer,
        )
        session.add(submission)
        page.conversions += 1
        await session.flush()
        return {"status": "submitted", "id": str(submission.id)}


@app.get("/api/v1/portal/pages/{page_id}/submissions")
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
            "items": [{"id": str(s.id), "form_data": s.form_data, "utm": {"source": s.utm_source, "medium": s.utm_medium, "campaign": s.utm_campaign}, "converted": s.converted, "created_at": s.created_at.isoformat()} for s in items],
            "total": total or 0,
        }


# ── Campaign Routes ────────────────────────────────────────────────────

@app.post("/api/v1/portal/campaigns", response_model=CampaignRead, status_code=status.HTTP_201_CREATED)
async def create_campaign(body: CampaignCreate, ctx: AuthContext = Depends(get_auth_context)):
    async with session_scope() as session:
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
            "pages": max(1, (total or 0 + page_size - 1) // page_size),
        }


@app.post("/api/v1/portal/campaigns/{campaign_id}/launch")
async def launch_campaign(campaign_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context)):
    async with session_scope() as session:
        campaign = await session.get(PortalCampaign, campaign_id)
        if not campaign or campaign.tenant_id != ctx.tenant_id:
            raise HTTPException(404, "Campaign not found")
        campaign.status = "running"
        campaign.started_at = datetime.now(timezone.utc)
        await session.flush()
        return {"status": "launched", "campaign_id": str(campaign_id)}


@app.post("/api/v1/portal/campaigns/{campaign_id}/complete")
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

@app.post("/api/v1/portal/seo-profiles", response_model=SeoProfileRead, status_code=status.HTTP_201_CREATED)
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
        return os.getenv("PORTAL_BASE_URL", "https://omnidome.co.za"), urls


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
            "total_spend": sum(c.spent_zar for c in campaigns),
            "top_pages": sorted([{"slug": p.slug, "title": p.title, "views": p.views, "conversions": p.conversions} for p in pages], key=lambda x: x["views"], reverse=True)[:5],
        }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8026)
