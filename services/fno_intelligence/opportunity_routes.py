"""Opportunity finder routes (SPEC-opportunity-finder.md).

Mounted at /api/fno/opportunities. Company search is grounded on
OpenStreetMap (Nominatim for the area, Overpass for businesses); tender /
RFQ tracking scrapes user-supplied source URLs with Firecrawl and extracts
tenders with the OpenRouter model. Slow work (Overpass, scans) runs as
background jobs; the UI polls. Pure logic lives in opportunities.py.
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Literal, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.common.auth import get_current_tenant_id, get_current_user_id
from services.common.background_tasks import schedule_background
from services.common.firecrawl import REASONING_MODEL, FirecrawlError, firecrawl
from services.fno_intelligence import opportunities as opp
from services.fno_intelligence.database import get_session, get_session_factory
from services.fno_intelligence.models import OppCompany, OppCompanySearch
from services.fno_intelligence.web_intel import _reason

logger = logging.getLogger("fno_intelligence.opportunities")
router = APIRouter(prefix="/opportunities", tags=["Opportunity finder"])

_USER_AGENT = os.getenv("GEOCODE_USER_AGENT", "OmniDome-FNO-Intelligence/1.0 (local dev)")
_NOMINATIM = os.getenv("NOMINATIM_BASE_URL", "https://nominatim.openstreetmap.org").rstrip("/")
_OVERPASS_ENDPOINTS = [
    u.strip() for u in os.getenv(
        "OVERPASS_ENDPOINTS",
        "https://overpass-api.de/api/interpreter,https://overpass.kumi.systems/api/interpreter,"
        "https://overpass.private.coffee/api/interpreter",
    ).split(",") if u.strip()
]


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── companies ─────────────────────────────────────────────────────────────

class CompanySearchCreate(BaseModel):
    area: str = Field(..., min_length=2, max_length=200)
    category: str = "all"
    radius_km: int = 2


class CompanyPatch(BaseModel):
    status: Optional[Literal["new", "lead_created", "dismissed"]] = None
    sales_lead_id: Optional[uuid.UUID] = None


def _search_dict(s: OppCompanySearch) -> dict:
    return {
        "id": str(s.id), "area_query": s.area_query, "area_label": s.area_label,
        "category": s.category, "category_label": opp.CATEGORIES.get(s.category, {}).get("label", s.category),
        "radius_km": s.radius_km, "center_lat": s.center_lat, "center_lng": s.center_lng,
        "status": s.status, "error_message": s.error_message, "result_count": s.result_count,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "finished_at": s.finished_at.isoformat() if s.finished_at else None,
    }


def _company_dict(c: OppCompany) -> dict:
    return {
        "id": str(c.id), "search_id": str(c.search_id), "osm_type": c.osm_type, "osm_id": c.osm_id,
        "name": c.name, "category_label": c.category_label, "address_line": c.address_line,
        "suburb": c.suburb, "city": c.city, "postal_code": c.postal_code,
        "phone": c.phone, "email": c.email, "website": c.website,
        "lat": c.lat, "lng": c.lng, "distance_km": c.distance_km, "status": c.status,
        "sales_lead_id": str(c.sales_lead_id) if c.sales_lead_id else None,
        "enriched_at": c.enriched_at.isoformat() if c.enriched_at else None,
    }


async def _geocode_area(area: str) -> Optional[dict]:
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(
            f"{_NOMINATIM}/search",
            params={"q": opp.area_query(area), "format": "jsonv2", "limit": 5, "countrycodes": "za"},
            headers={"User-Agent": _USER_AGENT},
        )
    resp.raise_for_status()
    return opp.pick_area_result(resp.json())


async def _overpass(query: str) -> list[dict]:
    """Try each Overpass endpoint in turn; public instances are often busy."""
    last_error = "no Overpass endpoint configured"
    # The main instance is fast but allows only 2 concurrent queries per client,
    # so give it a second try after a short pause before using slower mirrors.
    attempts = _OVERPASS_ENDPOINTS[:1] * 2 + _OVERPASS_ENDPOINTS[1:]
    for i, url in enumerate(attempts):
        if i == 1:
            await asyncio.sleep(5)
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(url, data={"data": query}, headers={"User-Agent": _USER_AGENT})
            if resp.status_code == 200 and resp.headers.get("content-type", "").startswith("application/json"):
                return resp.json().get("elements", [])
            last_error = f"{url.split('/')[2]} answered HTTP {resp.status_code}"
        except httpx.HTTPError as exc:
            last_error = f"{url.split('/')[2]}: {type(exc).__name__}"
        logger.warning("[opportunities] Overpass attempt failed: %s", last_error)
    raise RuntimeError(f"OpenStreetMap search is busy right now ({last_error}). Try again in a minute.")


async def _run_company_search(search_id: uuid.UUID) -> None:
    async with get_session_factory()() as session:
        search = await session.get(OppCompanySearch, search_id)
        if search is None:
            return
        search.status = "running"
        await session.commit()
        try:
            query = opp.build_overpass_query(search.center_lat, search.center_lng, search.radius_km, search.category)
            companies = opp.parse_overpass_elements(await _overpass(query), (search.center_lat, search.center_lng))
            for c in companies:
                session.add(OppCompany(tenant_id=search.tenant_id, search_id=search.id, **c))
            search.result_count = len(companies)
            search.status = "done"
        except Exception as exc:  # recorded on the search; the UI shows it with a retry
            logger.exception("[opportunities] company search %s failed", search_id)
            search.status = "failed"
            search.error_message = str(exc)[:500]
        search.finished_at = _now()
        await session.commit()


@router.get("/company-categories")
async def list_company_categories():
    return [{"id": cid, "label": c["label"]} for cid, c in opp.CATEGORIES.items()]


@router.post("/company-searches", status_code=202)
async def create_company_search(
    body: CompanySearchCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_session),
):
    if body.category not in opp.CATEGORIES:
        raise HTTPException(422, "Unknown category")
    if body.radius_km not in opp.RADII_KM:
        raise HTTPException(422, f"Radius must be one of {', '.join(map(str, opp.RADII_KM))} km")
    try:
        place = await _geocode_area(body.area.strip())
    except httpx.HTTPError:
        raise HTTPException(503, "The map service didn't answer. Try again in a moment.")
    if place is None:
        raise HTTPException(422, "We couldn't find that area. Try a suburb and city, e.g. \"Rosebank, Johannesburg\".")
    search = OppCompanySearch(
        tenant_id=tenant_id, area_query=body.area.strip(), area_label=place.get("display_name"),
        category=body.category, radius_km=body.radius_km,
        center_lat=float(place["lat"]), center_lng=float(place["lon"]), created_by=user_id,
    )
    db.add(search)
    await db.commit()  # the background job opens its own session and must see this row
    schedule_background(_run_company_search(search.id))
    return _search_dict(search)


@router.get("/company-searches")
async def list_company_searches(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    rows = await db.execute(
        select(OppCompanySearch).where(OppCompanySearch.tenant_id == tenant_id)
        .order_by(desc(OppCompanySearch.created_at)).limit(20)
    )
    return [_search_dict(s) for s in rows.scalars().all()]


@router.get("/company-searches/{search_id}")
async def get_company_search(
    search_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    search = await db.get(OppCompanySearch, search_id)
    if search is None or search.tenant_id != tenant_id:
        raise HTTPException(404, "Search not found")
    rows = await db.execute(
        select(OppCompany).where(OppCompany.search_id == search_id, OppCompany.tenant_id == tenant_id)
        .order_by(OppCompany.distance_km, OppCompany.name)
    )
    return {**_search_dict(search), "companies": [_company_dict(c) for c in rows.scalars().all()]}


async def _get_company(db: AsyncSession, tenant_id: uuid.UUID, company_id: uuid.UUID) -> OppCompany:
    company = await db.get(OppCompany, company_id)
    if company is None or company.tenant_id != tenant_id:
        raise HTTPException(404, "Company not found")
    return company


@router.patch("/companies/{company_id}")
async def patch_company(
    company_id: uuid.UUID,
    body: CompanyPatch,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    company = await _get_company(db, tenant_id, company_id)
    if body.status is not None:
        company.status = body.status
    if body.sales_lead_id is not None:
        company.sales_lead_id = body.sales_lead_id
    await db.flush()
    return _company_dict(company)


_ENRICH_PROMPT = (
    'Public business contact details for "{name}" in {place}, South Africa: its official website, main phone '
    "number and general email. Only for this specific business; leave fields empty when not clearly stated."
)


def _contact_from_search(raw: dict) -> dict:
    """First search result whose structured extraction found contact details."""
    data = raw.get("data")
    items = data.get("web", []) if isinstance(data, dict) else (data or [])
    for item in items:
        found = item.get("json") if isinstance(item, dict) else None
        if isinstance(found, dict) and any(opp._clean_str(found.get(k)) for k in ("website", "phone", "email")):
            return found
    return {}


@router.post("/companies/{company_id}/enrich")
async def enrich_company(
    company_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    """Look up missing public contact details: Firecrawl search with structured
    extraction (OpenRouter over the markdown as a fallback). Never overwrites a
    value OpenStreetMap already had."""
    company = await _get_company(db, tenant_id, company_id)
    place = ", ".join(p for p in (company.suburb, company.city) if p) or "the area searched"
    prompt = _ENRICH_PROMPT.format(name=company.name, place=place)
    try:
        raw = await firecrawl.search(
            f'"{company.name}" {place} South Africa contact', limit=3, timeout=90,
            scrape_formats=["markdown", {"type": "json", "prompt": prompt, "schema": opp.CONTACT_JSON_SCHEMA}],
        )
    except FirecrawlError as exc:
        raise HTTPException(503, f"Web search is unavailable right now: {exc}")
    except httpx.HTTPError:
        raise HTTPException(503, "The web search took too long. Try again in a moment.")
    found = _contact_from_search(raw)
    if not found:
        markdown = firecrawl.markdown_from(raw)
        answer = await _reason(markdown, prompt + " Return ONLY a JSON object with website, phone and email.",
                               REASONING_MODEL) if markdown.strip() else None
        if answer:
            try:
                data = opp._extract_json(answer)
                found = data if isinstance(data, dict) else {}
            except ValueError:
                found = {}
    updated = []
    for field, limit in (("website", 500), ("phone", 80), ("email", 200)):
        value = opp._clean_str(found.get(field))
        if value and not getattr(company, field):
            setattr(company, field, value[:limit])
            updated.append(field)
    company.enriched_at = _now()
    company.enrichment = {"found": {k: found.get(k) for k in ("website", "phone", "email")}, "updated": updated}
    await db.flush()
    return {**_company_dict(company), "updated_fields": updated}


# ── tenders and RFQs ──────────────────────────────────────────────────────

import hashlib  # noqa: E402
from datetime import timedelta  # noqa: E402

from fastapi import Response  # noqa: E402
from sqlalchemy import func, text  # noqa: E402

from services.fno_intelligence.models import OppSnapshot, OppSource, OppTender  # noqa: E402

_SCAN_INTERVALS = (12, 24, 168)
_MAX_SCREENSHOT_BYTES = 5 * 1024 * 1024
_MAX_DETAIL_SCANS = 10
_STALE_SCAN_MINUTES = 30
_SCHEDULER_PERIOD_SECONDS = int(os.getenv("OPP_SCHEDULER_PERIOD_SECONDS", "600"))


class SourceCreate(BaseModel):
    url: str = Field(..., min_length=3, max_length=2000)
    label: Optional[str] = Field(None, max_length=200)
    scan_interval_hours: Literal[12, 24, 168] = 24


class SourcePatch(BaseModel):
    label: Optional[str] = Field(None, max_length=200)
    active: Optional[bool] = None
    scan_interval_hours: Optional[Literal[12, 24, 168]] = None


class TenderPatch(BaseModel):
    status: Optional[Literal["new", "reviewing", "bidding", "skipped"]] = None
    sales_lead_id: Optional[uuid.UUID] = None


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


def _source_dict(s: OppSource, tender_count: int = 0, latest_snapshot_id: Optional[uuid.UUID] = None) -> dict:
    return {
        "id": str(s.id), "url": s.url, "label": s.label, "active": s.active,
        "scan_interval_hours": s.scan_interval_hours, "last_scanned_at": _iso(s.last_scanned_at),
        "next_scan_at": _iso(s.next_scan_at), "last_status": s.last_status, "last_error": s.last_error,
        "last_tender_count": s.last_tender_count, "tender_count": tender_count,
        "latest_snapshot_id": str(latest_snapshot_id) if latest_snapshot_id else None,
        "created_at": _iso(s.created_at),
    }


def _tender_dict(t: OppTender, source: Optional[OppSource] = None) -> dict:
    return {
        "id": str(t.id), "source_id": str(t.source_id),
        "source_label": (source.label or source.url) if source else None,
        "snapshot_id": str(t.snapshot_id) if t.snapshot_id else None,
        "title": t.title, "reference": t.reference, "issuer": t.issuer, "description": t.description,
        "closing_at": _iso(t.closing_at), "closing_text": t.closing_text,
        "briefing_at": _iso(t.briefing_at), "briefing_text": t.briefing_text, "briefing_location": t.briefing_location,
        "required_documents": t.required_documents or [], "document_links": t.document_links or [],
        "detail_url": t.detail_url, "contact": t.contact, "status": t.status,
        "sales_lead_id": str(t.sales_lead_id) if t.sales_lead_id else None,
        "first_seen_at": _iso(t.first_seen_at), "last_seen_at": _iso(t.last_seen_at),
    }


async def _get_source(db: AsyncSession, tenant_id: uuid.UUID, source_id: uuid.UUID) -> OppSource:
    source = await db.get(OppSource, source_id)
    if source is None or source.tenant_id != tenant_id:
        raise HTTPException(404, "Source not found")
    return source


# ── scanning ──────────────────────────────────────────────────────────────

async def _claim_source(session: AsyncSession, source_id: uuid.UUID) -> bool:
    """Atomically mark a source as scanning. Only one worker can win, so the
    service's two uvicorn workers never scan the same source twice."""
    result = await session.execute(text(
        "UPDATE opp_sources SET last_status = 'scanning', last_scanned_at = now() "
        "WHERE id = :id AND (last_status <> 'scanning' "
        f"OR last_scanned_at < now() - interval '{_STALE_SCAN_MINUTES} minutes') RETURNING id"
    ), {"id": source_id})
    claimed = result.first() is not None
    await session.commit()
    return claimed


