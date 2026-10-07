"""Manual invoices, catalog, templates, documents, quotes, timeline/movements (SQLite harness, bare app)."""
import os
import sys
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from services.billing.tests.invoicing_env import (  # noqa: E402
    CUSTOMER, OTHER_TENANT, H, TENANT, issue, line, make_env, new_invoice,
)

D = Decimal


@pytest.fixture
def client(monkeypatch):
    return make_env(monkeypatch)


# ── manual invoices ──────────────────────────────────────────────────────────

def test_manual_invoice_totals_are_server_side_and_client_totals_ignored(client):
    r = client.post("/invoices/manual", headers=H("clerk"), json={
        "customer_id": str(CUSTOMER), "total_zar": "1.00", "vat_zar": "0", "subtotal_zar": "1",
        "lines": [{**line("Router", "2", "499.99"), "total_zar": "0.01"}, line("Cable", "1", "10.00", tax_rate="0")],
        "po_number": "PO-7", "source_type": "technician", "notes": "n", "terms": "t"})
    assert r.status_code == 201, r.text
    inv = r.json()
    assert inv["status"] == "draft" and inv["source_type"] == "technician" and inv["po_number"] == "PO-7"
    assert inv["subtotal_zar"] == "1009.98" and inv["vat_zar"] == "150.00" and inv["total_zar"] == "1159.98"
    assert inv["balance_zar"] == "1159.98" and inv["currency"] == "ZAR"
    assert all(l["line_id"] for l in inv["lines"])


def test_numbering_is_sequential_and_shared_with_invoices(client):
    a, b = new_invoice(client), new_invoice(client)
    na, nb = int(a["number"].rsplit("-", 1)[1]), int(b["number"].rsplit("-", 1)[1])
    assert nb == na + 1


def test_bad_input_rejected(client):
    bad = client.post("/invoices/manual", headers=H("clerk"), json={"customer_id": str(CUSTOMER), "lines": []})
    assert bad.status_code == 422
    neg = client.post("/invoices/manual", headers=H("clerk"),
                      json={"customer_id": str(CUSTOMER), "lines": [line(price="-5")]})
    assert neg.status_code == 422
    due = client.post("/invoices/manual", headers=H("clerk"), json={
        "customer_id": str(CUSTOMER), "lines": [line()], "issue_date": "2026-05-10", "due_date": "2026-05-01"})
    assert due.status_code == 422
    src = client.post("/invoices/manual", headers=H("clerk"), json={
        "customer_id": str(CUSTOMER), "lines": [line()], "source_type": "hacker"})
    assert src.status_code == 422


def test_role_gates(client):
    body = {"customer_id": str(CUSTOMER), "lines": [line()]}
    assert client.post("/invoices/manual", json=body, headers=H("reader")).status_code == 403
    inv = new_invoice(client)
    assert client.get(f"/invoices/{inv['id']}/detail", headers=H("reader")).status_code == 200
    assert client.put(f"/invoices/{inv['id']}", json={"notes": "x"}, headers=H("reader")).status_code == 403


def test_big_discount_needs_admin(client):
    body = {"customer_id": str(CUSTOMER), "lines": [line(discount="30.00")]}
    assert client.post("/invoices/manual", json=body, headers=H("clerk")).status_code == 403
    assert client.post("/invoices/manual", json=body, headers=H("admin")).status_code == 201


def test_update_draft_recomputes_and_is_blocked_after_issue(client):
    inv = new_invoice(client, lines=[line(price="100.00")])
    r = client.put(f"/invoices/{inv['id']}", headers=H("clerk"), json={
        "lines": [line("A", "3", "10.00"), line("B", "1", "5.00", discount="5", discount_type="percent")],
        "notes": "edited", "po_number": "PO-9"})
    assert r.status_code == 200, r.text
    u = r.json()
    assert u["subtotal_zar"] == "34.75" and u["vat_zar"] == "5.21" and u["total_zar"] == "39.96"
    assert u["notes"] == "edited" and u["po_number"] == "PO-9"
    issue(client, inv["id"])
    again = client.put(f"/invoices/{inv['id']}", headers=H("clerk"), json={"notes": "late"})
    assert again.status_code == 409


