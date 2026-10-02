"""Sales hardening against a real Postgres (TEST_DATABASE_URL; skipped without one).

Closed deals are terminal (one commission however many closes, even concurrent),
quote acceptance rules, the commission report, tenant isolation of foreign ids,
one default pipeline per tenant, roles, and the deals summary/pagination the web uses.

    TEST_DATABASE_URL=postgresql://.../omnidome_test python scripts/setup_test_db.py
    PYTHONPATH=. python -m pytest services/sales/tests/test_hardening_db.py -q
"""
import os
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, REPO_ROOT)

from services.common import testdb  # noqa: E402

testdb.use_test_database()
os.environ["AUTH_ENFORCE_RBAC"] = "false"  # roles come from the X-Roles header in these tests
os.environ["SALES_ENFORCE_ROLES"] = "true"

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from services.sales.main import app, guard  # noqa: E402


@pytest.fixture(scope="module")
def client():
    # Other test modules can construct the app before use_test_database sets
    # its environment. This suite tests sales authorization, not entitlements.
    prior = guard.enforce_modules
    guard.enforce_modules = False
    try:
        with TestClient(app) as c:
            yield c
    finally:
        guard.enforce_modules = prior
        testdb.reset_engines()


@pytest.fixture
def tenant():
    return testdb.new_tenant("sales hardening")


def hdr(tenant, user=None, roles="admin"):
    h = testdb.headers(tenant, user)
    if roles:
        h["X-Roles"] = roles
    return h


def _utc_today():
    """The service stamps and buckets in UTC; the host's local date differs around midnight."""
    return datetime.utcnow().date()


def sql(query, **params):
    with testdb.sync_engine().begin() as conn:
        return conn.execute(text(query), params).fetchall()


def new_contact(client, tenant):
    r = client.post("/contacts", json={"first_name": "Test", "last_name": "Customer"}, headers=hdr(tenant))
    assert r.status_code == 201, r.text
    return r.json()["id"]


def new_deal(client, tenant, value="1000.00", agent=None, **extra):
    body = {"name": "Deal", "customer_id": new_contact(client, tenant), "value_zar": value, **extra}
    if agent:
        body["agent_id"] = str(agent)
    r = client.post("/deals", json=body, headers=hdr(tenant))
    assert r.status_code == 201, r.text
    return r.json()


def commissions(deal_id):
    return sql("SELECT id FROM commissions WHERE deal_id = :d", d=deal_id)


# ── H4 ──────────────────────────────────────────────────────────────────────

def test_close_won_twice_books_one_commission(client, tenant):
    agent = testdb.new_user(tenant)
    deal = new_deal(client, tenant, agent=agent)
    first = client.post(f"/deals/{deal['id']}/close-won", headers=hdr(tenant))
    second = client.post(f"/deals/{deal['id']}/close-won", headers=hdr(tenant))
    assert first.status_code == 200 and second.status_code == 200, (first.text, second.text)
    assert second.json()["status"] == "WON" and second.json()["closed_at"] == first.json()["closed_at"]
    assert len(commissions(deal["id"])) == 1


def test_concurrent_close_won_books_exactly_one_commission(client, tenant):
    agent = testdb.new_user(tenant)
    deal = new_deal(client, tenant, agent=agent)

    def close(_):
        return client.post(f"/deals/{deal['id']}/close-won", headers=hdr(tenant)).status_code

    with ThreadPoolExecutor(max_workers=6) as pool:
        codes = list(pool.map(close, range(6)))
    assert set(codes) == {200}, codes
    assert len(commissions(deal["id"])) == 1


def test_close_lost_on_a_won_deal_is_409_and_keeps_the_commission(client, tenant):
    agent = testdb.new_user(tenant)
    deal = new_deal(client, tenant, agent=agent)
    assert client.post(f"/deals/{deal['id']}/close-won", headers=hdr(tenant)).status_code == 200
    r = client.post(f"/deals/{deal['id']}/close-lost", params={"reason": "changed their mind"}, headers=hdr(tenant))
    assert r.status_code == 409
    assert len(commissions(deal["id"])) == 1
    assert client.get(f"/deals/{deal['id']}", headers=hdr(tenant)).json()["status"] == "WON"


