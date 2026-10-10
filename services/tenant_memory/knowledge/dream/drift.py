"""Phase 1 - SOURCE DRIFT & VALIDITY.

* re-render a rotating sample (plus every high-importance card) from its live source with the existing builders and
  compare the content hash: refresh what changed, tombstone what vanished, flag sources whose table disappeared;
* mark cards older than their per-source freshness SLA `dream:stale` (unless verified against the source tonight);
* delete graph edges whose origin card no longer exists.

Only derived rows are written (chunks, tags, edges). Source tables are read-only here.
"""
from __future__ import annotations

import hashlib
from datetime import timedelta

from services.tenant_memory.knowledge.dream import actions
from services.tenant_memory.knowledge.dream.context import PhaseCtx
from services.tenant_memory.knowledge.dream.store import STALE_TAG
from services.tenant_memory.knowledge.indexer import EmbeddingBlocked
from services.tenant_memory.knowledge.retrieval import DEFAULT_STALE_DAYS, STALE_AFTER_DAYS

CURSOR_KEY = ("__dream__", "drift_cursor")
MAX_JEV_STALE_CANDIDATES = 10


def in_sample(source_type: str, source_id: str, day_ordinal: int, rotation: int) -> bool:
    """Deterministic rotation: every card is picked on exactly one night in `rotation`."""
    h = int(hashlib.md5(f"{source_type}:{source_id}".encode()).hexdigest()[:8], 16)
    return h % max(1, rotation) == day_ordinal % max(1, rotation)


def sla_days(cfg, source_type: str) -> int:
    return int(cfg.stale_days.get(source_type) or STALE_AFTER_DAYS.get(source_type, DEFAULT_STALE_DAYS))


async def run(ctx: PhaseCtx) -> None:
    ctx.deps.renderer.reset()
    ctx.shared.setdefault("verified", [])
    ctx.shared["_verified"] = set(ctx.shared["verified"])
    ctx.shared.setdefault("_refreshed", [])
    ctx.shared.setdefault("adjudication_queue", [])
    if not ctx.state.get("verify_done"):
        await _verify(ctx)
        ctx.state["verify_done"] = True
        await ctx.checkpoint()
    if not ctx.state.get("stale_done"):
        await _stale(ctx)
        ctx.state["stale_done"] = True
        await ctx.checkpoint()
    await _orphan_edges(ctx)


# ── A. verify cards against their live source ──────────────────────────────

async def _verify(ctx: PhaseCtx) -> None:
    cfg, store, tenant = ctx.cfg, ctx.deps.store, ctx.tenant
    saved = await store.get_card_state(ctx.tenant, *CURSOR_KEY) or {}
    cursor = ctx.state.get("cursor", saved.get("cursor"))
    budget = max(0, cfg.max_cards_per_night - int(ctx.state.get("rendered", 0)))
    day = ctx.now.date().toordinal()
    missing_types: set = set(ctx.state.get("missing_types", []))
    wrapped = False
    while budget > 0:
        page = await store.scan_cards(tenant, tuple(cursor) if cursor else None, cfg.batch_size)
        if not page:
            cursor, wrapped = None, True
            break
        for ch in page:
            if budget <= 0:
                break
            cursor = [ch.source_type, ch.source_id, ch.chunk_no]
            if ch.valid_to is not None or ch.visibility == "private":
                ctx.inc("skipped_ephemeral")
                continue
            if not (ch.importance >= cfg.high_importance or in_sample(ch.source_type, ch.source_id, day, cfg.rotation_days)):
                continue
            if ch.source_type in missing_types:
                continue
            budget -= 1
            ctx.state["rendered"] = int(ctx.state.get("rendered", 0)) + 1
            try:
                await _verify_one(ctx, ch, missing_types)
            except EmbeddingBlocked as exc:
                ctx.error("embedding blocked during refresh", exc)
                ctx.note("embedding service unavailable: card refreshes postponed to the next night")
                budget = 0
                break
            except Exception as exc:  # noqa: BLE001 - one broken card must not end the phase
                ctx.error(f"{ch.source_type}:{ch.source_id}", exc)
        ctx.state["cursor"] = cursor
        ctx.state["missing_types"] = sorted(missing_types)
        ctx.shared["verified"] = sorted(ctx.shared["_verified"])
        await ctx.pause()
    ctx.state["cursor"] = cursor
    ctx.counts["pass_wrapped"] = int(wrapped)
    if not ctx.dry_run:
        await store.put_card_state(tenant, *CURSOR_KEY, {"cursor": cursor, "at": ctx.now.isoformat()})
    ctx.shared["verified"] = sorted(ctx.shared["_verified"])


