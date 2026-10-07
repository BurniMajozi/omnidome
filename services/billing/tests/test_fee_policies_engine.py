"""Pure fee-engine tests (no DB): amortisation, month rules, cap/min, grace, waivers, router credit, VAT."""
import os
import sys
from datetime import date
from decimal import Decimal

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from services.billing import fee_policies as fp  # noqa: E402

D = Decimal
START = date(2026, 1, 15)
SNAP = {"router": D("1500"), "activation": D("500"), "installation": D("1000")}


def make_policy(**over):
    base = dict(
        name="t", components=[fp.ComponentIn(code="router"), fp.ComponentIn(code="activation"),
                              fp.ComponentIn(code="installation")],
        router_credit=fp.RouterCredit(enabled=True))
    base.update(over)
    p = fp.PolicyIn(**base)
    row = type("R", (), dict(config=fp.policy_config_from_input(p), id="pol-1", policy_key="key-1", version=1,
                             name=p.name, term_months=p.term_months, trigger_types=p.trigger_types,
                             applies_to_plans=p.applies_to_plans))()
    return fp.policy_to_engine(row)


def inputs(effective, **over):
    base = dict(trigger="cancellation", term_start=START, term_months=24, components=dict(SNAP),
                monthly_rental_zar=D("500"), plan_keys=[], effective_date=effective, snapshot_present=True)
    base.update(over)
    return base


def after_months(n, day=15):
    return fp.add_months(START, n).replace(day=day) if day != 15 else fp.add_months(START, n)


def totals(bd):
    return {k: str(v) for k, v in bd["totals"].items()}


def test_canonical_example_router_activation_install_cancel_after_10_months():
    bd = fp.calculate_fee(make_policy(), inputs(after_months(10)))
    assert bd["months_elapsed"] == 10 and bd["months_remaining"] == 14
    by = {l["code"]: l for l in bd["lines"]}
    assert by["router"]["amount"] == D("875.00")
    assert by["activation"]["amount"] == D("291.67")
    assert by["installation"]["amount"] == D("583.33")
    assert by["router"]["monthly_amortisation"] == D("62.50")
    t = bd["totals"]
    assert (t["fee_net"], t["fee_vat"], t["fee_total"]) == (D("1750.00"), D("262.50"), D("2012.50"))
    assert "1500.00 x 14/24 = 875.00" in bd["formula"]


@pytest.mark.parametrize("months,remaining,net", [(0, 24, "3000.00"), (23, 1, "125.00"), (24, 0, "0.00"), (25, 0, "0.00")])
def test_boundary_months(months, remaining, net):
    bd = fp.calculate_fee(make_policy(), inputs(after_months(months)))
    assert bd["months_remaining"] == remaining
    assert bd["totals"]["fee_net"] == D(net)
    assert ("term_completed" in bd["flags"]) == (remaining == 0)


def test_started_month_rounding_up_vs_down():
    mid = date(2026, 11, 29)  # 10 whole months + 14 days
    up = fp.calculate_fee(make_policy(), inputs(mid))
    down = fp.calculate_fee(make_policy(month_rule=fp.MonthRule(remaining_rounding="down")), inputs(mid))
    assert up["months_remaining"] == 14 and up["totals"]["fee_net"] == D("1750.00")
    assert down["months_remaining"] == 13 and down["totals"]["fee_net"] == D("1625.00")


def test_prorated_days_uses_fraction_of_current_month():
    # Nov 15 -> Dec 15 is 30 days; Nov 30 is 15 days in = exactly half a month
    bd = fp.calculate_fee(make_policy(month_rule=fp.MonthRule(mode="prorated_days")), inputs(date(2026, 11, 30)))
    assert bd["months_elapsed"] == D("10.5") and bd["months_remaining"] == D("13.5")
    assert bd["totals"]["fee_net"] == D("1687.50")  # 3000 x 13.5/24


def test_month_end_dates_count_complete_months():
    assert fp.whole_months_between(date(2026, 1, 31), date(2026, 2, 28)) == 1
    assert fp.whole_months_between(date(2026, 1, 31), date(2026, 2, 27)) == 0
    assert fp.whole_months_between(date(2026, 1, 15), date(2026, 1, 14)) == 0


