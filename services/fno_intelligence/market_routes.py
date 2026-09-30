"""Market Watch: competitor pricing monitor (CAPABILITY-MAP 'market-signals').

Mounted at /api/fno/market. Scrapes user-supplied competitor pricing pages with
Firecrawl (JSON extraction), snapshots the extracted plans, diffs against the
previous snapshot and records typed signals. Nothing is fabricated: when
Firecrawl is unavailable the scan endpoints answer 503. The scheduler and
scan-all open their own DB sessions (never a request session).
"""

from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import json
import logging
import os
import re
import socket
import unicodedata
import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from services.common.auth import get_current_tenant_id
from services.common.circuit_breaker import CircuitBreakerError
from services.common.firecrawl import FirecrawlError, FirecrawlUnavailable, firecrawl
from services.fno_intelligence.database import get_session, get_session_factory
from services.fno_intelligence.models import MarketSignal, MarketSnapshot, MarketWatch

logger = logging.getLogger("fno_intelligence.market")
router = APIRouter(prefix="/market", tags=["Market watch"])

_SCAN_INTERVAL_HOURS = float(os.getenv("MARKET_SCAN_INTERVAL_HOURS", "24"))
_SCHEDULER_PERIOD_SECONDS = int(os.getenv("MARKET_SCHEDULER_PERIOD_SECONDS", "3600"))
_STUCK_AFTER = timedelta(minutes=10)

PLAN_PROMPT = (
    "Extract every internet/connectivity plan or package with a listed price on this page. "
    "For each: plan_name, speed_down_mbps, speed_up_mbps (numbers, Mbps), price_zar (monthly price "
    "in South African Rand as a number, no currency symbol), contention (e.g. '1:1' or null) and "
    "notes (promo terms, once-off fees, data caps). Use null when a value is not shown. "
    "Do not invent plans; return an empty list if there are none."
)
PLAN_SCHEMA = {
    "type": "object",
    "properties": {"plans": {"type": "array", "items": {"type": "object", "properties": {
        "plan_name": {"type": "string"},
        "speed_down_mbps": {"type": ["number", "null"]},
        "speed_up_mbps": {"type": ["number", "null"]},
        "price_zar": {"type": ["number", "null"]},
        "contention": {"type": ["string", "null"]},
        "notes": {"type": ["string", "null"]},
    }, "required": ["plan_name"]}}},
    "required": ["plans"],
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── pure helpers ──────────────────────────────────────────────────────────

def _num(v) -> Optional[float]:
    if v is None or isinstance(v, bool):
        return None
    try:
        return float(str(v).replace(",", "").replace("R", "").strip())
    except ValueError:
        return None


def normalize_plans(raw) -> list[dict]:
    out, seen = [], set()
    for p in raw or []:
        if not isinstance(p, dict):
            continue
        name = str(p.get("plan_name") or "").strip()
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        out.append({
            "plan_name": name[:200],
            "speed_down_mbps": _num(p.get("speed_down_mbps")),
            "speed_up_mbps": _num(p.get("speed_up_mbps")),
            "price_zar": _num(p.get("price_zar")),
            "contention": (str(p["contention"])[:50] if p.get("contention") else None),
            "notes": (str(p["notes"])[:500] if p.get("notes") else None),
        })
    return out


def diff_plans(before: list[dict], after: list[dict]) -> list[dict]:
    """Return [{type, plan_name, before, after}] between two normalized plan lists."""
    b = {p["plan_name"].lower(): p for p in before}
    a = {p["plan_name"].lower(): p for p in after}
    signals: list[dict] = []
    for key, plan in a.items():
        old = b.get(key)
        if old is None:
            signals.append({"type": "new_plan", "plan_name": plan["plan_name"], "before": None, "after": plan})
            continue
        if old.get("price_zar") != plan.get("price_zar"):
            signals.append({"type": "price_change", "plan_name": plan["plan_name"],
                            "before": {"price_zar": old.get("price_zar")},
                            "after": {"price_zar": plan.get("price_zar")}})
        if (old.get("speed_down_mbps") != plan.get("speed_down_mbps")
                or old.get("speed_up_mbps") != plan.get("speed_up_mbps")):
            signals.append({"type": "speed_change", "plan_name": plan["plan_name"],
                            "before": {"speed_down_mbps": old.get("speed_down_mbps"), "speed_up_mbps": old.get("speed_up_mbps")},
                            "after": {"speed_down_mbps": plan.get("speed_down_mbps"), "speed_up_mbps": plan.get("speed_up_mbps")}})
    for key, plan in b.items():
        if key not in a:
            signals.append({"type": "removed_plan", "plan_name": plan["plan_name"], "before": plan, "after": None})
    return signals


def _watch_dict(w: MarketWatch) -> dict:
    return {
        "id": str(w.id), "competitor_name": w.competitor_name, "url": w.url, "category": w.category,
        "active": w.active, "last_scraped_at": w.last_scraped_at.isoformat() if w.last_scraped_at else None,
        "last_status": w.last_status, "last_error": w.last_error,
        "created_at": w.created_at.isoformat() if w.created_at else None,
    }


def _signal_dict(s: MarketSignal, competitor: Optional[str] = None) -> dict:
    return {
        "id": str(s.id), "watch_id": str(s.watch_id), "competitor_name": competitor, "type": s.type,
        "plan_name": s.plan_name, "before": s.before, "after": s.after,
        "detected_at": s.detected_at.isoformat() if s.detected_at else None, "acknowledged": s.acknowledged,
    }


# ── watch URL validation (SSRF guard) ─────────────────────────────────────

class UnsafeWatchUrl(ValueError):
    """The URL is not an acceptable public competitor page."""


_BLOCKED_NETS = [ipaddress.ip_network(n) for n in (
    "0.0.0.0/8", "10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8", "169.254.0.0/16", "172.16.0.0/12",
    "192.0.0.0/24", "192.0.2.0/24", "192.88.99.0/24", "192.168.0.0/16", "198.18.0.0/15",
    "198.51.100.0/24", "203.0.113.0/24", "224.0.0.0/4", "240.0.0.0/4", "255.255.255.255/32",
    "::/128", "::1/128", "::ffff:0:0/96", "64:ff9b::/96", "64:ff9b:1::/48", "100::/64",
    "2001::/32", "2001:db8::/32", "2002::/16", "fc00::/7", "fe80::/10", "ff00::/8",
)]
_INTERNAL_SUFFIXES = (".localhost", ".local", ".internal", ".lan", ".home", ".corp", ".intranet",
                      ".localdomain", ".home.arpa")
_BAD_URL_CHARS = re.compile(r"[\\\s\x00-\x1f\x7f]")
_HOST_CHARS = re.compile(r"[a-z0-9._:\-]+")
_NUMERICISH = re.compile(r"[0-9a-fx.]+")


def _ip_is_public(ip) -> bool:
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    if any(ip in net for net in _BLOCKED_NETS if net.version == ip.version):
        return False
    return bool(ip.is_global) and not (ip.is_multicast or ip.is_reserved or ip.is_loopback
                                       or ip.is_link_local or ip.is_private)


def _default_resolver(host: str, port: int) -> list:
    return [i[4][0] for i in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)]


