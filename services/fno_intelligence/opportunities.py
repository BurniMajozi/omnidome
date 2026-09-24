"""Opportunity finder — pure logic (SPEC-opportunity-finder.md).

Company search grounded on OpenStreetMap (Overpass query building and result
parsing) and tender/RFQ extraction helpers (source-URL validation, tolerant
parsing of the LLM's JSON, South African date formats, de-duplication).
No network or DB here; see opportunity_routes.py for the flows.
"""

from __future__ import annotations

import calendar
import ipaddress
import json
import math
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from urllib.parse import urlsplit, urlunsplit

SAST = timezone(timedelta(hours=2), "SAST")

RADII_KM = (1, 2, 5, 10)
MAX_COMPANIES = 300

_AMENITY_HOSPITALITY = '["amenity"~"^(restaurant|cafe|fast_food|bar|pub)$"]'
_AMENITY_HEALTH = '["amenity"~"^(clinic|doctors|dentist|pharmacy|hospital|veterinary)$"]'
_AMENITY_EDUCATION = '["amenity"~"^(school|college|university|kindergarten)$"]'

# Category id -> label + Overpass tag filters (each filter is OR'd; all
# queries also require ["name"] so only identifiable businesses come back).
CATEGORIES: dict[str, dict[str, Any]] = {
    "all": {"label": "All businesses", "filters": [
        '["office"]', '["shop"]', _AMENITY_HOSPITALITY, _AMENITY_HEALTH, _AMENITY_EDUCATION,
        '["amenity"~"^(bank|fuel|car_rental)$"]', '["craft"]', '["industrial"]',
        '["tourism"~"^(hotel|guest_house|motel)$"]',
    ]},
    "offices": {"label": "Offices and professional services", "filters": ['["office"]']},
    "retail": {"label": "Retail and shops", "filters": ['["shop"]']},
    "hospitality": {"label": "Hospitality (food and stay)", "filters": [
        _AMENITY_HOSPITALITY, '["tourism"~"^(hotel|guest_house|motel|hostel)$"]',
    ]},
    "healthcare": {"label": "Healthcare", "filters": [_AMENITY_HEALTH, '["healthcare"]']},
    "education": {"label": "Education", "filters": [_AMENITY_EDUCATION]},
    "finance": {"label": "Finance and insurance", "filters": [
        '["amenity"~"^(bank|bureau_de_change)$"]', '["office"~"^(financial|insurance|accountant|tax_advisor)$"]',
    ]},
    "industrial": {"label": "Industrial and manufacturing", "filters": [
        '["industrial"]', '["craft"]', '["building"~"^(industrial|warehouse)$"]', '["man_made"="works"]',
    ]},
    "property": {"label": "Estates and property", "filters": [
        '["office"="estate_agent"]', '["building"="apartments"]', '["landuse"="residential"]["residential"]',
    ]},
}

_CATEGORY_KEYS = ("office", "shop", "amenity", "craft", "industrial", "tourism", "healthcare", "building", "man_made", "landuse")


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lng1 = map(math.radians, a)
    lat2, lng2 = map(math.radians, b)
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2
    return 2 * 6371.0088 * math.asin(math.sqrt(h))


def build_overpass_query(lat: float, lng: float, radius_km: int, category: str) -> str:
    if category not in CATEGORIES:
        raise ValueError(f"Unknown category: {category}")
    if radius_km not in RADII_KM:
        raise ValueError(f"Radius must be one of {RADII_KM} km")
    around = f"(around:{radius_km * 1000},{lat},{lng})"
    parts = "".join(f'nwr{around}["name"]{f};' for f in CATEGORIES[category]["filters"])
    return f"[out:json][timeout:50];({parts});out center tags {MAX_COMPANIES + 100};"


def _first(tags: dict, *keys: str) -> Optional[str]:
    for k in keys:
        v = (tags.get(k) or "").strip()
        if v:
            return v.split(";")[0].strip()
    return None


def _category_label(tags: dict) -> Optional[str]:
    for key in _CATEGORY_KEYS:
        value = (tags.get(key) or "").strip()
        if value:
            text = key if value == "yes" else value
            text = text.replace("_", " ")
            return text[:1].upper() + text[1:]
    return None


