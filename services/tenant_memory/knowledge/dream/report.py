"""Phase 7 - REPORT: the nightly memory health report (dream_runs.report + a knowledge card agents can retrieve).

`build_report` and `health_score` and `render_card` are pure so the output is deterministic for the same inputs.
The card (source_type `memory_health`, source_id `latest`, module `memory`) is visible to tenant admins only.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from services.tenant_memory.knowledge.cards.base import Card, frontmatter
from services.tenant_memory.knowledge.dream.context import PhaseCtx
from services.tenant_memory.knowledge.dream.store import OPEN_STATES
from services.tenant_memory.knowledge.indexer import EmbeddingBlocked
from services.tenant_memory.knowledge.kdata import ADMIN_ROLES


def _c(run: dict, phase: str) -> dict:
    return ((run.get("phase_results") or {}).get(phase) or {}).get("counts") or {}


def health_score(r: dict) -> int:
    """0..100, deterministic. Penalties are capped per component so one bad area cannot zero the score alone."""
    pen = 0.0
    canary = (r.get("canary") or {}).get("recall_at_3")
    pen += (1.0 - canary) * 30 if canary is not None else 5.0
    cards = r.get("cards") or {}
    pen += min(20.0, cards.get("stale", 0) / max(1, cards.get("live_sources", 0)) * 40)
    emb = r.get("embeddings") or {}
    pen += min(15.0, (emb.get("invalid", 0) / max(1, emb.get("scanned", 0))) * 300)
    sev = (r.get("findings") or {}).get("open_by_severity") or {}
    pen += min(15.0, sev.get("critical", 0) * 8 + sev.get("high", 0) * 4 + sev.get("medium", 0) * 1)
    m = r.get("metrics") or {}
    pen += min(10.0, (m.get("drifted", 0) / max(1, m.get("checked", 0))) * 50)
    pen += min(5.0, (r.get("forecast") or {}).get("degraded", 0) * 2)
    pen += min(10.0, len(r.get("errors") or []) * 2)
    return int(max(0, min(100, round(100 - pen))))


def health_label(score: int) -> str:
    return "excellent" if score >= 90 else "good" if score >= 75 else "fair" if score >= 60 else "needs attention"


def build_report(run: dict, shared: dict, card_counts: dict, finding_counts: dict, *, jev_enabled: bool, run_date: str) -> dict:
    d, e, n, rel = _c(run, "drift"), _c(run, "embeddings"), _c(run, "numbers"), _c(run, "relevance")
    errors = []
    for ph, res in sorted((run.get("phase_results") or {}).items()):
        errors += [f"{ph}: {x}" for x in (res.get("errors") or [])]
        if res.get("status") == "error":
            errors.append(f"{ph}: phase failed - {res.get('error', '')}")
    jev = shared.get("jev") or {}
    r = {
        "run_date": run_date, "dry_run": bool(run.get("dry_run")),
        "cards": {"live_chunks": card_counts.get("live_chunks", 0), "live_sources": card_counts.get("live_sources", 0),
                  "stale": card_counts.get("stale_tagged", 0), "tombstoned": card_counts.get("tombstoned", 0),
                  "models": card_counts.get("models", {})},
        "drift": {k: d.get(k, 0) for k in ("rendered", "verified", "content_drift", "refreshed", "vanished", "unverifiable", "stale_marked",
                                           "stale_cleared", "orphan_edge_origins", "dangling_edges")},
        "embeddings": {"scanned": e.get("scanned", 0), "invalid": e.get("vec_missing", 0) + e.get("vec_invalid", 0) + e.get("vec_outlier", 0),
                       "bad_dim": e.get("vec_bad_dim", 0), "model_mismatch": e.get("vec_model_mismatch", 0), "reembedded": e.get("reembedded", 0),
                       "collapsed_pairs": e.get("vec_dup_collapsed", 0), "semantic_drift": e.get("semantic_drift", 0)},
        "canary": shared.get("canary") or {"n": 0, "recall_at_3": None, "misses": []},
        "metrics": shared.get("metrics") or {"checked": n.get("actual_facts_checked", 0), "drifted": n.get("metric_drift", 0), "refreshed": False},
        "forecast": shared.get("forecast") or {"series_scored": 0, "degraded": 0, "mean_smape": None, "mean_coverage": None},
        "relevance": {"importance_up": rel.get("importance_up", 0), "importance_down": rel.get("importance_down", 0), "cold": rel.get("cold_cards", 0),
                      "conflicts": rel.get("conflicts", 0), "identical_merged": rel.get("identical_merged", 0),
                      "telemetry": (shared.get("relevance") or {}).get("telemetry"),
                      "skills_ranked": (shared.get("relevance") or {}).get("skills_ranked", [])},
        "consolidation": shared.get("consolidation") or {},
        "jev": {"enabled": jev_enabled, "calls": jev.get("calls", 0), "cost_usd": round(float(jev.get("cost_usd", 0.0)), 4), "cached": jev.get("cached", 0),
                "decided": jev.get("decided", 0), "queued_for_review": jev.get("queued_for_review", 0)},
        "findings": {"open_by_severity": finding_counts.get("open", {}), "total_open": finding_counts.get("total_open", 0)},
        "errors": errors[:30],
    }
    r["health_score"] = health_score(r)
    r["health_label"] = health_label(r["health_score"])
    return r


def render_card(report: dict) -> Card:
    """Deterministic: the same report always yields the same markdown (no wall-clock reads)."""
    r, day = report, report["run_date"]
    as_of = datetime.fromisoformat(day).replace(tzinfo=timezone.utc)
    c, canary, jev, rel = r["cards"], r["canary"], r["jev"], r["relevance"]
    recall = "not measured" if canary.get("recall_at_3") is None else f"{canary['recall_at_3']:.0%} ({canary.get('hits', 0)}/{canary.get('n', 0)} important cards found themselves in the top 3)"
    sev = r["findings"]["open_by_severity"]
    lines = [
        f"# Memory health report {day}", "",
        f"Overall health: {r['health_score']}/100 ({r['health_label']}).", "",
        "## Cards", f"- {c['live_sources']} indexed sources ({c['live_chunks']} chunks); {c['stale']} marked stale; {c['tombstoned']} tombstoned.",
        f"- Verified against live source tonight: {r['drift']['verified']} of {r['drift']['rendered']} re-rendered; refreshed after drift: {r['drift']['refreshed']}; "
        f"vanished at the source: {r['drift']['vanished']}; could not be verified: {r['drift']['unverifiable']}.", "",
        "## Embeddings and retrieval",
        f"- Vectors scanned {r['embeddings']['scanned']}: invalid {r['embeddings']['invalid']}, wrong model {r['embeddings']['model_mismatch']}, re-embedded {r['embeddings']['reembedded']}.",
        f"- Retrieval self-test recall@3: {recall}.", "",
        "## Numbers",
        f"- Actual metric facts checked {r['metrics'].get('checked', 0)}; silently changed in the source data: {r['metrics'].get('drifted', 0)}.",
        f"- Forecast series scored {r['forecast'].get('series_scored', 0)}; degraded models: {r['forecast'].get('degraded', 0)}"
        + (f"; mean sMAPE {r['forecast']['mean_smape']}%." if r['forecast'].get('mean_smape') is not None else "."), "",
        "## Relevance and priority",
        f"- Importance raised on {rel['importance_up']} cards, lowered on {rel['importance_down']}; cold (never retrieved) {rel['cold']}; conflicts for review {rel['conflicts']}.", "",
        "## Open findings",
        "- " + (", ".join(f"{k}: {sev[k]}" for k in ("critical", "high", "medium", "low", "info") if sev.get(k)) or "none"), "",
        "## JEV (external evaluator)",
        f"- {'on' if jev['enabled'] else 'off'}; calls {jev['calls']}, cost ${jev['cost_usd']}, cached {jev['cached']}, decided {jev['decided']}, left for human review {jev['queued_for_review']}.",
    ]
    if r["errors"]:
        lines += ["", "## Errors", *[f"- {e}" for e in r["errors"][:8]]]
    md = frontmatter("memory_health", "latest", "memory", as_of, ["memory", "health", "dream"]) + "\n".join(lines) + "\n"
    return Card("memory_health", "latest", "memory", f"Memory health report {day}", md, as_of, ["memory", "health", "dream"], importance=0.6,
                source_ref={"deep_link": "/dashboard/admin/agents"}, visibility="team", required_roles=sorted(ADMIN_ROLES))


async def run(ctx: PhaseCtx) -> None:
    deps, tenant = ctx.deps, ctx.tenant
    counts = await deps.store.count_cards(tenant)
    fc = await deps.store.finding_counts(tenant)
    report = build_report(ctx.run, ctx.shared, counts, fc, jev_enabled=bool(ctx.cfg.jev_enabled), run_date=ctx.run["run_date"])
    ctx.shared["report"] = report
    ctx.counts["health_score"] = report["health_score"]
    if ctx.dry_run:
        ctx.note("dry run: the health card was not written")
        return
    try:
        await deps.indexer.index_cards(tenant, [render_card(report)])
        ctx.counts["card_written"] = 1
    except EmbeddingBlocked as exc:
        ctx.error("health card", exc)
    except Exception as exc:  # noqa: BLE001
        ctx.error("health card", exc)
    await _notify(ctx, report)


async def _notify(ctx: PhaseCtx, report: dict) -> None:
    fresh = [f for f in await ctx.deps.store.list_findings(ctx.tenant, run_id=ctx.run["id"], limit=300)
             if f["severity"] in ("high", "critical") and f["status"] in OPEN_STATES and int(f.get("occurrences", 1)) <= 1]
    if not fresh and report["health_score"] >= 60:
        return
    crit = any(f["severity"] == "critical" for f in fresh) or report["health_score"] < 40
    first = fresh[0]["title"] if fresh else "overall memory health is low"
    try:
        await ctx.deps.ops.notify(ctx.tenant, f"Memory health: {len(fresh)} important finding(s), score {report['health_score']}/100",
                                  f"{first}. Open Agent Management > Memory > Dream state to review.",
                                  "critical" if crit else "warning", "/dashboard/admin/agents")
        ctx.inc("notified")
    except Exception as exc:  # noqa: BLE001
        ctx.error("notify", exc)
