"""BI Studio brand kits: per-tenant palette, fonts, voice and logo, validated hard.

Logo: PNG / JPEG / SVG, <= 512KB decoded, stored (sanitised) as a data URL. SVG is parsed and rebuilt from an
element/attribute allow-list (no scripts, no external references, no DOCTYPE/entities).
Website import is a SUGGESTION only: nothing is saved until the user confirms by creating/updating a kit.
"""

from __future__ import annotations

import base64
import binascii
import logging
import re
import uuid
import xml.etree.ElementTree as ET
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from services.common.auth import AuthContext, get_current_tenant_id
from services.fno_intelligence import analytics_common as ac
from services.fno_intelligence import database
from services.fno_intelligence.bi_models import BiBrandKit

logger = logging.getLogger("fno_intelligence.bi")
router = APIRouter(prefix="/brand-kits", tags=["BI Studio: brand kits"])

MAX_KITS = 10
MAX_LOGO_BYTES = 512 * 1024
SAFE_FONTS = {  # name -> export fallback
    "Calibri": "Arial", "Arial": "Arial", "Georgia": "Times New Roman", "Inter": "Arial", "Roboto": "Arial",
    "Montserrat": "Arial", "Helvetica": "Arial", "Times New Roman": "Times New Roman", "Verdana": "Arial",
    "Open Sans": "Arial", "Lato": "Arial", "Segoe UI": "Arial", "Cambria": "Georgia", "Tahoma": "Arial",
    "Trebuchet MS": "Arial", "Poppins": "Arial", "Source Sans Pro": "Arial",
}
LAYOUTS = ("title", "section", "content", "two_column", "chart_full", "chart_plus_text", "kpi_strip", "table",
           "comparison", "closing")
_HEX = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
_BAD_WORD = re.compile(r"[\x00-\x1f<>]")

DEFAULT_PALETTE = {"primary": "#0B5FFF", "secondary": "#1F2A44", "accent": "#F5A623", "background": "#FFFFFF",
                   "text": "#1B1F2A", "chart": ["#0B5FFF", "#F5A623", "#2BB673", "#E5484D", "#8E4EC6", "#12A594"]}


def norm_hex(v: Any, field: str = "colour") -> str:
    if not isinstance(v, str) or not _HEX.match(v.strip()):
        raise ValueError(f"{field}: expected a hex colour like #0B5FFF")
    h = v.strip().upper()
    if len(h) == 4:
        h = "#" + "".join(c * 2 for c in h[1:])
    return h


class Palette(BaseModel):
    model_config = ConfigDict(extra="forbid")
    primary: str = DEFAULT_PALETTE["primary"]
    secondary: str = DEFAULT_PALETTE["secondary"]
    accent: str = DEFAULT_PALETTE["accent"]
    background: str = DEFAULT_PALETTE["background"]
    text: str = DEFAULT_PALETTE["text"]
    chart: list[str] = Field(default_factory=lambda: list(DEFAULT_PALETTE["chart"]), min_length=6, max_length=6)

    @field_validator("primary", "secondary", "accent", "background", "text")
    @classmethod
    def _one(cls, v, info):
        return norm_hex(v, info.field_name)

    @field_validator("chart")
    @classmethod
    def _chart(cls, v):
        return [norm_hex(c, "chart colour") for c in v]


class Fonts(BaseModel):
    model_config = ConfigDict(extra="forbid")
    heading: str = "Calibri"
    body: str = "Calibri"

    @field_validator("heading", "body")
    @classmethod
    def _safe(cls, v):
        if v not in SAFE_FONTS:
            raise ValueError(f"font must be one of: {', '.join(sorted(SAFE_FONTS))}")
        return v


