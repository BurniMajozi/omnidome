"""Marketing service hardening: role gates, webhook verification/dedupe, unsubscribe tokens,
recipient validation, rate limits and the idempotent schema migration for the new tables.

Kept separate from main.py so it can be unit tested without the whole app.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
import re
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import text

from services.common.auth import AuthContext, get_auth_context
from services.common.rate_limiter import RateLimiter
from services.common.suppression import SUPPRESSION_DDL

logger = logging.getLogger("marketing.security")


def _truthy(name: str, default: str = "") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


# ═══════════════════════════ Roles / permissions ═══════════════════════════
# Roles come from the RBAC tables (AUTH_ENFORCE_RBAC, default on) or, with enforcement off,
# from the signed identity. Reads stay open to every member; writes need a write role.

MARKETING_ADMIN_ROLES = {"platform_admin", "org_admin", "owner", "admin", "tenant_admin", "super_admin"}
MARKETING_WRITE_ROLES = MARKETING_ADMIN_ROLES | {"manager"}
MARKETING_ADMIN_PERMS = {"marketing.admin", "marketing.*"}
MARKETING_WRITE_PERMS = MARKETING_ADMIN_PERMS | {"marketing.write"}


async def _effective_access(auth: AuthContext) -> Tuple[set, set]:
    if not auth.rbac_loaded:
        try:
            from services.common import rbac
            from services.marketing.database import get_session

            async with get_session() as session:
                await rbac._load_rbac(auth, session)
        except Exception as exc:  # noqa: BLE001
            logger.warning("RBAC lookup failed for marketing authorization: %s", exc)
            if _truthy("AUTH_ENFORCE_RBAC", "true"):
                return set(), set()  # fail closed: token roles are not trusted while enforcing
    return {r.lower() for r in auth.roles or []}, {p.lower() for p in auth.permissions or []}


async def _require(auth: AuthContext, roles: set, perms: set, what: str) -> AuthContext:
    if auth.is_platform_admin:
        return auth
    have_roles, have_perms = await _effective_access(auth)
    if have_roles & roles or have_perms & perms:
        return auth
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Insufficient permissions ({what} required)")


async def require_marketing_write(auth: AuthContext = Depends(get_auth_context)) -> AuthContext:
    return await _require(auth, MARKETING_WRITE_ROLES, MARKETING_WRITE_PERMS, "marketing write")


async def require_marketing_admin(auth: AuthContext = Depends(get_auth_context)) -> AuthContext:
    return await _require(auth, MARKETING_ADMIN_ROLES, MARKETING_ADMIN_PERMS, "marketing admin")


# ═══════════════════════════ Recipient validation / limits ═══════════════════════════

_EMAIL_RE = re.compile(
    r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]{1,64}@"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$"
)
_E164_RE = re.compile(r"^\+[1-9]\d{6,14}$")


def valid_email(value: Any) -> bool:
    return isinstance(value, str) and len(value) <= 254 and bool(_EMAIL_RE.match(value))


def valid_e164(value: Any) -> bool:
    return isinstance(value, str) and bool(_E164_RE.match(value))


def max_email_recipients() -> int:
    try:
        return max(1, int(os.getenv("EMAIL_MAX_RECIPIENTS", "500")))
    except ValueError:
        return 500


def clean_recipients(recipients: List[str]) -> Tuple[List[str], List[str]]:
    """Lower-case, strip, de-duplicate, strictly validate. Returns (valid, invalid).

    Raises 413 when the number of submitted recipients exceeds EMAIL_MAX_RECIPIENTS.
    """
    limit = max_email_recipients()
    if len(recipients) > limit:
        raise HTTPException(status_code=413, detail=f"Too many recipients (max {limit} per request)")
    seen: set = set()
    valid: List[str] = []
    invalid: List[str] = []
    for raw in recipients:
        e = (raw or "").strip().lower() if isinstance(raw, str) else ""
        if not valid_email(e):
            invalid.append(str(raw)[:80])
            continue
        if e not in seen:
            seen.add(e)
            valid.append(e)
    return valid, invalid


def _int_env(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except ValueError:
        return default


_email_limiter: Optional[RateLimiter] = None
_sms_limiter: Optional[RateLimiter] = None


def check_email_rate(tenant_id: Any) -> None:
    """Per-tenant send-request limit (EMAIL_RATE_PER_MIN, default 10 requests/minute)."""
    global _email_limiter
    if _email_limiter is None:
        _email_limiter = RateLimiter(max_requests=_int_env("EMAIL_RATE_PER_MIN", 10), window_seconds=60.0)
    _email_limiter.check_key(f"mkt-email:{tenant_id}")


def check_sms_rate(tenant_id: Any) -> None:
    """Per-tenant SMS limit (SMS_RATE_PER_MIN, default 20/minute)."""
    global _sms_limiter
    if _sms_limiter is None:
        _sms_limiter = RateLimiter(max_requests=_int_env("SMS_RATE_PER_MIN", 20), window_seconds=60.0)
    _sms_limiter.check_key(f"mkt-sms:{tenant_id}")


# ═══════════════════════════ Unsubscribe tokens ═══════════════════════════

UNSUBSCRIBE_TTL_SECONDS = 180 * 24 * 3600


class UnsubscribeNotConfigured(RuntimeError):
    pass


class BadUnsubscribeToken(ValueError):
    pass


def _unsub_secret() -> bytes:
    s = os.getenv("EMAIL_UNSUBSCRIBE_SECRET", "")
    if len(s) < 16:
        raise UnsubscribeNotConfigured("EMAIL_UNSUBSCRIBE_SECRET is not set (min 16 chars)")
    return s.encode()


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def sign_unsubscribe_token(tenant_id: Any, email: str, ttl: int = UNSUBSCRIBE_TTL_SECONDS, now: Optional[float] = None) -> str:
    exp = int((time.time() if now is None else now) + ttl)
    body = _b64(f"{uuid.UUID(str(tenant_id))}|{email.strip().lower()}|{exp}".encode())
    sig = _b64(hmac.new(_unsub_secret(), body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}"


def verify_unsubscribe_token(token: str, now: Optional[float] = None) -> Tuple[uuid.UUID, str]:
    """Returns (tenant_id, email) or raises BadUnsubscribeToken (tamper/expiry/format).
    Raises UnsubscribeNotConfigured when the secret is unset (fail closed)."""
    secret = _unsub_secret()
    try:
        body, sig = token.split(".", 1)
        expected = _b64(hmac.new(secret, body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(expected.encode(), sig.encode()):
            raise BadUnsubscribeToken("bad signature")
        tid_s, email, exp_s = _unb64(body).decode().split("|", 2)
        if int(exp_s) < (time.time() if now is None else now):
            raise BadUnsubscribeToken("expired")
        return uuid.UUID(tid_s), email
    except BadUnsubscribeToken:
        raise
    except Exception as exc:  # noqa: BLE001
        raise BadUnsubscribeToken("malformed") from exc


def unsubscribe_base_url() -> str:
    base = os.getenv("EMAIL_UNSUBSCRIBE_BASE_URL", "").strip().rstrip("/")
    if not base:
        raise UnsubscribeNotConfigured(
            "EMAIL_UNSUBSCRIBE_BASE_URL is not set (e.g. https://app.example.com/svc/marketing)")
    return base


def unsubscribe_url(tenant_id: Any, email: str) -> str:
    return f"{unsubscribe_base_url()}/email/unsubscribe?t={quote(sign_unsubscribe_token(tenant_id, email))}"


def unsubscribe_headers(url: str) -> Dict[str, str]:
    return {"List-Unsubscribe": f"<{url}>", "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"}


def with_unsubscribe_footer(body_html: str, url: str) -> str:
    footer = (f'<p style="font-size:12px;color:#888;margin-top:24px">You received this because you are on our '
              f'mailing list. <a href="{url}">Unsubscribe</a></p>')
    return (body_html or "") + footer


# ═══════════════════════════ Webhook helpers ═══════════════════════════

WEBHOOK_MAX_BODY = 1_048_576  # 1 MB
STORED_PAYLOAD_MAX = 64 * 1024


def verify_zernio_signature(headers: Any, raw_body: bytes) -> None:
    """Fail closed. Zernio signs HMAC-SHA256(secret, raw_body) hex in X-Zernio-Signature
    (no timestamp in that scheme, so replay protection is event-id dedupe)."""
    secret = os.getenv("ZERNIO_WEBHOOK_SECRET", "")
    if not secret:
        if _truthy("ZERNIO_WEBHOOK_ALLOW_UNSIGNED"):
            logger.critical("ZERNIO_WEBHOOK_ALLOW_UNSIGNED=true: accepting an UNSIGNED Zernio webhook")
            return
        logger.error("ZERNIO_WEBHOOK_SECRET not set: rejecting Zernio webhook")
        raise HTTPException(status_code=503, detail="Webhook secret not configured")
    signature = headers.get("X-Zernio-Signature", "") or ""
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected.encode(), signature.encode("utf-8", "ignore")):
        logger.warning("Zernio signature mismatch: sig_present=%s body_len=%d", bool(signature), len(raw_body))
        raise HTTPException(status_code=401, detail="Invalid webhook signature")


def webhook_event_id(headers: Any, payload: Any, raw_body: bytes) -> str:
    eid = headers.get("X-Zernio-Event-Id") or ""
    if not eid and isinstance(payload, dict):
        eid = str(payload.get("eventId") or payload.get("event_id") or payload.get("id") or "")
    if not eid:
        eid = "sha256:" + hashlib.sha256(raw_body).hexdigest()
    return eid[:256]


def record_webhook_event(conn, provider: str, event_id: str) -> bool:
    """True when this (provider, event_id) is new; False when already seen (duplicate)."""
    res = conn.execute(
        text("INSERT INTO marketing_webhook_events (provider, event_id) VALUES (:p, :e) "
             "ON CONFLICT (provider, event_id) DO NOTHING"),
        {"p": provider, "e": event_id},
    )
    return bool(res.rowcount)


def forget_webhook_event(conn, provider: str, event_id: str) -> None:
    conn.execute(text("DELETE FROM marketing_webhook_events WHERE provider = :p AND event_id = :e"),
                 {"p": provider, "e": event_id})


def bound_payload(payload: Any, event_type: str = "") -> Any:
    """Stored webhook payloads are capped so a signed-but-huge event cannot bloat the table."""
    import json

    try:
        raw = json.dumps(payload, default=str)
    except Exception:  # noqa: BLE001
        return {"truncated": True, "event": event_type}
    if len(raw) <= STORED_PAYLOAD_MAX:
        return payload
    return {"truncated": True, "event": event_type, "original_bytes": len(raw)}


# ═══════════════════════════ Campaign lifecycle ═══════════════════════════

CAMPAIGN_CHANNELS = {"email", "social", "search", "display", "sms", "whatsapp"}
CAMPAIGN_STATUSES = {"draft", "scheduled", "sending", "sent", "paused", "cancelled", "active", "completed"}
CAMPAIGN_TRANSITIONS: Dict[str, set] = {
    "draft": {"scheduled", "sending", "cancelled"},
    "scheduled": {"draft", "sending", "paused", "cancelled"},
    "sending": {"sent", "paused", "cancelled"},
    "paused": {"scheduled", "sending", "cancelled", "draft"},
    "sent": set(),
    "cancelled": {"draft"},
    "active": {"paused", "completed", "cancelled"},
    "completed": set(),
}


def transition_allowed(current: str, new: str) -> bool:
    return current == new or new in CAMPAIGN_TRANSITIONS.get(current, set())


# ═══════════════════════════ Migrations ═══════════════════════════

_SCHEMA_LOCK_KEY = 0x4D4B5453  # "MKTS"
_done = False

HARDENING_STATEMENTS = [
    """CREATE TABLE IF NOT EXISTS marketing_webhook_events (
        provider VARCHAR(40) NOT NULL,
        event_id VARCHAR(256) NOT NULL,
        received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        UNIQUE (provider, event_id)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_mkt_webhook_events_received ON marketing_webhook_events(received_at)",
    SUPPRESSION_DDL,
    "ALTER TABLE marketing_email_batches ADD COLUMN IF NOT EXISTS total_complained INT DEFAULT 0",
    "ALTER TABLE marketing_email_batches ADD COLUMN IF NOT EXISTS total_failed INT DEFAULT 0",
    "ALTER TABLE marketing_email_batches ADD COLUMN IF NOT EXISTS total_suppressed INT DEFAULT 0",
    "ALTER TABLE marketing_email_batches ALTER COLUMN campaign_id DROP NOT NULL",
    "ALTER TABLE marketing_email_batches ALTER COLUMN total_queued SET DEFAULT 0",
    "ALTER TABLE marketing_email_batches ALTER COLUMN total_sent SET DEFAULT 0",
    "ALTER TABLE marketing_email_batches ALTER COLUMN total_delivered SET DEFAULT 0",
    "ALTER TABLE marketing_email_batches ALTER COLUMN total_bounced SET DEFAULT 0",
    "ALTER TABLE marketing_email_batches ALTER COLUMN total_opened SET DEFAULT 0",
    "ALTER TABLE marketing_email_batches ALTER COLUMN total_clicked SET DEFAULT 0",
    "ALTER TABLE marketing_analytics_sync_state ADD COLUMN IF NOT EXISTS last_attempt_at TIMESTAMPTZ",
    "ALTER TABLE marketing_analytics_sync_state ADD COLUMN IF NOT EXISTS last_error_at TIMESTAMPTZ",
]


