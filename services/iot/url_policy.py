"""SSRF policy for tenant-supplied Home Assistant URLs.

Built on services/common/url_safety (same blocked-network table and `UnsafeUrl`), but a
Home Assistant is usually a private LAN box on :8123, so the rules differ:

* https only. IOT_ALLOW_HTTP=true also allows http (LAN Home Assistant without TLS).
* Loopback, link-local (incl. the 169.254.169.254 metadata address), CGNAT, multicast,
  reserved, unspecified and the 172.16.0.0/12 range (Docker's default bridge networks) are
  ALWAYS refused, whatever the flags.
* Docker-internal service names (db, admin, crm, ...) are single-label hostnames; any
  single-label host, "localhost", ".localhost" and ".internal" names are always refused.
* RFC1918 space (10/8, 192.168/16) and LAN host names (.local, .lan, .home, ...) are allowed
  ONLY when IOT_ALLOW_PRIVATE_HA=true (default false). Every address a name resolves to is
  checked, not just the first.
* No credentials in the URL, ports limited to 80/443/8123/8443, no query/fragment/path tricks.

Redirects are never followed (see HARestClient); the resolver is injectable for tests.
Residual risk: DNS can change between this check and the connect (rebinding).
"""

from __future__ import annotations

import ipaddress
import os
import socket
import unicodedata
from typing import Callable, Optional
from urllib.parse import urlsplit

from services.common.url_safety import UnsafeUrl, _BAD_URL_CHARS, _HOST_CHARS, _NUMERICISH, _ip_is_public

ALLOWED_PORTS = {80, 443, 8123, 8443}
_LAN_SUFFIXES = (".local", ".lan", ".home", ".home.arpa", ".localdomain", ".corp", ".intranet")
_ALWAYS_BLOCKED_SUFFIXES = (".localhost", ".internal")
_PRIVATE_OK = [ipaddress.ip_network(n) for n in ("10.0.0.0/8", "192.168.0.0/16", "fc00::/7")]
_DOCKER_NET = ipaddress.ip_network("172.16.0.0/12")


def _flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _default_resolver(host: str, port: int) -> list:
    return [i[4][0] for i in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)]


def _check_ip(ip, allow_private: bool) -> None:
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    if _ip_is_public(ip):
        return
    if allow_private and any(ip in net for net in _PRIVATE_OK if net.version == ip.version):
        return
    raise UnsafeUrl("address is not allowed")


def validate_ha_url(url: str, *, resolver: Optional[Callable] = None, allow_http: Optional[bool] = None,
                    allow_private: Optional[bool] = None) -> str:
    """Return the URL (without a trailing slash) or raise UnsafeUrl. Blocking (DNS)."""
    if allow_http is None:
        allow_http = _flag("IOT_ALLOW_HTTP")
    if allow_private is None:
        allow_private = _flag("IOT_ALLOW_PRIVATE_HA")
    raw = (url or "").strip()
    if not raw or _BAD_URL_CHARS.search(raw):
        raise UnsafeUrl("invalid URL")
    try:
        parts = urlsplit(raw)
        port = parts.port
    except ValueError:
        raise UnsafeUrl("invalid URL")
    scheme = parts.scheme.lower()
    if scheme not in ("https", "http") or (scheme == "http" and not allow_http):
        raise UnsafeUrl("only https URLs are allowed")
    if "@" in parts.netloc or parts.username is not None or parts.password is not None:
        raise UnsafeUrl("credentials in the URL are not allowed")
    if parts.query or parts.fragment:
        raise UnsafeUrl("query strings and fragments are not allowed")
    default_port = 443 if scheme == "https" else 80
    if port is not None and port not in ALLOWED_PORTS:
        raise UnsafeUrl("port is not allowed")
    host = parts.hostname
    if not host:
        raise UnsafeUrl("URL has no host")
    host = unicodedata.normalize("NFKC", host).rstrip(".").lower()
    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError:
        raise UnsafeUrl("invalid host name")
    if not host or not _HOST_CHARS.fullmatch(host):
        raise UnsafeUrl("invalid host name")

    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        _check_ip(literal, allow_private)
        if literal.version == 4 and literal in _DOCKER_NET:
            raise UnsafeUrl("address is not allowed")
        return raw.rstrip("/")
    if ":" in host:
        raise UnsafeUrl("invalid host name")
    labels = host.split(".")
    if labels[-1].isdigit() or labels[-1].startswith("0x") or _NUMERICISH.fullmatch(host):
        raise UnsafeUrl("numeric host names are not allowed")
    if len(labels) < 2 or host == "localhost" or host.endswith(_ALWAYS_BLOCKED_SUFFIXES):
        raise UnsafeUrl("internal host names are not allowed")
    if host.endswith(_LAN_SUFFIXES) and not allow_private:
        raise UnsafeUrl("LAN host names need IOT_ALLOW_PRIVATE_HA")
    try:
        addrs = (resolver or _default_resolver)(host, port or default_port)
    except (OSError, UnicodeError):
        raise UnsafeUrl("host name does not resolve")
    if not addrs:
        raise UnsafeUrl("host name does not resolve")
    for a in addrs:
        try:
            ip = ipaddress.ip_address(str(a).split("%")[0])
        except ValueError:
            raise UnsafeUrl("host resolved to an invalid address")
        _check_ip(ip, allow_private)
        if ip.version == 4 and ip in _DOCKER_NET:
            raise UnsafeUrl("address is not allowed")
    return raw.rstrip("/")


def safe_ha_url_or_none(url: str, **kw) -> Optional[str]:
    try:
        return validate_ha_url(url, **kw)
    except UnsafeUrl:
        return None
