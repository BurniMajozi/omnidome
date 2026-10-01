"""AgentMail (api.agentmail.to) client shared by marketing, communication and sales.

Verified against docs.agentmail.to (2026-09):
  * Send:   POST /v0/inboxes/{inbox_id}/messages/send  body: to/cc/bcc/reply_to/subject/text/html
            -> {message_id, thread_id}
  * Reply:  POST /v0/inboxes/{inbox_id}/messages/{message_id}/reply  body: text/html/to/cc/bcc/reply_all
            (no subject; the provider threads it and returns thread_id)
  * List:   GET  /v0/inboxes/{inbox_id}/messages  ?limit&page_token&after&before&ascending&labels
            -> {count, messages[], limit, next_page_token}; items carry `preview` only, so the
            full body is fetched with GET /v0/inboxes/{inbox_id}/messages/{message_id}.
  * Webhooks: GET/POST /v0/webhooks, PATCH/DELETE /v0/webhooks/{webhook_id}
            (PATCH accepts `enabled`, `event_types`); objects carry `secret` (whsec_...).
  * Webhook delivery is Svix-signed: headers svix-id / svix-timestamp / svix-signature
    ("v1,<base64>" space-delimited), signed content `{id}.{timestamp}.{raw_body}`,
    HMAC-SHA256 keyed with the base64-decoded part of the whsec_ secret, 5 minute tolerance.
  * Inbound payload: {"event_type": "message.received", "event_id", "message": {from_, to, subject,
    text, html, message_id, inbox_id, thread_id, in_reply_to, ...}}.

Credentials: a per-call `Creds` (tenant config, encrypted at rest in `agentmail_config`) wins;
env vars (AGENTMAIL_API_KEY / AGENTMAIL_INBOX / AGENTMAIL_WEBHOOK_SECRET) are the platform default.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import logging
import os
import re
import time
import uuid
from dataclasses import dataclass
from typing import Any, Iterable, Optional
from urllib.parse import quote

import httpx
from sqlalchemy import text

logger = logging.getLogger("common.agentmail")


class EmailNotConfigured(RuntimeError):
    pass


class SecretsUnavailable(RuntimeError):
    """SECRETS_ENCRYPTION_KEY missing/invalid: refuse to store or read secrets."""


@dataclass
class Creds:
    api_key: str
    inbox: str
    webhook_secret: str = ""
    source: str = "env"  # "env" | "tenant"


WEBHOOK_EVENT_TYPES = [
    "message.received", "message.sent", "message.delivered",
    "message.bounced", "message.complained", "message.rejected",
]

# Secrets learned at runtime from the AgentMail webhook object (platform-level key).
_RUNTIME_SECRETS: dict[str, str] = {}


def base_url() -> str:
    return os.getenv("AGENTMAIL_BASE_URL", "https://api.agentmail.to/v0").rstrip("/")


def env_creds() -> Optional[Creds]:
    key = os.getenv("AGENTMAIL_API_KEY")
    if not key:
        return None
    return Creds(api_key=key, inbox=inbox_address(),
                 webhook_secret=os.getenv("AGENTMAIL_WEBHOOK_SECRET", ""), source="env")


def inbox_address() -> str:
    return os.getenv("AGENTMAIL_INBOX") or os.getenv("AGENTMAIL_INBOX_ID") or "omnidome@agentmail.to"


def is_configured(creds: Optional[Creds] = None) -> bool:
    return bool((creds and creds.api_key) or os.getenv("AGENTMAIL_API_KEY"))


def _resolve(creds: Optional[Creds]) -> Creds:
    c = creds if (creds and creds.api_key) else env_creds()
    if not c:
        raise EmailNotConfigured("Email provider not configured - set AGENTMAIL_API_KEY")
    return c


def _headers(c: Creds) -> dict:
    return {"Authorization": f"Bearer {c.api_key}", "Content-Type": "application/json"}


def _json(resp: httpx.Response) -> dict:
    try:
        d = resp.json()
        return d if isinstance(d, dict) else {}
    except ValueError:
        return {}


def _check(resp: httpx.Response) -> None:
    if resp.status_code >= 400:
        raise RuntimeError(f"AgentMail {resp.status_code}: {resp.text[:300]}")


# ── Send / reply ────────────────────────────────────────────────────────────

async def send_email(to: str, subject: str, html: str, *, reply_to: Optional[str] = None,
                     timeout: float = 30.0, creds: Optional[Creds] = None,
                     headers: Optional[dict] = None) -> str:
    """Returns the provider message id. Raises on any failure (callers retry).

    `headers` are extra RFC 5322 headers (e.g. List-Unsubscribe) passed in the send payload."""
    c = _resolve(creds)
    payload: dict = {"to": [to], "subject": subject, "html": html or ""}
    if reply_to:
        payload["reply_to"] = [reply_to]
    if headers:
        payload["headers"] = {str(k): str(v) for k, v in headers.items()}
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            f"{base_url()}/inboxes/{quote(c.inbox, safe='')}/messages/send",
            headers=_headers(c), json=payload,
        )
    _check(resp)
    data = _json(resp)
    return str(data.get("message_id") or data.get("id") or "")


async def send_message(to: list, subject: str, html: str, *, text: Optional[str] = None,
                       cc: Optional[list] = None, bcc: Optional[list] = None,
                       reply_to_message_id: Optional[str] = None,
                       timeout: float = 30.0, creds: Optional[Creds] = None) -> str:
    """Multi-recipient send. With `reply_to_message_id`, uses the reply endpoint so the
    provider threads the message (In-Reply-To/References + thread_id); the reply
    endpoint takes no `subject`. Returns the provider message id."""
    c = _resolve(creds)
    inbox = quote(c.inbox, safe="")
    payload: dict = {"html": html or ""}
    if text:
        payload["text"] = text
    if to:
        payload["to"] = list(to)
    if cc:
        payload["cc"] = list(cc)
    if bcc:
        payload["bcc"] = list(bcc)
    if reply_to_message_id:
        url = f"{base_url()}/inboxes/{inbox}/messages/{quote(reply_to_message_id, safe='')}/reply"
    else:
        payload["subject"] = subject
        url = f"{base_url()}/inboxes/{inbox}/messages/send"
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, headers=_headers(c), json=payload)
    _check(resp)
    data = _json(resp)
    return str(data.get("message_id") or data.get("id") or "")


# ── Inbox reads (polling fallback) ─────────────────────────────────────────

async def get_inbox(inbox: str, *, creds: Optional[Creds] = None, timeout: float = 15.0) -> Optional[dict]:
    """The inbox object if `creds`' account owns it; None when the provider says it does
    not exist / is not visible to this key (404/403). Raises on anything else (unreachable,
    5xx, bad key) so callers can fail closed."""
    c = _resolve(creds)
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(f"{base_url()}/inboxes/{quote(inbox, safe='')}", headers=_headers(c))
    if resp.status_code in (403, 404):
        return None
    _check(resp)
    return _json(resp) or {"inbox_id": inbox}


async def list_messages(inbox: str, *, creds: Optional[Creds] = None, limit: int = 50,
                        after: Optional[str] = None, timeout: float = 30.0) -> list[dict]:
    c = _resolve(creds)
    params: dict[str, Any] = {"limit": limit, "ascending": "false"}
    if after:
        params["after"] = after
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(f"{base_url()}/inboxes/{quote(inbox, safe='')}/messages",
                                headers=_headers(c), params=params)
    _check(resp)
    return list(_json(resp).get("messages") or [])


async def get_message(inbox: str, message_id: str, *, creds: Optional[Creds] = None,
                      timeout: float = 30.0) -> dict:
    c = _resolve(creds)
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(
            f"{base_url()}/inboxes/{quote(inbox, safe='')}/messages/{quote(message_id, safe='')}",
            headers=_headers(c))
    _check(resp)
    return _json(resp)


_ADDR_IN_BRACKETS = re.compile(r"<([^<>]+)>")


def bare_address(value: Any) -> str:
    """First plain address from 'Name <a@b>' / list / str."""
    if isinstance(value, (list, tuple)):
        value = value[0] if value else ""
    value = str(value or "").strip()
    m = _ADDR_IN_BRACKETS.search(value)
    return (m.group(1) if m else value).strip()


def normalize_message(msg: dict, inbox_fallback: str = "") -> dict:
    """AgentMail message object (webhook `message` or GET message) -> flat inbound fields.

    Webhook uses `from_`; REST objects use `from`.
    """
    sender_raw = msg.get("from_") or msg.get("from") or ""
    sender = ", ".join(sender_raw) if isinstance(sender_raw, (list, tuple)) else str(sender_raw)
    to = msg.get("to") or []
    recipient = bare_address(to) or msg.get("inbox_id") or inbox_fallback
    return {
        "sender": sender[:255],
        "recipient": str(recipient)[:255],
        "subject": str(msg.get("subject") or "(no subject)")[:500],
        "body_text": str(msg.get("text") or msg.get("preview") or ""),
        "body_html": msg.get("html"),
        "message_id": str(msg.get("message_id") or "") or None,
        "headers": {
            "thread_id": msg.get("thread_id"), "inbox_id": msg.get("inbox_id"),
            "in_reply_to": msg.get("in_reply_to"), "references": msg.get("references"),
            "to": msg.get("to"), "cc": msg.get("cc"), "timestamp": msg.get("timestamp"),
        },
    }


# ── Webhook management ─────────────────────────────────────────────────────

async def list_webhooks(creds: Optional[Creds] = None, timeout: float = 30.0) -> list[dict]:
    c = _resolve(creds)
    out: list[dict] = []
    token: Optional[str] = None
    async with httpx.AsyncClient(timeout=timeout) as client:
        for _ in range(20):
            params: dict[str, Any] = {"limit": 100}
            if token:
                params["page_token"] = token
            resp = await client.get(f"{base_url()}/webhooks", headers=_headers(c), params=params)
            _check(resp)
            data = _json(resp)
            out.extend(data.get("webhooks") or [])
            token = data.get("next_page_token")
            if not token:
                break
    return out


async def create_webhook(url: str, event_types: Optional[list] = None,
                         creds: Optional[Creds] = None, timeout: float = 30.0) -> dict:
    c = _resolve(creds)
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(f"{base_url()}/webhooks", headers=_headers(c),
                                 json={"url": url, "event_types": event_types or WEBHOOK_EVENT_TYPES})
    _check(resp)
    return _json(resp)


async def update_webhook(webhook_id: str, *, creds: Optional[Creds] = None,
                         enabled: Optional[bool] = None, event_types: Optional[list] = None,
                         timeout: float = 30.0) -> dict:
    c = _resolve(creds)
    body: dict[str, Any] = {}
    if enabled is not None:
        body["enabled"] = enabled
    if event_types:
        body["event_types"] = event_types
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.patch(f"{base_url()}/webhooks/{quote(webhook_id, safe='')}",
                                  headers=_headers(c), json=body)
    _check(resp)
    return _json(resp)


async def delete_webhook(webhook_id: str, *, creds: Optional[Creds] = None, timeout: float = 30.0) -> None:
    c = _resolve(creds)
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.delete(f"{base_url()}/webhooks/{quote(webhook_id, safe='')}",
                                   headers=_headers(c))
    if resp.status_code not in (200, 202, 204, 404):
        _check(resp)


def remember_platform_secret(secret: str) -> None:
    if secret:
        _RUNTIME_SECRETS["platform"] = secret


# ── Svix signature verification ────────────────────────────────────────────

def verify_svix(raw_body: bytes, headers: Any, secrets: Iterable[str], tolerance: int = 300) -> bool:
    """True when any candidate secret validates the Svix-style signature and the
    timestamp is within `tolerance` seconds (replay protection)."""
    msg_id = headers.get("svix-id") or headers.get("webhook-id") or ""
    ts = headers.get("svix-timestamp") or headers.get("webhook-timestamp") or ""
    sig_header = headers.get("svix-signature") or headers.get("webhook-signature") or ""
    if not (msg_id and ts and sig_header):
        return False
    try:
        if abs(time.time() - int(ts)) > tolerance:
            return False
    except ValueError:
        return False
    signed = f"{msg_id}.{ts}.".encode() + raw_body
    provided = [p.split(",", 1)[1] for p in sig_header.split() if p.startswith("v1,") and "," in p]
    for secret in secrets:
        if not secret:
            continue
        raw = secret[6:] if secret.startswith("whsec_") else secret
        try:
            key = base64.b64decode(raw)
        except (binascii.Error, ValueError):
            continue
        expected = base64.b64encode(hmac.new(key, signed, hashlib.sha256).digest()).decode()
        if any(hmac.compare_digest(expected, p) for p in provided):
            return True
    return False


def platform_webhook_secrets() -> list[str]:
    out = [os.getenv("AGENTMAIL_WEBHOOK_SECRET", ""), _RUNTIME_SECRETS.get("platform", "")]
    return [s for s in out if s]


# ── Cheap pre-checks (run BEFORE any DB / decrypt work on an unauthenticated webhook) ──

MAX_WEBHOOK_BODY_BYTES = 1_048_576  # 1 MB


class BodyTooLarge(Exception):
    pass


def webhook_headers_ok(headers: Any, tolerance: int = 300) -> bool:
    """Svix headers present, well-formed and timestamp fresh. No secrets involved."""
    msg_id = headers.get("svix-id") or headers.get("webhook-id") or ""
    ts = headers.get("svix-timestamp") or headers.get("webhook-timestamp") or ""
    sig = headers.get("svix-signature") or headers.get("webhook-signature") or ""
    if not (msg_id and ts and sig) or len(msg_id) > 256 or len(sig) > 2048:
        return False
    try:
        return abs(time.time() - int(ts)) <= tolerance
    except ValueError:
        return False


async def read_body_capped(request: Any, limit: int = MAX_WEBHOOK_BODY_BYTES) -> bytes:
    """Read the request body, refusing more than `limit` bytes (Content-Length checked first,
    then the stream is bounded so a lying/absent header cannot force a large buffer)."""
    declared = request.headers.get("content-length")
    if declared:
        try:
            if int(declared) > limit:
                raise BodyTooLarge()
        except ValueError:
            raise BodyTooLarge()
    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > limit:
            raise BodyTooLarge()
        chunks.append(chunk)
    return b"".join(chunks)


# Decrypted per-tenant webhook secrets, cached in-process so unauthenticated traffic does
# not cause a DB read + decrypt per request. tenant_id -> (expires_at, has_own_creds, secret)
SECRET_CACHE_TTL = 60.0
_SECRET_CACHE: dict[str, tuple] = {}


def invalidate_secret_cache(tenant_id=None) -> None:
    if tenant_id is None:
        _SECRET_CACHE.clear()
    else:
        _SECRET_CACHE.pop(str(tenant_id), None)


def _cache_get(tenant_id) -> Optional[tuple]:
    hit = _SECRET_CACHE.get(str(tenant_id))
    if hit and hit[0] > time.monotonic():
        return hit
    return None


def _cache_put(tenant_id, has_own: bool, secret: str) -> list[str]:
    if len(_SECRET_CACHE) > 4096:
        _SECRET_CACHE.clear()
    _SECRET_CACHE[str(tenant_id)] = (time.monotonic() + SECRET_CACHE_TTL, has_own, secret)
    return _owner_secrets(has_own, secret)


def _owner_secrets(has_own: bool, secret: str) -> list[str]:
    """Secrets that may sign for a tenant's mailbox: its own webhook secret, plus the
    platform secret only when the tenant has no AgentMail account of its own (its mailboxes
    live in the platform account). A tenant with its own account never accepts the platform
    secret and no tenant's secret is ever accepted for another tenant."""
    out = [secret] if secret else []
    if not has_own:
        out += platform_webhook_secrets()
    return out


