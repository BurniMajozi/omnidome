"""PAYE table selection, verification gating, rebates and hand-computed deductions.

All expected numbers are worked out by hand from the SARS figures in tax_tables.py (comments show the
arithmetic). Run from the repo root:  PYTHONPATH=. python -m pytest services/hr/tests -q
"""
import dataclasses
from datetime import date

import pytest

from services.hr import tax_tables as tt
from services.hr.tax_tables import TABLES, TaxTableUnavailable, compute_deductions, resolve_table

T25 = TABLES[2025]   # 2025/26
T26 = TABLES[2026]   # 2026/27
APPROX = dict(abs=0.006)


# ── selection by tax year ────────────────────────────────────────────────

@pytest.mark.parametrize("period,year", [
    ("2025-03", 2025), ("2026-02", 2025), ("2026-03", 2026), ("2027-02", 2026), ("2025-12", 2025), ("2026-01", 2025),
])
def test_tax_year_for_period_runs_march_to_february(period, year):
    assert tt.tax_year_for_period(period) == year


def test_period_must_be_yyyy_mm():
    for bad in ("2026", "2026-13", "26-08", "", "2026-8"):
        with pytest.raises(ValueError):
            tt.parse_period(bad)


def test_table_picked_by_period_not_by_today():
    assert resolve_table("2026-02") is T25
    assert resolve_table("2026-08") is T26
    assert resolve_table("2026-08").rebate_primary == 17_820.0
    assert resolve_table("2025-09").rebate_primary == 17_235.0


def test_verified_tables_carry_source_and_date():
    for t in (T25, T26):
        assert t.verified is True
        assert t.source_url.startswith("https://www.sars.gov.za/")
        assert t.verified_on == "2026-10-01"
    assert T25.version != T26.version
    assert T26.version.startswith("sars-2026/27@")


def test_year_without_loaded_figures_is_refused_even_with_acknowledgement():
    for period in ("2027-05", "2024-06"):
        with pytest.raises(TaxTableUnavailable) as e:
            resolve_table(period, allow_unverified=True)
        assert "not verified" in e.value.detail


def test_unverified_table_needs_acknowledgement(monkeypatch):
    fake = dataclasses.replace(T26, tax_year=2027, verified=False)
    monkeypatch.setitem(TABLES, 2027, fake)
    with pytest.raises(TaxTableUnavailable) as e:
        resolve_table("2027-05")
    assert e.value.tax_year == 2027
    assert "PAYE tables for tax year 2027/28 not verified" == e.value.detail
    assert resolve_table("2027-05", allow_unverified=True).version.endswith("-UNVERIFIED")


def test_tax_year_end_dates():
    assert tt.tax_year_end(2025) == date(2026, 2, 28)
    assert tt.tax_year_end(2027) == date(2028, 2, 29)


# ── tax on annual income (bracket arithmetic) ────────────────────────────

def test_2025_bracket_edges_and_interior():
    assert T25.tax_on_annual(237_100) == pytest.approx(42_678.0)                       # 18% x 237,100
    assert T25.tax_on_annual(300_000) == pytest.approx(59_032.0)                       # 42,678 + 26% x 62,900
    assert T25.tax_on_annual(1_000_000) == pytest.approx(309_519.0)                    # 251,258 + 41% x 142,100
    assert T25.tax_on_annual(2_000_000) == pytest.approx(726_839.0)                    # 644,489 + 45% x 183,000


def test_2026_bracket_edges_and_interior():
    assert T26.tax_on_annual(245_100) == pytest.approx(44_118.0)                       # 18% x 245,100
    assert T26.tax_on_annual(300_000) == pytest.approx(58_392.0)                       # 44,118 + 26% x 54,900
    assert T26.tax_on_annual(1_200_000) == pytest.approx(388_113.0)                    # 259,783 + 41% x 313,000
    assert T26.tax_on_annual(2_000_000) == pytest.approx(720_969.0)                    # 666,339 + 45% x 121,400


