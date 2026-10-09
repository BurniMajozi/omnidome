"""Deck Studio persistence + routes: decks, insert-only versions, optimistic concurrency, data snapshots
(deck runs), server-side token resolution and JSON export. Mounted under /api/fno/bi/decks.

Roles: viewer reads / resolves / exports; analyst creates, edits, duplicates, restores, refreshes;
admin deletes and publishes (and is the only role that may edit a published deck).
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, desc, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from services.common.auth import AuthContext, get_current_tenant_id
from services.fno_intelligence import analytics_common as ac
from services.fno_intelligence import bi_brand, database
from services.fno_intelligence import bi_deck_model as dm
from services.fno_intelligence.bi_models import BiBrandKit, BiDeck, BiDeckRun, BiDeckVersion
from services.fno_intelligence.bi_semantic import QuerySpec, canonical_key, check_rate, run_query

logger = logging.getLogger("fno_intelligence.bi")
router = APIRouter(prefix="/decks", tags=["BI Studio: decks"])

MAX_DECKS = 500
MAX_VERSIONS = 1000
KEEP_RUNS = 10


# ── serialisation ─────────────────────────────────────────────────────────

def _iso(d: Optional[datetime]) -> Optional[str]:
    if not d:
        return None
    if d.tzinfo is None:  # SQLite hands back naive datetimes; everything we store is UTC
        d = d.replace(tzinfo=timezone.utc)
    return d.isoformat()


def deck_public(d: BiDeck, *, with_doc: bool = True) -> dict:
    out = {"id": str(d.id), "title": d.title, "status": d.status, "brand_kit_id": str(d.brand_kit_id) if d.brand_kit_id else None,
           "version": d.version, "slide_count": len((d.doc or {}).get("slides", [])),
           "created_by": str(d.created_by) if d.created_by else None, "updated_by": str(d.updated_by) if d.updated_by else None,
           "published_by": str(d.published_by) if d.published_by else None, "published_at": _iso(d.published_at),
           "created_at": _iso(d.created_at), "updated_at": _iso(d.updated_at)}
    if with_doc:
        out["doc"] = d.doc
    return out


async def load_deck(db: AsyncSession, tenant_id: uuid.UUID, deck_id: uuid.UUID) -> BiDeck:
    d = await db.get(BiDeck, deck_id)
    if d is None or d.tenant_id != tenant_id:
        raise HTTPException(404, "Deck not found")
    return d


def parse_if_match(request: Request, body_version: Optional[int]) -> int:
    raw = request.headers.get("if-match")
    if raw:
        m = re.search(r"(\d+)", raw)
        if m:
            return int(m.group(1))
        raise HTTPException(400, "If-Match must carry the deck version number")
    if body_version is not None:
        return body_version
    raise HTTPException(428, "Send the deck version you are editing in an If-Match header (or base_version in the body)")


def _require_edit(d: BiDeck, auth: AuthContext) -> None:
    if d.status == "published" and not ac.has_tier(auth, "admin"):
        raise HTTPException(403, "This deck is published; an admin must unpublish it before it can be edited")


async def _check_kit(db: AsyncSession, tenant_id: uuid.UUID, kit_id: Optional[uuid.UUID]) -> Optional[BiBrandKit]:
    if kit_id is None:
        return None
    kit = await bi_brand.load_kit(db, tenant_id, kit_id)
    if kit is None:
        raise HTTPException(422, "brand_kit_id does not belong to this tenant")
    return kit


async def _validate_doc(raw: Any, kit_id: Optional[uuid.UUID]) -> tuple[dict, list[dict]]:
    doc, warnings, _ = dm.validate_deck_doc(raw)
    for u in dm.image_urls(doc):
        await ac.check_public_url(u, field="image url")
    doc.brand_kit_id = str(kit_id) if kit_id else None
    return dm.dump_doc(doc), warnings


async def _cas_save(db: AsyncSession, deck: BiDeck, expected: int, *, title: str, doc: dict, kit_id: Optional[uuid.UUID],
                    auth: AuthContext, note: Optional[str]) -> BiDeck:
    if expected != deck.version:
        raise HTTPException(409, {"message": "The deck was changed by someone else", "current_version": deck.version})
    n = (await db.execute(select(func.count()).select_from(BiDeckVersion).where(BiDeckVersion.deck_id == deck.id))).scalar_one()
    if n >= MAX_VERSIONS:
        raise HTTPException(409, f"This deck has reached {MAX_VERSIONS} saved versions; duplicate it to continue")
    res = await db.execute(
        update(BiDeck).where(BiDeck.id == deck.id, BiDeck.tenant_id == deck.tenant_id, BiDeck.version == expected)
        .values(title=title, doc=doc, brand_kit_id=kit_id, version=expected + 1, updated_by=auth.user_id, updated_at=ac.now()))
    if res.rowcount != 1:
        cur = (await db.execute(select(BiDeck.version).where(BiDeck.id == deck.id))).scalar_one_or_none()
        raise HTTPException(409, {"message": "The deck was changed by someone else", "current_version": cur})
    db.add(BiDeckVersion(tenant_id=deck.tenant_id, deck_id=deck.id, version=expected + 1, title=title, doc=doc,
                         note=(note or None) and note[:200], created_by=auth.user_id, created_at=ac.now()))
    try:
        await db.flush()
    except IntegrityError:
        raise HTTPException(409, {"message": "The deck was changed by someone else", "current_version": expected + 1})
    await db.refresh(deck)
    return deck


# ── request bodies ────────────────────────────────────────────────────────

class DeckCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(..., min_length=1, max_length=200)
    doc: Optional[dict] = None
    brand_kit_id: Optional[uuid.UUID] = None


class DeckUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    doc: Optional[dict] = None
    brand_kit_id: Optional[uuid.UUID] = None
    clear_brand_kit: bool = False
    base_version: Optional[int] = Field(None, ge=1)
    note: Optional[str] = Field(None, max_length=200)


class VersionRestore(BaseModel):
    model_config = ConfigDict(extra="forbid")
    base_version: Optional[int] = Field(None, ge=1)


class PublishBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    published: bool = True


class ResolveBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: Optional[uuid.UUID] = None
    refresh: bool = False


# ── CRUD ──────────────────────────────────────────────────────────────────

@router.get("")
async def list_decks(status: Optional[str] = Query(None, pattern="^(draft|published)$"), q: Optional[str] = Query(None, max_length=100),
                     limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0, le=100000),
                     tenant_id: uuid.UUID = Depends(get_current_tenant_id), _: AuthContext = Depends(ac.require_viewer),
                     db: AsyncSession = Depends(database.get_session)):
    stmt = select(BiDeck).where(BiDeck.tenant_id == tenant_id)
    if status:
        stmt = stmt.where(BiDeck.status == status)
    if q:
        stmt = stmt.where(func.lower(BiDeck.title).like("%" + q.lower().replace("%", "").replace("_", "") + "%"))
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (await db.execute(stmt.order_by(desc(BiDeck.updated_at)).limit(limit).offset(offset))).scalars().all()
    return {"items": [deck_public(d, with_doc=False) for d in rows], "total": total}


@router.post("", status_code=201)
async def create_deck(body: DeckCreate, auth: AuthContext = Depends(ac.require_analyst),
                      db: AsyncSession = Depends(database.get_session)):
    tenant_id = auth.tenant_id
    n = (await db.execute(select(func.count()).select_from(BiDeck).where(BiDeck.tenant_id == tenant_id))).scalar_one()
    if n >= MAX_DECKS:
        raise HTTPException(409, f"At most {MAX_DECKS} decks per tenant")
    kit = await _check_kit(db, tenant_id, body.brand_kit_id) or await bi_brand.default_kit(db, tenant_id)
    kit_id = kit.id if kit else None
    raw = body.doc if body.doc is not None else dm.starter_doc(body.title)
    if body.doc is not None:
        raw = {**raw, "title": raw.get("title") or body.title}
    doc, warnings = await _validate_doc(raw, kit_id)
    deck = BiDeck(tenant_id=tenant_id, title=body.title.strip(), status="draft", brand_kit_id=kit_id, doc=doc, version=1,
                  created_by=auth.user_id, updated_by=auth.user_id)
    db.add(deck)
    await db.flush()
    db.add(BiDeckVersion(tenant_id=tenant_id, deck_id=deck.id, version=1, title=deck.title, doc=doc,
                         note="Created", created_by=auth.user_id, created_at=ac.now()))
    await db.flush()
    await db.refresh(deck)
    return {**deck_public(deck), "warnings": {"ungrounded_numbers": warnings}}


@router.get("/{deck_id}")
async def get_deck(deck_id: uuid.UUID, tenant_id: uuid.UUID = Depends(get_current_tenant_id),
                   _: AuthContext = Depends(ac.require_viewer), db: AsyncSession = Depends(database.get_session)):
    return deck_public(await load_deck(db, tenant_id, deck_id))


@router.put("/{deck_id}")
async def update_deck(deck_id: uuid.UUID, body: DeckUpdate, request: Request, auth: AuthContext = Depends(ac.require_analyst),
                      db: AsyncSession = Depends(database.get_session)):
    expected = parse_if_match(request, body.base_version)
    deck = await load_deck(db, auth.tenant_id, deck_id)
    _require_edit(deck, auth)
    kit_id = deck.brand_kit_id
    if body.clear_brand_kit:
        kit_id = None
    elif body.brand_kit_id is not None:
        await _check_kit(db, auth.tenant_id, body.brand_kit_id)
        kit_id = body.brand_kit_id
    title = (body.title or deck.title).strip()
    raw = body.doc if body.doc is not None else deck.doc
    if body.doc is not None and body.title is None and isinstance(raw, dict) and raw.get("title"):
        title = str(raw["title"]).strip()[:200] or title
    raw = {**raw, "title": title}
    doc, warnings = await _validate_doc(raw, kit_id)
    deck = await _cas_save(db, deck, expected, title=title, doc=doc, kit_id=kit_id, auth=auth, note=body.note)
    return {**deck_public(deck), "warnings": {"ungrounded_numbers": warnings}}


@router.delete("/{deck_id}", status_code=204)
async def delete_deck(deck_id: uuid.UUID, auth: AuthContext = Depends(ac.require_admin),
                      db: AsyncSession = Depends(database.get_session)):
    deck = await load_deck(db, auth.tenant_id, deck_id)
    for model in (BiDeckRun, BiDeckVersion):
        await db.execute(delete(model).where(model.deck_id == deck.id, model.tenant_id == auth.tenant_id))
    await db.delete(deck)


@router.post("/{deck_id}/duplicate", status_code=201)
async def duplicate_deck(deck_id: uuid.UUID, auth: AuthContext = Depends(ac.require_analyst),
                         db: AsyncSession = Depends(database.get_session)):
    src = await load_deck(db, auth.tenant_id, deck_id)
    n = (await db.execute(select(func.count()).select_from(BiDeck).where(BiDeck.tenant_id == auth.tenant_id))).scalar_one()
    if n >= MAX_DECKS:
        raise HTTPException(409, f"At most {MAX_DECKS} decks per tenant")
    title = ("Copy of " + src.title)[:200]
    doc = {**src.doc, "title": title}
    deck = BiDeck(tenant_id=auth.tenant_id, title=title, status="draft", brand_kit_id=src.brand_kit_id, doc=doc, version=1,
                  created_by=auth.user_id, updated_by=auth.user_id)
    db.add(deck)
    await db.flush()
    db.add(BiDeckVersion(tenant_id=auth.tenant_id, deck_id=deck.id, version=1, title=title, doc=doc,
                         note=f"Duplicated from {src.id} v{src.version}", created_by=auth.user_id, created_at=ac.now()))
    await db.flush()
    await db.refresh(deck)
    return deck_public(deck)


@router.post("/{deck_id}/publish")
async def publish_deck(deck_id: uuid.UUID, body: PublishBody, auth: AuthContext = Depends(ac.require_admin),
                       db: AsyncSession = Depends(database.get_session)):
    deck = await load_deck(db, auth.tenant_id, deck_id)
    deck.status = "published" if body.published else "draft"
    deck.published_by = auth.user_id if body.published else None
    deck.published_at = ac.now() if body.published else None
    await db.flush()
    await db.refresh(deck)
    return deck_public(deck, with_doc=False)


# ── versions ──────────────────────────────────────────────────────────────

@router.get("/{deck_id}/versions")
async def list_versions(deck_id: uuid.UUID, tenant_id: uuid.UUID = Depends(get_current_tenant_id),
                        _: AuthContext = Depends(ac.require_viewer), db: AsyncSession = Depends(database.get_session)):
    await load_deck(db, tenant_id, deck_id)
    rows = (await db.execute(select(BiDeckVersion).where(BiDeckVersion.deck_id == deck_id, BiDeckVersion.tenant_id == tenant_id)
                             .order_by(desc(BiDeckVersion.version)).limit(200))).scalars().all()
    return {"items": [{"version": v.version, "title": v.title, "note": v.note, "created_by": str(v.created_by) if v.created_by else None,
                       "created_at": _iso(v.created_at), "slide_count": len((v.doc or {}).get("slides", []))} for v in rows]}


async def _version(db: AsyncSession, tenant_id: uuid.UUID, deck_id: uuid.UUID, n: int) -> BiDeckVersion:
    v = (await db.execute(select(BiDeckVersion).where(BiDeckVersion.deck_id == deck_id, BiDeckVersion.tenant_id == tenant_id,
                                                      BiDeckVersion.version == n))).scalars().first()
    if v is None:
        raise HTTPException(404, "Version not found")
    return v


@router.get("/{deck_id}/versions/{version}")
async def get_version(deck_id: uuid.UUID, version: int, tenant_id: uuid.UUID = Depends(get_current_tenant_id),
                      _: AuthContext = Depends(ac.require_viewer), db: AsyncSession = Depends(database.get_session)):
    await load_deck(db, tenant_id, deck_id)
    v = await _version(db, tenant_id, deck_id, version)
    return {"version": v.version, "title": v.title, "note": v.note, "doc": v.doc, "created_at": _iso(v.created_at)}


@router.post("/{deck_id}/versions/{version}/restore")
async def restore_version(deck_id: uuid.UUID, version: int, request: Request, body: Optional[VersionRestore] = None,
                          auth: AuthContext = Depends(ac.require_analyst), db: AsyncSession = Depends(database.get_session)):
    expected = parse_if_match(request, body.base_version if body else None)
    deck = await load_deck(db, auth.tenant_id, deck_id)
    _require_edit(deck, auth)
    old = await _version(db, auth.tenant_id, deck_id, version)
    doc, _ = await _validate_doc(old.doc, deck.brand_kit_id)
    deck = await _cas_save(db, deck, expected, title=old.title, doc=doc, kit_id=deck.brand_kit_id, auth=auth,
                           note=f"Restored from v{version}")
    return deck_public(deck)


# ── data: refresh, runs, resolve, export ─────────────────────────────────

async def execute_aliases(db: AsyncSession, tenant_id: uuid.UUID, specs: dict[str, QuerySpec]) -> tuple[dict, dict]:
    """Run each distinct query once; returns ({alias: result}, {alias: error message}). Does not touch the deck."""
    unique: dict[str, QuerySpec] = {}
    for sp in specs.values():
        unique.setdefault(canonical_key(sp), sp)
    check_rate(tenant_id, cost=len(unique)) if unique else None
    done: dict[str, Any] = {}
    for key, sp in unique.items():
        try:
            done[key] = await run_query(db, tenant_id, sp, enforce_rate=False)
        except HTTPException as exc:
            done[key] = str(exc.detail)[:300]
        except Exception as exc:  # noqa: BLE001
            logger.warning("deck query failed: %s", exc)
            done[key] = "Query failed"
    data, errors = {}, {}
    for alias, sp in specs.items():
        r = done[canonical_key(sp)]
        if isinstance(r, dict):
            data[alias] = r
        else:
            errors[alias] = r
    return data, errors


async def _make_run(db: AsyncSession, deck: BiDeck, doc: dm.DeckDoc, auth_user: Optional[uuid.UUID]) -> BiDeckRun:
    data, errors = await execute_aliases(db, deck.tenant_id, dm.alias_specs(doc))
    run = BiDeckRun(tenant_id=deck.tenant_id, deck_id=deck.id, doc_version=deck.version, data=data, errors=errors,
                    created_by=auth_user, as_of=ac.now())
    db.add(run)
    await db.flush()
    old = (await db.execute(select(BiDeckRun.id).where(BiDeckRun.deck_id == deck.id).order_by(desc(BiDeckRun.as_of))
                            .offset(KEEP_RUNS))).scalars().all()
    if old:
        await db.execute(delete(BiDeckRun).where(BiDeckRun.id.in_(old)))
    return run


def _run_public(run: BiDeckRun, with_data: bool = True) -> dict:
    out = {"run_id": str(run.id), "deck_id": str(run.deck_id), "doc_version": run.doc_version, "as_of": _iso(run.as_of),
           "errors": run.errors or {}, "queries": sorted((run.data or {}).keys())}
    if with_data:
        out["data"] = run.data or {}
    return out


@router.post("/{deck_id}/refresh")
async def refresh_deck(deck_id: uuid.UUID, auth: AuthContext = Depends(ac.require_analyst),
                       db: AsyncSession = Depends(database.get_session)):
    """Execute every block's query and store a data snapshot ("data as of ..."). The document is NOT modified."""
    deck = await load_deck(db, auth.tenant_id, deck_id)
    doc, _, _ = dm.validate_deck_doc(deck.doc)
    run = await _make_run(db, deck, doc, auth.user_id)
    blocks = {b.id: dm.block_alias(b) for s in doc.slides for b in s.blocks if dm.block_alias(b)}
    return {**_run_public(run), "blocks": blocks}