def _row_secret(row) -> tuple[bool, str]:
    if not row or not row["api_key_enc"]:
        return False, ""
    try:
        return True, decrypt_secret(row["webhook_secret_enc"] or "")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Cannot decrypt AgentMail webhook secret for tenant %s: %s", row["tenant_id"], exc)
        return True, ""


# ── Per-tenant encrypted storage ───────────────────────────────────────────

def _fernet():
    raw_key = os.getenv("SECRETS_ENCRYPTION_KEY", "").strip()
    if not raw_key:
        raise SecretsUnavailable("SECRETS_ENCRYPTION_KEY is not set; refusing to store/read tenant secrets")
    try:
        from cryptography.fernet import Fernet, MultiFernet
        keys = [k.strip() for k in raw_key.split(",") if k.strip()]
        prev = os.getenv("SECRETS_ENCRYPTION_KEY_PREVIOUS", "").strip()
        if prev and prev not in keys:
            keys.append(prev)
        if not keys:
            raise ValueError("No valid encryption keys provided")
        fernets = [Fernet(k.encode()) for k in keys]
        return MultiFernet(fernets) if len(fernets) > 1 else fernets[0]
    except Exception as exc:  # noqa: BLE001
        raise SecretsUnavailable(f"SECRETS_ENCRYPTION_KEY is invalid (needs a Fernet key): {exc}") from exc