def test_grace_period_waives_everything_and_is_transparent():
    pol = make_policy(grace_period_days=7)
    bd = fp.calculate_fee(pol, inputs(date(2026, 1, 20)))
    assert bd["totals"]["fee_total"] == D("0.00") and bd["totals"]["waived_total"] == D("3450.00")
    assert "grace_period_applied" in bd["flags"]
    assert any(l["kind"] == "waiver" and l["code"] == "grace_period" for l in bd["lines"])
    after = fp.calculate_fee(pol, inputs(date(2026, 1, 23)))  # day 8
    assert after["totals"]["fee_total"] == D("3450.00")


def test_max_cap_and_min_floor():
    capped = fp.calculate_fee(make_policy(max_fee_zar=D("1000")), inputs(after_months(10)))
    assert capped["totals"]["fee_net"] == D("1000.00") and "max_fee_applied" in capped["flags"]
    assert capped["totals"]["fee_total"] == D("1150.00")
    floored = fp.calculate_fee(make_policy(min_fee_zar=D("300")), inputs(after_months(23)))
    assert floored["totals"]["fee_net"] == D("300.00") and "min_fee_applied" in floored["flags"]
    none_owed = fp.calculate_fee(make_policy(min_fee_zar=D("300")), inputs(after_months(24)))
    assert none_owed["totals"]["fee_net"] == D("0.00")  # a minimum never creates a fee after the term


def test_router_credit_offset_mode():
    pol = make_policy()
    bd = fp.calculate_fee(pol, inputs(after_months(10), router_returned=True, router_condition="good"))
    assert bd["totals"]["fee_net"] == D("875.00")  # router 875 wiped
    assert bd["router_credit"]["applied"] is True
    missing = fp.calculate_fee(pol, inputs(after_months(10), router_returned=True, router_condition="missing_parts"))
    assert missing["totals"]["fee_net"] == D("1750.00") and missing["router_credit"]["applied"] is False
    not_returned = fp.calculate_fee(pol, inputs(after_months(10), router_returned=False))
    assert not_returned["totals"]["fee_net"] == D("1750.00")


def test_router_credit_by_condition_mode():
    pol = make_policy(router_credit=fp.RouterCredit(enabled=True, mode="credit_value_by_condition"))
    for cond, credit in (("new", "875.00"), ("good", "787.50"), ("fair", "525.00"), ("damaged", "218.75"), ("missing_parts", "0.00")):
        bd = fp.calculate_fee(pol, inputs(after_months(10), router_returned=True, router_condition=cond))
        assert D("1750.00") - bd["totals"]["fee_net"] == D(credit), cond
    unknown = fp.calculate_fee(pol, inputs(after_months(10), router_returned=True))
    assert unknown["totals"]["fee_net"] == D("1750.00") and "router_condition_unknown_no_credit" in unknown["flags"]


def test_router_credit_disabled_does_nothing():
    pol = make_policy(router_credit=fp.RouterCredit(enabled=False))
    bd = fp.calculate_fee(pol, inputs(after_months(10), router_returned=True, router_condition="new"))
    assert bd["totals"]["fee_net"] == D("1750.00")


def test_declining_flat_and_rental_methods():
    dec = fp.calculate_fee(make_policy(method="declining"), inputs(after_months(10)))
    # R3000 x (14 x 15) / (24 x 25) = 1050.00
    assert dec["totals"]["fee_net"] == D("1050.00")
    flat = fp.calculate_fee(make_policy(method="flat", flat_percent=D("50")), inputs(after_months(10)))
    assert flat["totals"]["fee_net"] == D("1500.00")
    assert fp.calculate_fee(make_policy(method="flat"), inputs(after_months(24)))["totals"]["fee_net"] == D("0.00")
    rental = fp.calculate_fee(
        make_policy(method="percent_of_remaining_rental", components=[], rental_percent=D("50")),
        inputs(after_months(10), monthly_rental_zar=D("699")))
    assert rental["totals"]["fee_net"] == D("4893.00")  # 699 x 14 x 50%


