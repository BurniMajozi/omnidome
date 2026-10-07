"""Input validation and output sanitisation for the Portal Builder.

Everything served on a public (unauthenticated) route passes through here: slugs are validated,
CSS is reduced to a safe subset, page content strings are stripped of active markup, and
JavaScript is never served at all.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re
from html import escape
from html.parser import HTMLParser
from typing import Any, Optional

SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,98}[a-z0-9])?$")
RESERVED_SLUGS = frozenset({
    "admin", "api", "app", "assets", "builder", "dashboard", "login", "logout", "signup", "register",
    "public", "shared", "static", "health", "docs", "openapi", "portal", "www", "mail", "ftp", "cdn",
    "auth", "oauth", "settings", "account", "billing", "internal", "svc", "robots", "robots-txt",
    "sitemap", "sitemap-xml", "favicon", "favicon-ico", "well-known", "new", "edit", "null", "undefined",
})
PAGE_TYPES = frozenset({"landing", "campaign", "product", "seo"})
MAX_CONTENT_BYTES = 512 * 1024
MAX_CSS_CHARS = 50_000

# Strict policy for the public JSON/HTML preview: no script, no network except images, no framing.
PUBLIC_CSP = (
    "default-src 'none'; img-src https: data:; style-src 'unsafe-inline'; font-src https:; "
    "form-action 'none'; base-uri 'none'; frame-ancestors 'none'"
)


class SlugError(ValueError):
    pass


def normalize_slug(raw: str) -> str:
    slug = (raw or "").strip().lower()
    if not SLUG_RE.fullmatch(slug):
        raise SlugError("Slug must be 1-100 chars of a-z, 0-9 and hyphens, starting and ending with a letter or digit")
    if slug in RESERVED_SLUGS:
        raise SlugError("That slug is reserved")
    return slug


# ── CSS ────────────────────────────────────────────────────────────────

_CSS_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_CSS_BAD = [
    re.compile(r"@import[^;{}]*;?", re.I),
    re.compile(r"@charset[^;{}]*;?", re.I),
    re.compile(r"url\s*\([^)]*\)?", re.I),
    re.compile(r"image-set\s*\([^)]*\)?", re.I),
    re.compile(r"expression\s*\([^)]*\)?", re.I),
    re.compile(r"(?:behaviou?r|-moz-binding)\s*:[^;}]*;?", re.I),
    re.compile(r"(?:javascript|vbscript|data)\s*:", re.I),
]


def sanitize_css(css: Optional[str]) -> str:
    """Reduce author CSS to declarations that cannot load resources or run script."""
    if not css:
        return ""
    out = css[:MAX_CSS_CHARS].replace("\\", "")  # escapes could hide keywords from the filters below
    out = _CSS_COMMENT.sub("", out)
    out = out.replace("<", "").replace(">", "")
    for _ in range(3):  # repeat so nested fragments cannot reassemble into a banned token
        before = out
        for pat in _CSS_BAD:
            out = pat.sub("", out)
        if out == before:
            break
    return out.strip()


# ── URLs ───────────────────────────────────────────────────────────────

_CTRL = re.compile(r"[\x00-\x20\x7f]+")
_URL_KEYS = frozenset({"src", "href", "url", "link", "image", "img", "background", "poster", "action", "cta_url", "logo"})


def sanitize_url(value: Any) -> str:
    """Allow http(s), mailto, tel, fragment and site-relative URLs only."""
    if not isinstance(value, str):
        return ""
    v = value.strip()
    probe = _CTRL.sub("", v).lower()
    if not probe:
        return ""
    if probe.startswith(("http://", "https://", "mailto:", "tel:")):
        return v
    if probe.startswith("#") or (probe.startswith("/") and not probe.startswith("//") and "\\" not in probe):
        return v
    return ""


# ── HTML fragments ─────────────────────────────────────────────────────

_ALLOWED_TAGS = frozenset({"a", "b", "strong", "i", "em", "u", "br", "p", "ul", "ol", "li", "span",
                           "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "small", "sup", "sub"})
_VOID = frozenset({"br"})
_DROP_CONTENT = frozenset({"script", "style", "iframe", "object", "embed", "svg", "math", "template",
                           "noscript", "form", "textarea", "select", "title", "head"})


class _Cleaner(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self._skip = 0
        self._open: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in _DROP_CONTENT:
            self._skip += 1
            return
        if self._skip or tag not in _ALLOWED_TAGS:
            return
        if tag == "a":
            href = sanitize_url(dict(attrs).get("href") or "")
            self.out.append(f'<a href="{escape(href, quote=True)}" rel="noopener noreferrer nofollow">' if href else "<a>")
        else:
            self.out.append(f"<{tag}>")
        if tag not in _VOID:
            self._open.append(tag)

    def handle_endtag(self, tag):
        if tag in _DROP_CONTENT:
            self._skip = max(0, self._skip - 1)
            return
        if self._skip or tag not in _ALLOWED_TAGS or tag in _VOID or tag not in self._open:
            return
        while self._open:
            t = self._open.pop()
            self.out.append(f"</{t}>")
            if t == tag:
                break

    def handle_data(self, data):
        if not self._skip:
            self.out.append(escape(data, quote=False))

    def close(self):
        super().close()
        while self._open:
            self.out.append(f"</{self._open.pop()}>")


def sanitize_html(value: str) -> str:
    """Strip a fragment down to a small tag allow-list with no attributes except a safe href."""
    if "<" not in value:
        return value  # no markup possible; keep literal text (&, quotes) untouched
    cleaner = _Cleaner()
    try:
        cleaner.feed(value)
        cleaner.close()
    except Exception:  # noqa: BLE001 - malformed markup: fall back to escaped text
        return escape(re.sub(r"<[^>]*>", "", value), quote=False)
    return "".join(cleaner.out)


def sanitize_content(obj: Any, *, _depth: int = 0, _key: str = "") -> Any:
    """Recursively sanitise a page-builder JSON tree (strings only; structure is preserved)."""
    if _depth > 14:
        return None
    if isinstance(obj, str):
        if _key.lower() in _URL_KEYS:
            return sanitize_url(obj)
        return sanitize_html(obj)
    if isinstance(obj, dict):
        return {str(k)[:100]: sanitize_content(v, _depth=_depth + 1, _key=str(k)) for k, v in list(obj.items())[:200]}
    if isinstance(obj, list):
        return [sanitize_content(v, _depth=_depth + 1, _key=_key) for v in obj[:500]]
    if isinstance(obj, (int, float, bool)) or obj is None:
        return obj
    return str(obj)


# ── Tokens / hashing / client identity ─────────────────────────────────

def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _ip_salt() -> bytes:
    return (os.getenv("PORTAL_IP_SALT") or os.getenv("INTERNAL_AUTH_SECRET") or "portal-builder").encode()


def hash_ip(ip: str) -> str:
    return hmac.new(_ip_salt(), (ip or "unknown").encode(), hashlib.sha256).hexdigest()


def client_ip(request) -> str:
    """Client address. X-Forwarded-For is honoured only when PORTAL_TRUST_PROXY=true, and then only the
    right-most entry (the one appended by our own proxy; left entries are client-controlled)."""
    if os.getenv("PORTAL_TRUST_PROXY", "false").strip().lower() in {"1", "true", "yes", "on"}:
        xff = (request.headers.get("x-forwarded-for") or "").split(",")
        if xff and xff[-1].strip():
            return xff[-1].strip()
    return request.client.host if request.client else "unknown"


EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)+$")
