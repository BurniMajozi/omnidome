"""Household isolation, consent lifecycle and measured energy regressions."""
import asyncio
import sys
import uuid
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from services.common.auth import AuthContext
from services.iot import households
from services.iot.models import Base, IoTHome, IoTHomeEntity, IoTHomeReading, IoTHomeSupport, IoTHomeAudit, IoTGatewayBinding, CustomerPortalAccount, IoTHomeRoom, IoTHomeRoomAssignment
from services.iot.routes import homes
from services.iot.home_energy import counter_total
from services.iot.integration_catalog import catalogue
from services.iot.models import IoTHomeStatistic, IoTReportingRequest


@compiles(JSONB, "sqlite")
def json_sqlite(element, compiler, **kwargs):
    return "JSON"


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def store(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async def setup():
        async with engine.begin() as connection:
            await connection.run_sync(lambda db: Base.metadata.create_all(db, tables=[
                model.__table__ for model in [IoTHome, IoTHomeEntity, IoTHomeReading, IoTHomeSupport, IoTHomeAudit, IoTGatewayBinding, CustomerPortalAccount, IoTHomeRoom, IoTHomeRoomAssignment, IoTHomeStatistic, IoTReportingRequest]]))
    run(setup())
    factory = async_sessionmaker(engine, expire_on_commit=False)
    @asynccontextmanager
    async def session_scope():
        async with factory() as session:
            async with session.begin():
                yield session
    monkeypatch.setattr(homes, "get_session", session_scope)
    monkeypatch.setattr(households, "effective_access", AsyncMock(side_effect=lambda ctx: (set(ctx.roles), set(ctx.permissions))))
    monkeypatch.setattr(households, "rooms_for", AsyncMock(return_value={}))
    monkeypatch.setattr(households, "emit", AsyncMock())
    monkeypatch.setattr(homes, "emit", AsyncMock())
    monkeypatch.setattr(homes, "support_notice", AsyncMock())
    tenant, owner, other, staff = [uuid.uuid4() for _ in range(4)]
    contexts = [AuthContext(user_id=user, tenant_id=tenant, roles=["customer"] if user != staff else ["technician"], rbac_loaded=True)
                for user in [owner, other, staff]]
    async def seed():
        async with session_scope() as session:
            home = IoTHome(tenant_id=tenant, customer_id=uuid.uuid4(), owner_user_id=owner, name="Home A")
            second = IoTHome(tenant_id=tenant, customer_id=uuid.uuid4(), owner_user_id=other, name="Home B")
            session.add_all([home, second]); await session.flush()
            return home.id, second.id
    identities = run(seed())
    yield session_scope, contexts, identities
    run(engine.dispose())


def test_customer_cannot_read_other_home_and_cross_tenant_is_hidden(store):
    scope, (owner, other, staff), (home, second) = store
    async def check():
        assert [row["id"] for row in await homes.homes(owner)] == [str(home)]
        for ctx in [other, AuthContext(user_id=owner.user_id, tenant_id=uuid.uuid4(), roles=["owner"])]:
            with pytest.raises(HTTPException) as error:
                await homes.devices(home, ctx)
            assert error.value.status_code == 404
    run(check())


def test_managed_gateway_requires_platform_owner_and_one_home(store, monkeypatch):
    scope, (owner, other, staff), (home, second) = store
    monkeypatch.setenv("HOME_DOME_LOCAL_GATEWAY_ENABLED", "true")
    from services.iot import access
    monkeypatch.setattr(access, "effective_access", households.effective_access)
    async def check():
        with pytest.raises(HTTPException) as error:
            await homes.assign_gateway(home, owner)
        assert error.value.status_code == 403
        admin = AuthContext(user_id=staff.user_id, tenant_id=staff.tenant_id,
            roles=["platform_admin"], is_platform_admin=True, rbac_loaded=True)
        assert (await homes.assign_gateway(home, admin))["ok"]
        assert (await homes.assign_gateway(home, admin))["ok"]
        with pytest.raises(HTTPException) as error:
            await homes.assign_gateway(second, admin)
        assert error.value.status_code == 409
        with pytest.raises(HTTPException) as error:
            await homes.connect(home, homes.Connection(ha_url="http://other-service:8000", ha_token="never-a-real-token"), owner)
        assert error.value.status_code == 422
    run(check())


def test_managed_transport_rejects_unapproved_target_and_disabled_gateway(monkeypatch):
    from services.iot.managed_gateway import check_target, INTERNAL_URL
    monkeypatch.setenv("HOME_DOME_LOCAL_GATEWAY_ENABLED", "true")
    check_target(INTERNAL_URL)
    for target in ["http://db:5432", "http://127.0.0.1:8123", INTERNAL_URL + "/api"]:
        with pytest.raises(ValueError):
            check_target(target)
    monkeypatch.setenv("HOME_DOME_LOCAL_GATEWAY_ENABLED", "false")
    with pytest.raises(ValueError):
        check_target(INTERNAL_URL)


def test_portal_account_does_not_need_a_home_and_stays_customer_scoped(store):
    scope, (owner, other, staff), (home, second) = store
    customer_id = uuid.uuid4()
    async def check():
        async with scope() as session:
            # Staff has no home: access is supplied by an explicit customer association.
            await households.bind_customer_account(session, owner, staff.user_id, customer_id)
            assert await households.account_customer_for(session, staff) == customer_id
            with pytest.raises(HTTPException) as error:
                await households.account_customer_for(session, AuthContext(user_id=staff.user_id,
                    tenant_id=uuid.uuid4(), roles=["customer"], rbac_loaded=True))
            assert error.value.status_code == 404
            with pytest.raises(HTTPException) as error:
                await households.bind_customer_account(session, owner, staff.user_id, uuid.uuid4())
            assert error.value.status_code == 409
            assert await households.account_customer_for(session, owner) != customer_id
    run(check())


def test_customer_cannot_link_portal_accounts_even_when_legacy_role_gate_is_disabled(store, monkeypatch):
    scope, (owner, other, staff), (home, second) = store
    from services.iot import access
    monkeypatch.setattr(access, "effective_access", households.effective_access)
    monkeypatch.setenv("IOT_ENFORCE_ROLES", "false")
    with pytest.raises(HTTPException) as error:
        run(homes.link_portal_account(homes.PortalAccount(customer_id=uuid.uuid4(), owner_user_id=owner.user_id), owner))
    assert error.value.status_code == 403


def test_staff_and_platform_owner_need_customer_approval(store):
    scope, (owner, other, staff), (home, second) = store
    async def check():
        for ctx in [staff, AuthContext(user_id=staff.user_id, tenant_id=staff.tenant_id, roles=["owner"], is_platform_admin=True)]:
            with pytest.raises(HTTPException) as error:
                await homes.devices(home, ctx)
            assert error.value.status_code == 403
    run(check())


def test_grant_lifecycle_scope_expiry_revocation_and_wrong_approver(store):
    scope, (owner, other, staff), (home, second) = store
    async def check():
        request = await homes.request_support(home, homes.SupportRequest(reference="ticket-17", reason="Inspect offline camera", scopes=["diagnostics", "camera"]), staff)
        request_id = uuid.UUID(request["id"])
        with pytest.raises(HTTPException):
            await homes.approve(home, request_id, homes.Approval(scopes=["diagnostics"]), staff)
        with pytest.raises(HTTPException):
            await homes.approve(home, request_id, homes.Approval(scopes=["diagnostics", "control"]), owner)
        await homes.approve(home, request_id, homes.Approval(scopes=["diagnostics"]), owner)
        assert await homes.devices(home, staff) == []
        async with scope() as session:
            with pytest.raises(HTTPException):
                await households.home_for(session, staff, home, "camera")
            row = await session.get(IoTHomeSupport, request_id)
            row.expires_at = households.now() - timedelta(seconds=1)
        with pytest.raises(HTTPException):
            await homes.devices(home, staff)
        async with scope() as session:
            row = await session.get(IoTHomeSupport, request_id)
            row.expires_at = households.now() + timedelta(minutes=30)
        await homes.revoke(home, request_id, owner)
        with pytest.raises(HTTPException):
            await homes.devices(home, staff)
    run(check())


def test_device_commands_cannot_retarget_or_cross_home(store, monkeypatch):
    scope, (owner, other, staff), (home, second) = store
    client = SimpleNamespace(call_service=AsyncMock(), aclose=AsyncMock())
    monkeypatch.setattr(homes, "client_for", AsyncMock(return_value=client))
    async def check():
        async with scope() as session:
            entity = IoTHomeEntity(tenant_id=owner.tenant_id, home_id=home, entity_id="light.kitchen", name="Kitchen", domain="light", state="off", attributes={}, observed_at=households.now())
            session.add(entity); await session.flush(); identity = entity.id
        for payload in [homes.Command(service="turn_on", service_data={"entity_id": "lock.front_door"})]:
            with pytest.raises(HTTPException):
                await homes.control(home, identity, payload, owner)
        with pytest.raises(HTTPException):
            await homes.control(second, identity, homes.Command(service="turn_on"), other)
        await homes.control(home, identity, homes.Command(service="turn_on"), owner)
        assert client.call_service.await_args.kwargs["target"] == {"entity_id": "light.kitchen"}
        assert client.call_service.await_count == 1
    run(check())


def test_sync_namespaces_duplicate_entities_and_filters_secrets(store, monkeypatch):
    scope, (owner, other, staff), (home, second) = store
    client = SimpleNamespace(get_states=AsyncMock(return_value=[{"entity_id":"sensor.energy", "state":"10", "attributes":{
        "friendly_name":"Meter", "unit_of_measurement":"kWh", "access_token":"NEVER RETURN", "entity_picture":"/api/camera_proxy?token=SECRET"}}]),
        get_config=AsyncMock(return_value={"components":["imou", "mqtt", "sensor"]}), aclose=AsyncMock())
    monkeypatch.setattr(households, "client_for", AsyncMock(return_value=client))
    async def check():
        for identity, ctx in [(home, owner), (second, other)]:
            assert (await homes.sync(identity, ctx))["ok"]
            rows = await homes.devices(identity, ctx)
            assert len(rows) == 1 and rows[0]["attributes"] == {"unit_of_measurement":"kWh"}
        async with scope() as session:
            assert len((await session.scalars(select(IoTHomeEntity))).all()) == 2
            assert len((await session.scalars(select(IoTHomeReading))).all()) == 2
    run(check())


def test_camera_scope_is_separate_and_invalid_images_are_rejected(store, monkeypatch):
    scope, (owner, other, staff), (home, second) = store
    client = SimpleNamespace(get_camera_image=AsyncMock(return_value=b"<html>bad response</html>"), aclose=AsyncMock())
    monkeypatch.setattr(homes, "client_for", AsyncMock(return_value=client))
    async def check():
        async with scope() as session:
            entity = IoTHomeEntity(tenant_id=owner.tenant_id, home_id=home, entity_id="camera.entry", name="Entry", domain="camera", state="idle", attributes={}, observed_at=households.now())
            session.add(entity); await session.flush(); identity = entity.id
        with pytest.raises(HTTPException) as error:
            await homes.snapshot(home, identity, owner)
        assert error.value.status_code == 502
        client.get_camera_image.return_value = b"\xff\xd8\xffimage"
        response = await homes.snapshot(home, identity, owner)
        assert response.headers["cache-control"] == "no-store, private"
        with pytest.raises(HTTPException):
            await homes.snapshot(home, identity, staff)
    run(check())


@pytest.mark.parametrize("states,expected", [(["100", "102"], 2), (["100"], None), (["100", "0", "3"], None), (["unavailable", "unknown"], None)])
def test_energy_totals_require_measured_counter_history(states, expected):
    result = counter_total("grid_import", [SimpleNamespace(state=value, unit="kWh") for value in states])
    assert result["value"] == expected


def test_all_featured_integrations_and_imou_are_available_but_not_falsely_connected():
    rows = catalogue(["imou", "mqtt.sensor"])
    assert len(rows) == 21
    assert {row["id"] for row in rows if row["status"] == "loaded"} == {"imou", "mqtt"}
    assert len({row["id"] for row in rows}) == 21


def test_support_scopes_and_duration_are_validated():
    for payload in [{"scopes":["camera"]}, {"scopes":["diagnostics"], "minutes":61}, {"scopes":["administrator"]}]:
        with pytest.raises(ValidationError):
            homes.Approval(**payload)
