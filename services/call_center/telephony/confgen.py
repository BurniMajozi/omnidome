"""Strict validation + rendering of Asterisk config for one tenant. Pure: no I/O.

Security model: nothing from a tenant ever reaches a config file unless it passed an allow-list
validator here. Hosts/usernames/DIDs are restricted to safe character sets; passwords may not contain
characters that are special in Asterisk config (`;`, backslash, `${`, control chars) and are REJECTED
rather than escaped. Object names are derived from UUID hex, never from tenant text. The dialplan never
interpolates tenant text other than validated digits.
"""

from __future__ import annotations

import hashlib
import ipaddress
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Sequence

REALM = "omnidome"
APP_NAME = "omnidome"  # Stasis application name (must match ASTERISK_ARI_APP in the asterisk container)

_HOST_LABEL = re.compile(r"^(?!-)[A-Za-z0-9-]{1,63}(?<!-)$")
_USERNAME = re.compile(r"^[A-Za-z0-9._+@=-]{1,64}$")
_CALLER_ID = re.compile(r"^\+?[0-9]{3,20}$")
_CALLER_NAME = re.compile(r"^[A-Za-z0-9 ._-]{0,40}$")
_DID = re.compile(r"^\+[1-9][0-9]{7,14}$")
_ENDPOINT_ID = re.compile(r"^w[0-9a-f]{20}$")
TRANSPORTS = {"udp": "transport-udp", "tcp": "transport-tcp", "tls": "transport-tls"}
AUTH_MODES = ("registration", "ip")


class ConfigError(ValueError):
    """Tenant-supplied SIP settings are unusable. The message never contains the offending secret."""


def tenant_hex(tenant_id) -> str:
    return uuid.UUID(str(tenant_id)).hex


def trunk_name(tenant_id) -> str:
    return f"trk_{tenant_hex(tenant_id)}"


def inbound_context(tenant_id) -> str:
    return f"in_{tenant_hex(tenant_id)}"


def agent_context(tenant_id) -> str:
    return f"ag_{tenant_hex(tenant_id)}"


def validate_host(host: str) -> str:
    host = (host or "").strip()
    if not host or len(host) > 253:
        raise ConfigError("SIP host is missing or too long")
    try:
        return str(ipaddress.IPv4Address(host))
    except ValueError:
        pass
    if ":" in host:
        raise ConfigError("IPv6 trunk hosts are not supported; use a hostname")
    if not all(_HOST_LABEL.fullmatch(label) for label in host.rstrip(".").split(".")):
        raise ConfigError("SIP host must be a hostname or IPv4 address")
    return host.rstrip(".")


def validate_port(value) -> int:
    try:
        port = int(str(value).strip())
    except (TypeError, ValueError):
        raise ConfigError("SIP port must be a number")
    if not 1 <= port <= 65535:
        raise ConfigError("SIP port out of range")
    return port


def validate_username(value: str) -> str:
    if not _USERNAME.fullmatch(value or ""):
        raise ConfigError("SIP username has unsupported characters (allowed: letters, digits . _ + @ = -)")
    return value


def validate_secret(value: str) -> str:
    v = value or ""
    if not v or len(v) > 128:
        raise ConfigError("SIP password is missing or too long")
    if v != v.strip():
        raise ConfigError("SIP password must not start or end with a space")
    if any(ord(c) < 0x20 or ord(c) > 0x7E for c in v) or ";" in v or "\\" in v or "${" in v:
        raise ConfigError("SIP password contains characters that cannot be written safely to the PBX config "
                          "(no ; backslash ${ or control/non-ASCII characters)")
    return v


def validate_did(value: str) -> str:
    if not _DID.fullmatch(value or ""):
        raise ConfigError("DIDs must be E.164 numbers such as +27211234567")
    return value