def parse_overpass_elements(elements: list[dict], center: tuple[float, float], limit: int = MAX_COMPANIES) -> list[dict]:
    """Overpass `out center tags` elements -> company dicts, nearest first."""
    seen: set[tuple[str, int]] = set()
    companies = []
    for el in elements:
        tags = el.get("tags") or {}
        name = (tags.get("name") or "").strip()
        if not name:
            continue
        lat = el.get("lat", (el.get("center") or {}).get("lat"))
        lng = el.get("lon", (el.get("center") or {}).get("lon"))
        if lat is None or lng is None:
            continue
        key = (el.get("type", "node"), int(el.get("id", 0)))
        if key in seen:
            continue
        seen.add(key)
        street = " ".join(p for p in (tags.get("addr:housenumber"), tags.get("addr:street")) if p)
        companies.append({
            "osm_type": key[0],
            "osm_id": key[1],
            "name": name,
            "category_label": _category_label(tags),
            "address_line": street or None,
            "suburb": _first(tags, "addr:suburb"),
            "city": _first(tags, "addr:city"),
            "postal_code": _first(tags, "addr:postcode"),
            "phone": _first(tags, "phone", "contact:phone", "contact:mobile"),
            "email": _first(tags, "email", "contact:email"),
            "website": _first(tags, "website", "contact:website", "url"),
            "lat": float(lat),
            "lng": float(lng),
            "distance_km": round(haversine_km(center, (float(lat), float(lng))), 2),
        })
    companies.sort(key=lambda c: (c["distance_km"], c["name"].lower()))
    return companies[:limit]


# ── source URLs ───────────────────────────────────────────────────────────

_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.\-]*:(?!\d)")
_BLOCKED_SUFFIXES = (".local", ".localhost", ".internal", ".lan", ".home.arpa")


def validate_source_url(url: str) -> str:
    """Normalise a user-supplied source URL; raise ValueError unless it's a
    public http(s) URL (no localhost, private IPs or internal service names)."""
    url = (url or "").strip()
    if not url:
        raise ValueError("Enter the page's URL")
    if "://" not in url and not _SCHEME_RE.match(url):
        url = "https://" + url
    parts = urlsplit(url)
    if parts.scheme.lower() not in ("http", "https"):
        raise ValueError("Use an http or https address")
    host = (parts.hostname or "").lower()
    if not host:
        raise ValueError("That address has no website in it")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip is not None:
        if not ip.is_global:
            raise ValueError("Use a public website, not a private or local address")
    elif host == "localhost" or "." not in host or host.endswith(_BLOCKED_SUFFIXES):
        raise ValueError("Use a public website, not a private or local address")
    netloc = host + (f":{parts.port}" if parts.port else "")
    return urlunsplit((parts.scheme.lower(), netloc, parts.path, parts.query, ""))


# ── tender extraction ─────────────────────────────────────────────────────

TENDER_FIELDS = ("title", "reference", "issuer", "description", "closing_text", "briefing_text",
                 "briefing_location", "detail_url", "contact")
_FIELD_ALIASES = {
    "closing_text": ("closing_text", "closing_date", "closing", "closes"),
    "briefing_text": ("briefing_text", "briefing_date", "briefing", "briefing_session"),
    "detail_url": ("detail_url", "url", "link"),
    "reference": ("reference", "reference_number", "tender_number", "bid_number"),
}
_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)


def build_tender_extraction_instruction(page_url: str) -> str:
    return (
        f"The content below is the procurement page {page_url}. List every tender, RFQ, RFP or bid "
        "opportunity it shows. Return ONLY a JSON array (no prose). Each item: "
        '{"title", "reference", "issuer", "description" (one sentence), "closing_text" (closing date/time exactly '
        'as written), "briefing_text" (briefing session date/time as written, or null), "briefing_location", '
        '"required_documents" (list of document names the bidder must submit), "document_links" (list of '
        '{"label", "url"} for downloadable tender documents), "detail_url" (link to the tender\'s own page), '
        '"contact"}. Use null for anything the page does not state. Never invent values. If there are no '
        "tenders, return []."
    )


def build_tender_detail_instruction(title: str) -> str:
    return (
        f'The content below is the detail page for the tender "{title}". Return ONLY a JSON object with: '
        '"closing_text", "briefing_text", "briefing_location", "required_documents" (list), "document_links" '
        '(list of {"label", "url"}), "contact", "description" (one sentence). Use null when not stated. '
        "Never invent values."
    )


