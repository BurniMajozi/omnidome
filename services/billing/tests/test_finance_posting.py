"""Posting contract: pure builders (balanced by construction) and the durable outbox."""
import asyncio
import os
import sys
import uuid
from datetime import date
from decimal import Decimal

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from services.billing import finance_posting as fp  # noqa: E402
from services.billing.models import BillingFinanceOutbox  # noqa: E402
from services.billing.tests import sqlite_harness as h  # noqa: E402

D = Decimal
ON = date(2026, 3, 31)
REAL_POST_ENTRY = fp.post_entry   # conftest swaps the module attribute for a no-op per test


def sums(entry):
    return (sum(D(l["debit"]) for l in entry["lines"]), sum(D(l["credit"]) for l in entry["lines"]))


def by_code(entry):
    return {l["account_code"]: l for l in entry["lines"]}


@pytest.mark.parametrize("subtotal,vat", [("100.00", "15.00"), ("499.00", "74.85"), ("0.01", "0.00"),
                                          ("33.33", "5.00"), ("1000.00", "0.00"), ("12345.67", "1851.85")])
def test_invoice_entry_is_balanced_with_vat_split(subtotal, vat):
    total = D(subtotal) + D(vat)
    e = fp.invoice_entry(uuid.uuid4(), "INV-1", ON, total, subtotal, vat)
    d, c = sums(e)
    assert d == c == total
    lines = by_code(e)
    assert D(lines["1100"]["debit"]) == total
    assert D(lines["4000"]["credit"]) == D(subtotal)                  # revenue ex VAT
    if D(vat):
        assert D(lines["2200"]["credit"]) == D(vat)
    else:
        assert "2200" not in lines
    assert e["source"] == "billing.invoice" and e["auto_post"] is True and e["date"] == "2026-03-31"
    assert all(isinstance(l["debit"], str) and isinstance(l["credit"], str) for l in e["lines"])


def test_invoice_entry_rebalances_when_legacy_rounding_disagrees():
    e = fp.invoice_entry(uuid.uuid4(), "INV-2", ON, "115.01", "100.00", "15.00")   # total != subtotal + vat
    d, c = sums(e)
    assert d == c == D("115.01") and D(by_code(e)["4000"]["credit"]) == D("100.01")


def test_seat_invoice_uses_its_own_source():
    e = fp.invoice_entry(uuid.uuid4(), "INV-3", ON, "115.00", "100.00", "15.00", source="billing.seat_invoice")
    assert e["source"] == "billing.seat_invoice"


@pytest.mark.parametrize("method,account", [("eft", "1000"), ("manual", "1000"), ("card", "1010")])
def test_payment_entry_bank_vs_paystack_clearing(method, account):
    e = fp.payment_entry(uuid.uuid4(), "ref", ON, "57.50", method)
    d, c = sums(e)
    assert d == c == D("57.50")
    assert D(by_code(e)[account]["debit"]) == D("57.50") and D(by_code(e)["1100"]["credit"]) == D("57.50")
    assert e["source"] == "billing.payment"


def test_payment_rounding_and_validation():
    assert sums(fp.payment_entry(uuid.uuid4(), "r", ON, "10.005"))[0] == D("10.01")      # half up
    with pytest.raises(ValueError):
        fp.payment_entry(uuid.uuid4(), "r", ON, "0")


@pytest.mark.parametrize("builder,source", [(fp.credit_note_entry, "billing.credit_note"), (fp.void_entry, "billing.void")])
def test_credit_note_and_void_reverse_revenue_and_vat(builder, source):
    # credit notes carry negative totals: the builder works on magnitudes
    e = builder(uuid.uuid4(), "CN-1", ON, "-69.00", "-60.00", "-9.00")
    d, c = sums(e)
    assert d == c == D("69.00")
    lines = by_code(e)
    assert D(lines["4000"]["debit"]) == D("60.00") and D(lines["2200"]["debit"]) == D("9.00")
    assert D(lines["1100"]["credit"]) == D("69.00") and e["source"] == source


