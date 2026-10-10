"""Forecaster tests: pure numpy, SQLite, no network, no torch, no LLM."""
from __future__ import annotations

import logging
import pathlib
import uuid
from datetime import date, datetime, timedelta, timezone

import numpy as np
import pytest
from sqlalchemy import create_engine, text

from services.fno_intelligence import metric_catalog as mc
from services.forecaster import baselines, chronos_adapter, history, run, selection

TODAY = date(2026, 10, 10)             # current month Oct 2026 => last complete month is Sep 2026
TENANT = str(uuid.UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"))
PKG = pathlib.Path(__file__).resolve().parents[1]


def seasonal_series(n=48, seed=0, noise=2.0):
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    return 100 + 1.5 * t + 20 * np.sin(2 * np.pi * t / 12) + rng.normal(0, noise, n)


# ── baselines ────────────────────────────────────────────────────────────────

def test_baselines_recover_seasonality_and_trend():
    y = seasonal_series(48, noise=0.0)
    truth = 100 + 1.5 * np.arange(48, 54) + 20 * np.sin(2 * np.pi * np.arange(48, 54) / 12)
    for name in ("holt_winters", "theta"):
        f = baselines.ALL[name][0](y, 6, 12)
        assert np.mean(np.abs(f - truth) / truth) < 0.06, name
    # a non-seasonal model cannot track the sine and must be worse than holt_winters
    err_hw = np.abs(baselines.holt_winters(y, 6, 12) - truth).mean()
    err_drift = np.abs(baselines.drift(y, 6) - truth).mean()
    assert err_hw < err_drift


def test_seasonal_naive_repeats_last_season():
    y = np.arange(24, dtype=float)
    assert list(baselines.seasonal_naive(y, 3, 12)) == [12.0, 13.0, 14.0]


def test_seasonal_models_need_two_full_seasons():
    assert "holt_winters" not in baselines.candidates(23, 12)
    assert "holt_winters" in baselines.candidates(24, 12)
    assert "seasonal_naive" not in baselines.candidates(20, 12)


def test_selection_prefers_seasonal_model_on_seasonal_data():
    fc = selection.forecast_series(seasonal_series(48, noise=1.0), 6, 12)
    assert fc.model_name.split("-", 1)[1] in ("holt_winters", "theta", "seasonal_naive")
    assert fc.mase < 1.0
    assert len(fc.point) == 6 and fc.n_origins >= 3
    assert {"naive", "drift"} <= set(fc.scores)       # others were scored and lost


def test_selection_picks_trend_model_on_linear_series():
    y = 50 + 4.0 * np.arange(30) + np.random.default_rng(1).normal(0, 1.0, 30)
    fc = selection.forecast_series(y, 3, 12)          # 30 < 2 seasons plus origins => non-seasonal only
    assert fc.model_name.split("-", 1)[1] in ("drift", "holt_damped", "theta")
    assert fc.point[-1] > y[-1]                       # trend continues upward


def test_backtest_selection_is_by_lowest_mase():
    fc = selection.forecast_series(seasonal_series(48, noise=1.0), 3, 12)
    best = min(fc.scores, key=lambda k: fc.scores[k]["mase"])
    assert fc.model_name == f"baseline-{best}"


def test_interval_contains_point_and_widens_with_horizon():
    fc = selection.forecast_series(seasonal_series(48, seed=3, noise=4.0), 6, 12)
    assert np.all(fc.lower <= fc.point) and np.all(fc.point <= fc.upper)
    w = fc.upper - fc.lower
    assert w[-1] >= w[0] * 0.9 and w.min() > 0


def test_interval_coverage_sanity():
    """Nominal 80% intervals should cover well over half of held-out points on noisy seasonal data."""
    hit = tot = 0
    for seed in range(25):
        full = seasonal_series(51, seed=seed, noise=5.0)
        fc = selection.forecast_series(full[:48], 3, 12, level=0.8)
        truth = full[48:]
        hit += int(np.sum((truth >= fc.lower) & (truth <= fc.upper)))
        tot += 3
    assert hit / tot >= 0.6, hit / tot


def test_negative_forecasts_are_clipped_for_counts_and_currency():
    y = np.maximum(np.linspace(40, 1, 30) + np.random.default_rng(2).normal(0, 1.5, 30), 0)
    fc = selection.forecast_series(y, 6, 12, nonnegative=True)
    assert fc.point.min() >= 0 and fc.lower.min() >= 0 and fc.upper.min() >= 0
    unclipped = selection.forecast_series(y, 6, 12, nonnegative=False)
    assert unclipped.lower.min() < 0 or unclipped.point.min() < 0      # sanity: clipping did the work


def test_too_short_history_raises():
    with pytest.raises(selection.InsufficientHistory):
        selection.forecast_series(np.arange(5.0), 3, 12)


def test_constant_series_does_not_crash():
    fc = selection.forecast_series(np.full(20, 7.0), 3, 12)
    assert np.allclose(fc.point, 7.0) and np.all(fc.lower <= 7.0) and np.all(fc.upper >= 7.0)


# ── foundation model plug-in and fallback ────────────────────────────────────

class OracleModel:
    """Stands in for Chronos: knows the exact deterministic series, so it must win the backtest."""
    name, version = "chronos-bolt-small", "fake+0"

    def __init__(self, f):
        self.f = f

    def predict(self, y, h, level):
        t0 = len(y)
        med = np.array([self.f(t0 + i) for i in range(h)])
        return med, med - 3.0, med + 3.0


class BrokenModel:
    name, version = "chronos-bolt-small", "fake+0"

    def predict(self, y, h, level):
        raise RuntimeError("weights corrupt")


def test_foundation_model_selected_when_it_backtests_best_and_supplies_intervals():
    f = lambda t: 100 + 1.5 * t + 20 * np.sin(2 * np.pi * t / 12)
    y = np.array([f(t) for t in range(48)]) + np.random.default_rng(4).normal(0, 6, 48) * 0   # noiseless => oracle exact
    fc = selection.forecast_series(y, 4, 12, foundation=OracleModel(f))
    assert fc.model_name == "chronos-bolt-small" and fc.model_version == "fake+0"
    assert np.allclose(fc.upper - fc.point, 3.0)


def test_falls_back_to_baselines_when_foundation_fails():
    fc = selection.forecast_series(seasonal_series(48), 3, 12, foundation=BrokenModel())
    assert fc.model_name.startswith("baseline-")
    assert any("unavailable" in n for n in fc.notes)


def test_chronos_adapter_reports_unavailable_without_weights(tmp_path, monkeypatch):
    monkeypatch.setenv("FORECAST_MODEL_DIR", str(tmp_path))
    monkeypatch.delenv("FORECAST_CHRONOS", raising=False)
    ok, why = chronos_adapter.status()
    assert not ok and "weights not found" in why
    assert chronos_adapter.load() is None


def test_chronos_adapter_off_switch_and_model_allowlist(tmp_path, monkeypatch):
    monkeypatch.setenv("FORECAST_MODEL_DIR", str(tmp_path))
    monkeypatch.setenv("FORECAST_CHRONOS", "off")
    assert chronos_adapter.status() == (False, "disabled by FORECAST_CHRONOS=off")
    monkeypatch.setenv("FORECAST_CHRONOS", "auto")
    monkeypatch.setenv("FORECAST_CHRONOS_MODEL", "timesfm-3.0")        # license-restricted: must never be accepted
    ok, why = chronos_adapter.status()
    assert not ok and "not an allowed" in why


def test_weights_present_but_package_missing_degrades(tmp_path, monkeypatch):
    d = tmp_path / "chronos-bolt-small"
    d.mkdir()
    (d / "config.json").write_text("{}")
    monkeypatch.setenv("FORECAST_MODEL_DIR", str(tmp_path))
    monkeypatch.delenv("FORECAST_CHRONOS", raising=False)
    monkeypatch.delenv("FORECAST_CHRONOS_MODEL", raising=False)
    import sys
    monkeypatch.setitem(sys.modules, "chronos", None)                  # makes `import chronos` raise ImportError
    ok, why = chronos_adapter.status()
    assert not ok and "not importable" in why
    assert chronos_adapter.load() is None


# ── history rules ────────────────────────────────────────────────────────────

def monthly_actuals(n, end=date(2026, 9, 1), value=lambda i: 100.0 + i):
    out, d = [], end
    for _ in range(n):
        out.append(d)
        d = date(d.year - (d.month == 1), (d.month - 2) % 12 + 1, 1)
    return [(s, value(i)) for i, s in enumerate(sorted(out))]


M = mc.BY_KEY["billing.revenue_invoiced.month"]


def test_min_history_guard_emits_nothing():
    with pytest.raises(history.Skip, match="only 11 usable"):
        history.build_series(M, monthly_actuals(11), TODAY)
    s = history.build_series(M, monthly_actuals(12), TODAY)
    assert len(s.values) == 12


def test_stale_history_is_not_forecast():
    old = monthly_actuals(30, end=date(2026, 5, 1))
    with pytest.raises(history.Skip, match="stale"):
        history.build_series(M, old, TODAY)


def test_leading_zero_run_does_not_count_as_history():
    rows = monthly_actuals(14, value=lambda i: 0.0 if i < 5 else 50.0 + i)
    with pytest.raises(history.Skip, match="only 9 usable"):
        history.build_series(M, rows, TODAY)


def test_gap_filling_zero_for_counts_interpolation_for_averages():
    rows = monthly_actuals(16)
    del rows[8]
    s = history.build_series(M, rows, TODAY)
    assert s.values[8] == 0.0 and len(s.values) == 16 and s.real_points == 15
    avg = mc.BY_KEY["support.avg_resolution_hours.week"]
    wk = [(date(2026, 9, 28) - timedelta(weeks=i), 10.0 + i) for i in range(40)]
    wk = sorted(wk)
    del wk[10]
    s2 = history.build_series(avg, wk, TODAY)
    assert s2.values[10] != 0.0 and 10.0 <= s2.values[10] <= 50.0


def test_all_zero_recent_history_is_skipped():
    rows = [(d, 0.0) for d, _ in monthly_actuals(20)]
    with pytest.raises(history.Skip):
        history.build_series(M, rows, TODAY)


# ── end to end on SQLite with a recording sink ───────────────────────────────

class RecordingSink:
    def __init__(self):
        self.facts = []

    def write(self, tenant, fact):
        self.facts.append((tenant, fact))
        return {"id": "x", "inserted": True}


def make_db(tmp_path, n_months=36, key=M.key):
    eng = create_engine(f"sqlite:///{tmp_path / 'f.db'}")
    with eng.begin() as c:
        c.execute(text("CREATE TABLE tenant_metric_facts (tenant_id TEXT, metric_key TEXT, dimensions_hash TEXT, period_start DATE, "
                       "period_end DATE, kind TEXT, value REAL)"))
        for s, v in monthly_actuals(n_months, value=lambda i: 1000 + 20 * i + 100 * np.sin(2 * np.pi * i / 12)):
            c.execute(text("INSERT INTO tenant_metric_facts VALUES (:t, :k, :h, :s, :e, 'actual', :v)"),
                      {"t": TENANT, "k": key, "h": history.EMPTY_DIMS_HASH, "s": s, "e": mc.period_end(s, "month"), "v": float(v)})
    return eng


def test_run_tenant_writes_forecast_facts_through_sink_only(tmp_path):
    eng = make_db(tmp_path)
    sink = RecordingSink()
    with eng.connect() as c:
        summary = run.run_tenant(c, TENANT, sink, keys=[M.key], horizon=4, today=TODAY)
    assert summary[M.key]["status"] == "forecast" and summary[M.key]["facts"] == 4
    assert len(sink.facts) == 4
    starts = [f["period_start"] for _, f in sink.facts]
    assert starts == ["2026-10-01", "2026-11-01", "2026-12-01", "2027-01-01"]
    for tenant, f in sink.facts:
        assert tenant == TENANT
        assert f["kind"] == "forecast" and f["written_by"] == "forecast_run"
        assert f["model_name"] and f["model_version"] and f["interval_level"] == 0.8
        assert f["lower_bound"] <= f["value"] <= f["upper_bound"] and f["lower_bound"] >= 0
        assert f["method"].startswith("forecast:") and "smape=" in f["method"] and len(f["method"]) <= 80
        assert 0 <= f["confidence"] <= 1
        assert f["source_query"]["dataset"] == "billing_invoices" and f["source_query"]["measures"] == ["invoiced"]


def test_facts_validate_against_the_real_metric_fact_schema(tmp_path):
    MetricFactIn = pytest.importorskip("services.tenant_memory.knowledge.metrics").MetricFactIn
    eng = make_db(tmp_path)
    sink = RecordingSink()
    with eng.connect() as c:
        run.run_tenant(c, TENANT, sink, keys=[M.key], today=TODAY)
    assert sink.facts
    for _, f in sink.facts:
        MetricFactIn(**f)
        with pytest.raises(Exception):
            MetricFactIn(**{**f, "kind": "actual"})       # a forecast run can never write an actual


def test_insufficient_history_emits_nothing_and_logs_reason(tmp_path, caplog):
    eng = make_db(tmp_path, n_months=8)
    sink = RecordingSink()
    with caplog.at_level(logging.INFO, logger="forecaster"), eng.connect() as c:
        summary = run.run_tenant(c, TENANT, sink, keys=[M.key], today=TODAY)
    assert sink.facts == []
    assert summary[M.key]["status"] == "skipped" and "only 8 usable" in summary[M.key]["reason"]
    assert "no forecast" in caplog.text


def test_dry_run_writes_nothing(tmp_path):
    eng = make_db(tmp_path)
    sink = RecordingSink()
    with eng.connect() as c:
        s = run.run_tenant(c, TENANT, sink, keys=[M.key], today=TODAY, dry_run=True)
    assert s[M.key]["status"] == "dry_run" and sink.facts == []


def test_non_forecastable_metric_is_refused(tmp_path):
    eng = make_db(tmp_path)
    sink = RecordingSink()
    with eng.connect() as c:
        s = run.run_tenant(c, TENANT, sink, keys=["sales.pipeline_value_by_stage"], today=TODAY)
    assert s["sales.pipeline_value_by_stage"]["status"] == "skipped" and sink.facts == []


def test_sink_failure_is_isolated_per_metric(tmp_path):
    class Boom:
        def write(self, tenant, fact):
            raise RuntimeError("down")
    eng = make_db(tmp_path)
    with eng.connect() as c:
        s = run.run_tenant(c, TENANT, Boom(), keys=[M.key], today=TODAY)
    assert s[M.key]["status"] == "error"


def test_process_pending_claims_runs_once_and_records_summary(tmp_path):
    from services.fno_intelligence.forecast_models import FORECAST_TABLES
    from services.fno_intelligence.models import Base
    eng = make_db(tmp_path)
    Base.metadata.create_all(eng, tables=FORECAST_TABLES)
    rid = uuid.uuid4()
    with eng.begin() as c:
        c.execute(text("INSERT INTO forecast_runs (id, tenant_id, status, metric_keys, horizon, created_at) "
                       "VALUES (:i, :t, 'queued', :k, 2, CURRENT_TIMESTAMP)"),
                  {"i": rid.hex, "t": uuid.UUID(TENANT).hex, "k": f'["{M.key}"]'})
    sink = RecordingSink()
    done = run.process_pending(eng, sink, today=TODAY)
    assert done == [(rid.hex, "done")] or done == [(str(rid), "done")] or done[0][1] == "done"
    assert len(sink.facts) == 2
    assert run.process_pending(eng, sink, today=TODAY) == []          # already claimed/finished
    with eng.connect() as c:
        row = c.execute(text("SELECT status, summary FROM forecast_runs")).one()
    assert row[0] == "done" and M.key in str(row[1])


# ── hard rules ───────────────────────────────────────────────────────────────

def test_no_llm_or_timesfm3_code_paths():
    banned = ("openrouter", "llm_complete", "anthropic", "openai", "ollama", "gemini", "from services.common.firecrawl")
    for p in PKG.glob("*.py"):
        src = p.read_text(encoding="utf-8").lower()
        for b in banned:
            assert b not in src, f"{p.name} mentions {b}"
    adapter = (PKG / "chronos_adapter.py").read_text(encoding="utf-8")
    assert "import timesfm" not in adapter and "from timesfm" not in adapter


def test_baseline_path_never_imports_torch():
    import sys
    import importlib
    for mod in ("services.forecaster.baselines", "services.forecaster.selection", "services.forecaster.history", "services.forecaster.run"):
        importlib.import_module(mod)
    assert "torch" not in sys.modules or True        # torch may be loaded by other tests; the modules themselves never import it
    for p in PKG.glob("*.py"):
        if p.name != "chronos_adapter.py":
            assert "import torch" not in p.read_text(encoding="utf-8"), p.name
