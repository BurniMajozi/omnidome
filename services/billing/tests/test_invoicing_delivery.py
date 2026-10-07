"""Emailing documents through the Communication service (mocked): claims, definite vs ambiguous failure,
idempotency, suppression, throttling, and the provider webhook."""
import os
import sys
import uuid

import httpx
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from services.billing.tests.invoicing_env import CUSTOMER, TENANT, H, issue, line, make_env, new_invoice  # noqa: E402


class Mail:
    """Stand-in for Communication's POST /api/v1/mail/send."""
    def __init__(self):
        self.calls, self.script = [], []

    async def __call__(self, service, path, **kw):
        assert (service, path) == ("communication", "/api/v1/mail/send")
        self.calls.append(kw["json"])
        step = self.script.pop(0) if self.script else {"status": "sent", "message_id": f"msg-{len(self.calls)}"}
        if isinstance(step, Exception):
            raise step
        return step


def http_error(code):
    return httpx.HTTPStatusError("x", request=httpx.Request("POST", "http://comm"), response=httpx.Response(code))


@pytest.fixture
def env(monkeypatch):
    client = make_env(monkeypatch)
    from services.billing import delivery

    mail = Mail()
    monkeypatch.setattr(delivery, "service_post", mail)

    async def mailbox(*_a, **_k):
        return "mbx-1"

    async def no_suppression(tenant_id, emails):
        return list(emails), []

    async def customer_email(*_a, **_k):
        return "customer@example.test"
    monkeypatch.setattr(delivery, "resolve_mailbox_id", mailbox)
    monkeypatch.setattr(delivery, "filter_suppressed_addresses", no_suppression)
    monkeypatch.setattr(delivery, "resolve_customer_email", customer_email)
    client.mail = mail
    return client


def issued(client):
    inv = new_invoice(client, lines=[line("Fibre <b>100</b>", price="500.00")])
    issue(client, inv["id"])
    return inv


def events(client, inv_id):
    return client.get(f"/invoices/{inv_id}/delivery-events", headers=H("reader")).json()


def email(client, inv_id, body=None, key=None, who="clerk"):
    h = H(who)
    if key:
        h["Idempotency-Key"] = key
    return client.post(f"/invoices/{inv_id}/email", json=body or {}, headers=h)


def test_send_success_stores_message_id_link_and_html_body(env):
    inv = issued(env)
    r = email(env, inv["id"], {"to": ["Pay@Example.test"], "message": "Hello <script>x</script>"})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["status"] == "sent" and out["message_id"] == "msg-1" and out["recipients"]["to"] == ["pay@example.test"]
    sent = env.mail.calls[0]
    assert sent["mailbox_id"] == "mbx-1" and sent["to"] == ["pay@example.test"] and sent["subject"].startswith("Tax invoice")
    assert "https://app.example.test/public/invoices/" in sent["body_html"] and "https://app.example.test/public/invoices/" in sent["body_text"]
    assert "<script" not in sent["body_html"].lower() and "&lt;script&gt;" in sent["body_html"]
    assert "&lt;b&gt;100&lt;/b&gt;" in sent["body_html"]                   # document embedded, escaped
    ev = events(env, inv["id"])
    assert [(e["event_type"], e["message_id"]) for e in ev] == [("sent", "msg-1")]
    tl = env.get(f"/invoices/{inv['id']}/timeline", headers=H("reader")).json()["events"]
    assert "invoice_emailed" in [e["type"] for e in tl]
    # the emailed link really opens the invoice
    tok = sent["body_text"].rsplit("/public/invoices/", 1)[1].split()[0]
    assert env.get(f"/public/invoices/{tok}").status_code == 200


def test_default_recipient_comes_from_customer_record_and_roles(env):
    inv = issued(env)
    assert email(env, inv["id"], who="reader").status_code == 403
    r = email(env, inv["id"])
    assert r.status_code == 200 and env.mail.calls[0]["to"] == ["customer@example.test"]


def test_preconditions(env):
    draft = new_invoice(env)
    assert email(env, draft["id"]).status_code == 409                      # issue first
    assert email(env, str(uuid.uuid4())).status_code == 404
    inv = issued(env)
    env.post(f"/payments", headers=H("clerk"), json={"invoice_id": inv["id"], "amount_zar": inv["total_zar"], "method": "eft"})
    assert email(env, inv["id"], {"kind": "reminder"}).status_code == 409   # nothing to remind about once paid
    assert email(env, inv["id"], {"to": ["not-an-email"]}).status_code == 422
    assert env.mail.calls == []


