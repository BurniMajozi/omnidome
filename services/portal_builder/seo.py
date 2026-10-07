"""On-page SEO audit with real, deterministic scoring, plus an honest keyword-provider stub.

No number here is invented: every check is computed from the fetched page. Keyword volume/CPC comes
only from a configured third-party provider (SEO_PROVIDER_API_KEY); otherwise the caller is told so.
"""

from __future__ import annotations

import os
import re
from urllib.parse import urljoin, urlsplit

import httpx

from services.portal_builder.fetcher import Extracted

_POINTS = {"pass": 1.0, "warn": 0.5, "fail": 0.0}


def _check(cid: str, label: str, status: str, weight: int, detail: str) -> dict:
    return {"id": cid, "label": label, "status": status, "weight": weight, "detail": detail}


def audit(x: Extracted, final_url: str, keyword: str | None = None) -> dict:
    checks: list[dict] = []
    title = x.title.strip()
    tl = len(title)
    if not title:
        checks.append(_check("title", "Title tag", "fail", 10, "Missing <title>"))
    elif 30 <= tl <= 60:
        checks.append(_check("title", "Title tag", "pass", 10, f"{tl} characters"))
    else:
        checks.append(_check("title", "Title tag", "warn", 10, f"{tl} characters; aim for 30-60"))

    desc = (x.metas.get("description") or "").strip()
    dl = len(desc)
    if not desc:
        checks.append(_check("meta_description", "Meta description", "fail", 8, "Missing meta description"))
    elif 70 <= dl <= 160:
        checks.append(_check("meta_description", "Meta description", "pass", 8, f"{dl} characters"))
    else:
        checks.append(_check("meta_description", "Meta description", "warn", 8, f"{dl} characters; aim for 70-160"))

    h1s = [t for lvl, t in x.headings if lvl == 1]
    if len(h1s) == 1:
        checks.append(_check("h1", "Single H1", "pass", 8, h1s[0][:120]))
    elif not h1s:
        checks.append(_check("h1", "Single H1", "fail", 8, "No <h1> found"))
    else:
        checks.append(_check("h1", "Single H1", "warn", 8, f"{len(h1s)} <h1> elements; use exactly one"))

    levels = [lvl for lvl, _ in x.headings]
    skipped = any(b - a > 1 for a, b in zip(levels, levels[1:]))
    checks.append(_check("heading_structure", "Heading hierarchy",
                         "pass" if len(levels) > 1 and not skipped else "warn", 3,
                         "Headings nest without skipping levels" if len(levels) > 1 and not skipped
                         else ("Heading levels are skipped" if skipped else "Only one heading; add sub-headings")))

    if x.canonical:
        abs_c = urljoin(final_url, x.canonical)
        checks.append(_check("canonical", "Canonical link", "pass", 5, abs_c[:200]))
    else:
        checks.append(_check("canonical", "Canonical link", "warn", 5, "No rel=canonical link"))

    if x.images:
        missing = sum(1 for _, alt in x.images if alt is None or not alt.strip())
        total = len(x.images)
        ratio = 1 - missing / total
        st = "pass" if missing == 0 else ("warn" if ratio >= 0.6 else "fail")
        checks.append(_check("image_alt", "Image alt text", st, 6, f"{total - missing}/{total} images have alt text"))
    else:
        checks.append(_check("image_alt", "Image alt text", "pass", 0, "No images on the page"))

    words = x.words
    st = "pass" if words >= 300 else ("warn" if words >= 150 else "fail")
    checks.append(_check("word_count", "Content length", st, 8, f"{words} words; 300+ recommended"))

    host = (urlsplit(final_url).hostname or "").lower()
    internal = external = empty = 0
    for href, text in x.links:
        if href.startswith(("#", "javascript:", "mailto:", "tel:")) or not href:
            continue
        h = (urlsplit(urljoin(final_url, href)).hostname or "").lower()
        if h == host:
            internal += 1
        else:
            external += 1
        if not text.strip():
            empty += 1
    checks.append(_check("links", "Internal links", "pass" if internal >= 1 else "warn", 4,
                         f"{internal} internal, {external} external links"))
    checks.append(_check("link_text", "Descriptive link text", "pass" if empty == 0 else "warn", 3,
                         "All links have text" if empty == 0 else f"{empty} links have no anchor text"))

    checks.append(_check("https", "HTTPS", "pass" if final_url.lower().startswith("https://") else "fail", 6,
                         "Served over HTTPS" if final_url.lower().startswith("https://") else "Not served over HTTPS"))
    checks.append(_check("viewport", "Mobile viewport", "pass" if "viewport" in x.metas else "fail", 5,
                         "viewport meta present" if "viewport" in x.metas else "No viewport meta tag"))
    checks.append(_check("lang", "Language attribute", "pass" if x.lang else "warn", 2,
                         x.lang or "<html lang> missing"))
    robots = (x.metas.get("robots") or "").lower()
    checks.append(_check("indexable", "Indexable", "fail" if "noindex" in robots else "pass", 8,
                         "robots meta contains noindex" if "noindex" in robots else "No noindex directive"))
    og = [k for k in ("og:title", "og:description", "og:image") if x.metas.get(k)]
    checks.append(_check("open_graph", "Open Graph tags", "pass" if len(og) == 3 else ("warn" if og else "fail"), 3,
                         f"{len(og)}/3 of og:title, og:description, og:image"))
    checks.append(_check("structured_data", "Structured data (JSON-LD)", "pass" if x.jsonld else "warn", 3,
                         f"{x.jsonld} JSON-LD block(s)" if x.jsonld else "No JSON-LD found"))

    kw_stats = None
    if keyword and keyword.strip():
        kw = keyword.strip().lower()
        body_words = max(words, 1)
        occurrences = 0
        for p in x.paragraphs:
            occurrences += len(re.findall(re.escape(kw), p.lower()))
        kw_stats = {
            "keyword": kw, "in_title": kw in title.lower(), "in_h1": any(kw in t.lower() for t in h1s),
            "in_meta_description": kw in desc.lower(), "occurrences_in_text": occurrences,
            "density_pct": round(occurrences * len(kw.split()) / body_words * 100, 2),
        }
        hits = sum([kw_stats["in_title"], kw_stats["in_h1"], kw_stats["in_meta_description"]])
        checks.append(_check("keyword_placement", "Target keyword placement",
                             "pass" if hits == 3 else ("warn" if hits else "fail"), 6,
                             f"'{kw}' appears in {hits}/3 of title, H1, meta description"))

    scored = [c for c in checks if c["weight"] > 0]
    total = sum(c["weight"] for c in scored)
    earned = sum(c["weight"] * _POINTS[c["status"]] for c in scored)
    score = round(earned / total * 100) if total else 0
    grade = "A" if score >= 90 else "B" if score >= 75 else "C" if score >= 60 else "D" if score >= 40 else "F"
    return {
        "url": final_url, "score": score, "grade": grade, "checks": checks,
        "summary": {s: sum(1 for c in checks if c["status"] == s) for s in ("pass", "warn", "fail")},
        "stats": {"title_length": tl, "meta_description_length": dl, "word_count": words,
                  "images": len(x.images), "links_internal": internal, "links_external": external,
                  "headings": len(x.headings)},
        "keyword": kw_stats,
    }


