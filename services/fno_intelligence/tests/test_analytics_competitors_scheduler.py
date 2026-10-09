"""Per-competitor auto-scan schedule: user-chosen (default manual), calendar maths, atomic claim, credit caps,
failure backoff + auto-pause, tenant isolation, validation. Fakes only."""

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import update

from services.fno_intelligence import analytics_common as ac
from services.fno_intelligence import competitors as cp
from services.fno_intelligence import database
from services.fno_intelligence.analytics_models import AiCompetitor
from services.fno_intelligence.tests.analytics_harness import TENANT_B, env
from services.fno_intelligence.tests.test_analytics_competitors import PRICING, _make, _page, _scan

UTC = timezone.utc


def _dt(*a):
    return datetime(*a, tzinfo=UTC)


async def _force_due(cid, **vals):
    async with database.get_session_factory()() as db:
        await db.execute(update(AiCompetitor).where(AiCompetitor.id == uuid.UUID(cid)).values(
            next_scan_at=ac.now() - timedelta(minutes=1), **vals))
        await db.commit()


async def _row(cid) -> AiCompetitor:
    async with database.get_session_factory()() as db:
        return await db.get(AiCompetitor, uuid.UUID(cid))


# ── pure schedule maths ───────────────────────────────────────────────────

def test_next_run_is_local_time_in_johannesburg():
    now = _dt(2026, 10, 9, 10, 0)                      # Fri 12:00 SAST
    assert cp.next_run_at(now, "daily", "13:00") == _dt(2026, 10, 9, 11, 0)       # still today
    assert cp.next_run_at(now, "daily", "06:00") == _dt(2026, 10, 10, 4, 0)       # tomorrow 06:00 SAST = 04:00Z
    assert cp.next_run_at(now, "weekly", "06:00", 0) == _dt(2026, 10, 12, 4, 0)   # next Monday
    assert cp.next_run_at(now, "weekly", "14:00", 4) == _dt(2026, 10, 9, 12, 0)   # today (Fri) later
    assert cp.next_run_at(now, "monthly", "06:00", None, 1) == _dt(2026, 11, 1, 4, 0)
    assert cp.next_run_at(_dt(2026, 12, 20, 10, 0), "monthly", "06:00", None, 5) == _dt(2027, 1, 5, 4, 0)
    assert cp.next_run_at(now, "12h") == now + timedelta(hours=12)
    assert cp.next_run_at(now, None) is None


def test_normalize_schedule_validation():
    assert cp.normalize_schedule(None)["scan_interval_hours"] is None
    assert cp.normalize_schedule("daily")["schedule_time"] == "06:00"
    assert cp.normalize_schedule("monthly", "09:30", None, 28)["scan_interval_hours"] == 720
    for bad in [("hourly",), ("daily", "25:00"), ("weekly", "06:00", None), ("weekly", "06:00", 7),
                ("monthly", "06:00", None, 29), ("monthly", "06:00", None, None)]:
        with pytest.raises(ValueError):
            cp.normalize_schedule(*bad)


def test_plan_next_scan_outcomes():
    now = _dt(2026, 10, 9, 10, 0)
    daily = {"frequency": "daily", "time_": "06:00", "weekday": None, "day_of_month": None}
    ok = cp.plan_next_scan(now=now, schedule=daily, outcome="ok", failures=3, scheduled=True, rand=lambda: 0)
    assert ok["consecutive_failures"] == 0 and ok["next_scan_at"] == _dt(2026, 10, 10, 4, 0)
    assert "next_scan_at" not in cp.plan_next_scan(now=now, schedule=None, outcome="ok", failures=0, scheduled=True)
    cap = cp.plan_next_scan(now=now, schedule=daily, outcome="capped", failures=1, scheduled=True, cap_scope="daily", rand=lambda: 0)
    assert cap["last_status"] == "capped" and cap["consecutive_failures"] == 1 and cap["next_scan_at"] > _dt(2026, 10, 10, 0, 0)
    delays, f = [], 0
    for _ in range(4):
        p = cp.plan_next_scan(now=now, schedule=daily, outcome="failed", failures=f, scheduled=True, rand=lambda: 0)
        f = p["consecutive_failures"]
        delays.append((p["next_scan_at"] - now).total_seconds() / 60)
    assert delays == [30, 60, 120, 240]                                          # exponential backoff
    paused = cp.plan_next_scan(now=now, schedule=daily, outcome="failed", failures=4, scheduled=True)
    assert paused["next_scan_at"] is None and paused["consecutive_failures"] == 5
    manual_fail = cp.plan_next_scan(now=now, schedule=daily, outcome="failed", failures=0, scheduled=False)
    assert manual_fail["consecutive_failures"] == 0 and "next_scan_at" not in manual_fail


def test_sanitize_error_redacts_and_truncates():
    out = cp.sanitize_error("boom Bearer abc.def-123 key fc-SECRET123 https://x.example/?token=zzz " + "x" * 400)
    assert "abc.def" not in out and "SECRET123" not in out and "zzz" not in out and len(out) <= 240


# ── API / scheduler ───────────────────────────────────────────────────────