def _extract_json(text: str) -> Any:
    text = (text or "").strip()
    fenced = _FENCE_RE.search(text)
    if fenced:
        text = fenced.group(1).strip()
    starts = [i for i in (text.find("["), text.find("{")) if i != -1]
    if not starts:
        raise ValueError("No JSON found in the model's answer")
    start = min(starts)
    end = max(text.rfind("]"), text.rfind("}"))
    if end < start:
        raise ValueError("No JSON found in the model's answer")
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError as exc:
        raise ValueError(f"The model's answer wasn't valid JSON: {exc}") from exc


def _clean_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, dict):
        value = ", ".join(str(v) for v in value.values() if v)
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text or None


def _clean_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        value = re.split(r"[;\n]", value)
    return [s for s in (_clean_str(v) for v in value) if s]


def _clean_links(value: Any) -> list[dict]:
    links = []
    for item in value or []:
        if isinstance(item, str):
            url, label = item.strip(), None
        elif isinstance(item, dict):
            url = (item.get("url") or item.get("href") or "").strip()
            label = _clean_str(item.get("label") or item.get("name"))
        else:
            continue
        if url:
            links.append({"label": label, "url": url})
    return links


def normalize_tender(item: dict) -> Optional[dict]:
    if not isinstance(item, dict):
        return None
    out: dict[str, Any] = {}
    for field in TENDER_FIELDS:
        aliases = _FIELD_ALIASES.get(field, (field,))
        out[field] = next((_clean_str(item.get(a)) for a in aliases if _clean_str(item.get(a))), None)
    out["required_documents"] = _clean_list(item.get("required_documents") or item.get("documents_required"))
    out["document_links"] = _clean_links(item.get("document_links") or item.get("documents"))
    return out


def parse_tender_json(text: str) -> list[dict]:
    """Tolerant parse of the LLM's answer: code fences and surrounding prose
    are ignored; accepts a list or {"tenders": [...]}; drops untitled items."""
    data = _extract_json(text)
    if isinstance(data, dict):
        data = data.get("tenders", [data] if data.get("title") else [])
    tenders = []
    for item in data if isinstance(data, list) else []:
        t = normalize_tender(item)
        if t and t["title"]:
            tenders.append(t)
    return tenders


def parse_tender_detail_json(text: str) -> dict:
    data = _extract_json(text)
    if isinstance(data, list):
        data = data[0] if data and isinstance(data[0], dict) else {}
    return normalize_tender({"title": "detail", **(data if isinstance(data, dict) else {})}) or {}


# ── dates ─────────────────────────────────────────────────────────────────

_MONTHS = {name.lower(): i for i, name in enumerate(calendar.month_name) if name}
_MONTHS.update({name.lower(): i for i, name in enumerate(calendar.month_abbr) if name})
_MONTHS["sept"] = 9
_DMY_WORDS = re.compile(r"(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]{3,9})\.?,?\s+(\d{4})")
_YMD = re.compile(r"(\d{4})[/\-.](\d{1,2})[/\-.](\d{1,2})")
_DMY = re.compile(r"(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})")
_TIME = re.compile(r"(?:at\s*)?(\d{1,2})\s*[:hH]\s*(\d{2})")


def parse_sa_datetime(text: Optional[str], *, end_of_day: bool = True) -> Optional[datetime]:
    """Parse the date formats SA tender pages use (day-first). Date-only values
    default to 23:59 so a tender isn't shown as closed before its closing day ends."""
    if not text:
        return None
    y = mo = d = None
    m = _DMY_WORDS.search(text)
    if m and m.group(2).lower() in _MONTHS:
        d, mo, y = int(m.group(1)), _MONTHS[m.group(2).lower()], int(m.group(3))
    else:
        m = _YMD.search(text)
        if m:
            y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        else:
            m = _DMY.search(text)
            if m:
                d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if m is None or y is None:
        return None
    t = _TIME.search(text, m.end())
    hour, minute = (int(t.group(1)), int(t.group(2))) if t else ((23, 59) if end_of_day else (0, 0))
    try:
        return datetime(y, mo, d, hour, minute, tzinfo=SAST)
    except ValueError:
        return None


def tender_dedupe_key(reference: Optional[str], title: Optional[str]) -> str:
    ref = re.sub(r"[^a-z0-9/\-]", "", (reference or "").lower())
    if ref:
        return f"ref:{ref}"
    return "title:" + re.sub(r"[^a-z0-9]+", " ", (title or "").lower()).strip()
