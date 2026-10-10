from datetime import date

from services.tenant_memory.knowledge.dream import numbers as N

from .helpers import NOW, T1, fact, make_env, mk_card


def test_smape_and_mase_pure():
    assert N.smape(100, 100) == 0 and N.smape(0, 0) == 0 and round(N.smape(100, 50), 2) == 66.67 and N.smape(0, 10) == 200
    assert N.mase([1, 1], [1, 2, 3, 4]) == 1.0                    # naive one-step error is 1
    assert N.mase([1], [5, 5, 5, 5]) is None and N.mase([], [1, 2, 3]) is None
    assert N.parse_method("forecast:theta|smape=8.2|mase=0.71|n=6") == {"smape": 8.2, "mase": 0.71, "n": 6.0}


def test_detect_metric_drift_ignores_new_periods_and_noise():
    a = fact(T1, "billing.rev", date(2026, 8, 1), date(2026, 8, 31), 1000)
    b = fact(T1, "billing.rev", date(2026, 9, 1), date(2026, 9, 30), 500)
    after = [dict(a, value=1002.0), dict(b, value=650.0), fact(T1, "billing.rev", date(2026, 10, 1), date(2026, 10, 31), 5)]
    d = N.detect_metric_drift([a, b], after, 0.005)
    assert [x["period_start"] for x in d] == ["2026-09-01"] and d[0]["rel_change"] == 0.3        # 0.2% is noise, a new period is not drift
    assert N.detect_metric_drift([a], [dict(a, value=1000.001)], 0.005) == []


def _series(tenant=T1):
    out = []
    vals = [100, 110, 120, 130, 140, 150]
    for i, v in enumerate(vals):
        out.append(fact(tenant, "sales.deals_won.month", date(2026, 3 + i, 1), date(2026, 3 + i, 28), v))
    return out


def test_metric_data_drift_is_recorded_with_before_after_and_the_card_is_refreshed():
    e = make_env()
    f = fact(T1, "sales.won_value.month", date(2026, 8, 1), date(2026, 8, 31), 1000, fid="fact-1")
    e.ops.facts = [f]
    e.index(T1, mk_card("metric_fact", "fact-1", "Won value Aug", "value 1000", module="analytics"))
    e.renderer.script[("metric_fact", "fact-1")] = mk_card("metric_fact", "fact-1", "Won value Aug", "value 1200", module="analytics")
    e.metrics.mutate = lambda ops: ops.facts.__setitem__(0, dict(ops.facts[0], value=1200.0))
    res = e.night(phases=["numbers"])
    assert e.metrics.calls == 1 and res["phase_results"]["numbers"]["counts"]["metric_drift"] == 1
    d = e.findings(type="metric_drift")[0]
    assert d["detail"]["changes"][0]["before"] == 1000 and d["detail"]["changes"][0]["after"] == 1200 and d["severity"] == "high"
    c = e.findings(type="card_contradicts_fact")[0]
    assert "1000" in c["detail"]["before"] and "1200" in c["detail"]["after"]
    assert "1200" in e.live(T1, "metric_fact", "fact-1")[0].markdown


def test_forecast_accuracy_is_scored_and_written_and_degradation_flagged():
    e = make_env()
    actuals = _series()                                          # March..August actual
    good = [fact(T1, "sales.deals_won.month", a["period_start"], a["period_end"], a["value"] * 1.03, kind="forecast", written_by="forecast_run",
                 model_name="baseline-theta", model_version="theta-1", lo=a["value"] * 0.9, hi=a["value"] * 1.1, level=0.8,
                 method="forecast:theta|smape=8.0|mase=0.7|n=6") for a in actuals]
    bad = [fact(T1, "sales.deals_won.month", a["period_start"], a["period_end"], a["value"] * 2.2, kind="forecast", written_by="forecast_run",
                model_name="chronos", model_version="chronos-1", lo=a["value"] * 1.9, hi=a["value"] * 2.0, level=0.8,
                method="forecast:chronos|smape=8.0|mase=0.7|n=6") for a in actuals]
    e.ops.facts = actuals + good + bad
    res = e.night(phases=["numbers"])
    c = res["phase_results"]["numbers"]["counts"]
    assert c["forecast_series_scored"] == 2 and c["forecast_degraded"] == 1 and c["accuracy_facts_written"] == 2
    assert {f.metric_key for _, f in e.ops.written} == {"meta.forecast_accuracy.sales.deals_won.month"}
    by_model = {f.dimensions["version"]: f for _, f in e.ops.written}
    assert by_model["theta-1"].value < 5 and "deg=0" in by_model["theta-1"].method
    assert by_model["chronos-1"].value > 50 and "deg=1" in by_model["chronos-1"].method and by_model["chronos-1"].written_by == "system"
    f = e.findings(type="forecast_degraded")[0]
    assert "chronos-1" in f["dedupe_key"] and f["severity"] == "high" and any("coverage" in r for r in f["detail"]["reasons"])
    s = N.score_forecasts(e.ops.facts, date(2026, 10, 10))
    assert sorted(x["coverage"] for x in s) == [0.0, 1.0]


def test_open_periods_and_unmatched_forecasts_are_not_scored():
    facts = _series()[:2] + [fact(T1, "sales.deals_won.month", date(2026, 10, 1), date(2026, 10, 31), 99, kind="forecast", written_by="forecast_run",
                                  model_name="m", model_version="v1")]
    assert N.score_forecasts(facts, date(2026, 10, 10)) == []


def test_dry_run_does_not_refresh_metrics_or_write_facts():
    e = make_env()
    actuals = _series()
    e.ops.facts = actuals + [fact(T1, "sales.deals_won.month", a["period_start"], a["period_end"], a["value"] * 3, kind="forecast", written_by="forecast_run",
                                  model_name="m", model_version="v1", method="forecast:m|smape=5") for a in actuals]
    res = e.night(phases=["numbers"], dry_run=True)
    assert e.metrics.calls == 0 and e.ops.written == [] and res["phase_results"]["numbers"]["counts"]["forecast_series_scored"] == 1
    assert e.findings(type="forecast_degraded")[0]["status"] == "proposed"


def test_no_refresher_means_an_honest_note_not_a_failure():
    e = make_env()
    e.deps.metrics = None
    res = e.night(phases=["numbers"])
    assert res["status"] == "completed" and any("not configured" in n for n in res["phase_results"]["numbers"]["notes"])
