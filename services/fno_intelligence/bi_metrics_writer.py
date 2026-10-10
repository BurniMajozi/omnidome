"""Deterministic metric-fact writer for the BI layer.

Runs governed bi_semantic queries for catalogued metrics (metric_catalog.py) and writes the results as ACTUAL
metric facts (written_by='bi_semantic', method='semantic_query') to the tenant_memory metric-facts API. No LLM is
involved anywhere in this module; the only inputs are governed query results.

Entry points
  snapshot_metrics(...)            explicit run (admin endpoint + daily scheduler)
  maybe_record_after_query(...)    best-effort hook called by bi_semantic.run_query (never raises, rate limited)
  run_metrics_scheduler()          env-gated daily snapshot loop (tenant-sequential, small batches)

Idempotency: a fact's identity is (tenant, metric_key, dimensions, period_start, period_end, kind, model_version);
re-running updates the same row (upsert in tenant_memory), so repeated snapshots/hook calls never duplicate.
Only COMPLETE periods are written for series (a half-finished month would be a misleading "actual").

Env
  TENANT_MEMORY_SERVICE_URL        where to POST facts (unset => writer disabled, hook/scheduler no-op)
  BI_METRICS_SNAPSHOT_ENABLED      daily snapshot loop, default true
  BI_METRICS_SNAPSHOT_HOUR         local (Africa/Johannesburg) hour after which the daily run happens, default 2
  BI_METRICS_TENANT_PAUSE_S        pause between tenants, default 3
  BI_METRICS_METRIC_PAUSE_S        pause between metrics, default 0.2
  BI_METRIC_HOOK_ENABLED           record facts when a catalogued query runs, default true
  BI_METRIC_HOOK_MIN_INTERVAL_S    per (tenant, metric) hook refresh interval, default 900
  METRICS_SYSTEM_USER_ID           identity used for the signed service call
"""
from __future__ import annotations

import asyncio
import logging
import os
import time as _time
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional, Protocol

import httpx

from services.fno_intelligence import metric_catalog as mc

logger = logging.getLogger("fno_intelligence.bi_metrics")

WRITTEN_BY = "bi_semantic"
METHOD = "semantic_query"
SYSTEM_USER_DEFAULT = "00000000-0000-4000-8000-0000000000f1"


class SinkError(RuntimeError):
    pass


class FactSink(Protocol):
    def configured(self) -> bool: ...
    async def write(self, tenant: uuid.UUID, fact: dict) -> dict: ...


class HttpFactSink:
    """POSTs a fact to tenant_memory `/api/v1/metrics/facts`. The identity headers are signed on the way out by
    services.common.internal_auth (installed on httpx when services.common.auth is imported); tenant_memory then
    requires the `metrics.write` permission, which this service identity carries and agents/LLM tools do not."""

    def __init__(self, base_url: Optional[str] = None, client: Optional[httpx.AsyncClient] = None):
        self._base = (base_url if base_url is not None else os.getenv("TENANT_MEMORY_SERVICE_URL", "")).rstrip("/")
        self._client = client

    def configured(self) -> bool:
        return bool(self._base)

    def _headers(self, tenant: uuid.UUID) -> dict:
        return {"X-Tenant-Id": str(tenant), "X-User-Id": os.getenv("METRICS_SYSTEM_USER_ID", SYSTEM_USER_DEFAULT),
                "X-Roles": "service", "X-Permissions": "metrics.write"}

    async def write(self, tenant: uuid.UUID, fact: dict) -> dict:
        url = f"{self._base}/api/v1/metrics/facts"
        try:
            if self._client is not None:
                r = await self._client.post(url, json=fact, headers=self._headers(tenant))
            else:
                async with httpx.AsyncClient(timeout=15.0) as c:
                    r = await c.post(url, json=fact, headers=self._headers(tenant))
        except httpx.HTTPError as exc:
            raise SinkError(f"metric-facts API unreachable: {exc.__class__.__name__}") from exc
        if r.status_code >= 300:
            raise SinkError(f"metric-facts API {r.status_code}: {r.text[:200]}")
        return r.json() if r.content else {}


