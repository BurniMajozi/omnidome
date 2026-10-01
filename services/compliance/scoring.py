"""Compliance scoring rules (pure functions).

A category with no obligations is NOT assessed: its score is None, never 100 or
'exempt'. The overview uses only the LATEST snapshot per category and averages
over assessed categories; with none assessed the overall score is None.
"""

from __future__ import annotations

from typing import Iterable, Optional


def _val(x):
    return getattr(x, "value", x)


def score_category(statuses: Iterable) -> Optional[dict]:
    """statuses: the obligations' status values. None when there are none."""
    vals = [_val(s) for s in statuses]
    total = len(vals)
    if total == 0:
        return None
    compliant = sum(1 for v in vals if v == "compliant")
    non_compliant = sum(1 for v in vals if v == "non_compliant")
    at_risk = sum(1 for v in vals if v == "at_risk")
    score = compliant / total * 100
    status = "compliant" if score >= 90 else "at_risk" if score >= 70 else "non_compliant"
    return {"score": round(score, 2), "status": status, "issues": non_compliant + at_risk, "critical": non_compliant}


def latest_per_category(rows: Iterable) -> list:
    """rows: objects with .category and .calculated_at (any order). Newest per category."""
    best: dict = {}
    for r in rows:
        key = _val(r.category)
        cur = best.get(key)
        stamp = r.calculated_at
        if cur is None or (stamp is not None and (cur.calculated_at is None or stamp > cur.calculated_at)) \
                or (stamp == cur.calculated_at and getattr(r, "id", 0) > getattr(cur, "id", 0)):
            best[key] = r
    return list(best.values())


def overall_score(latest: Iterable) -> Optional[int]:
    scores = [float(r.score) for r in latest if r.score is not None]
    return round(sum(scores) / len(scores)) if scores else None
