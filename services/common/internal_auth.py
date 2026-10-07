"""Signed internal identity (AUTH_MODE=signed).

The web tier authenticates the caller (Supabase token -> admin DB) and signs the
resulting identity with a secret (INTERNAL_AUTH_SECRET) that only web and the
backends hold. Backends verify the signature instead of trusting raw
X-User-Id / X-Tenant-Id headers, so a request that reaches a backend port
directly cannot forge an identity.

Canonical string (UTF-8, fields joined by "\\n"):

    v1
    <METHOD upper-case>
    <decoded URL path, no query string>
    <unix timestamp, seconds>
    <user_id lower-case>
    <tenant_id lower-case>
    <roles: split on ",", trimmed, de-duplicated, sorted, joined with ",">
    <permissions: same normalisation>
    <modules: same normalisation>
    <org_id lower-case, empty when absent>

Signature = lower-case hex HMAC-SHA256(secret, canonical). Sent as
``x-identity-ts`` and ``x-identity-sig`` next to the existing identity headers
(x-user-id, x-tenant-id, x-roles, x-permissions, x-modules, x-org-id), which the
signature covers, so tampering with any of them (or replaying the signature on
another method/path, or outside the +-60s window) is rejected.

The TypeScript signer (apps/web/lib/internal-identity.ts) must produce identical
bytes; both test suites pin the same test vector.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import re
import time
from contextvars import ContextVar
from typing import Iterable, Mapping, Optional

logger = logging.getLogger("omnidome.auth")

VERSION = "v1"
TS_HEADER = "x-identity-ts"
SIG_HEADER = "x-identity-sig"
SKEW_SECONDS = 60
MIN_SECRET_LENGTH = 32

_TS_RE = re.compile(r"^\d{1,12}$")
_SIG_RE = re.compile(r"^[0-9a-f]{64}$")


class IdentityError(Exception):
    """Signature missing/invalid. `reason` is safe to log (never contains secrets)."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class IdentityConfigError(Exception):
    """AUTH_MODE=signed but INTERNAL_AUTH_SECRET is missing/too short (fail closed)."""


def get_secret() -> str:
    secret = (os.getenv("INTERNAL_AUTH_SECRET") or "").strip()
    if len(secret) < MIN_SECRET_LENGTH:
        raise IdentityConfigError(
            f"INTERNAL_AUTH_SECRET is not set or shorter than {MIN_SECRET_LENGTH} characters"
        )
    return secret


def _norm_list(value: Optional[str | Iterable[str]]) -> str:
    if value is None:
        return ""
    items = value.split(",") if isinstance(value, str) else list(value)
    return ",".join(sorted({str(i).strip() for i in items if str(i).strip()}))


def _norm_id(value: Optional[str]) -> str:
    return (value or "").strip().lower()


def canonical_string(
    *,
    method: str,
    path: str,
    ts: int | str,
    user_id: Optional[str],
    tenant_id: Optional[str],
    roles: Optional[str | Iterable[str]] = None,
    permissions: Optional[str | Iterable[str]] = None,
    modules: Optional[str | Iterable[str]] = None,
    org_id: Optional[str] = None,
) -> str:
    return "\n".join(
        [
            VERSION,
            method.strip().upper(),
            path,
            str(int(ts)),
            _norm_id(user_id),
            _norm_id(tenant_id),
            _norm_list(roles),
            _norm_list(permissions),
            _norm_list(modules),
            _norm_id(org_id),
        ]
    )


def compute_signature(secret: str, **fields) -> str:
    return hmac.new(secret.encode("utf-8"), canonical_string(**fields).encode("utf-8"), hashlib.sha256).hexdigest()


def _get(headers: Mapping[str, str], name: str) -> Optional[str]:
    # Starlette/httpx Headers are case-insensitive; plain dicts are not.
    if hasattr(headers, "get"):
        value = headers.get(name)
        if value is not None:
            return value
    for key, val in headers.items():
        if key.lower() == name:
            return val
    return None


def sign_headers(
    headers: Mapping[str, str],
    method: str,
    path: str,
    secret: Optional[str] = None,
    now: Optional[int] = None,
) -> dict[str, str]:
    """Return {x-identity-ts, x-identity-sig} for the identity headers in `headers`."""
    secret = secret or get_secret()
    ts = int(time.time()) if now is None else int(now)
    sig = compute_signature(
        secret,
        method=method,
        path=path,
        ts=ts,
        user_id=_get(headers, "x-user-id"),
        tenant_id=_get(headers, "x-tenant-id"),
        roles=_get(headers, "x-roles"),
        permissions=_get(headers, "x-permissions"),
        modules=_get(headers, "x-modules"),
        org_id=_get(headers, "x-org-id"),
    )
    return {TS_HEADER: str(ts), SIG_HEADER: sig}