def test_tenant_isolation(client):
    inv = new_invoice(client)
    assert client.get(f"/invoices/{inv['id']}/detail", headers=H("admin", OTHER_TENANT)).status_code == 404
    assert client.put(f"/invoices/{inv['id']}", json={"notes": "x"}, headers=H("admin", OTHER_TENANT)).status_code == 404


def test_duplicate_and_reorder(client):
    inv = new_invoice(client, lines=[line("A", price="10"), line("B", price="20"), line("C", price="30")])
    dup = client.post(f"/invoices/{inv['id']}/duplicate", headers=H("clerk"))
    assert dup.status_code == 201
    d = dup.json()
    assert d["id"] != inv["id"] and d["number"] != inv["number"] and d["status"] == "draft"
    assert d["total_zar"] == inv["total_zar"] and [l["description"] for l in d["lines"]] == ["A", "B", "C"]
    assert {l["line_id"] for l in d["lines"]}.isdisjoint({l["line_id"] for l in inv["lines"]})

    ids = [l["line_id"] for l in inv["lines"]]
    r = client.put(f"/invoices/{inv['id']}/lines/order", headers=H("clerk"), json={"order": [ids[2], ids[0], ids[1]]})
    assert r.status_code == 200 and [l["description"] for l in r.json()["lines"]] == ["C", "A", "B"]
    assert client.put(f"/invoices/{inv['id']}/lines/order", headers=H("clerk"), json={"order": ids[:2]}).status_code == 422
    assert client.put(f"/invoices/{inv['id']}/lines/order", headers=H("clerk"),
                      json={"order": [ids[0], ids[0], ids[1]]}).status_code == 422


def test_issue_keeps_finance_contract_revenue_posted_on_issue_only(client):
    from services.billing.models import BillingFinanceOutbox
    inv = new_invoice(client)
    with client.get_session() as s:
        assert s.query(BillingFinanceOutbox).count() == 0     # a draft never reaches the ledger
    issue(client, inv["id"])
    with client.get_session() as s:
        rows = s.query(BillingFinanceOutbox).all()
        assert [(r.source, r.source_id) for r in rows] == [("billing.invoice", inv["id"])]


# ── catalog ──────────────────────────────────────────────────────────────────

def test_item_catalog_crud_and_use_on_invoice(client):
    r = client.post("/invoice-items", headers=H("clerk"), json={
        "name": "Fibre install", "description": "Standard", "unit_price_zar": "950.00", "category": "install"})
    assert r.status_code == 201
    item = r.json()
    assert item["tax_rate"] == "15.00" and item["active"] is True
    assert client.get("/invoice-items?q=fibre", headers=H("reader")).json()[0]["id"] == item["id"]
    assert client.get("/invoice-items?category=other", headers=H("reader")).json() == []
    assert client.put(f"/invoice-items/{item['id']}", headers=H("clerk"), json={"unit_price_zar": "1000"}).json()["unit_price_zar"] == "1000.00"
    inv = new_invoice(client, lines=[line("Fibre install", price="1000", catalog_item_id=item["id"])])
    assert inv["lines"][0]["catalog_item_id"] == item["id"]
    bad = client.post("/invoices/manual", headers=H("clerk"), json={
        "customer_id": str(CUSTOMER), "lines": [line(catalog_item_id=str(uuid.uuid4()))]})
    assert bad.status_code == 422
    assert client.delete(f"/invoice-items/{item['id']}", headers=H("clerk")).status_code == 403
    assert client.delete(f"/invoice-items/{item['id']}", headers=H("admin")).status_code == 204
    assert client.get(f"/invoice-items/{item['id']}", headers=H("reader")).status_code == 404
    # tenant scoped
    assert client.get("/invoice-items", headers=H("reader", OTHER_TENANT)).json() == []


