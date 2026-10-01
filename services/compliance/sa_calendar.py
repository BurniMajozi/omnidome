"""South African dates: SAST clock, public holidays and statutory due dates.

South Africa has no daylight saving, so SAST is a fixed UTC+2 offset (no tzdata
needed). Public holidays: the fixed-date holidays of the Public Holidays Act
(a holiday that falls on a Sunday moves to the Monday) plus Good Friday and
Family Day (Easter Monday). One-off proclaimed holidays (e.g. election days)
are NOT known here, so due dates are labelled as estimates.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Optional

SAST = timezone(timedelta(hours=2), name="SAST")


def sast_now() -> datetime:
    return datetime.now(SAST)


def sast_today() -> date:
    return sast_now().date()


def easter_sunday(year: int) -> date:
    """Gregorian Easter (anonymous / Meeus algorithm)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def public_holidays(year: int) -> dict[date, str]:
    fixed = {
        (1, 1): "New Year's Day",
        (3, 21): "Human Rights Day",
        (4, 27): "Freedom Day",
        (5, 1): "Workers' Day",
        (6, 16): "Youth Day",
        (8, 9): "National Women's Day",
        (9, 24): "Heritage Day",
        (12, 16): "Day of Reconciliation",
        (12, 25): "Christmas Day",
        (12, 26): "Day of Goodwill",
    }
    out: dict[date, str] = {}
    for (m, d), name in fixed.items():
        day = date(year, m, d)
        out[day] = name
        if day.weekday() == 6:  # Sunday -> the Monday is also a public holiday
            out.setdefault(day + timedelta(days=1), f"{name} (observed)")
    easter = easter_sunday(year)
    out[easter - timedelta(days=2)] = "Good Friday"
    out[easter + timedelta(days=1)] = "Family Day"
    return out


def is_public_holiday(day: date) -> bool:
    return day in public_holidays(day.year)


def is_business_day(day: date) -> bool:
    return day.weekday() < 5 and not is_public_holiday(day)


def previous_business_day(day: date) -> date:
    while not is_business_day(day):
        day -= timedelta(days=1)
    return day


def parse_period(period: str) -> tuple[int, int]:
    """'YYYY-MM' -> (year, month); ValueError when malformed."""
    try:
        y, m = period.split("-")
        year, month = int(y), int(m)
        if len(y) != 4 or not 1 <= month <= 12:
            raise ValueError
        return year, month
    except Exception:
        raise ValueError("period must be YYYY-MM") from None


def period_bounds(period: str) -> tuple[date, date]:
    year, month = parse_period(period)
    start = date(year, month, 1)
    end = date(year + (month == 12), (month % 12) + 1, 1) - timedelta(days=1)
    return start, end


def emp201_due_date(period: str) -> tuple[date, str]:
    """EMP201 for `period` is due on the 7th of the following month, moved to the
    previous business day when the 7th is a weekend or public holiday."""
    year, month = parse_period(period)
    ny, nm = (year + 1, 1) if month == 12 else (year, month + 1)
    nominal = date(ny, nm, 7)
    due = previous_business_day(nominal)
    note = "Estimated; verify on SARS eFiling"
    if due != nominal:
        note = f"Moved from {nominal.isoformat()} (weekend/public holiday) to the previous business day. {note}"
    return due, note
