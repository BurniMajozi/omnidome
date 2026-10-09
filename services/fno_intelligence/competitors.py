"""B. Competitor analysis: tracked competitors, scans, immutable snapshots, change detection.

A scan finds the pricing/promotion pages (Firecrawl /map, only when not supplied), scrapes each page
once with markdown + JSON extraction, normalises the plans and VERIFIES every extracted price against
the scraped page text (unverified prices are kept but flagged, and changes involving them are flagged).
Snapshots are insert-only; consecutive snapshots are diffed into analytics_competitor_changes.
Numbers are never produced by our LLM: it is only a fallback extractor when Firecrawl returned no JSON,
and its output goes through the same verification.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import uuid
from datetime import datetime, timedelta
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from services.common.auth import AuthContext, get_current_tenant_id
from services.common.background_tasks import schedule_background
from services.fno_intelligence import analytics_common as ac
from services.fno_intelligence import database
from services.fno_intelligence.analytics_models import (
    AiCompetitor, AiCompetitorChange, AiCompetitorSnapshot,
)

logger = logging.getLogger("fno_intelligence.competitors")
router = APIRouter(prefix="/competitors", tags=["Analytics: competitors"])

_STUCK_AFTER = timedelta(minutes=15)
MAX_PRICING_PAGES = 2
MAX_PROMO_PAGES = 1
SCAN_CREDIT_ESTIMATE = 1 + (MAX_PRICING_PAGES + MAX_PROMO_PAGES) * 5

PLAN_PROMPT = (
    "Extract every internet/connectivity plan with a listed price, and every active promotion or special offer. "
    "Copy numbers and price strings EXACTLY as printed on the page (price_text must be the literal text, e.g. "
    "'R 799 pm'); do not calculate, convert or round. Use null when something is not shown. Do not invent items; "
    "return empty lists if there are none."
)
_PLAN_PROPS = {
    "plan_name": {"type": "string"},
    "price_text": {"type": ["string", "null"]},
    "price_amount": {"type": ["number", "null"]},
    "currency": {"type": ["string", "null"]},
    "billing_period": {"type": ["string", "null"]},
    "speed_text": {"type": ["string", "null"]},
    "speed_down_mbps": {"type": ["number", "null"]},
    "data_text": {"type": ["string", "null"]},
    "contract_term": {"type": ["string", "null"]},
    "setup_fee_text": {"type": ["string", "null"]},
    "setup_fee_amount": {"type": ["number", "null"]},
    "promo_text": {"type": ["string", "null"]},
    "valid_until": {"type": ["string", "null"]},
}
PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "plans": {"type": "array", "items": {"type": "object", "properties": _PLAN_PROPS, "required": ["plan_name"]}},
        "promotions": {"type": "array", "items": {"type": "object", "properties": {
            "title": {"type": "string"}, "description": {"type": ["string", "null"]},
            "discount_text": {"type": ["string", "null"]}, "valid_until": {"type": ["string", "null"]},
        }, "required": ["title"]}},
    },
    "required": ["plans"],
}

_PRICING_STRONG = ("pricing", "prices", "price", "packages", "package", "plans", "plan", "rates", "tariff")
_PRICING_WEAK = ("fibre", "fiber", "internet", "products", "home", "business", "uncapped")
_PROMO_STRONG = ("promo", "promotion", "promotions", "special", "specials", "offer", "offers", "deals", "deal",
                 "discount", "black-friday", "campaign")
_EXCLUDE = re.compile(r"/(blog|news|careers?|jobs|terms|privacy|legal|login|signin|faq|support|help|contact|"
                      r"press|investors?|wp-content|wp-json|tag|category|author)(/|$|\.)|\.(pdf|jpg|png|zip)$", re.I)


# ── pure functions (unit tested) ──────────────────────────────────────────

def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def to_number(v: Any) -> Optional[float]:
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    t = re.sub(r"[^\d,.\-]", "", str(v).replace(" ", " "))
    if not t or not re.search(r"\d", t):
        return None
    if "," in t and "." in t:
        t = t.replace(",", "")
    elif "," in t:
        t = t.replace(",", ".") if re.search(r",\d{1,2}$", t) else t.replace(",", "")
    try:
        return float(t)
    except ValueError:
        return None


def _amount_pattern(amount: float) -> re.Pattern:
    whole, frac = divmod(round(abs(amount), 2), 1)
    digits = str(int(whole))
    groups = []
    while digits:
        groups.insert(0, digits[-3:])
        digits = digits[:-3]
    body = r"[ ,. ]?".join(re.escape(g) for g in groups) if len(groups) > 1 else re.escape(groups[0])
    cents = int(round(frac * 100))
    tail = rf"[.,]{cents:02d}" if cents else r"(?:[.,]00)?"
    # not part of a longer number on either side (incl. thousand-grouped prefixes like '1 299')
    return re.compile(rf"(?<!\d)(?<!\d[ ,. ]){body}{tail}(?![\d])(?![.,]\d)")


def price_in_text(amount: Optional[float], page_text: str, price_text: Optional[str] = None) -> bool:
    """True only if the extracted price literally appears in the page text."""
    if amount is None or not page_text:
        return False
    haystack = ac.norm_ws(page_text)
    if price_text:
        pt = ac.norm_ws(price_text)
        n = to_number(pt)
        if pt and pt.lower() in haystack.lower() and n is not None and abs(n - amount) < 0.005:
            return True
    return bool(_amount_pattern(amount).search(haystack))


def make_plan_key(p: dict) -> str:
    return f"{slug(p['plan_name'])}|{slug(p.get('billing_period') or 'monthly')}"


def _s(v: Any, n: int) -> Optional[str]:
    if v is None or isinstance(v, (dict, list)):
        return None
    t = ac.norm_ws(str(v))
    return t[:n] or None


def normalize_extraction(raw: Any, source_url: str, page_text: str) -> tuple[list[dict], list[dict]]:
    """Clean the extractor output and verify numbers against the page text. Returns (plans, promotions)."""
    raw = raw if isinstance(raw, dict) else {}
    plans, seen = [], set()
    for p in raw.get("plans") or []:
        if not isinstance(p, dict):
            continue
        name = _s(p.get("plan_name"), 200)
        if not name:
            continue
        amount = to_number(p.get("price_amount"))
        ptext = _s(p.get("price_text"), 80)
        if amount is None and ptext:
            amount = to_number(ptext)
        setup_amt = to_number(p.get("setup_fee_amount"))
        stext = _s(p.get("setup_fee_text"), 80)
        cur = _s(p.get("currency"), 8)
        cur = cur.upper() if cur else None
        if cur is None and ptext and re.search(r"(^|\s)R\s?\d|ZAR", ptext):
            cur = "ZAR"
        period = _s(p.get("billing_period"), 30)
        plan = {
            "plan_name": name, "price_amount": amount, "price_text": ptext, "currency": cur,
            "billing_period": period.lower() if period else None,
            "speed_text": _s(p.get("speed_text"), 60), "speed_down_mbps": to_number(p.get("speed_down_mbps")),
            "data_text": _s(p.get("data_text"), 60), "contract_term": _s(p.get("contract_term"), 60),
            "setup_fee_amount": setup_amt, "setup_fee_text": stext,
            "promo_text": _s(p.get("promo_text"), 300), "valid_until": _s(p.get("valid_until"), 60),
            "price_verified": price_in_text(amount, page_text, ptext),
            "setup_fee_verified": price_in_text(setup_amt, page_text, stext) if setup_amt is not None else None,
            "source_url": source_url,
        }
        plan["plan_key"] = make_plan_key(plan)
        if plan["plan_key"] in seen:
            continue
        seen.add(plan["plan_key"])
        plans.append(plan)
    promos, pseen = [], set()
    lowered = ac.norm_ws(page_text).lower()
    for p in raw.get("promotions") or []:
        if not isinstance(p, dict):
            continue
        title = _s(p.get("title"), 200)
        if not title or slug(title) in pseen:
            continue
        pseen.add(slug(title))
        promos.append({
            "promo_key": slug(title), "title": title, "description": _s(p.get("description"), 500),
            "discount_text": _s(p.get("discount_text"), 100), "valid_until": _s(p.get("valid_until"), 60),
            "title_on_page": ac.norm_ws(title).lower() in lowered, "source_url": source_url,
        })
    return plans, promos


def _money(plan: dict) -> str:
    amt = plan.get("price_amount")
    if amt is None:
        return plan.get("price_text") or ""
    cur = plan.get("currency") or ""
    return f"{cur} {amt:g}".strip() + (f" / {plan['billing_period']}" if plan.get("billing_period") else "")


_ATTR_FIELDS = (("speed_down_mbps", "speed (Mbps)"), ("contract_term", "contract term"),
                ("setup_fee_amount", "setup fee"), ("data_text", "data allowance"))


def diff_snapshots(prev_plans: list[dict], new_plans: list[dict], prev_promos: list[dict],
                   new_promos: list[dict], ok_urls: set[str]) -> list[dict]:
    """Changes between consecutive snapshots. Removals are only reported for items whose source page
    was successfully re-fetched, so a failed page never looks like 'everything was removed'."""
    out: list[dict] = []
    p_idx = {p["plan_key"]: p for p in prev_plans}
    n_idx = {p["plan_key"]: p for p in new_plans}
    for key, new in n_idx.items():
        old = p_idx.get(key)
        if old is None:
            out.append({"change_type": "new_plan", "subject": new["plan_name"], "old_value": None,
                        "new_value": _money(new), "currency": new.get("currency"),
                        "verified": bool(new.get("price_verified")), "source_url": new.get("source_url")})
            continue
        a, b = old.get("price_amount"), new.get("price_amount")
        if a is not None and b is not None and abs(a - b) >= 0.005:
            out.append({"change_type": "price_up" if b > a else "price_down", "subject": new["plan_name"],
                        "old_value": f"{a:g}", "new_value": f"{b:g}", "abs_change": round(b - a, 2),
                        "pct_change": round((b - a) / a * 100, 2) if a else None,
                        "currency": new.get("currency") or old.get("currency"),
                        "verified": bool(old.get("price_verified") and new.get("price_verified")),
                        "source_url": new.get("source_url")})
        for f, label in _ATTR_FIELDS:
            x, y = old.get(f), new.get(f)
            if x is not None and y is not None and str(x) != str(y):
                out.append({"change_type": "plan_attribute_change", "subject": f"{new['plan_name']} - {label}",
                            "old_value": str(x), "new_value": str(y), "currency": new.get("currency"),
                            "verified": False, "source_url": new.get("source_url")})
    for key, old in p_idx.items():
        if key not in n_idx and old.get("source_url") in ok_urls:
            out.append({"change_type": "removed_plan", "subject": old["plan_name"], "old_value": _money(old),
                        "new_value": None, "currency": old.get("currency"),
                        "verified": bool(old.get("price_verified")), "source_url": old.get("source_url")})
    pp = {p["promo_key"]: p for p in prev_promos}
    nn = {p["promo_key"]: p for p in new_promos}
    for key, new in nn.items():
        old = pp.get(key)
        if old is None:
            out.append({"change_type": "new_promotion", "subject": new["title"], "old_value": None,
                        "new_value": new.get("discount_text") or new.get("description"), "verified": bool(new.get("title_on_page")),
                        "source_url": new.get("source_url")})
        elif (old.get("valid_until") or None) != (new.get("valid_until") or None):
            out.append({"change_type": "promotion_changed", "subject": new["title"],
                        "old_value": old.get("valid_until"), "new_value": new.get("valid_until"),
                        "verified": bool(new.get("title_on_page")), "source_url": new.get("source_url")})
    for key, old in pp.items():
        if key not in nn and old.get("source_url") in ok_urls:
            out.append({"change_type": "ended_promotion", "subject": old["title"],
                        "old_value": old.get("discount_text") or old.get("description"), "new_value": None,
                        "verified": bool(old.get("title_on_page")), "source_url": old.get("source_url")})
    return out


def _url_score(url: str, title: str, strong: tuple, weak: tuple = ()) -> int:
    from urllib.parse import urlsplit
    path = urlsplit(url).path.lower()
    if _EXCLUDE.search(path) or path in ("", "/"):
        return 0
    hay = re.split(r"[^a-z0-9]+", path + " " + (title or "").lower())
    return 3 * sum(1 for w in strong if w in hay) + sum(1 for w in weak if w in hay)


def pick_pages(website: str, links: list[dict]) -> dict[str, list[str]]:
    """Choose pricing and promotion pages from /map results (same site only)."""
    cands = []
    for l in links:
        url = ac.plain_result_url(l.get("url") if isinstance(l, dict) else l)
        if url and ac.same_site(url, website):
            cands.append((url, str(l.get("title") or "") if isinstance(l, dict) else ""))
    pricing = sorted(((_url_score(u, t, _PRICING_STRONG, _PRICING_WEAK), u) for u, t in cands), reverse=True)
    promo = sorted(((_url_score(u, t, _PROMO_STRONG), u) for u, t in cands), reverse=True)
    pr = [u for s, u in pricing if s >= 3][:MAX_PRICING_PAGES]
    pm = [u for s, u in promo if s >= 3 and u not in pr][:MAX_PROMO_PAGES]
    return {"pricing": pr, "promo": pm}


def snapshot_hash(plans: list[dict], promos: list[dict]) -> str:
    core = [(p["plan_key"], p.get("price_amount"), p.get("speed_down_mbps"), p.get("contract_term")) for p in plans]
    return ac.sha256(json.dumps([sorted(core, key=str), sorted(x["promo_key"] for x in promos)], default=str))


# ── scanning ──────────────────────────────────────────────────────────────

LLM_EXTRACT_SYSTEM = (
    "You extract internet plans and promotions from a web page for a pricing database. Copy every number and "
    "price string EXACTLY as printed; never calculate or round. Use null when unknown. Never invent items.\n"
    + ac.UNTRUSTED_RULES
)


async def llm_extract(markdown: str, url: str) -> Optional[dict]:
    """Fallback only when Firecrawl returned no JSON. Output still goes through verification."""
    user = ("Return JSON {\"plans\": [{plan_name, price_text, price_amount, currency, billing_period, speed_text, "
            "speed_down_mbps, data_text, contract_term, setup_fee_text, setup_fee_amount, promo_text, valid_until}], "
            "\"promotions\": [{title, description, discount_text, valid_until}]}.\n\n"
            + ac.wrap_source("P1", url, markdown, 12000))
    res = await ac.llm_complete(LLM_EXTRACT_SYSTEM, user, max_tokens=3000)
    parsed = ac.parse_json_loose(res[0]) if res else None
    return parsed if isinstance(parsed, dict) else None


async def fetch_page(mf: ac.MeteredFirecrawl, url: str, kind: str) -> dict:
    page = {"url": url, "kind": kind, "fetched_at": ac.now().isoformat(), "status": "ok", "error": None,
            "chars": 0, "content_hash": None, "excerpt_hash": None, "extraction": None}
    try:
        raw = await mf.scrape(url, json_schema=PLAN_SCHEMA, json_prompt=PLAN_PROMPT)
        data = raw.get("data") or {}
        md = data.get("markdown") or ""
        page["markdown"], page["json"] = md, data.get("json")
        page["chars"] = len(md)
        page["content_hash"] = ac.sha256(md)
        page["excerpt_hash"] = ac.sha256(ac.norm_ws(md)[:2000])
        if not md.strip():
            page.update(status="failed", error="Page returned no readable text")
    except ac.CreditCapExceeded:
        raise
    except Exception as exc:
        page.update(status="failed", error=ac.err_text(exc), markdown="", json=None)
    return page


async def collect_pages(mf: ac.MeteredFirecrawl, comp: dict) -> list[dict]:
    pricing = [comp["pricing_page_url"]] if comp.get("pricing_page_url") else []
    promo = [comp["promo_page_url"]] if comp.get("promo_page_url") else []
    if not pricing or not promo:
        try:
            mapped = await mf.map(comp["website"], search="pricing plans packages promotions specials deals", limit=100)
            links = mapped.get("links") or (mapped.get("data") or {}).get("links") or []
            found = pick_pages(comp["website"], links)
            for u in found["pricing"] if not pricing else []:
                if await ac.is_safe_to_fetch(u):
                    pricing.append(u)
            for u in found["promo"] if not promo else []:
                if await ac.is_safe_to_fetch(u):
                    promo.append(u)
        except ac.CreditCapExceeded:
            raise
        except Exception as exc:
            logger.info("map failed for %s: %s", comp["website"], exc)
    if not pricing and not promo:
        pricing = [comp["website"]]  # nothing discovered: read the home page
    pages = []
    for kind, urls in (("pricing", pricing), ("promo", promo)):
        for u in urls:
            pages.append(await fetch_page(mf, u, kind))
    return pages


async def extract_from_pages(pages: list[dict]) -> tuple[list[dict], list[dict], str]:
    plans, promos, methods = [], [], set()
    pk, prk = set(), set()
    for pg in pages:
        if pg["status"] != "ok":
            continue
        raw = pg.get("json") if isinstance(pg.get("json"), dict) else None
        method = "firecrawl_json"
        if not raw or not (raw.get("plans") or raw.get("promotions")):
            raw, method = await llm_extract(pg["markdown"], pg["url"]), "llm_markdown"
        p, pr = normalize_extraction(raw, pg["url"], pg["markdown"])
        pg["extraction"] = method if (p or pr) else "none"
        if p or pr:
            methods.add(method)
        for x in p:
            if x["plan_key"] not in pk:
                pk.add(x["plan_key"])
                plans.append(x)
        for x in pr:
            if x["promo_key"] not in prk:
                prk.add(x["promo_key"])
                promos.append(x)
    return plans, promos, ("+".join(sorted(methods)) or "none")


def _provenance(pg: dict) -> dict:
    return {k: pg[k] for k in ("url", "kind", "fetched_at", "status", "error", "chars", "content_hash",
                               "excerpt_hash", "extraction")}


async def claim_scan(db: AsyncSession, tenant_id: uuid.UUID, competitor_id: uuid.UUID) -> bool:
    t = ac.now()
    res = await db.execute(
        update(AiCompetitor)
        .where(AiCompetitor.id == competitor_id, AiCompetitor.tenant_id == tenant_id,
               (AiCompetitor.scan_status != "scanning") | (AiCompetitor.scan_started_at.is_(None))
               | (AiCompetitor.scan_started_at < t - _STUCK_AFTER))
        .values(scan_status="scanning", scan_started_at=t, last_error=None))
    await db.commit()
    return res.rowcount == 1


async def execute_scan(tenant_id: uuid.UUID, competitor_id: uuid.UUID) -> dict:
    """Run a scan whose claim was already taken. Own DB sessions; records the outcome on the competitor."""
    async with database.get_session_factory()() as db:
        c = await db.get(AiCompetitor, competitor_id)
        if c is None or c.tenant_id != tenant_id:
            return {"status": "missing"}
        comp = {"website": c.website, "pricing_page_url": c.pricing_page_url, "promo_page_url": c.promo_page_url}
    mf = ac.MeteredFirecrawl(tenant_id, "competitor", competitor_id)
    status, error, new_changes, snap_id = "failed", None, 0, None
    try:
        pages = await collect_pages(mf, comp)
        ok = [p for p in pages if p["status"] == "ok"]
        if not ok:
            raise RuntimeError("None of the competitor pages could be read: "
                               + "; ".join(f"{p['url']}: {p['error']}" for p in pages)[:300])
        plans, promos, method = await extract_from_pages(pages)
        async with database.get_session_factory()() as db:
            if not plans and not promos:
                status, error = "no_data", "Pages were read but no priced plans or promotions could be found on them."
            else:
                prev = (await db.execute(select(AiCompetitorSnapshot).where(
                    AiCompetitorSnapshot.competitor_id == competitor_id,
                    AiCompetitorSnapshot.tenant_id == tenant_id)
                    .order_by(desc(AiCompetitorSnapshot.scanned_at)).limit(1))).scalar_one_or_none()
                snap = AiCompetitorSnapshot(
                    tenant_id=tenant_id, competitor_id=competitor_id, scanned_at=ac.now(),
                    pages=[_provenance(p) for p in pages], plans=plans, promotions=promos,
                    content_hash=snapshot_hash(plans, promos), extraction_method=method)
                db.add(snap)
                await db.flush()
                snap_id = snap.id
                if prev is not None:
                    ok_urls = {p["url"] for p in ok}
                    for d in diff_snapshots(prev.plans or [], plans, prev.promotions or [], promos, ok_urls):
                        db.add(AiCompetitorChange(tenant_id=tenant_id, competitor_id=competitor_id,
                                                  snapshot_id=snap.id, previous_snapshot_id=prev.id, **d))
                        new_changes += 1
                status = "ok"
            await db.commit()
    except Exception as exc:
        error = ac.err_text(exc)
        logger.warning("competitor scan %s failed: %s", competitor_id, error)
    async with database.get_session_factory()() as db:
        c = await db.get(AiCompetitor, competitor_id)
        if c is not None:
            c.scan_status, c.last_error, c.last_scanned_at = status, error, ac.now()
            await db.commit()
    return {"status": status, "error": error, "new_changes": new_changes, "snapshot_id": str(snap_id) if snap_id else None,
            "credits": mf.spent}


# ── optional daily scheduler (default OFF) ────────────────────────────────

def scheduler_enabled() -> bool:
    return os.getenv("ANALYTICS_COMPETITOR_SCHEDULER_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}


async def run_competitor_scheduler() -> None:
    """Re-scan active competitors not scanned within ANALYTICS_COMPETITOR_SCAN_INTERVAL_HOURS (default 24).
    Returns immediately unless ANALYTICS_COMPETITOR_SCHEDULER_ENABLED=true. Own sessions per scan; a tenant
    at its credit cap is skipped, never overrun."""
    if not scheduler_enabled():
        return
    interval = float(os.getenv("ANALYTICS_COMPETITOR_SCAN_INTERVAL_HOURS", "24"))
    period = int(os.getenv("ANALYTICS_COMPETITOR_SCHEDULER_PERIOD_SECONDS", "3600"))
    await asyncio.sleep(120)
    while True:
        try:
            cutoff = ac.now() - timedelta(hours=interval)
            async with database.get_session_factory()() as db:
                rows = (await db.execute(select(AiCompetitor.tenant_id, AiCompetitor.id).where(
                    AiCompetitor.active.is_(True),
                    (AiCompetitor.last_scanned_at.is_(None)) | (AiCompetitor.last_scanned_at < cutoff)).limit(20))).all()
            for tenant_id, cid in rows:
                try:
                    await ac.check_headroom(tenant_id, SCAN_CREDIT_ESTIMATE)
                except ac.CreditCapExceeded:
                    continue
                async with database.get_session_factory()() as db:
                    if not await claim_scan(db, tenant_id, cid):
                        continue
                await execute_scan(tenant_id, cid)
        except Exception:
            logger.exception("competitor scheduler tick failed")
        await asyncio.sleep(period)


async def sweep_stuck(db: AsyncSession) -> int:
    cutoff = ac.now() - _STUCK_AFTER
    rows = (await db.execute(select(AiCompetitor).where(
        AiCompetitor.scan_status == "scanning", AiCompetitor.scan_started_at < cutoff))).scalars().all()
    for c in rows:
        c.scan_status, c.last_error = "failed", "Interrupted (service restarted) - scan again."
    return len(rows)


# ── routes ────────────────────────────────────────────────────────────────

def max_competitors() -> int:
    try:
        return max(1, int(os.getenv("ANALYTICS_MAX_COMPETITORS_PER_TENANT", "25")))
    except ValueError:
        return 25


class CompetitorIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    website: str = Field(..., min_length=8, max_length=2000)
    pricing_page_url: Optional[str] = Field(None, max_length=2000)
    promo_page_url: Optional[str] = Field(None, max_length=2000)
    social_urls: Optional[list[str]] = Field(None, max_length=6)


class CompetitorPatch(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    website: Optional[str] = Field(None, min_length=8, max_length=2000)
    pricing_page_url: Optional[str] = Field(None, max_length=2000)
    promo_page_url: Optional[str] = Field(None, max_length=2000)
    social_urls: Optional[list[str]] = Field(None, max_length=6)
    active: Optional[bool] = None


async def _validate_urls(data: dict) -> None:
    for f in ("website", "pricing_page_url", "promo_page_url"):
        if data.get(f):
            await ac.check_public_url(data[f], field=f)
    for i, u in enumerate(data.get("social_urls") or []):
        await ac.check_public_url(u, field=f"social_urls[{i}]")


def comp_dict(c: AiCompetitor) -> dict:
    return {
        "id": str(c.id), "name": c.name, "website": c.website, "pricing_page_url": c.pricing_page_url,
        "promo_page_url": c.promo_page_url, "social_urls": c.social_urls or [], "active": c.active,
        "scan_status": c.scan_status, "last_error": c.last_error,
        "last_scanned_at": c.last_scanned_at.isoformat() if c.last_scanned_at else None,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


def snap_dict(s: AiCompetitorSnapshot, *, full: bool = True) -> dict:
    d = {"id": str(s.id), "competitor_id": str(s.competitor_id), "scanned_at": s.scanned_at.isoformat(),
         "content_hash": s.content_hash, "extraction_method": s.extraction_method,
         "plans_count": len(s.plans or []), "promotions_count": len(s.promotions or [])}
    if full:
        d.update(pages=s.pages, plans=s.plans, promotions=s.promotions)
    return d


def change_dict(ch: AiCompetitorChange, name: Optional[str] = None) -> dict:
    return {
        "id": str(ch.id), "competitor_id": str(ch.competitor_id), "competitor_name": name,
        "snapshot_id": str(ch.snapshot_id), "previous_snapshot_id": str(ch.previous_snapshot_id),
        "change_type": ch.change_type, "subject": ch.subject, "old_value": ch.old_value, "new_value": ch.new_value,
        "abs_change": ch.abs_change, "pct_change": ch.pct_change, "currency": ch.currency, "verified": ch.verified,
        "source_url": ch.source_url, "detected_at": ch.detected_at.isoformat() if ch.detected_at else None,
    }


async def _get(db: AsyncSession, tenant_id: uuid.UUID, cid: uuid.UUID) -> AiCompetitor:
    c = await db.get(AiCompetitor, cid)
    if c is None or c.tenant_id != tenant_id:
        raise HTTPException(404, "Competitor not found")
    return c


async def _latest_snapshot(db: AsyncSession, tenant_id: uuid.UUID, cid: uuid.UUID) -> Optional[AiCompetitorSnapshot]:
    return (await db.execute(select(AiCompetitorSnapshot).where(
        AiCompetitorSnapshot.tenant_id == tenant_id, AiCompetitorSnapshot.competitor_id == cid)
        .order_by(desc(AiCompetitorSnapshot.scanned_at)).limit(1))).scalar_one_or_none()


@router.post("", status_code=201)
async def create_competitor(body: CompetitorIn, auth: AuthContext = Depends(ac.require_analyst),
                            db: AsyncSession = Depends(database.get_session)):
    data = body.model_dump()
    await _validate_urls(data)
    count = (await db.execute(select(func.count()).select_from(AiCompetitor).where(
        AiCompetitor.tenant_id == auth.tenant_id))).scalar_one()
    if count >= max_competitors():
        raise HTTPException(409, f"Competitor limit reached ({max_competitors()} per tenant)")
    if (await db.execute(select(AiCompetitor.id).where(
            AiCompetitor.tenant_id == auth.tenant_id, func.lower(AiCompetitor.name) == body.name.strip().lower()))).first():
        raise HTTPException(409, "A competitor with that name already exists")
    c = AiCompetitor(tenant_id=auth.tenant_id, **{**data, "name": body.name.strip()})
    db.add(c)
    await db.flush()
    await db.refresh(c)
    return comp_dict(c)


@router.get("")
async def list_competitors(tenant_id: uuid.UUID = Depends(get_current_tenant_id),
                           _: AuthContext = Depends(ac.require_viewer), db: AsyncSession = Depends(database.get_session)):
    rows = (await db.execute(select(AiCompetitor).where(AiCompetitor.tenant_id == tenant_id)
                             .order_by(AiCompetitor.name))).scalars().all()
    return [comp_dict(c) for c in rows]


@router.get("/overview")
async def overview(tenant_id: uuid.UUID = Depends(get_current_tenant_id),
                   _: AuthContext = Depends(ac.require_viewer), db: AsyncSession = Depends(database.get_session)):
    comps = (await db.execute(select(AiCompetitor).where(AiCompetitor.tenant_id == tenant_id)
                              .order_by(AiCompetitor.name))).scalars().all()
    out = []
    for c in comps:
        snap = await _latest_snapshot(db, tenant_id, c.id)
        ch = (await db.execute(select(AiCompetitorChange).where(
            AiCompetitorChange.tenant_id == tenant_id, AiCompetitorChange.competitor_id == c.id)
            .order_by(desc(AiCompetitorChange.detected_at)).limit(3))).scalars().all()
        out.append({**comp_dict(c), "plans_count": len(snap.plans or []) if snap else 0,
                    "promotions_count": len(snap.promotions or []) if snap else 0,
                    "latest_snapshot_at": snap.scanned_at.isoformat() if snap else None,
                    "latest_changes": [change_dict(x, c.name) for x in ch]})
    return {"competitors": out, "count": len(out)}


@router.get("/activity")
async def activity(limit: int = Query(50, ge=1, le=200), tenant_id: uuid.UUID = Depends(get_current_tenant_id),
                   _: AuthContext = Depends(ac.require_viewer), db: AsyncSession = Depends(database.get_session)):
    """Newest-first feed of detected changes and completed scans across all competitors."""
    changes = (await db.execute(
        select(AiCompetitorChange, AiCompetitor.name).join(AiCompetitor, AiCompetitor.id == AiCompetitorChange.competitor_id)
        .where(AiCompetitorChange.tenant_id == tenant_id)
        .order_by(desc(AiCompetitorChange.detected_at)).limit(limit))).all()
    snaps = (await db.execute(
        select(AiCompetitorSnapshot, AiCompetitor.name).join(AiCompetitor, AiCompetitor.id == AiCompetitorSnapshot.competitor_id)
        .where(AiCompetitorSnapshot.tenant_id == tenant_id)
        .order_by(desc(AiCompetitorSnapshot.scanned_at)).limit(limit))).all()
    feed = [{"kind": "change", "at": ch.detected_at.isoformat(), **change_dict(ch, n)} for ch, n in changes]
    feed += [{"kind": "scan", "at": s.scanned_at.isoformat(), "competitor_id": str(s.competitor_id),
              "competitor_name": n, "snapshot_id": str(s.id), "plans_count": len(s.plans or []),
              "promotions_count": len(s.promotions or [])} for s, n in snaps]
    feed.sort(key=lambda x: x["at"], reverse=True)
    return {"items": feed[:limit]}


@router.get("/{competitor_id}")
async def get_competitor(competitor_id: uuid.UUID, tenant_id: uuid.UUID = Depends(get_current_tenant_id),
                         _: AuthContext = Depends(ac.require_viewer), db: AsyncSession = Depends(database.get_session)):
    return comp_dict(await _get(db, tenant_id, competitor_id))


@router.put("/{competitor_id}")
async def update_competitor(competitor_id: uuid.UUID, body: CompetitorPatch, auth: AuthContext = Depends(ac.require_analyst),
                            db: AsyncSession = Depends(database.get_session)):
    c = await _get(db, auth.tenant_id, competitor_id)
    data = body.model_dump(exclude_unset=True)
    await _validate_urls(data)
    if data.get("name") and data["name"].strip().lower() != c.name.lower():
        if (await db.execute(select(AiCompetitor.id).where(
                AiCompetitor.tenant_id == auth.tenant_id, func.lower(AiCompetitor.name) == data["name"].strip().lower()))).first():
            raise HTTPException(409, "A competitor with that name already exists")
    for k, v in data.items():
        if k == "name" and v:
            c.name = v.strip()
        elif k in ("pricing_page_url", "promo_page_url"):
            setattr(c, k, v or None)  # null/empty clears it (back to auto-discovery)
        elif v is not None:
            setattr(c, k, v)
    await db.flush()
    return comp_dict(c)


@router.delete("/{competitor_id}", status_code=204)
async def delete_competitor(competitor_id: uuid.UUID, tenant_id: uuid.UUID = Depends(get_current_tenant_id),
                            _: AuthContext = Depends(ac.require_admin), db: AsyncSession = Depends(database.get_session)):
    c = await _get(db, tenant_id, competitor_id)
    for model in (AiCompetitorChange, AiCompetitorSnapshot):  # explicit: SQLite/test DBs do not cascade
        for row in (await db.execute(select(model).where(model.competitor_id == c.id))).scalars().all():
            await db.delete(row)
    await db.delete(c)


@router.post("/{competitor_id}/scan", status_code=202)
async def scan_competitor(competitor_id: uuid.UUID, auth: AuthContext = Depends(ac.require_analyst),
                          db: AsyncSession = Depends(database.get_session)):
    c = await _get(db, auth.tenant_id, competitor_id)
    await ac.check_headroom(auth.tenant_id, SCAN_CREDIT_ESTIMATE, db)
    await db.commit()
    async with database.get_session_factory()() as own:
        if not await claim_scan(own, auth.tenant_id, competitor_id):
            raise HTTPException(409, "A scan of this competitor is already running")
    schedule_background(execute_scan(auth.tenant_id, competitor_id))
    return {"competitor_id": str(c.id), "scan_status": "scanning",
            "estimated_credits": SCAN_CREDIT_ESTIMATE, "message": "Scan started; poll GET /competitors/{id}."}


@router.get("/{competitor_id}/snapshots")
async def list_snapshots(competitor_id: uuid.UUID, limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0),
                         tenant_id: uuid.UUID = Depends(get_current_tenant_id),
                         _: AuthContext = Depends(ac.require_viewer), db: AsyncSession = Depends(database.get_session)):
    await _get(db, tenant_id, competitor_id)
    q = select(AiCompetitorSnapshot).where(AiCompetitorSnapshot.tenant_id == tenant_id,
                                           AiCompetitorSnapshot.competitor_id == competitor_id)
    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    rows = (await db.execute(q.order_by(desc(AiCompetitorSnapshot.scanned_at)).limit(limit).offset(offset))).scalars().all()
    return {"total": total, "limit": limit, "offset": offset, "items": [snap_dict(s) for s in rows]}


@router.get("/{competitor_id}/changes")
async def list_changes(competitor_id: uuid.UUID, change_type: Optional[str] = None,
                       limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
                       tenant_id: uuid.UUID = Depends(get_current_tenant_id),
                       _: AuthContext = Depends(ac.require_viewer), db: AsyncSession = Depends(database.get_session)):
    c = await _get(db, tenant_id, competitor_id)
    q = select(AiCompetitorChange).where(AiCompetitorChange.tenant_id == tenant_id,
                                         AiCompetitorChange.competitor_id == competitor_id)
    if change_type:
        q = q.where(AiCompetitorChange.change_type == change_type)
    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    rows = (await db.execute(q.order_by(desc(AiCompetitorChange.detected_at)).limit(limit).offset(offset))).scalars().all()
    return {"total": total, "limit": limit, "offset": offset, "items": [change_dict(x, c.name) for x in rows]}


@router.get("/{competitor_id}/pricing-history")
async def pricing_history(competitor_id: uuid.UUID, limit: int = Query(120, ge=1, le=500),
                          tenant_id: uuid.UUID = Depends(get_current_tenant_id),
                          _: AuthContext = Depends(ac.require_viewer), db: AsyncSession = Depends(database.get_session)):
    """One time series per plan across the most recent `limit` snapshots (oldest first)."""
    await _get(db, tenant_id, competitor_id)
    snaps = (await db.execute(select(AiCompetitorSnapshot).where(
        AiCompetitorSnapshot.tenant_id == tenant_id, AiCompetitorSnapshot.competitor_id == competitor_id)
        .order_by(desc(AiCompetitorSnapshot.scanned_at)).limit(limit))).scalars().all()
    series: dict[str, dict] = {}
    for s in reversed(snaps):
        for p in s.plans or []:
            e = series.setdefault(p["plan_key"], {"plan_key": p["plan_key"], "plan_name": p["plan_name"],
                                                  "currency": p.get("currency"), "points": []})
            e["points"].append({"scanned_at": s.scanned_at.isoformat(), "snapshot_id": str(s.id),
                                "price_amount": p.get("price_amount"), "price_verified": p.get("price_verified"),
                                "source_url": p.get("source_url")})
    return {"competitor_id": str(competitor_id), "snapshots_considered": len(snaps), "plans": list(series.values())}


@router.get("/{competitor_id}/promotions")
async def promotions(competitor_id: uuid.UUID, tenant_id: uuid.UUID = Depends(get_current_tenant_id),
                     _: AuthContext = Depends(ac.require_viewer), db: AsyncSession = Depends(database.get_session)):
    await _get(db, tenant_id, competitor_id)
    snap = await _latest_snapshot(db, tenant_id, competitor_id)
    ended = (await db.execute(select(AiCompetitorChange).where(
        AiCompetitorChange.tenant_id == tenant_id, AiCompetitorChange.competitor_id == competitor_id,
        AiCompetitorChange.change_type == "ended_promotion").order_by(desc(AiCompetitorChange.detected_at)).limit(50))).scalars().all()
    return {"as_of": snap.scanned_at.isoformat() if snap else None,
            "active": (snap.promotions if snap else []) or [],
            "plan_promos": [{"plan_name": p["plan_name"], "promo_text": p["promo_text"], "valid_until": p.get("valid_until"),
                             "source_url": p.get("source_url")} for p in ((snap.plans if snap else []) or []) if p.get("promo_text")],
            "ended": [{"title": x.subject, "ended_detected_at": x.detected_at.isoformat() if x.detected_at else None,
                       "last_seen_value": x.old_value} for x in ended]}