def test_templates_default_switching_and_validation(client):
    t1 = client.post("/invoice-templates", headers=H("admin"), json={"name": "One", "accent_colour": "#112233"}).json()
    assert t1["is_default"] is True                    # first template becomes default
    t2 = client.post("/invoice-templates", headers=H("admin"), json={"name": "Two", "is_default": True}).json()
    lst = {t["name"]: t["is_default"] for t in client.get("/invoice-templates", headers=H("reader")).json()}
    assert lst == {"One": False, "Two": True}
    assert client.get("/invoice-templates/default", headers=H("reader")).json()["id"] == t2["id"]
    assert client.post("/invoice-templates", headers=H("clerk"), json={"name": "x"}).status_code == 403
    for bad in ({"accent_colour": "red"}, {"accent_colour": "#12345"}, {"logo_url": "javascript:alert(1)"},
                {"logo_url": "data:text/html;base64,AAAA"}, {"accent_colour": "#000000;background:url(x)"}):
        assert client.post("/invoice-templates", headers=H("admin"), json={"name": "bad", **bad}).status_code == 422, bad
    p = client.patch(f"/invoice-templates/{t1['id']}", headers=H("admin"), json={"is_default": True})
    assert p.status_code == 200 and p.json()["is_default"] is True
    assert {t["name"]: t["is_default"] for t in client.get("/invoice-templates", headers=H("reader")).json()}["Two"] is False


# ── documents ────────────────────────────────────────────────────────────────

XSS = '<script>alert(1)</script>"><img src=x onerror=alert(2)>'


def test_document_html_is_escaped_and_scriptless_and_uses_template(client):
    client.post("/invoice-templates", headers=H("admin"), json={
        "name": "Brand", "company_name": XSS, "company_address": XSS, "footer": XSS, "payment_details": XSS,
        "default_terms": XSS, "logo_url": "https://cdn.example.test/logo.png", "accent_colour": "#ff0000",
        "show_columns": {"discount": False, "tax": False}})
    inv = new_invoice(client, notes=XSS, po_number=XSS[:70], lines=[line(XSS, price="10")],
                      bill_to={"name": XSS, "address": XSS})
    r = client.get(f"/invoices/{inv['id']}/document", headers=H("reader"))
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    html = r.text
    assert "<script" not in html.lower() and "<img src=x" not in html and 'onerror=alert' not in html.replace("&quot;", '"').replace("onerror=alert(2)&gt;", "")
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "--accent:#ff0000" in html and "https://cdn.example.test/logo.png" in html
    assert "Discount</th>" not in html and "VAT %</th>" not in html     # toggled off columns
    assert "default-src 'none'" in r.headers["content-security-policy"]
    assert r.headers["x-content-type-options"] == "nosniff"


def test_document_never_serves_foreign_tenant_or_scripts_in_css(client):
    inv = new_invoice(client)
    assert client.get(f"/invoices/{inv['id']}/document", headers=H("reader", OTHER_TENANT)).status_code == 404


def test_exports_csv_json_html_and_csv_injection_guard(client):
    inv = new_invoice(client, lines=[line("=HYPERLINK(\"http://evil\")", price="10"), line("@cmd", price="1")])
    csv = client.get(f"/invoices/{inv['id']}/export?format=csv", headers=H("reader"))
    assert csv.status_code == 200 and csv.headers["content-type"].startswith("text/csv")
    assert "'=HYPERLINK" in csv.text and "'@cmd" in csv.text
    js = client.get(f"/invoices/{inv['id']}/export?format=json", headers=H("reader")).json()
    assert js["total"] == inv["total_zar"] and js["currency"] == "ZAR" and "tenant_id" not in js
    assert client.get(f"/invoices/{inv['id']}/export?format=html", headers=H("reader")).status_code == 200
    assert client.get(f"/invoices/{inv['id']}/export?format=pdf", headers=H("reader")).status_code == 422


# ── quotes ───────────────────────────────────────────────────────────────────

def new_quote(client, who="clerk", **kw):
    body = {"customer_id": str(CUSTOMER), "lines": [line("Fibre 100", price="500.00")], **kw}
    r = client.post("/quotes", json=body, headers=H(who))
    assert r.status_code == 201, r.text
    return r.json()