async def _download_screenshot(url: Optional[str]) -> tuple[Optional[bytes], Optional[str]]:
    if not url:
        return None, None
    if url.startswith("data:image/"):
        import base64
        header, _, b64 = url.partition(",")
        return base64.b64decode(b64)[:_MAX_SCREENSHOT_BYTES], header[5:].split(";")[0]
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.get(url)
        if resp.status_code == 200 and len(resp.content) <= _MAX_SCREENSHOT_BYTES:
            return resp.content, resp.headers.get("content-type", "image/png").split(";")[0]
    except httpx.HTTPError:
        logger.warning("[opportunities] screenshot download failed")
    return None, None


async def _extract_page(url: str, *, detail: bool = False) -> dict:
    """Firecrawl scrape with structured extraction (+ screenshot for listing pages)."""
    formats: list = ["markdown", {
        "type": "json",
        "prompt": opp.TENDER_DETAIL_PROMPT if detail else opp.TENDER_LIST_PROMPT,
        "schema": opp.TENDER_DETAIL_JSON_SCHEMA if detail else opp.TENDER_LIST_JSON_SCHEMA,
    }]
    if not detail:
        formats.insert(1, {"type": "screenshot", "fullPage": True})
    # Listing pages with many tenders take Firecrawl 60-90 s to extract.
    raw = await firecrawl.scrape(url, formats=formats, timeout=240 if not detail else 120,
                                 only_main_content=not detail)
    return raw.get("data") or {}


