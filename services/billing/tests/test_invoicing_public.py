"""Share links (hashed, expiring, revocable), the public routes' sanitising, generic 404s and rate limits."""
import os
import sys
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from services.billing.tests.invoicing_env import (  # noqa: E402
    CUSTOMER, OTHER_TENANT, TENANT, H, issue, line, make_env, new_invoice,
)

D = Decimal


@pytest.fixture
def client(monkeypatch):
    return make_env(monkeypatch)


def issued_invoice(client, **kw):
    inv = new_invoice(client, bill_to={"name": "Thandi N", "email": "thandi@example.test", "phone": "0831112222",
                                      "address": "1 Main Rd"}, **kw)
    issue(client, inv["id"])
    return inv


def mint(client, invoice_id, who="clerk", **body):
    r = client.post(f"/invoices/{invoice_id}/share-link", json=body, headers=H(who))
    assert r.status_code == 201, r.text
    return r.json()


# ── token handling ───────────────────────────────────────────────────────────

def test_token_is_unguessable_and_only_its_hash_is_stored(client):
    from services.billing.doc_service import hash_token
    from services.billing.models_invoicing import DocumentShareLink
    inv = issued_invoice(client)
    link = mint(client, inv["id"])
    tok = link["token"]
    assert len(tok) >= 43 and link["api_path"] == f"/public/invoices/{tok}"
    assert link["url"] == f"https://app.example.test/public/invoices/{tok}"
    with client.get_session() as s:
        row = s.query(DocumentShareLink).one()
        assert row.token_hash == hash_token(tok) and tok not in (row.token_hash or "")
        cols = [str(getattr(row, c.name)) for c in row.__table__.columns]
        assert not any(tok in c for c in cols)
    assert mint(client, inv["id"])["token"] != tok            # every link is distinct


def test_cannot_share_a_draft_or_void_and_reader_cannot_mint(client):
    inv = new_invoice(client)
    assert client.post(f"/invoices/{inv['id']}/share-link", json={}, headers=H("clerk")).status_code == 409
    issue(client, inv["id"])
    assert client.post(f"/invoices/{inv['id']}/share-link", json={}, headers=H("reader")).status_code == 403
    assert client.post(f"/invoices/{inv['id']}/void", headers=H("admin")).status_code == 200
    assert client.post(f"/invoices/{inv['id']}/share-link", json={}, headers=H("clerk")).status_code == 409
    assert client.post(f"/invoices/{uuid.uuid4()}/share-link", json={}, headers=H("clerk")).status_code == 404


def test_expiry_revocation_and_wrong_token_all_look_identical(client):
    from services.billing.models_invoicing import DocumentShareLink
    inv = issued_invoice(client)
    good = mint(client, inv["id"])
    expired = mint(client, inv["id"], expires_in_days=1)
    revoked = mint(client, inv["id"])
    assert client.get(f"/public/invoices/{good['token']}").status_code == 200
    with client.get_session() as s:
        s.get(DocumentShareLink, uuid.UUID(expired["id"])).expires_at -= timedelta(days=2)
    assert client.post(f"/share-links/{revoked['id']}/revoke", headers=H("clerk")).json()["active"] is False
    bodies = set()
    for tok in (expired["token"], revoked["token"], "nope", "x" * 43, "A" * 500):
        r = client.get(f"/public/invoices/{tok}")
        assert r.status_code == 404
        bodies.add(r.text)
    assert len(bodies) == 1 and "invoice" not in bodies.pop().lower()      # generic, leaks nothing
    # a quote token does not open an invoice route (and vice versa)
    q = client.post("/quotes", headers=H("clerk"), json={"customer_id": str(CUSTOMER), "lines": [line()]}).json()
    qlink = client.post(f"/quotes/{q['id']}/share-link", json={}, headers=H("clerk")).json()
    assert client.get(f"/public/invoices/{qlink['token']}").status_code == 404
    assert client.get(f"/public/quotes/{good['token']}").status_code == 404


def test_max_active_links_per_document(client, monkeypatch):
    from services.billing import doc_service
    monkeypatch.setattr(doc_service, "MAX_ACTIVE_LINKS_PER_DOC", 2)
    inv = issued_invoice(client)
    mint(client, inv["id"]); mint(client, inv["id"])
    assert client.post(f"/invoices/{inv['id']}/share-link", json={}, headers=H("clerk")).status_code == 409


def test_link_listing_shows_views_without_tokens(client):
    inv = issued_invoice(client)
    link = mint(client, inv["id"])
    client.get(f"/public/invoices/{link['token']}")
    client.get(f"/public/invoices/{link['token']}")
    rows = client.get(f"/invoices/{inv['id']}/share-links", headers=H("reader")).json()
    assert rows[0]["view_count"] == 2 and rows[0]["active"] is True
    assert "token" not in rows[0] and link["token"] not in str(rows)


