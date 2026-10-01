"""SSRF-safe validation of user-supplied URLs (shared by market watch and compliance).

`validate_public_url` is a pure/blocking check (DNS resolution is injectable for
tests). Callers that follow redirects MUST call it again for every hop.
Residual risk: DNS can change between this check and the socket connect
(rebinding); prefer a third-party fetcher (Firecrawl) where possible.
"""

from __future__ import annotations

import ipaddress
import os
import re
import socket
import unicodedata
from typing import Optional
from urllib.parse import urlsplit


class UnsafeUrl(ValueError):
    """The URL is not an acceptable public page."""


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


def validate_public_url(url: str, *, resolver=None, allow_http: Optional[bool] = None,
                        allow_http_env: str = "ALLOW_HTTP_FETCH") -> str:
    """Return the URL if it is a safe public page, else raise UnsafeUrl.

    https only (http when the `allow_http_env` variable is "true"), default port only, no userinfo, no
    localhost/single-label/internal names, no IP-literal tricks, and every address the
    name resolves to must be public (loopback/private/link-local/metadata/CGNAT refused).
    `resolver(host, port) -> [ip, ...]` is injectable for tests. Blocking (DNS).
    """
    if allow_http is None:
        allow_http = os.getenv(allow_http_env, "").strip().lower() == "true"
    raw = (url or "").strip()
    if not raw or _BAD_URL_CHARS.search(raw):
        raise UnsafeUrl("URL contains whitespace, control characters or backslashes")
    try:
        parts = urlsplit(raw)
        port = parts.port
    except ValueError:
        raise UnsafeUrl("Malformed URL")
    scheme = parts.scheme.lower()
    if scheme not in ("https", "http") or (scheme == "http" and not allow_http):
        raise UnsafeUrl("Only https URLs are allowed")
    if "@" in parts.netloc or parts.username is not None or parts.password is not None:
        raise UnsafeUrl("URLs with credentials are not allowed")
    default_port = 443 if scheme == "https" else 80
    if port is not None and port != default_port:
        raise UnsafeUrl("Non-standard ports are not allowed")
    host = parts.hostname
    if not host:
        raise UnsafeUrl("URL has no host")
    host = unicodedata.normalize("NFKC", host).rstrip(".").lower()
    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError:
        raise UnsafeUrl("Invalid host name")
    if not host or not _HOST_CHARS.fullmatch(host):
        raise UnsafeUrl("Invalid host name")

    literal = None
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        pass
    if literal is not None:
        if not _ip_is_public(literal):
            raise UnsafeUrl("Address is not a public address")
        return raw
    if ":" in host:
        raise UnsafeUrl("Invalid host name")
    labels = host.split(".")
    # decimal / octal / hex / short-form IPv4 ("2130706433", "0x7f.1", "127.1", "0177.0.0.1")
    if labels[-1].isdigit() or labels[-1].startswith("0x") or _NUMERICISH.fullmatch(host):
        raise UnsafeUrl("Numeric host names are not allowed")
    if len(labels) < 2 or host == "localhost" or host.endswith(_INTERNAL_SUFFIXES):
        raise UnsafeUrl("Internal host names are not allowed")
    try:
        addrs = (resolver or _default_resolver)(host, default_port)
    except (OSError, UnicodeError):
        raise UnsafeUrl("Host name does not resolve")
    if not addrs:
        raise UnsafeUrl("Host name does not resolve")
    for a in addrs:
        try:
            ip = ipaddress.ip_address(str(a).split("%")[0])
        except ValueError:
            raise UnsafeUrl("Host resolved to an invalid address")
        if not _ip_is_public(ip):
            raise UnsafeUrl("Host resolves to a non-public address")
    return raw