def _merge(target: OppTender, found: dict, page_url: str, *, overwrite: bool) -> None:
    """Copy extracted values onto a tender. With overwrite=False only empty
    fields are filled; user-set status is never touched."""
    def put(field: str, value):
        if value in (None, "", []):
            return
        if overwrite or getattr(target, field) in (None, "", []):
            setattr(target, field, value)

    put("reference", (found.get("reference") or "")[:200] or None)
    put("issuer", (found.get("issuer") or "")[:300] or None)
    put("description", found.get("description"))
    put("closing_text", (found.get("closing_text") or "")[:200] or None)
    put("closing_at", opp.parse_sa_datetime(found.get("closing_text"), now=_now()))
    put("briefing_text", (found.get("briefing_text") or "")[:300] or None)
    put("briefing_at", opp.parse_sa_datetime(found.get("briefing_text"), end_of_day=False))
    put("briefing_location", found.get("briefing_location"))
    put("contact", found.get("contact"))
    put("required_documents", found.get("required_documents") or [])
    links = []
    for link in found.get("document_links") or []:
        absolute = opp.resolve_url(page_url, link.get("url"))
        if absolute:
            links.append({"label": link.get("label"), "url": absolute})
    put("document_links", links)
    put("detail_url", opp.resolve_url(page_url, found.get("detail_url")))


