"""SSRF-safe page fetch + HTML extraction (used by the site importer and the SEO audit).

Every hop (initial URL and each redirect) is re-validated with services.common.url_safety.
Responses are capped in size and time, and only HTML content types are read.
Residual risk (documented in url_safety): DNS rebinding between validation and connect.
Nothing returned from here contains raw HTML: only extracted, plain-text fields.
"""

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any, Optional
from urllib.parse import urljoin, urlsplit

import httpx

from services.common.url_safety import UnsafeUrl, validate_public_url

MAX_BYTES = 1_500_000
TIMEOUT_S = 10.0
MAX_REDIRECTS = 4
USER_AGENT = "OmniDomePortalBot/1.0 (+site import; contact your administrator)"
_HTML_TYPES = ("text/html", "application/xhtml+xml")


class FetchError(Exception):
    def __init__(self, message: str, status_code: int = 422):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


@dataclass
class FetchResult:
    requested_url: str
    final_url: str
    status_code: int
    html: str
    content_type: str
    truncated: bool
    redirects: int
    elapsed_ms: int


# Injectable for tests.
_transport: Optional[httpx.AsyncBaseTransport] = None
_resolver = None


async def fetch_html(url: str, *, max_bytes: int = MAX_BYTES, timeout: float = TIMEOUT_S,
                     max_redirects: int = MAX_REDIRECTS) -> FetchResult:
    started = time.monotonic()
    deadline = started + timeout
    current = url
    redirects = 0
    async with httpx.AsyncClient(follow_redirects=False, timeout=timeout, transport=_transport,
                                 trust_env=False, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"}) as client:
        while True:
            try:
                await asyncio.to_thread(validate_public_url, current, resolver=_resolver)
            except UnsafeUrl as exc:
                raise FetchError(f"URL not allowed: {exc}", 422)
            if time.monotonic() > deadline:
                raise FetchError("Fetch timed out", 504)
            try:
                async with client.stream("GET", current) as resp:
                    if resp.status_code in (301, 302, 303, 307, 308):
                        loc = resp.headers.get("location")
                        if not loc:
                            raise FetchError("Redirect without a Location header", 502)
                        redirects += 1
                        if redirects > max_redirects:
                            raise FetchError("Too many redirects", 502)
                        current = urljoin(current, loc)
                        continue
                    ctype = (resp.headers.get("content-type") or "").split(";")[0].strip().lower()
                    if ctype not in _HTML_TYPES:
                        raise FetchError(f"Unsupported content type '{ctype or 'unknown'}'; HTML pages only", 415)
                    declared = resp.headers.get("content-length")
                    if declared and declared.isdigit() and int(declared) > max_bytes * 4:
                        raise FetchError("Page is too large", 413)
                    buf = bytearray()
                    truncated = False
                    async for chunk in resp.aiter_bytes():
                        buf.extend(chunk)
                        if len(buf) >= max_bytes:
                            truncated = True
                            del buf[max_bytes:]
                            break
                        if time.monotonic() > deadline:
                            raise FetchError("Fetch timed out", 504)
                    html = bytes(buf).decode(resp.charset_encoding or "utf-8", errors="replace")
                    return FetchResult(url, current, resp.status_code, html, ctype, truncated, redirects,
                                       int((time.monotonic() - started) * 1000))
            except FetchError:
                raise
            except httpx.TimeoutException:
                raise FetchError("Fetch timed out", 504)
            except (httpx.HTTPError, LookupError):
                raise FetchError("Could not fetch the page", 502)


# ── Extraction ─────────────────────────────────────────────────────────

_SKIP = frozenset({"script", "style", "noscript", "template", "svg", "head"})
_WS = re.compile(r"\s+")


def _clean(text: str, limit: int) -> str:
    return _WS.sub(" ", text).strip()[:limit]


@dataclass
class Extracted:
    title: str = ""
    lang: str = ""
    metas: dict = field(default_factory=dict)
    canonical: str = ""
    headings: list = field(default_factory=list)      # (level, text)
    paragraphs: list = field(default_factory=list)
    images: list = field(default_factory=list)        # (src, alt or None)
    links: list = field(default_factory=list)         # (href, text)
    words: int = 0
    jsonld: int = 0


class _Extractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.x = Extracted()
        self._skip = 0
        self._in_title = False
        self._block: Optional[str] = None
        self._buf: list[str] = []
        self._link: Optional[str] = None
        self._link_buf: list[str] = []
        self._in_body = False
        self._jsonld = False

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "html":
            self.x.lang = a.get("lang", "")[:20]
        elif tag == "title" and not self.x.title:
            self._in_title = True
            self._buf = []
        elif tag == "meta":
            key = (a.get("name") or a.get("property") or a.get("http-equiv") or "").lower()
            if key and "content" in a and key not in self.x.metas:
                self.x.metas[key] = a["content"][:1000]
        elif tag == "link" and "canonical" in a.get("rel", "").lower().split() and not self.x.canonical:
            self.x.canonical = a.get("href", "")[:2000]
        elif tag == "script" and a.get("type", "").lower() == "application/ld+json":
            self.x.jsonld += 1
        if tag == "body":
            self._in_body = True
        if tag in _SKIP and tag != "head":
            self._skip += 1
            return
        if self._skip:
            return
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "blockquote"):
            self._block, self._buf = tag, []
        elif tag == "img" and len(self.x.images) < 500:
            self.x.images.append((a.get("src") or a.get("data-src") or "", a.get("alt")))
        elif tag == "a" and "href" in a and len(self.x.links) < 1000:
            self._link, self._link_buf = a["href"], []

    def handle_endtag(self, tag):
        if tag == "title" and self._in_title:
            self._in_title = False
            self.x.title = _clean("".join(self._buf), 300)
            self._buf = []
        if tag in _SKIP and tag != "head":
            self._skip = max(0, self._skip - 1)
            return
        if self._skip:
            return
        if self._block == tag:
            text = _clean("".join(self._buf), 600)
            if text:
                if tag[0] == "h":
                    self.x.headings.append((int(tag[1]), text[:200]))
                elif len(self.x.paragraphs) < 120:
                    self.x.paragraphs.append(text)
            self._block, self._buf = None, []
        elif tag == "a" and self._link is not None:
            self.x.links.append((self._link[:2000], _clean("".join(self._link_buf), 200)))
            self._link = None

    def handle_data(self, data):
        if self._in_title:
            self._buf.append(data)
            return
        if self._skip:
            return
        if self._block:
            self._buf.append(data)
        if self._link is not None:
            self._link_buf.append(data)
        if self._in_body:
            self.x.words += len(data.split())


