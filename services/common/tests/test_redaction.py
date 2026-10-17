"""Tickets must never carry secrets, tokens or customer PII."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

import pytest  # noqa: E402

from services.common.redaction import redact_data, redact_text  # noqa: E402

JWT = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"


@pytest.mark.parametrize("raw,leak", [
    (f"Authorization: Bearer {JWT}", JWT),
    ("request failed with Bearer abcdef1234567890abcdef", "abcdef1234567890abcdef"),
    ("password=hunter2hunter2 failed", "hunter2hunter2"),
    ("db url postgresql://admin:s3cr3tpass@db:5432/coreconnect", "s3cr3tpass"),
    ("GET /cb?token=abc123def456ghi789&x=1", "abc123def456ghi789"),
    ("key sk-live-AbCdEfGhIjKlMnOpQrStUv", "AbCdEfGhIjKlMnOpQrStUv"),
    ("contact jane.doe@example.co.za please", "jane.doe@example.co.za"),
    ("call +27 82 123 4567 or 0821234567", "0821234567"),
    ("id 8001015009087 on file", "8001015009087"),
    ("card 4111 1111 1111 1111 declined", "4111 1111 1111 1111"),
    ("account number 1234567890 overdrawn", "1234567890"),
    ("signed AKIAIOSFODNN7EXAMPLE", "AKIAIOSFODNN7EXAMPLE"),
    ("-----BEGIN PRIVATE KEY-----\nMIIEvQIBADANBgkqhkiG9w0BAQEFAASC\n-----END PRIVATE KEY-----", "MIIEvQIBADANBgkqhkiG9w0BAQEFAASC"),
    ("hash 5f4dcc3b5aa765d61d8327deb882cf995f4dcc3b5aa765d6", "5f4dcc3b5aa765d61d8327deb882cf99"),
])
def test_text_is_redacted(raw, leak):
    out = redact_text(raw)
    assert leak not in out, out
    assert "[redacted" in out


def test_ordinary_text_survives():
    msg = "KeyError in billing.routes.create_invoice: missing field 'currency' (attempt 3)"
    assert redact_text(msg) == msg


def test_none_and_limit():
    assert redact_text(None) == ""
    out = redact_text("x " * 5000, limit=100)
    assert len(out) <= 100 and out.endswith("…")


def test_data_drops_secret_and_pii_keys():
    out = redact_data({"api_key": "abc", "Authorization": "Bearer x", "email": "a@b.co", "phone": "0821234567",
                       "name": "Jane", "invoice_id": "inv-1", "nested": {"password": "p", "note": "mail me at a@b.co"},
                       "items": [{"token": "t"}, "call 0821234567"], "count": 3})
    assert out["api_key"] == "[redacted-secret]" and out["Authorization"] == "[redacted-secret]"
    assert out["email"] == "[redacted-pii]" and out["phone"] == "[redacted-pii]" and out["name"] == "[redacted-pii]"
    assert out["invoice_id"] == "inv-1" and out["count"] == 3
    assert out["nested"]["password"] == "[redacted-secret]" and "a@b.co" not in out["nested"]["note"]
    assert out["items"][0]["token"] == "[redacted-secret]" and "0821234567" not in out["items"][1]


def test_redaction_is_idempotent():
    """Text is redacted at the hook, again by the rule table and again on insert: it must not grow or change."""
    raw = ("KeyError: 'no currency for jane@example.com using Bearer abcdefghijklmnop123456 password=hunter2hunter2' "
           "token: abcdefghij1234567890 call 0821234567 id 8001015009087")
    once = redact_text(raw)
    assert redact_text(once) == once == redact_text(redact_text(once))
    assert "]]" not in once
