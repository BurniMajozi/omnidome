"""Numbers-by-reference: token evaluation/formatting, ungrounded-number detection, AI text sanitising, insights."""

import pytest

from services.fno_intelligence import bi_insights as ins
from services.fno_intelligence import bi_tokens as tk

COLS = [{"id": "created_at", "kind": "time", "type": "time", "label": "Invoice date"},
        {"id": "invoiced", "kind": "measure", "type": "number", "format": "currency_zar", "additive": True, "label": "Invoiced"},
        {"id": "rate", "kind": "measure", "type": "number", "format": "percent", "additive": False, "label": "Rate"}]
RES = {"q1": {"columns": COLS, "rows": [["2026-01-01", 1000.0, 0.5], ["2026-02-01", 1100.0, 0.6], ["2026-03-01", 1800.0, 0.9]],
              "totals": {"invoiced": 3900.0, "rate": 0.7}}}
CAT = {"q2": {"columns": [{"id": "plan", "kind": "dimension", "type": "category", "label": "Plan"}, COLS[1]],
              "rows": [["Gold", 3000.0], ["Silver", 700.0], ["Bronze", 200.0]], "totals": {"invoiced": 3900.0}}}


def test_formats():
    f = tk.format_value
    assert f(1234567.891, "currency") == "R1 234 568" and f(12.5, "currency") == "R12.50" and f(-2500, "currency") == "-R2 500"
    assert f(1234567, "currency_compact") == "R1.2m" and f(2500, "currency_compact") == "R2.5k" and f(3e9, "currency_compact") == "R3bn"
    assert f(0.4567, "percent") == "45.7%" and f(0.4567, "percent0") == "46%" and f(-0.1, "signed_percent") == "-10.0%"
    assert f(0.1, "signed_percent") == "+10.0%" and f(1500, "signed_currency") == "+R1 500"
    assert f(42, "number") == "42" and f(1500000, "number") == "1 500 000" and f(2.456, "number") == "2.46"
    assert f(0.5, "duration") == "30 min" and f(5.25, "duration") == "5.2 h" and f(72, "duration") == "3.0 days"
    assert f("abc", "text") == "abc"
    with pytest.raises(tk.TokenError):
        f(1, "bogus")
    with pytest.raises(tk.TokenError):
        f("x", "currency")
    with pytest.raises(tk.TokenError):
        f(float("nan"), "number")


def test_evaluate_paths():
    ev = lambda body, res=RES: tk.evaluate(body, res)  # noqa: E731
    assert ev("q1.total") == (3900.0, "currency") and ev("q1.invoiced") == (3900.0, "currency")
    assert ev("q1.invoiced.last") == (1800.0, "currency") and ev("q1.last") == (1800.0, "currency")   # first measure is the default
    assert ev("q1.invoiced.prev")[0] == 1100.0 and ev("q1.invoiced.first")[0] == 1000.0
    assert ev("q1.invoiced.delta")[0] == 700.0
    assert ev("q1.invoiced.delta_pct") == (pytest.approx(700 / 1100), "signed_percent")
    assert ev("q1.rate.last")[1] == "percent" and ev("q1.rate.total")[0] == 0.7
    assert ev("q1.invoiced.max")[0] == 1800.0 and ev("q1.invoiced.min")[0] == 1000.0 and ev("q1.invoiced.avg")[0] == pytest.approx(3900 / 3)
    assert ev("q1.rows") == (3, "number")
    assert ev("q1.invoiced.last.label") == ("2026-03-01", "text") and ev("q1.invoiced.first.label")[0] == "2026-01-01"
    assert ev("q1.invoiced.row2.value")[0] == 1100.0 and ev("q1.invoiced.row2.label")[0] == "2026-02-01"
    assert ev("q2.top1.label", CAT) == ("Gold", "text") and ev("q2.invoiced.top1.value", CAT)[0] == 3000.0
    assert ev("q2.top1.share", CAT) == (pytest.approx(3000 / 3900), "percent")
    assert ev("q2.bottom1.label", CAT)[0] == "Bronze" and ev("q2.top2.label", CAT)[0] == "Silver"
    for bad in ("zz.total", "q1.invoiced.weird", "q1.invoiced.last.value", "q1.invoiced.total.extra", "", "q1.row9.value", "q1.top4.label"):
        with pytest.raises(tk.TokenError):
            ev(bad)
    with pytest.raises(tk.TokenError):
        tk.evaluate("q1.rate.top1.share", {"q1": RES["q1"]})            # share needs an additive measure
    zero = {"q": {"columns": COLS[:2], "rows": [["a", 0.0], ["b", 5.0]], "totals": {"invoiced": 5.0}}}
    with pytest.raises(tk.TokenError):
        tk.evaluate("q.delta_pct", zero)                                 # previous period zero: undefined, never inf
    one = {"q": {"columns": COLS[:2], "rows": [["a", 1.0]], "totals": {"invoiced": 1.0}}}
    with pytest.raises(tk.TokenError):
        tk.evaluate("q.delta", one)


