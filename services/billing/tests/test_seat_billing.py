"""Pure per-seat billing arithmetic (services/billing/seat_billing.py). No DB."""
import os
import sys
from datetime import date, datetime, timezone
from decimal import Decimal

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, REPO_ROOT)

from services.billing import seat_billing as sb  # noqa: E402

JUN = (date(2026, 6, 1), date(2026, 6, 30))


def ev(day, delta, hour=9, month=6, minute=0):
    return {"user_id": "u", "delta": delta, "reason": "t",
            "at": datetime(2026, month, day, hour, minute, tzinfo=timezone.utc)}


def peak(events, initial, period=JUN):
    return sb.compute_peak_seats(events, initial, *period)


# --- peak ------------------------------------------------------------------

def test_no_events_peak_is_initial():
    assert peak([], 5) == 5


def test_zero_seat_tenant():
    assert peak([], 0) == 0
    assert sb.build_cycle_invoice_lines(0, "100", *JUN) == []


def test_adds_then_removes_bills_the_peak():
    events = [ev(3, +1), ev(4, +1), ev(10, -1), ev(11, -1), ev(12, -1)]
    assert peak(events, 3) == 5          # 3 -> 5 -> 2; peak 5


def test_removal_first_then_add_does_not_exceed_initial():
    assert peak([ev(2, -2), ev(5, +1)], 4) == 4


def test_deactivate_then_reactivate_same_instant_no_phantom_seat():
    events = [ev(7, +1), ev(7, -1)]      # listed add-first, same instant
    assert peak(events, 3) == 3


def test_deactivate_then_reactivate_same_day():
    # removed at 09:00, back at 15:00: count returns to 3, never 4
    assert peak([ev(7, -1, hour=9), ev(7, +1, hour=15)], 3) == 3


def test_events_outside_period_ignored_and_pending_invites_count():
    events = [ev(30, +5, month=5), ev(1, +2, month=7)]
    assert peak(events, 4) == 4
    assert peak([ev(15, +1)], 4) == 5    # an invite counts as a +1 event


def test_period_boundaries_inclusive_of_last_day_exclusive_of_next():
    assert peak([ev(30, +1, hour=23, minute=59)], 1) == 2
    assert peak([{"at": "2026-07-01T00:00:00Z", "delta": 1}], 1) == 1
    assert peak([{"at": "2026-06-01T00:00:00Z", "delta": 1}], 1) == 2


def test_initial_from_current_undoes_period_events():
    events = [ev(3, +1), ev(9, -1), ev(20, +1)]          # net +1 in June
    assert sb.initial_seats_from_current(6, events, JUN[0]) == 5
    assert sb.initial_seats_from_current(0, [ev(3, +4)], JUN[0]) == 0  # clamped


# --- proration ---------------------------------------------------------------

def test_prorate_first_day_is_full_cycle():
    assert sb.prorate_addition("300.00", 1, *JUN, date(2026, 6, 1)) == Decimal("300.00")


def test_prorate_last_day_is_one_day():
    assert sb.prorate_addition("300.00", 1, *JUN, date(2026, 6, 30)) == Decimal("10.00")


def test_prorate_mid_cycle_and_seats_multiply():
    # 16 of 30 days remain on 15 June
    assert sb.prorate_addition("300.00", 2, *JUN, date(2026, 6, 15)) == Decimal("320.00")


def test_prorate_rounds_half_up_to_cents():
    assert sb.prorate_addition("100", 1, *JUN, date(2026, 6, 21)) == Decimal("33.33")   # 10/30
    feb = sb.month_period(2027, 2)
    assert sb.prorate_addition("100", 1, *feb, date(2027, 2, 28)) == Decimal("3.57")    # 1/28
    assert sb.prorate_addition("0.05", 1, *JUN, date(2026, 6, 16)) == Decimal("0.03")   # 0.0267


def test_prorate_leap_year_february_uses_29_days():
    feb = sb.month_period(2028, 2)
    assert feb == (date(2028, 2, 1), date(2028, 2, 29))
    assert sb.cycle_days(*feb) == 29
    assert sb.prorate_addition("290.00", 1, *feb, date(2028, 2, 29)) == Decimal("10.00")
    assert sb.cycle_days(*sb.month_period(2027, 2)) == 28


def test_prorate_outside_period_and_nonpositive():
    assert sb.prorate_addition("300", 1, *JUN, date(2026, 5, 20)) == Decimal("300.00")
    assert sb.prorate_addition("300", 1, *JUN, date(2026, 7, 2)) == Decimal("0.00")
    assert sb.prorate_addition("300", 0, *JUN, date(2026, 6, 10)) == Decimal("0.00")


def test_prorate_accepts_datetime_and_iso():
    assert sb.prorate_addition("300", 1, *JUN, datetime(2026, 6, 30, 23, 0, tzinfo=timezone.utc)) == Decimal("10.00")
    assert sb.prorate_addition("300", 1, *JUN, "2026-06-30T10:00:00Z") == Decimal("10.00")


# --- invoice lines -------------------------------------------------------------

def test_cycle_lines_base_only():
    lines = sb.build_cycle_invoice_lines(5, "300.00", *JUN)
    assert len(lines) == 1 and lines[0].quantity == 5 and lines[0].total_zar == Decimal("1500.00")
    assert sb.lines_total(lines) == Decimal("1500.00")


def test_cycle_lines_credit_prorated_additions_no_double_charge():
    # start 3 seats; +2 added 15 Jun (paid 320.00 pro rata); peak 5
    paid = sb.prorate_addition("300.00", 2, *JUN, date(2026, 6, 15))
    lines = sb.build_cycle_invoice_lines(5, "300.00", *JUN, [paid])
    assert [l.total_zar for l in lines] == [Decimal("1500.00"), Decimal("-320.00")]
    assert sb.lines_total(lines) == Decimal("1180.00")
    assert sb.lines_total(lines) + paid == Decimal("1500.00")


def test_cycle_lines_never_negative():
    lines = sb.build_cycle_invoice_lines(1, "100.00", *JUN, ["250.00"])
    assert sb.lines_total(lines) == Decimal("0.00")
    assert lines[1].total_zar == Decimal("-100.00")   # credit capped at base


def test_period_helpers():
    assert sb.previous_month_period(date(2026, 1, 15)) == (date(2025, 12, 1), date(2025, 12, 31))
    assert sb.parse_period("2028-02") == (date(2028, 2, 1), date(2028, 2, 29))
