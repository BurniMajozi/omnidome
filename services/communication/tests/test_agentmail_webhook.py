"""AgentMail inbound webhook (services/communication/routes/mail.py).

The webhook is public at the middleware: the Svix signature is its only
authentication, so these tests pin who gets in. The database helpers are
stubbed; the route, signature check and payload handling are real.

Run with cwd = services/communication:  python -m pytest tests -q
"""

import base64
import hashlib
import hmac
import json
import os
import sys
import time
from contextlib import asynccontextmanager

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, REPO_ROOT)

from services.communication.routes import mail  # noqa: E402

SECRET = "whsec_" + base64.b64encode(b"test-webhook-secret-32-bytes!!!!").decode()
OTHER_SECRET = "whsec_" + base64.b64encode(b"some-other-tenant-secret-bytes!!").decode()


def sign(body: bytes, secret: str = SECRET, msg_id: str = "msg_1", ts: int | None = None) -> dict:
    ts = int(time.time()) if ts is None else ts
    key = base64.b64decode(secret[len("whsec_"):])
    sig = base64.b64encode(hmac.new(key, f"{msg_id}.{ts}.".encode() + body, hashlib.sha256).digest()).decode()
    return {"svix-id": msg_id, "svix-timestamp": str(ts), "svix-signature": f"v1,{sig}",
            "content-type": "application/json"}


def received(**message) -> bytes:
    msg = {"from_": ["Thandi Mokoena <thandi@example.com>"], "to": ["support@omnidome.agentmail.to"],
           "subject": "Router blinking red", "text": "Hi, my router is blinking red since this morning.",
           "message_id": "<abc@example.com>", "thread_id": "t1", "inbox_id": "support@omnidome.agentmail.to"}
    msg.update(message)
    return json.dumps({"event_type": "message.received", "message": msg}).encode()


class Calls:
    def __init__(self):
        self.ingested, self.delivery = [], []


@pytest.fixture
def api(monkeypatch):
    calls = Calls()

    @asynccontextmanager
    async def no_db(*_a, **_k):
        yield None

    async def secrets(_session):
        return [SECRET]

    async def ingest(payload):
        calls.ingested.append(payload)
        return type("Row", (), {"id": "email-1"})() if "nobody" not in payload.recipient else None

    async def delivery(event_type, msg, detail):
        calls.delivery.append(event_type)

    monkeypatch.setattr(mail, "get_session", no_db)
    monkeypatch.setattr(mail, "_webhook_secrets", secrets)
    monkeypatch.setattr(mail, "_ingest_for_recipient", ingest)
    monkeypatch.setattr(mail, "_apply_delivery_event", delivery)
    app = FastAPI()
    app.include_router(mail.router)
    return TestClient(app), calls


def post(client, body: bytes, headers: dict):
    return client.post("/mail/webhook", content=body, headers=headers)


def test_signed_inbound_mail_is_accepted_and_normalised(api):
    client, calls = api
    body = received()
    r = post(client, body, sign(body))
    assert r.status_code == 200 and r.json() == {"status": "accepted", "email_id": "email-1"}
    p = calls.ingested[0]
    assert p.sender == "Thandi Mokoena <thandi@example.com>"
    assert p.recipient == "support@omnidome.agentmail.to"
    assert p.subject == "Router blinking red" and "blinking red" in p.body_text


@pytest.mark.parametrize("headers", [
    {"content-type": "application/json"},                                        # unsigned
    {"svix-id": "msg_1", "svix-timestamp": str(int(time.time())), "svix-signature": "v1,AAAA"},  # forged
])
def test_unsigned_or_forged_requests_are_rejected(api, headers):
    client, calls = api
    r = post(client, received(), headers)
    assert r.status_code == 401 and calls.ingested == []


def test_signature_from_another_secret_is_rejected(api):
    client, calls = api
    body = received()
    assert post(client, body, sign(body, secret=OTHER_SECRET)).status_code == 401
    assert calls.ingested == []


def test_replayed_old_delivery_is_rejected(api):
    client, calls = api
    body = received()
    r = post(client, body, sign(body, ts=int(time.time()) - 3600))
    assert r.status_code == 401 and calls.ingested == []


def test_body_changed_after_signing_is_rejected(api):
    client, calls = api
    headers = sign(received())
    r = post(client, received(subject="Please wire R50 000 to this account"), headers)
    assert r.status_code == 401 and calls.ingested == []


def test_no_configured_secret_refuses_everything(api, monkeypatch):
    client, calls = api

    async def none(_session):
        return []
    monkeypatch.setattr(mail, "_webhook_secrets", none)
    body = received()
    assert post(client, body, sign(body)).status_code == 503 and calls.ingested == []


def test_delivery_events_are_applied_and_other_events_ignored(api):
    client, calls = api
    bounced = json.dumps({"event_type": "message.bounced", "message": {"message_id": "<x>"}}).encode()
    assert post(client, bounced, sign(bounced)).json()["status"] == "accepted"
    assert calls.delivery == ["message.bounced"]
    other = json.dumps({"event_type": "domain.verified", "message": {}}).encode()
    assert post(client, other, sign(other)).json() == {"status": "ignored", "event": "domain.verified"}
    assert calls.ingested == []


def test_mail_for_an_unknown_mailbox_is_404(api):
    client, _ = api
    body = received(to=["nobody@omnidome.agentmail.to"], inbox_id="nobody@omnidome.agentmail.to")
    assert post(client, body, sign(body)).status_code == 404


def test_signed_but_malformed_payloads_are_400(api):
    client, _ = api
    for body in (b"not json", json.dumps({"event_type": "message.received", "message": "text"}).encode()):
        assert post(client, body, sign(body)).status_code == 400