def test_close_won_on_a_lost_deal_is_409(client, tenant):
    deal = new_deal(client, tenant)
    url = f"/deals/{deal['id']}/close-lost"
    assert client.post(url, params={"reason": "no budget"}, headers=hdr(tenant)).status_code == 200
    assert client.post(url, params={"reason": "no budget"}, headers=hdr(tenant)).status_code == 200  # same close: idempotent
    assert client.post(f"/deals/{deal['id']}/close-won", headers=hdr(tenant)).status_code == 409


def make_quote(client, tenant, contact, deal_id=None, valid_days=14):
    body = {"customer_id": contact, "total_monthly": "799.00", "term_months": 12, "valid_days": valid_days}
    if deal_id:
        body["deal_id"] = deal_id
    r = client.post("/quotes", json=body, headers=hdr(tenant))
    assert r.status_code == 201, r.text
    return r.json()


def test_accept_quote_needs_a_sent_unexpired_quote_and_never_reopens_a_deal(client, tenant):
    contact = new_contact(client, tenant)
    draft = make_quote(client, tenant, contact)
    assert client.post(f"/quotes/{draft['id']}/accept", json={}, headers=hdr(tenant)).status_code == 409  # DRAFT

    expired = make_quote(client, tenant, contact, valid_days=-1)
    assert client.post(f"/quotes/{expired['id']}/send", json={"mark_sent_only": True}, headers=hdr(tenant)).status_code == 409
    sent = make_quote(client, tenant, contact)
    r = client.post(f"/quotes/{sent['id']}/send", json={"mark_sent_only": True}, headers=hdr(tenant))
    assert r.status_code == 200 and r.json()["delivery"] == "marked_sent_only"
    with testdb.sync_engine().begin() as conn:
        conn.execute(text("UPDATE quotes SET valid_until = :d WHERE id = :q"),
                     {"d": _utc_today() - timedelta(days=1), "q": sent["id"]})
    assert client.post(f"/quotes/{sent['id']}/accept", json={}, headers=hdr(tenant)).status_code == 409  # expired

    deal = new_deal(client, tenant)
    assert client.post(f"/deals/{deal['id']}/close-won", headers=hdr(tenant)).status_code == 200
    linked = make_quote(client, tenant, contact, deal_id=deal["id"])
    client.post(f"/quotes/{linked['id']}/send", json={"mark_sent_only": True}, headers=hdr(tenant))
    assert client.post(f"/quotes/{linked['id']}/accept", json={}, headers=hdr(tenant)).status_code == 409  # closed deal
    after = client.get(f"/deals/{deal['id']}", headers=hdr(tenant)).json()
    assert after["status"] == "WON" and float(after["value_zar"]) == 1000.0


def test_accept_quote_happy_path_and_no_double_accept(client, tenant):
    contact = new_contact(client, tenant)
    q = make_quote(client, tenant, contact)
    client.post(f"/quotes/{q['id']}/send", json={"mark_sent_only": True}, headers=hdr(tenant))
    ok = client.post(f"/quotes/{q['id']}/accept", json={}, headers=hdr(tenant))
    assert ok.status_code == 200 and ok.json()["status"] == "ACCEPTED" and ok.json()["deal_id"]
    assert client.post(f"/quotes/{q['id']}/accept", json={}, headers=hdr(tenant)).status_code == 409


def test_quote_channels_that_are_not_wired_say_so(client, tenant):
    q = make_quote(client, tenant, new_contact(client, tenant))
    r = client.post(f"/quotes/{q['id']}/send", json={"channel": "sms", "recipient": "+27820000000"}, headers=hdr(tenant))
    assert r.status_code == 501
    assert client.get(f"/quotes/{q['id']}", headers=hdr(tenant)).json()["status"] == "DRAFT"  # nothing was claimed


# ── M1 ──────────────────────────────────────────────────────────────────────

