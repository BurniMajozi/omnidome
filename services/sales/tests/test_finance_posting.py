"""Close-won must not book revenue (billing invoices do); it only accrues the commission,
through finance with signed identity headers, and a failed post is recorded, not dropped."""
import asyncio
import os
import sys
import uuid
from datetime import datetime
from decimal import Decimal

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, REPO_ROOT)

from services.sales import main  # noqa: E402

TENANT = uuid.UUID("00000000-0000-0000-0000-000000000001")
AGENT = uuid.uuid4()


class FakeResp:
    def __init__(self, code):
        self.status_code = code


def fake_client(calls, code=200, boom=False):
    class C:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None, headers=None):
            if boom:
                raise RuntimeError("down")
            calls.append((url, json, headers))
            return FakeResp(code)
    return C


def post(code=200, boom=False, amount="1500.50", monkeypatch=None):
    calls = []
    main.httpx.AsyncClient = fake_client(calls, code, boom)
    ok = asyncio.run(main._post_commission_to_finance(TENANT, uuid.uuid4(), uuid.uuid4(), AGENT, Decimal(amount), datetime(2026, 10, 1)))
    return ok, calls


def test_no_revenue_bridge_remains():
    assert not hasattr(main, "_notify_finance_won")


def test_commission_accrual_posts_no_revenue_and_is_signed_and_auto_posted(monkeypatch):
    orig = main.httpx.AsyncClient
    monkeypatch.setenv("INTERNAL_SERVICE_KEY", "k" * 40)
    try:
        ok, calls = post()
    finally:
        main.httpx.AsyncClient = orig
    assert ok and len(calls) == 1
    url, body, headers = calls[0]
    assert url.endswith("/journal-entries")
    codes = {l["account_code"] for l in body["lines"]}
    assert codes == {"6050", "2110"} and "4000" not in codes and "1100" not in codes
    assert body["source"] == "sales.commission" and body["auto_post"] is True and body["source_id"]
    assert sum(Decimal(l["debit"]) for l in body["lines"]) == sum(Decimal(l["credit"]) for l in body["lines"]) == Decimal("1500.50")
    assert headers["X-Tenant-Id"] == str(TENANT) and headers["X-User-Id"] == str(AGENT)
    assert headers["X-Internal-Key"] == "k" * 40


def test_non_2xx_and_exceptions_are_reported_not_swallowed():
    orig = main.httpx.AsyncClient
    try:
        assert post(code=422)[0] is False
        assert post(code=500)[0] is False
        assert post(boom=True)[0] is False
    finally:
        main.httpx.AsyncClient = orig