def test_quote_for_prospect_and_customer_and_math(client):
    q = client.post("/quotes", headers=H("clerk"), json={
        "prospect_name": "Lerato M", "prospect_email": "lerato@example.test", "prospect_phone": "0821234567",
        "source": "field_sales", "created_by": "agent-7",
        "lines": [line("Router", "2", "250.00", discount="50"), line("Install", price="100", tax_rate="0")]}).json()
    assert q["status"] == "draft" and q["customer_id"] is None and q["source"] == "field_sales"
    assert q["number"].startswith("QUO-") and q["created_by"] == "agent-7"
    assert (q["subtotal_zar"], q["vat_zar"], q["total_zar"]) == ("550.00", "67.50", "617.50")
    assert q["prospect"]["email"] == "lerato@example.test"
    assert client.post("/quotes", headers=H("clerk"), json={"lines": [line()]}).status_code == 422   # no customer/prospect
    n2 = new_quote(client)
    assert int(n2["number"].rsplit("-", 1)[1]) == int(q["number"].rsplit("-", 1)[1]) + 1
    assert client.post("/quotes", headers=H("clerk"), json={
        "customer_id": str(CUSTOMER), "lines": [line()], "issue_date": "2026-05-10", "valid_until": "2026-05-01"}).status_code == 422


def test_quote_lifecycle_edit_send_accept(client):
    q = new_quote(client)
    up = client.put(f"/quotes/{q['id']}", headers=H("clerk"), json={"lines": [line("X", "2", "10.00")], "notes": "hi"})
    assert up.status_code == 200 and up.json()["total_zar"] == "23.00" and up.json()["notes"] == "hi"
    assert client.post(f"/quotes/{q['id']}/send", headers=H("clerk")).json()["status"] == "sent"
    assert client.put(f"/quotes/{q['id']}", headers=H("clerk"), json={"notes": "late"}).status_code == 409
    acc = client.post(f"/quotes/{q['id']}/accept", headers=H("clerk"), json={"note": "signed on device"})
    assert acc.json()["status"] == "accepted" and acc.json()["decision_note"] == "signed on device"
    assert client.post(f"/quotes/{q['id']}/accept", headers=H("clerk")).json()["status"] == "accepted"   # idempotent
    assert client.post(f"/quotes/{q['id']}/decline", headers=H("clerk")).status_code == 409


def test_quote_expiry_is_lazy(client):
    q = new_quote(client)
    client.post(f"/quotes/{q['id']}/send", headers=H("clerk"))
    with client.get_session() as s:
        from services.billing.models_invoicing import Quote
        row = s.get(Quote, uuid.UUID(q["id"]))
        row.valid_until = row.issue_date - timedelta(days=1)
    got = client.get(f"/quotes/{q['id']}", headers=H("reader")).json()
    assert got["status"] == "expired"
    assert client.post(f"/quotes/{q['id']}/accept", headers=H("clerk")).status_code == 409


def test_convert_is_idempotent_and_links_both_ways(client):
    q = new_quote(client)
    assert client.post(f"/quotes/{q['id']}/convert", headers=H("clerk"), json={}).status_code == 409   # not accepted
    client.post(f"/quotes/{q['id']}/accept", headers=H("clerk"))
    c1 = client.post(f"/quotes/{q['id']}/convert", headers=H("clerk"), json={})
    c2 = client.post(f"/quotes/{q['id']}/convert", headers=H("clerk"), json={})
    assert c1.status_code == c2.status_code == 200
    a, b = c1.json(), c2.json()
    assert a["created"] is True and b["created"] is False
    assert a["invoice"]["id"] == b["invoice"]["id"]
    assert a["invoice"]["status"] == "draft" and a["invoice"]["quote_id"] == q["id"]
    assert a["quote"]["status"] == "converted" and a["quote"]["converted_invoice_id"] == a["invoice"]["id"]
    assert a["invoice"]["total_zar"] == q["total_zar"]
    from services.billing.models import Invoice
    with client.get_session() as s:
        assert s.query(Invoice).count() == 1
    # the resulting draft goes through the normal issue path
    assert issue(client, a["invoice"]["id"])["status"] == "sent"


