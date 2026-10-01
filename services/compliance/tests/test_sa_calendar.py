"""Business-day / holiday helper and EMP201 due dates (Africa/Johannesburg)."""
from datetime import date

import pytest

from services.compliance import sa_calendar as cal


def test_easter_known_dates():
    assert cal.easter_sunday(2024) == date(2024, 3, 31)
    assert cal.easter_sunday(2025) == date(2025, 4, 20)
    assert cal.easter_sunday(2026) == date(2026, 4, 5)


def test_holidays_include_easter_derived_and_fixed():
    h = cal.public_holidays(2026)
    assert h[date(2026, 4, 3)] == "Good Friday"
    assert h[date(2026, 4, 6)] == "Family Day"
    assert date(2026, 12, 25) in h and date(2026, 9, 24) in h


def test_sunday_holiday_moves_to_monday():
    # 2025-06-16 (Youth Day) is a Monday; 2027-06-16 is a Wednesday. 2021-12-26 was a Sunday -> Monday 27th observed.
    h = cal.public_holidays(2021)
    assert date(2021, 12, 26) in h and date(2021, 12, 27) in h
    assert cal.is_public_holiday(date(2021, 12, 27))


def test_business_day_rules():
    assert cal.is_business_day(date(2026, 10, 1))        # Thursday
    assert not cal.is_business_day(date(2026, 10, 3))    # Saturday
    assert not cal.is_business_day(date(2026, 4, 3))     # Good Friday


@pytest.mark.parametrize("period,expected", [
    ("2026-09", date(2026, 10, 7)),    # Wednesday: stays on the 7th
    ("2026-10", date(2026, 11, 6)),    # 7 Nov 2026 is a Saturday -> Friday 6th
    ("2026-11", date(2026, 12, 7)),    # Monday
    ("2026-07", date(2026, 8, 7)),     # Friday
])
def test_emp201_due_dates(period, expected):
    due, note = cal.emp201_due_date(period)
    assert due == expected
    assert "verify" in note.lower()


def test_emp201_due_sunday_moves_back_to_friday():
    # 7 Mar 2027 is a Sunday -> Friday 5 Mar 2027 (period 2027-02)
    assert date(2027, 3, 7).weekday() == 6
    due, note = cal.emp201_due_date("2027-02")
    assert due == date(2027, 3, 5)
    assert "Moved from 2027-03-07" in note


def test_emp201_due_skips_holiday_chain():
    # Period 2027-03: 7 Apr 2027 is a Wednesday (stays). Period 2025-03: 7 Apr 2025 Monday.
    assert cal.emp201_due_date("2025-03")[0] == date(2025, 4, 7)
    # December period: due 7 Jan, year rolls over
    assert cal.emp201_due_date("2026-12")[0] == date(2027, 1, 7)


@pytest.mark.parametrize("bad", ["2026", "2026-13", "26-01", "abc", "2026-00", ""])
def test_period_parse_rejects_bad(bad):
    with pytest.raises(ValueError):
        cal.parse_period(bad)


def test_period_bounds():
    assert cal.period_bounds("2028-02") == (date(2028, 2, 1), date(2028, 2, 29))
    assert cal.period_bounds("2026-12") == (date(2026, 12, 1), date(2026, 12, 31))


def test_sast_is_utc_plus_2():
    assert cal.sast_now().utcoffset().total_seconds() == 7200
