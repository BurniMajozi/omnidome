"""Versioned South African PAYE / UIF / SDL tables and the payroll deduction calculation.

Every figure in a table with ``verified=True`` was read from an official SARS source on the
date in ``verified_on`` (see ``source_url``). A tax year with no confirmed figures is NOT
filled in from memory: it is either absent from ``TABLES`` or present with
``verified=False``. ``POST /payroll/runs`` refuses (503) to use such a table unless an HR
admin sends ``acknowledge_unverified_tables: true`` (and then only if figures exist at all).

Tax year key: the calendar year in which the SA tax year STARTS. ``2025`` is the 2025/26 tax
year (1 March 2025 - 28 February 2026). SARS labels the same year "2026" on its pages.

PAYE method (documented, simplified, no retirement-fund / other deductions):

* Regular remuneration (basic salary + regular allowances) is annualised x12.
  Monthly PAYE on it = max(0, (tax(annual_regular) - rebates) / 12 - monthly medical credit).
* Irregular remuneration (approved bonus / commission claims paid in the period) is NOT
  annualised. It is taxed with the SARS annual-payment method: the extra tax caused by adding
  it to the annualised regular remuneration,
      max(0, tax(regular + irregular) - rebates) - max(0, tax(regular) - rebates).
  This is what stops a bonus month being taxed as if it recurred 12 times.
* Rebates: primary always; + secondary when the employee is 65 or older, + tertiary when 75
  or older, judged on the last day of the tax year. With no date of birth only the primary
  rebate is used and the result is flagged ``age_unknown``.
* UIF: employee and employer each ``uif_rate`` of remuneration up to the monthly ceiling.
* SDL: employer ``sdl_rate`` of remuneration, only when the annual payroll exceeds
  ``sdl_payroll_threshold``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional, Tuple

# (lower bound exclusive, upper bound inclusive, tax at lower bound, marginal rate)
Bracket = Tuple[float, float, float, float]

_INF = float("inf")


@dataclass(frozen=True)
class TaxTable:
    tax_year: int                       # start year; 2025 == 2025/26
    brackets: Tuple[Bracket, ...]
    rebate_primary: float
    rebate_secondary: float             # added at 65+
    rebate_tertiary: float              # added at 75+
    threshold_under_65: float
    threshold_65: float
    threshold_75: float
    uif_rate: float
    uif_monthly_cap: float
    sdl_rate: float
    sdl_payroll_threshold: float        # annual leviable payroll at/below which no SDL is due
    medical_credit_main: float          # per month
    medical_credit_first_dependant: float
    medical_credit_additional: float
    source_url: str
    verified_on: str                    # ISO date the figures were read from the source
    verified: bool
    notes: str = ""

    @property
    def label(self) -> str:
        return f"{self.tax_year}/{str(self.tax_year + 1)[-2:]}"

    @property
    def version(self) -> str:
        return f"sars-{self.label}@{self.verified_on}" + ("" if self.verified else "-UNVERIFIED")

    def medical_credit_monthly(self, members: int) -> float:
        n = max(0, int(members or 0))
        if n == 0:
            return 0.0
        total = self.medical_credit_main
        if n >= 2:
            total += self.medical_credit_first_dependant
        if n > 2:
            total += (n - 2) * self.medical_credit_additional
        return total

    def rebates_for_age(self, age: Optional[int]) -> float:
        total = self.rebate_primary
        if age is not None and age >= 65:
            total += self.rebate_secondary
        if age is not None and age >= 75:
            total += self.rebate_tertiary
        return total

    def tax_on_annual(self, taxable: float) -> float:
        """Annual tax on taxable income before rebates and credits."""
        t = max(0.0, float(taxable))
        for lower, upper, base, rate in self.brackets:
            if t <= upper:
                return base + (t - lower) * rate
        return 0.0  # unreachable: last bracket is unbounded


# 2025/26: SARS "Rates of tax for individuals" (page: "12 March 2025 - No changes") and the SARS
# employer guide PAYE-GEN-01-G20 (2026 tax year) both give these figures; read 2026-10-01.
_T_2025 = TaxTable(
    tax_year=2025,
    brackets=(
        (0.0, 237_100.0, 0.0, 0.18),
        (237_100.0, 370_500.0, 42_678.0, 0.26),
        (370_500.0, 512_800.0, 77_362.0, 0.31),
        (512_800.0, 673_000.0, 121_475.0, 0.36),
        (673_000.0, 857_900.0, 179_147.0, 0.39),
        (857_900.0, 1_817_000.0, 251_258.0, 0.41),
        (1_817_000.0, _INF, 644_489.0, 0.45),
    ),
    rebate_primary=17_235.0, rebate_secondary=9_444.0, rebate_tertiary=3_145.0,
    threshold_under_65=95_750.0, threshold_65=148_217.0, threshold_75=165_689.0,
    uif_rate=0.01, uif_monthly_cap=17_712.0,
    sdl_rate=0.01, sdl_payroll_threshold=500_000.0,
    medical_credit_main=364.0, medical_credit_first_dependant=364.0, medical_credit_additional=246.0,
    source_url="https://www.sars.gov.za/tax-rates/income-tax/rates-of-tax-for-individuals/",
    verified_on="2026-10-01",
    verified=True,
    notes=("Brackets/rebates/thresholds/medical credits: SARS employer guide PAYE-GEN-01-G20 "
           "(https://www.sars.gov.za/wp-content/uploads/Ops/Guides/PAYE-GEN-01-G20-Guide-for-Employers-iro-Employees-Tax-for-2026-External-Guide.pdf). "
           "UIF ceiling R17,712/month (since 1 June 2021) and SDL R500,000 payroll exemption: same guide."),
)

# 2026/27: SARS page "Rates of tax for individuals" (2027 tax year, updated 25 February 2026) and the
# SARS employer guide PAYE-GEN-01-G21 (2027 tax year); read 2026-10-01.
_T_2026 = TaxTable(
    tax_year=2026,
    brackets=(
        (0.0, 245_100.0, 0.0, 0.18),
        (245_100.0, 383_100.0, 44_118.0, 0.26),
        (383_100.0, 530_200.0, 79_998.0, 0.31),
        (530_200.0, 695_800.0, 125_599.0, 0.36),
        (695_800.0, 887_000.0, 185_215.0, 0.39),
        (887_000.0, 1_878_600.0, 259_783.0, 0.41),
        (1_878_600.0, _INF, 666_339.0, 0.45),
    ),
    rebate_primary=17_820.0, rebate_secondary=9_765.0, rebate_tertiary=3_249.0,
    threshold_under_65=99_000.0, threshold_65=153_250.0, threshold_75=171_300.0,
    uif_rate=0.01, uif_monthly_cap=17_712.0,
    sdl_rate=0.01, sdl_payroll_threshold=500_000.0,
    medical_credit_main=376.0, medical_credit_first_dependant=376.0, medical_credit_additional=254.0,
    source_url="https://www.sars.gov.za/tax-rates/income-tax/rates-of-tax-for-individuals/",
    verified_on="2026-10-01",
    verified=True,
    notes=("Brackets/rebates/thresholds/medical credits: SARS employer guide PAYE-GEN-01-G21 "
           "(https://www.sars.gov.za/wp-content/uploads/Ops/Guides/PAYE-GEN-01-G21-Guide-for-Employers-iro-Employees-Tax-for-2027-External-Guide.pdf). "
           "UIF ceiling and SDL exemption unchanged in that guide."),
)

# Years not listed here (e.g. 2024/25 and 2027/28) have NO confirmed figures and are not guessed.
TABLES: Dict[int, TaxTable] = {_T_2025.tax_year: _T_2025, _T_2026.tax_year: _T_2026}


class TaxTableUnavailable(Exception):
    def __init__(self, tax_year: int, detail: str):
        super().__init__(detail)
        self.tax_year = tax_year
        self.detail = detail


_PERIOD_RE = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")


def parse_period(period: str) -> Tuple[int, int]:
    m = _PERIOD_RE.match((period or "").strip())
    if not m:
        raise ValueError("period must look like YYYY-MM")
    return int(m.group(1)), int(m.group(2))


def tax_year_for_period(period: str) -> int:
    """SA tax year (start year) a pay period falls in: 1 March .. end February."""
    year, month = parse_period(period)
    return year if month >= 3 else year - 1


def tax_year_end(tax_year: int) -> date:
    return date(tax_year + 1, 2, 29 if _is_leap(tax_year + 1) else 28)


def _is_leap(y: int) -> bool:
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def resolve_table(period: str, allow_unverified: bool = False) -> TaxTable:
    ty = tax_year_for_period(period)
    table = TABLES.get(ty)
    label = f"{ty}/{str(ty + 1)[-2:]}"
    if table is None:
        raise TaxTableUnavailable(ty, f"PAYE tables for tax year {label} not verified (no confirmed SARS figures are loaded)")
    if not table.verified and not allow_unverified:
        raise TaxTableUnavailable(ty, f"PAYE tables for tax year {label} not verified")
    return table


def age_on(dob: Optional[date], on: date) -> Optional[int]:
    if dob is None:
        return None
    return on.year - dob.year - ((on.month, on.day) < (dob.month, dob.day))


def dob_from_sa_id(id_number: Optional[str]) -> Optional[date]:
    """Date of birth encoded in a 13-digit South African ID (YYMMDD...). The century is the
    latest one that is not in the future. None if the number is not a plausible SA ID."""
    s = re.sub(r"\s", "", id_number or "")
    if not re.fullmatch(r"\d{13}", s):
        return None
    yy, mm, dd = int(s[0:2]), int(s[2:4]), int(s[4:6])
    today = date.today()
    for century in (2000, 1900):
        try:
            d = date(century + yy, mm, dd)
        except ValueError:
            return None
        if d <= today:
            return d
    return None


def compute_deductions(
    table: TaxTable,
    regular_monthly: float,
    irregular: float = 0.0,
    age: Optional[int] = None,
    medical_members: int = 0,
    other_deductions: float = 0.0,
    sdl_applies: bool = True,
) -> dict:
    """Payslip statutory deductions for one month. See the module docstring for the method."""
    regular = max(0.0, float(regular_monthly))
    irregular = max(0.0, float(irregular or 0.0))
    gross = regular + irregular
    rebates = table.rebates_for_age(age)
    annual_regular = regular * 12.0
    annual_taxable = annual_regular + irregular  # taxable income the PAYE is computed on

    tax_regular_annual = max(0.0, table.tax_on_annual(annual_regular) - rebates)
    med_credit = table.medical_credit_monthly(medical_members)
    paye_regular = max(0.0, tax_regular_annual / 12.0 - med_credit)
    paye_irregular = 0.0
    if irregular > 0:
        paye_irregular = max(0.0, table.tax_on_annual(annual_taxable) - rebates) - tax_regular_annual
        paye_irregular = max(0.0, paye_irregular)
    tax = round(paye_regular + paye_irregular, 2)

    uif = round(min(gross, table.uif_monthly_cap) * table.uif_rate, 2)
    sdl = round(gross * table.sdl_rate, 2) if sdl_applies else 0.0
    net = round(gross - tax - uif - other_deductions, 2)
    return {
        "tax_year": table.tax_year,
        "table_version": table.version,
        "table_verified": table.verified,
        "gross": round(gross, 2),
        "annual_taxable": round(annual_taxable, 2),
        "annual_gross": round(annual_taxable, 2),
        "tax_annual": round(table.tax_on_annual(annual_taxable), 2),
        "tax_rebate": round(rebates, 2),
        "medical_credit": round(med_credit, 2),
        "tax_regular": round(paye_regular, 2),
        "tax_irregular": round(paye_irregular, 2),
        "tax": tax,
        "uif": uif,
        "uif_employer": uif,
        "sdl": sdl,
        "other": other_deductions,
        "net": net,
        "age_known": age is not None,
        "age": age,
    }


def table_summary(table: TaxTable) -> dict:
    return {
        "tax_year": table.label, "version": table.version, "verified": table.verified,
        "verified_on": table.verified_on, "source_url": table.source_url,
    }