def validate_watch_url(url: str, *, resolver=None, allow_http: Optional[bool] = None) -> str:
    """Return the URL if it is a safe public page, else raise UnsafeWatchUrl.

    https only (http when MARKET_ALLOW_HTTP=true), default port only, no userinfo, no
    localhost/single-label/internal names, no IP-literal tricks, and every address the
    name resolves to must be public (loopback/private/link-local/metadata/CGNAT refused).
    `resolver(host, port) -> [ip, ...]` is injectable for tests. Blocking (DNS).
    """
    if allow_http is None:
        allow_http = os.getenv("MARKET_ALLOW_HTTP", "").strip().lower() == "true"
    raw = (url or "").strip()
    if not raw or _BAD_URL_CHARS.search(raw):
        raise UnsafeWatchUrl("URL contains whitespace, control characters or backslashes")
    try:
        parts = urlsplit(raw)
        port = parts.port
    except ValueError:
        raise UnsafeWatchUrl("Malformed URL")
    scheme = parts.scheme.lower()
    if scheme not in ("https", "http") or (scheme == "http" and not allow_http):
        raise UnsafeWatchUrl("Only https URLs are allowed")
    if "@" in parts.netloc or parts.username is not None or parts.password is not None:
        raise UnsafeWatchUrl("URLs with credentials are not allowed")
    default_port = 443 if scheme == "https" else 80
    if port is not None and port != default_port:
        raise UnsafeWatchUrl("Non-standard ports are not allowed")
    host = parts.hostname
    if not host:
        raise UnsafeWatchUrl("URL has no host")
    host = unicodedata.normalize("NFKC", host).rstrip(".").lower()
    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError:
        raise UnsafeWatchUrl("Invalid host name")
    if not host or not _HOST_CHARS.fullmatch(host):
        raise UnsafeWatchUrl("Invalid host name")

    literal = None
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        pass
    if literal is not None:
        if not _ip_is_public(literal):
            raise UnsafeWatchUrl("Address is not a public address")
        return raw
    if ":" in host:
        raise UnsafeWatchUrl("Invalid host name")
    labels = host.split(".")
    # decimal / octal / hex / short-form IPv4 ("2130706433", "0x7f.1", "127.1", "0177.0.0.1")
    if labels[-1].isdigit() or labels[-1].startswith("0x") or _NUMERICISH.fullmatch(host):
        raise UnsafeWatchUrl("Numeric host names are not allowed")
    if len(labels) < 2 or host == "localhost" or host.endswith(_INTERNAL_SUFFIXES):
        raise UnsafeWatchUrl("Internal host names are not allowed")
    try:
        addrs = (resolver or _default_resolver)(host, default_port)
    except (OSError, UnicodeError):
        raise UnsafeWatchUrl("Host name does not resolve")
    if not addrs:
        raise UnsafeWatchUrl("Host name does not resolve")
    for a in addrs:
        try:
            ip = ipaddress.ip_address(str(a).split("%")[0])
        except ValueError:
            raise UnsafeWatchUrl("Host resolved to an invalid address")
        if not _ip_is_public(ip):
            raise UnsafeWatchUrl("Host resolves to a non-public address")
    return raw


