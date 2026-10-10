"""Phase 3 - NUMBERS VALIDITY. No LLM touches a number here.

1. DATA DRIFT: snapshot the stored ACTUAL metric facts, ask the governed BI layer to recompute them (the existing
   `bi_semantic` queries via the snapshot endpoint), diff the values: a changed value for an already-closed period means
   the source data changed silently. Deltas are recorded with before/after.
2. FORECAST ACCURACY: score every past forecast against the actuals that have since arrived (sMAPE, MASE vs naive,
   interval coverage), write `meta.forecast_accuracy.*` facts (deterministic writer identity `system`) and flag models
   whose realised accuracy degraded versus their own backtest, so the forecaster can reselect.
3. CONTRADICTIONS: a metric_fact card that no longer matches its (changed) fact is refreshed, or marked stale.
"""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, timedelta
from typing import Optional

from services.tenant_memory.knowledge.dream import actions
from services.tenant_memory.knowledge.dream.context import PhaseCtx
from services.tenant_memory.knowledge.dream.store import STALE_TAG
from services.tenant_memory.knowledge.metrics import MetricFactIn

ACCURACY_PREFIX = "meta.forecast_accuracy."


# ── pure maths ──────────────────────────────────────────────────────────────

def smape(actual: float, forecast: float) -> float:
    """Symmetric MAPE in percent (0..200). Both zero -> 0."""
    d = abs(actual) + abs(forecast)
    return 0.0 if d == 0 else 200.0 * abs(actual - forecast) / d


def mase(errors_abs: list[float], history: list[float]) -> Optional[float]:
    """Mean absolute error scaled by the in-sample one-step naive error of the actuals; None without a usable scale."""
    if not errors_abs or len(history) < 3:
        return None
    scale = sum(abs(history[i] - history[i - 1]) for i in range(1, len(history))) / (len(history) - 1)
    if scale <= 1e-12:
        return None
    return (sum(errors_abs) / len(errors_abs)) / scale


def parse_method(method: Optional[str]) -> dict:
    """'forecast:<model>|smape=8.2|mase=0.71|n=6' -> {'smape': 8.2, 'mase': 0.71, 'n': 6.0}"""
    out: dict = {}
    for part in (method or "").split("|")[1:]:
        k, _, v = part.partition("=")
        try:
            out[k.strip()] = float(v)
        except ValueError:
            continue
    return out


def _key(f: dict) -> tuple:
    return (f["metric_key"], f["dimensions_hash"], f["period_start"], f["period_end"])


def detect_metric_drift(before: list[dict], after: list[dict], tol: float) -> list[dict]:
    """Facts present in both snapshots whose value moved by more than `tol` (relative, absolute floor 1e-9)."""
    prev = {_key(f): f for f in before}
    out = []
    for f in after:
        p = prev.get(_key(f))
        if p is None:
            continue
        a, b = float(p["value"]), float(f["value"])
        base = max(abs(a), 1e-9)
        rel = abs(b - a) / base
        if abs(b - a) > 1e-9 and rel > tol:
            out.append({"id": f.get("id"), "metric_key": f["metric_key"], "period_start": str(f["period_start"]),
                        "period_end": str(f["period_end"]), "before": a, "after": b, "rel_change": round(rel, 6)})
    out.sort(key=lambda d: (-d["rel_change"], d["metric_key"], d["period_start"]))
    return out


def score_forecasts(facts: list[dict], today: date) -> list[dict]:
    """One result per (series, model_version) with at least one closed period that now has an actual."""
    actuals: dict[tuple, dict] = {}
    series_vals: dict[tuple, list] = defaultdict(list)
    for f in facts:
        if f["kind"] == "actual" and f.get("written_by") == "bi_semantic" and not f["metric_key"].startswith("meta."):
            actuals[_key(f)] = f
            series_vals[(f["metric_key"], f["dimensions_hash"])].append((f["period_start"], float(f["value"])))
    groups: dict[tuple, list] = defaultdict(list)
    for f in facts:
        if f["kind"] != "forecast" or f["period_end"] >= today:
            continue
        a = actuals.get(_key(f))
        if a is not None:
            groups[(f["metric_key"], f["dimensions_hash"], f.get("model_name") or "", f.get("model_version") or "")].append((f, a))
    out = []
    for (mk, dh, mn, mv), pairs in sorted(groups.items(), key=lambda kv: kv[0]):
        sm = [smape(float(a["value"]), float(f["value"])) for f, a in pairs]
        abs_err = [abs(float(a["value"]) - float(f["value"])) for f, a in pairs]
        hist = [v for _, v in sorted(series_vals[(mk, dh)])]
        bounded = [(f, a) for f, a in pairs if f.get("lower_bound") is not None and f.get("upper_bound") is not None]
        cover = (sum(1 for f, a in bounded if float(f["lower_bound"]) <= float(a["value"]) <= float(f["upper_bound"])) / len(bounded)) if bounded else None
        newest = max(pairs, key=lambda p: p[0].get("as_of") or p[0]["period_end"])[0]
        out.append({"metric_key": mk, "dimensions_hash": dh, "model_name": mn, "model_version": mv, "n": len(pairs),
                    "smape": round(sum(sm) / len(sm), 3), "mase": (round(m, 3) if (m := mase(abs_err, hist)) is not None else None),
                    "coverage": round(cover, 3) if cover is not None else None,
                    "interval_level": (bounded[0][0].get("interval_level") if bounded else None),
                    "backtest": parse_method(newest.get("method")), "period_start": min(f["period_start"] for f, _ in pairs),
                    "period_end": max(f["period_end"] for f, _ in pairs), "dimensions": newest.get("dimensions") or {}})
    return out