def test_vat_inclusive_extracts_vat_per_line():
    pol = make_policy(vat=fp.VatRule(rate=D("0.15"), treatment="inclusive"))
    bd = fp.calculate_fee(pol, inputs(after_months(10)))
    t = bd["totals"]
    assert t["fee_total"] == D("1750.00")
    assert t["fee_net"] + t["fee_vat"] == t["fee_total"]
    assert t["fee_vat"] == sum((l["vat"] for l in bd["lines"]), D("0"))
    zero_vat = fp.calculate_fee(make_policy(vat=fp.VatRule(rate=D("0"))), inputs(after_months(10)))
    assert zero_vat["totals"]["fee_vat"] == D("0.00") and zero_vat["totals"]["fee_total"] == D("1750.00")


def test_decimal_rounding_half_up_per_line_and_totals_consistent():
    bd = fp.calculate_fee(make_policy(), inputs(after_months(10), components={"router": D("100.05"), "activation": D("0.01"), "installation": D("33.33")}))
    by = {l["code"]: l for l in bd["lines"]}
    assert by["router"]["amount"] == D("58.36")        # 100.05 x 14/24 = 58.3625
    assert by["activation"]["amount"] == D("0.01")     # 0.00583 rounds to 0.01 (half-up on the cent grid)
    assert bd["totals"]["fee_net"] == sum((l["net"] for l in bd["lines"]), D("0"))
    assert bd["totals"]["fee_total"] == bd["totals"]["fee_net"] + bd["totals"]["fee_vat"]


def test_snapshot_missing_falls_back_to_fixed_and_flags():
    pol = make_policy(components=[fp.ComponentIn(code="router", fixed_amount=D("1200")),
                                  fp.ComponentIn(code="activation")])
    bd = fp.calculate_fee(pol, inputs(after_months(12), components={}, snapshot_present=False))
    assert "snapshot_missing" in bd["flags"]
    assert "component_router_not_in_snapshot_used_fixed" in bd["flags"]
    assert "component_activation_amount_unresolved" in bd["flags"]
    assert bd["totals"]["fee_net"] == D("600.00")


def test_catalog_source_by_plan():
    pol = make_policy(components=[fp.ComponentIn(code="router", amount_source="catalog")],
                      catalog_amounts={"router": {"Fibre 100": D("800"), "default": D("600")}})
    a = fp.calculate_fee(pol, inputs(after_months(12), components={}, plan_keys=["Fibre 100"]))
    b = fp.calculate_fee(pol, inputs(after_months(12), components={}, plan_keys=["Other"]))
    assert a["totals"]["fee_net"] == D("400.00") and b["totals"]["fee_net"] == D("300.00")


def test_not_recoverable_component_is_listed_but_zero():
    pol = make_policy(components=[fp.ComponentIn(code="router"), fp.ComponentIn(code="activation", recoverable=False)])
    bd = fp.calculate_fee(pol, inputs(after_months(10)))
    act = next(l for l in bd["lines"] if l["code"] == "activation")
    assert act["amount"] == D("0.00") and "not recoverable" in act["formula"]


def test_auto_waiver_vs_eligible_only():
    pol = make_policy(waivers=[
        fp.WaiverRule(reason_code="fno_fault", required_tier="none"),
        fp.WaiverRule(reason_code="death", required_tier="admin", waive_percent=D("50"))])
    auto = fp.calculate_fee(pol, inputs(after_months(10), reason_code="fno_fault"))
    assert auto["totals"]["fee_total"] == D("0.00") and "waiver_applied_fno_fault" in auto["flags"]
    elig = fp.calculate_fee(pol, inputs(after_months(10), reason_code="death"))
    assert elig["totals"]["fee_total"] == D("2012.50")  # not applied automatically
    e = elig["waiver_eligibility"][0]
    assert e["applied"] is False and e["required_tier"] == "admin" and e["indicative_gross"] == D("1006.25")
    plain = fp.calculate_fee(pol, inputs(after_months(10), reason_code="voluntary"))
    assert plain["waiver_eligibility"] == []