def test_entry_is_json_serialisable_and_has_the_contract_keys():
    import json
    e = fp.invoice_entry(uuid.uuid4(), "INV-9", ON, "115.00", "100.00", "15.00")
    assert set(e) == {"date", "description", "source", "source_id", "auto_post", "lines"}
    assert set(e["lines"][0]) == {"account_code", "debit", "credit"}
    json.dumps(e)


# ── outbox ──────────────────────────────────────────────────────────────────

@pytest.fixture
def db():
    return h.make_session_factory()


def test_enqueue_is_idempotent_per_source_id(db):
    tenant = uuid.uuid4()
    e = fp.invoice_entry(uuid.uuid4(), "INV-1", ON, "115.00", "100.00", "15.00")
    with db() as s:
        assert fp.enqueue(s, tenant, e) is not None
        assert fp.enqueue(s, tenant, e) is None
        assert s.query(BillingFinanceOutbox).count() == 1
        row = s.query(BillingFinanceOutbox).one()
        assert row.status == "pending" and row.payload["source_id"] == e["source_id"]


def test_deliver_marks_sent_and_failures_are_retried_with_the_error(db):
    tenant = uuid.uuid4()
    good = fp.invoice_entry(uuid.uuid4(), "INV-1", ON, "115.00", "100.00", "15.00")
    bad = fp.invoice_entry(uuid.uuid4(), "INV-2", ON, "230.00", "200.00", "30.00")
    with db() as s:
        fp.enqueue(s, tenant, good)
        fp.enqueue(s, tenant, bad)
    posted = []

    async def poster(tid, entry):
        if entry["source_id"] == bad["source_id"]:
            raise RuntimeError("finance returned HTTP 500: boom")
        posted.append((tid, entry["source_id"]))

    out = asyncio.run(fp.deliver(tenant, poster=poster, session_factory=db))
    assert out == {"attempted": 2, "sent": 1, "failed": 1}
    assert posted == [(tenant, good["source_id"])]
    with db() as s:
        rows = {r.source_id: r for r in s.query(BillingFinanceOutbox).all()}
        assert rows[good["source_id"]].status == "sent"
        failed = rows[bad["source_id"]]
        assert failed.status == "failed" and failed.attempts == 1 and "HTTP 500" in failed.last_error
        assert failed.next_attempt_at is not None

    # backoff: not retried until due, unless forced (the retry endpoint)
    assert asyncio.run(fp.deliver(tenant, poster=poster, session_factory=db))["attempted"] == 0
    async def ok(tid, entry):
        return None
    out = asyncio.run(fp.deliver(tenant, poster=ok, session_factory=db, force=True))
    assert out["sent"] == 1
    with db() as s:
        assert s.query(BillingFinanceOutbox).filter_by(status="sent").count() == 2


def test_sent_rows_are_never_resent(db):
    tenant = uuid.uuid4()
    with db() as s:
        fp.enqueue(s, tenant, fp.invoice_entry(uuid.uuid4(), "INV-1", ON, "115.00", "100.00", "15.00"))
    calls = []

    async def poster(tid, entry):
        calls.append(1)
    asyncio.run(fp.deliver(tenant, poster=poster, session_factory=db))
    asyncio.run(fp.deliver(tenant, poster=poster, session_factory=db, force=True))
    assert len(calls) == 1


def test_post_entry_treats_non_2xx_as_failure(monkeypatch):
    import httpx

    class Resp:
        def __init__(self, code):
            self.status_code, self.text = code, "x"

    class Client:
        code = 500

        def __init__(self, *a, **k): ...
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, json=None, headers=None):
            Client.seen = (url, headers, json)
            return Resp(Client.code)

    monkeypatch.setattr(httpx, "AsyncClient", Client)
    real = REAL_POST_ENTRY
    tenant = uuid.uuid4()
    entry = fp.invoice_entry(uuid.uuid4(), "INV-1", ON, "115.00", "100.00", "15.00")
    with pytest.raises(RuntimeError, match="HTTP 500"):
        asyncio.run(real(tenant, entry))
    Client.code = 200
    asyncio.run(real(tenant, entry))
    url, headers, body = Client.seen
    assert url.endswith("/journal-entries") and headers["x-tenant-id"] == str(tenant) and "x-user-id" in headers
    assert body["source"] == "billing.invoice"
