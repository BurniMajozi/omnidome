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
    extract_event_meta,
    normalize_reaction_event,
    normalize_webhook_event,
)
from services.marketing.zernio_client import ZernioClient  # noqa: E402


def sample_event(**overrides):
    """Real Zernio message.received payload shape (Sep 2026)."""
    evt = {
        "id": "8dafe19b-24b2-4b75-a862-93d9127c882e",
        "event": "message.received",
        "message": {
            "id": "6aa5920dc7f9323ddc0ea8c2",
            "conversationId": "conv_abc",
            "platform": "telegram",
            "platformMessageId": "25393",
            "direction": "incoming",
            "text": "Hello, I need help",
            "attachments": [],
            "sender": {"id": "8975916657", "name": "John Doe", "handle": "johndoe", "contactId": "contact_123"},
            "sentAt": "2026-09-12T17:55:24.000Z",
            "isRead": False,
            "sentVia": None
        },
        "conversation": {
            "id": "6aa57f8a726ebfe037e0851e",
            "platformConversationId": "-5286740183",
            "participantId": "8975916657",
            "participantName": "John Doe",
            "status": "active",
            "contactId": "contact_123"
        },
        "account": {
            "id": "6a281f5f2b2567671a469f50",
            "platform": "telegram",
            "username": "OmniDome",
            "displayName": "OmniDome",
            "profileId": "6a281d3beb3b0bd452f03cc4",
            "accountId": "6a281f5f2b2567671a469f50"
        },
        "timestamp": "2026-09-12T17:55:25.157Z"
    }
    # Allow nested overrides for message fields
    if overrides:
        if "message" in overrides:
            evt["message"].update(overrides.pop("message"))
        evt.update(overrides)
    return evt


# ── normalization ──────────────────────────────────────────────────────

def test_normalize_dm():
    n = normalize_webhook_event(sample_event())
    assert n["message_type"] == "DM"
    assert n["platform"] == "telegram"
    assert n["external_id"] == "6aa5920dc7f9323ddc0ea8c2"
    assert n["sender_name"] == "John Doe"
    assert n["status"] == "UNREAD"
    assert n["conversation_id"] == "conv_abc"


def test_normalize_comment_and_mention():
    assert normalize_webhook_event(sample_event(event="comment.received"))["message_type"] == "COMMENT"
    assert normalize_webhook_event(sample_event(event="mention.received"))["message_type"] == "MENTION"


def test_normalize_platform_alias():
    n = normalize_webhook_event(sample_event(message={"platform": "x"}))
    assert n["platform"] == "twitter"


def test_normalize_missing_sender():
    n = normalize_webhook_event(sample_event(message={"sender": {}}))
    assert n["sender_name"] == "Unknown"


def test_normalize_text_fallback_and_thread():
    n = normalize_webhook_event(sample_event(message={"text": "hi", "platform": "whatsapp"}))
    assert n["content"] == "hi"
    assert n["parent_id"] is None  # parent_id not in real payload, defaults to None


# ── event meta (route + normalizer share this) ─────────────────────────

def test_extract_event_meta_real_shape():
    # Real payload: event at top level, platform nested under message.
    assert extract_event_meta(sample_event()) == ("message.received", "telegram")


def test_extract_event_meta_reaction():
    # The route branches on this — must see the top-level "event" key.
    evt = sample_event(event="reaction.received", message={"platform": "whatsapp"})
    assert extract_event_meta(evt) == ("reaction.received", "whatsapp")


def test_extract_event_meta_legacy_and_missing():
    # Legacy flat shape still works; junk degrades to ("unknown", "unknown").
    assert extract_event_meta({"event_type": "message.received", "platform": "x"}) == (
        "message.received", "x",
    )
    assert extract_event_meta({}) == ("unknown", "unknown")
    # A non-dict "message" must not raise (defensive: some events send a string).
    assert extract_event_meta({"event": "ping", "message": "not-a-dict"}) == ("ping", "unknown")


# ── sentiment ──────────────────────────────────────────────────────────