class Voice(BaseModel):
    model_config = ConfigDict(extra="forbid")
    formality: Literal["formal", "neutral", "casual"] = "neutral"
    jargon_level: Literal["low", "medium", "high"] = "medium"
    banned_words: list[str] = Field(default_factory=list, max_length=50)
    notes: str = Field("", max_length=500)

    @field_validator("banned_words")
    @classmethod
    def _words(cls, v):
        out = []
        for w in v:
            w = (w or "").strip()
            if not w or len(w) > 40 or _BAD_WORD.search(w):
                raise ValueError("banned words must be 1-40 characters without control characters or angle brackets")
            out.append(w)
        return out

    @field_validator("notes")
    @classmethod
    def _notes(cls, v):
        return ac.clean_untrusted(v, 500)


class LayoutPrefs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    default_layout: Literal["title", "section", "content", "two_column", "chart_full", "chart_plus_text", "kpi_strip",
                            "table", "comparison", "closing"] = "content"
    title_align: Literal["left", "center"] = "left"
    density: Literal["compact", "comfortable"] = "comfortable"
    show_logo: bool = True
    logo_position: Literal["top_left", "top_right", "bottom_left", "bottom_right"] = "top_right"


class BrandConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    company_name: str = Field("", max_length=120)
    tagline: str = Field("", max_length=160)
    palette: Palette = Field(default_factory=Palette)
    fonts: Fonts = Field(default_factory=Fonts)
    voice: Voice = Field(default_factory=Voice)
    footer_text: str = Field("", max_length=160)
    slide_numbers: bool = True
    layout_prefs: LayoutPrefs = Field(default_factory=LayoutPrefs)

    @field_validator("company_name", "tagline", "footer_text")
    @classmethod
    def _plain(cls, v):
        v = ac.norm_ws(v or "")
        if re.search(r"[<>\x00-\x1f]", v):
            raise ValueError("text must not contain angle brackets or control characters")
        return v


class BrandKitIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(..., min_length=1, max_length=120)
    company_name: Optional[str] = None
    tagline: Optional[str] = None
    palette: Optional[dict] = None
    fonts: Optional[dict] = None
    voice: Optional[dict] = None
    footer_text: Optional[str] = None
    slide_numbers: Optional[bool] = None
    layout_prefs: Optional[dict] = None
    logo_data_url: Optional[str] = Field(None, max_length=900_000)
    remove_logo: bool = False
    make_default: bool = False


class BrandKitPatch(BrandKitIn):
    name: Optional[str] = Field(None, min_length=1, max_length=120)  # type: ignore[assignment]


# ── logo validation / SVG sanitising (pure, unit tested) ──────────────────

_DATA_URL = re.compile(r"^data:(image/png|image/jpeg|image/svg\+xml);base64,([A-Za-z0-9+/=\s]+)$")
SVG_NS = "http://www.w3.org/2000/svg"
_SVG_ELEMENTS = {"svg", "g", "path", "rect", "circle", "ellipse", "line", "polyline", "polygon", "text", "tspan", "defs",
                 "lineargradient", "radialgradient", "stop", "clippath", "title", "desc", "mask", "symbol"}
_SVG_ATTRS = {"id", "class", "d", "x", "y", "x1", "x2", "y1", "y2", "cx", "cy", "r", "rx", "ry", "width", "height", "viewbox",
              "fill", "stroke", "stroke-width", "stroke-linecap", "stroke-linejoin", "stroke-miterlimit", "stroke-dasharray",
              "stroke-opacity", "fill-opacity", "opacity", "fill-rule", "clip-rule", "clip-path", "mask", "points", "transform",
              "offset", "stop-color", "stop-opacity", "gradientunits", "gradienttransform", "fx", "fy", "preserveaspectratio",
              "font-family", "font-size", "font-weight", "font-style", "text-anchor", "dx", "dy", "xmlns", "version",
              "style", "clippathunits", "maskunits", "spreadmethod", "letter-spacing"}