@router.get("/{deck_id}/runs")
async def list_runs(deck_id: uuid.UUID, tenant_id: uuid.UUID = Depends(get_current_tenant_id),
                    _: AuthContext = Depends(ac.require_viewer), db: AsyncSession = Depends(database.get_session)):
    await load_deck(db, tenant_id, deck_id)
    rows = (await db.execute(select(BiDeckRun).where(BiDeckRun.deck_id == deck_id, BiDeckRun.tenant_id == tenant_id)
                             .order_by(desc(BiDeckRun.as_of)).limit(KEEP_RUNS))).scalars().all()
    return {"items": [_run_public(r, with_data=False) for r in rows]}


@router.get("/{deck_id}/runs/{run_id}")
async def get_run(deck_id: uuid.UUID, run_id: uuid.UUID, tenant_id: uuid.UUID = Depends(get_current_tenant_id),
                  _: AuthContext = Depends(ac.require_viewer), db: AsyncSession = Depends(database.get_session)):
    await load_deck(db, tenant_id, deck_id)
    run = await db.get(BiDeckRun, run_id)
    if run is None or run.tenant_id != tenant_id or run.deck_id != deck_id:
        raise HTTPException(404, "Run not found")
    return _run_public(run)


async def _pick_run(db: AsyncSession, deck: BiDeck, doc: dm.DeckDoc, auth: AuthContext, body: ResolveBody) -> BiDeckRun:
    if body.run_id:
        run = await db.get(BiDeckRun, body.run_id)
        if run is None or run.tenant_id != deck.tenant_id or run.deck_id != deck.id:
            raise HTTPException(404, "Run not found")
        return run
    if not body.refresh:
        run = (await db.execute(select(BiDeckRun).where(BiDeckRun.deck_id == deck.id, BiDeckRun.tenant_id == deck.tenant_id)
                                .order_by(desc(BiDeckRun.as_of)).limit(1))).scalars().first()
        if run is not None and run.doc_version == deck.version:
            return run
    if not ac.has_tier(auth, "analyst") and body.refresh:
        raise HTTPException(403, "Refreshing deck data needs an analytics analyst role")
    return await _make_run(db, deck, doc, auth.user_id)