# ── public view / sanitising ─────────────────────────────────────────────────

def test_public_view_json_is_sanitised_and_records_view_once_per_window(client):
    inv = issued_invoice(client, po_number="PO-1", notes="Thanks")
    link = mint(client, inv["id"])
    r = client.get(f"/public/invoices/{link['token']}")
    assert r.status_code == 200
    body, text = r.json(), r.text
    for secret in (str(TENANT), str(CUSTOMER), inv["id"], "thandi@example.test", "0831112222", "tenant_id",
                   "customer_id", "subscription"):
        assert secret not in text, secret
    assert body["number"] == inv["number"] and body["total"] == inv["total_zar"] and body["balance"] == inv["total_zar"]
    assert body["bill_to"] == {"name": "Thandi N", "address": "1 Main Rd"}
    assert body["payable"] is True and body["pay_path"] == f"/public/invoices/{link['token']}/pay"
    assert r.headers["cache-control"] == "no-store"
    client.get(f"/public/invoices/{link['token']}")
    events = client.get(f"/invoices/{inv['id']}/delivery-events", headers=H("reader")).json()
    assert [e["event_type"] for e in events] == ["viewed"]                   # deduped inside the window
    tl = client.get(f"/invoices/{inv['id']}/timeline", headers=H("reader")).json()["events"]
    assert "invoice_viewed" in [e["type"] for e in tl]


def test_public_view_html_is_escaped_and_scriptless(client):
    xss = "<script>alert(1)</script>"
    inv = new_invoice(client, notes=xss, lines=[line(xss)], bill_to={"name": xss})
    issue(client, inv["id"])
    link = mint(client, inv["id"])
    r = client.get(f"/public/invoices/{link['token']}?format=html")
    assert r.status_code == 200 and "<script" not in r.text.lower() and "&lt;script&gt;" in r.text
    assert "default-src 'none'" in r.headers["content-security-policy"]
    assert client.get(f"/public/invoices/{link['token']}?format=pdf").status_code == 422


def test_paid_invoice_view_is_not_payable_and_pay_is_refused(client):
    inv = issued_invoice(client)
    link = mint(client, inv["id"])
    client.post("/payments", headers=H("clerk"), json={"invoice_id": inv["id"], "amount_zar": inv["total_zar"], "method": "eft"})
    body = client.get(f"/public/invoices/{link['token']}").json()
    assert body["payable"] is False and body["pay_path"] is None and body["status"] == "paid"
    assert client.post(f"/public/invoices/{link['token']}/pay", json={}).status_code == 409


def test_public_pay_uses_paystack_initialize_logic(client, monkeypatch):
    from services.billing.routes import paystack as ps
    from services.billing.schemas import PaystackInitializeResponse
    inv = issued_invoice(client)
    link = mint(client, inv["id"])
    seen = {}

    async def fake_init(body, ctx):
        seen.update(invoice_id=body.invoice_id, amount=body.amount_zar, tenant=ctx.tenant_id, cb=body.callback_url)
        return PaystackInitializeResponse(authorization_url="https://checkout.paystack.com/abc", access_code="AC", reference="OD-1")
    monkeypatch.setattr(ps, "initialize_paystack", fake_init)
    r = client.post(f"/public/invoices/{link['token']}/pay", json={"amount_zar": "50.00"})
    assert r.status_code == 200 and r.json() == {"authorization_url": "https://checkout.paystack.com/abc", "reference": "OD-1"}
    assert str(seen["invoice_id"]) == inv["id"] and seen["amount"] == D("50.00") and seen["tenant"] == TENANT

    from fastapi import HTTPException

    async def refuse(body, ctx):
        raise HTTPException(status_code=400, detail="Amount must be between 0.01 and the outstanding R1 SECRET")
    monkeypatch.setattr(ps, "initialize_paystack", refuse)
    r = client.post(f"/public/invoices/{link['token']}/pay", json={})
    assert r.status_code == 409 and "SECRET" not in r.text

    async def down(body, ctx):
        raise HTTPException(status_code=503, detail="Paystack not configured")
    monkeypatch.setattr(ps, "initialize_paystack", down)
    assert client.post(f"/public/invoices/{link['token']}/pay", json={}).status_code == 503


# ── public quotes ────────────────────────────────────────────────────────────