def test_manual_waiver_partial_and_full():
    pol = make_policy()
    bd = fp.calculate_fee(pol, inputs(after_months(10)))
    fp.apply_waiver_to_breakdown(bd, pol["vat"], code="w1", label="goodwill", reason_code="goodwill", amount_gross=D("500.00"))
    assert bd["totals"]["fee_total"] == D("1512.50") and bd["totals"]["waived_total"] == D("500.00")
    assert bd["totals"]["fee_net"] + bd["totals"]["fee_vat"] == bd["totals"]["fee_total"]
    fp.apply_waiver_to_breakdown(bd, pol["vat"], code="w2", label="rest", reason_code="goodwill", percent=D("100"))
    assert bd["totals"]["fee_total"] == D("0.00") and bd["totals"]["fee_net"] == D("0.00")
    with pytest.raises(ValueError):
        fp.apply_waiver_to_breakdown(bd, pol["vat"], code="w3", label="x", reason_code="x", percent=D("10"))


def test_approval_tier_needed():
    pol = make_policy(auto_approve_waiver_limit_zar=D("200"), waivers=[
        fp.WaiverRule(reason_code="fno_fault", required_tier="none"),
        fp.WaiverRule(reason_code="relocation_in_coverage", required_tier="clerk"),
        fp.WaiverRule(reason_code="death", required_tier="admin")])
    assert fp.approval_tier_needed(pol, "relocation_in_coverage", D("150")) == "clerk"
    assert fp.approval_tier_needed(pol, "relocation_in_coverage", D("200.01")) == "admin"
    assert fp.approval_tier_needed(pol, "death", D("1")) == "admin"
    assert fp.approval_tier_needed(pol, "fno_fault", D("50")) == "clerk"
    assert fp.approval_tier_needed(pol, "made_up_reason", D("1")) == "admin"


def test_deterministic_and_hash_sensitivity():
    pol = make_policy()
    i1 = inputs(after_months(10))
    assert fp.jsonable(fp.calculate_fee(pol, i1)) == fp.jsonable(fp.calculate_fee(pol, dict(i1)))
    h = fp.inputs_hash(pol, i1)
    assert h == fp.inputs_hash(pol, dict(i1))
    assert h != fp.inputs_hash(pol, inputs(after_months(11)))
    assert h != fp.inputs_hash(pol, inputs(after_months(10), router_returned=True, router_condition="good"))
    assert h != fp.inputs_hash(pol, inputs(after_months(10), components={**SNAP, "router": D("1600")}))
    assert h == fp.inputs_hash(pol, inputs(after_months(10), outstanding_balance_zar=D("999")))  # informational only


def test_downgrade_trigger_uses_same_engine():
    pol = make_policy(trigger_types=["downgrade"])
    bd = fp.calculate_fee(pol, inputs(after_months(10), trigger="downgrade"))
    assert bd["trigger"] == "downgrade" and bd["totals"]["fee_net"] == D("1750.00")


def test_outstanding_balance_include_vs_exclude():
    inc = fp.calculate_fee(make_policy(outstanding_balance="include"), inputs(after_months(10), outstanding_balance_zar=D("300")))
    exc = fp.calculate_fee(make_policy(), inputs(after_months(10), outstanding_balance_zar=D("300")))
    assert inc["totals"]["total_payable"] == D("2312.50") and exc["totals"]["total_payable"] == D("2012.50")


def test_policy_validation():
    with pytest.raises(ValueError):
        fp.PolicyIn(name="x", components=[])
    with pytest.raises(ValueError):
        fp.PolicyIn(name="x", components=[fp.ComponentIn(code="router", amount_source="fixed")])
    with pytest.raises(ValueError):
        fp.PolicyIn(name="x", components=[fp.ComponentIn(code="a"), fp.ComponentIn(code="a")])
    with pytest.raises(ValueError):
        fp.PolicyIn(name="x", components=[fp.ComponentIn(code="a")], min_fee_zar=D("5"), max_fee_zar=D("1"))
