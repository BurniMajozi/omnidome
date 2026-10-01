"""Calendar maths, SAST boundaries, aging buckets, collection rate, seat re-run + catch-up."""
import asyncio
import os
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from services.billing import calc, seat_runs  # noqa: E402
from services.billing.models import BillingFinanceOutbox, Invoice, SeatBillingRun  # noqa: E402
from services.billing.routes import reports  # noqa: E402
from services.billing.tests import sqlite_harness as h  # noqa: E402

D = Decimal


def test_month_stepping_visits_every_month_including_february():
    # the old `1st - 30*i days` skipped February and repeated January from 31 Mar
    assert calc.month_starts(date(2026, 3, 31), 4) == [date(2026, 3, 1), date(2026, 2, 1), date(2026, 1, 1), date(2025, 12, 1)]
    assert calc.month_starts(date(2026, 1, 15), 3) == [date(2026, 1, 1), date(2025, 12, 1), date(2025, 11, 1)]
    labels = [d.strftime("%Y-%m") for d in calc.month_starts(date(2026, 3, 31), 24)]
    assert len(set(labels)) == 24


def test_billing_anchor_31_returns_to_the_31st_and_leap_years_work():
    jan31 = date(2026, 1, 31)
    feb = calc.add_interval(jan31, "monthly", 31)
    assert feb == date(2026, 2, 28)
    assert calc.add_interval(feb, "monthly", 31) == date(2026, 3, 31)         # not stuck at the 28th
    assert calc.add_interval(date(2026, 3, 31), "monthly", 31) == date(2026, 4, 30)
    assert calc.add_interval(date(2028, 1, 31), "monthly", 31) == date(2028, 2, 29)   # leap year
    assert calc.add_interval(date(2026, 11, 30), "quarterly", 30) == date(2027, 2, 28)
    assert calc.add_interval(date(2024, 2, 29), "annual", 29) == date(2025, 2, 28)
    assert calc.add_interval(date(2025, 2, 28), "annual", 29) == date(2026, 2, 28)
    assert calc.add_interval(date(2026, 8, 31), "semi_annual") == date(2027, 2, 28)   # no anchor: day of start


def test_chain_of_monthly_periods_from_the_31st():
    d, seen = date(2026, 1, 31), []
    for _ in range(5):
        d = calc.add_interval(d, "monthly", 31)
        seen.append(d)
    assert seen == [date(2026, 2, 28), date(2026, 3, 31), date(2026, 4, 30), date(2026, 5, 31), date(2026, 6, 30)]


def test_month_bounds_are_sast_midnights_in_utc():
    lo, hi = calc.month_bounds_utc(date(2026, 3, 1))
    assert lo == datetime(2026, 2, 28, 22, 0, tzinfo=timezone.utc) and hi == datetime(2026, 3, 31, 22, 0, tzinfo=timezone.utc)
    # an invoice created at 23:30 UTC on 28 Feb is 01:30 SAST on 1 March: it belongs to March
    stamp = datetime(2026, 2, 28, 23, 30, tzinfo=timezone.utc)
    assert lo <= stamp < hi
    assert calc.today_sast(datetime(2026, 2, 28, 23, 30, tzinfo=timezone.utc)) == date(2026, 3, 1)


def test_collection_rate_is_clamped_and_null_without_invoicing():
    assert calc.collection_rate(D("50"), D("100")) == D("50.00")
    assert calc.collection_rate(D("250"), D("100")) == D("100.00")           # can no longer exceed 100%
    assert calc.collection_rate(D("-5"), D("100")) == D("0.00")
    assert calc.collection_rate(D("10"), D("0")) is None and calc.collection_rate(D("10"), None) is None
    assert calc.collection_rate(D("1"), D("3")) == D("33.33")


@pytest.mark.parametrize("days,keys", [
    (-5, ["current"]), (0, ["current"]), (1, ["1_30", "30_days"]), (30, ["1_30", "30_days"]),
    (31, ["31_60", "60_days"]), (60, ["31_60", "60_days"]), (61, ["61_90", "90_days_plus"]),
    (90, ["61_90", "90_days_plus"]), (91, ["90_plus", "90_days_plus"]), (400, ["90_plus", "90_days_plus"]),
])
def test_aging_bucket_boundaries(days, keys):
    assert calc.aging_keys(days) == keys