# ── Keyword research (provider-gated) ──────────────────────────────────

def provider_configured() -> bool:
    return bool(os.getenv("SEO_PROVIDER_API_KEY", "").strip())


async def keyword_metrics(keywords: list[str], *, transport: httpx.AsyncBaseTransport | None = None) -> dict:
    """Search volume / CPC from a configured provider. Without SEO_PROVIDER_API_KEY nothing is returned.

    Provider: DataForSEO (SEO_PROVIDER=dataforseo, the only adapter); SEO_PROVIDER_API_KEY is "login:password".
    """
    if not provider_configured():
        return {"provider_configured": False, "keywords": [],
                "message": "Set SEO_PROVIDER_API_KEY to enable keyword volume and CPC data."}
    provider = os.getenv("SEO_PROVIDER", "dataforseo").strip().lower()
    if provider != "dataforseo":
        return {"provider_configured": True, "provider": provider, "keywords": [],
                "error": f"Unsupported SEO_PROVIDER '{provider}'"}
    login, _, password = os.getenv("SEO_PROVIDER_API_KEY", "").partition(":")
    body = [{"keywords": keywords[:100], "location_code": int(os.getenv("SEO_LOCATION_CODE", "2710")),
             "language_code": os.getenv("SEO_LANGUAGE_CODE", "en")}]
    try:
        async with httpx.AsyncClient(timeout=20, transport=transport) as c:
            r = await c.post("https://api.dataforseo.com/v3/keywords_data/google_ads/search_volume/live",
                             json=body, auth=(login, password))
            r.raise_for_status()
            data = r.json()
        rows = (((data.get("tasks") or [{}])[0].get("result")) or [])
    except Exception:  # noqa: BLE001
        return {"provider_configured": True, "provider": provider, "keywords": [],
                "error": "Keyword provider request failed"}
    return {"provider_configured": True, "provider": provider, "keywords": [
        {"keyword": r.get("keyword"), "search_volume": r.get("search_volume"), "cpc": r.get("cpc"),
         "competition": r.get("competition")} for r in rows]}
