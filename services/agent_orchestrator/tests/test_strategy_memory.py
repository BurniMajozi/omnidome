import asyncio
import uuid

import pytest
from fastapi import HTTPException

from services.agent_orchestrator.routes import memory
from services.common.auth import AuthContext


def _ctx(role):
    return AuthContext(user_id=uuid.uuid4(), tenant_id=uuid.uuid4(), roles=[role])


def test_strategy_write_requires_agent_admin(monkeypatch):
    with pytest.raises(HTTPException) as error:
        asyncio.run(memory.create_strategy_entry(
            memory.StrategyEntryRequest(title="Sales policy", content="Use approved sales targets only."),
            _ctx("org_user"),
        ))
    assert error.value.status_code == 403


def test_strategy_write_is_tenant_scoped_and_explicit(monkeypatch):
    seen = {}

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"id": "saved"}

    class Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, url, *, headers, json):
            seen.update(url=url, headers=headers, body=json)
            return Response()

    monkeypatch.setattr(memory.httpx, "AsyncClient", Client)
    ctx = _ctx("org_admin")
    result = asyncio.run(memory.create_strategy_entry(
        memory.StrategyEntryRequest(title="Sales policy", content="Use approved sales targets only.",
                                    agent_type="custom_sales"), ctx,
    ))
    assert result == {"id": "saved"}
    assert seen["headers"]["X-Tenant-Id"] == str(ctx.tenant_id)
    assert seen["body"]["source_type"] == "operator_strategy"
    assert seen["body"]["scope_key"] == "agent:custom_sales"
    assert seen["body"]["metadata"]["approved_by"] == str(ctx.user_id)
