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
import random
import re
import uuid
from datetime import datetime, timedelta, timezone
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


# ── auto-scan scheduling (pure helpers, unit tested) ──────────────────────

SCAN_INTERVALS = (12, 24, 168, 720)  # hours: 12h, daily, weekly, monthly (null = manual only)
_SECRET_RE = re.compile(r"(?i)(bearer\s+[\w\-.~+/=]+|\bfc-[\w-]+|(?:api[_-]?key|token|secret|password)=[^\s&]+|"
                        r"https?://[^\s]*[?&](?:key|token|apikey)=[^\s&]+)")


def _env_num(key: str, default: float, minimum: float = 0) -> float:
    try:
        return max(minimum, float(os.getenv(key, str(default))))
    except ValueError:
        return default


def max_consecutive_failures() -> int:
    return int(_env_num("ANALYTICS_COMPETITOR_MAX_FAILURES", 5, 1))


def sanitize_error(msg: Optional[str], limit: int = 240) -> Optional[str]:
    """Short, single-line, secret-free error text for the UI."""
    if not msg:
        return None
    t = _SECRET_RE.sub("[redacted]", ac.norm_ws(str(msg)))
    return (t[: limit - 1] + "…") if len(t) > limit else t


def aware(dt: Optional[datetime]) -> Optional[datetime]:
    """SQLite hands back naive datetimes; everything we store is UTC."""
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _jitter(interval_hours: float, rand, max_minutes: float = 30) -> timedelta:
    """Up to 10% of the interval (max `max_minutes`) so tenants do not all fire at once."""
    return timedelta(minutes=rand() * min(0.1 * interval_hours * 60, max_minutes))


def next_period_start(now: datetime, scope: str) -> datetime:
    if scope == "monthly":
        m = ac._month_start(now)
        return m.replace(year=m.year + 1, month=1) if m.month == 12 else m.replace(month=m.month + 1)
    return ac._day_start(now) + timedelta(days=1)


# ── schedule: the USER chooses when (Africa/Johannesburg local time); default is manual only ──

TENANT_TZ_NAME = "Africa/Johannesburg"
FREQUENCIES = ("12h", "daily", "weekly", "monthly")
INTERVAL_OF = {"12h": 12, "daily": 24, "weekly": 168, "monthly": 720}
FREQ_OF_INTERVAL = {v: k for k, v in INTERVAL_OF.items()}
SCANS_PER_MONTH = {"12h": 60.0, "daily": 30.0, "weekly": 4.3, "monthly": 1.0}
DEFAULT_TIME = "06:00"
_TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def _tz():
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(TENANT_TZ_NAME)
    except Exception:  # tzdata missing (e.g. Windows): South Africa has no DST, UTC+2 is exact
        return timezone(timedelta(hours=2))


def normalize_schedule(frequency: Optional[str], time_: Optional[str] = None, weekday: Optional[int] = None,
                       day_of_month: Optional[int] = None) -> dict:
    """Validate and normalise a schedule. frequency None/'off'/'manual' = manual only. Raises ValueError."""
    if frequency in (None, "", "off", "manual"):
        return {"schedule_frequency": None, "schedule_time": None, "schedule_weekday": None,
                "schedule_day_of_month": None, "scan_interval_hours": None}
    if frequency not in FREQUENCIES:
        raise ValueError(f"schedule_frequency must be one of {', '.join(FREQUENCIES)} or null (manual only)")
    out = {"schedule_frequency": frequency, "schedule_time": None, "schedule_weekday": None,
           "schedule_day_of_month": None, "scan_interval_hours": INTERVAL_OF[frequency]}
    if frequency == "12h":
        return out
    t = time_ or DEFAULT_TIME
    if not _TIME_RE.match(t):
        raise ValueError("schedule_time must be HH:MM (24-hour, South Africa time)")
    out["schedule_time"] = t
    if frequency == "weekly":
        if weekday is None or not isinstance(weekday, int) or isinstance(weekday, bool) or not 0 <= weekday <= 6:
            raise ValueError("schedule_weekday is required for weekly scans (0=Monday ... 6=Sunday)")
        out["schedule_weekday"] = weekday
    if frequency == "monthly":
        if day_of_month is None or not isinstance(day_of_month, int) or isinstance(day_of_month, bool)                 or not 1 <= day_of_month <= 28:
            raise ValueError("schedule_day_of_month is required for monthly scans (1-28)")
        out["schedule_day_of_month"] = day_of_month
    return out