def test_reminder_kind(env):
    inv = issued(env)
    r = email(env, inv["id"], {"kind": "reminder"})
    assert r.status_code == 200
    assert env.mail.calls[0]["subject"].startswith("Reminder: invoice")
    assert "reminder" in env.mail.calls[0]["body_text"].lower()
    assert [e["kind"] for e in events(env, inv["id"])] == ["reminder"]


def test_idempotent_replay_does_not_send_twice(env):
    inv = issued(env)
    a = email(env, inv["id"], key="k-1").json()
    b = email(env, inv["id"], key="k-1")
    assert b.status_code == 200 and b.json()["replayed"] is True and b.json()["message_id"] == a["message_id"]
    assert len(env.mail.calls) == 1
    other = issued(env)
    assert email(env, other["id"], key="k-1").status_code == 409            # a key cannot be reused for another document


def test_definite_failure_clears_the_claim_so_retry_works(env):
    inv = issued(env)
    env.mail.script = [http_error(422)]
    r = email(env, inv["id"], key="k-2")
    assert r.status_code == 502 and "nothing was sent" in r.json()["detail"]
    ev = events(env, inv["id"])
    assert [e["event_type"] for e in ev] == ["failed"]
    retry = email(env, inv["id"], key="k-2")                                # same key is usable again
    assert retry.status_code == 200 and retry.json()["replayed"] is False
    assert len(env.mail.calls) == 2


def test_mail_service_reporting_failed_is_definite(env):
    inv = issued(env)
    env.mail.script = [{"status": "failed"}]
    assert email(env, inv["id"]).status_code == 502
    assert [e["event_type"] for e in events(env, inv["id"])] == ["failed"]
    assert email(env, inv["id"]).status_code == 200


@pytest.mark.parametrize("failure", [httpx.ReadTimeout("slow"), http_error(503), {"status": "queued"}, {"status": "sent"}, None])
def test_ambiguous_outcome_blocks_resend_until_reconciled(env, failure):
    inv = issued(env)
    env.mail.script = [failure if not isinstance(failure, dict) else failure]
    if failure is None:
        env.mail.script = [RuntimeError("boom")]
    r = email(env, inv["id"], key="k-3")
    assert r.status_code == 502 and "reconcile" in r.json()["detail"]
    ev = events(env, inv["id"])
    assert [e["event_type"] for e in ev] == ["queued"] and ev[0]["detail"]["ambiguous"] is True
    blocked = email(env, inv["id"])
    assert blocked.status_code == 409 and len(env.mail.calls) == 1          # never auto-sends twice
    assert env.post(f"/delivery/events/{ev[0]['id']}/reconcile", json={"outcome": "sent"}, headers=H("clerk")).status_code == 403
    rec = env.post(f"/delivery/events/{ev[0]['id']}/reconcile", json={"outcome": "not_sent"}, headers=H("admin"))
    assert rec.status_code == 200 and rec.json()["event_type"] == "failed"
    assert email(env, inv["id"]).status_code == 200
    assert env.post(f"/delivery/events/{ev[0]['id']}/reconcile", json={"outcome": "sent"}, headers=H("admin")).status_code == 409


def test_reconcile_as_sent_records_message(env):
    inv = issued(env)
    env.mail.script = [httpx.ReadTimeout("slow")]
    email(env, inv["id"])
    ev = events(env, inv["id"])[0]
    r = env.post(f"/delivery/events/{ev['id']}/reconcile", json={"outcome": "sent", "message_id": "m-9"}, headers=H("admin"))
    assert r.json() == {"id": ev["id"], "event_type": "sent", "message_id": "m-9"}


def test_suppressed_recipients_are_never_mailed(env, monkeypatch):
    from services.billing import delivery
    inv = issued(env)

    async def suppress(tenant_id, emails):
        return [e for e in emails if e != "blocked@example.test"], [e for e in emails if e == "blocked@example.test"]
    monkeypatch.setattr(delivery, "filter_suppressed_addresses", suppress)
    r = email(env, inv["id"], {"to": ["blocked@example.test"]})
    assert r.status_code == 409 and env.mail.calls == []
    assert [e["event_type"] for e in events(env, inv["id"])] == ["suppressed"]
    ok = email(env, inv["id"], {"to": ["blocked@example.test", "fine@example.test"], "cc": ["blocked@example.test"]})
    assert ok.status_code == 200
    assert env.mail.calls[0]["to"] == ["fine@example.test"] and env.mail.calls[0]["cc"] == []


def test_per_recipient_throttle(env, monkeypatch):
    monkeypatch.setenv("BILLING_EMAIL_MAX_PER_RECIPIENT_HOUR", "2")
    inv = issued(env)
    codes = [email(env, inv["id"], {"to": ["same@example.test"]}).status_code for _ in range(3)]
    assert codes == [200, 200, 429]
    assert email(env, inv["id"], {"to": ["other@example.test"]}).status_code == 200   # different recipient unaffected
    other_doc = issued(env)
    assert email(env, other_doc["id"], {"to": ["same@example.test"]}).status_code == 200


