"""OmniDome-hosted connection flow for social / ads / WhatsApp accounts (Zernio behind the scenes).

Why this exists
---------------
The old `GET /social/accounts/connect/{platform}` called Zernio's `GET /v1/connect/{platform}`
with only `profileId`. With no `redirect_url`, Zernio finishes on its OWN hosted pages and
dashboard (account-selection UI, then zernio.com), which asks the tenant to sign in to
zernio.com. Tenants must never see Zernio, so every flow now:

  1. starts with an OmniDome-owned `redirect_url` (server-configured, never browser supplied)
     carrying an opaque, HMAC-bound `st` state value,
  2. uses `headless=true` for platforms that need a Page/organization/board/location picker, so
     the picker is rendered by OmniDome and Zernio only receives our API calls,
  3. is completed through `POST /social/connect/complete` and (when a pick is needed)
     `POST /social/connect/select`, which re-verify tenant + user + TTL and then verify the new
     account really belongs to the tenant's Zernio profile before mapping it to the tenant.

Tenant isolation rules enforced here
------------------------------------
  * `st` = `<nonce>.<mac>`; the nonce row stores tenant, user, platform and the tenant's own
    Zernio profile id. The MAC binds nonce|tenant|user|platform|profile|expiry.
  * The state is validated on every call: MAC, row exists, not expired (30 min TTL), tenant and
    user equal the authenticated caller's, platform unchanged.
  * Account ids that arrive from the browser (`accountId` on the OAuth redirect, selection ids)
    are never trusted: they are checked against `GET /v1/accounts?profileId=<tenant profile>`
    (and, for selections, against the option list we returned ourselves).
  * Provider temp tokens are kept server-side only (Fernet-encrypted in the session row, cleared
    on completion) and are never returned to the browser; `access_token` fields of provider
    lists are stripped.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text

from services.common.auth import AuthContext, get_auth_context, get_current_tenant_id
from services.common.db import get_engine
from services.marketing.security import require_marketing_admin
from services.marketing.zernio_errors import not_configured, provider_error

logger = logging.getLogger("marketing.connect")

router = APIRouter()

STATE_TTL = timedelta(minutes=30)
CALLBACK_PATH = "/dashboard/marketing/connect/callback"

# ───────────────────────── platform catalog ─────────────────────────
#
# flow:
#   oauth            redirect to the platform, account is created straight away
#   oauth_select     redirect (headless), then OmniDome renders a Page/org/board/location picker
#   credentials      form -> POST /social/connect/credentials/{platform}
#   telegram_code    access code the user sends to the Telegram bot
#   embedded_signup  Meta Embedded Signup popup in OmniDome (WhatsApp)
# `zernio` is the platform id used in /v1/connect/{platform}[/ads].

SOCIAL_PLATFORMS: Dict[str, Dict[str, Any]] = {
    "facebook": {"label": "Facebook", "flow": "oauth_select", "step": "select_page", "zernio": "facebook"},
    "instagram": {"label": "Instagram", "flow": "oauth", "zernio": "instagram",
                  "login_methods": ["instagram_login", "facebook_login"]},
    "linkedin": {"label": "LinkedIn", "flow": "oauth_select", "step": "select_organization", "zernio": "linkedin"},
    "twitter": {"label": "X (Twitter)", "flow": "oauth", "zernio": "twitter"},
    "tiktok": {"label": "TikTok", "flow": "oauth", "zernio": "tiktok"},
    "youtube": {"label": "YouTube", "flow": "oauth", "zernio": "youtube"},
    "threads": {"label": "Threads", "flow": "oauth", "zernio": "threads"},
    "reddit": {"label": "Reddit", "flow": "oauth", "zernio": "reddit"},
    "pinterest": {"label": "Pinterest", "flow": "oauth_select", "step": "select_board", "zernio": "pinterest"},
    "googlebusiness": {"label": "Google Business Profile", "flow": "oauth_select", "step": "select_location",
                       "zernio": "googlebusiness"},
    "snapchat": {"label": "Snapchat", "flow": "oauth_select", "step": "select_public_profile", "zernio": "snapchat"},
    "bluesky": {"label": "Bluesky", "flow": "credentials",
                "fields": [{"name": "identifier", "label": "Handle or email", "secret": False},
                           {"name": "app_password", "label": "App password", "secret": True}]},
    "telegram": {"label": "Telegram", "flow": "telegram_code"},
    "whatsapp": {"label": "WhatsApp", "flow": "embedded_signup", "step": "select_phone_number", "zernio": "whatsapp"},
}

# Ads connections are separate Zernio accounts (platform metaads/googleads/tiktokads/...).
# The connect id differs from the social platform id for readability in the UI.
ADS_PLATFORMS: Dict[str, Dict[str, Any]] = {
    "meta_ads": {"label": "Meta Ads (Facebook & Instagram)", "flow": "oauth_select", "step": "select_page",
                 "zernio": "facebook", "account_platform": "metaads", "login_modes": ["classic", "business"]},
    "google_ads": {"label": "Google Ads", "flow": "oauth", "zernio": "googleads", "account_platform": "googleads"},
    "tiktok_ads": {"label": "TikTok Ads", "flow": "oauth", "zernio": "tiktok", "account_platform": "tiktokads"},
    "linkedin_ads": {"label": "LinkedIn Ads", "flow": "oauth", "zernio": "linkedin", "account_platform": "linkedinads"},
    "pinterest_ads": {"label": "Pinterest Ads", "flow": "oauth", "zernio": "pinterest", "account_platform": "pinterestads"},
    "x_ads": {"label": "X Ads", "flow": "oauth", "zernio": "twitter", "account_platform": "xads"},
}

SELECT_STEPS = {
    "select_page", "select_account", "select_organization", "select_board",
    "select_location", "select_public_profile", "select_phone_number",
}
_SENSITIVE_KEY = re.compile(r"(?i)(token|secret|password|authorization)")


# ───────────────────────── small helpers ─────────────────────────


def _mk():
    """Late import of the marketing app module (avoids a circular import at load time)."""
    from services.marketing import main as mk
    return mk


def _client():
    c = _mk().get_zernio_client()
    if c is None:
        raise not_configured()
    return c


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _state_secret() -> bytes:
    """Signing key for `st`. Prefer a dedicated secret; otherwise derive one from the platform's
    Zernio key (never leaves the server, rotates with it). Fails closed when neither exists."""
    dedicated = os.getenv("MARKETING_CONNECT_STATE_SECRET", "").strip()
    if len(dedicated) >= 16:
        return dedicated.encode()
    api_key = os.getenv("ZERNIO_API_KEY", "").strip()
    if api_key:
        return hmac.new(api_key.encode(), b"omnidome-marketing-connect-state-v1", hashlib.sha256).digest()
    raise not_configured()


def _mac(nonce: str, tenant: str, user: str, platform: str, profile: str, exp: str) -> str:
    msg = "|".join([nonce, tenant, user, platform, profile, exp]).encode()
    digest = hmac.new(_state_secret(), msg, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest[:15]).decode().rstrip("=")  # 20 chars


def _epoch(dt: datetime) -> str:
    """Timezone-independent expiry stamp for the MAC (DB drivers return differing tzinfo)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return str(int(dt.timestamp()))