def extract(html: str) -> Extracted:
    p = _Extractor()
    try:
        p.feed(html)
        p.close()
    except Exception:  # noqa: BLE001 - tolerate hostile/malformed markup, keep what was parsed
        pass
    return p.x


def _abs_http(base: str, value: str) -> str:
    if not value or value.startswith("data:"):
        return ""
    absu = urljoin(base, value.strip())
    return absu if urlsplit(absu).scheme in ("http", "https") and len(absu) <= 2000 else ""


def to_structured(x: Extracted, base_url: str) -> dict:
    """Sanitised, structured page content: plain-text fields and absolute http(s) image URLs only."""
    desc = x.metas.get("description") or x.metas.get("og:description") or ""
    og_image = _abs_http(base_url, x.metas.get("og:image", ""))
    h1 = next((t for lvl, t in x.headings if lvl == 1), "")
    images, seen = [], set()
    for src, alt in x.images:
        u = _abs_http(base_url, src)
        if u and u not in seen:
            seen.add(u)
            images.append({"src": u, "alt": _clean(alt or "", 200)})
        if len(images) >= 30:
            break
    blocks: list[dict] = [{"type": "hero", "heading": h1 or x.title,
                           "subheading": _clean(desc, 300) or (x.paragraphs[0] if x.paragraphs else ""),
                           "image": og_image or (images[0]["src"] if images else "")}]
    current: Optional[dict] = None
    para_iter = iter(x.paragraphs)
    # Headings and paragraphs are collected in separate lists, so sections group paragraphs sequentially.
    for lvl, text in x.headings:
        if lvl == 1:
            continue
        current = {"type": "text", "heading": text, "body": ""}
        blocks.append(current)
    if len(blocks) > 1:
        per = max(1, len(x.paragraphs) // (len(blocks) - 1))
        for blk in blocks[1:]:
            blk["body"] = "\n\n".join([next(para_iter, "") for _ in range(per)]).strip()[:2000]
    elif x.paragraphs:
        blocks.append({"type": "text", "heading": "", "body": "\n\n".join(x.paragraphs[:12])[:4000]})
    if images:
        blocks.append({"type": "gallery", "images": images[:12]})
    return {
        "title": x.title, "description": _clean(desc, 500), "lang": x.lang, "og_image": og_image,
        "headings": [{"level": lvl, "text": t} for lvl, t in x.headings[:60]],
        "paragraphs": x.paragraphs[:60], "images": images, "blocks": blocks[:40],
        "stats": {"words": x.words, "links": len(x.links), "images": len(x.images)},
    }
