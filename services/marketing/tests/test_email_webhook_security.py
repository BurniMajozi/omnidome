"""/email/webhook (AgentMail delivery events): pre-checks before DB work, per-owner secret.
The DB is faked. Run from repo root: python -m pytest services/marketing/tests/test_email_webhook_security.py -q
"""
import base64
import hashlib
import hmac
import json
import os
import sys
import time
import uuid
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))

from services.common import agentmail  # noqa: E402
from services.marketing import main as mk  # noqa: E402

A = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
B = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
SEC_A = "whsec_" + base64.b64encode(b"tenant-a-secret-bytes-0123456789").decode()
SEC_B = "whsec_" + base64.b64encode(b"tenant-b-secret-bytes-0123456789").decode()


def sign(body, secret, ts=None):
    ts = int(time.time()) if ts is None else ts
    sig = base64.b64encode(hmac.new(base64.b64decode(secret[6:]), f"m1.{ts}.".encode() + body,
                                    hashlib.sha256).digest()).decode()
    return {"svix-id": "m1", "svix-timestamp": str(ts), "svix-signature": f"v1,{sig}"}


class Conn:
    def __init__(self, log):
        self.log = log

    def execute(self, stmt, params=None):
        q = str(stmt)
        self.log.append(q)
        row = {"tenant_id": B, "batch_id": uuid.uuid4(), "recipient_email": "x@y.co"}
        return SimpleNamespace(mappings=lambda: SimpleNamespace(first=lambda: row))


@pytest.fixture
def client(monkeypatch):
    log = []

    class Engine:
        @contextmanager
        def begin(self):
            log.append("BEGIN")
            yield Conn(log)

    monkeypatch.setattr(mk, "get_engine", lambda: Engine())
    monkeypatch.setattr(mk, "_ensure_marketing_tables", lambda e: None)
    monkeypatch.setattr(agentmail, "owner_webhook_secrets_sync",
                        lambda conn, tid: {A: [SEC_A], B: [SEC_B]}.get(tid, []))
    return TestClient(mk.app), log


def delivered():
    return json.dumps({"event_type": "message.delivered", "message": {"message_id": "<m>"}}).encode()


def test_prechecks_reject_before_any_db_work(client):
    c, log = client
    assert c.post("/email/webhook", content=delivered()).status_code == 401
    stale = sign(delivered(), SEC_B, ts=int(time.time()) - 3600)
    assert c.post("/email/webhook", content=delivered(), headers=stale).status_code == 401
    big = b"x" * (agentmail.MAX_WEBHOOK_BODY_BYTES + 1)
    assert c.post("/email/webhook", content=big, headers=sign(big, SEC_B)).status_code == 413
    assert log == []


def test_only_the_owning_tenants_secret_is_accepted(client):
    c, log = client
    body = delivered()
    assert c.post("/email/webhook", content=body, headers=sign(body, SEC_A)).status_code == 401  # A forging for B
    assert c.post("/email/webhook", content=body, headers=sign(body, SEC_B)).status_code == 200