def test_default_is_manual_and_put_validation(tmp_path, monkeypatch):
    async def go():
        async with env(tmp_path, monkeypatch) as e:
            e.fc.pages[PRICING] = _page()
            cid = await _make(e, promo_page_url=None)
            c = (await e.req("GET", f"/competitors/{cid}")).json()
            assert c["schedule_frequency"] is None and c["next_scan_at"] is None and c["scan_interval_hours"] is None
            for bad in [{"scan_interval_hours": 6}, {"schedule_frequency": "hourly"},
                        {"schedule_frequency": "daily", "schedule_time": "7pm"},
                        {"schedule_frequency": "weekly", "schedule_time": "06:00"},
                        {"schedule_frequency": "monthly", "schedule_day_of_month": 31}]:
                assert (await e.req("PUT", f"/competitors/{cid}", json=bad)).status_code == 422, bad
            assert (await e.req("PUT", f"/competitors/{cid}", json={"name": "Renamed"})).json()["schedule_frequency"] is None
            r = await e.req("PUT", f"/competitors/{cid}", json={"schedule_frequency": "weekly", "schedule_time": "07:15",
                                                                "schedule_weekday": 2})
            c = r.json()
            assert c["scan_interval_hours"] == 168 and c["last_status"] == "queued" and c["next_scan_at"]
            assert c["estimated_credits_per_month"] == round(4.3 * cp.SCAN_CREDIT_ESTIMATE)
            assert datetime.fromisoformat(c["next_scan_at"]).astimezone(cp._tz()).strftime("%H:%M") == "07:15"
            # legacy interval shortcut still works, then turning off clears everything
            assert (await e.req("PUT", f"/competitors/{cid}", json={"scan_interval_hours": 24})).json()["schedule_frequency"] == "daily"
            off = (await e.req("PUT", f"/competitors/{cid}", json={"schedule_frequency": None})).json()
            assert off["next_scan_at"] is None and off["scan_interval_hours"] is None and off["last_status"] is None
            r = await e.req("POST", "/competitors", json={"name": "Sched Co", "website": "https://s.example",
                                                           "schedule_frequency": "monthly", "schedule_day_of_month": 3})
            assert r.status_code == 201 and r.json()["schedule_day_of_month"] == 3 and r.json()["next_scan_at"]
    asyncio.run(go())


def test_due_selection_only_scheduled_active_due(tmp_path, monkeypatch):
    async def go():
        async with env(tmp_path, monkeypatch) as e:
            e.fc.pages[PRICING] = _page()
            e.fc.pages["https://d.example/p"] = _page()
            manual = await _make(e, name="Manual")                                    # never scheduled
            future = await _make(e, name="Future", website="https://f.example")
            inactive = await _make(e, name="Inactive", website="https://i.example")
            due = await _make(e, name="Due", website="https://d.example", pricing_page_url="https://d.example/p",
                              promo_page_url=None)
            for cid in (future, inactive, due):
                await e.req("PUT", f"/competitors/{cid}", json={"schedule_frequency": "daily", "schedule_time": "06:00"})
            await e.req("PUT", f"/competitors/{inactive}", json={"active": False})
            await _force_due(inactive)
            await _force_due(due)
            res = await cp.run_scheduler_tick()
            assert len(res) == 1 and {c[1] for c in e.fc.calls if c[0] == "scrape"} == {"https://d.example/p"}
            assert (await _row(manual)).last_scanned_at is None
            assert (await _row(future)).last_scanned_at is None and (await _row(inactive)).last_scanned_at is None
            d = await _row(due)
            assert d.last_status == "ok" and d.last_scanned_at and cp.aware(d.next_scan_at) > ac.now()
            hhmm = cp.aware(d.next_scan_at).astimezone(cp._tz()).strftime("%H:%M")
            assert "06:00" <= hhmm <= "06:05"
    asyncio.run(go())


def test_two_concurrent_ticks_scan_once(tmp_path, monkeypatch):
    async def go():
        async with env(tmp_path, monkeypatch) as e:
            e.fc.pages[PRICING] = _page()
            cid = await _make(e, promo_page_url=None)
            await e.req("PUT", f"/competitors/{cid}", json={"schedule_frequency": "daily"})
            await _force_due(cid)
            a, b = await asyncio.gather(cp.run_scheduler_tick(), cp.run_scheduler_tick())
            assert len(a) + len(b) == 1 and e.fc.count("scrape") == 1
    asyncio.run(go())


def test_parallel_limit_and_per_tick_cap(tmp_path, monkeypatch):
    async def go():
        async with env(tmp_path, monkeypatch) as e:
            running = peak = 0
            orig = cp.execute_scan

            async def slow(*a, **k):
                nonlocal running, peak
                running += 1
                peak = max(peak, running)
                await asyncio.sleep(0.05)
                try:
                    return await orig(*a, **k)
                finally:
                    running -= 1
            monkeypatch.setattr(cp, "execute_scan", slow)
            for i in range(4):
                e.fc.pages[f"https://c{i}.example/pricing"] = _page()
                cid = await _make(e, name=f"C{i}", website=f"https://c{i}.example",
                                  pricing_page_url=f"https://c{i}.example/pricing", promo_page_url=None)
                await e.req("PUT", f"/competitors/{cid}", json={"schedule_frequency": "daily"})
                await _force_due(cid)
            res = await cp.run_scheduler_tick(max_scans=3, parallel=2)
            assert len(res) == 3 and peak == 2
    asyncio.run(go())