async def _verify_one(ctx: PhaseCtx, ch, missing_types: set) -> None:
    deps, tenant, key = ctx.deps, ctx.tenant, f"{ch.source_type}:{ch.source_id}"
    r = await deps.renderer.render(tenant, ch.source_type, ch.source_id)
    ctx.inc("rendered")
    if r.status == "source_missing":
        missing_types.add(ch.source_type)
        await ctx.finding(type="source_table_missing", severity="high", source_type=ch.source_type,
                          title=f"Source for '{ch.source_type}' cards is unreachable ({r.note or 'table missing'})",
                          detail={"note": r.note, "action_needed": "check the source service/migration; cards were NOT removed"},
                          dedupe_key=f"source_table_missing:{ch.source_type}", action={"kind": "none"})
        return
    if r.status == "gone":
        ctx.inc("vanished")
        if not ctx.dry_run:
            await actions.tombstone(deps, tenant, ch.source_type, ch.source_id)
        await ctx.finding(type="source_vanished", severity="medium", source_type=ch.source_type, source_id=ch.source_id,
                          title=f"Source row for card '{ch.title[:80]}' no longer exists",
                          detail={"before": {"title": ch.title, "as_of": ch.as_of.isoformat() if ch.as_of else None}, "after": "tombstoned"},
                          auto_applied=True, action={"kind": "tombstone"})
        return
    if r.status != "ok" or r.card is None:
        ctx.inc("unverifiable")
        ctx.shared.setdefault("_unverifiable", set()).add(key)
        return
    new = actions.card_hashes(deps, tenant, r.card)
    old = await actions.stored_hashes(deps, tenant, ch.source_type, ch.source_id)
    if new == old:
        ctx.inc("verified")
        ctx.shared["_verified"].add(key)
        if STALE_TAG in ch.tags and not ctx.dry_run:
            await deps.store.tag_source(tenant, ch.source_type, ch.source_id, [], [STALE_TAG])
        return
    ctx.inc("content_drift")
    ctx.shared["_verified"].add(key)
    before_chunks = await deps.store.get_chunks(tenant, ch.source_type, ch.source_id)
    before_md = before_chunks[0].markdown if before_chunks else ""
    detail = {"before": {"hash": (old.get(0) or "")[:12], "chunks": len(old), "title": ch.title, "preview": actions.preview(before_md)},
              "after": {"hash": (new.get(0) or "")[:12], "chunks": len(new), "title": r.card.title, "preview": actions.preview(r.card.markdown)}}
    if not ctx.dry_run:
        if before_chunks and before_chunks[0].embedding:
            ctx.shared["_refreshed"].append((ch.source_type, ch.source_id, list(before_chunks[0].embedding)))
        await deps.indexer.index_cards(tenant, [r.card])
        ctx.inc("refreshed")
    await ctx.finding(type="content_drift", severity="low", source_type=ch.source_type, source_id=ch.source_id,
                      title=f"Card '{r.card.title[:80]}' no longer matched its live source - refreshed",
                      detail=detail, auto_applied=True, action={"kind": "refresh"})


# ── B. staleness ────────────────────────────────────────────────────────────