@dataclass(frozen=True)
class TrunkConfig:
    host: str
    port: int
    username: str
    password: str
    transport: str = "udp"
    auth_mode: str = "registration"
    caller_id: Optional[str] = None
    caller_name: str = ""

    def __repr__(self) -> str:  # never leak the password through logging / tracebacks
        return f"TrunkConfig(host={self.host!r}, port={self.port}, transport={self.transport!r}, auth_mode={self.auth_mode!r})"

    @classmethod
    def from_credentials(cls, fields: Dict[str, str]) -> "TrunkConfig":
        f = {str(k).strip().lower(): (v if isinstance(v, str) else str(v)) for k, v in (fields or {}).items()}
        transport = (f.get("transport") or "udp").strip().lower()
        if transport not in TRANSPORTS:
            raise ConfigError("transport must be udp, tcp or tls")
        auth_mode = (f.get("auth_mode") or "registration").strip().lower()
        if auth_mode not in AUTH_MODES:
            raise ConfigError("auth_mode must be 'registration' or 'ip'")
        host = validate_host(f.get("host", ""))
        port = validate_port(f.get("port") or (5061 if transport == "tls" else 5060))
        username = password = ""
        if auth_mode == "registration":
            username = validate_username(f.get("username", ""))
            password = validate_secret(f.get("password", ""))
        elif f.get("username"):
            username = validate_username(f["username"])
        cid = (f.get("caller_id") or "").strip() or None
        if cid and not _CALLER_ID.fullmatch(cid):
            raise ConfigError("caller_id must be digits (optionally with a leading +)")
        cname = (f.get("caller_name") or "").strip()
        if not _CALLER_NAME.fullmatch(cname):
            raise ConfigError("caller_name has unsupported characters")
        return cls(host, port, username, password, transport, auth_mode, cid, cname)


def check_fields(fields: Dict[str, str]) -> None:
    """Lenient save-time check: every field that IS present must be safe to render. Completeness
    (host, username, password...) is only enforced when the trunk is provisioned."""
    f = {str(k).strip().lower(): (v if isinstance(v, str) else str(v)) for k, v in (fields or {}).items()}
    checks = {"host": validate_host, "port": validate_port, "username": validate_username,
              "password": validate_secret}
    for key, fn in checks.items():
        if f.get(key):
            fn(f[key])
    if f.get("transport") and f["transport"].strip().lower() not in TRANSPORTS:
        raise ConfigError("transport must be udp, tcp or tls")
    if f.get("auth_mode") and f["auth_mode"].strip().lower() not in AUTH_MODES:
        raise ConfigError("auth_mode must be 'registration' or 'ip'")
    if f.get("caller_id") and not _CALLER_ID.fullmatch(f["caller_id"].strip()):
        raise ConfigError("caller_id must be digits (optionally with a leading +)")
    if f.get("caller_name") and not _CALLER_NAME.fullmatch(f["caller_name"].strip()):
        raise ConfigError("caller_name has unsupported characters")


@dataclass(frozen=True)
class WebrtcEndpoint:
    endpoint_id: str       # "w" + 20 hex
    md5_cred: str          # md5(endpoint:REALM:password); the plaintext password is never stored
    expires_at: Optional[datetime] = None

    def __post_init__(self):
        if not _ENDPOINT_ID.fullmatch(self.endpoint_id) or not re.fullmatch(r"[0-9a-f]{32}", self.md5_cred):
            raise ConfigError("invalid webrtc endpoint")


def md5_cred(endpoint_id: str, password: str) -> str:
    return hashlib.md5(f"{endpoint_id}:{REALM}:{password}".encode()).hexdigest()  # noqa: S324 (SIP digest auth)


def did_extensions(dids: Sequence[str]) -> List[str]:
    """Extension strings a provider may present for each DID (E.164 with/without +, ZA national 0-form)."""
    out: List[str] = []
    for did in dids:
        validate_did(did)
        digits = did[1:]
        variants = [digits, did]
        if digits.startswith("27"):
            variants.append("0" + digits[2:])
        for v in variants:
            if v not in out:
                out.append(v)
    return out


