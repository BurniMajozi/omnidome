"""Load a metric's ACTUAL history from tenant_metric_facts and turn it into a clean, gap-free series."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

import numpy as np
from sqlalchemy import text

from services.fno_intelligence import metric_catalog as mc

EMPTY_DIMS_HASH = hashlib.sha256(json.dumps({}, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()[:32]


class Skip(Exception):
    """Raised with the human-readable reason a metric produced no forecast (logged and recorded in the run summary)."""


@dataclass
class Series:
    metric: mc.Metric
    values: np.ndarray
    first_start: date
    last_start: date
    real_points: int


def _d(v) -> date:
    return v.date() if isinstance(v, datetime) else (v if isinstance(v, date) else date.fromisoformat(str(v)[:10]))


def load_actuals(conn, tenant: str, metric_key: str) -> list:
    """[(period_start, value)] ordered. Only kind='actual' with empty dimensions (the headline series)."""
    pg = conn.dialect.name == "postgresql"
    cond = "tenant_id = CAST(:t AS uuid)" if pg else "tenant_id = :t"
    rows = conn.execute(text(f"SELECT period_start, value FROM tenant_metric_facts WHERE {cond} AND metric_key = :k "
                             "AND kind = 'actual' AND dimensions_hash = :h ORDER BY period_start"),
                        {"t": tenant, "k": metric_key, "h": EMPTY_DIMS_HASH}).all()
    return [(_d(r[0]), float(r[1])) for r in rows]


def build_series(m: mc.Metric, actuals: list, today: date) -> Series:
    if not m.grain:
        raise Skip("not a time series metric")
    if not actuals:
        raise Skip("no actual facts yet (run a metric snapshot first)")
    by_start = {s: v for s, v in actuals}
    # leading zero run = the business/feature did not exist yet; counting it as history would fake the minimum
    if m.additive:
        for s in sorted(by_start):
            if by_start[s] != 0:
                break
            del by_start[s]
        if not by_start:
            raise Skip("all recorded actuals are zero")
    first, last = min(by_start), max(by_start)
    expected_last = mc.add_periods(mc.period_start_for(today, m.grain), m.grain, -1)
    if last < expected_last:
        raise Skip(f"history is stale: last actual period starts {last}, expected {expected_last}; run a metric snapshot first")
    idx, d = [], first
    while d <= last:
        idx.append(d)
        d = mc.next_period_start(d, m.grain)
    vals = np.array([by_start.get(d, np.nan) for d in idx], dtype=float)
    missing = np.isnan(vals)
    real = int((~missing).sum())
    if real < m.history_needed:
        raise Skip(f"only {real} usable periods; {m.history_needed} required for {m.grain} data")
    if missing.any():
        if m.additive:
            vals[missing] = 0.0
        else:
            xs = np.arange(len(vals))
            vals[missing] = np.interp(xs[missing], xs[~missing], vals[~missing])
    if float(np.abs(vals[-m.history_needed:]).sum()) == 0.0:
        raise Skip("no signal: the most recent history is all zero")
    return Series(m, vals, first, last, real)