def max_watches_per_tenant() -> int:
    try:
        return max(1, int(os.getenv("MARKET_MAX_WATCHES_PER_TENANT", "25")))
    except ValueError:
        return 25


async def _check_url_or_422(url: str) -> None:
    try:
        await asyncio.to_thread(validate_watch_url, url)
    except UnsafeWatchUrl as exc:
        raise HTTPException(422, f"URL rejected: {exc}")


# ── scanning ──────────────────────────────────────────────────────────────

async def _claim(db: AsyncSession, watch_id: uuid.UUID) -> bool:
    """Atomically mark a watch as scanning; False if another scan is in flight."""
    now = _now()
    res = await db.execute(
        update(MarketWatch)
        .where(MarketWatch.id == watch_id,
               (MarketWatch.last_status != "scanning") | (MarketWatch.scan_started_at < now - _STUCK_AFTER)
               | MarketWatch.scan_started_at.is_(None))
        .values(last_status="scanning", scan_started_at=now)
    )
    await db.commit()
    return res.rowcount == 1


async def _scan_watch(db: AsyncSession, watch_id: uuid.UUID) -> dict:
    """Scrape one watch, snapshot, diff. Re-raises after recording the failure
    on the watch (committed on this same session)."""
    if not await _claim(db, watch_id):
        raise HTTPException(409, "A scan of this watch is already running")
    watch = await db.get(MarketWatch, watch_id)
    try:
        await asyncio.to_thread(validate_watch_url, watch.url)  # re-check: DNS may have changed
        raw = await firecrawl.scrape(
            watch.url, timeout=180, only_main_content=True,
            formats=[{"type": "json", "prompt": PLAN_PROMPT, "schema": PLAN_SCHEMA}],
        )
        data = raw.get("data") or {}
        plans = normalize_plans((data.get("json") or {}).get("plans"))
        watch.last_scraped_at = _now()
        if not plans:
            # Never diff against an empty extraction: that would report every plan as removed.
            watch.last_status = "no_plans_found"
            watch.last_error = "No priced plans could be extracted from this page."
            await db.commit()
            return {"watch": _watch_dict(watch), "plans": [], "signals": []}
        prev = (await db.execute(
            select(MarketSnapshot).where(MarketSnapshot.watch_id == watch.id)
            .order_by(desc(MarketSnapshot.scraped_at)).limit(1)
        )).scalar_one_or_none()
        digest = hashlib.sha256(json.dumps(plans, sort_keys=True).encode()).hexdigest()
        signals: list[MarketSignal] = []
        if prev is None or prev.content_hash != digest:
            db.add(MarketSnapshot(tenant_id=watch.tenant_id, watch_id=watch.id, plans=plans, content_hash=digest))
            if prev is not None:
                for d in diff_plans(prev.plans or [], plans):
                    sig = MarketSignal(tenant_id=watch.tenant_id, watch_id=watch.id, type=d["type"],
                                       plan_name=d["plan_name"], before=d["before"], after=d["after"])
                    db.add(sig)
                    signals.append(sig)
        watch.last_status, watch.last_error = "ok", None
        await db.commit()
        for s in signals:
            await db.refresh(s)
        return {"watch": _watch_dict(watch), "plans": plans,
                "signals": [_signal_dict(s, watch.competitor_name) for s in signals]}
    except BaseException as exc:
        await db.rollback()
        watch = await db.get(MarketWatch, watch_id)
        if watch is not None:
            watch.last_status = "failed"
            watch.last_error = (str(exc)[:500] or exc.__class__.__name__)
            await db.commit()
        raise


