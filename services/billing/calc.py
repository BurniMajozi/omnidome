"""Pure date/period/report helpers (no DB, no I/O) so they can be unit tested."""
from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

SAST = timezone(timedelta(hours=2), "SAST")  # Africa/Johannesburg has no DST
_MONTHS = {"monthly": 1, "quarterly": 3, "semi_annual": 6, "annual": 12}


def today_sast(now: Optional[datetime] = None) -> date:
    return (now or datetime.now(timezone.utc)).astimezone(SAST).date()


def add_months(d: date, months: int, anchor_day: Optional[int] = None) -> date:
    """d + months, with the day taken from anchor_day (default d.day) clamped to the month length."""
    idx = d.year * 12 + (d.month - 1) + months
    year, month = divmod(idx, 12)
    month += 1
    day = min(anchor_day or d.day, monthrange(year, month)[1])
    return date(year, month, day)


def add_interval(start: date, interval: str, anchor_day: Optional[int] = None) -> date:
    """start + billing interval. Pass the subscription's original anchor day so a 31st anchor
    returns to the 31st after a short month (Jan 31 -> Feb 28 -> Mar 31) instead of sticking at 28."""
    return add_months(start, _MONTHS.get(interval, 1), anchor_day)


def month_starts(today: date, count: int) -> list[date]:
    """First day of the current month and the (count-1) months before it, newest first."""
    first = today.replace(day=1)
    return [add_months(first, -i, 1) for i in range(count)]


def next_month(first: date) -> date:
    return add_months(first, 1, 1)


def sast_instant(d: date) -> datetime:
    """Midnight SAST at the start of calendar date d, as an aware UTC instant."""
    return datetime(d.year, d.month, d.day, tzinfo=SAST).astimezone(timezone.utc)


def month_bounds_utc(first: date) -> tuple[datetime, datetime]:
    return sast_instant(first), sast_instant(next_month(first))


def collection_rate(collected: Decimal, invoiced: Decimal) -> Optional[Decimal]:
    """collected_in_period / invoiced_in_period as a percentage clamped to 0..100; None when nothing was invoiced."""
    if invoiced is None or invoiced <= 0:
        return None
    rate = (Decimal(collected or 0) / Decimal(invoiced) * 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return max(Decimal("0.00"), min(Decimal("100.00"), rate))


AGING_KEYS = ["current", "30_days", "60_days", "90_days_plus", "1_30", "31_60", "61_90", "90_plus"]


def aging_keys(days_overdue: int) -> list[str]:
    """Bucket keys for an invoice `days_overdue` past due (<=0 = not yet due).

    New distinct buckets: current, 1_30, 31_60, 61_90, 90_plus. The legacy keys are kept (additively)
    with their old meaning: 30_days = 1-30, 60_days = 31-60, 90_days_plus = everything over 60
    (the web labels it "60+")."""
    if days_overdue <= 0:
        return ["current"]
    if days_overdue <= 30:
        return ["1_30", "30_days"]
    if days_overdue <= 60:
        return ["31_60", "60_days"]
    if days_overdue <= 90:
        return ["61_90", "90_days_plus"]
    return ["90_plus", "90_days_plus"]
