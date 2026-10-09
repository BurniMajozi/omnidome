"""Telephony service layer: provisioning (config volume + PBX reload), admission control for outbound
calls, WebRTC credentials, trunk status, recording access.

`Telephony` is the runtime object (one per process; the call-center service runs a single worker).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import httpx
from sqlalchemy import delete, select

from services.call_center import policy
from services.call_center.database import (
    Agent, CallQueue, CallSession, ProviderCredential, TelephonySettings, WebrtcEndpointRow, _get_session_factory,
)
from services.call_center.telephony import confgen, numbers
from services.call_center.telephony.ari import AriClient, AriError, ari_settings, run_forever
from services.call_center.telephony.bridge import TelephonyBridge, TenantRoute
from services.call_center.telephony.confgen import ConfigError, TrunkConfig, WebrtcEndpoint
from services.call_center.telephony.store import DEFAULT_ALLOWED_PREFIXES, DbStore, route_from_settings
from services.common import secretbox

logger = logging.getLogger("call_center.telephony")

MAX_WEBRTC_PER_AGENT = 3
_REC_NAME = re.compile(r"^([0-9a-f]{32})_([0-9a-f]{32})$")


class TelephonyError(Exception):
    """Maps to an HTTP error. `code` is a stable machine-readable string for the UI."""

    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def hard_limits() -> Dict[str, int]:
    return {"concurrent": _int_env("TELEPHONY_HARD_MAX_CONCURRENT", 50),
            "seconds": _int_env("TELEPHONY_HARD_MAX_SECONDS", 4 * 3600),
            "per_hour": _int_env("TELEPHONY_HARD_MAX_PER_HOUR", 200)}


def webrtc_ttl_seconds() -> int:
    return max(60, min(3600, _int_env("TELEPHONY_WEBRTC_TTL_SECONDS", 900)))


def ice_servers() -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    stun = [u.strip() for u in os.getenv("TELEPHONY_STUN_URLS", "stun:stun.l.google.com:19302").split(",") if u.strip()]
    if stun:
        out.append({"urls": stun})
    turn = os.getenv("TELEPHONY_TURN_URL", "").strip()
    if turn:
        out.append({"urls": [u.strip() for u in turn.split(",") if u.strip()],
                    "username": os.getenv("TELEPHONY_TURN_USERNAME", ""),
                    "credential": os.getenv("TELEPHONY_TURN_CREDENTIAL", "")})
    return out


# ── settings ───────────────────────────────────────────────────────────────

def default_settings(tenant_id) -> Dict[str, Any]:
    return {"tenant_id": str(tenant_id), "enabled": False, "dids": [], "inbound_queue_id": None,
            "allowed_prefixes": list(DEFAULT_ALLOWED_PREFIXES), "blocked_prefixes": [],
            "max_concurrent_calls": 5, "max_call_seconds": 3600, "max_calls_per_agent_hour": 30,
            "recording_enabled": False, "recording_announcement_confirmed": False}


def settings_view(row: Optional[TelephonySettings], tenant_id) -> Dict[str, Any]:
    if row is None:
        d = default_settings(tenant_id)
        d["recording_effective"] = False
        return d
    return {"tenant_id": str(row.tenant_id), "enabled": bool(row.enabled), "dids": list(row.dids or []),
            "inbound_queue_id": str(row.inbound_queue_id) if row.inbound_queue_id else None,
            "allowed_prefixes": list(row.allowed_prefixes or []), "blocked_prefixes": list(row.blocked_prefixes or []),
            "max_concurrent_calls": row.max_concurrent_calls, "max_call_seconds": row.max_call_seconds,
            "max_calls_per_agent_hour": row.max_calls_per_agent_hour,
            "recording_enabled": bool(row.recording_enabled),
            "recording_announcement_confirmed": bool(row.recording_announcement_confirmed),
            "recording_effective": bool(row.recording_enabled and row.recording_announcement_confirmed)}


def validate_settings_patch(patch: Dict[str, Any]) -> Dict[str, Any]:
    """Return a cleaned copy of the supplied fields or raise TelephonyError(422)."""
    out: Dict[str, Any] = {}
    hard = hard_limits()
    try:
        if "dids" in patch:
            dids = [confgen.validate_did(d.strip()) for d in patch["dids"]]
            if len(dids) > 50:
                raise ConfigError("at most 50 DIDs")
            out["dids"] = list(dict.fromkeys(dids))
        if "allowed_prefixes" in patch:
            out["allowed_prefixes"] = numbers.validate_prefixes(patch["allowed_prefixes"])
        if "blocked_prefixes" in patch:
            out["blocked_prefixes"] = numbers.validate_prefixes(patch["blocked_prefixes"])
    except (ConfigError, ValueError) as exc:
        raise TelephonyError(422, "invalid_settings", str(exc))
    for key, lo, hi in (("max_concurrent_calls", 1, hard["concurrent"]), ("max_call_seconds", 30, hard["seconds"]),
                        ("max_calls_per_agent_hour", 1, hard["per_hour"])):
        if key in patch:
            v = patch[key]
            if not isinstance(v, int) or isinstance(v, bool) or not lo <= v <= hi:
                raise TelephonyError(422, "invalid_settings", f"{key} must be between {lo} and {hi}")
            out[key] = v
    for key in ("enabled", "recording_enabled", "recording_announcement_confirmed"):
        if key in patch:
            if not isinstance(patch[key], bool):
                raise TelephonyError(422, "invalid_settings", f"{key} must be true or false")
            out[key] = patch[key]
    if "inbound_queue_id" in patch:
        out["inbound_queue_id"] = patch["inbound_queue_id"]
    return out


# ── pure helpers ──────────────────────────────────────────────────────────

def parse_registration_status(lines: List[str], trunk: str) -> Optional[str]:
    """Registration state ('registered' | 'rejected' | 'unregistered' | ...) from `pjsip list registrations`
    output, or None when the trunk is not listed (config not loaded yet)."""
    for line in lines:
        if trunk in line:
            m = re.search(re.escape(trunk) + r"\S*\s+\S+\s+(\w+)\s*$", line.strip())
            if m:
                return m.group(1).lower()
            low = line.lower()
            for word in ("unregistered", "rejected", "registered", "stopped"):
                if word in low:
                    return word
    return None


def recording_path(root: Path, tenant_id, recording_ref: str) -> Optional[Path]:
    """Resolve 'asterisk/<tenanthex>_<sessionhex>.wav' to a file under `root`; None if it is not that tenant's."""
    m = re.fullmatch(r"asterisk/([0-9a-f]{32}_[0-9a-f]{32})\.wav", recording_ref or "")
    if not m:
        return None
    name = m.group(1)
    t = _REC_NAME.match(name)
    if not t or t.group(1) != confgen.tenant_hex(tenant_id):
        return None
    path = (root / f"{name}.wav").resolve()
    return path if path.parent == root.resolve() else None


