"""Secrets in URLs must never reach the logs. cwd = services/communication: python -m pytest tests -q"""
import io
import logging
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, REPO_ROOT)

from services.communication.log_redact import RedactSecretsFilter, redact  # noqa: E402

JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjMifQ.c2lnbmF0dXJl"


def test_redacts_query_values():
    out = redact(f"GET /api/v1/ws?channel_id=abc&token={JWT}&x=1 HTTP/1.1")
    assert JWT not in out and "token=REDACTED" in out and "channel_id=abc" in out and "x=1" in out
    assert "access_token=REDACTED" in redact("/p?access_token=abc123&a=b")
    assert "apikey=REDACTED" in redact("/p?a=b&apikey=sekret")


def test_redacts_authorization_and_bare_jwt():
    assert "Bearer abc" not in redact("Authorization: Bearer abc.def")
    assert JWT not in redact(f"value {JWT} end")


def test_leaves_normal_text():
    s = "GET /api/v1/channels?limit=10 HTTP/1.1"
    assert redact(s) == s


def test_uvicorn_style_access_record_args_redacted():
    buf = io.StringIO()
    lg = logging.getLogger("test.access")
    lg.propagate = False
    h = logging.StreamHandler(buf)
    h.addFilter(RedactSecretsFilter())
    lg.addHandler(h)
    lg.setLevel(logging.INFO)
    lg.info('%s - "%s %s HTTP/%s" %d', "1.2.3.4:5", "GET", f"/ws?token={JWT}", "1.1", 101)
    assert JWT not in buf.getvalue() and "token=REDACTED" in buf.getvalue()