def next_run_at(after: datetime, frequency: Optional[str], time_: Optional[str] = None, weekday: Optional[int] = None,
                day_of_month: Optional[int] = None) -> Optional[datetime]:
    """Next UTC instant strictly after `after` matching the schedule in Africa/Johannesburg local time.
    The local wall-clock time is built first and converted afterwards, so DST zones stay correct."""
    if frequency is None:
        return None
    after = aware(after)
    if frequency == "12h":
        return after + timedelta(hours=12)
    tz = _tz()
    local = after.astimezone(tz)
    hh, mm = (int(x) for x in (time_ or DEFAULT_TIME).split(":"))

    def at(d):
        return datetime(d.year, d.month, d.day, hh, mm, tzinfo=tz)

    if frequency == "daily":
        cand = at(local)
        while cand.astimezone(timezone.utc) <= after:
            cand = at(local.date() + timedelta(days=1)) if cand.date() == local.date() else at(cand.date() + timedelta(days=1))
        return cand.astimezone(timezone.utc)
    if frequency == "weekly":
        days = ((weekday or 0) - local.weekday()) % 7
        d = local.date() + timedelta(days=days)
        cand = at(d)
        while cand.astimezone(timezone.utc) <= after:
            d += timedelta(days=7)
            cand = at(d)
        return cand.astimezone(timezone.utc)
    # monthly
    y, m = local.year, local.month
    while True:
        cand = at(datetime(y, m, day_of_month or 1))
        if cand.astimezone(timezone.utc) > after:
            return cand.astimezone(timezone.utc)
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def schedule_of(c) -> dict:
    return {"frequency": c.schedule_frequency, "time_": c.schedule_time, "weekday": c.schedule_weekday,
            "day_of_month": c.schedule_day_of_month}


def estimated_credits_per_month(frequency: Optional[str]) -> Optional[int]:
    return round(SCANS_PER_MONTH[frequency] * SCAN_CREDIT_ESTIMATE) if frequency in SCANS_PER_MONTH else None


def plan_next_scan(*, now: datetime, schedule: Optional[dict], outcome: str, failures: int,
                   scheduled: bool, cap_scope: str = "daily", rand=None) -> dict:
    """What to store after a scan. outcome: ok | no_data | capped | failed. `schedule` is schedule_of(c)
    (frequency None = manual only: next_scan_at is never set). Returns last_status, consecutive_failures and
    (only when it should change) next_scan_at."""
    rand = rand or (lambda: random.random())
    freq = (schedule or {}).get("frequency")
    ih = INTERVAL_OF.get(freq) if freq else None

    def regular(after: datetime) -> datetime:
        base = next_run_at(after, **schedule)
        return base + (_jitter(ih, rand) if freq == "12h" else timedelta(minutes=rand() * 5))

    if outcome in ("ok", "no_data"):
        out = {"last_status": "ok", "consecutive_failures": 0}
        if ih:
            out["next_scan_at"] = regular(now)
        return out
    if outcome == "capped":
        out = {"last_status": "capped", "consecutive_failures": failures}
        if ih:
            out["next_scan_at"] = regular(next_period_start(now, cap_scope) - timedelta(seconds=1))
        return out
    f = failures + 1 if scheduled else failures
    out = {"last_status": "failed", "consecutive_failures": f}
    if ih and scheduled:
        if f >= max_consecutive_failures():
            out["next_scan_at"] = None  # auto-paused until the user resumes
        else:
            base = _env_num("ANALYTICS_COMPETITOR_BACKOFF_BASE_MINUTES", 30, 1)
            delay = min(base * (2 ** (f - 1)), ih * 60)
            out["next_scan_at"] = now + timedelta(minutes=delay) + _jitter(ih, rand)
    return out