def test_commission_report_returns_counts_per_agent(client, tenant):
    agent = testdb.new_user(tenant)
    for _ in range(2):
        d = new_deal(client, tenant, agent=agent)
        client.post(f"/deals/{d['id']}/close-won", headers=hdr(tenant))
    today = _utc_today().isoformat()
    r = client.get("/commissions/report", params={"start_date": today, "end_date": today}, headers=hdr(tenant))
    assert r.status_code == 200, r.text
    row = next(x for x in r.json() if x["agent_id"] == str(agent))
    assert row["deals_count"] == 2 and row["pending"] == 2 and row["paid"] == 0  # end day included


# ── M3 ──────────────────────────────────────────────────────────────────────

def test_foreign_ids_are_404_not_leaks_or_500s(client):
    mine, theirs = testdb.new_tenant("mine"), testdb.new_tenant("theirs")
    their_contact = new_contact(client, theirs)
    their_deal = new_deal(client, theirs)
    their_stage = client.get("/pipeline/stages", headers=hdr(theirs)).json()[0]["id"]
    their_lead = client.post("/leads", json={"first_name": "A", "last_name": "B"}, headers=hdr(theirs)).json()["id"]

    base = {"name": "x", "value_zar": "10", "customer_id": new_contact(client, mine)}
    assert client.post("/deals", json={**base, "stage_id": their_stage}, headers=hdr(mine)).status_code == 404
    assert client.post("/deals", json={**base, "lead_id": their_lead}, headers=hdr(mine)).status_code == 404
    assert client.post("/deals", json={**base, "agent_id": str(uuid.uuid4())}, headers=hdr(mine)).status_code == 404
    assert client.post("/deals", json={**base, "customer_id": their_contact}, headers=hdr(mine)).status_code == 404
    mine_deal = new_deal(client, mine)
    assert client.put(f"/deals/{mine_deal['id']}/stage", json={"stage_id": their_stage}, headers=hdr(mine)).status_code == 404
    assert client.get(f"/deals/{their_deal['id']}", headers=hdr(mine)).status_code == 404
    q = {"customer_id": their_contact}
    assert client.post("/quotes", json=q, headers=hdr(mine)).status_code == 404


def test_deal_list_does_not_leak_a_foreign_lead(client):
    mine, theirs = testdb.new_tenant("mine"), testdb.new_tenant("theirs")
    their_lead = client.post("/leads", json={"first_name": "A", "last_name": "B", "owner_name": "Secret Owner"},
                             headers=hdr(theirs)).json()["id"]
    deal = new_deal(client, mine)
    with testdb.sync_engine().begin() as conn:  # corrupt row: mine points at a lead of theirs
        conn.execute(text("UPDATE deals SET lead_id = :l WHERE id = :d"), {"l": their_lead, "d": deal["id"]})
    row = client.get("/deals", headers=hdr(mine)).json()[0]
    assert row["lead_reference"] is None and row["owner_name"] is None


# ── M4 ──────────────────────────────────────────────────────────────────────

def test_fresh_tenant_gets_exactly_one_default_pipeline_under_concurrency(client, tenant):
    def hit(i):
        path = "/pipeline/stages" if i % 2 else "/deals"
        return client.get(path, headers=hdr(tenant)).status_code

    with ThreadPoolExecutor(max_workers=8) as pool:
        codes = list(pool.map(hit, range(16)))
    assert set(codes) == {200}, codes
    assert sql("SELECT count(*) FROM pipelines WHERE tenant_id = :t AND is_default", t=tenant)[0][0] == 1


def test_duplicate_stage_names_are_409(client, tenant):
    assert client.post("/pipeline/stages", json={"name": "Closed Won"}, headers=hdr(tenant)).status_code == 409
    assert client.post("/pipeline/stages", json={"name": "  closed   lost "}, headers=hdr(tenant)).status_code == 409
    assert client.post("/pipeline/stages", json={"name": "Site survey"}, headers=hdr(tenant)).status_code == 201
    assert client.post("/pipeline/stages", json={"name": "SITE SURVEY"}, headers=hdr(tenant)).status_code == 409


# ── M5 ──────────────────────────────────────────────────────────────────────

