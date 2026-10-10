"""Artifact registry cards: platform-made work product (BI decks, brand kits, research runs, competitor and
campaign analyses) so agents can answer "do we have X?" and hand back a link instead of regenerating it.

Rules:
  * Every card carries `source_ref.deep_link`, a REAL in-app route (see `app_link`): the dashboard page reads
    `section` + `sub` and Deck Studio reads `deck`.
  * Decks/kits/research live in BI Studio (module "analytics"): tenant-visible; the orchestrator additionally
    checks the caller's panel access (modules) before offering them.
  * Structured fields (kind, status, version, owner, ...) live in the frontmatter so `artifacts.find` can parse
    them from a search hit without a second lookup.
  * Brand kits: names and flags only. No logo data, no colours/fonts beyond the kit name.
  * Builders are pure and deterministic (same row, same markdown), so rebuilds never re-embed.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Awaitable, Callable, Optional
from urllib.parse import urlencode

from services.tenant_memory.knowledge.cards import sources as S
from services.tenant_memory.knowledge.cards import sources_ext as SX
from services.tenant_memory.knowledge.cards.base import Card, fmt_dt, frontmatter
from services.tenant_memory.knowledge.cards.builders_ext import jsonish
from services.tenant_memory.knowledge.kdata import IMPORTANCE
from services.tenant_memory.knowledge.textutil import clip, scrub

ARTIFACT_KINDS = ("bi_deck", "bi_brand_kit", "research", "competitor", "campaign_analysis", "portal_page")

# kind -> (dashboard section, sub tab, query param carrying the id)
_ROUTES: dict[str, tuple[str, str, Optional[str]]] = {
    "bi_deck": ("analytics", "presentations", "deck"),
    "bi_brand_kit": ("analytics", "presentations", "brand_kit"),
    "research": ("analytics", "research", "research"),
    "competitor": ("analytics", "competitors", "competitor"),
    "campaign_analysis": ("analytics", "campaign-analysis", "analysis"),
    "portal_page": ("portal", "website", "page"),
}

_UUIDISH = re.compile(r"^[0-9a-fA-F-]{8,64}$")


def app_link(kind: str, ident: str) -> str:
    """Same-origin app path that opens the artifact: /dashboard?section=analytics&sub=presentations&deck=<id>."""
    section, sub, param = _ROUTES[kind]
    q = {"section": section, "sub": sub}
    if param and _UUIDISH.match(str(ident)):
        q[param] = str(ident)
    return "/dashboard?" + urlencode(q)


def _s(v: Any, n: int = 200) -> str:
    return clip(scrub("" if v is None else str(v)), n)


# ── decks ───────────────────────────────────────────────────────────────────

def _deck_datasets(doc: dict) -> list[str]:
    found: set[str] = set()
    for spec in (doc.get("queries") or {}).values():
        if isinstance(spec, dict) and spec.get("dataset"):
            found.add(str(spec["dataset"]))
    for slide in doc.get("slides") or []:
        for b in (slide.get("blocks") or []) if isinstance(slide, dict) else []:
            q = b.get("query") if isinstance(b, dict) else None
            if isinstance(q, dict) and q.get("dataset"):
                found.add(str(q["dataset"]))
    return sorted(found)


def deck_card(row: dict, ctx: Optional[dict], as_of: Optional[datetime]) -> Card:
    ctx = ctx or {}
    did = str(row["id"])
    doc = jsonish(row.get("doc")) or {}
    slides = [s for s in (doc.get("slides") or []) if isinstance(s, dict)]
    status = str(row.get("status") or "draft")
    version = int(row.get("version") or 1)
    owner_id = str(row["created_by"]) if row.get("created_by") else None
    owner = (ctx.get("users") or {}).get(owner_id or "") or ""
    kit_id = str(row["brand_kit_id"]) if row.get("brand_kit_id") else ""
    kit = (ctx.get("kits") or {}).get(kit_id) or ""
    datasets = _deck_datasets(doc)
    title = _s(row.get("title"), 160) or "Untitled deck"
    link = app_link("bi_deck", did)
    lines = [f"# Deck: {title}", "",
             "- Kind: BI Studio presentation deck (Deck Studio)",
             f"- Status: {status} (version {version})",
             f"- Slides: {len(slides)}",
             f"- Brand kit: {_s(kit, 100) or 'none'}",
             f"- Owner: {_s(owner, 100) or owner_id or 'unknown'}",
             f"- Created: {fmt_dt(row.get('created_at')) or 'unknown'}; last updated: {fmt_dt(row.get('updated_at')) or 'unknown'}"]
    if status == "published":
        lines.append(f"- Published: {fmt_dt(row.get('published_at')) or 'yes'}")
    lines.append(f"- Open in app: {link}")
    if datasets:
        lines += ["", "## Datasets used", ", ".join(datasets)]
    if slides:
        lines += ["", "## Slides"]
        for i, s in enumerate(slides[:40], 1):
            lines.append(f"{i}. {_s(s.get('title'), 120) or '(untitled)'} - layout {_s(s.get('layout'), 24) or 'content'}")
        notes = [(i, _s(s.get("notes"), 160)) for i, s in enumerate(slides[:40], 1) if str(s.get("notes") or "").strip()]
        if notes:
            lines += ["", "## Speaker notes (excerpts)"] + [f"- Slide {i}: {n}" for i, n in notes[:12]]
    tags = ["deck", "presentation", "bi-studio", "artifact", status]
    extra = {"kind": "bi_deck", "deck_id": did, "status": status, "version": version, "slide_count": len(slides),
             "owner": owner or owner_id, "updated": fmt_dt(row.get("updated_at")), "brand_kit": kit}
    md = frontmatter("bi_deck", did, "analytics", as_of, tags, extra) + "\n".join(lines) + "\n"
    ref = {"deep_link": link, "kind": "bi_deck", "status": status, "version": version, "slide_count": len(slides),
           "owner_id": owner_id, "owner": owner or None, "brand_kit": kit or None, "datasets": datasets}
    card = Card("bi_deck", did, "analytics", f"Deck: {title}", md, as_of, tags, IMPORTANCE["high"], ref)
    card.owner_id = owner_id            # recorded for provenance; visibility stays tenant (module access checked by the caller)
    return card


def brand_kit_card(row: dict, ctx: Optional[dict], as_of: Optional[datetime]) -> Card:
    """Names and flags only. Logo data, palette and fonts are deliberately not read."""
    kid = str(row["id"])
    name = _s(row.get("name"), 120) or "Brand kit"
    link = app_link("bi_brand_kit", kid)
    lines = [f"# Brand kit: {name}", "", "- Kind: BI Studio brand kit (used by Deck Studio)",
             f"- Default kit: {'yes' if row.get('is_default') else 'no'}",
             f"- Last updated: {fmt_dt(row.get('updated_at')) or 'unknown'}", f"- Open in app: {link}"]
    tags = ["brand-kit", "bi-studio", "artifact"]
    extra = {"kind": "bi_brand_kit", "status": "default" if row.get("is_default") else "active", "updated": fmt_dt(row.get("updated_at"))}
    md = frontmatter("bi_brand_kit", kid, "analytics", as_of, tags, extra) + "\n".join(lines) + "\n"
    return Card("bi_brand_kit", kid, "analytics", f"Brand kit: {name}", md, as_of, tags, IMPORTANCE["normal"],
                {"deep_link": link, "kind": "bi_brand_kit", "is_default": bool(row.get("is_default"))})


# ── enrichment (owner + brand-kit names) ────────────────────────────────────

async def _deck_enrich(session, tenant: str, rows: list[dict]) -> dict:
    ctx: dict[str, dict] = {"users": {}, "kits": {}}
    uids = sorted({str(r["created_by"]) for r in rows if r.get("created_by")})
    kids = sorted({str(r["brand_kit_id"]) for r in rows if r.get("brand_kit_id")})
    try:
        if uids:
            res = await S._rows(session, "SELECT id::text AS id, full_name FROM users WHERE tenant_id = CAST(:t AS uuid) AND id::text = ANY(:ids)",
                                {"t": tenant, "ids": uids})
            ctx["users"] = {r["id"]: r.get("full_name") for r in res if r.get("full_name")}
    except Exception:  # noqa: BLE001 - owner name is a nicety; the id is still recorded
        pass
    try:
        if kids:
            res = await S._rows(session, "SELECT id::text AS id, name FROM analytics_brand_kits WHERE tenant_id = CAST(:t AS uuid) AND id::text = ANY(:ids)",
                                {"t": tenant, "ids": kids})
            ctx["kits"] = {r["id"]: r.get("name") for r in res}
    except Exception:  # noqa: BLE001
        pass
    return ctx


_DECK_SELECT = "t.title, t.status, t.version, t.doc, t.brand_kit_id::text AS brand_kit_id, t.created_by::text AS created_by, t.published_at, t.created_at, t.updated_at"
_KIT_SELECT = "t.name, t.is_default, t.updated_at"

ARTIFACT_SOURCES = [
    SX.keyset_source("bi_decks", "analytics", "bi_deck", probe="analytics_decks", frm="analytics_decks t", select=_DECK_SELECT,
                     ts="COALESCE(t.updated_at, t.created_at)", enrich=_deck_enrich, build=lambda r, c, a: deck_card(r, c, a)),
    SX.keyset_source("bi_brand_kits", "analytics", "bi_brand_kit", probe="analytics_brand_kits", frm="analytics_brand_kits t", select=_KIT_SELECT,
                     ts="COALESCE(t.updated_at, t.created_at)", build=lambda r, c, a: brand_kit_card(r, c, a)),
]


# ── single-row loaders (write-through endpoint) ─────────────────────────────
# Each returns the Card for ONE row, or None when the row is gone / not indexable (-> tombstone). The memory
# service re-reads the row itself, so a caller can only ask "refresh this id", never inject card content.

Loader = Callable[[Any, str, str], Awaitable[Optional[Card]]]


async def _one_generic(session, tenant: str, table: str, select: str, sid: str, extra_where: str = "") -> Optional[dict]:
    if not await SX.table_exists(session, table):
        return None
    rows = await S._rows(session, f"SELECT {select} FROM {table} t WHERE t.tenant_id = CAST(:t AS uuid) AND t.id = CAST(:sid AS uuid){extra_where}",
                         {"t": tenant, "sid": sid})
    return rows[0] if rows else None


async def _load_deck(session, tenant: str, sid: str) -> Optional[Card]:
    r = await _one_generic(session, tenant, "analytics_decks", f"t.id::text AS id, {_DECK_SELECT}, COALESCE(t.updated_at, t.created_at) AS ts", sid)
    return deck_card(r, await _deck_enrich(session, tenant, [r]), S._utc(r["ts"])) if r else None


async def _load_kit(session, tenant: str, sid: str) -> Optional[Card]:
    r = await _one_generic(session, tenant, "analytics_brand_kits", f"t.id::text AS id, {_KIT_SELECT}, COALESCE(t.updated_at, t.created_at) AS ts", sid)
    return brand_kit_card(r, None, S._utc(r["ts"])) if r else None


async def _load_research(session, tenant: str, sid: str) -> Optional[Card]:
    from services.tenant_memory.knowledge.cards import builders as B
    r = await _one_generic(session, tenant, "analytics_research_runs",
                           "t.id::text AS id, t.question, t.report, t.sources, COALESCE(t.finished_at, t.created_at) AS ts", sid, " AND t.status = 'done'")
    return B.research_card(r, S._utc(r["ts"])) if r else None


async def _load_campaign_analysis(session, tenant: str, sid: str) -> Optional[Card]:
    from services.tenant_memory.knowledge.cards import builders as B
    r = await _one_generic(session, tenant, "analytics_campaign_analyses",
                           "t.id::text AS id, t.name, t.subject, t.own_campaign_id::text AS own_campaign_id, t.competitor_id::text AS competitor_id, "
                           "t.aggregate, t.limitations, t.item_count, t.last_run_at, COALESCE(t.last_run_at, t.created_at) AS ts", sid, " AND t.aggregate IS NOT NULL")
    return B.campaign_analysis_card(r, S._utc(r["ts"])) if r else None


async def _load_competitor(session, tenant: str, sid: str) -> Optional[Card]:
    from services.tenant_memory.knowledge.cards import builders as B
    r = await _one_generic(session, tenant, "analytics_competitors",
                           "t.id::text AS id, t.name, t.website, t.last_scanned_at, t.scan_status, t.last_status, "
                           "GREATEST(COALESCE(t.last_scanned_at, t.updated_at), t.updated_at) AS ts", sid, " AND t.active = true")
    if not r:
        return None
    snap = await S._rows(session, """SELECT scanned_at, pages, plans, promotions FROM analytics_competitor_snapshots
        WHERE tenant_id = CAST(:t AS uuid) AND competitor_id = CAST(:c AS uuid) ORDER BY scanned_at DESC LIMIT 1""", {"t": tenant, "c": sid})
    chg = await S._rows(session, """SELECT change_type, subject, old_value, new_value, pct_change, source_url, detected_at
        FROM analytics_competitor_changes WHERE tenant_id = CAST(:t AS uuid) AND competitor_id = CAST(:c AS uuid)
        ORDER BY detected_at DESC LIMIT 10""", {"t": tenant, "c": sid})
    return B.competitor_card(r, snap[0] if snap else None, chg, S._utc(r["ts"]))


ROW_LOADERS: dict[str, Loader] = {
    "bi_deck": _load_deck, "bi_brand_kit": _load_kit, "research": _load_research,
    "campaign_analysis": _load_campaign_analysis, "competitor": _load_competitor,
}


async def load_card(session, tenant: str, source_type: str, source_id: str) -> Optional[Card]:
    if source_type not in ROW_LOADERS:
        raise KeyError(source_type)
    if not _UUIDISH.match(str(source_id)):
        raise ValueError("source_id must be a uuid")
    async with session.begin_nested():
        return await ROW_LOADERS[source_type](session, tenant, source_id)


def register(sources: dict) -> None:
    for s in ARTIFACT_SOURCES:
        sources[s.name] = s


register(S.SOURCES)