def test_aging_report_keeps_old_keys_and_adds_distinct_new_ones(monkeypatch):
    db = h.make_session_factory()
    h.patch_sessions(monkeypatch, db)
    tenant = uuid.uuid4()
    today = calc.today_sast()
    with db() as s:
        for days in (-3, 10, 45, 75, 120):
            h.make_invoice(s, tenant, due=today - timedelta(days=days))
    from services.common.auth import AuthContext
    rows = {r.bucket: r for r in reports.aging_report(AuthContext(user_id=uuid.uuid4(), tenant_id=tenant))}
    new = {k: rows[k].count for k in ("current", "1_30", "31_60", "61_90", "90_plus")}
    assert new == {"current": 1, "1_30": 1, "31_60": 1, "61_90": 1, "90_plus": 1}
    assert rows["90_days_plus"].count == 2 and rows["90_days_plus"].legacy and not rows["61_90"].legacy
    assert rows["30_days"].total_zar == D("115.00")


def test_revenue_counts_issued_invoices_net_of_credit_notes_only(monkeypatch):
    db = h.make_session_factory()
    h.patch_sessions(monkeypatch, db)
    tenant = uuid.uuid4()
    lo, hi = calc.month_bounds_utc(calc.today_sast().replace(day=1))
    with db() as s:
        h.make_invoice(s, tenant, status="sent")                                    # 115
        h.make_invoice(s, tenant, status="paid", paid="115.00")                     # 115
        h.make_invoice(s, tenant, status="draft")                                   # excluded
        h.make_invoice(s, tenant, status="voided")                                  # excluded
        orig = h.make_invoice(s, tenant, status="paid", paid="115.00")
        cn = h.make_invoice(s, tenant, status="credit_issued", subtotal="-50.00", vat="-7.50")
        cn.credit_note_of = orig.id                                                 # -57.50
        gone = h.make_invoice(s, tenant, status="voided")
        cn2 = h.make_invoice(s, tenant, status="paid", subtotal="-100.00", vat="-15.00")
        cn2.credit_note_of = gone.id                                                # against a voided invoice: ignored
        s.flush()
        assert reports.invoiced_net(s, tenant, lo - timedelta(days=1), hi + timedelta(days=1)) == D("287.50")


# ── seat billing: skipped re-run, SAST periods, catch-up ───────────────────

def snapshot():
    return {"current_seats": 3, "events": []}


def test_a_skipped_seat_run_can_be_rerun_once_a_price_exists():
    db = h.make_session_factory()
    tenant = uuid.uuid4()
    start, end = date(2026, 3, 1), date(2026, 3, 31)
    with db() as s:
        run, created = seat_runs.reconcile_tenant(s, tenant, start, end, snapshot(), unit_price=D("0.00"))
        assert created and run.status == "skipped" and run.invoice_id is None
        assert seat_runs.reconcile_tenant(s, tenant, start, end, snapshot(), unit_price=D("0.00"))[1] is False   # still no price
    with db() as s:
        run, created = seat_runs.reconcile_tenant(s, tenant, start, end, snapshot(), unit_price=D("50.00"))
        assert created and run.status == "invoiced" and run.invoice_id is not None
        assert s.query(SeatBillingRun).count() == 1                                  # same slot reused
        inv = s.get(Invoice, run.invoice_id)
        assert inv.status == "sent" and inv.total_zar == D("172.50")                  # 3 seats x 50 + VAT
        posted = s.query(BillingFinanceOutbox).one()
        assert posted.source == "billing.seat_invoice"
    with db() as s:
        again, created = seat_runs.reconcile_tenant(s, tenant, start, end, snapshot(), unit_price=D("50.00"))
        assert not created and s.query(Invoice).count() == 1                           # now final


def test_completed_periods_catch_up_in_sast():
    assert seat_runs.completed_periods(date(2026, 4, 10), 0) == [(date(2026, 3, 1), date(2026, 3, 31))]
    assert seat_runs.completed_periods(date(2026, 4, 10), 2) == [
        (date(2026, 1, 1), date(2026, 1, 31)), (date(2026, 2, 1), date(2026, 2, 28)), (date(2026, 3, 1), date(2026, 3, 31))]
    assert seat_runs.completed_periods(date(2026, 1, 20), 1)[0] == (date(2025, 11, 1), date(2025, 11, 30))
