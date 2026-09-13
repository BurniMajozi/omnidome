"""Analytics sync — pull Zernio analytics per tenant profile and upsert into the
marketing DB tables. Customer dashboards then read those tables directly.

Why windows instead of a "changed since" cursor: metrics have none — likes keep
arriving on posts published weeks ago — so a watermark only ever picks up new
posts and stops refreshing older ones. We sync in overlapping windows:

  hot        hourly   last 30 days     (metrics still moving)
  long tail  weekly   up to 366 days   (everything older)
  followers  daily    follower-stats refreshes once/day upstream
  backfill   once     full history in <=366-day chunks, at onboarding
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import date, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple

from sqlalchemy import text

from services.common.db import get_engine
from services.marketing.zernio_client import ZernioClient, ZernioRateLimitError

logger = logging.getLogger("analytics_worker.sync")

PAGE_LIMIT = 50
MAX_RL_RETRIES = 6


def _days_ago(n: int) -> str:
    return (date.today() - timedelta(days=n)).isoformat()


def _num(d: Dict[str, Any], *keys: str) -> int:
    for k in keys:
        v = d.get(k)
        if isinstance(v, (int, float)):
            return int(v)
    return 0


def configured() -> bool:
    return bool(os.getenv("ZERNIO_API_KEY"))


# ── tenant → profile ────────────────────────────────────────────────────

def iter_tenant_profiles() -> List[Tuple[str, str]]:
    """Every tenant that has a Zernio profile mapped. Tolerant of the table not
    existing yet (returns [])."""
    engine = get_engine()
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT tenant_id, zernio_profile_id FROM marketing_tenant_profiles")
            ).all()
        return [(str(r[0]), r[1]) for r in rows]
    except Exception as e:  # noqa: BLE001 — table may not exist before marketing boots
        logger.warning("could not read tenant profiles (marketing not initialised yet?): %s", e)
        return []


def maybe_seed_from_env() -> None:
    """Convenience for single-profile / dev setups: if SEED_TENANT_ID and
    ZERNIO_PROFILE_ID are both set, ensure that mapping exists."""
    tid = os.getenv("SEED_TENANT_ID")
    pid = os.getenv("ZERNIO_PROFILE_ID")
    if not (tid and pid):
        return
    engine = get_engine()
    try:
        with engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO marketing_tenant_profiles (tenant_id, zernio_profile_id)
                    VALUES (:tid, :pid)
                    ON CONFLICT (tenant_id) DO UPDATE SET zernio_profile_id = EXCLUDED.zernio_profile_id, updated_at = now()
                """),
                {"tid": tid, "pid": pid},
            )
        logger.info("seeded tenant %s -> profile %s", tid, pid)
    except Exception as e:  # noqa: BLE001
        logger.warning("seed skipped: %s", e)


# ── rate-limit-aware call ────────────────────────────────────────────────

async def _rl(call: Callable[[], Any]) -> Any:
    """Await a Zernio call, sleeping through 429s and retrying the same page."""
    for attempt in range(MAX_RL_RETRIES):
        try:
            return await call()
        except ZernioRateLimitError as e:
            secs = e.seconds_until_reset()
            logger.warning("rate limited; sleeping %ss (attempt %d/%d)", secs, attempt + 1, MAX_RL_RETRIES)
            await asyncio.sleep(secs)
    return await call()  # final attempt; let it raise if still limited


# ── upserts ──────────────────────────────────────────────────────────────

