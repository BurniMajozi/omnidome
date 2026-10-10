"""Reversible, derived-data-only fixes shared by the phases and by `POST /findings/{id}/resolve` (apply).

Nothing here touches an operational source table: it re-renders cards, tombstones/tags derived chunks, restores an
importance value or removes dangling graph edges. A finding's `action` names one of these kinds.
"""
from __future__ import annotations

from typing import Optional

from services.tenant_memory.knowledge.cards.base import Card
from services.tenant_memory.knowledge.dream.ports import DreamDeps
from services.tenant_memory.knowledge.dream.store import STALE_TAG
from services.tenant_memory.knowledge.indexer import card_to_chunks


def card_hashes(deps: DreamDeps, tenant: str, card: Card) -> dict[int, str]:
    s = deps.indexer.s
    return {c.chunk_no: c.content_hash for c in card_to_chunks(tenant, card, deps.embedder.model, s.chunk_chars, s.chunk_overlap)}


async def stored_hashes(deps: DreamDeps, tenant: str, source_type: str, source_id: str) -> dict[int, str]:
    state = await deps.store.kstore.source_state(tenant, source_type, source_id)
    return {no: h for no, (h, _model) in state.items()}


async def tombstone(deps: DreamDeps, tenant: str, source_type: str, source_id: str) -> int:
    n = await deps.store.kstore.tombstone_source(tenant, source_type, source_id)
    await deps.store.kstore.delete_edges_by_origin(tenant, f"{source_type}:{source_id}")
    return n


async def apply_action(deps: DreamDeps, tenant: str, finding: dict) -> dict:
    """Execute a finding's stored action. Returns {'applied': bool, ...}; never raises for an unsupported kind."""
    act = finding.get("action") or {}
    kind = act.get("kind")
    st, sid = act.get("source_type") or finding.get("source_type"), act.get("source_id") or finding.get("source_id")
    if kind in (None, "none", "review"):
        return {"applied": False, "note": "this finding has no automatic fix; accept or dismiss it"}
    if kind == "refresh":
        r = await deps.renderer.render(tenant, st, sid)
        if r.status == "gone":
            return {"applied": True, "result": "source gone: card tombstoned", "chunks": await tombstone(deps, tenant, st, sid)}
        if r.status != "ok" or r.card is None:
            return {"applied": False, "note": f"cannot re-render this card ({r.status})"}
        stats = await deps.indexer.index_cards(tenant, [r.card], force=True)
        return {"applied": True, "result": "card refreshed from its live source", "stats": stats}
    if kind == "tombstone":
        return {"applied": True, "result": "derived card tombstoned (source untouched)", "chunks": await tombstone(deps, tenant, st, sid)}
    if kind == "clear_stale":
        return {"applied": True, "tags_changed": await deps.store.tag_source(tenant, st, sid, [], [STALE_TAG])}
    if kind == "set_importance":
        n = await deps.store.kstore.set_importance(tenant, st, sid, float(act["value"]))
        state = await deps.store.get_card_state(tenant, st, sid) or {}
        state.update({"adjusted": float(act["value"]), "reason": "manual revert"})
        await deps.store.put_card_state(tenant, st, sid, state)
        return {"applied": n > 0, "chunks": n}
    if kind == "delete_edges":
        origins = list(act.get("origins") or [])
        for o in origins:
            await deps.store.kstore.delete_edges_by_origin(tenant, o)
        return {"applied": True, "origins": len(origins)}
    return {"applied": False, "note": f"unsupported action kind {kind!r}"}


def preview(markdown: str, limit: int = 160) -> str:
    from services.tenant_memory.knowledge.textutil import clip, split_frontmatter
    return clip(split_frontmatter(markdown)[1], limit)