# ── provisioning ──────────────────────────────────────────────────────────

class Provisioner:
    """Renders per-tenant config into the shared volume and asks the PBX to reload (admin sidecar)."""

    def __init__(self, factory, root: Optional[Path] = None, admin_url: Optional[str] = None,
                 admin_token: Optional[str] = None, http: Optional[httpx.AsyncClient] = None):
        self._factory = factory
        self.root = Path(root or os.getenv("TELEPHONY_GENERATED_DIR", "/asterisk-generated"))
        self.admin_url = (admin_url if admin_url is not None else os.getenv("ASTERISK_ADMIN_URL", "")).rstrip("/")
        self._token = admin_token if admin_token is not None else os.getenv("ASTERISK_ADMIN_TOKEN", "")
        self._http = http
        self._lock = asyncio.Lock()
        self.errors: Dict[str, str] = {}
        self.last_reload_error: Optional[str] = None

    def __repr__(self) -> str:
        return f"Provisioner(root={str(self.root)!r}, admin_url={self.admin_url!r})"

    @property
    def admin_configured(self) -> bool:
        return bool(self.admin_url and self._token)

    async def admin(self, method: str, path: str) -> Any:
        if not self.admin_configured:
            raise TelephonyError(503, "pbx_unavailable", "PBX admin endpoint is not configured")
        client = self._http or httpx.AsyncClient(timeout=15.0)
        try:
            resp = await client.request(method, f"{self.admin_url}{path}",
                                        headers={"Authorization": f"Bearer {self._token}"})
        except httpx.HTTPError as exc:
            raise TelephonyError(503, "pbx_unavailable", f"PBX admin unreachable ({type(exc).__name__})")
        finally:
            if self._http is None:
                await client.aclose()
        if resp.status_code != 200:
            raise TelephonyError(503, "pbx_unavailable", f"PBX admin returned HTTP {resp.status_code}")
        return resp.json()

    async def _load(self) -> Tuple[List[TelephonySettings], Dict[Any, ProviderCredential], Dict[Any, List[WebrtcEndpointRow]]]:
        now = datetime.now(timezone.utc)
        async with self._factory() as db:
            settings = (await db.execute(select(TelephonySettings).where(TelephonySettings.enabled.is_(True)))).scalars().all()
            creds = (await db.execute(select(ProviderCredential).where(ProviderCredential.provider == "sip"))).scalars().all()
            eps = (await db.execute(select(WebrtcEndpointRow))).scalars().all()
        by_ep: Dict[Any, List[WebrtcEndpointRow]] = {}
        for e in eps:
            exp = e.expires_at if e.expires_at.tzinfo else e.expires_at.replace(tzinfo=timezone.utc)
            if exp > now:
                by_ep.setdefault(e.tenant_id, []).append(e)
        return list(settings), {c.tenant_id: c for c in creds}, by_ep

    def trunk_for(self, cred: Optional[ProviderCredential]) -> Tuple[Optional[TrunkConfig], Optional[str]]:
        if cred is None:
            return None, None
        try:
            return TrunkConfig.from_credentials(json.loads(secretbox.decrypt(cred.config_enc))), None
        except ConfigError as exc:
            return None, str(exc)
        except (secretbox.SecretsUnavailable, ValueError):
            return None, "stored SIP credentials cannot be read (check SECRETS_ENCRYPTION_KEY)"

    def render_all(self, settings, creds, eps) -> Dict[str, str]:
        # placeholders keep the PBX's #include globs non-empty before the first tenant is provisioned
        files: Dict[str, str] = {"pjsip_00base.conf": "; omnidome generated config\n",
                                 "ext_00base.conf": "; omnidome generated config\n"}
        self.errors = {}
        for s in settings:
            hx = confgen.tenant_hex(s.tenant_id)
            trunk, err = self.trunk_for(creds.get(s.tenant_id))
            dids = list(s.dids or []) if trunk else []
            try:
                webrtc = [WebrtcEndpoint(e.endpoint_id, e.md5_cred) for e in eps.get(s.tenant_id, [])]
                files[f"pjsip_{hx}.conf"] = confgen.render_pjsip(s.tenant_id, trunk, webrtc)
                files[f"ext_{hx}.conf"] = confgen.render_dialplan(s.tenant_id, dids)
            except ConfigError as exc:
                err = err or str(exc)
            if err:
                self.errors[hx] = err
        return files

    async def reconcile(self) -> Dict[str, Any]:
        async with self._lock:
            settings, creds, eps = await self._load()
            files = self.render_all(settings, creds, eps)
            changed = False
            try:
                self.root.mkdir(parents=True, exist_ok=True)
                for name, content in files.items():
                    path = self.root / name
                    if path.exists() and path.read_text(encoding="utf-8") == content:
                        continue
                    tmp = path.with_suffix(".tmp")
                    tmp.write_text(content, encoding="utf-8")
                    os.chmod(tmp, 0o644)
                    os.replace(tmp, path)
                    changed = True
                for stale in [p for p in self.root.iterdir()
                              if p.suffix == ".conf" and p.name.startswith(("pjsip_", "ext_")) and p.name not in files]:
                    stale.unlink()
                    changed = True
            except OSError as exc:
                self.last_reload_error = f"cannot write PBX config ({type(exc).__name__})"
                return {"changed": False, "reloaded": False, "errors": dict(self.errors),
                        "reload_error": self.last_reload_error}
            reloaded = False
            if changed:
                try:
                    await self.admin("POST", "/reload")
                    reloaded, self.last_reload_error = True, None
                except TelephonyError as exc:
                    self.last_reload_error = exc.message
            return {"changed": changed, "reloaded": reloaded, "errors": dict(self.errors),
                    "reload_error": self.last_reload_error}

    async def registrations(self) -> List[str]:
        data = await self.admin("GET", "/registrations")
        return [str(x) for x in data.get("lines", [])]