_sink: Optional[FactSink] = None


def get_sink() -> FactSink:
    return _sink if _sink is not None else HttpFactSink()


def set_sink(sink: Optional[FactSink]) -> None:
    """Tests (and alternative deployments) inject a sink here; None restores the HTTP default."""
    global _sink
    _sink = sink


# ── time helpers ──────────────────────────────────────────────────────────────

def local_today() -> date:
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Africa/Johannesburg")).date()
    except Exception:  # tzdata missing (Windows/slim images): SAST is a fixed UTC+2
        return (datetime.now(timezone.utc) + timedelta(hours=2)).date()


def _parse_day(v: Any) -> Optional[date]:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


# ── result -> facts (pure) ────────────────────────────────────────────────────

def _base_fact(m: mc.Metric, spec: dict, as_of: datetime) -> dict:
    return {"metric_key": m.key, "label": m.label[:160], "unit": m.unit, "kind": "actual", "method": METHOD,
            "source_query": spec, "as_of": as_of.isoformat(), "written_by": WRITTEN_BY}


def _col_index(columns: list, kind: str, id_: Optional[str] = None) -> Optional[int]:
    for i, c in enumerate(columns):
        if c.get("kind") == kind and (id_ is None or c.get("id") == id_):
            return i
    return None


def facts_from_series(m: mc.Metric, columns: list, rows: list, *, spec: dict, today: date,
                      date_from: Optional[date] = None, date_to: Optional[date] = None,
                      as_of: Optional[datetime] = None) -> list:
    """Series result -> actual facts for COMPLETE periods inside the requested window. Additive measures are
    zero-filled between the first and last bucket seen (a month without events is a real 0); averages are not."""
    ti, vi = _col_index(columns, "time"), _col_index(columns, "measure", m.measure)
    if ti is None or vi is None or not m.grain:
        return []
    values: dict[date, float] = {}
    for r in rows:
        start, v = _parse_day(r[ti]), r[vi]
        if start is None or v is None:
            continue
        try:
            values[start] = float(v)
        except (TypeError, ValueError):
            continue
    if not values:
        return []
    if m.additive:
        d, last = min(values), max(values)
        while d <= last:
            values.setdefault(d, 0.0)
            d = mc.next_period_start(d, m.grain)
    as_of = as_of or datetime.now(timezone.utc)
    out = []
    for start in sorted(values):
        end = mc.period_end(start, m.grain)
        if end >= today:                                   # period still in progress
            continue
        if date_from and start < date_from or date_to and end > date_to:
            continue                                       # partially outside the requested window
        f = _base_fact(m, spec, as_of)
        f.update(dimensions={}, period_start=start.isoformat(), period_end=end.isoformat(), grain=m.grain,
                 value=max(values[start], 0.0) if m.nonnegative else values[start])
        out.append(f)
    return out


def facts_from_snapshot(m: mc.Metric, columns: list, rows: list, *, spec: dict, today: date,
                        as_of: Optional[datetime] = None) -> list:
    vi = _col_index(columns, "measure", m.measure)
    dim_idx = [(i, c["id"]) for i, c in enumerate(columns) if c.get("kind") == "dimension"]
    if vi is None:
        return []
    as_of = as_of or datetime.now(timezone.utc)
    out = []
    for r in rows:
        if r[vi] is None:
            continue
        f = _base_fact(m, spec, as_of)
        f.update(dimensions={name: str(r[i]) for i, name in dim_idx}, period_start=today.isoformat(),
                 period_end=today.isoformat(), grain="day", value=float(r[vi]))
        out.append(f)
    return out


def facts_from_result(m: mc.Metric, result: dict, *, spec: dict, today: date, date_from: Optional[date] = None,
                      date_to: Optional[date] = None) -> list:
    if result.get("meta", {}).get("truncated"):
        return []
    if m.shape == "snapshot":
        return facts_from_snapshot(m, result["columns"], result["rows"], spec=spec, today=today)
    return facts_from_series(m, result["columns"], result["rows"], spec=spec, today=today, date_from=date_from, date_to=date_to)