def make_state(tenant: str, user: str, platform: str, profile: str, exp: datetime) -> Dict[str, str]:
    nonce = secrets.token_urlsafe(16)  # 22 chars
    st = f"{nonce}.{_mac(nonce, tenant, user, platform, profile, _epoch(exp))}"
    return {"nonce": nonce, "st": st}


def split_state(st: str) -> tuple:
    if not isinstance(st, str) or st.count(".") != 1 or len(st) > 120:
        raise HTTPException(status_code=400, detail={"error": "invalid_state", "message": "Invalid connection state."})
    nonce, mac = st.split(".")
    if not re.fullmatch(r"[A-Za-z0-9_\-]{10,64}", nonce):
        raise HTTPException(status_code=400, detail={"error": "invalid_state", "message": "Invalid connection state."})
    return nonce, mac


def callback_base() -> str:
    """Absolute OmniDome URL Zernio redirects to. Server configured only: a browser-supplied
    redirect would let an attacker receive the OAuth hand-off params."""
    explicit = os.getenv("MARKETING_CONNECT_CALLBACK_URL", "").strip()
    if explicit:
        return explicit.split("?", 1)[0]
    for var in ("OMNIDOME_PUBLIC_URL", "PUBLIC_URL", "PUBLIC_BASE_URL", "NEXT_PUBLIC_APP_URL"):
        base = os.getenv(var, "").strip().rstrip("/")
        if base:
            return base + CALLBACK_PATH
    if os.getenv("ENVIRONMENT", os.getenv("APP_ENV", "")).strip().lower() in ("", "dev", "development", "local", "test"):
        return "http://localhost:3000" + CALLBACK_PATH
    raise HTTPException(status_code=503, detail={
        "error": "callback_not_configured",
        "message": "Connection callback URL is not configured (set OMNIDOME_PUBLIC_URL or MARKETING_CONNECT_CALLBACK_URL).",
    })


def safe_return_to(value: Optional[str]) -> Optional[str]:
    """Only same-site relative paths survive; anything else is dropped."""
    if not value:
        return None
    v = value.strip()
    if not v.startswith("/") or v.startswith("//") or "\\" in v or "\n" in v or "\r" in v or len(v) > 300:
        return None
    return v


def sanitize(value: Any) -> Any:
    """Strip token-like keys from provider payloads before they reach the browser."""
    if isinstance(value, dict):
        return {k: sanitize(v) for k, v in value.items() if not _SENSITIVE_KEY.search(str(k))}
    if isinstance(value, list):
        return [sanitize(v) for v in value]
    return value


def decode_user_profile(raw: Any) -> Any:
    """`userProfile` arrives percent-encoded twice (Zernio guide): once by the URL, once by us
    reading the query. Accept a dict, a JSON string, or a still-encoded JSON string."""
    if isinstance(raw, dict) or raw is None:
        return raw
    s = str(raw)
    for _ in range(2):
        try:
            return json.loads(s)
        except ValueError:
            from urllib.parse import unquote
            s = unquote(s)
    return None


def _secret_box():
    from services.common import secretbox
    return secretbox


# ───────────────────────── session store (DB) ─────────────────────────
# Kept in tiny functions so tests (and any future store swap) patch one place.


def store_create(row: Dict[str, Any]) -> None:
    with get_engine().begin() as conn:
        conn.execute(text("""
            INSERT INTO marketing_connect_sessions
              (nonce, tenant_id, user_id, platform, category, profile_id, flow, reconnect_account_id,
               return_to, options, status, expires_at)
            VALUES (:nonce, :tenant_id, :user_id, :platform, :category, :profile_id, :flow, :reconnect,
                    :return_to, CAST(:options AS jsonb), 'pending', :expires_at)
        """), row)


def store_get(nonce: str) -> Optional[Dict[str, Any]]:
    with get_engine().connect() as conn:
        r = conn.execute(text("SELECT * FROM marketing_connect_sessions WHERE nonce = :n"), {"n": nonce}).mappings().first()
    return dict(r) if r else None


