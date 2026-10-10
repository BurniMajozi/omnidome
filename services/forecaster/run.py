"""Forecast batch job (NOT an API).  Usage:

    python -m services.forecaster.run                       # every tenant that has actual metric facts, every forecastable metric
    python -m services.forecaster.run --tenant <uuid> --metric billing.revenue_invoiced.month --horizon 6
    python -m services.forecaster.run --pending             # execute queued rows from POST /api/fno/bi/forecast/runs
    python -m services.forecaster.run --dry-run             # compute and log, write nothing
    python -m services.forecaster.run --no-chronos          # force the numpy baselines

History comes from ACTUAL metric facts (written by fno_intelligence.bi_metrics_writer from governed queries).
Forecasts go back ONLY through tenant_memory's metric-facts API as kind='forecast', written_by='forecast_run'.
No LLM is involved; no model weights are downloaded (Chronos is used only if installed AND already on disk).
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import JSON, bindparam, create_engine, text
from sqlalchemy.engine.url import make_url

from services.fno_intelligence import metric_catalog as mc
from services.forecaster import chronos_adapter, history, selection
from services.forecaster.history import Skip

log = logging.getLogger("forecaster")
INTERVAL_LEVEL = 0.8


def today_local() -> date:
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Africa/Johannesburg")).date()
    except Exception:
        return (datetime.now(timezone.utc) + timedelta(hours=2)).date()


def build_facts(m: mc.Metric, series: history.Series, fc: selection.Forecast, *, as_of: datetime) -> list:
    """Forecast -> metric-fact dicts (one per future period), shaped for POST /api/v1/metrics/facts."""
    method = f"forecast:{fc.model_name}|smape={fc.smape:.1f}|mase={fc.mase:.2f}|n={fc.n_origins}"[:80]
    conf = round(max(0.0, min(1.0, 1.0 - fc.smape / 100.0)), 3)        # backtest accuracy proxy, not a probability
    spec = m.query_spec()
    out, start = [], mc.next_period_start(series.last_start, m.grain)
    for i in range(len(fc.point)):
        end = mc.period_end(start, m.grain)
        pt, lo, hi = round(float(fc.point[i]), 2), round(float(fc.lower[i]), 2), round(float(fc.upper[i]), 2)
        lo, hi = min(lo, pt), max(hi, pt)
        out.append({"metric_key": m.key, "label": m.label[:160], "dimensions": {}, "period_start": start.isoformat(),
                    "period_end": end.isoformat(), "grain": m.grain, "value": pt, "unit": m.unit, "kind": "forecast",
                    "lower_bound": lo, "upper_bound": hi, "interval_level": fc.level, "model_name": fc.model_name,
                    "model_version": fc.model_version, "method": method, "confidence": conf, "source_query": spec,
                    "as_of": as_of.isoformat(), "written_by": "forecast_run"})
        start = mc.next_period_start(start, m.grain)
    return out


def forecast_metric(conn, tenant: str, m: mc.Metric, *, horizon: Optional[int], today: date, foundation, as_of: datetime) -> list:
    if not (m.forecastable and m.shape == "series"):
        raise Skip("metric is not forecastable")
    series = history.build_series(m, history.load_actuals(conn, tenant, m.key), today)
    h = max(1, min(horizon or m.default_horizon, mc.MAX_HORIZON[m.grain]))
    fc = selection.forecast_series(series.values, h, m.season_length, level=INTERVAL_LEVEL, foundation=foundation,
                                   nonnegative=m.nonnegative)
    for note in fc.notes:
        log.warning("%s: %s", m.key, note)
    log.info("%s: %d points -> %s (mase %.2f, smape %.1f%%) h=%d", m.key, series.real_points, fc.model_name, fc.mase, fc.smape, h)
    return build_facts(m, series, fc, as_of=as_of)


def run_tenant(conn, tenant: str, sink, *, keys: Optional[list] = None, horizon: Optional[int] = None, today: Optional[date] = None,
               foundation=None, dry_run: bool = False) -> dict:
    today = today or today_local()
    as_of = datetime.now(timezone.utc)
    summary: dict = {}
    metrics = mc.select(keys) if keys else mc.forecastable()
    for m in metrics:
        try:
            facts = forecast_metric(conn, tenant, m, horizon=horizon, today=today, foundation=foundation, as_of=as_of)
            if not dry_run:
                for f in facts:
                    sink.write(tenant, f)
            summary[m.key] = {"status": "dry_run" if dry_run else "forecast", "facts": len(facts),
                              "model": facts[0]["model_name"], "method": facts[0]["method"]}
        except (Skip, selection.InsufficientHistory) as exc:
            log.info("%s: no forecast - %s", m.key, exc)
            summary[m.key] = {"status": "skipped", "reason": str(exc)}
        except Exception as exc:                                   # one bad metric/tenant must not stop the batch
            log.exception("%s: failed", m.key)
            summary[m.key] = {"status": "error", "error": f"{exc.__class__.__name__}: {exc}"[:200]}
    return summary


# ── engine / tenants / queued runs ───────────────────────────────────────────

def make_engine(url: Optional[str] = None):
    u = make_url(url or os.environ["DATABASE_URL"])
    if u.drivername.startswith("postgresql"):
        u = u.set(drivername="postgresql+psycopg2")
    return create_engine(u, pool_pre_ping=True)


def tenants_with_actuals(conn) -> list:
    return [str(uuid.UUID(str(r[0]))) for r in conn.execute(text("SELECT DISTINCT tenant_id FROM tenant_metric_facts WHERE kind = 'actual'"))]


def _uuid_sql(conn, name: str) -> str:
    return f"CAST(:{name} AS uuid)" if conn.dialect.name == "postgresql" else f":{name}"


def _id_param(conn, rid):
    return str(rid) if conn.dialect.name == "postgresql" else rid


def process_pending(engine, sink, *, foundation=None, today: Optional[date] = None, limit: int = 5, dry_run: bool = False) -> list:
    """Claim queued forecast_runs rows (oldest first) and execute them. Safe for concurrent runners (guarded UPDATE)."""
    done: list = []
    with engine.begin() as c:
        rows = c.execute(text("SELECT id, tenant_id, metric_keys, horizon FROM forecast_runs WHERE status = 'queued' "
                              "ORDER BY created_at LIMIT :n"), {"n": limit}).all()
    for rid, tenant, keys, horizon in rows:
        with engine.begin() as c:
            claimed = c.execute(text(f"UPDATE forecast_runs SET status = 'running', started_at = :now WHERE id = {_uuid_sql(c, 'id')} "
                                     "AND status = 'queued'"), {"id": _id_param(c, rid), "now": datetime.now(timezone.utc)}).rowcount
        if claimed != 1:
            continue
        keys = json.loads(keys) if isinstance(keys, str) else keys
        status, error, summary = "done", None, {}
        try:
            with engine.connect() as c:
                summary = run_tenant(c, str(uuid.UUID(str(tenant))), sink, keys=keys or None, horizon=horizon, today=today,
                                     foundation=foundation, dry_run=dry_run)
            if summary and all(v["status"] == "error" for v in summary.values()):
                status, error = "failed", "every metric failed"
        except Exception as exc:
            status, error = "failed", f"{exc.__class__.__name__}: {exc}"[:500]
        with engine.begin() as c:
            c.execute(text(f"UPDATE forecast_runs SET status = :s, error = :e, summary = :sum, finished_at = :now "
                           f"WHERE id = {_uuid_sql(c, 'id')}").bindparams(bindparam("sum", type_=JSON)),
                      {"s": status, "e": error, "sum": summary, "now": datetime.now(timezone.utc), "id": _id_param(c, rid)})
        done.append((str(rid), status))
    return done


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m services.forecaster.run", description="Forecast batch job")
    ap.add_argument("--tenant", help="tenant uuid (default: every tenant with actual facts)")
    ap.add_argument("--metric", action="append", help="metric key (repeatable; default: all forecastable)")
    ap.add_argument("--horizon", type=int, help="periods ahead (default: per-metric)")
    ap.add_argument("--pending", action="store_true", help="execute queued rows from the forecast_runs table, then exit")
    ap.add_argument("--dry-run", action="store_true", help="compute and log; write nothing")
    ap.add_argument("--no-chronos", action="store_true", help="skip the foundation model even if installed")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if a.no_chronos:
        os.environ["FORECAST_CHRONOS"] = "off"
    from services.forecaster.sink import HttpSink
    sink = HttpSink()
    if not a.dry_run and not sink.configured():
        log.error("TENANT_MEMORY_SERVICE_URL is not set; nothing can be written (use --dry-run to test)")
        return 2
    foundation = chronos_adapter.load()
    if foundation:
        log.info("model path: %s %s plus statistical baselines", foundation.name, foundation.version)
    else:
        log.info("model path: statistical baselines only (%s)", chronos_adapter.status()[1])
    engine = make_engine()
    if a.pending:
        res = process_pending(engine, sink, foundation=foundation, dry_run=a.dry_run)
        log.info("processed %d queued run(s): %s", len(res), res)
        return 0
    failed = 0
    with engine.connect() as c:
        tenants = [str(uuid.UUID(a.tenant))] if a.tenant else tenants_with_actuals(c)
        for t in tenants:
            s = run_tenant(c, t, sink, keys=a.metric, horizon=a.horizon, foundation=foundation, dry_run=a.dry_run)
            counts = {k: sum(1 for v in s.values() if v["status"] == k) for k in ("forecast", "dry_run", "skipped", "error")}
            failed += counts["error"]
            log.info("tenant %s: %s", t, counts)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