def test_sentiment_positive():
    assert _detect_sentiment("Thanks, that was awesome!") == "POSITIVE"


def test_sentiment_negative():
    assert _detect_sentiment("This is broken, I want a refund") == "NEGATIVE"


def test_sentiment_neutral_and_empty():
    assert _detect_sentiment("What are your hours?") == "NEUTRAL"
    assert _detect_sentiment("") == "NEUTRAL"


def test_sentiment_attached_to_normalized():
    n = normalize_webhook_event(sample_event(message={"text": "Terrible service, very angry"}))
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


# ── spec-verified endpoint paths ───────────────────────────────────────
# Every path below was cross-checked against https://zernio.com/openapi.json
# (484 paths). These tests pin the client to the real API so imagined
# endpoints (e.g. /messages/list-inbox-conversations) can never regress.

class _RecordingClient(ZernioClient):
    """Capture (method, path, params, json) instead of hitting the network."""

    def __init__(self):
        super().__init__(api_key="dummy", webhook_secret="dummy")
        self.calls = []

    async def _request(self, method, path, params=None, json_data=None):
        self.calls.append({
            "method": method, "path": path,
            "params": params or {}, "json": json_data or {},
        })
        return {"data": []}


def test_spec_list_conversations_path():
    import asyncio
    c = _RecordingClient()
    asyncio.new_event_loop().run_until_complete(
        c.list_conversations(platform="telegram", limit=3, account_id="acc1")
    )
    call = c.calls[0]
    assert call["method"] == "GET"
    assert call["path"] == "/inbox/conversations"
    assert call["params"]["platform"] == "telegram"
    assert call["params"]["limit"] == 3
    assert call["params"]["accountId"] == "acc1"


def test_spec_get_conversation_path():
    import asyncio
    c = _RecordingClient()
    asyncio.new_event_loop().run_until_complete(
        c.get_conversation("conv1", account_id="acc1")
    )
    call = c.calls[0]
    assert call["path"] == "/inbox/conversations/conv1"
    assert call["params"]["accountId"] == "acc1"


def test_spec_fetch_messages_path():
    import asyncio
    c = _RecordingClient()
    asyncio.new_event_loop().run_until_complete(
        c.fetch_messages("conv1", account_id="acc1", limit=10)
    )
    call = c.calls[0]
    assert call["path"] == "/inbox/conversations/conv1/messages"
    assert call["params"]["accountId"] == "acc1"
    assert "direction" not in call["params"]  # spec uses sortOrder, not direction


def test_spec_send_message_path_and_body():
    import asyncio
    c = _RecordingClient()
    asyncio.new_event_loop().run_until_complete(
        c.send_message("conv1", "hello", account_id="acc1")
    )
    call = c.calls[0]
    assert call["method"] == "POST"
    assert call["path"] == "/inbox/conversations/conv1/messages"
    assert call["json"]["message"] == "hello"
    assert call["json"]["accountId"] == "acc1"
    assert "attachmentType" not in call["json"]  # not in spec schema


def test_spec_get_account_uses_list():
    import asyncio
    c = _RecordingClient()
    c.calls.clear()
    # stub list response by patching _request once
    async def fake_list(method, path, params=None, json_data=None):
        c.calls.append({"method": method, "path": path})
        return [{"_id": "a1", "platform": "telegram"}]
    c._request = fake_list
    result = asyncio.new_event_loop().run_until_complete(c.get_account("a1"))
    assert result["_id"] == "a1"
    assert all(call["path"] == "/accounts" for call in c.calls)  # no GET /accounts/{id}


def test_spec_connect_url_needs_profile():
    import asyncio
    c = _RecordingClient()
    env_backup = os.environ.pop("ZERNIO_PROFILE_ID", None)
    try:
        url = asyncio.new_event_loop().run_until_complete(c.get_connect_url("telegram"))
        assert url == ""  # graceful skip without profile id, no network call
        assert c.calls == []
    finally:
        if env_backup is not None:
            os.environ["ZERNIO_PROFILE_ID"] = env_backup