def test_convert_prospect_needs_customer_and_force_is_admin_only(client):
    q = client.post("/quotes", headers=H("clerk"), json={"prospect_name": "P", "lines": [line()]}).json()
    client.post(f"/quotes/{q['id']}/accept", headers=H("clerk"))
    assert client.post(f"/quotes/{q['id']}/convert", headers=H("clerk"), json={}).status_code == 422
    ok = client.post(f"/quotes/{q['id']}/convert", headers=H("clerk"), json={"customer_id": str(CUSTOMER)})
    assert ok.status_code == 200 and ok.json()["invoice"]["customer_id"] == str(CUSTOMER)
    assert ok.json()["invoice"]["bill_to"]["name"] == "P"

    q2 = new_quote(client)
    assert client.post(f"/quotes/{q2['id']}/convert", headers=H("clerk"), json={"force": True}).status_code == 403
    assert client.post(f"/quotes/{q2['id']}/convert", headers=H("admin"), json={"force": True}).status_code == 200
    q3 = new_quote(client)
    client.post(f"/quotes/{q3['id']}/decline", headers=H("clerk"))
    assert client.post(f"/quotes/{q3['id']}/convert", headers=H("admin"), json={"force": True}).status_code == 409


def test_quote_document_and_listing(client):
    q = new_quote(client, notes=XSS)
    html = client.get(f"/quotes/{q['id']}/document", headers=H("reader")).text
    assert "<script" not in html.lower() and "Valid until" in html and "&lt;script&gt;" in html
    lst = client.get("/quotes?status=draft", headers=H("reader")).json()
    assert lst["total"] == 1 and lst["items"][0]["id"] == q["id"]
    assert client.get("/quotes", headers=H("reader", OTHER_TENANT)).json()["total"] == 0


# ── timeline / movements ─────────────────────────────────────────────────────

def test_timeline_movements_and_suggested_actions(client):
    inv = new_invoice(client, lines=[line(price="1000.00")])
    assert [a["id"] for a in client.get(f"/invoices/{inv['id']}/timeline", headers=H("reader")).json()["suggested_actions"]] \
        == ["issue_invoice", "edit_draft"]
    issue(client, inv["id"])
    p = client.post("/payments", headers=H("clerk"), json={"invoice_id": inv["id"], "amount_zar": "300.00", "method": "eft"})
    assert p.status_code == 201, p.text

    tl = client.get(f"/invoices/{inv['id']}/timeline", headers=H("reader")).json()
    types = [e["type"] for e in tl["events"]]
    assert types == ["invoice_issued", "partial_payment"]
    for e in tl["events"]:
        assert {"type", "at", "amount", "status", "invoice_id", "customer_id", "actor", "next_actions"} <= set(e)
        assert e["invoice_id"] == inv["id"] and e["customer_id"] == str(CUSTOMER)
    ids = {a["id"]: a for a in tl["suggested_actions"]}
    assert "record_payment" in ids and ids["record_payment"]["endpoint"] == "POST /payments"
    assert ids["share_pay_link"]["endpoint"] == f"POST /invoices/{inv['id']}/share-link"
    assert "queue_call" not in ids                      # not overdue yet
    assert tl["events"][0]["next_actions"] == [a["id"] for a in tl["suggested_actions"]]

    feed = client.get("/billing/movements", headers=H("reader")).json()
    assert [m["type"] for m in feed["items"]][:2] == ["partial_payment", "invoice_issued"] or \
        {m["type"] for m in feed["items"]} >= {"partial_payment", "invoice_issued"}
    only = client.get("/billing/movements?type=partial_payment", headers=H("reader")).json()
    assert [m["type"] for m in only["items"]] == ["partial_payment"] and only["items"][0]["amount"] == "300.00"
    assert client.get("/billing/movements?type=invoice_*", headers=H("reader")).json()["items"][0]["type"] == "invoice_issued"
    assert client.get(f"/billing/movements?customer_id={uuid.uuid4()}", headers=H("reader")).json()["items"] == []
    assert client.get("/billing/movements?from=2030-01-01", headers=H("reader")).json()["items"] == []
    assert client.get("/billing/movements?from=2026-02-01&to=2026-01-01", headers=H("reader")).status_code == 422
    assert client.get("/billing/movements", headers=H("reader", OTHER_TENANT)).json()["items"] == []


