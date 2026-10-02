"""Invitation codes are email-only credentials; the link never contains the code."""
import asyncio
import uuid

from services.admin import iam, supabase_sync


def test_code_hash_is_bound_to_invite_and_email(monkeypatch):
    monkeypatch.setenv("INVITE_CODE_SECRET", "test-secret")
    invite_id = uuid.uuid4()
    digest = iam.invite_code_hash(invite_id, "Person@Example.test", "12345678")
    assert digest == iam.invite_code_hash(invite_id, "person@example.test", "12345678")
    assert digest != iam.invite_code_hash(uuid.uuid4(), "person@example.test", "12345678")
    assert digest != iam.invite_code_hash(invite_id, "other@example.test", "12345678")
    assert digest != iam.invite_code_hash(invite_id, "person@example.test", "87654321")


def test_agentmail_delivery_contains_code_but_response_does_not(monkeypatch):
    seen = []

    async def send(to, subject, html):
        seen.append((to, subject, html))
        return "message-id"

    monkeypatch.setattr(iam.agentmail, "send_email", send)
    monkeypatch.setenv("APP_PUBLIC_URL", "https://example.test")
    invite_id = uuid.uuid4()
    result = asyncio.run(iam.deliver_invite(invite_id, "person@example.test", "12345678", True))
    assert result["email_requested"] is True
    assert "12345678" in seen[0][2]
    assert seen[0][0] == "person@example.test"
    assert result["accept_link"] == f"https://example.test/auth/claim?invite={invite_id}"
    assert "12345678" not in str(result)


def test_supabase_create_is_confirmed_and_does_not_invoke_invite(monkeypatch):
    sent = []

    async def request(method, path, **kw):
        sent.append((method, path, kw))
        return {"id": str(uuid.uuid4())}

    admin = supabase_sync.SupabaseAdmin("https://example.test", "test-key")
    monkeypatch.setattr(admin, "_req", request)
    asyncio.run(admin.create_confirmed_user("person@example.test", "long-password-123"))
    assert sent == [("POST", "/admin/users", {"json": {"email": "person@example.test", "password": "long-password-123", "email_confirm": True}})]