def test_brackets_are_continuous():
    for t in (T25, T26):
        for (lo, up, base, rate), (lo2, _up2, base2, _r2) in zip(t.brackets, t.brackets[1:]):
            assert up == lo2
            assert base + (up - lo) * rate == pytest.approx(base2, abs=1.0)


# ── monthly deductions, 2025/26 (hand computed) ──────────────────────────

def test_2025_monthly_20000_primary_rebate_only():
    # annual 240,000 -> 42,678 + 26% x 2,900 = 43,432; - 17,235 = 26,197; /12 = 2,183.0833
    d = compute_deductions(T25, 20_000)
    assert d["tax"] == pytest.approx(2_183.08, **APPROX)
    assert d["uif"] == pytest.approx(177.12, **APPROX)            # 1% of the R17,712 ceiling
    assert d["uif_employer"] == pytest.approx(177.12, **APPROX)
    assert d["sdl"] == pytest.approx(200.0, **APPROX)
    assert d["net"] == pytest.approx(17_639.80, **APPROX)         # 20,000 - 2,183.08 - 177.12
    assert d["annual_taxable"] == pytest.approx(240_000.0)
    assert (d["tax_year"], d["table_version"]) == (2025, T25.version)


def test_2025_monthly_10000():
    # annual 120,000 x 18% = 21,600; - 17,235 = 4,365; /12 = 363.75; UIF 100
    d = compute_deductions(T25, 10_000)
    assert d["tax"] == pytest.approx(363.75, **APPROX)
    assert d["uif"] == pytest.approx(100.0, **APPROX)
    assert d["net"] == pytest.approx(9_536.25, **APPROX)


def test_2025_monthly_8000_just_above_threshold():
    # annual 96,000 x 18% = 17,280; - 17,235 = 45; /12 = 3.75
    d = compute_deductions(T25, 8_000)
    assert d["tax"] == pytest.approx(3.75, **APPROX)


def test_below_threshold_pays_no_paye():
    d = compute_deductions(T25, 7_000)   # 84,000 x 18% = 15,120 < 17,235
    assert d["tax"] == 0.0


def test_2025_bonus_month_uses_annual_payment_method_not_x12():
    # regular 30,000: annual 360,000 -> 42,678 + 26% x 122,900 = 74,632; - 17,235 = 57,397 -> 4,783.0833/month
    # with 30,000 bonus: 390,000 -> 77,362 + 31% x 19,500 = 83,407; - 17,235 = 66,172
    # bonus tax = 66,172 - 57,397 = 8,775; total = 4,783.0833 + 8,775 = 13,558.0833
    d = compute_deductions(T25, 30_000, irregular=30_000)
    assert d["tax_regular"] == pytest.approx(4_783.08, **APPROX)
    assert d["tax_irregular"] == pytest.approx(8_775.0, **APPROX)
    assert d["tax"] == pytest.approx(13_558.08, **APPROX)
    assert d["gross"] == pytest.approx(60_000.0)
    assert d["annual_taxable"] == pytest.approx(390_000.0)
    # the old behaviour (60,000 x 12 = 720,000): (179,147 + 39% x 47,000 - 17,235)/12 = 15,020.17 -> overstated
    old = (T25.tax_on_annual(720_000) - 17_235) / 12
    assert old == pytest.approx(15_020.17, abs=0.01)
    assert d["tax"] < old


def test_2025_age_rebates():
    # tax before rebates on 240,000 = 43,432
    d65 = compute_deductions(T25, 20_000, age=66)    # rebates 17,235 + 9,444 = 26,679 -> 16,753/12
    assert d65["tax"] == pytest.approx(1_396.08, **APPROX)
    assert d65["tax_rebate"] == pytest.approx(26_679.0)
    d75 = compute_deductions(T25, 20_000, age=76)    # + 3,145 = 29,824 -> 13,608/12
    assert d75["tax"] == pytest.approx(1_134.0, **APPROX)
    assert d75["tax_rebate"] == pytest.approx(29_824.0)
    assert compute_deductions(T25, 20_000, age=64)["tax"] == pytest.approx(2_183.08, **APPROX)
    assert compute_deductions(T25, 20_000, age=None)["age_known"] is False