async def build_resolution(db: AsyncSession, deck: BiDeck, auth: AuthContext, body: ResolveBody) -> dict:
    doc, _, _ = dm.validate_deck_doc(deck.doc)
    run = await _pick_run(db, deck, doc, auth, body)
    kit = await bi_brand.load_kit(db, deck.tenant_id, deck.brand_kit_id)
    slides, unresolved = dm.resolve_deck(doc, run.data or {})
    return {"deck_id": str(deck.id), "title": deck.title, "version": deck.version, "run_id": str(run.id),
            "run_doc_version": run.doc_version, "stale_data": run.doc_version != deck.version, "as_of": _iso(run.as_of),
            "theme": dm.effective_theme(kit.config if kit else None, doc.theme),
            "slides": slides, "unresolved": unresolved, "query_errors": run.errors or {},
            "_run": run, "_doc": doc, "_kit": kit}


@router.post("/{deck_id}/resolve")
async def resolve_deck_route(deck_id: uuid.UUID, body: Optional[ResolveBody] = None, auth: AuthContext = Depends(ac.require_viewer),
                             db: AsyncSession = Depends(database.get_session)):
    """Tokens -> display strings, computed server-side from the chosen (default: latest current) data snapshot."""
    deck = await load_deck(db, auth.tenant_id, deck_id)
    res = await build_resolution(db, deck, auth, body or ResolveBody())
    return {k: v for k, v in res.items() if not k.startswith("_")}


@router.get("/{deck_id}/export/json")
async def export_json(deck_id: uuid.UUID, run_id: Optional[uuid.UUID] = None, refresh: bool = False,
                      auth: AuthContext = Depends(ac.require_viewer), db: AsyncSession = Depends(database.get_session)):
    """Everything a client needs to build the PowerPoint: document, resolved text, theme, brand kit (with logo) and data."""
    deck = await load_deck(db, auth.tenant_id, deck_id)
    res = await build_resolution(db, deck, auth, ResolveBody(run_id=run_id, refresh=refresh))
    kit = res["_kit"]
    return {"format": "omnidome-deck/1", "exported_at": ac.now().isoformat(),
            "deck": {"id": str(deck.id), "title": deck.title, "version": deck.version, "status": deck.status},
            "doc": dm.dump_doc(res["_doc"]),
            "brand_kit": bi_brand.kit_public(kit) if kit else None,
            **{k: v for k, v in res.items() if not k.startswith("_")},
            "data": res["_run"].data or {}}