# ── explicit snapshot ─────────────────────────────────────────────────────────

def _env_float(key: str, default: float) -> float:
    try:
        return max(0.0, float(os.getenv(key, default)))
    except ValueError:
        return default


async def snapshot_metrics(db, tenant_id: uuid.UUID, keys: Optional[list] = None, periods: Optional[int] = None, *,
                           sink: Optional[FactSink] = None, today: Optional[date] = None,
                           pause_s: Optional[float] = None) -> dict:
    """Run the governed query for each catalogued metric and upsert ACTUAL facts. One failing metric never stops
    the others. Returns {metric_key: {facts, inserted, updated, error?}}."""
    from services.fno_intelligence import bi_semantic as sem        # late: keeps the catalog/forecaster import light

    sink = sink or get_sink()
    if not sink.configured():
        raise SinkError("TENANT_MEMORY_SERVICE_URL is not configured; metric facts cannot be written")
    today = today or local_today()
    pause = _env_float("BI_METRICS_METRIC_PAUSE_S", 0.2) if pause_s is None else pause_s
    summary: dict[str, dict] = {}
    for m in mc.select(keys):
        res: dict[str, Any] = {"facts": 0, "inserted": 0, "updated": 0}
        summary[m.key] = res
        try:
            n = max(1, min(int(periods or mc.DEFAULT_PERIODS.get(m.grain or "", 36)), 240))
            if m.shape == "series":
                date_from = mc.add_periods(mc.period_start_for(today, m.grain), m.grain, -n)
                date_to = today
            else:
                date_from = date_to = None
            spec = m.query_spec(date_from, date_to)
            result = await sem.run_query(db, tenant_id, sem.QuerySpec(**spec), enforce_rate=False)
            facts = facts_from_result(m, result, spec=spec, today=today, date_from=date_from, date_to=date_to)
            for f in facts:
                out = await sink.write(tenant_id, f)
                res["facts"] += 1
                res["inserted" if out.get("inserted") else "updated"] += 1
        except Exception as exc:                                    # noqa: BLE001 - isolate per metric
            res["error"] = str(getattr(exc, "detail", None) or exc)[:200]
            logger.warning("metric snapshot %s failed for tenant %s: %s", m.key, tenant_id, res["error"])
        if pause:
            await asyncio.sleep(pause)
    return summary


# ── query hook ────────────────────────────────────────────────────────────────

_HOOK_LAST: dict = {}


def hook_enabled() -> bool:
    return os.getenv("BI_METRIC_HOOK_ENABLED", "true").strip().lower() not in ("0", "false", "no", "off") and get_sink().configured()


def match_metric(spec) -> Optional[mc.Metric]:
    """The catalogued metric a QuerySpec computes exactly (same dataset/measure/dimensions/time dim/grain/filters), if any."""
    from services.fno_intelligence import bi_semantic as sem
    if len(spec.measures) != 1:
        return None
    ds = sem.DATASETS.get(spec.dataset)
    filters = [{"field": f.field, "op": f.op, "value": f.value} for f in spec.filters]
    for m in mc.CATALOG:
        if m.dataset != spec.dataset or m.measure != spec.measures[0]:
            continue
        if filters != [dict(f) for f in m.filters]:
            continue
        if m.shape == "snapshot":
            if list(spec.dimensions) == list(m.snapshot_dimensions) and (spec.time is None or spec.time.grain is None):
                return m
            continue
        if spec.dimensions or spec.time is None or spec.time.grain != m.grain:
            continue
        if (spec.time.dimension or (ds.default_time if ds else None)) == m.time_dimension:
            return m
    return None


