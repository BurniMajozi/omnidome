"""Deterministic insight computation for Deck Studio narratives.

All arithmetic (period-over-period, share, trend, outliers) happens here, in code. Each insight carries a
`sentence` made ONLY of words and {{tokens}} (figures are resolved server-side later), plus the raw numbers
in `data` for audit/UI. The LLM may rephrase sentences but never computes or types a figure.
"""

from __future__ import annotations

import math
import statistics
from typing import Optional

MAX_INSIGHTS = 6


def _idx(cols: list[dict], cid: str) -> int:
    return [c["id"] for c in cols].index(cid)


def _num(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def trend_direction(values: list[float]) -> Optional[str]:
    """'up' | 'down' | 'flat' from the least-squares slope relative to the mean; None if < 3 points."""
    v = [x for x in values if _num(x)]
    if len(v) < 3:
        return None
    n = len(v)
    xm, ym = (n - 1) / 2, sum(v) / n
    den = sum((i - xm) ** 2 for i in range(n))
    slope = sum((i - xm) * (y - ym) for i, y in enumerate(v)) / den if den else 0.0
    scale = abs(ym) or max(abs(x) for x in v) or 1.0
    rel = slope * (n - 1) / scale  # total drift across the window relative to level
    return "flat" if abs(rel) < 0.05 else ("up" if rel > 0 else "down")


def outlier_rows(values: list[float], z: float = 2.0) -> list[int]:
    """Indexes whose z-score exceeds `z` (needs >= 5 points and non-zero spread)."""
    v = [x for x in values if _num(x)]
    if len(v) < 5 or len(v) != len(values):
        return []
    sd = statistics.pstdev(v)
    if sd == 0:
        return []
    mu = statistics.fmean(v)
    return [i for i, x in enumerate(v) if abs((x - mu) / sd) > z]


def compute_insights(alias: str, result: dict, *, max_items: int = MAX_INSIGHTS) -> list[dict]:
    cols = result.get("columns") or []
    rows = result.get("rows") or []
    measures = [c for c in cols if c.get("kind") == "measure"]
    if not measures or not rows:
        return []
    has_time = any(c.get("kind") == "time" for c in cols)
    out: list[dict] = []
    for mc in measures[:3]:
        m, label = mc["id"], mc["label"]
        mi = _idx(cols, m)
        vals = [r[mi] for r in rows]
        ref = f"{alias}.{m}"
        if has_time and len(rows) >= 2 and _num(vals[-1]) and _num(vals[-2]):
            last, prev = vals[-1], vals[-2]
            data = {"last": last, "prev": prev, "delta": last - prev}
            if prev:
                data["delta_pct"] = (last - prev) / abs(prev)
                word = "rose" if last > prev else "fell" if last < prev else "was unchanged"
                out.append({"kind": "period_over_period", "measure": m, "importance": abs(data["delta_pct"]) + 1, "data": data,
                            "sentence": f"{label} {word} to {{{{{ref}.last}}}} in {{{{{ref}.last.label}}}}, "
                                        f"{{{{{ref}.delta_pct}}}} against {{{{{ref}.prev}}}} in {{{{{ref}.prev.label}}}}."})
            else:
                out.append({"kind": "period_over_period", "measure": m, "importance": 1, "data": data,
                            "sentence": f"{label} was {{{{{ref}.last}}}} in {{{{{ref}.last.label}}}} after {{{{{ref}.prev}}}} the period before."})
        if has_time:
            d = trend_direction([v for v in vals if _num(v)])
            if d:
                phrase = {"up": "trended upward", "down": "trended downward", "flat": "was broadly flat"}[d]
                out.append({"kind": "trend", "measure": m, "importance": 0.6 if d != "flat" else 0.3, "data": {"direction": d},
                            "sentence": f"Across the period shown, {label} {phrase}."})
            for i in outlier_rows(vals)[:2]:
                if i < 99:
                    out.append({"kind": "outlier", "measure": m, "importance": 0.9, "data": {"row": i + 1, "value": vals[i]},
                                "sentence": f"{{{{{ref}.row{i + 1}.label}}}} stood out for {label} at {{{{{ref}.row{i + 1}.value}}}}."})
            continue
        if len(rows) >= 2 and mc.get("additive"):
            ranked = sorted((v for v in vals if _num(v)), reverse=True)
            total = (result.get("totals") or {}).get(m)
            if ranked and _num(total) and total:
                share = ranked[0] / total
                out.append({"kind": "top_share", "measure": m, "importance": 0.5 + share, "data": {"top": ranked[0], "share": share},
                            "sentence": f"{{{{{ref}.top1.label}}}} led on {label} with {{{{{ref}.top1.value}}}}, "
                                        f"{{{{{ref}.top1.share}}}} of the total."})
                if len(ranked) >= 3:
                    out.append({"kind": "bottom", "measure": m, "importance": 0.3, "data": {"bottom": ranked[-1]},
                                "sentence": f"{{{{{ref}.bottom1.label}}}} was lowest at {{{{{ref}.bottom1.value}}}}."})
        elif len(rows) >= 2:
            ranked = sorted((v for v in vals if _num(v)), reverse=True)
            if ranked:
                out.append({"kind": "extremes", "measure": m, "importance": 0.4, "data": {"max": ranked[0], "min": ranked[-1]},
                            "sentence": f"{label} ranged from {{{{{ref}.bottom1.value}}}} ({{{{{ref}.bottom1.label}}}}) "
                                        f"to {{{{{ref}.top1.value}}}} ({{{{{ref}.top1.label}}}})."})
        elif _num(vals[0]):
            out.append({"kind": "total", "measure": m, "importance": 0.2, "data": {"value": vals[0]},
                        "sentence": f"{label} stands at {{{{{ref}.total}}}}."})
    out.sort(key=lambda i: -i["importance"])
    return out[:max_items]