def _upsert_posts(tenant_id: str, profile_id: str, posts: List[Dict[str, Any]]) -> int:
    rows = []
    for p in posts:
        a = p.get("analytics") or {}
        platforms = p.get("platforms") or []
        sync_status = next((pl["syncStatus"] for pl in platforms if pl.get("syncStatus")), "synced")
        platform = p.get("platform") or (platforms[0].get("platform") if platforms else "unknown")
        post_id = str(p.get("_id") or p.get("id") or "")
        if not post_id:
            continue
        rows.append({
            "tid": tenant_id, "pid": profile_id, "post_id": post_id, "platform": str(platform),
            "published_at": p.get("publishedAt"), "url": p.get("platformPostUrl"),
            "likes": _num(a, "likes"), "comments": _num(a, "comments"),
            "impressions": _num(a, "impressions"), "reach": _num(a, "reach"),
            "shares": _num(a, "shares"), "saves": _num(a, "saves"),
            "clicks": _num(a, "clicks"), "views": _num(a, "views"),
            "sync_status": sync_status,
        })
    if not rows:
        return 0
    stmt = text("""
        INSERT INTO marketing_post_analytics
          (tenant_id, profile_id, post_id, platform, published_at, platform_post_url,
           likes, comments, impressions, reach, shares, saves, clicks, views, sync_status, last_updated)
        VALUES
          (:tid, :pid, :post_id, :platform, :published_at, :url,
           :likes, :comments, :impressions, :reach, :shares, :saves, :clicks, :views, :sync_status, now())
        ON CONFLICT (tenant_id, post_id, platform) DO UPDATE SET
          published_at = EXCLUDED.published_at, platform_post_url = EXCLUDED.platform_post_url,
          likes = EXCLUDED.likes, comments = EXCLUDED.comments, impressions = EXCLUDED.impressions,
          reach = EXCLUDED.reach, shares = EXCLUDED.shares, saves = EXCLUDED.saves,
          clicks = EXCLUDED.clicks, views = EXCLUDED.views, sync_status = EXCLUDED.sync_status,
          last_updated = now()
    """)
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(stmt, rows)
    return len(rows)


def _upsert_daily(tenant_id: str, profile_id: str, attribution: str, daily_data: List[Dict[str, Any]]) -> int:
    rows = []
    for d in daily_data:
        if not d.get("date"):
            continue
        m = d.get("metrics") or {}
        rows.append({
            "tid": tenant_id, "pid": profile_id, "d": d["date"], "attr": attribution, "plat": "all",
            "pc": _num(d, "postCount"),
            "impressions": _num(m, "impressions"), "reach": _num(m, "reach"),
            "likes": _num(m, "likes"), "comments": _num(m, "comments"),
            "shares": _num(m, "shares"), "saves": _num(m, "saves"),
            "clicks": _num(m, "clicks"), "views": _num(m, "views"),
        })
    if not rows:
        return 0
    stmt = text("""
        INSERT INTO marketing_daily_metrics
          (tenant_id, profile_id, metric_date, attribution, platform, post_count,
           impressions, reach, likes, comments, shares, saves, clicks, views)
        VALUES
          (:tid, :pid, :d, :attr, :plat, :pc,
           :impressions, :reach, :likes, :comments, :shares, :saves, :clicks, :views)
        ON CONFLICT (tenant_id, metric_date, attribution, platform) DO UPDATE SET
          post_count = EXCLUDED.post_count, impressions = EXCLUDED.impressions, reach = EXCLUDED.reach,
          likes = EXCLUDED.likes, comments = EXCLUDED.comments, shares = EXCLUDED.shares,
          saves = EXCLUDED.saves, clicks = EXCLUDED.clicks, views = EXCLUDED.views, updated_at = now()
    """)
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(stmt, rows)
    return len(rows)


def _upsert_followers(tenant_id: str, profile_id: str, granularity: str, payload: Dict[str, Any]) -> int:
    """Best-effort parse of follower-stats. The endpoint's exact shape isn't
    pinned in the docs, so accept the common envelopes and store what we find."""
    accounts = None
    if isinstance(payload, dict):
        accounts = payload.get("accounts") or payload.get("data") or payload.get("stats")
    if not isinstance(accounts, list):
        return 0
    rows = []
    for acct in accounts:
        if not isinstance(acct, dict):
            continue
        acct_id = str(acct.get("accountId") or acct.get("_id") or acct.get("id") or "")
        platform = acct.get("platform")
        series = acct.get("stats") or acct.get("series") or acct.get("history") or acct.get("points") or []
        for pt in series if isinstance(series, list) else []:
            d = pt.get("date") if isinstance(pt, dict) else None
            if not (d and acct_id):
                continue
            rows.append({
                "tid": tenant_id, "pid": profile_id, "acct": acct_id, "plat": platform,
                "d": d, "g": granularity,
                "followers": _num(pt, "followers", "count", "value"),
                "growth": _num(pt, "growth", "delta", "change"),
            })
    if not rows:
        return 0
    stmt = text("""
        INSERT INTO marketing_follower_stats
          (tenant_id, profile_id, account_id, platform, stat_date, granularity, followers, growth)
        VALUES (:tid, :pid, :acct, :plat, :d, :g, :followers, :growth)
        ON CONFLICT (tenant_id, account_id, stat_date, granularity) DO UPDATE SET
          followers = EXCLUDED.followers, growth = EXCLUDED.growth,
          platform = EXCLUDED.platform, updated_at = now()
    """)
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(stmt, rows)
    return len(rows)