def maybe_record_after_query(tenant_id: uuid.UUID, spec, result: dict) -> bool:
    """Called by bi_semantic.run_query after a successful run. Best effort: never raises, never blocks the query
    (the write is scheduled on the event loop), at most one refresh per (tenant, metric) per interval."""
    try:
        if not hook_enabled():
            return False
        m = match_metric(spec)
        if m is None:
            return False
        interval = _env_float("BI_METRIC_HOOK_MIN_INTERVAL_S", 900)
        key, now_ = (str(tenant_id), m.key), _time.monotonic()
        if now_ - _HOOK_LAST.get(key, -1e12) < interval:
            return False
        today = local_today()
        s = spec.model_dump(by_alias=True, mode="json", exclude_none=True)
        t = spec.time
        facts = facts_from_result(m, result, spec=s, today=today, date_from=t.from_ if t else None, date_to=t.to if t else None)
        if not facts:
            return False
        _HOOK_LAST[key] = now_
        if len(_HOOK_LAST) > 5000:
            _HOOK_LAST.clear()
        from services.common.background_tasks import schedule_background
        schedule_background(_write_all(get_sink(), tenant_id, facts, m.key))
        return True
    except Exception as exc:                                         # noqa: BLE001 - must never fail the query
        logger.debug("metric hook skipped: %s", exc)
        return False


async def _write_all(sink: FactSink, tenant_id: uuid.UUID, facts: list, key: str) -> None:
    try:
        for f in facts:
            await sink.write(tenant_id, f)
    except Exception as exc:                                         # noqa: BLE001
        logger.warning("metric hook write for %s failed: %s", key, str(exc)[:200])


def reset_hook_state() -> None:
    _HOOK_LAST.clear()


# ── daily scheduler ───────────────────────────────────────────────────────────

def scheduler_enabled() -> bool:
    return os.getenv("BI_METRICS_SNAPSHOT_ENABLED", "true").strip().lower() not in ("0", "false", "no", "off")


async def _tenant_ids(session_factory) -> list:
    from sqlalchemy import text
    async with session_factory() as s:
        rows = (await s.execute(text("SELECT id FROM tenants"))).all()
    return [r[0] if isinstance(r[0], uuid.UUID) else uuid.UUID(str(r[0])) for r in rows]


async def run_snapshot_for_all_tenants(session_factory=None, *, sink: Optional[FactSink] = None, today: Optional[date] = None,
                                       tenant_pause_s: Optional[float] = None) -> dict:
    if session_factory is None:
        from services.fno_intelligence import database
        session_factory = database.get_session_factory()
    tenants = await _tenant_ids(session_factory)
    pause = _env_float("BI_METRICS_TENANT_PAUSE_S", 3) if tenant_pause_s is None else tenant_pause_s
    report: dict[str, Any] = {}
    for tid in tenants:                                              # sequential on purpose (small VM)
        try:
            async with session_factory() as s:
                report[str(tid)] = await snapshot_metrics(s, tid, sink=sink, today=today)
        except Exception as exc:                                     # noqa: BLE001
            report[str(tid)] = {"error": str(exc)[:200]}
            logger.warning("daily metric snapshot failed for tenant %s: %s", tid, exc)
        if pause:
            await asyncio.sleep(pause)
    return report


async def run_metrics_scheduler() -> None:
    """Daily loop. Checks every 30 min; runs once per local day after BI_METRICS_SNAPSHOT_HOUR. Safe to run on every
    replica start: snapshots are idempotent upserts."""
    if not scheduler_enabled():
        logger.info("metric snapshot scheduler disabled (BI_METRICS_SNAPSHOT_ENABLED=false)")
        return
    if not get_sink().configured():
        logger.info("metric snapshot scheduler idle: TENANT_MEMORY_SERVICE_URL not set")
        return
    await asyncio.sleep(90)                                          # let the service and tenant_memory settle
    last_run: Optional[date] = None
    while True:
        try:
            today = local_today()
            try:
                hour_gate = int(os.getenv("BI_METRICS_SNAPSHOT_HOUR", "2"))
            except ValueError:
                hour_gate = 2
            local_hour = (datetime.now(timezone.utc) + timedelta(hours=2)).hour
            if last_run != today and local_hour >= hour_gate:
                report = await run_snapshot_for_all_tenants()
                last_run = today
                logger.info("daily metric snapshot done for %d tenant(s)", len(report))
        except Exception as exc:                                     # noqa: BLE001
            logger.warning("metric snapshot loop error: %s", exc)
        await asyncio.sleep(1800)