# ── scanning ──────────────────────────────────────────────────────────────

def _claimable(t: datetime):
    return ((AiCompetitor.scan_status != "scanning") | (AiCompetitor.scan_started_at.is_(None))
            | (AiCompetitor.scan_started_at < t - _STUCK_AFTER))


async def claim_scan(db: AsyncSession, tenant_id: uuid.UUID, competitor_id: uuid.UUID, *, due_only: bool = False) -> bool:
    """Atomic claim (one UPDATE). Safe across uvicorn workers; a claim older than _STUCK_AFTER is recoverable.
    due_only (scheduler): additionally requires an active, scheduled, due competitor."""
    t = ac.now()
    conds = [AiCompetitor.id == competitor_id, AiCompetitor.tenant_id == tenant_id, _claimable(t)]
    if due_only:
        conds += [AiCompetitor.active.is_(True), AiCompetitor.scan_interval_hours.is_not(None),
                  AiCompetitor.next_scan_at.is_not(None), AiCompetitor.next_scan_at <= t]
    res = await db.execute(update(AiCompetitor).where(*conds)
                           .values(scan_status="scanning", scan_started_at=t, last_error=None, last_status="scanning"))
    await db.commit()
    return res.rowcount == 1


async def execute_scan(tenant_id: uuid.UUID, competitor_id: uuid.UUID, scheduled: bool = False) -> dict:
    """Run a scan whose claim was already taken. Own DB sessions; records the outcome on the competitor."""
    async with database.get_session_factory()() as db:
        c = await db.get(AiCompetitor, competitor_id)
        if c is None or c.tenant_id != tenant_id:
            return {"status": "missing"}
        comp = {"website": c.website, "pricing_page_url": c.pricing_page_url, "promo_page_url": c.promo_page_url}
    mf = ac.MeteredFirecrawl(tenant_id, "competitor", competitor_id)
    status, error, new_changes, snap_id, cap_scope = "failed", None, 0, None, "daily"
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
    except ac.CreditCapExceeded as exc:
        status, error = "capped", sanitize_error(ac.err_text(exc))
        cap_scope = "monthly" if "monthly" in str(exc.detail) else "daily"
        logger.info("competitor scan %s stopped by credit cap (%s)", competitor_id, cap_scope)
    except Exception as exc:
        error = sanitize_error(ac.err_text(exc))
        logger.warning("competitor scan %s failed: %s", competitor_id, error)
    async with database.get_session_factory()() as db:
        c = await db.get(AiCompetitor, competitor_id)
        if c is not None:
            t = ac.now()
            plan = plan_next_scan(now=t, schedule=schedule_of(c), outcome=status,
                                  failures=c.consecutive_failures or 0, scheduled=scheduled, cap_scope=cap_scope)
            c.scan_status = "failed" if status == "capped" else status
            c.last_error = error
            if status != "capped":
                c.last_scanned_at = t
            c.last_status = plan["last_status"]
            c.consecutive_failures = plan["consecutive_failures"]
            if "next_scan_at" in plan:
                c.next_scan_at = plan["next_scan_at"]
            if (plan["last_status"] == "failed" and scheduled and c.schedule_frequency
                    and plan["consecutive_failures"] >= max_consecutive_failures()):
                c.last_error = sanitize_error(f"Auto-scan paused after {plan['consecutive_failures']} failed scans "
                                              f"in a row. Last error: {error}", 300)
            await db.commit()
    return {"status": status, "error": error, "new_changes": new_changes, "snapshot_id": str(snap_id) if snap_id else None,
            "credits": mf.spent}