def store_update(nonce: str, **fields: Any) -> None:
    allowed = {"status", "error", "pending_enc", "completed_at", "options"}
    sets, params = [], {"n": nonce}
    for k, v in fields.items():
        if k not in allowed:
            raise ValueError(k)
        if k == "options":
            sets.append("options = CAST(:options AS jsonb)")
            params["options"] = json.dumps(v)
        else:
            sets.append(f"{k} = :{k}")
            params[k] = v
    if not sets:
        return
    with get_engine().begin() as conn:
        conn.execute(text(f"UPDATE marketing_connect_sessions SET {', '.join(sets)} WHERE nonce = :n"), params)


def load_session(st: str, auth: AuthContext, tenant_id: uuid.UUID, expect_open: bool = True) -> Dict[str, Any]:
    """Validate `st` end to end and return the session row. See module docstring."""
    nonce, mac = split_state(st)
    row = store_get(nonce)
    if not row:
        raise HTTPException(status_code=400, detail={"error": "invalid_state", "message": "Unknown or expired connection state."})
    exp = row["expires_at"]
    exp_stamp = _epoch(exp) if isinstance(exp, datetime) else str(exp)
    expected = _mac(nonce, str(row["tenant_id"]), str(row.get("user_id") or ""), row["platform"], row["profile_id"], exp_stamp)
    if not hmac.compare_digest(expected, mac):
        raise HTTPException(status_code=400, detail={"error": "invalid_state", "message": "Invalid connection state."})
    if isinstance(exp, datetime) and exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if isinstance(exp, datetime) and exp < _now():
        raise HTTPException(status_code=400, detail={"error": "state_expired", "message": "This connection attempt expired. Start again."})
    if str(row["tenant_id"]) != str(tenant_id) or str(row.get("user_id") or "") != str(auth.user_id):
        # Same message as unknown state: do not reveal that the nonce exists for someone else.
        raise HTTPException(status_code=403, detail={"error": "state_mismatch", "message": "This connection attempt belongs to a different user."})
    if expect_open and row.get("status") == "completed":
        raise HTTPException(status_code=409, detail={"error": "already_completed", "message": "This connection attempt was already completed."})
    return row


# ───────────────────────── catalog + start ─────────────────────────