def test_public_quote_view_accept_decline_flow(client):
    q = client.post("/quotes", headers=H("clerk"), json={
        "prospect_name": "Sipho", "prospect_email": "s@example.test", "lines": [line(price="300")]}).json()
    link = client.post(f"/quotes/{q['id']}/share-link", json={}, headers=H("clerk")).json()
    assert client.get(f"/quotes/{q['id']}", headers=H("reader")).json()["status"] == "sent"      # sharing marks it sent
    v = client.get(f"/public/quotes/{link['token']}")
    assert v.status_code == 200 and v.json()["actionable"] is True
    assert "s@example.test" not in v.text and q["id"] not in v.text
    assert client.get(f"/quotes/{q['id']}", headers=H("reader")).json()["status"] == "viewed"
    a = client.post(f"/public/quotes/{link['token']}/accept", json={"note": "Please proceed"})
    assert a.status_code == 200 and a.json()["status"] == "accepted"
    assert client.post(f"/public/quotes/{link['token']}/accept", json={}).json()["status"] == "accepted"   # idempotent
    assert client.post(f"/public/quotes/{link['token']}/decline", json={}).status_code == 409
    got = client.get(f"/quotes/{q['id']}", headers=H("reader")).json()
    assert got["decision_note"] == "Please proceed" and got["accepted_at"]
    after = client.get(f"/public/quotes/{link['token']}").json()
    assert after["actionable"] is False and after["accept_path"] is None


def test_public_quote_draft_and_expired_are_not_actionable(client):
    from services.billing.models_invoicing import Quote
    q = client.post("/quotes", headers=H("clerk"), json={"customer_id": str(CUSTOMER), "lines": [line()]}).json()
    link = client.post(f"/quotes/{q['id']}/share-link", json={}, headers=H("clerk")).json()
    with client.get_session() as s:
        row = s.get(Quote, uuid.UUID(q["id"]))
        row.valid_until = row.issue_date - timedelta(days=1)
    assert client.post(f"/public/quotes/{link['token']}/accept", json={}).status_code == 409
    q2 = client.post("/quotes", headers=H("clerk"), json={"customer_id": str(CUSTOMER), "lines": [line()]}).json()
    with client.get_session() as s:                     # a draft with a (hand-made) link must not be reachable
        from services.billing.doc_service import mint_link
        tok, _ = mint_link(s, TENANT, "quote", uuid.UUID(q2["id"]), "test")
    assert client.get(f"/public/quotes/{tok}").status_code == 404


def test_public_routes_never_cross_tenants(client):
    inv = issued_invoice(client)
    link = mint(client, inv["id"])
    # the link is the authority: same body regardless of any caller tenant header
    r = client.get(f"/public/invoices/{link['token']}", headers=H("admin", OTHER_TENANT))
    assert r.status_code == 200 and r.json()["number"] == inv["number"]


# ── rate limits ──────────────────────────────────────────────────────────────

def test_per_ip_rate_limit_on_views_and_actions(client, monkeypatch):
    from services.billing.routes import public_invoices as pub
    inv = issued_invoice(client)
    link = mint(client, inv["id"])
    monkeypatch.setattr(pub, "view_limiter", pub.RateLimiter(max_requests=3, window_seconds=60))
    codes = [client.get(f"/public/invoices/{link['token']}").status_code for _ in range(5)]
    assert codes == [200, 200, 200, 429, 429]
    monkeypatch.setattr(pub, "action_limiter", pub.RateLimiter(max_requests=2, window_seconds=60))
    codes = [client.post(f"/public/invoices/{link['token']}/pay", json={}).status_code for _ in range(3)]
    assert codes[-1] == 429


def test_rate_limit_is_per_ip_not_global(client, monkeypatch):
    from services.billing.routes import public_invoices as pub
    inv = issued_invoice(client)
    link = mint(client, inv["id"])
    monkeypatch.setenv("TRUSTED_PROXY_HOPS", "1")
    monkeypatch.setattr(pub, "view_limiter", pub.RateLimiter(max_requests=1, window_seconds=60))
    ok1 = client.get(f"/public/invoices/{link['token']}", headers={"x-forwarded-for": "9.9.9.9, 1.1.1.1"})
    ok2 = client.get(f"/public/invoices/{link['token']}", headers={"x-forwarded-for": "9.9.9.9, 2.2.2.2"})
    blocked = client.get(f"/public/invoices/{link['token']}", headers={"x-forwarded-for": "9.9.9.9, 1.1.1.1"})
    assert (ok1.status_code, ok2.status_code, blocked.status_code) == (200, 200, 429)


def test_repeated_bad_tokens_get_the_ip_throttled(client, monkeypatch):
    from services.billing.routes import public_invoices as pub
    inv = issued_invoice(client)
    link = mint(client, inv["id"])
    monkeypatch.setattr(pub, "bad_tokens", pub.BadTokenThrottle(max_bad=3, window=600))
    assert [client.get(f"/public/invoices/guess{i}").status_code for i in range(4)] == [404, 404, 404, 429]
    assert client.get(f"/public/invoices/{link['token']}").status_code == 429      # even a good token, from that IP