def ensure_hardening_schema(engine, force: bool = False) -> None:
    """Idempotent, run once per process under a Postgres advisory lock (several workers may
    boot together). create_all never ALTERs existing tables, hence explicit statements."""
    global _done
    if _done and not force:
        return
    is_pg = engine.dialect.name == "postgresql"
    lock_conn = engine.connect() if is_pg else None
    try:
        if lock_conn is not None:
            lock_conn.execute(text("SELECT pg_advisory_lock(:k)"), {"k": _SCHEMA_LOCK_KEY})
            lock_conn.commit()
        for stmt in HARDENING_STATEMENTS:
            try:
                with engine.begin() as conn:
                    conn.execute(text(stmt))
            except Exception as exc:  # noqa: BLE001 - one failed step must not block the service
                logger.warning("marketing hardening migration step skipped: %s (%s)", str(stmt).strip()[:70], exc)
        # uniqueness of the Zernio profile across tenants (dedupe-safe: skip when duplicates exist)
        try:
            with engine.begin() as conn:
                dupes = conn.execute(text(
                    "SELECT zernio_profile_id, count(*) FROM marketing_tenant_profiles "
                    "GROUP BY zernio_profile_id HAVING count(*) > 1")).all()
                if dupes:
                    logger.error("duplicate zernio_profile_id across tenants %s: unique index NOT created; "
                                 "resolve manually", [d[0] for d in dupes])
                else:
                    conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_mkt_tenant_profiles_profile "
                                      "ON marketing_tenant_profiles(zernio_profile_id)"))
        except Exception as exc:  # noqa: BLE001
            logger.warning("tenant-profile unique index skipped: %s", exc)
        _done = True
    finally:
        if lock_conn is not None:
            try:
                lock_conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _SCHEMA_LOCK_KEY})
                lock_conn.commit()
            finally:
                lock_conn.close()
