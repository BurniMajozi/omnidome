"""Statutory payroll helpers (pure functions + config). NOTHING here talks to SARS.

Rates and thresholds are configuration with documented defaults. They are NOT
verified against the current SARS tables, so every output that uses them carries
`rates_verified: false`; an operator must confirm them on SARS before relying on
a figure. Override via environment:

    COMPLIANCE_UIF_RATE                       default 0.01   (employee 1% + employer 1%)
    COMPLIANCE_UIF_MONTHLY_CEILING            default 17712  (monthly remuneration ceiling)
    COMPLIANCE_SDL_RATE                       default 0.01
    COMPLIANCE_SDL_ANNUAL_PAYROLL_THRESHOLD   default 500000 (SDL applies only above this annual payroll)
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

PAID_RUN_STATUSES = ("PAID", "PARTIALLY_PAID")
FILING_NOTE = "File manually on SARS eFiling; enter the PRN/receipt here when done."
RATES_NOTE = "Rates/thresholds are configuration defaults; verify with SARS."

_PRN_RE = re.compile(r"[A-Za-z0-9]{16,19}")


def _env_float(key: str, default: float) -> float:
    try:
        return float(os.getenv(key, default))
    except (TypeError, ValueError):
        return float(default)


@dataclass(frozen=True)
class StatutoryRates:
    uif_rate: float
    uif_monthly_ceiling: float
    sdl_rate: float
    sdl_annual_payroll_threshold: float
    rates_verified: bool = False

    def as_dict(self) -> dict:
        return {
            "uif_rate": self.uif_rate,
            "uif_monthly_remuneration_ceiling_zar": self.uif_monthly_ceiling,
            "sdl_rate": self.sdl_rate,
            "sdl_annual_payroll_threshold_zar": self.sdl_annual_payroll_threshold,
            "rates_verified": self.rates_verified,
            "note": RATES_NOTE,
        }


def load_rates() -> StatutoryRates:
    return StatutoryRates(
        uif_rate=_env_float("COMPLIANCE_UIF_RATE", 0.01),
        uif_monthly_ceiling=_env_float("COMPLIANCE_UIF_MONTHLY_CEILING", 17712.0),
        sdl_rate=_env_float("COMPLIANCE_SDL_RATE", 0.01),
        sdl_annual_payroll_threshold=_env_float("COMPLIANCE_SDL_ANNUAL_PAYROLL_THRESHOLD", 500000.0),
    )


def _money(v) -> Optional[float]:
    return None if v is None else round(float(v), 2)


def aggregate_payslips(row) -> dict:
    """Turn the (count, gross, paye, uif_employee, uif_employer, sdl, net, run_ids) aggregate row of
    PAID/PARTIALLY_PAID payslips into statutory figures. No row / zero employees -> every figure None
    (never a substituted estimate)."""
    empty = {
        "employee_count": None, "gross_remuneration": None, "paye": None, "uif_employee": None,
        "uif_employer": None, "sdl": None, "net_pay": None, "total_liability": None, "run_ids": [],
    }
    if row is None or not row[0]:
        return empty
    count, gross, paye, uif_e, uif_c, sdl, net, run_ids = (list(row) + [None] * 8)[:8]
    out = {
        "employee_count": int(count),
        "gross_remuneration": _money(gross),
        "paye": _money(paye),
        "uif_employee": _money(uif_e),
        "uif_employer": _money(uif_c),
        "sdl": _money(sdl),
        "net_pay": _money(net),
        "run_ids": [r for r in str(run_ids or "").split(",") if r],
    }
    parts = [out["paye"], out["uif_employee"], out["uif_employer"], out["sdl"]]
    out["total_liability"] = round(sum(p or 0.0 for p in parts), 2)
    return out


def uif_for(gross: Optional[float], rates: Optional[StatutoryRates] = None) -> Optional[float]:
    """Employee-side UIF on `gross` (capped at the remuneration ceiling); None when gross is unknown."""
    if gross is None:
        return None
    rates = rates or load_rates()
    return round(min(float(gross), rates.uif_monthly_ceiling) * rates.uif_rate, 2)


def normalise_prn(value: str) -> str:
    return re.sub(r"\s+", "", value or "")


def is_valid_prn(value: str) -> bool:
    """Loose SARS payment reference check: 16-19 letters/digits (the real PRN comes from eFiling)."""
    return bool(_PRN_RE.fullmatch(normalise_prn(value)))


def workpaper_note(figures: dict) -> str:
    if figures.get("employee_count") is None:
        return ("No paid payroll runs were found for this period, so no figures could be prepared. "
                + FILING_NOTE)
    return FILING_NOTE