async def _scan_source(source_id: uuid.UUID) -> None:
    async with get_session_factory()() as session:
        if not await _claim_source(session, source_id):
            return
        source = await session.get(OppSource, source_id)
        if source is None:
            return
        try:
            data = await _extract_page(source.url)
            markdown = data.get("markdown") or ""
            tenders = opp.tenders_from_data(data.get("json"))
            if not tenders and markdown.strip():
                answer = await _reason(markdown, opp.build_tender_extraction_instruction(source.url), REASONING_MODEL)
                if answer:
                    try:
                        tenders = opp.parse_tender_json(answer)
                    except ValueError:
                        tenders = []
            shot, mime = await _download_screenshot(data.get("screenshot"))
            snapshot = OppSnapshot(
                tenant_id=source.tenant_id, source_id=source.id, url=source.url,
                content_hash=hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
                markdown=markdown[:500_000], screenshot=shot, screenshot_mime=mime, tender_count=len(tenders),
            )
            session.add(snapshot)
            await session.flush()

            now = _now()
            new_ones: list[OppTender] = []
            for found in tenders:
                key = opp.tender_dedupe_key(found.get("reference"), found["title"])[:500]
                existing = (await session.execute(select(OppTender).where(
                    OppTender.tenant_id == source.tenant_id, OppTender.source_id == source.id,
                    OppTender.dedupe_key == key,
                ))).scalar_one_or_none()
                if existing:
                    _merge(existing, found, source.url, overwrite=True)
                    existing.last_seen_at = now
                    existing.updated_at = now
                else:
                    tender = OppTender(
                        tenant_id=source.tenant_id, source_id=source.id, snapshot_id=snapshot.id,
                        dedupe_key=key, title=found["title"], required_documents=[], document_links=[],
                        first_seen_at=now, last_seen_at=now, updated_at=now,
                    )
                    _merge(tender, found, source.url, overwrite=True)
                    session.add(tender)
                    new_ones.append(tender)
            await session.commit()

            # Fill documents / briefing from tenders' own pages: open tenders not
            # read yet, soonest closing first, a few per scan so every tender is
            # covered over successive scans without one scan running for ages.
            pending_detail = (await session.execute(
                select(OppTender).where(
                    OppTender.tenant_id == source.tenant_id, OppTender.source_id == source.id,
                    OppTender.detail_url.is_not(None), OppTender.detail_scanned.is_(False),
                    (OppTender.closing_at.is_(None)) | (OppTender.closing_at >= now),
                ).order_by(OppTender.closing_at.asc().nulls_last()).limit(_MAX_DETAIL_SCANS)
            )).scalars().all()
            for tender in pending_detail:
                try:
                    detail = await _extract_page(tender.detail_url, detail=True)
                    found = opp.normalize_tender({"title": tender.title, **(detail.get("json") or {})}) or {}
                    _merge(tender, found, tender.detail_url, overwrite=False)
                except Exception:  # a detail page failing never fails the scan
                    logger.warning("[opportunities] detail scan failed for %s", tender.detail_url)
                tender.detail_scanned = True
                await session.commit()

            source.last_status = "ok"
            source.last_error = None
            source.last_tender_count = len(tenders)
        except Exception as exc:  # recorded on the source; existing tenders are kept
            logger.exception("[opportunities] scan of source %s failed", source_id)
            await session.rollback()
            source = await session.get(OppSource, source_id)
            if source is None:
                return
            source.last_status = "failed"
            source.last_error = str(exc)[:500]
        source.last_scanned_at = _now()
        source.next_scan_at = _now() + timedelta(hours=source.scan_interval_hours)
        await session.commit()


