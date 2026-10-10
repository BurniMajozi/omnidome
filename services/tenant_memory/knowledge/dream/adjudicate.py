"""Phase 5 - JEV ADJUDICATION (budgeted, optional, external).

Only borderline items the deterministic phases queued: 'is this card still current?', 'do these two cards contradict?',
'is this memory worth keeping long term?'. Acts ONLY at p >= approve (0.90) or p <= reject (0.10); the middle band stays
with a human in the admin panel. Decisions are cached (30 days), capped per tenant per night (calls and USD) and the whole
phase is a no-op unless DREAM_JEV_ENABLED (or the tenant setting) is on AND credentials exist. A dry run only reads the cache.
"""
from __future__ import annotations

import os

from services.tenant_memory.knowledge.dream import jev as J
from services.tenant_memory.knowledge.dream.context import PhaseCtx
from services.tenant_memory.knowledge.dream.store import COLD_TAG, STALE_TAG

PRIORITY = {"contradict": 0, "still_current": 1, "keep_long_term": 2}


def est_cost() -> float:
    try:
        return float(os.getenv("DREAM_JEV_EST_COST_USD", "0.002"))
    except ValueError:
        return 0.002


async def run(ctx: PhaseCtx) -> None:
    cfg, deps, tenant = ctx.cfg, ctx.deps, ctx.tenant
    queue = sorted(ctx.shared.get("adjudication_queue", []), key=lambda i: (PRIORITY.get(i["kind"], 9), i["source_type"], i["source_id"]))
    st = ctx.jev_state()
    ctx.counts["candidates"] = len(queue)
    live = bool(cfg.jev_enabled and deps.jev is not None and deps.jev.configured() and not ctx.dry_run)
    if not queue:
        return
    if not cfg.jev_enabled:
        ctx.note("JEV adjudication is off (DREAM_JEV_ENABLED): borderline items stay with the human review queue")
    elif deps.jev is None or not deps.jev.configured():
        ctx.note("JEV credentials missing: borderline items stay with the human review queue")
    elif ctx.dry_run:
        ctx.note("dry run: JEV is not called (cached decisions only)")
    done = set(ctx.state.get("done", []))
    for item in queue:
        ident = f"{item['kind']}:{item['source_type']}:{item['source_id']}:{item.get('other_id', '')}"
        if ident in done:
            continue
        ctx.check_kill()
        try:
            await _one(ctx, item, st, live)
        except Exception as exc:  # noqa: BLE001
            ctx.error(f"jev {item['kind']}", exc)
        done.add(ident)
        ctx.state["done"] = sorted(done)
        await ctx.checkpoint()
    ctx.counts.update({"jev_calls": st["calls"], "jev_cached": st["cached"], "queued_for_review": st["queued_for_review"], "decided": st["decided"]})


async def _one(ctx: PhaseCtx, item: dict, st: dict, live: bool) -> None:
    cfg, deps, tenant = ctx.cfg, ctx.deps, ctx.tenant
    kind = item["kind"]
    chunks = await deps.store.get_chunks(tenant, item["source_type"], item["source_id"])
    if not chunks or not J.eligible_for_jev(chunks[0], cfg.jev_exclude_modules):
        st["queued_for_review"] += 1
        ctx.inc("not_eligible")
        return
    now = ctx.now
    if kind == "contradict":
        other = await deps.store.get_chunks(tenant, item["source_type"], item["other_id"])
        if not other or not J.eligible_for_jev(other[0], cfg.jev_exclude_modules):
            st["queued_for_review"] += 1
            ctx.inc("not_eligible")
            return
        state = {"card_a": J.card_payload(chunks[0], now), "card_b": J.card_payload(other[0], now)}
    else:
        state = {"card": J.card_payload(chunks[0], now)}
        if kind == "still_current":
            r = await deps.renderer.render(tenant, item["source_type"], item["source_id"])
            state["live_source"] = ({"excerpt": J.excerpt(r.card.markdown)} if r.status == "ok" and r.card is not None
                                    else {"unavailable": r.status})
    key = J.cache_key(kind, state)
    cached = await deps.store.cache_get(tenant, key)
    if cached is not None:
        p, model, cost, was_cached = float(cached["p"]), cached.get("model", ""), 0.0, True
        st["cached"] += 1
    else:
        if not live:
            st["queued_for_review"] += 1
            return
        if st["calls"] >= cfg.jev_max_calls or st["cost_usd"] >= cfg.jev_max_cost_usd:
            st["queued_for_review"] += 1
            ctx.inc("budget_exhausted")
            return
        ans = await deps.jev.ask(state, {kind: J.QUESTIONS[kind]})
        p = float(ans.probs.get(kind, 0.5))
        cost = float(ans.cost_usd or est_cost())
        model, was_cached = ans.model, False
        st["calls"] += 1
        st["cost_usd"] = round(st["cost_usd"] + cost, 6)
        await deps.store.cache_put(tenant, key, {"p": p, "model": model, "kind": kind})
    verdict = J.decide(p, cfg.jev_approve, cfg.jev_reject)
    jev = {"question": kind, "p": round(p, 4), "decision": verdict, "model": model, "cached": was_cached, "cost_usd": round(cost, 6),
           "thresholds": {"approve": cfg.jev_approve, "reject": cfg.jev_reject}}
    if verdict == "review":
        st["queued_for_review"] += 1
        if kind == "contradict":
            await _attach_to_conflict(ctx, item, jev)
        return
    st["decided"] += 1
    await _apply(ctx, item, verdict, jev, chunks[0])