def test_org_user_cannot_delete_edit_the_pipeline_or_set_targets(client, tenant):
    deal = new_deal(client, tenant)
    user = hdr(tenant, roles="org_user")
    assert client.delete(f"/deals/{deal['id']}", headers=user).status_code == 403
    assert client.post("/pipeline/stages", json={"name": "Nope"}, headers=user).status_code == 403
    body = {"period_start": "2026-09-01", "period_end": "2026-09-30", "target_value_zar": "1000"}
    assert client.post("/targets", json=body, headers=user).status_code == 403
    assert client.get("/commissions/report", headers=user).status_code == 403
    assert client.delete(f"/deals/{deal['id']}", headers=hdr(tenant, roles="org_admin")).status_code == 204


def test_agent_reads_only_their_own_commissions_unless_manager(client, tenant):
    me, other = testdb.new_user(tenant), testdb.new_user(tenant)
    agent = hdr(tenant, me, roles="sales_agent")
    assert client.get("/commissions", headers=agent).status_code == 200
    assert client.get("/commissions", params={"agent_id": str(other)}, headers=agent).status_code == 403
    assert client.get("/commissions", params={"agent_id": str(other)}, headers=hdr(tenant, me, roles="manager")).status_code == 200


# ── H2: what the web uses ───────────────────────────────────────────────────

def test_deals_pagination_headers_and_summary(client, tenant):
    agent = testdb.new_user(tenant)
    won = [new_deal(client, tenant, value="100.10", agent=agent) for _ in range(3)]
    for d in won:
        client.post(f"/deals/{d['id']}/close-won", headers=hdr(tenant))
    lost = new_deal(client, tenant, value="50.00")
    client.post(f"/deals/{lost['id']}/close-lost", params={"reason": "no budget"}, headers=hdr(tenant))
    new_deal(client, tenant, value="25.00")

    page = client.get("/deals", params={"limit": 2, "offset": 1}, headers=hdr(tenant))
    assert page.status_code == 200 and isinstance(page.json(), list) and len(page.json()) == 2
    assert page.headers["X-Total-Count"] == "5"

    today = _utc_today().isoformat()
    s = client.get("/deals/summary", headers=hdr(tenant)).json()
    assert (s["count"], s["won_count"], s["lost_count"], s["open_count"]) == (5, 3, 1, 1)
    assert s["won_value_zar"] == 300.30 and s["lost_value_zar"] == 50.0 and s["open_value_zar"] == 25.0
    assert s["total_value_zar"] == 375.30

    won_today = client.get("/deals/summary", params={"status": "WON", "closed_from": today, "closed_to": today},
                           headers=hdr(tenant)).json()
    assert won_today["count"] == 3 and won_today["won_value_zar"] == 300.30  # the end day itself is included
    yesterday = (_utc_today() - timedelta(days=1)).isoformat()
    assert client.get("/deals/summary", params={"closed_to": yesterday}, headers=hdr(tenant)).json()["count"] == 0
    listed = client.get("/deals", params={"status": "WON", "closed_to": today}, headers=hdr(tenant))
    assert len(listed.json()) == 3 and listed.headers["X-Total-Count"] == "3"


# ── H3 end to end ───────────────────────────────────────────────────────────

def test_funnel_counts_sum_to_total_leads(client, tenant):
    for i, status in enumerate(["NEW", "CONTACTED", "QUALIFIED"]):
        lead = client.post("/leads", json={"first_name": f"L{i}", "last_name": "x", "source": "BROADBAND"},
                           headers=hdr(tenant)).json()
        if status != "NEW":
            client.post(f"/leads/{lead['id']}/stage", json={"status": status}, headers=hdr(tenant))
    piped = client.post("/leads", json={"first_name": "P", "last_name": "x", "pipeline": {"stage_name": "Qualified",
                        "value_zar": "89997"}}, headers=hdr(tenant)).json()
    assert piped["deal_stage"] == "Qualified"
    f = client.get("/leads/funnel", headers=hdr(tenant)).json()
    assert f["totals"]["total_leads"] == 4 == sum(s["count"] for s in f["overall_funnel"])
    assert {s["stage"]: s["count"] for s in f["overall_funnel"]}["QUALIFIED"] == 2
    assert f["totals"]["total_pipeline_value_zar"] == 89997.0
    assert next(c for c in f["channels"] if c["channel"] == "OTHER")["total_leads"] == 3  # BROADBAND is not an ad