# ── always-on auto-scan scheduler ─────────────────────────────────────────

def scheduler_enabled() -> bool:
    """Kill switch: ANALYTICS_COMPETITOR_SCHEDULER_ENABLED=false turns the loop off (default ON)."""
    return os.getenv("ANALYTICS_COMPETITOR_SCHEDULER_ENABLED", "true").strip().lower() not in {"0", "false", "no", "off"}


async def _push_capped(tenant_id: uuid.UUID, cid: uuid.UUID, scope: str, message: str) -> None:
    t = ac.now()
    when = next_period_start(t, scope) + timedelta(minutes=random.random() * 30)
    async with database.get_session_factory()() as db:
        await db.execute(update(AiCompetitor).where(
            AiCompetitor.id == cid, AiCompetitor.tenant_id == tenant_id, AiCompetitor.next_scan_at <= t)
            .values(next_scan_at=when, last_status="capped",
                    last_error=sanitize_error(f"Paused until credits reset ({scope} cap). {message}", 300)))
        await db.commit()


async def _pause_blocked(tenant_id: uuid.UUID, cid: uuid.UUID) -> None:
    async with database.get_session_factory()() as db:
        await db.execute(update(AiCompetitor).where(AiCompetitor.id == cid, AiCompetitor.tenant_id == tenant_id)
                         .values(next_scan_at=None, last_status="blocked",
                                 last_error="Auto-scan paused: the website address is not allowed to be fetched. "
                                            "Check the URL, then resume."))
        await db.commit()


async def run_scheduler_tick(max_scans: Optional[int] = None, parallel: Optional[int] = None) -> list[dict]:
    """One pass: scan up to `max_scans` due competitors, at most `parallel` at a time. Returns the outcomes
    of the scans that actually ran (claims lost to another worker are skipped)."""
    max_scans = max_scans or int(_env_num("ANALYTICS_COMPETITOR_MAX_SCANS_PER_TICK", 5, 1))
    parallel = parallel or int(_env_num("ANALYTICS_COMPETITOR_MAX_PARALLEL", 2, 1))
    t = ac.now()
    async with database.get_session_factory()() as db:
        rows = (await db.execute(select(AiCompetitor.tenant_id, AiCompetitor.id, AiCompetitor.website).where(
            AiCompetitor.active.is_(True), AiCompetitor.scan_interval_hours.is_not(None),
            AiCompetitor.next_scan_at.is_not(None), AiCompetitor.next_scan_at <= t, _claimable(t))
            .order_by(AiCompetitor.next_scan_at).limit(max_scans))).all()
    sem = asyncio.Semaphore(parallel)
    results: list[dict] = []

    async def one(tenant_id: uuid.UUID, cid: uuid.UUID, website: str) -> None:
        async with sem:
            try:
                try:
                    await ac.check_headroom(tenant_id, SCAN_CREDIT_ESTIMATE)
                except ac.CreditCapExceeded as exc:
                    await _push_capped(tenant_id, cid, "monthly" if "monthly" in str(exc.detail) else "daily",
                                       str(exc.detail))
                    return
                if not await ac.is_safe_to_fetch(website):
                    await _pause_blocked(tenant_id, cid)
                    return
                async with database.get_session_factory()() as db:
                    if not await claim_scan(db, tenant_id, cid, due_only=True):
                        return
                results.append(await execute_scan(tenant_id, cid, scheduled=True))
            except Exception:
                logger.exception("scheduled competitor scan %s crashed", cid)

    await asyncio.gather(*(one(*r) for r in rows))
    return results


