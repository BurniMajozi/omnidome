"""Reporting boundaries, historical replay, malformed data and meter resets."""
import asyncio
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from fastapi import HTTPException
from sqlalchemy import select
from services.iot.tests.test_homedome import store
from services.iot.models import IoTHomeEntity, IoTHomeStatistic, IoTReportingRequest
from services.iot.routes import home_reports as api
from services.iot.households import now
from services.iot.home_reports import series_report, clean_statistic

def test_upgrade_is_idempotent_private_and_never_activates_a_plan(store, monkeypatch):
    scope, (owner, other, staff), (home, _) = store
    monkeypatch.setattr(api, "get_session", scope)
    async def check():
        assert (await api.reports(home, 30, owner))["series"] == []
        for ctx in [other, staff]:
            with pytest.raises(HTTPException):
                await api.request_upgrade(home, ctx)
            with pytest.raises(HTTPException):
                await api.reports(home, 30, ctx)
        await api.request_upgrade(home, owner)
        await api.request_upgrade(home, owner)
        async with scope() as session:
            assert len((await session.scalars(select(IoTReportingRequest))).all()) == 1
        report = await api.reports(home, 30, owner)
        assert report["plan"] == "included" and report["upgrade_status"] == "requested"
    asyncio.run(check())

def test_meter_reset_and_gap_do_not_create_fake_consumption():
    entity = SimpleNamespace(entity_id="sensor.energy", name="Energy", room=None, attributes={"state_class": "total_increasing", "unit_of_measurement": "kWh"})
    end = now()
    rows = [(end-timedelta(minutes=15), {"state": 100}), (end-timedelta(minutes=10), {"state": 103}),
        (end-timedelta(minutes=5), {"state": 0}), (end, {"state": 2})]
    result = series_report(entity, rows, "observations")
    assert result["total"] == 5 and result["skipped_samples"] == 2
    result = series_report(entity, [(end-timedelta(days=2), {"state": 1}), (end, {"state": 100})], "observations")
    assert result["total"] is None and not result["points"]
    assert clean_statistic({"mean": float("nan"), "state": True, "secret": "discard", "sum": 2}) == {"sum": 2}
    result = series_report(entity, [(end-timedelta(hours=1), {"change": 1e308}), (end, {"change": 1e308})], "recorder")
    assert result["total"] is None and not result["points"]

def test_import_replay_corrects_values_and_drops_foreign_series(store, monkeypatch):
    scope, (owner, *_), (home, _) = store
    monkeypatch.setattr(api, "get_session", scope)
    monkeypatch.setattr(api, "client_for", AsyncMock(return_value=SimpleNamespace(ha_url="https://home.example")))
    monkeypatch.setattr(api, "token_for_integration", lambda _: "server-only")
    stamp = now().replace(minute=0, second=0, microsecond=0)-timedelta(hours=1)
    socket = AsyncMock(spec=api.HAWebSocketClient)
    socket.request.return_value = {"sensor.temp": [{"start": stamp.timestamp()*1000, "mean": 21, "secret": "discard"}],
        "sensor.foreign": [{"start": stamp.timestamp()*1000, "mean": 99}]}
    monkeypatch.setattr(api, "HAWebSocketClient", lambda *args, **kwargs: socket)
    async def check():
        async with scope() as session:
            session.add(IoTHomeEntity(tenant_id=owner.tenant_id, home_id=home, entity_id="sensor.temp", name="Temperature", domain="sensor",
                state="21", attributes={"state_class": "measurement", "unit_of_measurement": "°C"}, observed_at=now()))
        assert (await api.import_history(home, owner))["samples"] == 1
        socket.request.return_value["sensor.temp"][0]["mean"] = 22
        await api.import_history(home, owner)
        async with scope() as session:
            rows = (await session.scalars(select(IoTHomeStatistic))).all()
            assert len(rows) == 1 and rows[0].values == {"mean": 22}
        assert (await api.reports(home, 30, owner))["series"][0]["average"] == 22
        assert socket.connect.await_count == 2 and socket.close.await_count == 2
    asyncio.run(check())

def test_request_queue_is_tenant_scoped_and_does_not_expose_readings(store, monkeypatch):
    scope, (owner, other, _), (home, _) = store
    monkeypatch.setattr(api, "get_session", scope)
    async def check():
        request = await api.request_upgrade(home, owner)
        rows = await api.requests(owner)  # Role gate is enforced by FastAPI dependency.
        assert len(rows) == 1 and "series" not in rows[0]
        identity = rows[0]["id"]
        import uuid
        foreign = SimpleNamespace(tenant_id=uuid.uuid4())
        assert await api.requests(foreign) == []
        with pytest.raises(HTTPException):
            await api.update_request(uuid.UUID(identity), api.RequestStatus(status="closed"), foreign)
        await api.update_request(uuid.UUID(identity), api.RequestStatus(status="closed"), owner)
        assert (await api.reports(home, 30, owner))["upgrade_status"] == "closed"
    asyncio.run(check())

def test_http_queue_rejects_customer_and_technician_roles(store, monkeypatch):
    import httpx
    from fastapi import FastAPI
    from services.common.auth import get_auth_context
    scope, (owner, _, staff), _ = store
    monkeypatch.setattr(api, "get_session", scope)
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[api.enabled] = lambda: None
    async def check():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            for ctx in [owner, staff]:
                app.dependency_overrides[get_auth_context] = lambda: ctx
                assert (await client.get("/reporting/requests")).status_code == 403
            owner.roles = ["org_admin"]
            app.dependency_overrides[get_auth_context] = lambda: owner
            assert (await client.get("/reporting/requests")).status_code == 200
    asyncio.run(check())

def test_application_registers_reporting_and_authenticated_viewer_routes():
    from services.iot.main import app
    from services.iot.access import require_tier
    paths = {route.path for route in app.routes}
    assert "/api/iot/homes/{home_id}/reports" in paths
    assert any(path.startswith("/api/iot/reference/") for path in paths)
    assert callable(require_tier("viewer"))
    with pytest.raises(ValueError):
        require_tier("unknown")

@pytest.mark.parametrize("enabled", [None, "false"])
def test_reference_refresh_defaults_on_and_is_cancelled_at_shutdown(monkeypatch, enabled):
    from contextlib import asynccontextmanager
    from services.iot import main, database, ha_reference_worker
    from services.common import event_bus
    monkeypatch.setenv("HOME_DOME_POLL_ENABLED", "false")
    if enabled is None:
        monkeypatch.delenv("HA_REFERENCE_REFRESH_ENABLED", raising=False)
    else:
        monkeypatch.setenv("HA_REFERENCE_REFRESH_ENABLED", enabled)
    monkeypatch.setattr(main.guard, "ensure_startup", lambda: None)
    monkeypatch.setattr(main, "run_with_db_retry", AsyncMock())
    monkeypatch.setattr(event_bus, "ensure_schema", AsyncMock())
    @asynccontextmanager
    async def fake_session():
        yield object()
    monkeypatch.setattr(database, "get_session", fake_session)
    async def check():
        started, stopped = asyncio.Event(), asyncio.Event()
        async def refresh():
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                stopped.set()
        monkeypatch.setattr(ha_reference_worker, "refresh_loop", refresh)
        async with main.lifespan(main.app):
            await asyncio.sleep(0)
            assert started.is_set() is (enabled is None)
        assert stopped.is_set() is (enabled is None)
    asyncio.run(check())
