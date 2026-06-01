"""Web Analytics Tracking Service - captures page views, clicks, forms, sessions."""

import hashlib
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import uvicorn
from fastapi import FastAPI, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import func, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from user_agents import parse as parse_ua

from services.web_analytics.database import get_session, init_tables
from services.web_analytics.models import (
    ClickEvent,
    FormEvent,
    PageView,
    SessionTracking,
    PageAnalyticsBase,
)

app = FastAPI(title="OmniDome Web Analytics", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _hash_ip(ip: str) -> str:
    salt = os.getenv("ANALYTICS_IP_SALT", "omnidome-analytics-salt")
    return hashlib.sha256(f"{salt}{ip}".encode()).hexdigest()[:16]


def _parse_device(ua_string: str):
    ua = parse_ua(ua_string)
    if ua.is_mobile:
        return "mobile", ua.browser.family or "", str(ua.browser.version_string or ""), ua.os.family or "", str(ua.os.version_string or "")
    elif ua.is_tablet:
        return "tablet", ua.browser.family or "", str(ua.browser.version_string or ""), ua.os.family or "", str(ua.os.version_string or "")
    else:
        return "desktop", ua.browser.family or "", str(ua.browser.version_string or ""), ua.os.family or "", str(ua.os.version_string or "")


def _get_geo(request: Request):
    """Extract geo info from Cloudflare / Vercel / custom headers."""
    country = (
        request.headers.get("cf-ipcountry")
        or request.headers.get("x-vercel-ip-country")
        or request.headers.get("x-geo-country")
    )
    city = (
        request.headers.get("x-vercel-ip-city")
        or request.headers.get("x-geo-city")
    )
    region = (
        request.headers.get("x-vercel-ip-country-region")
        or request.headers.get("x-geo-region")
    )
    lat = request.headers.get("x-vercel-ip-latitude") or request.headers.get("x-geo-lat")
    lon = request.headers.get("x-vercel-ip-longitude") or request.headers.get("x-geo-lon")

    try:
        lat = float(lat) if lat else None
    except (ValueError, TypeError):
        lat = None
    try:
        lon = float(lon) if lon else None
    except (ValueError, TypeError):
        lon = None

    return {
        "country": country,
        "city": city,
        "region": region,
        "latitude": lat,
        "longitude": lon,
    }


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class TrackPageView(BaseModel):
    session_id: str
    visitor_id: str
    url: str
    path: str
    title: Optional[str] = None
    referrer: Optional[str] = None
    screen_width: Optional[int] = None
    screen_height: Optional[int] = None
    time_on_page: Optional[int] = None
    scroll_depth: Optional[int] = None
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None
    utm_term: Optional[str] = None
    utm_content: Optional[str] = None


class TrackClick(BaseModel):
    session_id: str
    visitor_id: str
    page_view_id: Optional[str] = None
    element_tag: Optional[str] = None
    element_id: Optional[str] = None
    element_class: Optional[str] = None
    element_text: Optional[str] = None
    href: Optional[str] = None
    x: Optional[int] = None
    y: Optional[int] = None
    path: str


class TrackForm(BaseModel):
    session_id: str
    visitor_id: str
    page_view_id: Optional[str] = None
    form_id: Optional[str] = None
    form_name: Optional[str] = None
    form_action: Optional[str] = None
    event_type: str  # view, start, submit, abandon, validation_error
    fields_interacted: Optional[list] = None
    fields_count: Optional[int] = None
    time_to_complete: Optional[int] = None
    validation_errors: Optional[list] = None
    path: str


class SessionStart(BaseModel):
    session_id: str
    visitor_id: str
    landing_page: str
    referrer: Optional[str] = None
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None
    utm_term: Optional[str] = None
    utm_content: Optional[str] = None


class SessionEnd(BaseModel):
    session_id: str
    duration_seconds: int | None = None


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def startup():
    init_tables()


# ---------------------------------------------------------------------------
# Ingestion endpoints (called by frontend tracker)
# ---------------------------------------------------------------------------

@app.post("/track/pageview")
async def track_pageview(data: TrackPageView, request: Request, session: AsyncSession = Depends(get_session)):
    ua_string = request.headers.get("user-agent", "")
    device_type, browser, browser_ver, os, os_ver = _parse_device(ua_string)
    geo = _get_geo(request)
    ip = request.client.host if request.client else ""

    # Create page view
    pv = PageView(
        session_id=data.session_id,
        visitor_id=data.visitor_id,
        url=data.url,
        path=data.path,
        title=data.title,
        referrer=data.referrer,
        user_agent=ua_string[:500] if ua_string else None,
        device_type=device_type,
        browser=browser[:50] if browser else None,
        browser_version=browser_ver[:20] if browser_ver else None,
        os=os[:50] if os else None,
        os_version=os_ver[:20] if os_ver else None,
        screen_width=data.screen_width,
        screen_height=data.screen_height,
        time_on_page=data.time_on_page,
        scroll_depth=data.scroll_depth,
        ip_hash=_hash_ip(ip) if ip else None,
        country=geo["country"],
        city=geo["city"],
        region=geo["region"],
        latitude=geo["latitude"],
        longitude=geo["longitude"],
    )
    session.add(pv)

    # Update session tracking
    result = await session.execute(
        select(SessionTracking).where(SessionTracking.session_id == data.session_id)
    )
    sess = result.scalar_one_or_none()
    if sess:
        sess.pageviews_count += 1
        sess.is_bounce = False
    else:
        # First pageview — create session
        sess = SessionTracking(
            session_id=data.session_id,
            visitor_id=data.visitor_id,
            landing_page=data.url,
            referrer=data.referrer,
            utm_source=data.utm_source,
            utm_medium=data.utm_medium,
            utm_campaign=data.utm_campaign,
            utm_term=data.utm_term,
            utm_content=data.utm_content,
            device_type=device_type,
            browser=browser[:50] if browser else None,
            os=os[:50] if os else None,
            country=geo["country"],
            country_name=None,
            started_at=datetime.now(timezone.utc),
        )
        session.add(sess)

    await session.flush()
    return {"status": "ok", "page_view_id": str(pv.id)}


@app.post("/track/click")
async def track_click(data: TrackClick, session: AsyncSession = Depends(get_session)):
    ce = ClickEvent(
        session_id=data.session_id,
        visitor_id=data.visitor_id,
        page_view_id=uuid.UUID(data.page_view_id) if data.page_view_id else None,
        element_tag=data.element_tag,
        element_id=data.element_id,
        element_class=data.element_class,
        element_text=data.element_text,
        href=data.href,
        x=data.x,
        y=data.y,
        path=data.path,
    )
    session.add(ce)

    # Update session event count
    result = await session.execute(
        select(SessionTracking).where(SessionTracking.session_id == data.session_id)
    )
    sess = result.scalar_one_or_none()
    if sess:
        sess.events_count += 1

    return {"status": "ok"}


@app.post("/track/form")
async def track_form(data: TrackForm, session: AsyncSession = Depends(get_session)):
    fe = FormEvent(
        session_id=data.session_id,
        visitor_id=data.visitor_id,
        page_view_id=uuid.UUID(data.page_view_id) if data.page_view_id else None,
        form_id=data.form_id,
        form_name=data.form_name,
        form_action=data.form_action,
        event_type=data.event_type,
        fields_interacted=data.fields_interacted,
        fields_count=data.fields_count,
        time_to_complete=data.time_to_complete,
        validation_errors=data.validation_errors,
        path=data.path,
    )
    session.add(fe)

    result = await session.execute(
        select(SessionTracking).where(SessionTracking.session_id == data.session_id)
    )
    sess = result.scalar_one_or_none()
    if sess:
        sess.events_count += 1

    return {"status": "ok"}


@app.post("/track/session/end")
async def end_session(data: SessionEnd, session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(SessionTracking).where(SessionTracking.session_id == data.session_id)
    )
    sess = result.scalar_one_or_none()
    if sess:
        sess.ended_at = datetime.now(timezone.utc)
        sess.duration_seconds = data.duration_seconds
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Dashboard analytics endpoints (used by the admin dashboard)
# ---------------------------------------------------------------------------

def _date_filter(days: int = 30):
    return datetime.now(timezone.utc) - timedelta(days=days)


@app.get("/analytics/overview")
async def analytics_overview(days: int = 30, session: AsyncSession = Depends(get_session)):
    since = _date_filter(days)

    # Total page views
    pv_result = await session.execute(
        select(func.count(PageView.id)).where(PageView.created_at >= since)
    )
    total_pageviews = pv_result.scalar()

    # Unique visitors
    vis_result = await session.execute(
        select(func.count(func.distinct(PageView.visitor_id))).where(PageView.created_at >= since)
    )
    unique_visitors = vis_result.scalar()

    # Unique sessions
    sess_result = await session.execute(
        select(func.count(func.distinct(PageView.session_id))).where(PageView.created_at >= since)
    )
    unique_sessions = sess_result.scalar()

    # Avg session duration
    avg_dur_result = await session.execute(
        select(func.avg(SessionTracking.duration_seconds)).where(
            SessionTracking.started_at >= since,
            SessionTracking.duration_seconds.isnot(None),
        )
    )
    avg_duration = avg_dur_result.scalar()

    # Bounce rate
    bounce_result = await session.execute(
        select(func.count(SessionTracking.id)).where(
            SessionTracking.started_at >= since,
            SessionTracking.is_bounce == True,
        )
    )
    bounces = bounce_result.scalar()
    total_sessions = sess_result.scalar() if sess_result else 0

    total_sess_result = await session.execute(
        select(func.count(SessionTracking.id)).where(SessionTracking.started_at >= since)
    )
    total_sessions = total_sess_result.scalar()
    bounce_rate = (bounces / total_sessions * 100) if total_sessions > 0 else 0

    return {
        "total_pageviews": total_pageviews,
        "unique_visitors": unique_visitors,
        "unique_sessions": unique_sessions,
        "avg_session_duration": round(avg_duration or 0),
        "bounce_rate": round(bounce_rate, 1),
    }


@app.get("/analytics/traffic")
async def analytics_traffic(days: int = 30, session: AsyncSession = Depends(get_session)):
    since = _date_filter(days)

    # Page views per day
    result = await session.execute(
        select(
            func.date_trunc("day", PageView.created_at).label("day"),
            func.count(PageView.id).label("pageviews"),
            func.count(func.distinct(PageView.visitor_id)).label("unique_visitors"),
            func.count(func.distinct(PageView.session_id)).label("sessions"),
        )
        .where(PageView.created_at >= since)
        .group_by(text("day"))
        .order_by(text("day"))
    )
    rows = result.all()
    return [
        {
            "date": row.day.isoformat() if row.day else "",
            "pageviews": row.pageviews,
            "unique_visitors": row.unique_visitors,
            "sessions": row.sessions,
        }
        for row in rows
    ]


@app.get("/analytics/pages")
async def analytics_pages(days: int = 30, limit: int = 20, session: AsyncSession = Depends(get_session)):
    since = _date_filter(days)

    result = await session.execute(
        select(
            PageView.path,
            PageView.title,
            func.count(PageView.id).label("pageviews"),
            func.count(func.distinct(PageView.visitor_id)).label("unique_visitors"),
            func.avg(PageView.time_on_page).label("avg_time_on_page"),
        )
        .where(PageView.created_at >= since)
        .group_by(PageView.path, PageView.title)
        .order_by(func.count(PageView.id).desc())
        .limit(limit)
    )
    rows = result.all()
    return [
        {
            "path": row.path,
            "title": row.title or row.path,
            "pageviews": row.pageviews,
            "unique_visitors": row.unique_visitors,
            "avg_time_on_page": round(row.avg_time_on_page or 0),
        }
        for row in rows
    ]


@app.get("/analytics/devices")
async def analytics_devices(days: int = 30, session: AsyncSession = Depends(get_session)):
    since = _date_filter(days)

    # Device type breakdown
    device_result = await session.execute(
        select(
            PageView.device_type,
            func.count(PageView.id).label("count"),
        )
        .where(PageView.created_at >= since)
        .group_by(PageView.device_type)
        .order_by(func.count(PageView.id).desc())
    )
    devices = [{"device": (row.device_type or "unknown"), "count": row.count} for row in device_result.all()]

    # Browser breakdown
    browser_result = await session.execute(
        select(
            PageView.browser,
            func.count(PageView.id).label("count"),
        )
        .where(PageView.created_at >= since, PageView.browser.isnot(None))
        .group_by(PageView.browser)
        .order_by(func.count(PageView.id).desc())
        .limit(10)
    )
    browsers = [{"browser": (row.browser or "unknown"), "count": row.count} for row in browser_result.all()]

    # OS breakdown
    os_result = await session.execute(
        select(
            PageView.os,
            func.count(PageView.id).label("count"),
        )
        .where(PageView.created_at >= since, PageView.os.isnot(None))
        .group_by(PageView.os)
        .order_by(func.count(PageView.id).desc())
        .limit(10)
    )
    os_list = [{"os": (row.os or "unknown"), "count": row.count} for row in os_result.all()]

    # Screen resolution breakdown
    screen_result = await session.execute(
        select(
            func.concat(PageView.screen_width, "x", PageView.screen_height).label("resolution"),
            func.count(PageView.id).label("count"),
        )
        .where(
            PageView.created_at >= since,
            PageView.screen_width.isnot(None),
            PageView.screen_height.isnot(None),
        )
        .group_by(PageView.screen_width, PageView.screen_height)
        .order_by(func.count(PageView.id).desc())
        .limit(10)
    )
    screens = [
        {"resolution": (row.resolution or "unknown"), "count": row.count}
        for row in screen_result.all()
        if row.resolution and "None" not in row.resolution
    ]

    return {
        "devices": devices,
        "browsers": browsers,
        "os": os_list,
        "screens": screens,
    }


@app.get("/analytics/locations")
async def analytics_locations(days: int = 30, limit: int = 50, session: AsyncSession = Depends(get_session)):
    since = _date_filter(days)

    # Country breakdown
    country_result = await session.execute(
        select(
            PageView.country,
            PageView.country_name,
            func.count(PageView.id).label("pageviews"),
            func.count(func.distinct(PageView.visitor_id)).label("unique_visitors"),
        )
        .where(PageView.created_at >= since, PageView.country.isnot(None))
        .group_by(PageView.country, PageView.country_name)
        .order_by(func.count(PageView.id).desc())
        .limit(limit)
    )
    countries = [
        {
            "country_code": row.country or "unknown",
            "country": row.country_name or row.country or "Unknown",
            "pageviews": row.pageviews,
            "unique_visitors": row.unique_visitors,
        }
        for row in country_result.all()
    ]

    # City breakdown
    city_result = await session.execute(
        select(
            PageView.city,
            PageView.region,
            PageView.country,
            func.count(PageView.id).label("pageviews"),
        )
        .where(PageView.created_at >= since, PageView.city.isnot(None))
        .group_by(PageView.city, PageView.region, PageView.country)
        .order_by(func.count(PageView.id).desc())
        .limit(limit)
    )
    cities = [
        {
            "city": row.city or "Unknown",
            "region": row.region,
            "country": row.country,
            "pageviews": row.pageviews,
        }
        for row in city_result.all()
    ]

    return {"countries": countries, "cities": cities}


@app.get("/analytics/forms")
async def analytics_forms(days: int = 30, session: AsyncSession = Depends(get_session)):
    since = _date_filter(days)

    # Form-level stats
    result = await session.execute(
        select(
            FormEvent.form_id,
            FormEvent.form_name,
            FormEvent.path,
            FormEvent.event_type,
            func.count(FormEvent.id).label("count"),
            func.avg(FormEvent.time_to_complete).label("avg_time"),
        )
        .where(FormEvent.created_at >= since)
        .group_by(FormEvent.form_id, FormEvent.form_name, FormEvent.path, FormEvent.event_type)
        .order_by(FormEvent.form_id, FormEvent.event_type)
    )
    rows = result.all()

    # Pivot into form objects
    forms = {}
    for row in rows:
        key = row.form_id or row.form_name or row.path
        if key not in forms:
            forms[key] = {
                "form_id": row.form_id,
                "form_name": row.form_name or row.path,
                "path": row.path,
                "views": 0,
                "starts": 0,
                "submits": 0,
                "abandons": 0,
                "errors": 0,
                "avg_time_to_complete": 0,
            }
        if row.event_type == "view":
            forms[key]["views"] = row.count
        elif row.event_type == "start":
            forms[key]["starts"] = row.count
        elif row.event_type == "submit":
            forms[key]["submits"] = row.count
        elif row.event_type == "abandon":
            forms[key]["abandons"] = row.count
        elif row.event_type == "validation_error":
            forms[key]["errors"] = row.count

        if row.avg_time and row.event_type == "submit":
            forms[key]["avg_time_to_complete"] = round(row.avg_time)

    # Calculate conversion rates
    for f in forms.values():
        total_starts = f["starts"] or f["views"]
        f["conversion_rate"] = round(f["submits"] / total_starts * 100, 1) if total_starts > 0 else 0

    return {
        "forms": list(forms.values()),
    }


@app.get("/analytics/referrers")
async def analytics_referrers(days: int = 30, limit: int = 20, session: AsyncSession = Depends(get_session)):
    since = _date_filter(days)

    result = await session.execute(
        select(
            SessionTracking.referrer,
            func.count(SessionTracking.id).label("sessions"),
        )
        .where(SessionTracking.started_at >= since, SessionTracking.referrer.isnot(None))
        .group_by(SessionTracking.referrer)
        .order_by(func.count(SessionTracking.id).desc())
        .limit(limit)
    )
    rows = result.all()
    return [
        {"referrer": row.referrer or "direct", "sessions": row.sessions}
        for row in rows
    ]


@app.get("/analytics/utm")
async def analytics_utm(days: int = 30, session: AsyncSession = Depends(get_session)):
    since = _date_filter(days)

    result = await session.execute(
        select(
            SessionTracking.utm_source,
            SessionTracking.utm_medium,
            SessionTracking.utm_campaign,
            func.count(SessionTracking.id).label("sessions"),
        )
        .where(
            SessionTracking.started_at >= since,
            SessionTracking.utm_source.isnot(None),
        )
        .group_by(
            SessionTracking.utm_source,
            SessionTracking.utm_medium,
            SessionTracking.utm_campaign,
        )
        .order_by(func.count(SessionTracking.id).desc())
        .limit(30)
    )
    rows = result.all()
    return [
        {
            "source": row.utm_source,
            "medium": row.utm_medium,
            "campaign": row.utm_campaign,
            "sessions": row.sessions,
        }
        for row in rows
    ]


@app.get("/analytics/realtime")
async def analytics_realtime(session: AsyncSession = Depends(get_session)):
    """Active users in the last 5 minutes."""
    five_min_ago = datetime.now(timezone.utc) - timedelta(minutes=5)

    result = await session.execute(
        select(
            func.count(func.distinct(PageView.visitor_id)).label("active_visitors"),
            func.count(PageView.id).label("pageviews"),
        )
        .where(PageView.created_at >= five_min_ago)
    )
    row = result.one()

    # Top active pages
    pages_result = await session.execute(
        select(
            PageView.path,
            func.count(func.distinct(PageView.visitor_id)).label("visitors"),
        )
        .where(PageView.created_at >= five_min_ago)
        .group_by(PageView.path)
        .order_by(func.count(func.distinct(PageView.visitor_id)).desc())
        .limit(10)
    )
    pages = [{"path": r.path, "visitors": r.visitors} for r in pages_result.all()]

    return {
        "active_visitors": row.active_visitors,
        "pageviews_last_5min": row.pageviews,
        "top_pages": pages,
    }


@app.get("/")
async def root():
    return {"message": "OmniDome Web Analytics Service is active"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8016)