def verify_request(
    headers: Mapping[str, str],
    method: str,
    path: str,
    secret: str,
    now: Optional[int] = None,
    skew: int = SKEW_SECONDS,
) -> None:
    """Raise IdentityError unless the identity headers carry a valid, fresh signature
    for exactly this method and path. Fails closed on an empty secret."""
    if not secret or len(secret) < MIN_SECRET_LENGTH:
        raise IdentityError("secret_unset")
    ts_raw = _get(headers, TS_HEADER)
    sig = (_get(headers, SIG_HEADER) or "").strip().lower()
    if not ts_raw or not sig:
        raise IdentityError("missing_signature")
    if not _TS_RE.match(ts_raw.strip()) or not _SIG_RE.match(sig):
        raise IdentityError("malformed_signature")
    ts = int(ts_raw.strip())
    current = int(time.time()) if now is None else int(now)
    if abs(current - ts) > skew:
        raise IdentityError("timestamp_out_of_window")
    expected = compute_signature(
        secret,
        method=method,
        path=path,
        ts=ts,
        user_id=_get(headers, "x-user-id"),
        tenant_id=_get(headers, "x-tenant-id"),
        roles=_get(headers, "x-roles"),
        permissions=_get(headers, "x-permissions"),
        modules=_get(headers, "x-modules"),
        org_id=_get(headers, "x-org-id"),
    )
    if not hmac.compare_digest(sig.encode("ascii"), expected.encode("ascii")):
        raise IdentityError("bad_signature")


# ---------------------------------------------------------------------------
# Startup banner + outbound signing for service-to-service calls
# ---------------------------------------------------------------------------

_banner_logged = False
_httpx_patched = False

# Verified caller identity of the request/job currently being served, set by a
# service from its verified AuthContext (never from client input). The httpx
# signing patch uses it ONLY to add x-roles / x-permissions to an outgoing call
# that already names the same tenant and user.
identity_context: ContextVar[Optional[dict]] = ContextVar("identity_context", default=None)


def set_identity_context(tenant_id, user_id, roles=(), permissions=()):
    """Bind the verified identity for this task; returns the reset token."""
    return identity_context.set({
        "tenant_id": _norm_id(str(tenant_id)) if tenant_id else "",
        "user_id": _norm_id(str(user_id)) if user_id else "",
        "roles": _norm_list(list(roles or [])),
        "permissions": _norm_list(list(permissions or [])),
    })


def _fill_roles_from_context(headers) -> None:
    """Add x-roles/x-permissions from identity_context when (and only when) the
    request already carries the same tenant+user and sets no x-roles itself."""
    ident = identity_context.get()
    if not ident or not ident.get("tenant_id") or not ident.get("user_id"):
        return
    if headers.get("x-roles"):
        return
    if _norm_id(headers.get("x-tenant-id")) != ident["tenant_id"]:
        return
    if _norm_id(headers.get("x-user-id")) != ident["user_id"]:
        return
    if ident["roles"]:
        headers["x-roles"] = ident["roles"]
    if ident["permissions"] and not headers.get("x-permissions"):
        headers["x-permissions"] = ident["permissions"]


def log_mode_banner(mode: str) -> None:
    global _banner_logged
    if _banner_logged:
        return
    _banner_logged = True
    if mode == "signed":
        try:
            get_secret()
            logger.info("AUTH_MODE=signed: internal identity signatures are required")
        except IdentityConfigError as exc:
            logger.critical(
                "AUTH_MODE=signed but %s. FAILING CLOSED: every authenticated route will answer 503 "
                "until INTERNAL_AUTH_SECRET (>=32 chars) is set.",
                exc,
            )
    elif mode in {"header", "dev"}:
        logger.warning(
            "SECURITY WARNING: AUTH_MODE=%s trusts client-supplied X-User-Id / X-Tenant-Id / X-Roles headers. "
            "Any caller that can reach this port can impersonate any user or tenant. "
            "Set AUTH_MODE=signed and INTERNAL_AUTH_SECRET for anything reachable beyond a trusted dev machine.",
            mode,
        )


def install_httpx_signing() -> None:
    """Sign identity headers on outgoing httpx calls made by this service.

    Backends call each other with X-Tenant-Id / X-User-Id headers (~50 call sites).
    Rather than touch every one, sign at the transport boundary: any request that
    carries identity headers and no signature gets x-identity-ts / x-identity-sig
    computed over its final method + path. No-op when INTERNAL_AUTH_SECRET is unset
    (header-mode peers ignore the extra headers, so this is safe in every mode).
    """
    global _httpx_patched
    if _httpx_patched:
        return
    try:
        import httpx
    except ImportError:  # pragma: no cover
        return
    _httpx_patched = True

    def _maybe_sign(request) -> None:
        h = request.headers
        if SIG_HEADER not in h:
            _fill_roles_from_context(h)
        if SIG_HEADER in h or not (h.get("x-tenant-id") or h.get("x-user-id")):
            return
        try:
            secret = get_secret()
        except IdentityConfigError:
            return
        for k, v in sign_headers(h, request.method, request.url.path, secret).items():
            request.headers[k] = v

    orig_async = httpx.AsyncClient.send
    orig_sync = httpx.Client.send

    async def async_send(self, request, *args, **kwargs):
        _maybe_sign(request)
        return await orig_async(self, request, *args, **kwargs)

    def sync_send(self, request, *args, **kwargs):
        _maybe_sign(request)
        return orig_sync(self, request, *args, **kwargs)

    httpx.AsyncClient.send = async_send  # type: ignore[method-assign]
    httpx.Client.send = sync_send  # type: ignore[method-assign]
