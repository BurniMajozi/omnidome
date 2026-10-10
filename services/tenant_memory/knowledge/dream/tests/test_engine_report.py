import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from services.tenant_memory.knowledge.cards.base import stable_text
from services.tenant_memory.knowledge.dream import PHASES, report as RP, runner
from services.tenant_memory.knowledge.dream.engine import in_window, local_date, run_due
from services.tenant_memory.knowledge.dream.ports import Telemetry, Usage
from services.tenant_memory.knowledge.dream.settings import DreamSettings, clamp, merged
from services.tenant_memory.knowledge.kdata import AccessScope, content_hash

from .helpers import NOW, T1, T2, edge, fact, make_env, mk_card, run


def seeded():
    e = make_env(jev_enabled=True)
    old = NOW - timedelta(days=60)
    e.index(T1, mk_card("ticket", "t1", "Soweto outage", "fibre cut", importance=0.9), mk_card("ticket", "t2", "Billing question", "invoice query", as_of=old),
            mk_card("ticket", "t3", "Router swap", "replace router", importance=0.9, edges=[edge("ticket", "t3", "ticket", "t1")]),
            mk_card("ticket", "t4", "Gone ticket", "closed long ago", importance=0.9))
    e.renderer.script[("ticket", "t1")] = mk_card("ticket", "t1", "Soweto outage", "fibre repaired", importance=0.9)
    e.renderer.script[("ticket", "t4")] = "gone"
    return e


def test_full_night_runs_every_phase_in_order_and_writes_report_and_card():
    e = seeded()
    res = e.night()
    assert res["status"] == "completed" and res["phases_done"] == list(PHASES) and res["health_score"] is not None
    assert list(res["phase_results"]) == list(PHASES) and all(r["status"] == "ok" for r in res["phase_results"].values())
    rep = res["report"]
    assert rep["drift"]["content_drift"] == 1 and rep["drift"]["vanished"] == 1 and rep["cards"]["live_sources"] >= 3
    assert e.consolidated == [(T1, False)] and rep["consolidation"]["promoted"] == 2 and rep["consolidation"]["tombstones_purged"] == 7
    card = e.live(T1, "memory_health", "latest")
    assert card and card[0].module == "memory" and "Memory health report" in card[0].title
    assert run(e.dstore.get_run(T1, res["id"]))["health_score"] == rep["health_score"]


def test_health_card_is_admin_only_and_findable_by_agents_with_the_memory_panel():
    e = seeded()
    e.night()
    chunk = e.live(T1, "memory_health", "latest")[0]
    assert AccessScope(T1, is_admin=True).allows(chunk)
    assert not AccessScope(T1, roles=frozenset({"agent"})).allows(chunk) and not AccessScope(T1, roles=frozenset({"sales"}), modules=frozenset({"memory"})).allows(chunk)
    assert AccessScope(T1, roles=frozenset({"admin"}), modules=frozenset({"memory"})).allows(chunk)


def test_report_card_is_deterministic():
    e = seeded()
    res = e.night()
    rep = res["report"]
    a, b = RP.render_card(rep), RP.render_card(dict(rep))
    assert a.markdown == b.markdown and content_hash(stable_text(a.markdown)) == content_hash(stable_text(b.markdown))
    assert a.visibility == "team" and "admin" in a.required_roles and a.source_id == "latest"
    again = dict(rep, errors=list(rep["errors"]))
    assert RP.health_score(again) == rep["health_score"] == RP.health_score(rep)
    assert "Overall health" in a.markdown and rep["run_date"] in a.title


def test_health_score_components_and_bounds():
    base = {"canary": {"recall_at_3": 1.0}, "cards": {"stale": 0, "live_sources": 100}, "embeddings": {"invalid": 0, "scanned": 100},
            "findings": {"open_by_severity": {}}, "metrics": {"drifted": 0, "checked": 10}, "forecast": {"degraded": 0}, "errors": []}
    assert RP.health_score(base) == 100
    assert RP.health_score({**base, "canary": {"recall_at_3": 0.5}}) == 85
    assert RP.health_score({**base, "canary": {"recall_at_3": None}}) == 95
    assert RP.health_score({**base, "cards": {"stale": 50, "live_sources": 100}}) == 80
    assert RP.health_score({**base, "findings": {"open_by_severity": {"critical": 5}}}) == 85            # capped
    worst = {"canary": {"recall_at_3": 0.0}, "cards": {"stale": 100, "live_sources": 100}, "embeddings": {"invalid": 100, "scanned": 100},
             "findings": {"open_by_severity": {"critical": 9}}, "metrics": {"drifted": 10, "checked": 10}, "forecast": {"degraded": 9}, "errors": ["x"] * 9}
    assert 0 <= RP.health_score(worst) <= 5 and RP.health_label(95) == "excellent" and RP.health_label(10) == "needs attention"


