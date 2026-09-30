"""Inbound mail -> channel Message construction uses only real Message columns (no DB).
Run with cwd = services/communication:  python -m pytest tests -q
"""
import os
import sys
import uuid
from types import SimpleNamespace

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, REPO_ROOT)

from services.communication.models import Message  # noqa: E402
from services.communication.routes.mail import build_inbound_channel_message  # noqa: E402


def _args(body="hello"):
    mailbox = SimpleNamespace(id=uuid.uuid4(), inbound_channel_id=uuid.uuid4(), display_name="Support")
    payload = SimpleNamespace(sender="a@b.co", subject="Hi", body_text=body)
    return mailbox, payload


def test_builds_message_with_real_columns_and_tenant():
    mailbox, payload = _args()
    tenant = uuid.uuid4()
    m = build_inbound_channel_message(tenant, None, mailbox, payload)
    assert isinstance(m, Message)
    assert m.tenant_id == tenant
    assert m.channel_id == mailbox.inbound_channel_id
    assert m.user_id == mailbox.id  # falls back to the mailbox when no user
    assert "a@b.co" in m.content and "Hi" in m.content


def test_uses_user_id_and_truncates_long_body():
    mailbox, payload = _args("x" * 500)
    user = uuid.uuid4()
    m = build_inbound_channel_message(uuid.uuid4(), user, mailbox, payload)
    assert m.user_id == user
    assert m.content.endswith("...") and "x" * 301 not in m.content


def test_short_body_has_no_ellipsis():
    mailbox, payload = _args("short")
    assert not build_inbound_channel_message(uuid.uuid4(), None, mailbox, payload).content.endswith("...")
