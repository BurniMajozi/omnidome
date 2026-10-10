"""Phase 4 - RELEVANCE & PRIORITY.

* usefulness per card from retrieval telemetry (retrieved / used / cited / thumbs / JEV scores) -> a bounded, explainable
  nudge of the stored `importance` (max +-step per night, max +-drift from the builder's base, protected cards can only
  go up, never below 0.1);
* cards never retrieved for a long time decay (tagged `dream:cold`) - archived by the M5 rules in phase 6, never deleted here;
* near-duplicate / contradictory cards become 'conflict' review items (identical text is merged only for configured types).
Skills are knowledge cards too, so their usage-based priority is the same mechanism (`skills_ranked` in the report).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from services.tenant_memory.knowledge.dream import actions
from services.tenant_memory.knowledge.dream.context import PhaseCtx
from services.tenant_memory.knowledge.dream.ports import Usage
from services.tenant_memory.knowledge.dream.settings import DreamSettings
from services.tenant_memory.knowledge.dream.store import COLD_TAG, STALE_TAG
from services.tenant_memory.knowledge.textutil import split_frontmatter

PROTECTED_MODULE_PREFIXES = ("compliance", "legal")
PROTECTED_TAGS = frozenset({"compliance", "legal", "critical", "popia", "regulatory"})
IMPORTANCE_FLOOR = 0.1
STATUS_WORDS = frozenset({"active", "inactive", "cancelled", "canceled", "suspended", "paid", "unpaid", "overdue", "open", "closed",
                          "resolved", "pending", "won", "lost", "approved", "rejected", "expired"})
_NUM = re.compile(r"\d[\d,]*\.?\d*")
_WORD = re.compile(r"[a-z]+")


@dataclass
class Adjustment:
    new: float
    reason: str
    cold: bool = False


def is_protected(module: str, tags: list, base: float) -> bool:
    mod = (module or "").lower()
    return base >= 0.95 or mod.startswith(PROTECTED_MODULE_PREFIXES) or bool(PROTECTED_TAGS & {t.lower() for t in (tags or [])})


def usefulness(u: Usage) -> float:
    """0..1 from cite rate (50%), use rate (20%), thumbs (20% when any) and mean JEV score (10% when any)."""
    r = max(1, u.retrieved)
    parts = [(0.5, min(1.0, u.cited / r)), (0.2, min(1.0, u.used / r))]
    if u.up + u.down:
        parts.append((0.2, (u.up / (u.up + u.down))))
    if u.jev_avg is not None:
        parts.append((0.1, max(0.0, min(1.0, u.jev_avg))))
    w = sum(p for p, _ in parts)
    return sum(p * v for p, v in parts) / w


def plan_adjustment(*, base: float, current: float, protected: bool, usage: Optional[Usage], age_days: float,
                    telemetry_days: float, cfg: DreamSettings) -> Optional[Adjustment]:
    """Pure and explainable. Returns the new importance (rounded to 3 dp) or None for 'leave it alone'."""
    step = cfg.importance_max_step
    lo = max(IMPORTANCE_FLOOR, base - cfg.importance_max_drift)
    hi = min(1.0, base + cfg.importance_max_drift)
    if protected:
        lo = max(lo, min(base, 1.0))                       # protected cards never drop below their base
    target, reason, cold = current, "", False
    if usage is not None and usage.retrieved >= cfg.min_samples:
        score = usefulness(usage)
        used_never_cited = usage.retrieved >= 2 * cfg.min_samples and usage.used / usage.retrieved >= 0.5 and usage.cited == 0 and usage.up <= usage.down
        if used_never_cited:
            target, reason = max(lo, current - step), f"injected into {usage.used} of {usage.retrieved} answers but never cited"
        elif score >= 0.6:
            target, reason = min(hi, current + step), f"frequently cited (usefulness {score:.2f} over {usage.retrieved} retrievals)"
        elif score <= 0.1:
            target, reason = max(lo, current - step), f"retrieved {usage.retrieved}x but almost never used or cited (usefulness {score:.2f})"
        elif current > base:
            target, reason = max(base, current - step / 2), "usage normal: easing the boost back toward the base importance"
        elif current < base:
            target, reason = min(base, current + step / 2), "usage normal: easing the reduction back toward the base importance"
    elif (usage is None or usage.retrieved == 0) and telemetry_days >= cfg.decay_after_days and age_days >= cfg.decay_after_days \
            and base <= 0.5 and not protected:
        target, reason, cold = max(lo, current - step), f"never retrieved in {int(min(age_days, telemetry_days))}+ days", True
    target = round(max(IMPORTANCE_FLOOR, min(1.0, target)), 3)
    if abs(target - current) < 1e-6:
        return Adjustment(current, reason, cold) if cold and reason else None
    return Adjustment(target, reason, cold)


def _body(markdown: str) -> str:
    return " ".join(split_frontmatter(markdown)[1].lower().split())


def conflict_signal(a: str, b: str) -> Optional[str]:
    """Two cards that are about the same thing (high word overlap) but state different figures or opposite statuses."""
    wa, wb = set(_WORD.findall(a)), set(_WORD.findall(b))
    if not wa or not wb or len(wa & wb) / len(wa | wb) < 0.6:
        return None
    na, nb = set(_NUM.findall(a)), set(_NUM.findall(b))
    if na != nb:
        return f"different figures ({', '.join(sorted(na ^ nb)[:4])})"
    sa, sb = wa & STATUS_WORDS, wb & STATUS_WORDS
    if sa != sb:
        return f"different status words ({', '.join(sorted(sa ^ sb))})"
    return None


async def run(ctx: PhaseCtx) -> None:
    if not ctx.state.get("importance_done"):
        await _importance(ctx)
        ctx.state["importance_done"] = True
        await ctx.checkpoint()
    if not ctx.state.get("conflicts_done"):
        await _conflicts(ctx)
        ctx.state["conflicts_done"] = True
        await ctx.checkpoint()


async def _importance(ctx: PhaseCtx) -> None:
    cfg, deps, tenant, now = ctx.cfg, ctx.deps, ctx.tenant, ctx.now
    tel = await deps.ops.retrieval_telemetry(tenant, now - timedelta(days=cfg.telemetry_days))
    summary = {"telemetry": tel.available, "note": tel.note, "adjusted_up": 0, "adjusted_down": 0, "cold": 0, "skills_ranked": [], "top_cited": []}
    ctx.shared["relevance"] = summary
    if not tel.available:
        ctx.note(f"retrieval telemetry unavailable ({tel.note or 'no retrieval_log'}): importance left unchanged")
        return
    telemetry_days = (now - tel.observed_since).total_seconds() / 86400 if tel.observed_since else 0.0
    ranked = sorted(((k, u) for k, u in tel.usage.items()), key=lambda kv: (-kv[1].cited, -kv[1].retrieved, kv[0]))
    summary["top_cited"] = [{"source_type": k[0], "source_id": k[1], "cited": u.cited, "retrieved": u.retrieved} for k, u in ranked[:5] if u.cited]
    summary["skills_ranked"] = [{"source_id": k[1], "cited": u.cited, "retrieved": u.retrieved} for k, u in ranked if k[0] == "skill"][:5]
    await _judge_flags(ctx, tel)
    cursor, adjusted = None, 0
    while adjusted < cfg.max_adjustments:
        page = await deps.store.scan_cards(tenant, cursor, cfg.batch_size)
        if not page:
            break
        for ch in page:
            cursor = (ch.source_type, ch.source_id, ch.chunk_no)
            if ch.valid_to is not None or ch.visibility == "private" or ch.source_type == "memory_health":
                continue
            st = await deps.store.get_card_state(tenant, ch.source_type, ch.source_id) or {}
            ours = st.get("adjusted") is not None and abs(float(st["adjusted"]) - ch.importance) < 1e-3
            base = float(st["base"]) if ours and "base" in st else ch.importance
            ref = ch.updated_at or ch.as_of
            age = (now - (ref if ref.tzinfo else ref.replace(tzinfo=timezone.utc))).total_seconds() / 86400 if ref else 0.0
            adj = plan_adjustment(base=base, current=ch.importance, protected=is_protected(ch.module, ch.tags, base) or bool(st.get("keep")),
                                  usage=tel.usage.get((ch.source_type, ch.source_id)), age_days=age, telemetry_days=telemetry_days, cfg=cfg)
            if adj is None:
                continue
            adjusted += 1
            moved = adj.new != ch.importance
            if adj.new > ch.importance:
                summary["adjusted_up"] += 1
            elif adj.new < ch.importance:
                summary["adjusted_down"] += 1
            if adj.cold:
                summary["cold"] += 1
            if not ctx.dry_run:
                if moved:
                    await deps.store.kstore.set_importance(tenant, ch.source_type, ch.source_id, adj.new)
                    await deps.store.put_card_state(tenant, ch.source_type, ch.source_id,
                                                    {"base": base, "adjusted": adj.new, "reason": adj.reason, "at": now.isoformat()})
                await deps.store.tag_source(tenant, ch.source_type, ch.source_id, [COLD_TAG] if adj.cold else [], [] if adj.cold else [COLD_TAG])
            await ctx.finding(type="importance_adjusted" if moved else "cold_card", severity="info", source_type=ch.source_type,
                              source_id=ch.source_id, title=f"{'Importance' if moved else 'Priority'} of '{ch.title[:70]}': {ch.importance:.2f} -> {adj.new:.2f}",
                              detail={"before": ch.importance, "after": adj.new, "base": base, "reason": adj.reason, "max_step": cfg.importance_max_step,
                                      "protected": is_protected(ch.module, ch.tags, base) or bool(st.get("keep"))},
                              dedupe_key=f"imp:{ch.source_type}:{ch.source_id}", auto_applied=True,
                              action={"kind": "set_importance", "value": ch.importance})
            if adj.cold and adj.new <= 0.25 and len(ctx.shared.setdefault("adjudication_queue", [])) < 25:
                ctx.shared["adjudication_queue"].append({"kind": "keep_long_term", "source_type": ch.source_type, "source_id": ch.source_id})
            if adjusted >= cfg.max_adjustments:
                break
        await ctx.pause()
    ctx.counts.update({"importance_up": summary["adjusted_up"], "importance_down": summary["adjusted_down"], "cold_cards": summary["cold"]})


async def _judge_flags(ctx: PhaseCtx, tel) -> None:
    """Cards the JEV judge repeatedly found out of date at answer time: mark stale (reversible tag) and ask for a refresh."""
    for (st, sid), u in sorted(tel.usage.items()):
        if u.not_current < 3 or u.not_current / max(1, u.retrieved) < 0.5:
            continue
        chunks = await ctx.deps.store.get_chunks(ctx.tenant, st, sid)
        if not chunks or chunks[0].visibility == "private":
            continue
        if not ctx.dry_run:
            await ctx.deps.store.tag_source(ctx.tenant, st, sid, [STALE_TAG], [])
        ctx.inc("judge_flagged_stale")
        await ctx.finding(type="judge_flags_stale", severity="medium", source_type=st, source_id=sid,
                          title=f"The relevance judge found '{chunks[0].title[:70]}' out of date in {u.not_current} of {u.retrieved} answers",
                          detail={"not_current": u.not_current, "retrieved": u.retrieved}, dedupe_key=f"judge_stale:{st}:{sid}",
                          auto_applied=True, action={"kind": "refresh"})


async def _conflicts(ctx: PhaseCtx) -> None:
    cfg, deps, tenant = ctx.cfg, ctx.deps, ctx.tenant
    kstore = deps.store.kstore
    found = merged = 0
    for t in sorted((await deps.store.count_cards(tenant))["source_types"]):
        if t == "memory_health":
            continue
        for a, b, sim in await kstore.near_duplicates(tenant, t, cfg.conflict_cosine, 40):
            ca, cb = await deps.store.get_chunks(tenant, t, a), await deps.store.get_chunks(tenant, t, b)
            if not ca or not cb:
                continue
            ba, bb = _body(ca[0].markdown), _body(cb[0].markdown)
            key = f"{t}:{min(a, b)}:{max(a, b)}"
            if ba == bb:
                auto = t in cfg.auto_merge_identical_types
                if auto and not ctx.dry_run:
                    await actions.tombstone(deps, tenant, t, b)
                    merged += 1
                await ctx.finding(type="duplicate_identical", severity="low", source_type=t, source_id=b,
                                  title=f"Two '{t}' cards have identical text ('{cb[0].title[:60]}')",
                                  detail={"keep": a, "duplicate": b, "cosine": round(sim, 4), "auto_merged": auto and not ctx.dry_run},
                                  dedupe_key=f"dup:{key}", auto_applied=auto, action={"kind": "tombstone", "source_type": t, "source_id": b})
                continue
            why = conflict_signal(ba, bb)
            if why:
                found += 1
                await ctx.finding(type="conflict", severity="medium", source_type=t, source_id=a,
                                  title=f"Possible conflict between two '{t}' cards: {why}",
                                  detail={"a": {"id": a, "title": ca[0].title, "preview": actions.preview(ca[0].markdown, 200)},
                                          "b": {"id": b, "title": cb[0].title, "preview": actions.preview(cb[0].markdown, 200)},
                                          "cosine": round(sim, 4), "signal": why, "needs": "human review: decide which statement is right"},
                                  dedupe_key=f"conflict:{key}", action={"kind": "review"})
                q = ctx.shared.setdefault("adjudication_queue", [])
                if len(q) < 25:
                    q.append({"kind": "contradict", "source_type": t, "source_id": a, "other_id": b, "dedupe_key": f"conflict:{key}"})
    ctx.counts.update({"conflicts": found, "identical_merged": merged})