def test_critical_new_findings_notify_the_tenant():
    e = make_env()
    e.index(T1, mk_card("campaign", "c1", "Campaign one", "x", importance=0.9))
    e.renderer.script[("campaign", "c1")] = "source_missing"
    e.night()
    assert e.ops.notes and e.ops.notes[0][0] == T1 and e.ops.notes[0][2] in ("warning", "critical")
    quiet = make_env()
    quiet.index(T1, mk_card("ticket", "t", "Fine", "x"))
    quiet.night()
    assert quiet.ops.notes == []


def test_a_failing_phase_is_recorded_and_the_night_continues():
    e = seeded()

    async def boom(*a, **k):
        raise RuntimeError("renderer exploded")
    e.renderer.render = boom
    res = e.night()
    # the renderer error is contained per card; make a whole-phase failure by breaking the store scan too
    assert res["status"] in ("completed", "completed_with_errors") and res["phases_done"] == list(PHASES)
    e2 = seeded()
    e2.deps.consolidate = lambda t, d: (_ for _ in ()).throw(RuntimeError("db down"))
    res2 = e2.night()
    assert res2["status"] == "completed_with_errors" and res2["phase_results"]["consolidate"]["status"] == "error"
    assert res2["phase_results"]["report"]["status"] == "ok" and any("db down" in x for x in res2["errors"])


def test_interrupted_night_resumes_without_redoing_finished_phases():
    e = seeded()
    calls = {"n": 0}

    async def consolidate(tenant, dry_run):
        calls["n"] += 1
        if calls["n"] == 1:
            raise asyncio.CancelledError()
        return {"promotion": {"promoted": [], "expired_deleted": 0}}
    e.deps.consolidate = consolidate
    with pytest.raises(asyncio.CancelledError):
        e.night(trigger="nightly", resume=True)
    first = run(e.dstore.list_runs(T1))[0]
    assert first["status"] == "interrupted" and first["phases_done"] == ["drift", "embeddings", "numbers", "relevance", "adjudicate"]
    rendered = list(e.renderer.calls)
    res = e.night(trigger="nightly", resume=True)
    assert res["id"] == first["id"] and res["status"] == "completed" and res["phases_done"] == list(PHASES)
    assert e.renderer.calls == rendered                                    # drift was NOT repeated
    assert calls["n"] == 2 and len(run(e.dstore.list_runs(T1))) == 1


def test_resume_inside_a_phase_continues_from_its_cursor():
    e = make_env(max_cards_per_night=500, high_importance=0.0, batch_size=2)
    e.index(T1, *[mk_card("ticket", f"t{i}", f"Ticket number {i}", "x") for i in range(6)])
    seen = []
    orig = e.renderer.render

    async def flaky(tenant, st, sid):
        seen.append(sid)
        if sid == "t3" and seen.count("t3") == 1:
            raise asyncio.CancelledError()
        return await orig(tenant, st, sid)
    e.renderer.render = flaky
    with pytest.raises(asyncio.CancelledError):
        e.night(phases=["drift"], trigger="nightly", resume=True)
    res = e.night(phases=["drift"], trigger="nightly", resume=True)
    assert res["status"] == "completed"
    assert seen.count("t0") == 1 and seen.count("t1") == 1 and seen.count("t3") == 2          # t0/t1 (earlier batch) were not redone


def _snapshot(e):
    rows = {k: (c.content_hash, c.importance, tuple(c.tags), c.deleted_at, tuple(c.embedding or ()), c.embedding_model, c.markdown) for k, c in e.store.rows.items()}
    return rows, {k: len(v) for k, v in e.store.edges.items()}, dict(e.dstore.card_state)


def test_dry_run_makes_no_changes_anywhere_except_the_dream_log():
    e = seeded()
    e.index(T1, mk_card("ticket", "bad", "Bad vector", "x", importance=0.9))
    e.live(T1, "ticket", "bad")[0].embedding = [0.0] * 32
    run(e.store.replace_edges(T1, "ticket:ghost", [edge("ticket", "ghost", "ticket", "t1")]))
    e.ops.facts = [fact(T1, "sales.won_value.month", NOW.date() - timedelta(days=40), NOW.date() - timedelta(days=10), 10)]
    e.ops.telemetry = Telemetry(True, {("ticket", "t3"): Usage(retrieved=20, used=20, cited=20)}, observed_since=NOW - timedelta(days=90))
    before = _snapshot(e)
    res = e.night(dry_run=True)
    assert _snapshot(e) == before
    assert res["dry_run"] is True and res["status"] == "completed"
    assert e.ops.written == [] and e.metrics.calls == 0 and e.jev.calls == [] and e.ops.notes == []
    assert e.consolidated == [(T1, True)] and not e.live(T1, "memory_health", "latest")
    statuses = {f["status"] for f in e.findings()}
    assert statuses <= {"proposed"} and statuses                                    # everything is a proposal, nothing was applied
    assert any(f["detail"].get("would_auto_apply") for f in e.findings())
    assert run(e.dstore.list_runs(T1, include_dry=False)) == []                     # dry runs never count as the nightly


def test_the_same_night_after_a_dry_run_then_applies_the_changes():
    e = seeded()
    e.night(dry_run=True)
    assert "cut" in e.live(T1, "ticket", "t1")[0].markdown
    e.night()
    assert "repaired" in e.live(T1, "ticket", "t1")[0].markdown and not e.live(T1, "ticket", "t4")