_CAMEL = {"viewbox": "viewBox", "gradientunits": "gradientUnits", "gradienttransform": "gradientTransform",
          "preserveaspectratio": "preserveAspectRatio", "clippathunits": "clipPathUnits", "maskunits": "maskUnits",
          "spreadmethod": "spreadMethod"}
_PAINT_REF = re.compile(r"^url\(#[A-Za-z0-9_\-:.]+\)$")
_DANGEROUS_STYLE = re.compile(r"url\s*\(\s*(?!#)|javascript|expression|@import|behavior|-moz-binding|<|&#", re.I)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower() if isinstance(tag, str) else ""


def sanitise_svg(raw: bytes) -> bytes:
    """Rebuild an SVG from an allow-list. Raises ValueError when it cannot be made safe."""
    try:
        txt = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError("SVG must be UTF-8 text")
    if re.search(r"<!\s*(doctype|entity)|<\?xml-stylesheet|<!\[CDATA\[", txt, re.I):
        raise ValueError("SVG with DOCTYPE, entities, stylesheets or CDATA is not allowed")
    try:
        root = ET.fromstring(txt)
    except ET.ParseError as exc:
        raise ValueError(f"SVG is not valid XML: {exc}")
    if _local(root.tag) != "svg":
        raise ValueError("Root element must be <svg>")

    def clean(el: ET.Element) -> Optional[ET.Element]:
        name = _local(el.tag)
        if name not in _SVG_ELEMENTS:
            return None
        out = ET.Element(f"{{{SVG_NS}}}{name if name not in ('lineargradient','radialgradient','clippath') else {'lineargradient':'linearGradient','radialgradient':'radialGradient','clippath':'clipPath'}[name]}")
        for k, v in el.attrib.items():
            key = _local(k)
            if key.startswith("on") or key not in _SVG_ATTRS or key == "xmlns":
                continue
            if "}" in k and not k.startswith(f"{{{SVG_NS}}}"):
                continue  # xlink:*, xml:* and other namespaces dropped
            val = str(v)
            if re.search(r"javascript:|data:|<|\x00", val, re.I):
                continue
            if key == "style" and _DANGEROUS_STYLE.search(val):
                continue
            if key in ("fill", "stroke", "clip-path", "mask") and "url(" in val.lower() and not _PAINT_REF.match(val.strip()):
                continue
            out.set(_CAMEL.get(key, key), val)
        if name in ("text", "tspan", "title", "desc"):
            out.text = (el.text or "")[:500]
        for ch in el:
            c = clean(ch)
            if c is not None:
                out.append(c)
            if name in ("text", "tspan") and ch.tail:
                if len(out):
                    out[-1].tail = (ch.tail or "")[:500]
        return out

    safe = clean(root)
    if safe is None:
        raise ValueError("SVG has no usable content")
    ET.register_namespace("", SVG_NS)
    data = ET.tostring(safe, encoding="utf-8")
    if re.search(rb"<script|javascript:|onload|onerror", data, re.I):
        raise ValueError("SVG still contains active content after sanitising")
    return data


def validate_logo(data_url: str) -> tuple[str, str]:
    """-> (sanitised data URL, mime). Raises ValueError (turned into HTTP 422 by callers)."""
    m = _DATA_URL.match((data_url or "").strip())
    if not m:
        raise ValueError("logo must be a base64 data URL of type image/png, image/jpeg or image/svg+xml")
    mime, b64 = m.group(1), re.sub(r"\s+", "", m.group(2))
    if len(b64) > MAX_LOGO_BYTES * 4 // 3 + 8:
        raise ValueError("logo is larger than 512KB")
    try:
        raw = base64.b64decode(b64, validate=True)
    except (binascii.Error, ValueError):
        raise ValueError("logo is not valid base64")
    if len(raw) > MAX_LOGO_BYTES:
        raise ValueError("logo is larger than 512KB")
    if not raw:
        raise ValueError("logo is empty")
    if mime == "image/png" and not raw.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("file content is not a PNG")
    if mime == "image/jpeg" and not raw.startswith(b"\xff\xd8\xff"):
        raise ValueError("file content is not a JPEG")
    if mime == "image/svg+xml":
        raw = sanitise_svg(raw)
        if len(raw) > MAX_LOGO_BYTES:
            raise ValueError("logo is larger than 512KB")
    return f"data:{mime};base64,{base64.b64encode(raw).decode()}", mime


