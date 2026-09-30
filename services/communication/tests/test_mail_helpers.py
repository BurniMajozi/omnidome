"""AgentMail client helpers (services/common/agentmail.py) and outbound mail
helpers (services/communication/routes/mail.py): signatures, tenant-secret
encryption, message normalisation, address checks, reply formatting.

Run with cwd = services/communication:  python -m pytest tests -q
"""

import base64
import hashlib
import hmac
import os
import sys
import time

import pytest
from fastapi import HTTPException

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, REPO_ROOT)

from services.common import agentmail  # noqa: E402
from services.communication.routes import mail  # noqa: E402

KEY = b"test-webhook-secret-32-bytes!!!!"


def headers_for(body: bytes, key: bytes = KEY, ts: int | None = None, extra_sigs: str = "") -> dict:
    ts = int(time.time()) if ts is None else ts
    sig = base64.b64encode(hmac.new(key, f"m1.{ts}.".encode() + body, hashlib.sha256).digest()).decode()
    return {"svix-id": "m1", "svix-timestamp": str(ts), "svix-signature": f"{extra_sigs}v1,{sig}".strip()}


# ── verify_svix ─────────────────────────────────────────────────────────────

def test_accepts_whsec_prefixed_and_raw_secrets():
    body = b'{"a":1}'
    raw = base64.b64encode(KEY).decode()
    assert agentmail.verify_svix(body, headers_for(body), ["whsec_" + raw])
    assert agentmail.verify_svix(body, headers_for(body), [raw])


def test_accepts_when_any_of_several_signatures_or_secrets_match():
    # Svix sends several space-separated signatures during secret rotation.
    body = b"{}"
    raw = base64.b64encode(KEY).decode()
    h = headers_for(body, extra_sigs="v1,bm90LXRoaXMtb25l ")
    assert agentmail.verify_svix(body, h, ["whsec_" + base64.b64encode(b"x" * 32).decode(), "whsec_" + raw])


def test_rejects_stale_future_or_garbled_timestamps():
    body, raw = b"{}", base64.b64encode(KEY).decode()
    assert not agentmail.verify_svix(body, headers_for(body, ts=int(time.time()) - 301), [raw])
    assert not agentmail.verify_svix(body, headers_for(body, ts=int(time.time()) + 301), [raw])
    h = headers_for(body)
    h["svix-timestamp"] = "yesterday"
    assert not agentmail.verify_svix(body, h, [raw])


def test_rejects_missing_headers_and_unusable_secrets():
    body = b"{}"
    assert not agentmail.verify_svix(body, {}, [base64.b64encode(KEY).decode()])
    assert not agentmail.verify_svix(body, headers_for(body), ["", "not base64 !!!"])


# ── Tenant secret encryption ────────────────────────────────────────────────

def test_secrets_round_trip_and_are_not_stored_in_clear(monkeypatch):
    from cryptography.fernet import Fernet
    monkeypatch.setenv("SECRETS_ENCRYPTION_KEY", Fernet.generate_key().decode())
    token = agentmail.encrypt_secret("am_live_secret_value")
    assert "am_live_secret_value" not in token
    assert agentmail.decrypt_secret(token) == "am_live_secret_value"


def test_no_or_bad_encryption_key_refuses_instead_of_storing_in_clear(monkeypatch):
    monkeypatch.delenv("SECRETS_ENCRYPTION_KEY", raising=False)
    with pytest.raises(agentmail.SecretsUnavailable):
        agentmail.encrypt_secret("x")
    monkeypatch.setenv("SECRETS_ENCRYPTION_KEY", "not-a-fernet-key")
    with pytest.raises(agentmail.SecretsUnavailable):
        agentmail.encrypt_secret("x")


# ── Message normalisation ───────────────────────────────────────────────────

def test_webhook_and_rest_message_shapes_normalise_the_same():
    webhook = {"from_": ["A <a@x.com>"], "to": ["Inbox <in@y.to>"], "subject": "Hi", "text": "t", "message_id": "m"}
    rest = {"from": "A <a@x.com>", "to": ["in@y.to"], "subject": "Hi", "text": "t", "message_id": "m"}
    for shape in (webhook, rest):
        n = agentmail.normalize_message(shape)
        assert n["sender"] == "A <a@x.com>" and n["recipient"] == "in@y.to" and n["message_id"] == "m"


def test_missing_fields_get_safe_defaults_and_long_ones_are_cut():
    n = agentmail.normalize_message({"inbox_id": "in@y.to", "preview": "p", "subject": "s" * 900})
    assert n["recipient"] == "in@y.to" and n["body_text"] == "p" and len(n["subject"]) == 500
    assert agentmail.normalize_message({})["subject"] == "(no subject)"


def test_bare_address():
    assert agentmail.bare_address("Thandi <t@x.com>") == "t@x.com"
    assert agentmail.bare_address(["t@x.com", "u@x.com"]) == "t@x.com"
    assert agentmail.bare_address(None) == ""


# ── Outbound helpers ────────────────────────────────────────────────────────

def test_addresses_are_validated_and_deduplicated_case_insensitively():
    assert mail._clean_addrs(["a@x.com", " A@X.com ", "", "b@y.org"], "to") == ["a@x.com", "b@y.org"]
    with pytest.raises(HTTPException) as exc:
        mail._clean_addrs(["not-an-address"], "cc")
    assert exc.value.status_code == 422 and "cc" in exc.value.detail


def test_plain_text_bodies_are_html_escaped():
    html = mail._text_to_html('<script>alert("x")</script>\nline 2')
    assert "<script>" not in html and "&lt;script&gt;" in html and "white-space:pre-wrap" in html


def test_reply_subject_and_target():
    assert mail._reply_subject("Router issue") == "Re: Router issue"
    assert mail._reply_subject("RE: Router issue") == "RE: Router issue"
    assert mail._reply_target("Thandi Mokoena <thandi@example.com>") == "thandi@example.com"
    assert mail._reply_target("thandi@example.com") == "thandi@example.com"