def encrypt_secret(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt_secret(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode() if token else ""


CONFIG_DDL = """
CREATE TABLE IF NOT EXISTS agentmail_config (
    tenant_id UUID PRIMARY KEY,
    api_key_enc TEXT,
    inbox VARCHAR(255),
    webhook_secret_enc TEXT,
    webhook_id VARCHAR(120),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""

_UPSERT = """
INSERT INTO agentmail_config (tenant_id, api_key_enc, inbox, webhook_secret_enc, webhook_id, updated_at)
VALUES (CAST(:tid AS uuid), :k, :i, :w, :wid, now())
ON CONFLICT (tenant_id) DO UPDATE SET
  api_key_enc = COALESCE(EXCLUDED.api_key_enc, agentmail_config.api_key_enc),
  inbox = COALESCE(EXCLUDED.inbox, agentmail_config.inbox),
  webhook_secret_enc = COALESCE(EXCLUDED.webhook_secret_enc, agentmail_config.webhook_secret_enc),
  webhook_id = COALESCE(EXCLUDED.webhook_id, agentmail_config.webhook_id),
  updated_at = now()
"""

_SELECT = "SELECT tenant_id, api_key_enc, inbox, webhook_secret_enc, webhook_id FROM agentmail_config"


def _row_to_creds(row) -> Optional[Creds]:
    if not row or not row["api_key_enc"]:
        return None
    try:
        return Creds(api_key=decrypt_secret(row["api_key_enc"]),
                     inbox=row["inbox"] or inbox_address(),
                     webhook_secret=decrypt_secret(row["webhook_secret_enc"] or ""),
                     source="tenant")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Cannot decrypt AgentMail config for tenant %s: %s", row["tenant_id"], exc)
        return None


def _save_params(tenant_id, api_key, inbox, webhook_secret, webhook_id) -> dict:
    return {
        "tid": str(tenant_id),
        "k": encrypt_secret(api_key) if api_key else None,
        "i": inbox or None,
        "w": encrypt_secret(webhook_secret) if webhook_secret else None,
        "wid": webhook_id or None,
    }


# sync (marketing uses a sync engine): `conn` is a sqlalchemy Connection
def ensure_config_table_sync(conn) -> None:
    conn.execute(text(CONFIG_DDL))


def owner_webhook_secrets_sync(conn, tenant_id) -> list[str]:
    hit = _cache_get(tenant_id)
    if hit:
        return _owner_secrets(hit[1], hit[2])
    ensure_config_table_sync(conn)
    row = conn.execute(text(_SELECT + " WHERE tenant_id = CAST(:tid AS uuid)"),
                       {"tid": str(tenant_id)}).mappings().first()
    return _cache_put(tenant_id, *_row_secret(row))


def load_creds_sync(conn, tenant_id) -> Optional[Creds]:
    ensure_config_table_sync(conn)
    row = conn.execute(text(_SELECT + " WHERE tenant_id = CAST(:tid AS uuid)"),
                       {"tid": str(tenant_id)}).mappings().first()
    return _row_to_creds(row)


def save_creds_sync(conn, tenant_id, *, api_key=None, inbox=None, webhook_secret=None, webhook_id=None) -> None:
    params = _save_params(tenant_id, api_key, inbox, webhook_secret, webhook_id)  # raises before any write
    ensure_config_table_sync(conn)
    conn.execute(text(_UPSERT), params)
    invalidate_secret_cache(tenant_id)


# async (communication): `session` is an AsyncSession
async def ensure_config_table(session) -> None:
    await session.execute(text(CONFIG_DDL))


async def load_creds(session, tenant_id) -> Optional[Creds]:
    await ensure_config_table(session)
    row = (await session.execute(text(_SELECT + " WHERE tenant_id = CAST(:tid AS uuid)"),
                                 {"tid": str(tenant_id)})).mappings().first()
    return _row_to_creds(row)


async def owner_webhook_secrets(session, tenant_id) -> list[str]:
    """Webhook secrets acceptable for `tenant_id`'s mail (see _owner_secrets); cached 60s."""
    hit = _cache_get(tenant_id)
    if hit:
        return _owner_secrets(hit[1], hit[2])
    await ensure_config_table(session)
    row = (await session.execute(text(_SELECT + " WHERE tenant_id = CAST(:tid AS uuid)"),
                                 {"tid": str(tenant_id)})).mappings().first()
    return _cache_put(tenant_id, *_row_secret(row))


async def load_all_creds(session) -> list[tuple[uuid.UUID, Creds]]:
    await ensure_config_table(session)
    rows = (await session.execute(text(_SELECT))).mappings().all()
    out = []
    for r in rows:
        c = _row_to_creds(r)
        if c:
            out.append((r["tenant_id"] if isinstance(r["tenant_id"], uuid.UUID) else uuid.UUID(str(r["tenant_id"])), c))
    return out


async def save_creds(session, tenant_id, *, api_key=None, inbox=None, webhook_secret=None, webhook_id=None) -> None:
    params = _save_params(tenant_id, api_key, inbox, webhook_secret, webhook_id)
    await ensure_config_table(session)
    await session.execute(text(_UPSERT), params)
    invalidate_secret_cache(tenant_id)