def build_config(base: Optional[dict], body: BrandKitIn) -> dict:
    """Merge the request over the stored config and validate the whole thing."""
    cfg = dict(base or {})
    for key in ("company_name", "tagline", "footer_text", "slide_numbers"):
        v = getattr(body, key)
        if v is not None:
            cfg[key] = v
    for key in ("palette", "fonts", "voice", "layout_prefs"):
        v = getattr(body, key)
        if v is not None:
            if not isinstance(v, dict):
                raise ValueError(f"{key} must be an object")
            cfg[key] = {**(cfg.get(key) or {}), **v}
    return BrandConfig(**cfg).model_dump()


def _http422(exc: Exception) -> HTTPException:
    if hasattr(exc, "errors"):
        errs = [f"{'.'.join(str(p) for p in e.get('loc', ()))}: {e.get('msg', '')}" for e in exc.errors()][:6]  # type: ignore[attr-defined]
        return HTTPException(422, "; ".join(errs))
    return HTTPException(422, str(exc))


def kit_public(k: BiBrandKit, *, include_logo: bool = True) -> dict:
    out = {"id": str(k.id), "name": k.name, "is_default": bool(k.is_default), **(k.config or {}),
           "has_logo": bool(k.logo_data_url), "logo_mime": k.logo_mime,
           "created_by": str(k.created_by) if k.created_by else None, "updated_by": str(k.updated_by) if k.updated_by else None,
           "created_at": k.created_at.isoformat() if k.created_at else None,
           "updated_at": k.updated_at.isoformat() if k.updated_at else None}
    if include_logo:
        out["logo_data_url"] = k.logo_data_url
    return out


async def load_kit(db: AsyncSession, tenant_id: uuid.UUID, kit_id: Optional[uuid.UUID]) -> Optional[BiBrandKit]:
    if kit_id is None:
        return None
    k = await db.get(BiBrandKit, kit_id)
    return k if k is not None and k.tenant_id == tenant_id else None


async def default_kit(db: AsyncSession, tenant_id: uuid.UUID) -> Optional[BiBrandKit]:
    return (await db.execute(select(BiBrandKit).where(BiBrandKit.tenant_id == tenant_id, BiBrandKit.is_default.is_(True))
                             )).scalars().first()


# ── routes ────────────────────────────────────────────────────────────────

@router.get("/options")
async def options(_: AuthContext = Depends(ac.require_viewer)):
    return {"fonts": [{"name": n, "export_fallback": f} for n, f in sorted(SAFE_FONTS.items())], "layouts": list(LAYOUTS),
            "default_palette": DEFAULT_PALETTE, "max_logo_bytes": MAX_LOGO_BYTES,
            "logo_types": ["image/png", "image/jpeg", "image/svg+xml"], "max_kits": MAX_KITS}


@router.get("")
async def list_kits(tenant_id: uuid.UUID = Depends(get_current_tenant_id), _: AuthContext = Depends(ac.require_viewer),
                    db: AsyncSession = Depends(database.get_session)):
    rows = (await db.execute(select(BiBrandKit).where(BiBrandKit.tenant_id == tenant_id)
                             .order_by(BiBrandKit.is_default.desc(), BiBrandKit.name))).scalars().all()
    return {"items": [kit_public(k, include_logo=False) for k in rows]}