def test_credit_capped_tenant_is_not_scanned_and_pushed_forward(tmp_path, monkeypatch):
    async def go():
        async with env(tmp_path, monkeypatch) as e:
            e.fc.pages[PRICING] = _page()
            cid = await _make(e, promo_page_url=None)
            await e.req("PUT", f"/competitors/{cid}", json={"schedule_frequency": "daily"})
            await _force_due(cid)
            monkeypatch.setenv("FIRECRAWL_TENANT_DAILY_CREDITS", "5")
            assert await cp.run_scheduler_tick() == [] and e.fc.count("scrape") == 0
            r = await _row(cid)
            assert r.last_status == "capped" and "credits reset" in r.last_error
            assert cp.aware(r.next_scan_at) >= cp.next_period_start(ac.now(), "daily")
            assert r.consecutive_failures == 0
            assert await cp.run_scheduler_tick() == []                             # no retry storm: not due anymore
    asyncio.run(go())


def test_failure_backoff_then_auto_pause_and_resume(tmp_path, monkeypatch):
    async def go():
        async with env(tmp_path, monkeypatch) as e:
            e.fc.pages[PRICING] = _page()
            e.fc.fail_urls.add(PRICING)
            monkeypatch.setattr(cp.random, "random", lambda: 0.0)                  # no jitter: deterministic gaps
            cid = await _make(e, promo_page_url=None)
            await e.req("PUT", f"/competitors/{cid}", json={"schedule_frequency": "daily"})
            gaps = []
            for i in range(1, 6):
                await _force_due(cid)
                await cp.run_scheduler_tick()
                r = await _row(cid)
                assert r.consecutive_failures == i and r.last_status == "failed"
                if i < 5:
                    gaps.append(cp.aware(r.next_scan_at) - ac.now())
            assert all(b > a * 1.5 for a, b in zip(gaps, gaps[1:]))                # exponential
            assert r.next_scan_at is None and "paused after 5" in r.last_error
            assert await cp.run_scheduler_tick() == []                             # paused: never picked again
            assert (await e.req("GET", f"/competitors/{cid}")).json()["auto_scan_paused"] is True
            e.fc.fail_urls.clear()
            res = (await e.req("POST", f"/competitors/{cid}/resume")).json()
            assert res["consecutive_failures"] == 0 and res["next_scan_at"] and res["last_status"] == "queued"
            assert (await e.req("POST", f"/competitors/{cid}/resume", tenant=TENANT_B)).status_code == 404
    asyncio.run(go())


def test_manual_scan_still_works_and_manual_failure_does_not_pause(tmp_path, monkeypatch):
    async def go():
        async with env(tmp_path, monkeypatch) as e:
            e.fc.pages[PRICING] = _page()
            cid = await _make(e, promo_page_url=None)
            c = await _scan(e, cid)
            assert c["scan_status"] == "ok" and c["last_status"] == "ok" and c["next_scan_at"] is None   # stays unscheduled
            await e.req("PUT", f"/competitors/{cid}", json={"schedule_frequency": "daily"})
            e.fc.fail_urls.add(PRICING)
            c = await _scan(e, cid)
            assert c["last_status"] == "failed" and c["consecutive_failures"] == 0 and c["next_scan_at"]
    asyncio.run(go())


def test_seen_badge_and_tenant_isolation(tmp_path, monkeypatch):
    async def go():
        async with env(tmp_path, monkeypatch) as e:
            e.fc.pages[PRICING] = _page()
            cid = await _make(e, promo_page_url=None)
            await _scan(e, cid)
            e.fc.pages[PRICING] = _page(price50="R849")
            await _scan(e, cid)
            ov = (await e.req("GET", "/competitors/overview")).json()
            assert ov["competitors"][0]["new_changes_since_last_view"] == 1
            assert ov["estimated_credits_per_scan"] == cp.SCAN_CREDIT_ESTIMATE
            assert (await e.req("POST", f"/competitors/{cid}/seen", tenant=TENANT_B)).status_code == 404
            assert (await e.req("POST", f"/competitors/{cid}/seen")).json()["new_changes_since_last_view"] == 0
            assert (await e.req("GET", "/competitors/overview")).json()["competitors"][0]["new_changes_since_last_view"] == 0
            await asyncio.sleep(1.1)  # sqlite CURRENT_TIMESTAMP has 1s resolution
            e.fc.pages[PRICING] = _page(price50="R899")
            await _scan(e, cid)
            assert (await e.req("GET", f"/competitors/{cid}")).json()["new_changes_since_last_view"] == 1
            assert (await e.req("GET", "/competitors", tenant=TENANT_B)).json() == []
    asyncio.run(go())