# ── runtime ───────────────────────────────────────────────────────────────

class Telephony:
    def __init__(self, factory=None, ari: Optional[AriClient] = None, provisioner: Optional[Provisioner] = None,
                 store: Optional[DbStore] = None, bridge: Optional[TelephonyBridge] = None):
        self.factory = factory or _get_session_factory()
        self.ari = ari
        self.store = store or DbStore(self.factory, on_recording_ready=self._on_recording_ready)
        self.provisioner = provisioner or Provisioner(self.factory)
        self.bridge = bridge or (TelephonyBridge(ari, self.store, notice_media=os.getenv(
            "ASTERISK_RECORDING_NOTICE_SOUND", "sound:this-call-may-be-monitored-or-recorded")) if ari else None)
        self._tasks: List[asyncio.Task] = []
        self._reconcile_pending: Optional[asyncio.Task] = None

    @property
    def available(self) -> bool:
        return self.ari is not None and self.bridge is not None

    # lifecycle
    async def start(self) -> None:
        if not self.available:
            logger.info("telephony disabled: ASTERISK_ARI_URL / ASTERISK_ARI_PASSWORD not set")
            return
        await self.bridge.recover()
        self._tasks.append(asyncio.create_task(run_forever(self.ari, self.bridge.handle_event, self.bridge.set_link_state)))
        self._tasks.append(asyncio.create_task(self._reaper()))
        self.reconcile_soon(0.5)

    async def stop(self) -> None:
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        if self.ari:
            await self.ari.aclose()

    async def _reaper(self) -> None:
        while True:
            await asyncio.sleep(60)
            try:
                async with self.factory() as db:
                    await db.execute(delete(WebrtcEndpointRow).where(
                        WebrtcEndpointRow.expires_at < datetime.now(timezone.utc) - timedelta(minutes=5)))
                    await db.commit()
                await self.provisioner.reconcile()
            except Exception:  # noqa: BLE001
                logger.exception("telephony reaper failed")

    def reconcile_soon(self, delay: float = 2.0) -> None:
        """Debounced reconcile; the delay lets the request transaction commit first."""
        if not self.available and not self.provisioner.admin_configured:
            return
        if self._reconcile_pending and not self._reconcile_pending.done():
            return

        async def go():
            await asyncio.sleep(delay)
            try:
                await self.provisioner.reconcile()
            except Exception:  # noqa: BLE001
                logger.exception("telephony reconcile failed")
        self._reconcile_pending = asyncio.get_running_loop().create_task(go())

    # settings
    async def get_settings_row(self, tenant_id) -> Optional[TelephonySettings]:
        async with self.factory() as db:
            return (await db.execute(select(TelephonySettings).where(TelephonySettings.tenant_id == tenant_id))).scalar_one_or_none()

    async def update_settings(self, tenant_id, patch: Dict[str, Any]) -> Dict[str, Any]:
        clean = validate_settings_patch(patch)
        async with self.factory() as db:
            if clean.get("inbound_queue_id"):
                qid = clean["inbound_queue_id"] = uuid.UUID(str(clean["inbound_queue_id"]))
                if not (await db.execute(select(CallQueue.id).where(CallQueue.id == qid, CallQueue.tenant_id == tenant_id))).first():
                    raise TelephonyError(404, "queue_not_found", "Queue not found")
            row = (await db.execute(select(TelephonySettings).where(TelephonySettings.tenant_id == tenant_id))).scalar_one_or_none()
            if row is None:
                row = TelephonySettings(tenant_id=tenant_id, **{k: v for k, v in default_settings(tenant_id).items()
                                                               if k not in ("tenant_id", "inbound_queue_id")})
                db.add(row)
            if clean.get("dids"):
                for other in (await db.execute(select(TelephonySettings).where(TelephonySettings.tenant_id != tenant_id))).scalars():
                    clash = set(other.dids or []) & set(clean["dids"])
                    if clash:
                        raise TelephonyError(409, "did_in_use", "One of those numbers is already assigned to another account")
            for k, v in clean.items():
                setattr(row, k, v)
            await db.commit()
            view = settings_view(row, tenant_id)
        self.reconcile_soon()
        return view

    # trunk
    async def load_trunk(self, tenant_id) -> Tuple[Optional[TrunkConfig], Optional[str], bool]:
        """(trunk, config_error, credentials_exist)"""
        async with self.factory() as db:
            cred = (await db.execute(select(ProviderCredential).where(
                ProviderCredential.tenant_id == tenant_id, ProviderCredential.provider == "sip"))).scalar_one_or_none()
        trunk, err = self.provisioner.trunk_for(cred)
        return trunk, err, cred is not None

    async def trunk_status(self, tenant_id, *, admin_view: bool = False) -> Dict[str, Any]:
        settings = await self.get_settings_row(tenant_id)
        trunk, err, exists = await self.load_trunk(tenant_id)
        out: Dict[str, Any] = {
            "available": self.available, "bridge_connected": bool(self.bridge and self.bridge.connected),
            "enabled": bool(settings and settings.enabled), "configured": exists and err is None,
            "registered": False, "state": "not_configured", "detail": "No SIP trunk configured",
            "mode": trunk.auth_mode if trunk else None, "last_error": None,
        }
        if admin_view and trunk:
            out["host"], out["port"], out["transport"] = trunk.host, trunk.port, trunk.transport
        if not exists:
            return out
        if err:
            out.update(state="config_error", detail=f"Trunk credentials are unusable: {err}", last_error=err)
            return out
        if not self.available:
            out.update(state="pbx_unavailable", detail="Telephony server (Asterisk) is not connected",
                       last_error=(self.bridge.last_error if self.bridge else "ASTERISK_ARI_URL not set"))
            return out
        if not (settings and settings.enabled):
            out.update(state="disabled", detail="Telephony is switched off for this account")
            return out
        hx = confgen.tenant_hex(tenant_id)
        if hx in self.provisioner.errors:
            e = self.provisioner.errors[hx]
            out.update(state="config_error", detail=f"Trunk config not applied: {e}", last_error=e)
            return out
        name = confgen.trunk_name(tenant_id)
        try:
            if trunk.auth_mode == "registration":
                state = parse_registration_status(await self.provisioner.registrations(), name)
                if state is None:
                    out.update(state="not_loaded", detail="Trunk is configured but the PBX has not loaded it yet",
                               last_error=self.provisioner.last_reload_error)
                elif state == "registered":
                    out.update(registered=True, state="registered", detail="Trunk registered")
                else:
                    out.update(state=state, detail=f"Trunk not registered: {state}. Check host, username and password "
                               "with your provider.", last_error=state)
            else:
                ep = await self.ari.endpoint_state(name)
                if ep == "online":
                    out.update(registered=True, state="reachable", detail="Provider answered SIP OPTIONS (IP-auth trunk)")
                else:
                    out.update(state="unreachable", detail=f"Trunk not reachable: {ep or 'not loaded'}", last_error=ep)
        except TelephonyError as exc:
            out.update(state="pbx_unavailable", detail=exc.message, last_error=exc.message)
        except AriError as exc:
            out.update(state="pbx_unavailable", detail=str(exc), last_error=str(exc))
        return out

    async def test_registration(self, tenant_id, wait_seconds: float = 12.0) -> Dict[str, Any]:
        """Re-apply config and check registration. Never places a call."""
        result = await self.provisioner.reconcile()
        deadline = asyncio.get_running_loop().time() + wait_seconds
        status = await self.trunk_status(tenant_id, admin_view=True)
        while not status["registered"] and status["state"] in ("not_loaded", "unregistered", "registering") \
                and asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(1.5)
            status = await self.trunk_status(tenant_id, admin_view=True)
        status["applied"] = {"changed": result["changed"], "reloaded": result["reloaded"]}
        return status

    # agents / webrtc
    async def _agent_for_user(self, db, tenant_id, user_id) -> Optional[Agent]:
        return (await db.execute(select(Agent).where(Agent.tenant_id == tenant_id, Agent.user_id == user_id))).scalars().first()

    async def issue_webrtc(self, tenant_id, user_id) -> Dict[str, Any]:
        wss = os.getenv("TELEPHONY_WSS_URL", "").strip()
        if not self.available:
            raise TelephonyError(503, "pbx_unavailable", "Telephony server (Asterisk) is not connected")
        if not wss.startswith("wss://") and os.getenv("TELEPHONY_ALLOW_INSECURE_WS", "").lower() != "true":
            raise TelephonyError(503, "wss_not_configured", "TELEPHONY_WSS_URL (wss://...) is not configured")
        settings = await self.get_settings_row(tenant_id)
        if not (settings and settings.enabled):
            raise TelephonyError(409, "telephony_disabled", "Telephony is not enabled for this account")
        async with self.factory() as db:
            agent = await self._agent_for_user(db, tenant_id, user_id)
            if agent is None:
                raise TelephonyError(409, "no_agent_profile", "Your user is not linked to a call-center agent profile")
            endpoint_id = "w" + secrets.token_hex(10)
            password = secrets.token_urlsafe(24)
            ttl = webrtc_ttl_seconds()
            expires = datetime.now(timezone.utc) + timedelta(seconds=ttl)
            db.add(WebrtcEndpointRow(tenant_id=tenant_id, agent_id=agent.id, endpoint_id=endpoint_id,
                                     md5_cred=confgen.md5_cred(endpoint_id, password), expires_at=expires))
            old = (await db.execute(select(WebrtcEndpointRow).where(
                WebrtcEndpointRow.tenant_id == tenant_id, WebrtcEndpointRow.agent_id == agent.id
            ).order_by(WebrtcEndpointRow.created_at.desc()))).scalars().all()
            for extra in old[MAX_WEBRTC_PER_AGENT - 1:]:
                await db.delete(extra)
            display = agent.name
            agent_id = agent.id
            await db.commit()
        await self.provisioner.reconcile()
        domain = os.getenv("TELEPHONY_SIP_DOMAIN", "").strip() or (urlparse(wss).hostname or "omnidome.invalid")
        return {"sip_uri": f"sip:{endpoint_id}@{domain}", "username": endpoint_id, "password": password,
                "realm": confgen.REALM, "ws_url": wss, "ice_servers": ice_servers(), "display_name": display,
                "agent_id": str(agent_id), "expires_at": expires.isoformat(), "expires_in": ttl}

    # outbound
    async def _refuse(self, tenant_id, user_id, agent_id, to, code, status, message):
        await self.store.audit(tenant_id, "originate", f"refused:{code}", user_id=user_id, agent_id=agent_id, to_number=to)
        raise TelephonyError(status, code, message)

    async def place_call(self, *, tenant_id, user_id, is_admin: bool, to: str, agent_id=None) -> Dict[str, Any]:
        if not self.available:
            raise TelephonyError(503, "pbx_unavailable", "Telephony server (Asterisk) is not connected")
        raw_to = (to or "")[:40]
        async with self.factory() as db:
            if agent_id is not None:
                agent = (await db.execute(select(Agent).where(Agent.id == agent_id, Agent.tenant_id == tenant_id))).scalar_one_or_none()
                if agent is not None and not is_admin and agent.user_id != user_id:
                    agent = None
            else:
                agent = await self._agent_for_user(db, tenant_id, user_id)
            settings = (await db.execute(select(TelephonySettings).where(TelephonySettings.tenant_id == tenant_id))).scalar_one_or_none()
            ep_rows = []
            if agent is not None:
                ep_rows = (await db.execute(select(WebrtcEndpointRow).where(
                    WebrtcEndpointRow.tenant_id == tenant_id, WebrtcEndpointRow.agent_id == agent.id
                ).order_by(WebrtcEndpointRow.created_at.desc()))).scalars().all()
        aid = agent.id if agent else None
        if agent is None:
            await self._refuse(tenant_id, user_id, None, raw_to, "no_agent_profile", 403,
                               "No call-center agent profile is linked to this user")
        if not (settings and settings.enabled):
            await self._refuse(tenant_id, user_id, aid, raw_to, "telephony_disabled", 409, "Telephony is not enabled")
        try:
            e164 = numbers.normalize_e164(raw_to)
            numbers.check_dial_policy(e164, settings.allowed_prefixes or [], settings.blocked_prefixes or [])
        except numbers.NumberError as exc:
            await self._refuse(tenant_id, user_id, aid, raw_to, "invalid_number", 422, str(exc))
        except numbers.DialDenied as exc:
            msgs = {"blocked_prefix": "This destination is blocked (premium-rate or restricted range)",
                    "destination_not_allowed": "Calls to this country/prefix are not enabled for your account"}
            await self._refuse(tenant_id, user_id, aid, e164, exc.reason, 403, msgs.get(exc.reason, "Destination not allowed"))
        trunk, err, exists = await self.load_trunk(tenant_id)
        if not exists or err:
            await self._refuse(tenant_id, user_id, aid, e164, "no_trunk", 409, "No SIP trunk configured" if not exists else f"Trunk unusable: {err}")
        status = await self.trunk_status(tenant_id)
        if not status["registered"]:
            await self._refuse(tenant_id, user_id, aid, e164, "trunk_not_registered", 409, f"Trunk not registered: {status['state']}")
        hard = hard_limits()
        per_hour = min(settings.max_calls_per_agent_hour or 30, hard["per_hour"])
        if await self.store.agent_calls_last_hour(tenant_id, aid) >= per_hour:
            await self._refuse(tenant_id, user_id, aid, e164, "agent_hourly_limit", 429, "Hourly call limit reached for this agent")
        route = route_from_settings(settings)
        route.max_concurrent_calls = min(route.max_concurrent_calls, hard["concurrent"])
        route.max_call_seconds = min(route.max_call_seconds, hard["seconds"])
        if self.bridge.active_count(tenant_id) >= route.max_concurrent_calls:
            await self._refuse(tenant_id, user_id, aid, e164, "max_concurrent_calls", 429, "Your account has reached its concurrent call limit")
        now = datetime.now(timezone.utc)
        ep = next((r.endpoint_id for r in ep_rows if (r.expires_at if r.expires_at.tzinfo else r.expires_at.replace(tzinfo=timezone.utc)) > now), None)
        if ep is None or (await self._endpoint_state(ep)) != "online":
            await self._refuse(tenant_id, user_id, aid, e164, "softphone_not_registered", 409,
                               "Your softphone is not registered. Open the softphone and wait for 'Ready'.")
        audit_id = await self.store.audit(tenant_id, "originate", "accepted", user_id=user_id, agent_id=aid, to_number=e164)
        caller = trunk.caller_id
        try:
            call = await self.bridge.start_outbound(route=route, agent_id=aid, agent_endpoint=ep, number=e164,
                                                    trunk_endpoint=confgen.trunk_name(tenant_id), caller_id=caller)
        except PermissionError as exc:
            await self.store.update_audit(tenant_id, audit_id, f"refused:{exc}")
            raise TelephonyError(429 if "concurrent" in str(exc) else 409, str(exc), "Call not allowed right now")
        except AriError as exc:
            await self.store.update_audit(tenant_id, audit_id, "failed:ari")
            raise TelephonyError(502, "pbx_error", str(exc))
        await self.store.update_audit(tenant_id, audit_id, "originated", call.session_id)
        return call.public()

    async def _endpoint_state(self, endpoint_id: str) -> Optional[str]:
        try:
            return await self.ari.endpoint_state(endpoint_id)
        except AriError:
            return None

    # in-call control
    def _call_for(self, tenant_id, user_id, is_admin, call_id: str):
        call = self.bridge.get_call(tenant_id, call_id) if self.bridge else None
        if call is None:
            raise TelephonyError(404, "call_not_found", "Call not found")
        return call

    async def _authorize(self, tenant_id, user_id, is_admin, call):
        if is_admin:
            return
        async with self.factory() as db:
            agent = await self._agent_for_user(db, tenant_id, user_id)
        if agent is None or call.agent_id != agent.id:
            raise TelephonyError(403, "not_your_call", "This call belongs to another agent")

    async def control(self, tenant_id, user_id, is_admin, call_id: str, action: str, **kw) -> Dict[str, Any]:
        call = self._call_for(tenant_id, user_id, is_admin, call_id)
        await self._authorize(tenant_id, user_id, is_admin, call)
        try:
            if action == "hangup":
                await self.bridge.hangup(tenant_id, call_id)
                return {"id": call_id, "state": "ended"}
            if action == "hold":
                return (await self.bridge.hold(tenant_id, call_id, bool(kw.get("on", True)))).public()
            if action == "dtmf":
                await self.bridge.dtmf(tenant_id, call_id, kw.get("digits", ""))
                return call.public()
            if action == "transfer":
                return await self._transfer(tenant_id, user_id, call, kw.get("to_agent_id"), kw.get("to_number"))
        except LookupError:
            raise TelephonyError(404, "call_not_found", "Call not found")
        except PermissionError as exc:
            raise TelephonyError(409, "bad_call_state", str(exc))
        except ValueError as exc:
            raise TelephonyError(422, "invalid_input", str(exc))
        except AriError as exc:
            raise TelephonyError(502, "pbx_error", str(exc))
        raise TelephonyError(400, "unknown_action", "Unknown action")

    async def _transfer(self, tenant_id, user_id, call, to_agent_id, to_number) -> Dict[str, Any]:
        if bool(to_agent_id) == bool(to_number):
            raise TelephonyError(422, "invalid_input", "Provide exactly one of to_agent_id or to_number")
        if to_agent_id:
            tid = uuid.UUID(str(to_agent_id))
            async with self.factory() as db:
                tgt = (await db.execute(select(Agent).where(Agent.id == tid, Agent.tenant_id == tenant_id))).scalar_one_or_none()
                eps = [] if tgt is None else (await db.execute(select(WebrtcEndpointRow).where(
                    WebrtcEndpointRow.tenant_id == tenant_id, WebrtcEndpointRow.agent_id == tid
                ).order_by(WebrtcEndpointRow.created_at.desc()))).scalars().all()
            if tgt is None:
                raise TelephonyError(404, "agent_not_found", "Agent not found")
            now = datetime.now(timezone.utc)
            ep = next((r.endpoint_id for r in eps if (r.expires_at if r.expires_at.tzinfo else r.expires_at.replace(tzinfo=timezone.utc)) > now), None)
            if ep is None or await self._endpoint_state(ep) != "online" or self.bridge.active_for_agent(tenant_id, tid):
                raise TelephonyError(409, "agent_unavailable", "That agent is not available")
            await self.store.audit(tenant_id, "transfer", "accepted", user_id=user_id, agent_id=tid, session_id=call.session_id)
            return (await self.bridge.transfer(tenant_id, call.id, endpoint=f"PJSIP/{ep}", caller_id=call.number,
                                               new_agent_id=tid)).public()
        # external number: identical dial policy as click-to-call
        settings = await self.get_settings_row(tenant_id)
        try:
            e164 = numbers.normalize_e164(to_number)
            numbers.check_dial_policy(e164, settings.allowed_prefixes or [], settings.blocked_prefixes or [])
        except numbers.NumberError as exc:
            await self.store.audit(tenant_id, "transfer", "refused:invalid_number", user_id=user_id, to_number=str(to_number)[:40])
            raise TelephonyError(422, "invalid_number", str(exc))
        except numbers.DialDenied as exc:
            await self.store.audit(tenant_id, "transfer", f"refused:{exc.reason}", user_id=user_id, to_number=e164)
            raise TelephonyError(403, exc.reason, "Destination not allowed")
        trunk, err, exists = await self.load_trunk(tenant_id)
        if not trunk:
            raise TelephonyError(409, "no_trunk", "No SIP trunk configured")
        await self.store.audit(tenant_id, "transfer", "accepted", user_id=user_id, to_number=e164, session_id=call.session_id)
        return (await self.bridge.transfer(tenant_id, call.id,
                                           endpoint=f"PJSIP/{e164}@{confgen.trunk_name(tenant_id)}",
                                           caller_id=trunk.caller_id)).public()

    # recordings (admin tier enforced by the route regex)
    async def recording_file(self, tenant_id, session_id) -> Path:
        async with self.factory() as db:
            s = (await db.execute(select(CallSession).where(CallSession.id == session_id, CallSession.tenant_id == tenant_id))).scalar_one_or_none()
        if s is None or not s.recording_url:
            raise TelephonyError(404, "no_recording", "No recording for this call")
        root = Path(os.getenv("TELEPHONY_RECORDINGS_DIR", "/asterisk-recordings"))
        path = recording_path(root, tenant_id, s.recording_url)
        if path is None or not path.is_file():
            raise TelephonyError(404, "no_recording", "Recording file is not available")
        return path

    async def transcribe_recording(self, tenant_id, session_id, user_id=None, language: str = "en") -> str:
        from services.call_center.deepgram_service import DeepgramError, transcribe_audio
        path = await self.recording_file(tenant_id, session_id)
        if path.stat().st_size > 200 * 1024 * 1024:
            raise TelephonyError(413, "recording_too_large", "Recording is too large to transcribe")
        data = await asyncio.get_running_loop().run_in_executor(None, path.read_bytes)
        try:
            res = await transcribe_audio(audio_bytes=data, tenant_id=str(tenant_id), language=language,
                                         user_id=str(user_id) if user_id else None)
        except DeepgramError as exc:
            raise TelephonyError(503, "stt_unavailable", str(exc))
        text = res.get("transcript", "")
        async with self.factory() as db:
            s = (await db.execute(select(CallSession).where(CallSession.id == session_id, CallSession.tenant_id == tenant_id))).scalar_one_or_none()
            if s and policy.consent_allows_recording(s.recording_consent):
                s.transcript = text
                await db.commit()
        return text

    async def _on_recording_ready(self, tenant_id, session_id) -> None:
        if os.getenv("TELEPHONY_AUTO_TRANSCRIBE", "").strip().lower() in {"1", "true", "yes", "on"}:
            try:
                await self.transcribe_recording(tenant_id, session_id)
            except TelephonyError as exc:
                logger.warning("auto-transcribe skipped: %s", exc.code)


_runtime: Optional[Telephony] = None


def build_runtime() -> Telephony:
    cfg = ari_settings()
    ari = AriClient(cfg["url"], cfg["user"], cfg["password"], cfg["app"]) if cfg else None
    return Telephony(ari=ari)


def get_runtime() -> Telephony:
    global _runtime
    if _runtime is None:
        _runtime = build_runtime()
    return _runtime


def set_runtime(rt: Optional[Telephony]) -> None:
    global _runtime
    _runtime = rt
