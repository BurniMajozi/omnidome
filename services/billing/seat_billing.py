"""Per-seat billing arithmetic (pure functions, stdlib only, no I/O).

Business rules (owner decisions):
  * Billable seats for a cycle = the PEAK number of concurrent seats
    (active users + pending invites) at any moment inside the cycle.
    Deactivating a user frees the seat at once, but the peak already reached
    in the cycle is still billed.
  * Seats ADDED mid-cycle are charged pro rata immediately for the remaining
    days of the cycle; that charge is later credited against the cycle invoice
    so nothing is billed twice.
  * REMOVALS take effect next cycle, with no refunds.

Conventions
  * Currency ZAR, amounts are Decimal rounded ROUND_HALF_UP to cents. VAT is
    NOT applied here; the invoice builder adds it.
  * A cycle is the closed date range [period_start, period_end] (both days
    included), e.g. 2028-02-01..2028-02-29.
  * Day count: ACTUAL days. total_days = (end - start).days + 1;
    remaining_days = (end - added_on).days + 1 - the day the seat is added
    counts as a billable day. fraction = remaining_days / total_days.
    An addition dated before the period is charged in full (fraction 1); one
    dated after the period charges nothing.
  * Seat events: dicts {user_id, delta, reason, at}. `delta` is +1/-1 per
    seat (larger magnitudes are allowed); `at` is a datetime or ISO string.
    Naive datetimes are treated as UTC. The period is evaluated in UTC dates.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Iterable, List, Optional, Sequence, Union

CENT = Decimal("0.01")


def money(value: Any) -> Decimal:
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def _to_dt(value: Union[str, datetime, date]) -> datetime:
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, date):
        dt = datetime.combine(value, time.min)
    else:
        text = str(value).strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _period_bounds(period_start: date, period_end: date) -> tuple[datetime, datetime]:
    """[start 00:00, end+1day 00:00) in UTC."""
    if period_end < period_start:
        raise ValueError("period_end before period_start")
    lo = datetime.combine(period_start, time.min, tzinfo=timezone.utc)
    hi = datetime.combine(period_end + timedelta(days=1), time.min, tzinfo=timezone.utc)
    return lo, hi


def initial_seats_from_current(current_seats: int, events: Iterable[dict], period_start: date) -> int:
    """Seats in force at the start of the period, derived from today's seat
    count by undoing every event dated on/after period_start."""
    lo = datetime.combine(period_start, time.min, tzinfo=timezone.utc)
    later = sum(int(e["delta"]) for e in events if _to_dt(e["at"]) >= lo)
    return max(0, int(current_seats) - later)


def compute_peak_seats(
    events: Sequence[dict], initial_seats: int, period_start: date, period_end: date
) -> int:
    """Maximum concurrent seats during the period.

    Replays events inside the period on top of `initial_seats` (seats at the
    start of the period). Events at the same instant are applied together
    (removals first) so an instantaneous deactivate+reactivate never
    manufactures a phantom extra seat, and a same-second swap is not a peak.
    Events outside the period are ignored. Never negative.
    """
    lo, hi = _period_bounds(period_start, period_end)
    inside = sorted(
        ((_to_dt(e["at"]), int(e["delta"])) for e in events if lo <= _to_dt(e["at"]) < hi),
        key=lambda x: x[0],
    )
    seats = max(0, int(initial_seats))
    peak = seats
    i = 0
    while i < len(inside):
        j = i
        net = 0
        while j < len(inside) and inside[j][0] == inside[i][0]:
            net += inside[j][1]
            j += 1
        seats = max(0, seats + net)
        peak = max(peak, seats)
        i = j
    return peak


def cycle_days(period_start: date, period_end: date) -> int:
    return (period_end - period_start).days + 1


def remaining_days(period_start: date, period_end: date, on: Union[date, datetime]) -> int:
    d = on.astimezone(timezone.utc).date() if isinstance(on, datetime) and on.tzinfo else (
        on.date() if isinstance(on, datetime) else on)
    if d < period_start:
        d = period_start
    if d > period_end:
        return 0
    return (period_end - d).days + 1


def prorate_addition(
    unit_price: Any, added_seats: int, period_start: date, period_end: date, at: Union[date, datetime, str]
) -> Decimal:
    """Pro rata charge (ex VAT, ZAR) for seats added on `at`."""
    if added_seats <= 0:
        return Decimal("0.00")
    if isinstance(at, str):
        at = _to_dt(at)
    rem = remaining_days(period_start, period_end, at)
    total = cycle_days(period_start, period_end)
    amount = Decimal(str(unit_price)) * added_seats * Decimal(rem) / Decimal(total)
    return money(amount)


@dataclass
class InvoiceLineSpec:
    description: str
    quantity: int
    unit_price_zar: Decimal
    total_zar: Decimal
    line_type: str = "seat"
    period_start: Optional[date] = None
    period_end: Optional[date] = None

    def as_dict(self) -> dict:
        return {
            "description": self.description,
            "quantity": self.quantity,
            "unit_price_zar": str(self.unit_price_zar),
            "total_zar": str(self.total_zar),
            "line_type": self.line_type,
            "period_start": self.period_start.isoformat() if self.period_start else None,
            "period_end": self.period_end.isoformat() if self.period_end else None,
        }


def build_cycle_invoice_lines(
    peak_seats: int,
    unit_price: Any,
    period_start: date,
    period_end: date,
    prorated_charges: Optional[Iterable[Any]] = None,
) -> List[InvoiceLineSpec]:
    """Lines for the end-of-cycle seat invoice.

    Line 1: peak_seats x unit_price. Line 2 (only if there were any): a credit
    for prorated addition charges already invoiced this cycle. The credit is
    capped at the base amount, so the invoice never goes negative. Zero peak
    seats yields no lines. `prorated_charges` are the ex-VAT amounts already
    charged.
    """
    unit = money(unit_price)
    if peak_seats <= 0 or unit <= 0:
        return []
    label = f"{period_start.isoformat()} to {period_end.isoformat()}"
    base = money(unit * peak_seats)
    lines = [InvoiceLineSpec(
        f"OmniDome seats - peak {peak_seats} seat(s), {label}",
        peak_seats, unit, base, "seat", period_start, period_end,
    )]
    already = money(sum((Decimal(str(c)) for c in (prorated_charges or [])), Decimal("0")))
    credit = min(already, base)
    if credit > 0:
        lines.append(InvoiceLineSpec(
            f"Less: pro rata seat additions already invoiced ({label})",
            1, -credit, -credit, "seat_credit", period_start, period_end,
        ))
    return lines


def lines_total(lines: Iterable[InvoiceLineSpec]) -> Decimal:
    return max(Decimal("0.00"), money(sum((l.total_zar for l in lines), Decimal("0"))))


def month_period(year: int, month: int) -> tuple[date, date]:
    start = date(year, month, 1)
    nxt = date(year + (month == 12), (month % 12) + 1, 1)
    return start, nxt - timedelta(days=1)


def previous_month_period(today: date) -> tuple[date, date]:
    first = today.replace(day=1)
    last_prev = first - timedelta(days=1)
    return month_period(last_prev.year, last_prev.month)


def parse_period(value: str) -> tuple[date, date]:
    """'YYYY-MM' -> (first, last day of that month)."""
    y, m = value.split("-")
    return month_period(int(y), int(m))