def test_tenant_isolation_across_a_full_night():
    e = seeded()
    e.index(T2, mk_card("ticket", "t1", "Soweto outage", "fibre cut", importance=0.9))
    before = {k: c.markdown for k, c in e.store.rows.items() if c.tenant_id == T2}
    e.night(T1)
    assert {k: c.markdown for k, c in e.store.rows.items() if c.tenant_id == T2 if c.source_type != "memory_health"} == before
    assert run(e.dstore.list_runs(T2)) == [] and e.findings(T2) == [] and run(e.dstore.get_run(T2, run(e.dstore.list_runs(T1))[0]["id"])) is None
    assert not e.live(T2, "memory_health", "latest") and e.live(T1, "memory_health", "latest")


def test_kill_switch_before_and_during_a_run():
    e = seeded()
    e.killed[0] = True
    assert e.night()["status"] == "skipped" and run(e.dstore.list_runs(T1)) == []
    e.killed[0] = False

    async def consolidate(tenant, dry_run):
        e.killed[0] = True                                                         # thrown while phase 6 runs
        return {}
    e.deps.consolidate = consolidate
    res = e.night()
    assert res["status"] == "aborted" and "report" not in res["phases_done"] and "consolidate" in res["phases_done"]


def test_phase_selection_and_unknown_phase():
    e = seeded()
    res = e.night(phases=["drift", "report"])
    assert res["phases_done"] == ["drift", "report"] and e.consolidated == []
    with pytest.raises(ValueError):
        e.night(phases=["nope"])


def test_second_run_is_skipped_while_the_first_holds_the_lock():
    e = seeded()
    run(e.store.try_lock(f"dream:{T1}"))
    assert e.night()["status"] == "skipped"


def test_settings_are_clamped_and_jev_thresholds_cannot_be_loosened():
    s = merged({"jev_approve": 0.5, "jev_reject": 0.5, "window_start": "99:99", "window_hours": 99, "canary_n": 9999, "not_tunable": 1, "jev_max_calls": -4})
    assert s.jev_approve == 0.80 and s.jev_reject == 0.20 and s.window_start == "23:59" and s.window_hours == 12 and s.canary_n == 100 and s.jev_max_calls == 0
    assert clamp(DreamSettings(importance_max_step=5)).importance_max_step == 0.1
    assert merged({"enabled": True}).enabled is True and merged({"batch_size": 1}).batch_size != 1


def test_window_is_local_johannesburg_time():
    cfg = DreamSettings()
    at = lambda h, m: datetime(2026, 10, 10, h, m, tzinfo=timezone.utc)      # noqa: E731
    assert not in_window(at(0, 29), cfg) and in_window(at(0, 30), cfg) and in_window(at(3, 29), cfg) and not in_window(at(3, 30), cfg)
    assert local_date(at(23, 0), cfg.timezone) == "2026-10-11"               # 01:00 SAST the next day
    assert in_window(at(1, 0), DreamSettings(window_start="03:00", window_hours=1.0)) and not in_window(at(2, 0), DreamSettings(window_start="03:00", window_hours=1.0))


def test_run_due_runs_enabled_tenants_in_their_window_once_per_night_one_at_a_time():
    e = make_env()
    order = []
    orig = e.engine.run_tenant

    async def traced(tenant, **kw):
        order.append(tenant)
        return await orig(tenant, **kw)
    e.engine.run_tenant = traced
    run(e.dstore.put_settings(T2, {"enabled": False}, "t"))
    done = run(run_due(e.engine, [T1, T2]))
    assert order == [T1] and done[0]["status"] == "completed"
    assert run(run_due(e.engine, [T1, T2])) == []                              # already ran tonight
    e.clock.advance(hours=12)
    e.clock.t = e.clock.t.replace(hour=10)
    assert run(run_due(e.engine, [T1])) == []                                  # outside the window
    e.clock.advance(days=1)
    e.clock.t = e.clock.t.replace(hour=1, minute=0)
    assert [d["tenant"] for d in run(run_due(e.engine, [T1]))] == [T1]         # next night
    e.deps.base_settings = DreamSettings(enabled=False)
    e.clock.advance(days=1)
    assert run(run_due(e.engine, [T1])) == []


def test_worker_job_runs_a_dry_run_by_default(monkeypatch):
    e = seeded()
    monkeypatch.setitem(runner._engines, id(e.store), e.engine)
    out = run(runner.run_dream_job(e.store, e.emb, {"tenant_id": T1, "params": {}, "requested_by": "u1"}))
    assert out["status"] == "completed"
    r = run(e.dstore.list_runs(T1))[0]
    assert r["dry_run"] is True and r["trigger"] == "manual" and r["requested_by"] == "u1"
    out2 = run(runner.run_dream_job(e.store, e.emb, {"tenant_id": T1, "params": {"dry_run": False, "phases": ["drift"]}}))
    assert out2["phases_done"] == ["drift"] and "repaired" in e.live(T1, "ticket", "t1")[0].markdown