def test_resolve_text():
    out, un = tk.resolve_text("Total {{q1.invoiced}} ({{q1.invoiced.delta_pct}}), peak {{ q1.invoiced.max | currency_compact }}; "
                              "rate {{q1.rate.last|percent0}}.", RES)
    assert out == "Total R3 900 (+63.6%), peak R1.8k; rate 90%." and un == []
    out, un = tk.resolve_text("A {{nope.total}} B {{q1.invoiced|bogus}} C {{?}} D", RES)
    assert out == "A — B — C [add figure] D" and len(un) == 3
    assert tk.resolve_text("", RES) == ("", [])
    assert tk.resolve_ref("q1.invoiced.last", RES) == "R1 800"
    assert tk.resolve_ref("q1.invoiced.last", RES, "number") == "1 800"


def test_validate_token_refs_static():
    qm = {"q1": ["invoiced", "rate"], "empty": []}
    ok = "{{q1.invoiced}} {{q1.last}} {{q1.rate.delta_pct|percent}} {{q1.invoiced.top1.label}} {{q1.row3.value}} {{?}} {{empty.rows}}"
    assert tk.validate_token_refs(ok, qm) == []
    for bad in ("{{zz.total}}", "{{q1.nothing}}", "{{q1.invoiced.last.value}}", "{{q1.invoiced|bogus}}", "{{empty.total}}", "{{q1.invoiced.a.b.c}}"):
        assert tk.validate_token_refs(bad, qm), bad


@pytest.mark.parametrize("text_,literals", [
    ("Revenue grew 15% to R1 200 000.", ["15%", "R1 200 000"]),
    ("We added 3 customers and 1,234.50 more", ["3", "1,234.50"]),
    ("Revenue was {{q1.total}} in 2026, up {{q1.delta_pct}} in Q3 and H1 (FY25).", []),
    ("About two million homes passed, a hundred partners", ["two million", "a hundred"]),
    ("Available 24/7 on 4G and 5G with B2B plans", []),
    ("1. First point\n2. Second point", []),
    ("Top 3 segments by 50%", ["3", "50%"]),
    ("R5k and 7m and 2bn", ["R5k", "7m", "2bn"]),
    ("Since 1998 and in 2031", []),
])
def test_find_ungrounded(text_, literals):
    assert [g["literal"] for g in tk.find_ungrounded(text_)] == literals


def test_sanitise_ai_text_replaces_invented_figures_and_bad_tokens():
    qm = {"q1": ["invoiced"]}
    text_, rep = tk.sanitise_ai_text("Revenue hit R2 500 000, up 12% on {{q1.invoiced.last}} and {{q9.total}} and {{q1.fake}}.", qm)
    assert "2 500 000" not in text_ and "12%" not in text_ and "{{q9.total}}" not in text_ and "{{q1.fake}}" not in text_
    assert text_.count(tk.PLACEHOLDER) == 4 and "{{q1.invoiced.last}}" in text_
    assert rep["ungrounded_numbers"] == ["R2 500 000", "12%"] and len(rep["invalid_tokens"]) == 2
    assert tk.find_ungrounded(text_) == []            # nothing left that looks like a figure
    clean, rep = tk.sanitise_ai_text("No figures here, only {{q1.invoiced}}.", qm)
    assert clean == "No figures here, only {{q1.invoiced}}." and rep == {"ungrounded_numbers": [], "invalid_tokens": []}
    txt, _ = tk.sanitise_ai_text("Millions of homes and 3 million users", qm)
    assert not any(c.isdigit() for c in txt) and "million" not in txt.lower().replace("millions of homes", "")


def test_insights_are_deterministic_and_token_only():
    items = ins.compute_insights("q1", RES["q1"])
    kinds = {i["kind"] for i in items}
    assert "period_over_period" in kinds and "trend" in kinds
    for i in items:
        assert not tk.find_ungrounded(i["sentence"]), i["sentence"]               # sentences carry figures only as tokens
        out, un = tk.resolve_text(i["sentence"], RES)
        assert un == [] and "{{" not in out
    pop = next(i for i in items if i["kind"] == "period_over_period" and i["measure"] == "invoiced")
    assert pop["data"]["delta_pct"] == pytest.approx(700 / 1100)
    assert "rose" in pop["sentence"]
    cat_items = ins.compute_insights("q2", CAT["q2"])
    top = next(i for i in cat_items if i["kind"] == "top_share")
    assert top["data"]["share"] == pytest.approx(3000 / 3900)
    assert tk.resolve_text(top["sentence"], CAT)[0].startswith("Gold led on Invoiced with R3 000, 76.9% of the total")
    assert ins.compute_insights("q1", {"columns": COLS, "rows": [], "totals": {}}) == []
    assert ins.trend_direction([1, 2, 3, 4]) == "up" and ins.trend_direction([4, 3, 2, 1]) == "down" and ins.trend_direction([5, 5, 5.01]) == "flat"
    assert ins.trend_direction([1, 2]) is None
    assert ins.outlier_rows([10, 10, 10, 10, 10, 10, 10, 100]) == [7] and ins.outlier_rows([1, 2, 3]) == []
