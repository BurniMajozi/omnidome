from datetime import timedelta

from services.tenant_memory.knowledge.dream import relevance as R
from services.tenant_memory.knowledge.dream.ports import Telemetry, Usage
from services.tenant_memory.knowledge.dream.settings import DreamSettings
from services.tenant_memory.knowledge.dream.store import COLD_TAG, STALE_TAG

from .helpers import NOW, T1, make_env, mk_card, run

CFG = DreamSettings(importance_max_step=0.05, importance_max_drift=0.25, min_samples=5, decay_after_days=60)
HOT = Usage(retrieved=10, used=9, cited=8, up=3)
COLD = Usage(retrieved=10, used=0, cited=0, down=2)


def plan(**kw):
    a = dict(base=0.5, current=0.5, protected=False, usage=HOT, age_days=10, telemetry_days=90, cfg=CFG)
    a.update(kw)
    return R.plan_adjustment(**a)


def test_usefulness_weights():
    assert R.usefulness(Usage(retrieved=10, cited=10, used=10, up=5)) == 1.0 and R.usefulness(Usage(retrieved=10)) == 0.0


def test_adjustment_is_bounded_per_night_and_in_total():
    assert plan().new == 0.55                                              # one step up
    assert plan(current=0.74, base=0.5).new == 0.75                        # capped at base + 0.25
    assert plan(usage=COLD).new == 0.45
    assert plan(usage=COLD, current=0.25, base=0.5) is None                # already at the lowest allowed (base - 0.25): nothing to do
    assert plan(usage=COLD, base=0.2, current=0.12).new == 0.1             # absolute floor 0.1
    assert plan(usage=Usage(retrieved=2, cited=2)) is None                 # too few samples to say anything


def test_protected_cards_can_only_go_up_and_never_below_base():
    assert plan(usage=COLD, protected=True, base=0.9, current=0.9) is None
    assert plan(usage=COLD, protected=True, base=0.9, current=0.95).new == 0.9
    assert plan(usage=HOT, protected=True, base=0.9, current=0.9).new == 0.95
    assert R.is_protected("compliance.payroll_tax", [], 0.5) and R.is_protected("billing", ["POPIA"], 0.5) and R.is_protected("x", [], 1.0)
    assert not R.is_protected("support", ["ticket"], 0.5)


def test_normal_usage_eases_back_toward_base():
    mid = Usage(retrieved=10, cited=3, used=5)
    assert plan(usage=mid, current=0.6).new == 0.575 and plan(usage=mid, current=0.4).new == 0.425 and plan(usage=mid) is None


def test_never_retrieved_decays_only_with_a_long_enough_observation_window():
    assert plan(usage=None, age_days=90, telemetry_days=90).new == 0.45 and plan(usage=None, age_days=90, telemetry_days=90).cold
    assert plan(usage=None, age_days=90, telemetry_days=10) is None        # telemetry too young: absence proves nothing
    assert plan(usage=None, age_days=10, telemetry_days=90) is None
    assert plan(usage=None, age_days=90, telemetry_days=90, protected=True) is None
    assert plan(usage=None, age_days=90, telemetry_days=90, base=0.8, current=0.8) is None      # only low/normal importance decays


def test_conflict_signal():
    assert "figures" in R.conflict_signal("the router costs r499 per month for fibre", "the router costs r599 per month for fibre")
    assert "status" in R.conflict_signal("the account is active and fibre line works", "the account is cancelled and fibre line works")
    assert R.conflict_signal("totally unrelated text about invoices", "weather in johannesburg is sunny today") is None
    assert R.conflict_signal("same words same figure 10", "same words same figure 10") is None


def _env_with_telemetry():
    e = make_env(importance_max_step=0.05)
    old = NOW - timedelta(days=100)
    e.index(T1, mk_card("faq", "hot", "Router reset steps", "hold reset ten seconds", as_of=old), mk_card("faq", "meh", "Old banner", "nobody reads", as_of=old),
            mk_card("faq", "idle", "Idle note", "never touched", as_of=old),
            mk_card("policy", "law", "POPIA retention rule", "keep records", as_of=old, module="compliance"))
    for c in e.chunks(T1):
        c.updated_at = old
    e.ops.telemetry = Telemetry(True, {("faq", "hot"): Usage(retrieved=12, used=11, cited=10, up=4), ("faq", "meh"): Usage(retrieved=9, down=3)},
                                observed_since=NOW - timedelta(days=90))
    return e