async def _stale(ctx: PhaseCtx) -> None:
    cfg, store, tenant, now = ctx.cfg, ctx.deps.store, ctx.tenant, ctx.now
    verified, unverifiable = ctx.shared["_verified"], ctx.shared.get("_unverifiable", set())
    counts = await store.count_cards(tenant)
    ctx.shared["_card_counts"] = counts
    cutoffs = {t: now - timedelta(days=sla_days(cfg, t)) for t in counts["source_types"]}
    for t in sorted(counts["source_types"]):
        cands = [c for c in await store.find_stale(tenant, t, cutoffs[t], STALE_TAG, 500) if f"{t}:{c[1]}" not in verified]
        if not cands:
            continue
        ctx.inc("stale_marked", len(cands))
        if not ctx.dry_run:
            for _t, sid, _asof in cands:
                await store.tag_source(tenant, t, sid, [STALE_TAG], [])
        total = max(1, counts["source_types"][t])
        await ctx.finding(
            type="stale_cards", severity="medium" if len(cands) / total > 0.5 else "low", source_type=t,
            title=f"{len(cands)} '{t}' card(s) older than the {sla_days(cfg, t)}-day freshness limit and not verified tonight",
            detail={"count": len(cands), "of": total, "sla_days": sla_days(cfg, t), "oldest": [{"id": c[1], "as_of": c[2].isoformat()} for c in cands[:5]]},
            dedupe_key=f"stale_cards:{t}", auto_applied=True, action={"kind": "none"})
        queued = ctx.shared["adjudication_queue"]
        for _t, sid, asof in cands:
            if len(queued) >= MAX_JEV_STALE_CANDIDATES:
                break
            if f"{t}:{sid}" in unverifiable:
                queued.append({"kind": "still_current", "source_type": t, "source_id": sid, "as_of": asof.isoformat()})
    # clear the marker where the card became fresh again (re-indexed) or was verified
    for t, sid, asof in await store.tagged(tenant, STALE_TAG, 2000):
        fresh = asof is not None and t in cutoffs and asof >= cutoffs[t]
        if f"{t}:{sid}" in verified or fresh:
            ctx.inc("stale_cleared")
            if not ctx.dry_run:
                await store.tag_source(tenant, t, sid, [], [STALE_TAG])
    ctx.counts["stale_tagged_after"] = (await store.count_cards(tenant))["stale_tagged"]


# ── C. orphaned graph edges ─────────────────────────────────────────────────

async def _orphan_edges(ctx: PhaseCtx) -> None:
    store, kstore, tenant = ctx.deps.store, ctx.deps.store.kstore, ctx.tenant
    live: dict[str, set] = {}
    orphans = []
    for origin in sorted(await store.edge_origins(tenant)):
        t, _, sid = origin.partition(":")
        if t not in live:
            live[t] = await kstore.live_source_ids(tenant, t)
        if sid not in live[t]:
            orphans.append(origin)
        if len(orphans) >= 500:
            break
    ctx.counts["orphan_edge_origins"] = len(orphans)
    if orphans:
        if not ctx.dry_run:
            for o in orphans:
                await kstore.delete_edges_by_origin(tenant, o)
        await ctx.finding(type="orphan_edges", severity="low", title=f"{len(orphans)} graph edge group(s) pointed from cards that no longer exist - removed",
                          detail={"origins": orphans[:10], "count": len(orphans)}, dedupe_key="orphan_edges", auto_applied=True,
                          action={"kind": "delete_edges", "origins": orphans[:200]})
    types = list((await store.count_cards(tenant))["source_types"])
    dangling = await store.dangling_edges(tenant, types, 200)
    ctx.counts["dangling_edges"] = len(dangling)
    if dangling:
        await ctx.finding(type="dangling_edges", severity="info", title=f"{len(dangling)} graph edge(s) point at cards that are not indexed (yet)",
                          detail={"examples": [list(d) for d in dangling[:5]]}, dedupe_key="dangling_edges", action={"kind": "none"})