@router.get("/default")
async def get_default(tenant_id: uuid.UUID = Depends(get_current_tenant_id), _: AuthContext = Depends(ac.require_viewer),
                      db: AsyncSession = Depends(database.get_session)):
    k = await default_kit(db, tenant_id)
    return {"kit": kit_public(k) if k else None}


@router.get("/{kit_id}")
async def get_kit(kit_id: uuid.UUID, tenant_id: uuid.UUID = Depends(get_current_tenant_id),
                  _: AuthContext = Depends(ac.require_viewer), db: AsyncSession = Depends(database.get_session)):
    k = await load_kit(db, tenant_id, kit_id)
    if k is None:
        raise HTTPException(404, "Brand kit not found")
    return kit_public(k)


async def _make_default(db: AsyncSession, tenant_id: uuid.UUID, kit_id: uuid.UUID) -> None:
    await db.execute(update(BiBrandKit).where(BiBrandKit.tenant_id == tenant_id, BiBrandKit.id != kit_id)
                     .values(is_default=False))
    await db.execute(update(BiBrandKit).where(BiBrandKit.tenant_id == tenant_id, BiBrandKit.id == kit_id)
                     .values(is_default=True))


@router.post("", status_code=201)
async def create_kit(body: BrandKitIn, auth: AuthContext = Depends(ac.require_admin),
                     db: AsyncSession = Depends(database.get_session)):
    tenant_id = auth.tenant_id
    count = (await db.execute(select(func.count()).select_from(BiBrandKit).where(BiBrandKit.tenant_id == tenant_id))).scalar_one()
    if count >= MAX_KITS:
        raise HTTPException(409, f"At most {MAX_KITS} brand kits per tenant")
    try:
        cfg = build_config(None, body)
        logo, mime = validate_logo(body.logo_data_url) if body.logo_data_url else (None, None)
    except (ValueError, Exception) as exc:  # pydantic ValidationError is a ValueError subclass
        raise _http422(exc)
    kit = BiBrandKit(tenant_id=tenant_id, name=ac.norm_ws(body.name), config=cfg, logo_data_url=logo, logo_mime=mime,
                     is_default=False, created_by=auth.user_id, updated_by=auth.user_id)
    db.add(kit)
    try:
        await db.flush()
    except IntegrityError:
        raise HTTPException(409, "A brand kit with this name already exists")
    if body.make_default or count == 0:
        await _make_default(db, tenant_id, kit.id)
        await db.refresh(kit)
    return kit_public(kit)


@router.put("/{kit_id}")
async def update_kit(kit_id: uuid.UUID, body: BrandKitPatch, auth: AuthContext = Depends(ac.require_admin),
                     db: AsyncSession = Depends(database.get_session)):
    kit = await load_kit(db, auth.tenant_id, kit_id)
    if kit is None:
        raise HTTPException(404, "Brand kit not found")
    try:
        kit.config = build_config(kit.config, body)
        if body.logo_data_url:
            kit.logo_data_url, kit.logo_mime = validate_logo(body.logo_data_url)
        elif body.remove_logo:
            kit.logo_data_url, kit.logo_mime = None, None
    except Exception as exc:
        raise _http422(exc)
    if body.name:
        kit.name = ac.norm_ws(body.name)
    kit.updated_by = auth.user_id
    try:
        await db.flush()
    except IntegrityError:
        raise HTTPException(409, "A brand kit with this name already exists")
    if body.make_default:
        await _make_default(db, auth.tenant_id, kit.id)
    await db.refresh(kit)
    return kit_public(kit)


@router.post("/{kit_id}/default")
async def set_default(kit_id: uuid.UUID, auth: AuthContext = Depends(ac.require_admin),
                      db: AsyncSession = Depends(database.get_session)):
    kit = await load_kit(db, auth.tenant_id, kit_id)
    if kit is None:
        raise HTTPException(404, "Brand kit not found")
    await _make_default(db, auth.tenant_id, kit.id)
    await db.refresh(kit)
    return kit_public(kit, include_logo=False)


