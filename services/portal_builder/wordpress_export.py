"""Deterministic Gutenberg export of the builder's supported plain-text blocks."""
from __future__ import annotations

import hashlib
import json
import re
from html import escape
from urllib.parse import urlsplit


class ExportError(ValueError):
    pass


def plain(value) -> str:
    return re.sub(r"<[^>]*>", "", str(value or "")).strip()


def paragraph(value) -> str:
    text = plain(value)
    return f'<!-- wp:paragraph --><p>{escape(text).replace(chr(10), "<br>")}</p><!-- /wp:paragraph -->' if text else ""


def heading(value, level=2) -> str:
    text = plain(value)
    return f'<!-- wp:heading {{"level":{level}}} --><h{level} class="wp-block-heading">{escape(text)}</h{level}><!-- /wp:heading -->' if text else ""


def absolute_url(value, *, image=False) -> str:
    url = str(value or "").strip()
    p = urlsplit(url)
    allowed = {"https", "http"} if image else {"https", "http", "mailto", "tel"}
    if (not url or re.search(r"[\s\\\x00-\x1f]", url) or p.scheme.lower() not in allowed
            or (p.scheme.lower() in {"http", "https"} and (not p.hostname or p.username or p.password))):
        raise ExportError("WordPress needs absolute image and CTA URLs. Set a working enquiry link in Page settings; the OmniDome enquiry form is not exported.")
    return escape(url, quote=True)


def image(value, alt="") -> str:
    if not value:
        return ""
    src = absolute_url(value, image=True)
    return f'<!-- wp:image --><figure class="wp-block-image"><img src="{src}" alt="{escape(plain(alt), quote=True)}"/></figure><!-- /wp:image -->'


def export_page(page) -> dict:
    blocks = (page.content or {}).get("blocks", [])
    if not isinstance(blocks, list) or not 1 <= len(blocks) <= 24:
        raise ExportError("Export needs between 1 and 24 supported page sections")
    sections = []
    for b in blocks:
        kind = b.get("type") if isinstance(b, dict) else None
        if kind not in {"hero", "gallery", "features", "pricing", "faq", "cta", "text"}:
            raise ExportError(f"Section '{kind}' cannot be exported to WordPress yet")
        out = heading(b.get("heading")) + paragraph(b.get("subheading")) + paragraph(b.get("body"))
        out += image(b.get("image"))
        if kind == "gallery":
            for item in b.get("images", [])[:12]:
                out += image(item.get("src"), item.get("alt"))
        for item in b.get("items", [])[:24]:
            out += heading(item.get("title"), 3) + paragraph(item.get("price")) + paragraph(item.get("body"))
        if b.get("cta_label"):
            url = absolute_url(b.get("cta_url"))
            out += '<!-- wp:buttons --><div class="wp-block-buttons"><!-- wp:button --><div class="wp-block-button">'
            out += f'<a class="wp-block-button__link wp-element-button" href="{url}">{escape(plain(b["cta_label"]))}</a>'
            out += '</div><!-- /wp:button --></div><!-- /wp:buttons -->'
        sections.append('<!-- wp:group {"layout":{"type":"constrained"}} --><div class="wp-block-group">' + out + '</div><!-- /wp:group -->')
    payload = {"title": plain(page.title), "slug": page.slug, "excerpt": plain(page.description),
               "content": "\n".join(sections), "export_version": 1}
    if len(payload["content"].encode()) > 500_000:
        raise ExportError("Exported page exceeds the size limit")
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    warnings = ["WordPress uses your site's theme and block styles. Review its preview before publishing.",
                "Images remain linked to their source URLs; the OmniDome enquiry form is not exported."]
    if page.seo_meta:
        warnings.append("SEO plugin fields are not synced in this release; configure them in WordPress.")
    if page.custom_css:
        warnings.append("Custom CSS is not exported.")
    return {**payload, "exported_hash": digest, "warnings": warnings}