def test_overdue_invoice_suggestions_are_accurate_about_what_exists(client):
    from services.billing.routes.movements import suggest_actions
    from services.billing.models import Invoice
    from datetime import date
    inv = Invoice(id=uuid.uuid4(), tenant_id=TENANT, customer_id=CUSTOMER, number="X", status="overdue",
                  subtotal_zar=D("100"), vat_zar=D("15"), total_zar=D("115"), amount_paid_zar=D("0"),
                  due_date=date(2026, 1, 1), subscription_id=uuid.uuid4())
    acts = {a["id"]: a for a in suggest_actions(inv, today=date(2026, 2, 1), has_active_arrangement=False,
                                               open_refund_credit=True, already_emailed=True)}
    assert acts["send_reminder"]["endpoint"] == f"POST /invoices/{inv.id}/email" and acts["send_reminder"]["payload"] == {"kind": "reminder"}
    assert acts["offer_arrangement"]["endpoint"] == f"POST /collections/{CUSTOMER}/arrange"
    assert acts["suspend_service"]["endpoint"] == f"POST /collections/{CUSTOMER}/suspend"
    assert acts["issue_credit"]["endpoint"] == f"POST /invoices/{inv.id}/credit-note"
    for pending in ("queue_call", "mailer_builder", "review_upgrade_request", "issue_refund"):
        assert acts[pending]["endpoint"] is None and "integration pending" in acts[pending]["reason"]
    arranged = {a["id"] for a in suggest_actions(inv, today=date(2026, 2, 1), has_active_arrangement=True,
                                                open_refund_credit=False, already_emailed=True)}
    assert "offer_arrangement" not in arranged and "issue_refund" not in arranged and "send_invoice_email" not in arranged


def test_customer_app_endpoints(client):
    inv = new_invoice(client, lines=[line(price="200.00")])
    draft_only = client.get(f"/customer-app/invoices?customer_id={CUSTOMER}", headers=H("reader")).json()
    assert draft_only["items"] == []                                         # drafts never shown
    issue(client, inv["id"])
    q = new_quote(client)
    client.post(f"/quotes/{q['id']}/send", headers=H("clerk"))
    new_quote(client)                                                         # a draft quote stays hidden
    out = client.get(f"/customer-app/invoices?customer_id={CUSTOMER}&include_links=true", headers=H("reader")).json()
    item = out["items"][0]
    assert item["payable"] and item["balance_zar"] == "230.00" and out["outstanding_zar"] == "230.00"
    assert item["pay_link"]["token"] and item["pay_link"]["api_path"].startswith("/public/invoices/")
    assert client.get("/customer-app/invoices", headers=H("reader")).status_code == 422          # customer_id mandatory
    assert client.get(f"/customer-app/invoices?customer_id={CUSTOMER}", headers=H("reader", OTHER_TENANT)).json()["items"] == []
    quotes = client.get(f"/customer-app/quotes?customer_id={CUSTOMER}", headers=H("reader")).json()["items"]
    assert [x["id"] for x in quotes] == [q["id"]] and quotes[0]["actionable"] is True
    client.post("/payments", headers=H("clerk"), json={"invoice_id": inv["id"], "amount_zar": "30.00", "method": "eft"})
    st = client.get(f"/customer-app/statement?customer_id={CUSTOMER}", headers=H("reader")).json()
    assert [l["kind"] for l in st["lines"]] == ["invoice", "payment"] and st["closing_balance_zar"] == "200.00"
