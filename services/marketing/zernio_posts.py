"""Pure helpers for the social-post <-> Zernio mapping (no DB, no network: unit tested).

What was wrong before (item 2 of the integration brief)
-------------------------------------------------------
* Statuses were stored in mixed case ("scheduled" from create, "SCHEDULED" from the schedule
  endpoint, "DRAFT" default) and filtered by exact match, so the Scheduled view could miss rows.
* The composer sent `account_id: accounts[0]?.id`, but that id came from the legacy
  `social_media_accounts` credentials table which is empty for provider-connected tenants, so the
  required `account_id` was absent and `POST /social/posts` answered 422: nothing was ever saved.
* The provider call used field names the API ignores (`scheduleDate`, `mediaUrls`), so even a
  "scheduled" post reached Zernio as a draft with no media; queue "enqueue" never called the
  provider at all.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

POST_STATUSES = ("draft", "scheduled", "publishing", "published", "partial", "failed", "cancelled")
_ALIASES = {"queued": "scheduled", "pending": "scheduled", "canceled": "cancelled", "complete": "published"}
PLATFORM_ALIASES = {"x": "twitter", "gbp": "googlebusiness", "google_business": "googlebusiness", "fb": "facebook",
                    "ig": "instagram"}
# a scheduledFor in the past is published immediately by the provider, so never let one through by accident
MIN_SCHEDULE_LEAD = timedelta(seconds=30)


def norm_status(value: Optional[str], default: str = "draft") -> str:
    v = (value or "").strip().lower()
    v = _ALIASES.get(v, v)
    return v if v in POST_STATUSES else default


def parse_status_filter(raw: Optional[str]) -> Tuple[Optional[List[str]], bool]:
    """'scheduled,Draft' -> (['scheduled','draft'], queued_only=False). 'queued' means
    scheduled-through-a-queue. Unknown tokens are ignored; empty -> (None, False)."""
    if not raw:
        return None, False
    out: List[str] = []
    queued_only = False
    for tok in str(raw).split(","):
        t = tok.strip().lower()
        if not t:
            continue
        if t == "queued":
            queued_only = True
            t = "scheduled"
        t = _ALIASES.get(t, t)
        if t in POST_STATUSES and t not in out:
            out.append(t)
    return (out or None), (queued_only and out == ["scheduled"])


def blank_to_none(v: Any) -> Any:
    """'' / '   ' -> None (HTML forms and some clients send empty strings for optional fields)."""
    if isinstance(v, str) and not v.strip():
        return None
    return v


def norm_platform(p: str) -> str:
    p = (p or "").strip().lower()
    return PLATFORM_ALIASES.get(p, p)


def to_utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def iso_z(dt: datetime) -> str:
    return to_utc(dt).strftime("%Y-%m-%dT%H:%M:%SZ")


def check_schedule_time(dt: datetime, now: Optional[datetime] = None) -> datetime:
    """Returns the UTC time or raises ValueError (caller maps to 422)."""
    now = now or datetime.now(timezone.utc)
    u = to_utc(dt)
    if u < now + MIN_SCHEDULE_LEAD:
        raise ValueError("scheduled_for must be at least 30 seconds in the future")
    return u


def derive_intent(status: str, scheduled_for: Optional[datetime], queue_id: Any) -> str:
    """now | schedule | queue | draft, from the legacy `status` field the UI already sends."""
    s = norm_status(status)
    if s in ("published", "publishing"):
        return "now"
    if s == "scheduled":
        return "queue" if queue_id else "schedule"
    return "draft"


def build_targets(
    wanted_platforms: Iterable[str],
    account_ids: Optional[Iterable[str]],
    tenant_accounts: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, str]], List[str]]:
    """Resolve the provider `platforms: [{platform, accountId}]` strictly from THIS tenant's accounts.

    tenant_accounts: rows {account_id, platform, status} from marketing_connected_accounts.
    * explicit account_ids: each must be a tenant account (else listed in `missing`).
    * otherwise one account per requested platform (the first active one).
    Returns (targets, missing) where `missing` holds unmatched platforms / foreign account ids.
    """
    active = [a for a in tenant_accounts if str(a.get("status") or "connected").lower() not in ("disconnected", "error")]
    by_id = {str(a["account_id"]): a for a in active}
    targets: List[Dict[str, str]] = []
    missing: List[str] = []
    seen = set()
    if account_ids:
        for aid in account_ids:
            row = by_id.get(str(aid))
            if not row:
                missing.append(str(aid))
                continue
            if str(aid) not in seen:
                seen.add(str(aid))
                targets.append({"platform": norm_platform(row.get("platform") or ""), "accountId": str(aid)})
        return targets, missing
    first: Dict[str, str] = {}
    for a in active:
        first.setdefault(norm_platform(a.get("platform") or ""), str(a["account_id"]))
    for p in wanted_platforms:
        np = norm_platform(p)
        if np in first:
            if first[np] not in seen:
                seen.add(first[np])
                targets.append({"platform": np, "accountId": first[np]})
        else:
            missing.append(np)
    return targets, missing


def platform_errors(zpost: Dict[str, Any]) -> List[str]:
    """Per-platform failure messages from a provider post, for display."""
    out = []
    for pl in (zpost or {}).get("platforms") or []:
        if not isinstance(pl, dict):
            continue
        if str(pl.get("status") or "").lower() in ("failed", "error") or pl.get("errorMessage"):
            out.append(f"{pl.get('platform', 'platform')}: {str(pl.get('errorMessage') or pl.get('status'))[:200]}")
    return out


def result_fields(zpost: Dict[str, Any], intent: str) -> Dict[str, Any]:
    """Local columns derived from the provider's response (never invented):
    {status, publish_error, zernio_post_id, platforms_info, published_at?}"""
    z = zpost or {}
    status = norm_status(z.get("status"), default="")
    if not status:
        status = {"now": "published", "schedule": "scheduled", "queue": "scheduled", "draft": "draft"}[intent]
    errors = platform_errors(z)
    if status in ("failed", "partial") and not errors:
        errors = [f"provider reported status '{status}'"]
    out: Dict[str, Any] = {
        "status": status,
        "publish_error": "; ".join(errors)[:1000] if errors else None,
        "zernio_post_id": str(z.get("_id") or z.get("id") or "") or None,
        "platforms_info": [
            {k: pl.get(k) for k in ("platform", "accountId", "status", "platformPostId", "platformPostUrl", "errorMessage")}
            for pl in z.get("platforms") or [] if isinstance(pl, dict)
        ],
    }
    if status in ("published", "partial"):
        out["published_at"] = datetime.now(timezone.utc)
    return out


def event_to_status(event_type: str) -> Optional[str]:
    """Webhook event -> local status (post.* events documented at docs.zernio.com/webhooks/posts)."""
    return {
        "post.published": "published",
        "post.scheduled": "scheduled",
        "post.failed": "failed",
        "post.partial": "partial",
        "post.cancelled": "cancelled",
    }.get(event_type)