async def _due_source_ids() -> list[uuid.UUID]:
    async with get_session_factory()() as session:
        rows = await session.execute(text(
            "SELECT id FROM opp_sources WHERE active AND next_scan_at <= now() "
            "AND (last_status <> 'scanning' "
            f"OR last_scanned_at < now() - interval '{_STALE_SCAN_MINUTES} minutes') "
            "ORDER BY next_scan_at LIMIT 5"
        ))
        return [r[0] for r in rows.all()]


async def run_tender_scheduler() -> None:
    """Every OPP_SCHEDULER_PERIOD_SECONDS, scan sources that are due. Runs in
    each uvicorn worker; _claim_source makes sure each scan happens once."""
    await asyncio.sleep(60)
    while True:
        try:
            for source_id in await _due_source_ids():
                await _scan_source(source_id)
        except Exception:
            logger.exception("[opportunities] tender scheduler tick failed")
        await asyncio.sleep(_SCHEDULER_PERIOD_SECONDS)


# ── source endpoints ──────────────────────────────────────────────────────

@router.get("/sources")
async def list_sources(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    sources = (await db.execute(
        select(OppSource).where(OppSource.tenant_id == tenant_id).order_by(desc(OppSource.created_at))
    )).scalars().all()
    counts = dict((await db.execute(
        select(OppTender.source_id, func.count()).where(OppTender.tenant_id == tenant_id).group_by(OppTender.source_id)
    )).all())
    latest = dict((await db.execute(
        select(OppSnapshot.source_id, OppSnapshot.id)
        .where(OppSnapshot.tenant_id == tenant_id, OppSnapshot.screenshot.is_not(None))
        .distinct(OppSnapshot.source_id)
        .order_by(OppSnapshot.source_id, desc(OppSnapshot.fetched_at))
    )).all())
    return [_source_dict(s, counts.get(s.id, 0), latest.get(s.id)) for s in sources]


@router.post("/sources", status_code=201)
async def create_source(
    body: SourceCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    try:
        url = opp.validate_source_url(body.url)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    duplicate = (await db.execute(
        select(OppSource.id).where(OppSource.tenant_id == tenant_id, OppSource.url == url)
    )).first()
    if duplicate:
        raise HTTPException(409, "That page is already being watched")
    source = OppSource(
        tenant_id=tenant_id, url=url, label=(body.label or "").strip() or None,
        scan_interval_hours=body.scan_interval_hours, next_scan_at=_now(), last_status="queued",
    )
    db.add(source)
    await db.commit()  # the scan job opens its own session and must see this row
    schedule_background(_scan_source(source.id))
    return _source_dict(source)


@router.patch("/sources/{source_id}")
async def patch_source(
    source_id: uuid.UUID,
    body: SourcePatch,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    source = await _get_source(db, tenant_id, source_id)
    if body.label is not None:
        source.label = body.label.strip() or None
    if body.active is not None:
        source.active = body.active
    if body.scan_interval_hours is not None:
        source.scan_interval_hours = body.scan_interval_hours
        if source.last_scanned_at:
            source.next_scan_at = source.last_scanned_at + timedelta(hours=body.scan_interval_hours)
    await db.flush()
    return _source_dict(source)


@router.delete("/sources/{source_id}", status_code=204)
async def delete_source(
    source_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    source = await _get_source(db, tenant_id, source_id)
    await db.delete(source)
    return Response(status_code=204)


@router.post("/sources/{source_id}/scan", status_code=202)
async def scan_source_now(
    source_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    source = await _get_source(db, tenant_id, source_id)
    if source.last_status == "scanning":
        return _source_dict(source)
    source.last_status = "queued"
    await db.commit()
    schedule_background(_scan_source(source.id))
    return _source_dict(source)


# ── tender endpoints ──────────────────────────────────────────────────────

@router.get("/tenders")
async def list_tenders(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
    status: Optional[Literal["new", "reviewing", "bidding", "skipped"]] = None,
    source_id: Optional[uuid.UUID] = None,
    include_closed: bool = False,
):
    query = select(OppTender, OppSource).join(OppSource, OppSource.id == OppTender.source_id).where(
        OppTender.tenant_id == tenant_id
    )
    if status:
        query = query.where(OppTender.status == status)
    if source_id:
        query = query.where(OppTender.source_id == source_id)
    if not include_closed:
        query = query.where((OppTender.closing_at.is_(None)) | (OppTender.closing_at >= _now()))
    query = query.order_by(OppTender.closing_at.asc().nulls_last(), desc(OppTender.first_seen_at))
    rows = (await db.execute(query)).all()
    return [_tender_dict(t, s) for t, s in rows]


@router.patch("/tenders/{tender_id}")
async def patch_tender(
    tender_id: uuid.UUID,
    body: TenderPatch,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    tender = await db.get(OppTender, tender_id)
    if tender is None or tender.tenant_id != tenant_id:
        raise HTTPException(404, "Tender not found")
    if body.status is not None:
        tender.status = body.status
    if body.sales_lead_id is not None:
        tender.sales_lead_id = body.sales_lead_id
    tender.updated_at = _now()
    await db.flush()
    return _tender_dict(tender)


@router.get("/snapshots/{snapshot_id}/screenshot")
async def get_snapshot_screenshot(
    snapshot_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    snapshot = await db.get(OppSnapshot, snapshot_id)
    if snapshot is None or snapshot.tenant_id != tenant_id or not snapshot.screenshot:
        raise HTTPException(404, "Screenshot not found")
    return Response(content=snapshot.screenshot, media_type=snapshot.screenshot_mime or "image/png",
                    headers={"Cache-Control": "private, max-age=86400"})
