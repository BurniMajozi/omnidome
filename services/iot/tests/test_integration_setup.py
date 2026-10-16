"""Guided integration setup drives HA's config flow: owner-only, allow-listed, sanitised, secrets never echoed."""
import asyncio
from unittest.mock import AsyncMock
import pytest
from fastapi import HTTPException
from services.iot.tests.test_homedome import store
from services.iot.routes import integration_setup as api

FLOW = "a1b2c3d4e5f60718293a4b5c6d7e8f90"


def test_ha_form_is_reduced_to_safe_fields_with_region_options():
    step = api.public_step({"type": "form", "flow_id": FLOW, "step_id": "user", "secret_debug": "x",
        "data_schema": [{"name": "app_id", "type": "string", "required": True},
            {"name": "app_secret", "type": "string", "required": True},
            {"name": "region", "selector": {"select": {"options": ["sg", {"value": "eu", "label": "Europe"}]}}}],
        "errors": {"base": "invalid_auth"}})
    assert "secret_debug" not in step
    assert [f["name"] for f in step["fields"]] == ["app_id", "app_secret", "region"]
    assert step["fields"][2]["options"] == [{"value": "sg", "label": "sg"}, {"value": "eu", "label": "Europe"}]
    assert step["errors"] == {"base": "invalid_auth"}


def test_only_guided_integrations_can_start_and_only_the_owner(store, monkeypatch):
    scope, (owner, other, staff), (home, _) = store
    monkeypatch.setattr(api, "get_session", scope)
    client = AsyncMock()
    client.config_flow.return_value = {"type": "form", "flow_id": FLOW, "step_id": "user", "data_schema": []}
    monkeypatch.setattr(api, "client_for", AsyncMock(return_value=client))

    async def check():
        with pytest.raises(HTTPException) as unsupported:
            await api.start_setup(home, "alexa", owner)
        assert unsupported.value.status_code == 404
        for ctx in [other, staff]:
            with pytest.raises(HTTPException):
                await api.start_setup(home, "imou", ctx)
        client.config_flow.assert_not_awaited()
        step = await api.start_setup(home, "imou", owner)
        assert step["flow_id"] == FLOW
        client.config_flow.assert_awaited_once_with("POST", body={"handler": "imou", "show_advanced_options": False})
    asyncio.run(check())


def test_credentials_are_forwarded_but_never_returned_and_bad_flow_ids_are_rejected(store, monkeypatch):
    scope, (owner, *_), (home, _) = store
    monkeypatch.setattr(api, "get_session", scope)
    client = AsyncMock()
    client.config_flow.return_value = {"type": "form", "flow_id": FLOW, "step_id": "user", "errors": {"base": "invalid_auth"}, "data_schema": []}
    monkeypatch.setattr(api, "client_for", AsyncMock(return_value=client))

    async def check():
        with pytest.raises(HTTPException) as bad:
            await api.continue_setup(home, "../../etc", api.FlowInput(user_input={}), owner)
        assert bad.value.status_code == 422
        body = api.FlowInput(user_input={"app_id": "id", "app_secret": "s3cret-value", "region": "eu"})
        step = await api.continue_setup(home, FLOW, body, owner)
        assert "s3cret-value" not in str(step)
        client.config_flow.assert_awaited_with("POST", FLOW, {"app_id": "id", "app_secret": "s3cret-value", "region": "eu"})
    asyncio.run(check())


def test_ptz_requires_a_camera_movement_button(store, monkeypatch):
    scope, (owner, *_), (home, _) = store
    monkeypatch.setattr(api, "get_session", scope)
    from services.iot.models import IoTHomeEntity
    from services.iot import households
    client = AsyncMock()
    monkeypatch.setattr(api, "client_for", AsyncMock(return_value=client))

    async def check():
        async with scope() as session:
            good = IoTHomeEntity(tenant_id=owner.tenant_id, home_id=home, entity_id="button.porch_ptz_left", name="Porch PTZ left", domain="button", state="unknown", attributes={}, observed_at=households.now())
            bad = IoTHomeEntity(tenant_id=owner.tenant_id, home_id=home, entity_id="button.porch_restart", name="Porch restart", domain="button", state="unknown", attributes={}, observed_at=households.now())
            session.add_all([good, bad]); await session.flush()
            good_id, bad_id = good.id, bad.id
        result = await api.move_camera(home, good_id, api.Ptz(direction="left"), owner)
        assert result["ok"] is True
        client.call_service.assert_awaited_with("button", "press", target={"entity_id": "button.porch_ptz_left"})
        for entity, direction in [(bad_id, "left"), (good_id, "right")]:
            with pytest.raises(HTTPException) as error:
                await api.move_camera(home, entity, api.Ptz(direction=direction), owner)
            assert error.value.status_code == 422
    asyncio.run(check())


def test_activation_never_needs_home_assistant_ui_and_stores_no_password(monkeypatch):
    from services.iot import gateway_activation as gw
    monkeypatch.setattr(gw, "gateway_state", AsyncMock(return_value="needs_credentials"))
    with pytest.raises(gw.NeedsCredentials):
        asyncio.run(gw.activate("Home"))
    monkeypatch.setattr(gw, "gateway_state", AsyncMock(return_value="unavailable"))
    with pytest.raises(gw.GatewayUnavailable):
        asyncio.run(gw.activate("Home"))


def test_customers_are_never_given_a_home_assistant_address(store):
    scope, (owner, *_), (home, _) = store
    from services.iot.households import public_home
    from services.iot.models import IoTHome

    async def check():
        async with scope() as session:
            row = await session.get(IoTHome, home)
            row.managed_gateway_key, row.ha_url = "local", "http://localhost:8123"
            assert public_home(row, owner)["dashboard_url"] is None
    asyncio.run(check())
