"""Deck document model (JSON, versioned schema) and its validation / normalisation / token resolution.

Pure functions only (no database): routes live in bi_deck.py. See docs/bi-studio-api.md for the schema.
"""

from __future__ import annotations

import json
import re
from typing import Annotated, Any, Iterator, Literal, Optional, Union

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from services.fno_intelligence import analytics_common as ac
from services.fno_intelligence import bi_tokens as tk
from services.fno_intelligence.bi_semantic import DATASETS, BiQueryError, QuerySpec, validate_spec_only

SCHEMA_VERSION = 1
MAX_SLIDES = 60
MAX_BLOCKS_PER_SLIDE = 12
MAX_BLOCKS = 300
MAX_QUERIES = 60
MAX_DOC_BYTES = 1_500_000
MAX_IMAGE_URLS = 20
LAYOUTS = ("title", "section", "content", "two_column", "chart_full", "chart_plus_text", "kpi_strip", "table",
           "comparison", "closing")
CHART_TYPES = ("column", "bar", "line", "area", "pie", "donut", "stacked_column", "combo", "scatter", "waterfall")
_ID = r"^[A-Za-z0-9_\-]{1,40}$"
_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")


class Frame(BaseModel):
    model_config = ConfigDict(extra="forbid")
    x: float = Field(..., ge=0, le=100)
    y: float = Field(..., ge=0, le=100)
    w: float = Field(..., gt=0, le=100)
    h: float = Field(..., gt=0, le=100)