def _mark_state(tenant_id: str, profile_id: str, field: str, error: Optional[str] = None) -> None:
    # `field` is from a fixed allow-list, never user input.
    assert field in {"last_hot_sync", "last_longtail_sync", "last_follower_sync", "backfilled_at"}
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text(f"""
                INSERT INTO marketing_analytics_sync_state (tenant_id, profile_id, {field}, last_error, updated_at)
                VALUES (:tid, :pid, now(), :err, now())
                ON CONFLICT (tenant_id) DO UPDATE SET
                  {field} = now(), profile_id = EXCLUDED.profile_id, last_error = :err, updated_at = now()
            """),
            {"tid": tenant_id, "pid": profile_id, "err": error},
        )


# ── per-tenant sync ──────────────────────────────────────────────────────

async def sync_posts(client: ZernioClient, tenant_id: str, profile_id: str, window_days: int) -> int:
    total, page = 0, 1
    while True:
        data = await _rl(lambda pg=page: client.get_post_analytics(
            profile_id=profile_id, from_date=_days_ago(window_days), page=pg, limit=PAGE_LIMIT))
        data = data or {}
        total += _upsert_posts(tenant_id, profile_id, data.get("posts") or [])
        pages = int((data.get("pagination") or {}).get("pages", 1) or 1)
        if page >= pages:
            break
        page += 1
    return total


async def sync_daily(client: ZernioClient, tenant_id: str, profile_id: str, window_days: int) -> int:
    n = 0
    for attribution in ("publish", "received"):
        data = await _rl(lambda a=attribution: client.get_daily_metrics(
            profile_id=profile_id, from_date=_days_ago(window_days), attribution=a))
        n += _upsert_daily(tenant_id, profile_id, attribution, (data or {}).get("dailyData") or [])
    return n


async def sync_followers(client: ZernioClient, tenant_id: str, profile_id: str, granularity: str = "daily") -> int:
    data = await _rl(lambda: client.get_follower_stats(profile_id=profile_id, granularity=granularity))
    return _upsert_followers(tenant_id, profile_id, granularity, data or {})


# ── passes (called by the scheduler) ─────────────────────────────────────

async def run_pass(window_days: int, field: str, followers: bool = False) -> None:
    if not configured():
        logger.info("skip pass %s — ZERNIO_API_KEY not set", field)
        return
    client = ZernioClient()
    try:
        for tenant_id, profile_id in iter_tenant_profiles():
            try:
                posts = await sync_posts(client, tenant_id, profile_id, window_days)
                daily = await sync_daily(client, tenant_id, profile_id, window_days)
                foll = await sync_followers(client, tenant_id, profile_id) if followers else 0
                _mark_state(tenant_id, profile_id, field)
                logger.info("synced tenant=%s posts=%d daily=%d followers=%d", tenant_id, posts, daily, foll)
            except Exception as e:  # noqa: BLE001 — one tenant's failure must not stop the rest
                logger.error("sync failed tenant=%s: %s", tenant_id, e)
                _mark_state(tenant_id, profile_id, field, error=str(e)[:500])
    finally:
        await client.close()


async def run_backfill() -> None:
    """Once per tenant: pull full history in <=366-day chunks. Skips tenants
    already backfilled."""
    if not configured():
        return
    engine = get_engine()
    try:
        with engine.connect() as conn:
            done = {
                str(r[0])
                for r in conn.execute(
                    text("SELECT tenant_id FROM marketing_analytics_sync_state WHERE backfilled_at IS NOT NULL")
                ).all()
            }
    except Exception:  # noqa: BLE001
        done = set()
    client = ZernioClient()
    try:
        for tenant_id, profile_id in iter_tenant_profiles():
            if tenant_id in done:
                continue
            try:
                await sync_posts(client, tenant_id, profile_id, 366)
                await sync_daily(client, tenant_id, profile_id, 366)
                _mark_state(tenant_id, profile_id, "backfilled_at")
                logger.info("backfilled tenant=%s", tenant_id)
            except Exception as e:  # noqa: BLE001
                logger.error("backfill failed tenant=%s: %s", tenant_id, e)
    finally:
        await client.close()