async def _attach_to_conflict(ctx: PhaseCtx, item: dict, jev: dict, patch: dict | None = None) -> None:
    for f in await ctx.deps.store.list_findings(ctx.tenant, type="conflict", limit=500):
        if f.get("dedupe_key") == item.get("dedupe_key"):
            if not ctx.dry_run:
                await ctx.deps.store.update_finding(ctx.tenant, f["id"], {"jev": jev, **(patch or {})})
            return


async def _apply(ctx: PhaseCtx, item: dict, verdict: str, jev: dict, chunk) -> None:
    deps, tenant, kind = ctx.deps, ctx.tenant, item["kind"]
    st_, sid = item["source_type"], item["source_id"]
    if kind == "still_current":
        if verdict == "yes":
            if not ctx.dry_run:
                await deps.store.tag_source(tenant, st_, sid, [], [STALE_TAG])
            await ctx.finding(type="jev_still_current", severity="info", source_type=st_, source_id=sid, jev=jev, auto_applied=True,
                              title=f"JEV judged the old card '{chunk.title[:70]}' still current - stale marker cleared",
                              detail={"before": "dream:stale", "after": "cleared"}, action={"kind": "clear_stale"})
        else:
            await ctx.finding(type="jev_stale_confirmed", severity="medium", source_type=st_, source_id=sid, jev=jev,
                              title=f"JEV judged the card '{chunk.title[:70]}' out of date - needs a refresh from its source",
                              detail={"hint": "its live source could not be re-rendered automatically tonight"}, action={"kind": "refresh"})
    elif kind == "contradict":
        if verdict == "yes":
            await _attach_to_conflict(ctx, item, jev, {"severity": "high"})
        else:
            await _attach_to_conflict(ctx, item, jev, {"status": "dismissed", "resolved_by": "dream:jev", "resolved_at": ctx.now.isoformat()})
    elif kind == "keep_long_term":
        state = await deps.store.get_card_state(tenant, st_, sid) or {}
        if verdict == "yes":
            state["keep"] = True
            if not ctx.dry_run:
                await deps.store.put_card_state(tenant, st_, sid, state)
                await deps.store.tag_source(tenant, st_, sid, [], [COLD_TAG])
            await ctx.finding(type="jev_keep", severity="info", source_type=st_, source_id=sid, jev=jev, auto_applied=True,
                              title=f"JEV judged '{chunk.title[:70]}' worth keeping: protected from decay",
                              detail={"after": "kept"}, action={"kind": "none"})
        else:
            new = max(0.1, min(chunk.importance, 0.15))
            if not ctx.dry_run:
                await deps.store.kstore.set_importance(tenant, st_, sid, new)
                state.update({"base": state.get("base", chunk.importance), "adjusted": new, "reason": "JEV: not worth keeping long term"})
                await deps.store.put_card_state(tenant, st_, sid, state)
            await ctx.finding(type="jev_not_worth_keeping", severity="low", source_type=st_, source_id=sid, jev=jev, auto_applied=True,
                              title=f"JEV judged '{chunk.title[:70]}' not worth keeping long term: importance lowered (kept, not deleted)",
                              detail={"before": chunk.importance, "after": new}, action={"kind": "set_importance", "value": chunk.importance})
