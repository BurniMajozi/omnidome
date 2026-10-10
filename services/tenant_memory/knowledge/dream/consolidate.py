"""Phase 6 - CONSOLIDATION: the existing nightly jobs, run in the right order as part of the night.

short-term -> long-term promotion, expired working memory deleted, near-duplicate memory merge, episodic -> semantic roll-up,
M5 retention (archive low importance) and tombstone purge are `consolidation.consolidate_tenant`; M4 compaction/M5 housekeeping
of the orchestrator are triggered through the optional `housekeeping` port (off unless DREAM_HOUSEKEEPING_VIA_ORCHESTRATOR).
Nothing new is invented here, so the behaviour (and its safety) is exactly what already runs from the worker sweep.
"""
from __future__ import annotations

from services.tenant_memory.knowledge.dream.context import PhaseCtx


async def run(ctx: PhaseCtx) -> None:
    if ctx.state.get("done"):
        return
    rep = await ctx.deps.consolidate(ctx.tenant, ctx.dry_run)
    promo = rep.get("promotion") or {}
    out = {
        "promoted": len(promo.get("promoted") or []), "working_expired": int(promo.get("expired_deleted") or 0),
        "duplicate_groups": int((rep.get("merge") or {}).get("groups") or 0), "duplicates_archived": int((rep.get("merge") or {}).get("archived") or 0),
        "rollup_groups": int((rep.get("rollup") or {}).get("groups") or 0), "rollup_entries": int((rep.get("rollup") or {}).get("entries") or 0),
        "archived_low_importance": int((rep.get("decay") or {}).get("archived_low_importance") or 0),
        "chunks_decayed": int((rep.get("decay") or {}).get("chunks_decayed") or 0), "tombstones_purged": int(rep.get("purged_tombstones") or 0),
        "dry_run": ctx.dry_run,
    }
    ctx.counts.update({k: v for k, v in out.items() if isinstance(v, int)})
    ctx.state["done"] = True
    if ctx.deps.housekeeping is not None:
        try:
            hk = await ctx.deps.housekeeping(ctx.tenant, ctx.dry_run)
            out["housekeeping"] = {k: hk[k] for k in list(hk)[:8]} if isinstance(hk, dict) else {}
        except Exception as exc:  # noqa: BLE001
            ctx.error("orchestrator housekeeping", exc)
    ctx.shared["consolidation"] = out
    await ctx.checkpoint()