def degraded_reasons(s: dict) -> list[str]:
    reasons = []
    base = (s.get("backtest") or {}).get("smape")
    if s["n"] >= 2 and base is not None and s["smape"] > max(2 * base, base + 10):
        reasons.append(f"realised sMAPE {s['smape']:.1f}% vs backtest {base:.1f}%")
    if s["n"] >= 3 and s.get("mase") is not None and s["mase"] > 1.5:
        reasons.append(f"worse than a naive forecast (MASE {s['mase']:.2f})")
    lvl = s.get("interval_level")
    if s["n"] >= 4 and s.get("coverage") is not None and lvl and s["coverage"] < float(lvl) - 0.30:
        reasons.append(f"interval coverage {s['coverage']:.0%} vs nominal {float(lvl):.0%}")
    return reasons


# ── phase ───────────────────────────────────────────────────────────────────

async def run(ctx: PhaseCtx) -> None:
    deps, cfg, tenant = ctx.deps, ctx.cfg, ctx.tenant
    today = ctx.now.date()
    horizon = today - timedelta(days=max(cfg.metric_lookback_days, 200))
    drift_from = today - timedelta(days=cfg.metric_lookback_days)
    before = await deps.ops.metric_facts(tenant, horizon)
    after, refreshed = before, False
    if ctx.dry_run:
        ctx.note("dry run: the governed metric snapshot was not re-run; stored facts only")
    elif deps.metrics is None or not deps.metrics.configured():
        ctx.note("metric refresher not configured (FNO_INTELLIGENCE_SERVICE_URL): no data-drift check tonight")
    else:
        try:
            await deps.metrics.refresh(tenant, max(3, cfg.metric_lookback_days // 30 + 1))
            after, refreshed = await deps.ops.metric_facts(tenant, horizon), True
        except Exception as exc:  # noqa: BLE001
            ctx.error("metric snapshot refresh", exc)
            ctx.note("governed metric snapshot failed; comparing stored facts only")
    actual_b = [f for f in before if f["kind"] == "actual" and f.get("written_by") == "bi_semantic" and f["period_end"] >= drift_from]
    actual_a = [f for f in after if f["kind"] == "actual" and f.get("written_by") == "bi_semantic" and f["period_end"] >= drift_from]
    ctx.counts["actual_facts_checked"] = len(actual_a)
    drifted = detect_metric_drift(actual_b, actual_a, cfg.metric_tolerance) if refreshed else []
    ctx.counts["metric_drift"] = len(drifted)
    ctx.shared["metrics"] = {"checked": len(actual_a), "drifted": len(drifted), "refreshed": refreshed}
    by_metric: dict[str, list] = defaultdict(list)
    for d in drifted:
        by_metric[d["metric_key"]].append(d)
    for mk, items in sorted(by_metric.items()):
        worst = items[0]["rel_change"]
        await ctx.finding(
            type="metric_drift", severity="high" if worst > 0.10 else "medium" if worst > 0.02 else "low",
            title=f"Source data changed for closed periods of {mk}: {len(items)} value(s) moved (largest {worst:.1%})",
            detail={"metric_key": mk, "count": len(items), "changes": items[:8], "tolerance": cfg.metric_tolerance,
                    "note": "the actual facts were rewritten in place by the governed snapshot; before/after are listed here"},
            dedupe_key=f"metric_drift:{mk}", action={"kind": "none"}, auto_applied=True)
    await _contradictions(ctx, drifted)
    await _forecasts(ctx, after, today)


async def _contradictions(ctx: PhaseCtx, drifted: list[dict]) -> None:
    deps, tenant = ctx.deps, ctx.tenant
    for d in drifted[:50]:
        fid = d.get("id")
        if not fid:
            continue
        stored = await actions.stored_hashes(deps, tenant, "metric_fact", str(fid))
        if not stored:
            continue                                  # that fact has no card (yet)
        r = await deps.renderer.render(tenant, "metric_fact", str(fid))
        if r.status == "ok" and r.card is not None and actions.card_hashes(deps, tenant, r.card) != stored:
            ctx.inc("card_contradictions")
            chunks = await deps.store.get_chunks(tenant, "metric_fact", str(fid))
            before_md = chunks[0].markdown if chunks else ""
            if not ctx.dry_run:
                await deps.indexer.index_cards(tenant, [r.card])
            await ctx.finding(type="card_contradicts_fact", severity="medium", source_type="metric_fact", source_id=str(fid),
                              title=f"Card for {d['metric_key']} {d['period_start']} stated an out-of-date figure - refreshed",
                              detail={"before": actions.preview(before_md, 200), "after": actions.preview(r.card.markdown, 200),
                                      "fact_before": d["before"], "fact_after": d["after"]}, auto_applied=True, action={"kind": "refresh"})
        elif r.status in ("unverifiable", "source_missing") and not ctx.dry_run:
            await deps.store.tag_source(tenant, "metric_fact", str(fid), [STALE_TAG], [])
            ctx.inc("card_marked_stale")


async def _forecasts(ctx: PhaseCtx, facts: list[dict], today: date) -> None:
    scored = score_forecasts(facts, today)
    ctx.counts["forecast_series_scored"] = len(scored)
    if not scored:
        ctx.note("no past forecasts have a matching actual yet; nothing to score")
        ctx.shared["forecast"] = {"series_scored": 0, "degraded": 0, "mean_smape": None, "mean_coverage": None}
        return
    degraded = 0
    for s in scored:
        reasons = degraded_reasons(s)
        s["degraded"] = bool(reasons)
        degraded += bool(reasons)
        if not ctx.dry_run:
            await _write_accuracy_fact(ctx, s, reasons)
        if reasons:
            worst = s["smape"] > 50 or (s.get("mase") or 0) > 3
            await ctx.finding(
                type="forecast_degraded", severity="high" if worst else "medium",
                title=f"Forecast model {s['model_name'] or '?'} ({s['model_version'] or '?'}) is performing worse than expected on {s['metric_key']}",
                detail={"reasons": reasons, "scored_periods": s["n"], "smape": s["smape"], "mase": s["mase"], "coverage": s["coverage"],
                        "backtest": s["backtest"], "suggestion": "rerun the forecaster for this metric so it can reselect a model"},
                dedupe_key=f"forecast_degraded:{s['metric_key']}:{s['model_version']}", action={"kind": "none"})
    smapes = [s["smape"] for s in scored]
    covs = [s["coverage"] for s in scored if s["coverage"] is not None]
    ctx.counts["forecast_degraded"] = degraded
    ctx.shared["forecast"] = {"series_scored": len(scored), "degraded": degraded, "mean_smape": round(sum(smapes) / len(smapes), 2),
                              "mean_coverage": round(sum(covs) / len(covs), 3) if covs else None}


async def _write_accuracy_fact(ctx: PhaseCtx, s: dict, reasons: list[str]) -> None:
    key = re.sub(r"[^a-z0-9_.]", "_", (ACCURACY_PREFIX + s["metric_key"]).lower())[:118]
    na = lambda v: "na" if v is None else f"{v:.2f}"  # noqa: E731
    method = f"dream:fcacc|smape={s['smape']:.2f}|mase={na(s['mase'])}|cov={na(s['coverage'])}|n={s['n']}|deg={int(bool(reasons))}"
    try:
        await ctx.deps.ops.write_fact(ctx.tenant, MetricFactIn(
            metric_key=key, label=f"Forecast accuracy (sMAPE %) - {s['metric_key']}",
            dimensions={"model": s["model_name"], "version": s["model_version"], "series": s["dimensions_hash"]},
            period_start=s["period_start"], period_end=s["period_end"], value=float(s["smape"]), unit="pct", kind="actual",
            method=method[:80], confidence=max(0.0, min(1.0, 1 - s["smape"] / 100)), as_of=ctx.now, written_by="system"))
        ctx.inc("accuracy_facts_written")
    except Exception as exc:  # noqa: BLE001
        ctx.error("write accuracy fact", exc)