def render_pjsip(tenant_id, trunk: Optional[TrunkConfig], webrtc: Iterable[WebrtcEndpoint] = ()) -> str:
    """PJSIP objects for one tenant: its trunk (if configured) and its agents' WebRTC endpoints."""
    th = tenant_hex(tenant_id)
    name = trunk_name(tenant_id)
    lines: List[str] = [f"; generated for tenant {th} - do not edit"]
    if trunk is not None:
        t = TRANSPORTS[trunk.transport]
        server = f"sip:{trunk.host}:{trunk.port}"
        if trunk.transport != "udp":
            server += f";transport={trunk.transport}"
        lines += [
            f"[{name}]", "type=endpoint", f"transport={t}", f"context={inbound_context(tenant_id)}",
            "disallow=all", "allow=alaw,ulaw", f"aors={name}", "direct_media=no", "rtp_symmetric=yes",
            "force_rport=yes", "rewrite_contact=yes", "ice_support=no", "media_encryption=no",
            "trust_id_inbound=no", "send_pai=no", "send_rpid=no", f"set_var=OMNI_TENANT={th}",
        ]
        if trunk.auth_mode == "registration":
            lines += [f"outbound_auth={name}", f"from_user={trunk.username}", f"from_domain={trunk.host}"]
        lines += ["", f"[{name}]", "type=aor", f"contact={server}", "qualify_frequency=60", "max_contacts=1", ""]
        if trunk.auth_mode == "registration":
            lines += [
                f"[{name}]", "type=auth", "auth_type=userpass", f"username={trunk.username}",
                f"password={trunk.password}", "",
                f"[{name}]", "type=registration", f"transport={t}", f"outbound_auth={name}",
                f"server_uri={server}", f"client_uri=sip:{trunk.username}@{trunk.host}:{trunk.port}",
                f"contact_user={trunk.username}", "retry_interval=60", "forbidden_retry_interval=600",
                "expiration=3600", "line=yes", f"endpoint={name}", "",
            ]
        # inbound traffic is attributed to this tenant's trunk ONLY when it comes from the trunk host
        lines += [f"[{name}]", "type=identify", f"endpoint={name}", f"match={trunk.host}", ""]
    for ep in webrtc:
        lines += [
            f"[{ep.endpoint_id}]", "type=endpoint", "transport=transport-ws", f"context={agent_context(tenant_id)}",
            "disallow=all", "allow=opus,alaw,ulaw", "webrtc=yes", f"aors={ep.endpoint_id}", f"auth={ep.endpoint_id}",
            "direct_media=no", f"set_var=OMNI_TENANT={th}", "",
            f"[{ep.endpoint_id}]", "type=aor", "max_contacts=1", "remove_existing=yes", "remove_unavailable=yes",
            "qualify_frequency=30", "",
            f"[{ep.endpoint_id}]", "type=auth", "auth_type=md5", f"username={ep.endpoint_id}",
            f"md5_cred={ep.md5_cred}", f"realm={REALM}", "",
        ]
    return "\n".join(lines).rstrip() + "\n"


def render_dialplan(tenant_id, dids: Sequence[str]) -> str:
    """Per-tenant contexts. The trunk's context only knows this tenant's DIDs and hands them to Stasis with
    the tenant id baked in; the agents' context cannot dial anything (outbound goes through the API)."""
    th = tenant_hex(tenant_id)
    ext_lines: List[str] = []
    for did, variants in ((d, did_extensions([d])) for d in dids):
        for v in variants:
            ext_lines.append(f"exten => {v},1,Stasis({APP_NAME},inbound,{th},{did})")
    inbound = [f"[{inbound_context(tenant_id)}]", *ext_lines,
               "exten => _.,1,NoOp(unknown DID ignored)", " same => n,Hangup(1)", ""]
    agents = [f"[{agent_context(tenant_id)}]",
              "exten => _.,1,NoOp(agents cannot dial directly)", " same => n,Hangup(21)", ""]
    return f"; generated for tenant {th} - do not edit\n" + "\n".join(inbound + agents)