class _Block(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(..., pattern=_ID)
    slot: Optional[str] = Field(None, max_length=24)  # layout slot hint: main|left|right|top|bottom|...
    frame: Optional[Frame] = None                      # manual position, percent of the slide


class TextItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field("", max_length=1200)
    bullet: bool = False
    level: int = Field(0, ge=0, le=2)
    bold: bool = False


class TextBlock(_Block):
    type: Literal["text"]
    role: Literal["body", "callout", "quote", "caption"] = "body"
    align: Literal["left", "center", "right"] = "left"
    items: list[TextItem] = Field(default_factory=list, max_length=30)


class KpiBlock(_Block):
    type: Literal["kpi"]
    label: str = Field("", max_length=80)
    value_ref: str = Field(..., max_length=120, description="token body, e.g. q1.outstanding")
    delta_ref: Optional[str] = Field(None, max_length=120, description="e.g. q1.outstanding.delta_pct")
    format: Optional[str] = Field(None, max_length=24)
    delta_format: Optional[str] = Field(None, max_length=24)
    caption: str = Field("", max_length=200)
    good_direction: Literal["up", "down"] = "up"


class SeriesMap(BaseModel):
    model_config = ConfigDict(extra="forbid")
    x: Optional[str] = Field(None, max_length=50)
    y: list[str] = Field(default_factory=list, max_length=12)
    y2: list[str] = Field(default_factory=list, max_length=6)     # combo: measures drawn as a line on the second axis
    series: Optional[str] = Field(None, max_length=50)             # split by this dimension


class Axis(BaseModel):
    model_config = ConfigDict(extra="forbid")
    x_title: str = Field("", max_length=80)
    y_title: str = Field("", max_length=80)
    y_format: Optional[Literal["currency_zar", "number", "percent", "duration"]] = None
    y_min: Optional[float] = None
    y_max: Optional[float] = None
    sort: Literal["data", "value_desc", "value_asc"] = "data"


class ChartBlock(_Block):
    type: Literal["chart"]
    chart_type: Literal["column", "bar", "line", "area", "pie", "donut", "stacked_column", "combo", "scatter", "waterfall"]
    title: str = Field("", max_length=200)
    query: Optional[QuerySpec] = None
    query_ref: Optional[str] = Field(None, pattern=_ID)
    series: SeriesMap = Field(default_factory=SeriesMap)
    axis: Axis = Field(default_factory=Axis)
    labels: bool = False
    legend: Literal["none", "top", "bottom", "right"] = "bottom"
    colors: list[str] = Field(default_factory=list, max_length=12)

    @field_validator("colors")
    @classmethod
    def _colors(cls, v):
        for c in v:
            if not _HEX.match(c):
                raise ValueError("chart colours must be #RRGGBB")
        return [c.upper() for c in v]


class TableColumn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field: str = Field(..., max_length=50)
    label: Optional[str] = Field(None, max_length=80)
    format: Optional[str] = Field(None, max_length=24)


class TableBlock(_Block):
    type: Literal["table"]
    title: str = Field("", max_length=200)
    query: Optional[QuerySpec] = None
    query_ref: Optional[str] = Field(None, pattern=_ID)
    columns: list[TableColumn] = Field(default_factory=list, max_length=12)
    max_rows: int = Field(15, ge=1, le=50)


class ImageSource(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["brand_logo", "url"]
    url: Optional[str] = Field(None, max_length=ac.MAX_URL_LEN)


class ImageBlock(_Block):
    type: Literal["image"]
    source: ImageSource
    alt: str = Field("", max_length=200)
    fit: Literal["contain", "cover"] = "contain"


class ShapeBlock(_Block):
    type: Literal["shape"]
    shape: Literal["divider", "rect", "accent_bar"] = "divider"
    color: str = Field("primary", max_length=12)  # a palette role or #RRGGBB

    @field_validator("color")
    @classmethod
    def _c(cls, v):
        if v not in ("primary", "secondary", "accent", "text", "background") and not _HEX.match(v):
            raise ValueError("colour must be a palette role (primary|secondary|accent|text|background) or #RRGGBB")
        return v


Block = Annotated[Union[TextBlock, KpiBlock, ChartBlock, TableBlock, ImageBlock, ShapeBlock], Field(discriminator="type")]


class Slide(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(..., pattern=_ID)
    layout: Literal["title", "section", "content", "two_column", "chart_full", "chart_plus_text", "kpi_strip", "table",
                    "comparison", "closing"] = "content"
    title: str = Field("", max_length=200)
    subtitle: Optional[str] = Field(None, max_length=300)
    blocks: list[Block] = Field(default_factory=list, max_length=MAX_BLOCKS_PER_SLIDE)
    notes: str = Field("", max_length=4000)


class Theme(BaseModel):
    model_config = ConfigDict(extra="forbid")
    palette: Optional[dict] = None   # partial overrides of the brand kit palette
    fonts: Optional[dict] = None
    footer_text: Optional[str] = Field(None, max_length=160)
    slide_numbers: Optional[bool] = None

    @field_validator("palette")
    @classmethod
    def _pal(cls, v):
        if v is None:
            return v
        allowed = {"primary", "secondary", "accent", "background", "text", "chart"}
        if set(v) - allowed:
            raise ValueError(f"palette keys must be among {sorted(allowed)}")
        for k, c in v.items():
            if k == "chart":
                if not isinstance(c, list) or len(c) > 12 or not all(isinstance(x, str) and _HEX.match(x) for x in c):
                    raise ValueError("palette.chart must be a list of up to 12 #RRGGBB colours")
            elif not isinstance(c, str) or not _HEX.match(c):
                raise ValueError(f"palette.{k} must be #RRGGBB")
        return v

    @field_validator("fonts")
    @classmethod
    def _fonts(cls, v):
        from services.fno_intelligence.bi_brand import SAFE_FONTS
        if v is None:
            return v
        for k, f in v.items():
            if k not in ("heading", "body") or f not in SAFE_FONTS:
                raise ValueError("fonts must be {heading?, body?} from the safe font list")
        return v


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    strict_numbers: bool = False   # true: saving text with a literal figure outside a token is rejected


class DeckDoc(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1] = 1
    title: str = Field("Untitled deck", max_length=200)
    brand_kit_id: Optional[str] = None
    theme: Theme = Field(default_factory=Theme)
    settings: Settings = Field(default_factory=Settings)
    queries: dict[str, QuerySpec] = Field(default_factory=dict)
    slides: list[Slide] = Field(default_factory=list, max_length=MAX_SLIDES)

    @field_validator("queries")
    @classmethod
    def _q(cls, v):
        if len(v) > MAX_QUERIES:
            raise ValueError(f"at most {MAX_QUERIES} named queries")
        for k in v:
            if not re.match(_ID, k):
                raise ValueError(f"invalid query alias {k!r}")
        return v


def starter_doc(title: str) -> dict:
    return DeckDoc(title=title, slides=[Slide(id="s1", layout="title", title=title)]).model_dump(
        by_alias=True, mode="json", exclude_none=True)


# ── helpers over a parsed doc ─────────────────────────────────────────────

def block_alias(b: Any) -> Optional[str]:
    if b.type not in ("chart", "table"):
        return None
    return b.query_ref or (b.id if b.query is not None else None)


def alias_specs(doc: DeckDoc) -> dict[str, QuerySpec]:
    specs = dict(doc.queries)
    for s in doc.slides:
        for b in s.blocks:
            if b.type in ("chart", "table") and b.query is not None:
                specs[b.id] = b.query
    return specs


def available_columns(spec: QuerySpec) -> tuple[list[str], list[str]]:
    """(x-able ids: time dim then dimensions, measure ids) for a spec."""
    xs: list[str] = []
    if spec.time and spec.time.grain:
        ds = DATASETS[spec.dataset]
        xs.append(spec.time.dimension or ds.default_time)
    xs += list(spec.dimensions)
    return xs, list(spec.measures)


def iter_texts(doc: DeckDoc) -> Iterator[tuple[str, str]]:
    yield "title", doc.title
    for si, s in enumerate(doc.slides):
        p = f"slides[{si}]"
        yield f"{p}.title", s.title
        if s.subtitle:
            yield f"{p}.subtitle", s.subtitle
        yield f"{p}.notes", s.notes
        for bi, b in enumerate(s.blocks):
            q = f"{p}.blocks[{bi}]"
            if b.type == "text":
                for ii, it in enumerate(b.items):
                    yield f"{q}.items[{ii}]", it.text
            elif b.type == "kpi":
                yield f"{q}.label", b.label
                yield f"{q}.caption", b.caption
            elif b.type in ("chart", "table"):
                yield f"{q}.title", b.title
                if b.type == "chart":
                    yield f"{q}.axis.x_title", b.axis.x_title
                    yield f"{q}.axis.y_title", b.axis.y_title
            elif b.type == "image":
                yield f"{q}.alt", b.alt


def _fail(msg: str) -> HTTPException:
    return HTTPException(422, msg)


def _format_validation(exc: ValidationError) -> str:
    errs = []
    for e in exc.errors()[:6]:
        loc = ".".join(str(x) for x in e.get("loc", ()))
        errs.append(f"{loc}: {e.get('msg', '')}")
    return "Invalid deck: " + "; ".join(errs)


def validate_deck_doc(raw: Any) -> tuple[DeckDoc, list[dict], dict[str, list[str]]]:
    """Parse + semantically validate. Returns (doc, warnings, {alias: measure ids}).
    Raises HTTPException(422) for anything that must not be stored."""
    if not isinstance(raw, dict):
        raise _fail("Invalid deck: document must be a JSON object")
    try:
        size = len(json.dumps(raw, separators=(",", ":")))
    except (TypeError, ValueError):
        raise _fail("Invalid deck: document is not JSON serialisable")
    if size > MAX_DOC_BYTES:
        raise _fail(f"Deck is too large ({size // 1024} KB; limit {MAX_DOC_BYTES // 1024} KB)")
    try:
        doc = DeckDoc.model_validate(raw)
    except ValidationError as exc:
        raise _fail(_format_validation(exc))

    # unique ids; global block cap
    slide_ids, block_ids = set(), set()
    total = 0
    for s in doc.slides:
        if s.id in slide_ids:
            raise _fail(f"Duplicate slide id {s.id!r}")
        slide_ids.add(s.id)
        for b in s.blocks:
            total += 1
            if b.id in block_ids or b.id in doc.queries:
                raise _fail(f"Duplicate block or query id {b.id!r}")
            block_ids.add(b.id)
    if total > MAX_BLOCKS:
        raise _fail(f"At most {MAX_BLOCKS} blocks per deck")

    specs = alias_specs(doc)
    if len(specs) > MAX_QUERIES:
        raise _fail(f"At most {MAX_QUERIES} queries per deck")
    for alias, spec in specs.items():
        try:
            validate_spec_only(spec)
        except BiQueryError as exc:
            raise _fail(f"Query {alias!r}: {exc.detail}")
    qm = {a: list(sp.measures) for a, sp in specs.items()}

    urls = 0
    for si, s in enumerate(doc.slides):
        for b in s.blocks:
            if b.type in ("chart", "table"):
                if b.query is not None and b.query_ref:
                    raise _fail(f"Block {b.id!r}: give either query or query_ref, not both")
                if b.query is None and (not b.query_ref or b.query_ref not in doc.queries):
                    raise _fail(f"Block {b.id!r}: needs an inline query or a query_ref naming one of deck.queries")
                spec = specs[block_alias(b)]
                xs, ms = available_columns(spec)
                if b.type == "chart":
                    sm = b.series
                    if not sm.y:
                        sm.y = [m for m in ms if m not in sm.y2]
                    if sm.x is None and b.chart_type != "scatter" and xs:
                        sm.x = xs[0]
                    for y in sm.y + sm.y2:
                        if y not in ms:
                            raise _fail(f"Block {b.id!r}: series.y {y!r} is not a measure of its query")
                    if sm.x is not None and sm.x not in xs and not (b.chart_type == "scatter" and sm.x in ms):
                        raise _fail(f"Block {b.id!r}: series.x {sm.x!r} is not a dimension of its query")
                    if sm.series is not None and (sm.series not in spec.dimensions or sm.series == sm.x):
                        raise _fail(f"Block {b.id!r}: series.series {sm.series!r} must be another dimension of its query")
                    if b.chart_type in ("pie", "donut", "waterfall") and len(sm.y) != 1:
                        raise _fail(f"Block {b.id!r}: {b.chart_type} charts take exactly one measure")
                    if b.chart_type == "scatter" and len(sm.y) + (1 if sm.x in ms else 0) < 2:
                        raise _fail(f"Block {b.id!r}: scatter charts need two measures")
                    if b.chart_type == "combo" and not sm.y2:
                        raise _fail(f"Block {b.id!r}: combo charts need series.y2 (the line measure)")
                else:
                    if not b.columns:
                        b.columns = [TableColumn(field=c) for c in xs + ms][:12]
                    for col in b.columns:
                        if col.field not in xs + ms:
                            raise _fail(f"Block {b.id!r}: table column {col.field!r} is not in its query")
                        if col.format and col.format not in tk.FORMATS:
                            raise _fail(f"Block {b.id!r}: unknown format {col.format!r}")
            elif b.type == "image" and b.source.kind == "url":
                urls += 1
                if not ac.plain_result_url(b.source.url) or not b.source.url.lower().startswith("https://"):
                    raise _fail(f"Block {b.id!r}: image url must be a plain https URL")
            elif b.type == "image" and b.source.url:
                raise _fail(f"Block {b.id!r}: brand_logo images take no url")
            elif b.type == "kpi":
                for ref, fmt in ((b.value_ref, b.format), (b.delta_ref, b.delta_format)):
                    if ref is None:
                        continue
                    if not re.match(r"^[A-Za-z0-9_\-]+(\.[A-Za-z0-9_\-]+){0,3}$", ref):
                        raise _fail(f"Block {b.id!r}: invalid reference {ref!r}")
                    bad = tk.validate_token_refs("{{" + ref + "}}", qm)
                    if bad:
                        raise _fail(f"Block {b.id!r}: {bad[0]['reason']}")
                    if fmt and fmt not in tk.FORMATS:
                        raise _fail(f"Block {b.id!r}: unknown format {fmt!r}")
    if urls > MAX_IMAGE_URLS:
        raise _fail(f"At most {MAX_IMAGE_URLS} image URLs per deck")

    warnings: list[dict] = []
    for where, text_ in iter_texts(doc):
        bad = tk.validate_token_refs(text_, qm)
        if bad:
            raise _fail(f"{where}: {bad[0]['reason']} in {bad[0]['token']}")
        for g in tk.find_ungrounded(text_):
            warnings.append({"where": where, "literal": g["literal"]})
    if doc.settings.strict_numbers and warnings:
        w = warnings[0]
        raise _fail(f"strict_numbers is on: {w['literal']!r} in {w['where']} must come from a {{{{token}}}}")
    return doc, warnings, qm


def dump_doc(doc: DeckDoc) -> dict:
    return doc.model_dump(by_alias=True, mode="json", exclude_none=True)


def image_urls(doc: DeckDoc) -> list[str]:
    return [b.source.url for s in doc.slides for b in s.blocks
            if b.type == "image" and b.source.kind == "url" and b.source.url]


# ── resolution (server side) ──────────────────────────────────────────────

def effective_theme(kit_config: Optional[dict], theme: Theme) -> dict:
    from services.fno_intelligence.bi_brand import DEFAULT_PALETTE, BrandConfig
    base = dict(kit_config) if kit_config else BrandConfig().model_dump()
    pal = {**DEFAULT_PALETTE, **(base.get("palette") or {})}
    pal.update(theme.palette or {})
    fonts = {**(base.get("fonts") or {"heading": "Calibri", "body": "Calibri"}), **(theme.fonts or {})}
    return {"palette": pal, "fonts": fonts,
            "footer_text": theme.footer_text if theme.footer_text is not None else base.get("footer_text", ""),
            "slide_numbers": theme.slide_numbers if theme.slide_numbers is not None else base.get("slide_numbers", True),
            "company_name": base.get("company_name", ""), "tagline": base.get("tagline", ""),
            "layout_prefs": base.get("layout_prefs") or {}}


def resolve_deck(doc: DeckDoc, results: dict[str, dict]) -> tuple[list[dict], list[dict]]:
    """Resolve every token into display strings. Returns (slides, unresolved)."""
    unresolved: list[dict] = []

    def rt(where: str, text_: str) -> str:
        out, bad = tk.resolve_text(text_, results)
        unresolved.extend({"where": where, **b} for b in bad)
        return out

    slides = []
    for si, s in enumerate(doc.slides):
        p = f"slides[{si}]"
        blocks = []
        for bi, b in enumerate(s.blocks):
            q = f"{p}.blocks[{bi}]"
            base = {"id": b.id, "type": b.type, "slot": b.slot, "frame": b.frame.model_dump() if b.frame else None}
            if b.type == "text":
                base.update(role=b.role, align=b.align, items=[
                    {"text": rt(f"{q}.items[{i}]", it.text), "bullet": it.bullet, "level": it.level, "bold": it.bold}
                    for i, it in enumerate(b.items)])
            elif b.type == "kpi":
                value, delta, direction = None, None, None
                try:
                    value = tk.resolve_ref(b.value_ref, results, b.format)
                except tk.TokenError as exc:
                    unresolved.append({"where": f"{q}.value_ref", "token": b.value_ref, "reason": str(exc)})
                if b.delta_ref:
                    try:
                        raw, default = tk.evaluate(b.delta_ref, results)
                        delta = tk.format_value(raw, b.delta_format or default)
                        direction = "flat" if isinstance(raw, (int, float)) and raw == 0 else \
                            ("up" if isinstance(raw, (int, float)) and raw > 0 else "down")
                    except tk.TokenError as exc:
                        unresolved.append({"where": f"{q}.delta_ref", "token": b.delta_ref, "reason": str(exc)})
                good = None
                if direction in ("up", "down"):
                    good = direction == b.good_direction
                base.update(label=rt(f"{q}.label", b.label), value=value if value is not None else "—", delta=delta,
                            delta_direction=direction, delta_is_good=good, caption=rt(f"{q}.caption", b.caption))
            elif b.type == "chart":
                base.update(chart_type=b.chart_type, title=rt(f"{q}.title", b.title), query_alias=block_alias(b),
                            series=b.series.model_dump(), axis={**b.axis.model_dump(),
                                                                "x_title": rt(f"{q}.axis.x_title", b.axis.x_title),
                                                                "y_title": rt(f"{q}.axis.y_title", b.axis.y_title)},
                            labels=b.labels, legend=b.legend, colors=b.colors)
            elif b.type == "table":
                base.update(title=rt(f"{q}.title", b.title), query_alias=block_alias(b),
                            columns=[c.model_dump(exclude_none=True) for c in b.columns], max_rows=b.max_rows)
            elif b.type == "image":
                base.update(source=b.source.model_dump(exclude_none=True), alt=rt(f"{q}.alt", b.alt), fit=b.fit)
            elif b.type == "shape":
                base.update(shape=b.shape, color=b.color)
            blocks.append(base)
        slides.append({"id": s.id, "layout": s.layout, "title": rt(f"{p}.title", s.title),
                       "subtitle": rt(f"{p}.subtitle", s.subtitle) if s.subtitle else None,
                       "notes": rt(f"{p}.notes", s.notes), "blocks": blocks})
    return slides, unresolved
