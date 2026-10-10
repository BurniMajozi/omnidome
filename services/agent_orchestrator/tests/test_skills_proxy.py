"""Skills proxy routes: identity forwarding, error relay, live tool registry in the picker."""
import asyncio
import os
import sys
import uuid

import httpx
import pytest
from fastapi import HTTPException

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, REPO_ROOT)

from services.agent_orchestrator.routes import skills as proxy  # noqa: E402
from services.common.auth import AuthContext  # noqa: E402


def ctx(roles=("analyst",), permissions=()):
    return AuthContext(user_id=uuid.uuid4(), tenant_id=uuid.uuid4(), roles=list(roles), permissions=list(permissions))


REAL_CLIENT = httpx.AsyncClient


def mock_memory(monkeypatch, handler):
    real = REAL_CLIENT
    monkeypatch.setattr(proxy.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))


def test_identity_and_path_are_forwarded(monkeypatch):
    seen = {}

    def handle(request):
        seen.update(path=request.url.path, roles=request.headers.get("x-roles"), tenant=request.headers.get("x-tenant-id"))
        return httpx.Response(200, json={"ok": True})
    mock_memory(monkeypatch, handle)
    c = ctx(permissions=["agents.manage"])
    asyncio.run(proxy.share_skill(uuid.UUID(int=5), c))
    assert seen["path"] == f"/api/v1/skills/{uuid.UUID(int=5)}/share" and seen["tenant"] == str(c.tenant_id)
    assert "analyst" in seen["roles"] and "tenant_admin" in seen["roles"]       # agents.manage counts as admin downstream


def test_memory_errors_reach_the_panel_with_their_message(monkeypatch):
    mock_memory(monkeypatch, lambda r: httpx.Response(422, json={"detail": [{"loc": ["tools_required"], "msg": "unknown tool 'x'"}]}))
    with pytest.raises(HTTPException) as e:
        asyncio.run(proxy.import_preview(_Req({"markdown": "x"}), ctx()))
    assert e.value.status_code == 422 and "unknown tool" in str(e.value.detail)
    mock_memory(monkeypatch, lambda r: httpx.Response(403, json={"detail": "Only admins"}))
    with pytest.raises(HTTPException) as e:
        asyncio.run(proxy.activate_skill(uuid.UUID(int=1), ctx()))
    assert (e.value.status_code, e.value.detail) == (403, "Only admins")


def test_service_outage_is_503_not_empty(monkeypatch):
    def boom(request):
        raise httpx.ConnectError("down")
    mock_memory(monkeypatch, boom)
    with pytest.raises(HTTPException) as e:
        asyncio.run(proxy.get_skill(uuid.UUID(int=1), ctx()))
    assert e.value.status_code == 503


def test_meta_lists_the_live_registry_with_policies(monkeypatch):
    mock_memory(monkeypatch, lambda r: httpx.Response(200, json={"tools": [{"name": "stale_tool", "soft": False}], "caller": {"admin": True, "author": True}}))
    meta = asyncio.run(proxy.skills_meta(ctx()))
    names = {t["name"]: t for t in meta["tools"]}
    assert meta["tools_source"] == "registry" and "stale_tool" not in names
    assert names["support_create_ticket"]["requires_approval"] is True and names["support_get_tickets"]["mutates"] is False
    assert "skills.find" in names and "skills.get" in names


class _Req:
    def __init__(self, data):
        self._d = data

    async def json(self):
        return self._d