def test_importance_phase_nudges_logs_and_is_reversible():
    e = _env_with_telemetry()
    res = e.night(phases=["relevance"])
    assert res["phase_results"]["relevance"]["counts"]["importance_up"] == 1
    assert e.live(T1, "faq", "hot")[0].importance == 0.55 and e.live(T1, "faq", "meh")[0].importance == 0.45
    assert e.live(T1, "faq", "idle")[0].importance == 0.45 and COLD_TAG in e.live(T1, "faq", "idle")[0].tags
    assert e.live(T1, "policy", "law")[0].importance == 0.5                         # compliance: protected from decay
    st = run(e.dstore.get_card_state(T1, "faq", "hot"))
    assert st["base"] == 0.5 and st["adjusted"] == 0.55
    f = [x for x in e.findings(type="importance_adjusted") if x["source_id"] == "hot"][0]
    assert f["detail"]["before"] == 0.5 and f["detail"]["after"] == 0.55 and f["action"] == {"kind": "set_importance", "value": 0.5}
    e.night(phases=["relevance"])                                                   # second night: another step, still anchored to the same base
    assert e.live(T1, "faq", "hot")[0].importance == 0.6 and run(e.dstore.get_card_state(T1, "faq", "hot"))["base"] == 0.5


def test_a_builder_reset_becomes_the_new_base():
    e = _env_with_telemetry()
    e.night(phases=["relevance"])
    e.index(T1, mk_card("faq", "hot", "Router reset steps", "changed text", as_of=NOW - timedelta(days=1), importance=0.7))     # reindex rewrites importance
    e.night(phases=["relevance"])
    assert run(e.dstore.get_card_state(T1, "faq", "hot"))["base"] == 0.7 and e.live(T1, "faq", "hot")[0].importance == 0.75


def test_missing_telemetry_changes_nothing_and_says_so():
    e = _env_with_telemetry()
    e.ops.telemetry = Telemetry(False, note="table retrieval_log does not exist yet")
    res = e.night(phases=["relevance"])
    assert all(c.importance == 0.5 for c in e.chunks(T1)) and any("telemetry unavailable" in n for n in res["phase_results"]["relevance"]["notes"])


def test_keep_flag_from_jev_protects_a_card_from_decay():
    e = _env_with_telemetry()
    run(e.dstore.put_card_state(T1, "faq", "idle", {"keep": True, "base": 0.5}))
    e.night(phases=["relevance"])
    assert e.live(T1, "faq", "idle")[0].importance == 0.5


def test_dry_run_proposes_but_changes_nothing():
    e = _env_with_telemetry()
    e.night(phases=["relevance"], dry_run=True)
    assert all(c.importance == 0.5 and not c.tags for c in e.chunks(T1)) and run(e.dstore.get_card_state(T1, "faq", "hot")) is None
    assert {f["status"] for f in e.findings(type="importance_adjusted")} == {"proposed"}


def test_conflicting_cards_become_review_items_identical_ones_merge_only_for_allowed_types():
    e = make_env()
    e.index(T1, mk_card("price", "a", "Router price", "router costs r499 per month fibre line", importance=0.5),
            mk_card("price", "b", "Router price", "router costs r599 per month fibre line", importance=0.5),
            mk_card("memory_entry", "m1", "Decision", "use vendor alpha for installs", importance=0.5),
            mk_card("memory_entry", "m2", "Decision", "use vendor alpha for installs", importance=0.5),
            mk_card("note", "n1", "Same note", "identical body text here", importance=0.5),
            mk_card("note", "n2", "Same note", "identical body text here", importance=0.5))
    e.night(phases=["relevance"])
    c = e.findings(type="conflict")
    assert len(c) == 1 and c[0]["status"] == "open" and c[0]["action"]["kind"] == "review" and "figures" in c[0]["detail"]["signal"]
    assert e.live(T1, "price", "a") and e.live(T1, "price", "b")                    # conflicts are never auto-merged
    assert e.live(T1, "memory_entry", "m1") and not e.live(T1, "memory_entry", "m2")  # identical + allowed type: merged (derived card only)
    assert e.live(T1, "note", "n1") and e.live(T1, "note", "n2")                      # identical but not allowed: review item only
    dup = {f["source_id"]: f for f in e.findings(type="duplicate_identical")}
    assert dup["m2"]["status"] == "auto_applied" and dup["n2"]["status"] == "open" and dup["n2"]["action"]["kind"] == "tombstone"


def test_cards_injected_often_but_never_cited_lose_priority():
    used_only = Usage(retrieved=12, used=10, cited=0)
    assert plan(usage=used_only).new == 0.45 and "never cited" in plan(usage=used_only).reason
    assert plan(usage=Usage(retrieved=6, used=6, cited=0)) is None                # not enough evidence yet (needs 2x the minimum samples)
    assert plan(usage=Usage(retrieved=12, used=10, cited=0, up=3)) is None            # people liked it: not demoted


def test_cards_the_judge_keeps_finding_out_of_date_are_marked_stale_and_queued_for_refresh():
    e = _env_with_telemetry()
    e.ops.telemetry.usage[("faq", "idle")] = Usage(retrieved=6, used=2, cited=1, not_current=4)
    e.night(phases=["relevance"])
    assert STALE_TAG in e.live(T1, "faq", "idle")[0].tags
    f = e.findings(type="judge_flags_stale")[0]
    assert f["action"]["kind"] == "refresh" and f["detail"] == {"not_current": 4, "retrieved": 6}