@router.delete("/{kit_id}", status_code=204)
async def delete_kit(kit_id: uuid.UUID, auth: AuthContext = Depends(ac.require_admin),
                     db: AsyncSession = Depends(database.get_session)):
    kit = await load_kit(db, auth.tenant_id, kit_id)
    if kit is None:
        raise HTTPException(404, "Brand kit not found")
    await db.delete(kit)


# ── suggest from website (Firecrawl, credit-ledger accounted) ─────────────

class SuggestIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str = Field(..., min_length=4, max_length=ac.MAX_URL_LEN)


BRAND_SCHEMA = {
    "type": "object",
    "properties": {
        "company_name": {"type": "string"}, "tagline": {"type": "string"},
        "primary_color": {"type": "string", "description": "dominant brand colour as hex"},
        "secondary_color": {"type": "string"}, "accent_color": {"type": "string"},
        "logo_url": {"type": "string"}, "font_names": {"type": "array", "items": {"type": "string"}},
    },
}
BRAND_PROMPT = ("Extract the company's brand identity from this website: company name, tagline/slogan, primary, "
                "secondary and accent brand colours as hex codes, the main logo image URL and the font family names used.")
_URLISH = re.compile(r"https?://\S+|www\.\S+", re.I)


def sanitise_suggestion(raw: Any, page_url: str) -> dict:
    """Validate what Firecrawl's extractor returned. Everything is a suggestion; invalid parts are dropped."""
    raw = raw if isinstance(raw, dict) else {}

    def text_(key: str, n: int) -> str:
        v = raw.get(key)
        if not isinstance(v, str):
            return ""
        v = ac.norm_ws(_URLISH.sub("", ac.clean_untrusted(v, n * 2)))
        v = re.sub(r"[<>\x00-\x1f]", "", v)
        return "" if ac.INJECTION_MARK in v else v[:n]

    def colour(key: str) -> Optional[str]:
        try:
            return norm_hex(raw.get(key), key)
        except ValueError:
            return None

    fonts = []
    for f in raw.get("font_names") or []:
        if isinstance(f, str):
            hit = next((n for n in SAFE_FONTS if n.lower() == f.strip().strip("'\"").lower()), None)
            if hit and hit not in fonts:
                fonts.append(hit)
    logo = ac.plain_result_url(raw.get("logo_url"))
    palette = {k: v for k, v in (("primary", colour("primary_color")), ("secondary", colour("secondary_color")),
                                 ("accent", colour("accent_color"))) if v}
    return {"company_name": text_("company_name", 120), "tagline": text_("tagline", 160), "palette": palette,
            "fonts": {"heading": fonts[0], "body": fonts[-1]} if fonts else None,
            "logo_url": logo, "logo_note": "The backend never downloads this image; upload it as a PNG/JPEG/SVG to use it." if logo else None,
            "source_url": page_url}


@router.post("/suggest-from-url")
async def suggest_from_url(body: SuggestIn, auth: AuthContext = Depends(ac.require_analyst)):
    url = await ac.check_public_url(body.url)
    metered = ac.MeteredFirecrawl(auth.tenant_id, "bi_brand")
    try:
        res = await metered.scrape(url, json_schema=BRAND_SCHEMA, json_prompt=BRAND_PROMPT)
    except ac.CreditCapExceeded:
        raise
    except HTTPException:
        raise
    except ac.FIRECRAWL_ERRORS as exc:
        raise ac.firecrawl_http_error(exc)
    except Exception as exc:  # fake/unknown failures from the scraper
        logger.warning("brand suggestion scrape failed: %s", exc)
        raise HTTPException(502, "The website could not be read")
    data = (res or {}).get("data", res) or {}
    suggestion = sanitise_suggestion(data.get("json") if isinstance(data, dict) else None, url)
    suggestion["credits_used"] = metered.spent
    suggestion["saved"] = False
    return suggestion
