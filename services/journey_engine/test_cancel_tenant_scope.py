import asyncio
import uuid
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from services.journey_engine.main import trigger_cancel, respond_to_offer, CancelTrigger, CancelRespond

def test_snapshot_cannot_select_another_tenant():
    auth = SimpleNamespace(tenant_id=uuid.uuid4())
    data = CancelTrigger(customer_id=str(uuid.uuid4()), account_number="TEST", customer_snapshot={"tenant_id": str(uuid.uuid4())})
    with pytest.raises(HTTPException) as exc:
        asyncio.run(trigger_cancel(data, session=None, auth=auth))
    assert exc.value.status_code == 403

def test_respond_query_is_scoped_to_verified_tenant():
    auth = SimpleNamespace(tenant_id=uuid.uuid4())
    class Session:
        async def execute(self, query):
            compiled = query.compile(compile_kwargs={"literal_binds": True})
            assert "cancel_events.tenant_id" in str(compiled)
            assert auth.tenant_id.hex in str(compiled).replace("-", "")
            return SimpleNamespace(scalar_one_or_none=lambda: None)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(respond_to_offer(CancelRespond(cancel_event_id=str(uuid.uuid4()), decision="accept"), session=Session(), auth=auth))
    assert exc.value.status_code == 404