@router.get("/social/connect/platforms")
async def connect_platforms(tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    """What the Connections UI can offer, grouped by category, plus how each one connects."""
    def view(pid: str, meta: Dict[str, Any], category: str) -> Dict[str, Any]:
        out = {k: v for k, v in meta.items() if k not in ("zernio",)}
        out.update({"id": pid, "category": category})
        return out

    return {
        "configured": _mk().get_zernio_client() is not None,
        "social": [view(k, v, "social") for k, v in SOCIAL_PLATFORMS.items()],
        "ads": [view(k, v, "ads") for k, v in ADS_PLATFORMS.items()],
    }


class ConnectStartIn(BaseModel):
    platform: str
    category: str = Field("social", description="social | ads")
    return_to: Optional[str] = Field(None, description="Relative OmniDome path to land on afterwards")
    login_method: Optional[str] = Field(None, description="instagram only: instagram_login | facebook_login")
    login_mode: Optional[str] = Field(None, description="meta_ads only: classic | business")
    scopes: Optional[str] = Field(None, description="posting,analytics,comments,messaging,ads")
    reconnect_account_id: Optional[str] = None
    ad_account_ids: Optional[List[str]] = None


async def _start(body: ConnectStartIn, auth: AuthContext, tenant_id: uuid.UUID) -> Dict[str, Any]:
    mk = _mk()
    category = (body.category or "social").lower()
    pid_key = (body.platform or "").lower().strip()
    catalog = ADS_PLATFORMS if category == "ads" else SOCIAL_PLATFORMS
    meta = catalog.get(pid_key)
    if category not in ("social", "ads") or not meta:
        raise HTTPException(status_code=422, detail={"error": "unsupported_platform",
                                                     "message": f"Unsupported {category} platform '{body.platform}'."})
    if meta["flow"] not in ("oauth", "oauth_select", "embedded_signup"):
        raise HTTPException(status_code=422, detail={"error": "wrong_flow", "message": f"{meta['label']} does not use a redirect connect; see /social/connect/platforms."})
    if meta["flow"] == "embedded_signup":
        raise HTTPException(status_code=422, detail={"error": "wrong_flow", "message": "WhatsApp connects through /social/connect/whatsapp/*."})
    client = _client()
    try:
        profile_id = await mk._ensure_tenant_profile(tenant_id)
    except Exception as exc:  # noqa: BLE001
        raise provider_error("ensure profile", exc)
    if not profile_id:
        raise not_configured()

    if body.reconnect_account_id:
        mine = await _tenant_accounts_by_id(client, profile_id)
        if body.reconnect_account_id not in mine:
            raise HTTPException(status_code=403, detail={"error": "account_not_in_tenant", "message": "That account is not connected to this workspace."})
    if body.login_method and (pid_key != "instagram" or body.login_method not in ("instagram_login", "facebook_login")):
        raise HTTPException(status_code=422, detail={"error": "invalid_login_method", "message": "login_method applies to instagram only."})
    if body.login_mode and (pid_key != "meta_ads" or body.login_mode not in ("classic", "business")):
        raise HTTPException(status_code=422, detail={"error": "invalid_login_mode", "message": "login_mode applies to meta_ads only."})

    # Instagram via Facebook Login adds a Page picker, so it is a headless/select flow.
    needs_select = meta["flow"] == "oauth_select" or (pid_key == "instagram" and body.login_method == "facebook_login")
    if category == "ads" and pid_key == "meta_ads" and body.login_mode == "business":
        needs_select = False  # business login completes in Zernio's meta-ads callback, then redirects to us

    exp = _now() + STATE_TTL
    st = make_state(str(tenant_id), str(auth.user_id), pid_key, profile_id, exp)
    return_to = safe_return_to(body.return_to)
    redirect = f"{callback_base()}?st={quote(st['st'], safe='')}"
    if len(redirect) > 240:  # X caps the URL-encoded redirect at 258 chars
        raise HTTPException(status_code=503, detail={"error": "callback_too_long", "message": "Callback URL is too long for the provider (max ~240 chars)."})

    store_create({
        "nonce": st["nonce"], "tenant_id": str(tenant_id), "user_id": str(auth.user_id), "platform": pid_key,
        "category": category, "profile_id": profile_id, "flow": meta["flow"],
        "reconnect": body.reconnect_account_id, "return_to": return_to,
        "options": json.dumps({"login_method": body.login_method, "login_mode": body.login_mode,
                               "needs_select": needs_select, "zernio_platform": meta["zernio"]}),
        "expires_at": exp,
    })
    try:
        res = await client.start_connect(
            meta["zernio"], profile_id, redirect,
            headless=needs_select, ads=(category == "ads"),
            login_method=body.login_method, login_mode=body.login_mode, scopes=body.scopes,
            reconnect_account_id=body.reconnect_account_id, ad_account_ids=body.ad_account_ids,
        )
    except Exception as exc:  # noqa: BLE001
        store_update(st["nonce"], status="failed", error="start_failed")
        raise provider_error(f"connect start {pid_key}", exc)
    if res.get("alreadyConnected"):
        store_update(st["nonce"], status="completed", completed_at=_now())
        return {"status": "already_connected", "platform": pid_key, "account_id": res.get("accountId"), "state": st["st"]}
    auth_url = res.get("authUrl") or ""
    if not auth_url.startswith("https://"):
        store_update(st["nonce"], status="failed", error="no_auth_url")
        raise HTTPException(status_code=502, detail={"error": "provider_no_auth_url",
                                                     "message": f"The provider returned no authorization URL for {meta['label']}."})
    return {"status": "redirect", "platform": pid_key, "category": category, "auth_url": auth_url,
            "state": st["st"], "expires_in": int(STATE_TTL.total_seconds()), "flow": meta["flow"],
            "callback_url": callback_base()}


@router.post("/social/connect/start")
async def connect_start(
    body: ConnectStartIn,
    auth: AuthContext = Depends(require_marketing_admin),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Begin connecting a social or ads account. The browser must navigate to `auth_url`
    (the platform's own OAuth screen); it comes back to the OmniDome callback page with `st`."""
    return await _start(body, auth, tenant_id)


# ───────────────────────── complete (callback) ─────────────────────────


class ConnectCompleteIn(BaseModel):
    state: str
    params: Dict[str, Any] = Field(default_factory=dict, description="All query params present on the callback URL")


async def _tenant_accounts_by_id(client, profile_id: str) -> Dict[str, Dict[str, Any]]:
    try:
        accounts = await client.list_profile_accounts(profile_id)
    except Exception as exc:  # noqa: BLE001
        raise provider_error("list profile accounts", exc)
    out: Dict[str, Dict[str, Any]] = {}
    for a in accounts or []:
        if isinstance(a, dict):
            aid = str(a.get("_id") or a.get("id") or a.get("accountId") or "")
            pf = a.get("profileId")
            pf_id = str((pf or {}).get("_id") if isinstance(pf, dict) else pf or "")
            if aid and (not pf_id or pf_id == profile_id):  # profileId filter is server-side; double-check
                out[aid] = a
    return out


def _account_summary(a: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "account_id": str(a.get("_id") or a.get("id") or a.get("accountId") or ""),
        "platform": a.get("platform"),
        "username": a.get("username"),
        "display_name": a.get("displayName"),
        "profile_picture": a.get("profilePicture"),
        "is_active": a.get("isActive", True),
    }


async def _confirm_and_map(client, tenant_id: uuid.UUID, profile_id: str, account_ids: List[str]) -> List[Dict[str, Any]]:
    """Verify each id belongs to the tenant's Zernio profile, then write the tenant map."""
    mine = await _tenant_accounts_by_id(client, profile_id)
    out = []
    for aid in account_ids:
        acct = mine.get(str(aid))
        if not acct:
            logger.warning("connect: account %s not in profile %s for tenant %s", aid, profile_id, tenant_id)
            raise HTTPException(status_code=403, detail={"error": "account_not_in_tenant",
                                                         "message": "The connected account could not be verified for this workspace."})
        _mk()._upsert_connected_account(str(tenant_id), profile_id, {
            "accountId": str(aid), "platform": acct.get("platform"), "username": acct.get("username") or acct.get("displayName"),
        }, status="connected")
        out.append(_account_summary(acct))
    return out


def _flat(params: Dict[str, Any]) -> Dict[str, str]:
    return {str(k): (v if isinstance(v, str) else json.dumps(v)) for k, v in (params or {}).items() if v is not None}


@router.post("/social/connect/complete")
async def connect_complete(
    body: ConnectCompleteIn,
    auth: AuthContext = Depends(require_marketing_admin),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Called by the OmniDome callback page with every query param it received.

    Returns one of
      {status:"connected", accounts:[...]}                       (done)
      {status:"selection_required", step, selection_type, options:[...]}   (call /select)
      {status:"error", error, message, user_fixable}             (provider reported a failure)
    """
    session = load_session(body.state, auth, tenant_id)
    p = _flat(body.params)
    nonce = session["nonce"]
    return_to = session.get("return_to")
    client = _client()

    if p.get("error"):
        msg = p.get("error_message") or p.get("platform_error_description") or "The connection was not completed."
        store_update(nonce, status="failed", error=str(p.get("error"))[:100])
        return {"status": "error", "error": p.get("error"), "reason": p.get("error_reason"),
                "message": msg[:300], "user_fixable": str(p.get("is_user_fixable", "")).lower() == "true",
                "platform": session["platform"], "return_to": return_to}

    if p.get("profileId") and p["profileId"] != session["profile_id"]:
        raise HTTPException(status_code=403, detail={"error": "profile_mismatch", "message": "Callback does not match this workspace."})

    step = p.get("step")
    pending_token = p.get("pendingDataToken")

    # ── selection platforms ────────────────────────────────────────────
    if step in SELECT_STEPS or pending_token:
        step = step or SOCIAL_PLATFORMS.get(session["platform"], ADS_PLATFORMS.get(session["platform"], {})).get("step")
        if step not in SELECT_STEPS:
            raise HTTPException(status_code=400, detail={"error": "unknown_step", "message": "Unexpected provider step."})
        return await _begin_selection(client, session, tenant_id, p, step, pending_token)

    # ── direct success (Zernio already created the account) ────────────
    account_id = p.get("accountId")
    if p.get("connected") and account_id:
        accounts = await _confirm_and_map(client, tenant_id, session["profile_id"], [account_id])
        store_update(nonce, status="completed", completed_at=_now(), pending_enc=None)
        return {"status": "connected", "accounts": accounts, "return_to": return_to}

    raise HTTPException(status_code=400, detail={"error": "nothing_to_complete",
                                                 "message": "The callback carried no connection result."})


async def _begin_selection(client, session: Dict[str, Any], tenant_id: uuid.UUID, p: Dict[str, str],
                           step: str, pending_token: Optional[str]) -> Dict[str, Any]:
    nonce, profile_id = session["nonce"], session["profile_id"]
    temp_token = p.get("tempToken")
    connect_token = p.get("connect_token")
    user_profile = decode_user_profile(p.get("userProfile"))
    pending: Dict[str, Any] = {"step": step, "tempToken": temp_token, "connectToken": connect_token,
                               "userProfile": user_profile, "pendingDataToken": pending_token}
    options: List[Dict[str, Any]] = []
    selection_type = "pages"
    try:
        if pending_token:
            data = await client.get_pending_connect_data(pending_token)
            pending["tempToken"] = data.get("tempToken") or temp_token
            pending["refreshToken"] = data.get("refreshToken")
            pending["expiresIn"] = data.get("expiresIn")
            pending["userProfile"] = data.get("userProfile") or user_profile
            selection_type = data.get("selectionType") or selection_type
            if step == "select_organization":
                options = [{"id": "personal", "name": "Personal profile", "account_type": "personal"}]
                for o in data.get("organizations") or []:
                    options.append({"id": str(o.get("id")), "name": o.get("name"), "urn": o.get("urn"),
                                    "vanity_name": o.get("vanityName"), "account_type": "organization"})
            elif step == "select_board":
                options = [{"id": str(b.get("id")), "name": b.get("name")} for b in data.get("boards") or []]
            elif step == "select_location":
                locs = (await client.connect_get("googlebusiness/locations",
                                                 {"profileId": profile_id, "pendingDataToken": pending_token},
                                                 connect_token)).get("locations") or []
                options = [{"id": str(l.get("id")), "name": l.get("name"), "address": l.get("address"),
                            "account_id": l.get("accountId")} for l in locs]
            elif step == "select_public_profile":
                options = [{"id": str(x.get("id")), "name": x.get("display_name"), "username": x.get("username")}
                           for x in data.get("publicProfiles") or data.get("profiles") or []]
        elif step == "select_page":
            pages = (await client.connect_get("facebook/select-page", {"profileId": profile_id, "tempToken": temp_token},
                                              connect_token)).get("pages") or []
            options = [{"id": str(x.get("id")), "name": x.get("name"), "username": x.get("username"),
                        "category": x.get("category")} for x in pages]
        elif step == "select_account":
            pages = (await client.connect_get("instagram/select-account", {"profileId": profile_id, "tempToken": temp_token},
                                              connect_token)).get("pages") or []
            options = [{"id": str(x.get("id")), "name": x.get("name"),
                        "instagram_username": (x.get("instagram_business_account") or {}).get("username")} for x in pages]
        elif step == "select_board":
            boards = (await client.connect_get("pinterest/select-board", {"profileId": profile_id, "tempToken": temp_token},
                                               connect_token)).get("boards") or []
            options = [{"id": str(b.get("id")), "name": b.get("name")} for b in boards]
        elif step == "select_public_profile":
            profs = (await client.connect_get("snapchat/select-profile", {"profileId": profile_id, "tempToken": temp_token},
                                              connect_token)).get("publicProfiles") or []
            options = [{"id": str(x.get("id")), "name": x.get("display_name"), "username": x.get("username")} for x in profs]
        elif step == "select_phone_number":
            nums = (await client.connect_get("whatsapp/select-phone-number", {"profileId": profile_id, "tempToken": temp_token},
                                             connect_token)).get("phoneNumbers") or []
            options = [{"id": str(n.get("id")), "name": n.get("verified_name") or n.get("display_phone_number"),
                        "phone_number": n.get("display_phone_number"), "waba_id": n.get("wabaId"),
                        "name_status": n.get("name_status"), "quality_rating": n.get("quality_rating")} for n in nums]
        else:
            raise HTTPException(status_code=400, detail={"error": "unknown_step", "message": "Unexpected provider step."})
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        store_update(nonce, status="failed", error="selection_list_failed")
        raise provider_error(f"selection list {step}", exc)

    options = sanitize(options)
    if not options:
        store_update(nonce, status="failed", error="no_options")
        return {"status": "error", "error": "no_options", "message": "Nothing is available to connect for this login "
                "(for example no Page, organization or location is managed by this account).", "user_fixable": True,
                "platform": session["platform"], "return_to": session.get("return_to")}

    # Ads-only Meta connect: Zernio's guide says the backend may pick the first Page and show no picker.
    if session["category"] == "ads" and session["platform"] == "meta_ads" and step == "select_page" and len(options) >= 1:
        pending["optionIds"] = [options[0]["id"]]
        pending["options"] = options
        return await _do_select(client, session, tenant_id, pending, [options[0]["id"]], {})

    pending["optionIds"] = [o["id"] for o in options]
    pending["options"] = options
    try:
        enc = _secret_box().encrypt(json.dumps(pending))
    except Exception as exc:  # noqa: BLE001 - SecretsUnavailable
        logger.error("connect: cannot store selection state: %s", exc)
        raise HTTPException(status_code=503, detail={"error": "secrets_unavailable",
                                                     "message": "Secure storage is not configured (SECRETS_ENCRYPTION_KEY); this connection cannot continue."})
    store_update(nonce, pending_enc=enc, status="awaiting_selection")
    return {"status": "selection_required", "step": step, "selection_type": selection_type,
            "multiple": step in ("select_page", "select_account", "select_location"), "options": options,
            "platform": session["platform"], "return_to": session.get("return_to")}


# ───────────────────────── select ─────────────────────────


class ConnectSelectIn(BaseModel):
    state: str
    selection_ids: List[str] = Field(..., min_length=1, max_length=25)
    account_type: Optional[str] = Field(None, description="linkedin only: personal | organization")


def _read_pending(session: Dict[str, Any]) -> Dict[str, Any]:
    enc = session.get("pending_enc")
    if not enc:
        raise HTTPException(status_code=409, detail={"error": "no_pending_selection", "message": "There is nothing to select for this connection attempt."})
    try:
        return json.loads(_secret_box().decrypt(enc))
    except Exception as exc:  # noqa: BLE001
        logger.error("connect: pending state unreadable: %s", type(exc).__name__)
        raise HTTPException(status_code=503, detail={"error": "secrets_unavailable", "message": "Secure storage is not available."})


@router.post("/social/connect/select")
async def connect_select(
    body: ConnectSelectIn,
    auth: AuthContext = Depends(require_marketing_admin),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Finish a headless connection: the user picked a Page / organization / board / location / number."""
    session = load_session(body.state, auth, tenant_id)
    pending = _read_pending(session)
    allowed = set(pending.get("optionIds") or [])
    ids = [str(i) for i in body.selection_ids]
    if not ids or any(i not in allowed for i in ids):
        raise HTTPException(status_code=422, detail={"error": "invalid_selection",
                                                     "message": "That choice was not offered for this connection."})
    return await _do_select(_client(), session, tenant_id, pending, ids, {"account_type": body.account_type})


async def _do_select(client, session: Dict[str, Any], tenant_id: uuid.UUID, pending: Dict[str, Any],
                     ids: List[str], extra: Dict[str, Any]) -> Dict[str, Any]:
    profile_id = session["profile_id"]
    step = pending["step"]
    tt, ct, up = pending.get("tempToken"), pending.get("connectToken"), pending.get("userProfile")
    opts = {str(o["id"]): o for o in pending.get("options") or []}
    try:
        if step == "select_page":
            body = {"profileId": profile_id, "tempToken": tt, "userProfile": up}
            body.update({"pageId": ids[0]} if len(ids) == 1 else {"pageIds": ids})
            res = await client.connect_post("facebook/select-page", body, ct)
        elif step == "select_account":
            body = {"profileId": profile_id, "tempToken": tt}
            body.update({"pageId": ids[0]} if len(ids) == 1 else {"pageIds": ids})
            res = await client.connect_post("instagram/select-account", body, ct)
        elif step == "select_organization":
            chosen = opts[ids[0]]
            atype = "personal" if chosen.get("account_type") == "personal" else "organization"
            body = {"profileId": profile_id, "tempToken": tt, "userProfile": up, "accountType": atype}
            if atype == "organization":
                body["selectedOrganization"] = {k: v for k, v in {
                    "id": chosen["id"], "urn": chosen.get("urn"), "name": chosen.get("name"),
                    "vanityName": chosen.get("vanity_name")}.items() if v}
            res = await client.connect_post("linkedin/select-organization", body, ct)
        elif step == "select_board":
            chosen = opts[ids[0]]
            body = {"profileId": profile_id, "boardId": chosen["id"], "boardName": chosen.get("name"),
                    "tempToken": tt, "userProfile": up}
            if pending.get("refreshToken"):
                body["refreshToken"] = pending["refreshToken"]
            if pending.get("expiresIn"):
                body["expiresIn"] = pending["expiresIn"]
            res = await client.connect_post("pinterest/select-board", body, ct)
        elif step == "select_location":
            locs = [{"locationId": i, **({"accountId": opts[i].get("account_id")} if opts[i].get("account_id") else {})} for i in ids]
            body = {"profileId": profile_id, "pendingDataToken": pending.get("pendingDataToken")}
            body.update(locs[0] if len(locs) == 1 else {"locations": locs})
            res = await client.connect_post("googlebusiness/select-location", body, ct)
        elif step == "select_public_profile":
            chosen = opts[ids[0]]
            body = {"profileId": profile_id, "tempToken": tt, "userProfile": up,
                    "selectedPublicProfile": {"id": chosen["id"], "display_name": chosen.get("name") or chosen["id"],
                                              "username": chosen.get("username")}}
            res = await client.connect_post("snapchat/select-profile", body, ct)
        elif step == "select_phone_number":
            chosen = opts[ids[0]]
            body = {"profileId": profile_id, "phoneNumberId": chosen["id"], "wabaId": chosen.get("waba_id"),
                    "tempToken": tt, "userProfile": up}
            res = await client.connect_post("whatsapp/select-phone-number", body, ct)
        else:
            raise HTTPException(status_code=400, detail={"error": "unknown_step", "message": "Unexpected provider step."})
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        store_update(session["nonce"], status="failed", error="select_failed")
        raise provider_error(f"connect select {step}", exc)

    res = res or {}
    created = [a for a in (res.get("accounts") or []) if isinstance(a, dict)] or ([res["account"]] if isinstance(res.get("account"), dict) else [])
    account_ids = [str(a.get("accountId") or a.get("_id") or "") for a in created if a.get("accountId") or a.get("_id")]
    if res.get("adsAccountId"):
        account_ids.append(str(res["adsAccountId"]))
    if not account_ids:
        store_update(session["nonce"], status="failed", error="no_account_created")
        raise HTTPException(status_code=502, detail={"error": "provider_no_account", "message": "The provider did not report a connected account."})
    accounts = await _confirm_and_map(client, tenant_id, profile_id, account_ids)
    failed = [{"id": f.get("id"), "message": str(f.get("message") or "")[:200]} for f in (res.get("failed") or []) if isinstance(f, dict)]
    store_update(session["nonce"], status="completed", completed_at=_now(), pending_enc=None)
    out: Dict[str, Any] = {"status": "connected", "accounts": accounts, "return_to": session.get("return_to")}
    if failed:
        out["failed"] = failed
    return out


# ───────────────────────── credential / code based platforms ─────────────────────────


class BlueskyIn(BaseModel):
    identifier: str = Field(..., min_length=3, max_length=320)
    app_password: str = Field(..., min_length=8, max_length=200)


@router.post("/social/connect/credentials/bluesky")
async def connect_bluesky(
    body: BlueskyIn,
    auth: AuthContext = Depends(require_marketing_admin),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Bluesky uses an app password (never the account password). It is forwarded once to the
    provider and not stored or logged by OmniDome."""
    mk = _mk()
    client = _client()
    try:
        profile_id = await mk._ensure_tenant_profile(tenant_id)
        user_id = await client.get_current_user_id()
        res = await client.connect_post("bluesky/credentials", {
            "identifier": body.identifier, "appPassword": body.app_password, "state": f"{user_id}-{profile_id}",
        })
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise provider_error("bluesky connect", exc)
    aid = ((res or {}).get("account") or {}).get("accountId") or ((res or {}).get("account") or {}).get("_id")
    if not aid:
        # Response may omit the id; resolve by username among this profile's accounts.
        mine = await _tenant_accounts_by_id(client, profile_id)
        match = [k for k, v in mine.items() if v.get("platform") == "bluesky" and
                 str(v.get("username") or "").lower() == body.identifier.lower().lstrip("@")]
        aid = match[0] if match else None
    if not aid:
        raise HTTPException(status_code=502, detail={"error": "provider_no_account", "message": "The provider did not report a connected account."})
    accounts = await _confirm_and_map(client, tenant_id, profile_id, [str(aid)])
    return {"status": "connected", "accounts": accounts}


@router.post("/social/connect/telegram/start")
async def connect_telegram_start(
    auth: AuthContext = Depends(require_marketing_admin),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Returns the access code to send to the Telegram bot (valid 15 minutes) and a `state` to poll with."""
    mk = _mk()
    client = _client()
    try:
        profile_id = await mk._ensure_tenant_profile(tenant_id)
        res = await client.connect_get("telegram", {"profileId": profile_id})
    except Exception as exc:  # noqa: BLE001
        raise provider_error("telegram code", exc)
    exp = _now() + STATE_TTL
    st = make_state(str(tenant_id), str(auth.user_id), "telegram", profile_id, exp)
    store_create({
        "nonce": st["nonce"], "tenant_id": str(tenant_id), "user_id": str(auth.user_id), "platform": "telegram",
        "category": "social", "profile_id": profile_id, "flow": "telegram_code", "reconnect": None, "return_to": None,
        "options": json.dumps({"code": res.get("code")}), "expires_at": exp,
    })
    return {"status": "pending", "state": st["st"], "code": res.get("code"), "bot_username": res.get("botUsername"),
            "expires_in": res.get("expiresIn"), "instructions": res.get("instructions") or []}


@router.get("/social/connect/telegram/status")
async def connect_telegram_status(
    state: str = Query(...),
    auth: AuthContext = Depends(require_marketing_admin),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    session = load_session(state, auth, tenant_id)
    code = (session.get("options") or {}).get("code")
    if session["platform"] != "telegram" or not code:
        raise HTTPException(status_code=400, detail={"error": "invalid_state", "message": "Invalid connection state."})
    client = _client()
    try:
        res = await client._request("PATCH", "/connect/telegram", params={"code": code})
    except Exception as exc:  # noqa: BLE001
        raise provider_error("telegram status", exc)
    st = (res or {}).get("status")
    if st == "connected":
        aid = ((res or {}).get("account") or {}).get("_id")
        if not aid:
            raise HTTPException(status_code=502, detail={"error": "provider_no_account", "message": "The provider did not report a connected account."})
        accounts = await _confirm_and_map(client, tenant_id, session["profile_id"], [str(aid)])
        store_update(session["nonce"], status="completed", completed_at=_now())
        return {"status": "connected", "accounts": accounts}
    if st == "expired":
        store_update(session["nonce"], status="failed", error="expired")
    return {"status": st or "pending", "expires_in": (res or {}).get("expiresIn"), "message": (res or {}).get("message")}


# ───────────────────────── WhatsApp (in-app Embedded Signup) ─────────────────────────


@router.get("/social/connect/whatsapp/sdk-config")
async def whatsapp_sdk_config(
    auth: AuthContext = Depends(require_marketing_admin),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Meta app id + Embedded Signup config id so OmniDome can open Meta's signup popup itself
    (FB.login with `config_id`, `response_type: 'code'`, `extras: {setup: {}, sessionInfoVersion: 3}`).
    Also returns a one-time `state` that binds the follow-up call to this tenant and user."""
    mk = _mk()
    client = _client()
    try:
        profile_id = await mk._ensure_tenant_profile(tenant_id)
        cfg = await client.connect_get("whatsapp/sdk-config")
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise provider_error("whatsapp sdk-config", exc)
    exp = _now() + STATE_TTL
    st = make_state(str(tenant_id), str(auth.user_id), "whatsapp", profile_id, exp)
    store_create({
        "nonce": st["nonce"], "tenant_id": str(tenant_id), "user_id": str(auth.user_id), "platform": "whatsapp",
        "category": "social", "profile_id": profile_id, "flow": "embedded_signup", "reconnect": None,
        "return_to": None, "options": "{}", "expires_at": exp,
    })
    return {"app_id": cfg.get("appId"), "config_id": cfg.get("configId"), "branding": cfg.get("branding"),
            "state": st["st"], "expires_in": int(STATE_TTL.total_seconds())}


class WhatsAppSignupIn(BaseModel):
    state: str
    code: str = Field(..., min_length=5, max_length=2000, description="Authorization code from the WA_EMBEDDED_SIGNUP flow")
    waba_id: Optional[str] = None
    phone_number_id: Optional[str] = None
    is_coexistence: Optional[bool] = None


@router.post("/social/connect/whatsapp/embedded-signup")
async def whatsapp_embedded_signup(
    body: WhatsAppSignupIn,
    auth: AuthContext = Depends(require_marketing_admin),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Exchange the Embedded Signup code (from OmniDome's own popup) for a connected WhatsApp number."""
    session = load_session(body.state, auth, tenant_id)
    if session["platform"] != "whatsapp":
        raise HTTPException(status_code=400, detail={"error": "invalid_state", "message": "Invalid connection state."})
    client = _client()
    payload: Dict[str, Any] = {"code": body.code, "profileId": session["profile_id"]}
    for k, v in (("wabaId", body.waba_id), ("phoneNumberId", body.phone_number_id), ("isCoexistence", body.is_coexistence)):
        if v is not None:
            payload[k] = v
    try:
        res = await client.connect_post("whatsapp/embedded-signup", payload)
    except Exception as exc:  # noqa: BLE001
        raise provider_error("whatsapp embedded signup", exc)
    aid = ((res or {}).get("account") or {}).get("accountId")
    if not aid:
        raise HTTPException(status_code=502, detail={"error": "provider_no_account", "message": "The provider did not report a connected account."})
    accounts = await _confirm_and_map(client, tenant_id, session["profile_id"], [str(aid)])
    store_update(session["nonce"], status="completed", completed_at=_now())
    return {"status": "connected", "accounts": accounts}


class WhatsAppCredentialsIn(BaseModel):
    access_token: str = Field(..., min_length=20, max_length=1000, description="Permanent System User token (never stored by OmniDome)")
    waba_id: str = Field(..., min_length=3, max_length=64)
    phone_number_id: str = Field(..., min_length=3, max_length=64)
    pin: Optional[str] = Field(None, pattern=r"^\d{6}$")


@router.post("/social/connect/whatsapp/credentials")
async def whatsapp_credentials(
    body: WhatsAppCredentialsIn,
    auth: AuthContext = Depends(require_marketing_admin),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Connect a number by Meta credentials instead of the popup. Note (provider behaviour):
    connecting re-points this WABA's webhook delivery to the provider."""
    mk = _mk()
    client = _client()
    payload: Dict[str, Any] = {"accessToken": body.access_token, "wabaId": body.waba_id, "phoneNumberId": body.phone_number_id}
    if body.pin:
        payload["pin"] = body.pin
    try:
        profile_id = await mk._ensure_tenant_profile(tenant_id)
        payload["profileId"] = profile_id
        res = await client.connect_post("whatsapp/credentials", payload)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise provider_error("whatsapp credentials", exc)
    aid = ((res or {}).get("account") or {}).get("accountId")
    if not aid:
        raise HTTPException(status_code=502, detail={"error": "provider_no_account", "message": "The provider did not report a connected account."})
    accounts = await _confirm_and_map(client, tenant_id, profile_id, [str(aid)])
    out: Dict[str, Any] = {"status": "connected", "accounts": accounts}
    if res.get("registrationWarning"):
        out["warning"] = str(res["registrationWarning"])[:300]
    return out


# ───────────────────────── disconnect ─────────────────────────


@router.delete("/social/connect/accounts/{account_id}")
async def disconnect_connected_account(
    account_id: str,
    auth: AuthContext = Depends(require_marketing_admin),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Disconnect an account from the provider and mark it disconnected for the tenant. Only
    accounts verified as belonging to the tenant's profile can be disconnected."""
    mk = _mk()
    client = _client()
    profile_id = mk._get_tenant_profile(tenant_id)
    if not profile_id:
        raise HTTPException(status_code=404, detail={"error": "no_profile", "message": "No connections exist for this workspace."})
    mine = await _tenant_accounts_by_id(client, profile_id)
    if account_id not in mine:
        raise HTTPException(status_code=404, detail={"error": "account_not_found", "message": "Account not found in this workspace."})
    try:
        await client.disconnect_account(account_id)
    except Exception as exc:  # noqa: BLE001
        raise provider_error("disconnect", exc)
    mk._upsert_connected_account(str(tenant_id), profile_id, {"accountId": account_id}, status="disconnected")
    return {"status": "disconnected", "account_id": account_id}