async def run_competitor_scheduler() -> None:
    """Always-on loop (every ANALYTICS_COMPETITOR_SCHEDULER_PERIOD_SECONDS, default 600) mirroring the tender
    scheduler. Runs in each uvicorn worker; the atomic claim guarantees each scan runs once."""
    if not scheduler_enabled():
        return
    period = int(_env_num("ANALYTICS_COMPETITOR_SCHEDULER_PERIOD_SECONDS", 600, 5))
    await asyncio.sleep(int(_env_num("ANALYTICS_COMPETITOR_SCHEDULER_STARTUP_DELAY_SECONDS", 90, 0)))
    while True:
        try:
            await run_scheduler_tick()
        except Exception:
            logger.exception("competitor scheduler tick failed")
        await asyncio.sleep(period)


async def sweep_stuck(db: AsyncSession) -> int:
    cutoff = ac.now() - _STUCK_AFTER
    rows = (await db.execute(select(AiCompetitor).where(
        AiCompetitor.scan_status == "scanning", AiCompetitor.scan_started_at < cutoff))).scalars().all()
    for c in rows:
        c.scan_status, c.last_status, c.last_error = "failed", "failed", "Interrupted (service restarted) - scan again."
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
    schedule_frequency: Optional[Literal["12h", "daily", "weekly", "monthly"]] = Field(
        None, description="null = manual only (default)")
    schedule_time: Optional[str] = Field(None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$", description="HH:MM, Africa/Johannesburg")
    schedule_weekday: Optional[int] = Field(None, ge=0, le=6, description="0=Monday .. 6=Sunday (weekly)")
    schedule_day_of_month: Optional[int] = Field(None, ge=1, le=28, description="monthly")
    scan_interval_hours: Optional[Literal[12, 24, 168, 720]] = Field(
        None, description="legacy shortcut for schedule_frequency (12h/daily/weekly/monthly)")


class CompetitorPatch(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    website: Optional[str] = Field(None, min_length=8, max_length=2000)
    pricing_page_url: Optional[str] = Field(None, max_length=2000)
    promo_page_url: Optional[str] = Field(None, max_length=2000)
    social_urls: Optional[list[str]] = Field(None, max_length=6)
    active: Optional[bool] = None
    schedule_frequency: Optional[Literal["12h", "daily", "weekly", "monthly"]] = Field(
        None, description="null = manual only (default)")
    schedule_time: Optional[str] = Field(None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$", description="HH:MM, Africa/Johannesburg")
    schedule_weekday: Optional[int] = Field(None, ge=0, le=6, description="0=Monday .. 6=Sunday (weekly)")
    schedule_day_of_month: Optional[int] = Field(None, ge=1, le=28, description="monthly")
    scan_interval_hours: Optional[Literal[12, 24, 168, 720]] = Field(
        None, description="legacy shortcut for schedule_frequency (12h/daily/weekly/monthly)")


_SCHED_KEYS = ("schedule_frequency", "schedule_time", "schedule_weekday", "schedule_day_of_month", "scan_interval_hours")


def apply_schedule(c: AiCompetitor, data: dict, *, creating: bool = False) -> None:
    """Merge schedule fields from a request onto the competitor and (re)compute next_scan_at. Raises 422."""
    if not any(k in data for k in _SCHED_KEYS):
        return
    freq = data["schedule_frequency"] if "schedule_frequency" in data else (
        FREQ_OF_INTERVAL.get(data["scan_interval_hours"]) if data.get("scan_interval_hours") else
        (None if "scan_interval_hours" in data else c.schedule_frequency))
    cur = {"time": c.schedule_time, "weekday": c.schedule_weekday, "dom": c.schedule_day_of_month}
    try:
        norm = normalize_schedule(freq, data.get("schedule_time", cur["time"]),
                                  data.get("schedule_weekday", cur["weekday"]),
                                  data.get("schedule_day_of_month", cur["dom"]))
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    for k, v in norm.items():
        setattr(c, k, v)
    if norm["schedule_frequency"] is None:  # turned off: nothing may scan this competitor automatically
        c.next_scan_at, c.consecutive_failures = None, 0
        if c.last_status in ("queued", "capped", "blocked"):
            c.last_status = None
        return
    t = ac.now()
    if norm["schedule_frequency"] == "12h":
        c.next_scan_at = (aware(c.last_scanned_at) or t) + timedelta(hours=12)
    else:
        c.next_scan_at = next_run_at(t, **schedule_of(c))
    c.consecutive_failures = 0
    if c.last_status != "scanning":
        c.last_status = "queued"
        if c.scan_status != "scanning":
            c.last_error = None


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
        "scan_interval_hours": c.scan_interval_hours, "schedule_frequency": c.schedule_frequency,
        "schedule_time": c.schedule_time, "schedule_weekday": c.schedule_weekday,
        "schedule_day_of_month": c.schedule_day_of_month, "schedule_timezone": TENANT_TZ_NAME,
        "next_scan_at": c.next_scan_at.isoformat() if c.next_scan_at else None,
        "last_status": c.last_status, "consecutive_failures": c.consecutive_failures or 0,
        "auto_scan_paused": bool(c.schedule_frequency and c.next_scan_at is None),
        "estimated_credits_per_month": estimated_credits_per_month(c.schedule_frequency),
        "last_seen_at": c.last_seen_at.isoformat() if c.last_seen_at else None,
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


async def _new_changes(db: AsyncSession, tenant_id: uuid.UUID, c: AiCompetitor) -> int:
    q = select(func.count()).select_from(AiCompetitorChange).where(
        AiCompetitorChange.tenant_id == tenant_id, AiCompetitorChange.competitor_id == c.id)
    if c.last_seen_at is not None:
        q = q.where(AiCompetitorChange.detected_at > c.last_seen_at)
    return int((await db.execute(q)).scalar_one() or 0)


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
    sched = {k: data.pop(k) for k in _SCHED_KEYS}
    c = AiCompetitor(tenant_id=auth.tenant_id, **{**data, "name": body.name.strip()})
    apply_schedule(c, {k: v for k, v in sched.items() if k in body.model_fields_set}, creating=True)
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
                    "latest_changes": [change_dict(x, c.name) for x in ch],
                    "new_changes_since_last_view": await _new_changes(db, tenant_id, c)})
    return {"competitors": out, "count": len(out), "estimated_credits_per_scan": SCAN_CREDIT_ESTIMATE}


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
    c = await _get(db, tenant_id, competitor_id)
    return {**comp_dict(c), "new_changes_since_last_view": await _new_changes(db, tenant_id, c)}


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
    sched = {k: data.pop(k) for k in _SCHED_KEYS if k in data}
    apply_schedule(c, sched)
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


@router.post("/{competitor_id}/seen")
async def mark_seen(competitor_id: uuid.UUID, auth: AuthContext = Depends(ac.require_viewer),
                    db: AsyncSession = Depends(database.get_session)):
    """Clears the 'N new changes' badge (tenant-wide: one mark per competitor, not per user)."""
    c = await _get(db, auth.tenant_id, competitor_id)
    c.last_seen_at = ac.now()
    await db.flush()
    return {**comp_dict(c), "new_changes_since_last_view": 0}


@router.post("/{competitor_id}/resume")
async def resume_schedule(competitor_id: uuid.UUID, auth: AuthContext = Depends(ac.require_analyst),
                          db: AsyncSession = Depends(database.get_session)):
    """Un-pause an auto-paused schedule (after repeated failures / blocked URL): resets failures."""
    c = await _get(db, auth.tenant_id, competitor_id)
    if not c.schedule_frequency:
        raise HTTPException(409, "No auto-scan schedule is set for this competitor")
    c.consecutive_failures, c.last_error = 0, None
    c.last_status = "queued"
    c.next_scan_at = next_run_at(ac.now(), **schedule_of(c)) if c.schedule_frequency != "12h" else ac.now()
    await db.flush()
    return comp_dict(c)


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
