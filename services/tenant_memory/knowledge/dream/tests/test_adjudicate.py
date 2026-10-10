from datetime import timedelta

from services.tenant_memory.knowledge.dream import jev as J
from services.tenant_memory.knowledge.dream.ports import Telemetry, Usage
from services.tenant_memory.knowledge.dream.store import STALE_TAG

from .helpers import NOW, T1, make_env, mk_card, run

OLD = NOW - timedelta(days=60)
PHASES = ["drift", "relevance", "adjudicate"]


def stale_env(n=1, p=0.95, **kw):
    e = make_env(jev_enabled=True, **kw)
    topics = ["alpha handset", "bravo splitter", "charlie voucher", "delta antenna", "echo modem"]
    e.index(T1, *[mk_card("ticket", f"s{i}", f"Old ticket {topics[i]}", f"{topics[i]} complaint unrelated to others {topics[i]}", as_of=OLD) for i in range(n)])
    e.jev.script = {"still_current": p}
    return e


def test_decision_thresholds_act_only_at_the_calibrated_extremes():
    assert J.decide(0.90, 0.90, 0.10) == "yes" and J.decide(0.899, 0.90, 0.10) == "review"
    assert J.decide(0.10, 0.90, 0.10) == "no" and J.decide(0.101, 0.90, 0.10) == "review" and J.decide(0.5, 0.9, 0.1) == "review"


def test_confident_yes_clears_the_stale_marker():
    e = stale_env(p=0.95)
    res = e.night(phases=PHASES)
    assert STALE_TAG not in e.live(T1, "ticket", "s0")[0].tags
    f = e.findings(type="jev_still_current")[0]
    assert f["jev"]["decision"] == "yes" and f["jev"]["p"] == 0.95 and f["status"] == "auto_applied"
    assert res["jev_calls"] == 1 and res["jev_cost_usd"] == 0.01


def test_confident_no_confirms_staleness_and_asks_for_a_refresh():
    e = stale_env(p=0.04)
    e.night(phases=PHASES)
    assert STALE_TAG in e.live(T1, "ticket", "s0")[0].tags
    f = e.findings(type="jev_stale_confirmed")[0]
    assert f["status"] == "open" and f["action"]["kind"] == "refresh" and f["jev"]["decision"] == "no"


def test_middle_band_is_left_to_a_human():
    e = stale_env(p=0.5)
    res = e.night(phases=PHASES)
    assert STALE_TAG in e.live(T1, "ticket", "s0")[0].tags
    assert not e.findings(type="jev_still_current") and not e.findings(type="jev_stale_confirmed")
    assert res["phase_results"]["adjudicate"]["counts"]["queued_for_review"] == 1


def test_off_switch_makes_no_calls_and_queues_for_review():
    e = stale_env(p=0.99)
    e.deps.base_settings = e.deps.base_settings.__class__(**{**e.deps.base_settings.__dict__, "jev_enabled": False})
    res = e.night(phases=PHASES)
    assert e.jev.calls == [] and res["jev_calls"] == 0
    assert res["phase_results"]["adjudicate"]["counts"]["queued_for_review"] == 1
    assert any("off" in n for n in res["phase_results"]["adjudicate"]["notes"])


def test_per_night_call_cap_is_enforced():
    e = stale_env(n=4, p=0.95, jev_max_calls=2)
    res = e.night(phases=PHASES)
    assert len(e.jev.calls) == 2 and res["jev_calls"] == 2
    c = res["phase_results"]["adjudicate"]["counts"]
    assert c["budget_exhausted"] == 2 and c["queued_for_review"] == 2


def test_cost_cap_is_enforced():
    e = stale_env(n=4, p=0.95, jev_max_cost_usd=0.015)
    e.night(phases=PHASES)
    assert len(e.jev.calls) == 2                                           # 0.01 then 0.02 >= cap: stop


def test_decisions_are_cached_across_nights():
    e = stale_env(p=0.95)
    e.night(phases=PHASES)
    assert len(e.jev.calls) == 1
    assert STALE_TAG not in e.live(T1, "ticket", "s0")[0].tags              # JEV cleared it; tonight the SLA flags it again, same card text
    res = e.night(phases=PHASES)
    assert len(e.jev.calls) == 1 and res["phase_results"]["adjudicate"]["counts"]["jev_cached"] == 1 and res["jev_calls"] == 0


def test_dry_run_never_calls_jev():
    e = stale_env(p=0.95)
    res = e.night(phases=PHASES, dry_run=True)
    assert e.jev.calls == [] and STALE_TAG not in e.live(T1, "ticket", "s0")[0].tags and res["jev_calls"] == 0


def test_only_scrubbed_eligible_excerpts_are_sent():
    e = make_env(jev_enabled=True)
    e.index(T1, mk_card("ticket", "pii", "Callback request", "call jane.doe@example.com or 082 555 1234 about id 8001015009087", as_of=OLD),
            mk_card("payslip", "hr1", "Payroll run", "salary details", as_of=OLD, module="hr"),
            mk_card("ticket", "priv", "Private note", "mine", as_of=OLD, visibility="private", owner_id="33333333-3333-3333-3333-333333333333"))
    e.jev.script = {"still_current": 0.5}
    e.night(phases=PHASES)
    assert len(e.jev.calls) == 1
    sent = str(e.jev.calls[0][0])
    assert "example.com" not in sent and "555 1234" not in sent and "8001015009087" not in sent and "redacted" in sent
    assert "Payroll" not in sent and "Private note" not in sent                      # excluded module and private cards never leave


def _conflict_env(p):
    e = make_env(jev_enabled=True)
    e.index(T1, mk_card("price", "a", "Router price", "router costs r499 per month fibre line"), mk_card("price", "b", "Router price", "router costs r599 per month fibre line"))
    e.jev.script = {"contradict": p}
    return e


def test_contradiction_verdicts_update_the_conflict_review_item():
    e = _conflict_env(0.97)
    e.night(phases=PHASES)
    f = e.findings(type="conflict")[0]
    assert f["severity"] == "high" and f["status"] == "open" and f["jev"]["decision"] == "yes"
    e2 = _conflict_env(0.02)
    e2.night(phases=PHASES)
    f2 = e2.findings(type="conflict")[0]
    assert f2["status"] == "dismissed" and f2["resolved_by"] == "dream:jev"
    e3 = _conflict_env(0.5)
    e3.night(phases=PHASES)
    f3 = e3.findings(type="conflict")[0]
    assert f3["status"] == "open" and f3["jev"]["decision"] == "review"


def _cold_env(p):
    e = make_env(jev_enabled=True)
    old = NOW - timedelta(days=100)
    e.index(T1, mk_card("faq", "idle", "Idle note", "never touched", as_of=old, importance=0.25))
    for c in e.chunks(T1):
        c.updated_at = old
    e.ops.telemetry = Telemetry(True, {}, observed_since=NOW - timedelta(days=90))
    e.jev.script = {"keep_long_term": p}
    return e


def test_worth_keeping_verdicts():
    e = _cold_env(0.96)
    e.night(phases=PHASES)
    assert run(e.dstore.get_card_state(T1, "faq", "idle"))["keep"] is True and e.findings(type="jev_keep")
    e2 = _cold_env(0.03)
    e2.night(phases=PHASES)
    assert e2.live(T1, "faq", "idle")[0].importance == 0.15                           # lowered, never deleted
    f = e2.findings(type="jev_not_worth_keeping")[0]
    assert f["action"] == {"kind": "set_importance", "value": 0.2}                    # reversible: the value before JEV acted