def _raise_http(exc: Exception) -> None:
    if isinstance(exc, (FirecrawlUnavailable, CircuitBreakerError)):
        raise HTTPException(503, f"Firecrawl is unavailable: {exc}")
    if isinstance(exc, FirecrawlError):
        raise HTTPException(502, f"Scan failed: {exc}")
    raise exc


async def _due_watch_ids() -> list[uuid.UUID]:
    cutoff = _now() - timedelta(hours=_SCAN_INTERVAL_HOURS)
    async with get_session_factory()() as db:
        rows = await db.execute(
            select(MarketWatch.id).where(
                MarketWatch.active.is_(True),
                (MarketWatch.last_scraped_at.is_(None)) | (MarketWatch.last_scraped_at < cutoff),
                MarketWatch.last_status != "scanning",
            ).limit(20)
        )
        return [r[0] for r in rows.all()]


async def run_market_scheduler() -> None:
    """Every MARKET_SCHEDULER_PERIOD_SECONDS scan watches not scanned within
    MARKET_SCAN_INTERVAL_HOURS. Each scan uses its own DB session."""
    await asyncio.sleep(90)
    while True:
        try:
            for wid in await _due_watch_ids():
                async with get_session_factory()() as db:
                    try:
                        await _scan_watch(db, wid)
                    except Exception as exc:  # recorded on the watch; keep going
                        logger.warning("[market] scheduled scan of %s failed: %s", wid, exc)
        except Exception:
            logger.exception("[market] scheduler tick failed")
        await asyncio.sleep(_SCHEDULER_PERIOD_SECONDS)


# ── watch CRUD ────────────────────────────────────────────────────────────

class WatchCreate(BaseModel):
    competitor_name: str = Field(..., min_length=1, max_length=200)
    url: str = Field(..., min_length=8, max_length=2000, pattern=r"^https?://")
    category: Literal["fibre", "lte", "wireless", "other"] = "fibre"
    active: bool = True


class WatchPatch(BaseModel):
    competitor_name: Optional[str] = Field(None, min_length=1, max_length=200)
    url: Optional[str] = Field(None, min_length=8, max_length=2000, pattern=r"^https?://")
    category: Optional[Literal["fibre", "lte", "wireless", "other"]] = None
    active: Optional[bool] = None


async def _get_watch(db: AsyncSession, tenant_id: uuid.UUID, watch_id: uuid.UUID) -> MarketWatch:
    w = await db.get(MarketWatch, watch_id)
    if w is None or w.tenant_id != tenant_id:
        raise HTTPException(404, "Watch not found")
    return w


@router.get("/watches")
async def list_watches(tenant_id: uuid.UUID = Depends(get_current_tenant_id), db: AsyncSession = Depends(get_session)):
    rows = (await db.execute(select(MarketWatch).where(MarketWatch.tenant_id == tenant_id)
                             .order_by(MarketWatch.competitor_name))).scalars().all()
    return [_watch_dict(w) for w in rows]


@router.post("/watches", status_code=201)
async def create_watch(body: WatchCreate, tenant_id: uuid.UUID = Depends(get_current_tenant_id),
                       db: AsyncSession = Depends(get_session)):
    await _check_url_or_422(body.url)
    count = (await db.execute(select(func.count()).select_from(MarketWatch).where(
        MarketWatch.tenant_id == tenant_id))).scalar_one()
    if count >= max_watches_per_tenant():
        raise HTTPException(409, f"Watch limit reached ({max_watches_per_tenant()} per tenant)")
    dupe = (await db.execute(select(MarketWatch.id).where(
        MarketWatch.tenant_id == tenant_id, MarketWatch.url == body.url))).first()
    if dupe:
        raise HTTPException(409, "That URL is already being watched")
    w = MarketWatch(tenant_id=tenant_id, **body.model_dump())
    db.add(w)
    await db.flush()
    await db.refresh(w)
    return _watch_dict(w)


@router.patch("/watches/{watch_id}")
async def update_watch(watch_id: uuid.UUID, body: WatchPatch, tenant_id: uuid.UUID = Depends(get_current_tenant_id),
                       db: AsyncSession = Depends(get_session)):
    w = await _get_watch(db, tenant_id, watch_id)
    if body.url is not None:
        await _check_url_or_422(body.url)
    for k, v in body.model_dump(exclude_unset=True).items():
        if v is not None:
            setattr(w, k, v)
    await db.flush()
    return _watch_dict(w)