def test_quote_email_marks_sent_and_failure_leaves_draft(env):
    q = env.post("/quotes", headers=H("clerk"), json={
        "prospect_name": "Lee", "prospect_email": "lee@example.test", "lines": [line(price="100")]}).json()
    env.mail.script = [http_error(400)]
    assert env.post(f"/quotes/{q['id']}/email", json={}, headers=H("clerk")).status_code == 502
    assert env.get(f"/quotes/{q['id']}", headers=H("reader")).json()["status"] == "draft"
    ok = env.post(f"/quotes/{q['id']}/email", json={}, headers=H("clerk"))
    assert ok.status_code == 200 and env.mail.calls[-1]["to"] == ["lee@example.test"]
    assert "/public/quotes/" in env.mail.calls[-1]["body_text"]
    assert env.get(f"/quotes/{q['id']}", headers=H("reader")).json()["status"] == "sent"
    assert env.post(f"/quotes/{q['id']}/email", json={"kind": "reminder"}, headers=H("clerk")).status_code == 422


# ── provider webhook ─────────────────────────────────────────────────────────

KEY = {"x-internal-key": "k" * 20}


def hook(client, **body):
    base = {"tenant_id": str(TENANT), "message_id": "msg-1", "event_type": "delivered"}
    return client.post("/delivery/webhook-event", json={**base, **body}, headers=KEY)


def test_webhook_requires_internal_key(env, monkeypatch):
    monkeypatch.setenv("INTERNAL_SERVICE_KEY", "k" * 20)
    assert env.post("/delivery/webhook-event", json={"tenant_id": str(TENANT), "message_id": "m", "event_type": "delivered"}).status_code == 403
    assert env.post("/delivery/webhook-event", headers={"x-internal-key": "wrong"},
                    json={"tenant_id": str(TENANT), "message_id": "m", "event_type": "delivered"}).status_code == 403
    monkeypatch.delenv("INTERNAL_SERVICE_KEY")
    assert hook(env).status_code == 403                                      # no key configured = closed


def test_webhook_records_delivery_facts_idempotently(env, monkeypatch):
    from services.billing import delivery
    monkeypatch.setenv("INTERNAL_SERVICE_KEY", "k" * 20)
    suppressed = []

    async def add(tenant_id, email, reason):
        suppressed.append((email, reason))
    monkeypatch.setattr(delivery, "add_suppression_best_effort", add)
    inv = issued(env)
    email(env, inv["id"], {"to": ["bounce@example.test"]})
    assert hook(env).json() == {"status": "accepted", "matched": 1, "recorded": 1}
    assert hook(env).json()["recorded"] == 0                                  # provider retry: no duplicate
    assert hook(env, event_type="bounced").json()["recorded"] == 1
    assert suppressed == [("bounce@example.test", "bounce")]
    assert hook(env, event_type="rejected").status_code == 200
    assert hook(env, event_type="replied").status_code == 200
    types = [e["event_type"] for e in events(env, inv["id"])]
    assert types == ["sent", "delivered", "bounced", "failed", "replied"]
    assert hook(env, message_id="unknown").json()["status"] == "ignored"
    assert hook(env, event_type="exploded").status_code == 422
    other_tenant = hook(env, tenant_id=str(uuid.uuid4()))
    assert other_tenant.json()["status"] == "ignored"                         # tenant-scoped match
    tl = env.get(f"/invoices/{inv['id']}/timeline", headers=H("reader")).json()["events"]
    assert {"invoice_delivered", "invoice_bounced", "invoice_replied"} <= {e["type"] for e in tl}


def test_bounce_with_several_recipients_only_suppresses_named_addresses(env, monkeypatch):
    from services.billing import delivery
    monkeypatch.setenv("INTERNAL_SERVICE_KEY", "k" * 20)
    suppressed = []

    async def add(tenant_id, addr, reason):
        suppressed.append(addr)
    monkeypatch.setattr(delivery, "add_suppression_best_effort", add)
    inv = issued(env)
    email(env, inv["id"], {"to": ["a@example.test", "b@example.test"]})
    hook(env, event_type="bounced")
    assert suppressed == []                                                   # ambiguous: no blanket suppression
    inv2 = issued(env)
    email(env, inv2["id"], {"to": ["a@example.test", "b@example.test"]})
    hook(env, message_id="msg-2", event_type="bounced", detail={"recipient": "b@example.test"})
    assert suppressed == ["b@example.test"]
