"""Marketing Zernio tests — pure logic, no DB, no network.

Run from repo root:  PYTHONPATH=. .venv/Scripts/python -m pytest services/marketing/tests/ -q
Covers: webhook normalization, sentiment detection, HMAC verification,
escalation keywords, reaction normalization.
"""

import hashlib
import hmac
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))

from services.marketing.chat_webhooks import (  # noqa: E402
    ChatEngine,
    _detect_sentiment,
    normalize_reaction_event,
    normalize_webhook_event,
)
from services.marketing.zernio_client import ZernioClient  # noqa: E402


def sample_event(**overrides):
    evt = {
        "event_type": "message.received",
        "platform": "telegram",
        "conversation_id": "conv_abc",
        "message_id": "msg_xyz",
        "sender": {"name": "John Doe", "handle": "johndoe"},
        "content": "Hello, I need help",
        "timestamp": "2026-07-02T10:00:00Z",
    }
    evt.update(overrides)
    return evt


# ── normalization ──────────────────────────────────────────────────────

def test_normalize_dm():
    n = normalize_webhook_event(sample_event())
    assert n["message_type"] == "DM"
    assert n["platform"] == "telegram"
    assert n["external_id"] == "msg_xyz"
    assert n["sender_name"] == "John Doe"
    assert n["status"] == "UNREAD"
    assert n["conversation_id"] == "conv_abc"


def test_normalize_comment_and_mention():
    assert normalize_webhook_event(sample_event(event_type="comment.received"))["message_type"] == "COMMENT"
    assert normalize_webhook_event(sample_event(event_type="mention.received"))["message_type"] == "MENTION"


def test_normalize_platform_alias():
    n = normalize_webhook_event(sample_event(platform="x"))
    assert n["platform"] == "twitter"


def test_normalize_missing_sender():
    n = normalize_webhook_event(sample_event(sender={}))
    assert n["sender_name"] == "Unknown"


def test_normalize_text_fallback_and_thread():
    n = normalize_webhook_event({"event_type": "message.received", "platform": "whatsapp",
                                 "text": "hi", "parent_id": "p1"})
    assert n["content"] == "hi"
    assert n["parent_id"] == "p1"


# ── sentiment ──────────────────────────────────────────────────────────

def test_sentiment_positive():
    assert _detect_sentiment("Thanks, that was awesome!") == "POSITIVE"


def test_sentiment_negative():
    assert _detect_sentiment("This is broken, I want a refund") == "NEGATIVE"


def test_sentiment_neutral_and_empty():
    assert _detect_sentiment("What are your hours?") == "NEUTRAL"
    assert _detect_sentiment("") == "NEUTRAL"


def test_sentiment_attached_to_normalized():
    n = normalize_webhook_event(sample_event(content="Terrible service, very angry"))
    assert n["sentiment"] == "NEGATIVE"


# ── escalation ─────────────────────────────────────────────────────────

def test_should_escalate_keywords():
    engine = ChatEngine(db_session_factory=None)
    assert engine._should_escalate("I want a refund now") is True
    assert engine._should_escalate("billing overcharge on my account") is True
    assert engine._should_escalate("What are your hours?") is False


# ── HMAC verification ──────────────────────────────────────────────────

def test_verify_webhook_valid():
    secret = "test-secret-123"
    body = b'{"event_type": "message.received"}'
    sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    client = ZernioClient(api_key="dummy", webhook_secret=secret)
    assert client.verify_webhook(body, sig) is True


def test_verify_webhook_invalid():
    client = ZernioClient(api_key="dummy", webhook_secret="test-secret-123")
    assert client.verify_webhook(b"{}", "0" * 64) is False


def test_verify_webhook_no_secret_allows():
    client = ZernioClient(api_key="dummy", webhook_secret=None)
    # os env may or may not have the secret; force the skip path
    client.webhook_secret = None
    assert client.verify_webhook(b"{}", "anything") is True


# ── client construction ────────────────────────────────────────────────

def test_client_requires_key():
    env_backup = os.environ.pop("ZERNIO_API_KEY", None)
    try:
        try:
            ZernioClient(api_key=None)
            raise AssertionError("should have raised ValueError")
        except ValueError:
            pass
    finally:
        if env_backup is not None:
            os.environ["ZERNIO_API_KEY"] = env_backup


# ── reactions ──────────────────────────────────────────────────────────

def test_normalize_reaction():
    n = normalize_reaction_event({
        "platform": "whatsapp", "emoji": "👍",
        "messageId": "m1", "conversation_id": "c1",
        "sender": {"name": "Jane"},
    })
    assert n["event_type"] == "reaction.received"
    assert n["emoji"] == "👍"
    assert n["message_id"] == "m1"
    assert n["added"] is True