def test_2025_medical_credits():
    # 3 members: 364 + 364 + 246 = 974 per month
    d = compute_deductions(T25, 20_000, medical_members=3)
    assert T25.medical_credit_monthly(3) == 974.0
    assert d["tax"] == pytest.approx(2_183.08 - 974.0, **APPROX)
    assert compute_deductions(T25, 8_000, medical_members=1)["tax"] == 0.0   # credit cannot go negative


# ── monthly deductions, 2026/27 (hand computed) ──────────────────────────

def test_2026_monthly_20000():
    # annual 240,000 <= 245,100 -> 18% = 43,200; - 17,820 = 25,380; /12 = 2,115.00
    d = compute_deductions(T26, 20_000)
    assert d["tax"] == pytest.approx(2_115.0, **APPROX)
    assert d["net"] == pytest.approx(20_000 - 2_115.0 - 177.12, **APPROX)


def test_2026_monthly_30000():
    # annual 360,000 -> 44,118 + 26% x 114,900 = 73,992; - 17,820 = 56,172; /12 = 4,681.00
    assert compute_deductions(T26, 30_000)["tax"] == pytest.approx(4_681.0, **APPROX)


def test_2026_monthly_100000_top_bands_and_uif_cap():
    # annual 1,200,000 -> 388,113; - 17,820 = 370,293; /12 = 30,857.75
    d = compute_deductions(T26, 100_000)
    assert d["tax"] == pytest.approx(30_857.75, **APPROX)
    assert d["uif"] == pytest.approx(177.12, **APPROX)      # capped at R17,712 x 1%


def test_2026_bonus():
    # regular 30,000 -> 56,172 after rebate; with 50,000 bonus: 410,000 -> 79,998 + 31% x 26,900 = 88,337; - 17,820 = 70,517
    # bonus tax = 70,517 - 56,172 = 14,345; total = 4,681 + 14,345 = 19,026
    d = compute_deductions(T26, 30_000, irregular=50_000)
    assert d["tax_irregular"] == pytest.approx(14_345.0, **APPROX)
    assert d["tax"] == pytest.approx(19_026.0, **APPROX)


def test_2026_age_rebates_and_medical():
    # 66 -> rebates 17,820 + 9,765 = 27,585: (43,200 - 27,585)/12 = 1,301.25
    assert compute_deductions(T26, 20_000, age=66)["tax"] == pytest.approx(1_301.25, **APPROX)
    # 75+ adds 3,249: (43,200 - 30,834)/12 = 1,030.50
    assert compute_deductions(T26, 20_000, age=75)["tax"] == pytest.approx(1_030.5, **APPROX)
    assert T26.medical_credit_monthly(1) == 376.0 and T26.medical_credit_monthly(4) == 376 + 376 + 2 * 254


def test_sdl_only_when_applicable():
    assert compute_deductions(T26, 20_000, sdl_applies=False)["sdl"] == 0.0
    assert T26.sdl_payroll_threshold == 500_000.0


# ── age from date of birth / SA ID ──────────────────────────────────────

def test_age_on_last_day_of_tax_year():
    end = date(2027, 2, 28)
    assert tt.age_on(date(1962, 2, 28), end) == 65
    assert tt.age_on(date(1962, 3, 1), end) == 64
    assert tt.age_on(None, end) is None


def test_dob_from_sa_id():
    assert tt.dob_from_sa_id("6001015800086") == date(1960, 1, 1)
    assert tt.dob_from_sa_id("0502285800086") == date(2005, 2, 28)
    assert tt.dob_from_sa_id("0502295800086") is None     # 29 Feb 2005 does not exist
    assert tt.dob_from_sa_id("123") is None
    assert tt.dob_from_sa_id(None) is None
    assert tt.dob_from_sa_id("9913325800086") is None    # month 13
