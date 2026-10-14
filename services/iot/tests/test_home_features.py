"""Fresh flow and private customer feature regressions."""
import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from services.iot.tests.test_homedome import store
from services.iot.home_energy import measured_flows
from services.iot.home_energy import energy_report
from services.iot.models import IoTHome, IoTHomeEntity, IoTHomeReading
from services.iot.routes import home_features as feature

def test_flow_requires_fresh_available_readings_and_stops_on_offline():
    now = datetime.now(timezone.utc)
    state = SimpleNamespace(entity_id="sensor.grid", state="10", observed_at=now)
    row = SimpleNamespace(entity_id="sensor.grid", state="500", unit="W", observed_at=now)
    config = {"grid_power": "sensor.grid"}
    assert measured_flows(config, [row], [state], now)["grid_import"]
    row.state = "-500"
    assert measured_flows(config, [row], [state], now)["grid_export"]
    state.state = "unavailable"
    assert not any(measured_flows(config, [row], [state], now).values())
    state.state = "10"; row.observed_at = now - timedelta(minutes=4)
    assert not any(measured_flows(config, [row], [state], now).values())

def test_battery_direction_uses_real_counter_delta_not_assumed_signed_power():
    now = datetime.now(timezone.utc)
    config = {"battery_charge": "sensor.charge"}
    state = SimpleNamespace(entity_id="sensor.charge", state="10", observed_at=now)
    readings = [SimpleNamespace(entity_id="sensor.charge", state=value, unit="kWh", observed_at=now - timedelta(seconds=seconds)) for value, seconds in [("9", 60), ("10", 0)]]
    assert measured_flows(config, readings, [state], now)["battery_charge"]
    readings[-1].state = "0"
    assert not measured_flows(config, readings, [state], now)["battery_charge"]

def test_offline_gateway_stops_animation_even_when_last_reading_is_fresh(store):
    scope, (owner, *_), (identity, _) = store
    now = datetime.now(timezone.utc)
    async def check():
        async with scope() as session:
            home = await session.get(IoTHome, identity)
            home.energy_config = {"grid_power": "sensor.grid"}
            home.status = "connected"
            session.add(IoTHomeEntity(tenant_id=owner.tenant_id, home_id=identity, entity_id="sensor.grid", domain="sensor", name="Grid", state="500", attributes={"unit_of_measurement": "W"}, observed_at=now))
            session.add(IoTHomeReading(tenant_id=owner.tenant_id, home_id=identity, entity_id="sensor.grid", state="500", unit="W", observed_at=now))
            await session.flush()
            assert (await energy_report(session, home, now.date()))["flows"]["grid_import"]
            home.status = "offline"
            assert not any((await energy_report(session, home, now.date()))["flows"].values())
    asyncio.run(check())

@pytest.fixture
def features(store, monkeypatch):
    scope, contexts, identities = store
    monkeypatch.setattr(feature, "get_session", scope)
    client = AsyncMock()
    client.get_states.return_value = [{"entity_id": "media_player.home", "state": "idle", "attributes": {}},
        {"entity_id": "todo.shopping", "state": "1", "attributes": {}}]
    monkeypatch.setattr(feature, "client_for", AsyncMock(return_value=client))
    command = AsyncMock()
    monkeypatch.setattr(feature, "command", command)
    return contexts, identities, client, command

def test_private_features_reject_other_customer_and_support_staff(features):
    (owner, other, staff), (home, second), client, command = features
    async def check():
        for ctx in [other, staff]:
            for action in [lambda: feature.media(home, ctx), lambda: feature.map_locations(home, ctx),
                    lambda: feature.todos(home, "", ctx), lambda: feature.browse(home, "", ctx)]:
                with pytest.raises(HTTPException) as error:
                    await action()
                assert error.value.status_code in {403, 404}
        client.get_states.assert_not_awaited()
        command.assert_not_awaited()
    asyncio.run(check())

def test_media_control_targets_only_a_player_in_the_owned_gateway(features):
    (owner, *_), (home, _), client, command = features
    async def check():
        await feature.media_action(home, feature.MediaAction(player="media_player.home", action="play"), owner)
        client.call_service.assert_awaited_once_with("media_player", "media_play", {}, target={"entity_id": "media_player.home"})
        with pytest.raises(HTTPException):
            await feature.media_action(home, feature.MediaAction(player="media_player.someone_else", action="play"), owner)
    asyncio.run(check())

def test_media_rejects_arbitrary_urls_and_unlisted_playable_items(features):
    (owner, *_), (home, _), client, command = features
    command.return_value = {"children": []}
    async def check():
        for identity in ["http://127.0.0.1/secret", "media-source://radio_browser/unlisted"]:
            with pytest.raises(HTTPException):
                await feature.media_action(home, feature.MediaAction(player="media_player.home", action="play_item", content_id=identity), owner)
        client.call_service.assert_not_awaited()
    asyncio.run(check())

def test_media_action_validation_disallows_services_and_invalid_volume():
    with pytest.raises(ValidationError):
        feature.MediaAction(player="media_player.home", action="lock")
    with pytest.raises(ValidationError):
        feature.MediaAction(player="media_player.home", action="volume", volume=2)

def test_task_mutations_require_uid_in_the_selected_owned_list(features):
    (owner, *_), (home, _), client, command = features
    command.return_value = {"response": {"todo.shopping": {"items": [{"uid": "own-task", "summary": "Milk", "status": "needs_action"}]}}}
    async def check():
        with pytest.raises(HTTPException):
            await feature.todo_action(home, feature.TodoAction(list_id="todo.shopping", action="remove", item="other-task"), owner)
        client.call_service.assert_not_awaited()
        await feature.todo_action(home, feature.TodoAction(list_id="todo.shopping", action="complete", item="own-task"), owner)
        client.call_service.assert_awaited_once_with("todo", "update_item", {"item": "own-task", "status": "completed"}, target={"entity_id": "todo.shopping"})
    asyncio.run(check())

def test_map_discards_invalid_and_unavailable_locations():
    def row(latitude, longitude, state="home"):
        return {"entity_id": "person.owner", "state": state, "attributes": {"latitude": latitude, "longitude": longitude}}
    assert feature.location(row(-26.2, 28.0))["latitude"] == -26.2
    for source in [row(float("nan"), 28), row(-91, 28), row(0, 181), row(0, 0, "unavailable")]:
        assert feature.location(source) is None