@router.delete("/watches/{watch_id}", status_code=204)
async def delete_watch(watch_id: uuid.UUID, tenant_id: uuid.UUID = Depends(get_current_tenant_id),
                       db: AsyncSession = Depends(get_session)):
    await db.delete(await _get_watch(db, tenant_id, watch_id))


@router.post("/watches/{watch_id}/scan")
async def scan_watch(watch_id: uuid.UUID, tenant_id: uuid.UUID = Depends(get_current_tenant_id),
                     db: AsyncSession = Depends(get_session)):
    await _get_watch(db, tenant_id, watch_id)
    try:
        return await _scan_watch(db, watch_id)
    except HTTPException:
        raise
    except Exception as exc:
        # The failure state was already committed inside _scan_watch.
        _raise_http(exc)


@router.post("/scan-all")
async def scan_all(tenant_id: uuid.UUID = Depends(get_current_tenant_id), db: AsyncSession = Depends(get_session)):
    """Scan every active watch for the tenant (for cron/manual use). Sequential."""
    ids = [r[0] for r in (await db.execute(select(MarketWatch.id).where(
        MarketWatch.tenant_id == tenant_id, MarketWatch.active.is_(True)))).all()]
    results = []
    for wid in ids:
        async with get_session_factory()() as own:  # own session per scan
            try:
                r = await _scan_watch(own, wid)
                results.append({"watch_id": str(wid), "ok": True, "new_signals": len(r["signals"])})
            except (FirecrawlUnavailable, CircuitBreakerError) as exc:
                if not results:
                    raise HTTPException(503, f"Firecrawl is unavailable: {exc}")
                results.append({"watch_id": str(wid), "ok": False, "error": str(exc)})
            except Exception as exc:
                results.append({"watch_id": str(wid), "ok": False,
                                "error": exc.detail if isinstance(exc, HTTPException) else str(exc)})
    return {"scanned": len(results), "results": results}


# ── signals + compare ─────────────────────────────────────────────────────

@router.get("/signals")
async def list_signals(
    unacknowledged: bool = False,
    type: Optional[Literal["price_change", "new_plan", "removed_plan", "speed_change"]] = None,
    watch_id: Optional[uuid.UUID] = None,
    limit: int = Query(100, ge=1, le=500),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    q = (select(MarketSignal, MarketWatch.competitor_name)
         .join(MarketWatch, MarketWatch.id == MarketSignal.watch_id)
         .where(MarketSignal.tenant_id == tenant_id))
    if unacknowledged:
        q = q.where(MarketSignal.acknowledged.is_(False))
    if type:
        q = q.where(MarketSignal.type == type)
    if watch_id:
        q = q.where(MarketSignal.watch_id == watch_id)
    rows = (await db.execute(q.order_by(desc(MarketSignal.detected_at)).limit(limit))).all()
    return [_signal_dict(s, name) for s, name in rows]


@router.post("/signals/{signal_id}/acknowledge")
async def acknowledge_signal(signal_id: uuid.UUID, tenant_id: uuid.UUID = Depends(get_current_tenant_id),
                             db: AsyncSession = Depends(get_session)):
    s = await db.get(MarketSignal, signal_id)
    if s is None or s.tenant_id != tenant_id:
        raise HTTPException(404, "Signal not found")
    s.acknowledged = True
    await db.flush()
    return _signal_dict(s)


@router.get("/compare")
async def compare(tenant_id: uuid.UUID = Depends(get_current_tenant_id), db: AsyncSession = Depends(get_session)):
    """Latest snapshot per active watch, flattened to one row per competitor plan.
    Our own plans come from the billing plan catalog and are joined client-side."""
    watches = (await db.execute(select(MarketWatch).where(
        MarketWatch.tenant_id == tenant_id, MarketWatch.active.is_(True)))).scalars().all()
    rows = []
    for w in watches:
        snap = (await db.execute(select(MarketSnapshot).where(MarketSnapshot.watch_id == w.id)
                                 .order_by(desc(MarketSnapshot.scraped_at)).limit(1))).scalar_one_or_none()
        if snap is None:
            continue
        for p in snap.plans or []:
            rows.append({"watch_id": str(w.id), "competitor_name": w.competitor_name, "category": w.category,
                         "scraped_at": snap.scraped_at.isoformat() if snap.scraped_at else None, **p})
    return {"rows": rows}
