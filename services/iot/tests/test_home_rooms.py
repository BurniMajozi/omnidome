"""Empty room layout, private writes, gateway import and assignment persistence."""
import asyncio
from unittest.mock import AsyncMock
import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from services.iot.tests.test_homedome import store
from services.iot.models import IoTHome, IoTHomeEntity, IoTHomeRoom, IoTHomeRoomAssignment
from services.iot.routes import home_rooms as api
from services.iot.routes import homes
from services.iot import households

def test_owner_can_create_empty_room_without_gateway_and_duplicates_are_rejected(store, monkeypatch):
    scope, (owner, other, staff), (home, second) = store
    monkeypatch.setattr(api, "get_session", scope)
    network = AsyncMock()
    monkeypatch.setattr(households, "client_for", network)
    async def check():
        row = await api.create_room(home, api.RoomInput(name="  Living   room ", kind="living"), owner)
        assert row["name"] == "Living room"
        assert (await api.rooms(home, owner))[0]["id"] == row["id"]
        with pytest.raises(HTTPException) as error:
            await api.create_room(home, api.RoomInput(name="living room"), owner)
        assert error.value.status_code == 409
        for ctx in [other, staff]:
            with pytest.raises(HTTPException):
                await api.create_room(home, api.RoomInput(name="Kitchen"), ctx)
        network.assert_not_awaited()
    asyncio.run(check())

def test_gateway_empty_areas_are_imported_once_and_match_existing_room(store):
    scope, (owner, *_), (identity, _) = store
    async def check():
        async with scope() as session:
            home = await session.get(IoTHome, identity)
            session.add(IoTHomeRoom(tenant_id=owner.tenant_id, home_id=identity, name="Kitchen", kind="kitchen"))
            await session.flush()
            areas = [{"area_id": "kitchen", "name": "Kitchen"}, {"area_id": "living", "name": "Living room"}, None]
            await api.import_areas(session, home, areas)
            await api.import_areas(session, home, areas)
            rows = (await session.scalars(select(IoTHomeRoom))).all()
            assert len(rows) == 2
            assert next(row for row in rows if row.name == "Kitchen").ha_area_id == "kitchen"
    asyncio.run(check())

def test_room_assignment_is_home_scoped_and_survives_gateway_sync(store, monkeypatch):
    scope, (owner, *_), (identity, second) = store
    monkeypatch.setattr(api, "get_session", scope)
    client = AsyncMock()
    client.get_states.return_value = [{"entity_id": "light.test", "state": "on", "attributes": {"brightness": 128}}]
    client.get_config.return_value = {"components": []}
    monkeypatch.setattr(households, "client_for", AsyncMock(return_value=client))
    async def check():
        async with scope() as session:
            room = IoTHomeRoom(tenant_id=owner.tenant_id, home_id=identity, name="Office", kind="office")
            foreign = IoTHomeRoom(tenant_id=owner.tenant_id, home_id=second, name="Foreign room", kind="other")
            device = IoTHomeEntity(tenant_id=owner.tenant_id, home_id=identity, entity_id="light.test", name="Lamp", domain="light", state="off", attributes={}, observed_at=households.now())
            session.add_all([room, foreign, device]); await session.flush()
            room_id, foreign_id, device_id = room.id, foreign.id, device.id
        with pytest.raises(HTTPException) as error:
            await api.assign_room(identity, foreign_id, device_id, owner)
        assert error.value.status_code == 404
        await api.assign_room(identity, room_id, device_id, owner)
        async with scope() as session:
            home = await session.get(IoTHome, identity)
            assert (await households.sync_home(session, home))["ok"]
            assert (await session.get(IoTHomeEntity, device_id)).room == "Office"
    asyncio.run(check())

def test_blank_room_name_is_invalid():
    with pytest.raises(ValidationError):
        api.RoomInput(name="   ")

def test_blind_control_validates_position_and_confirms_only_the_targeted_device(store, monkeypatch):
    scope, (owner, *_), (identity, _) = store
    client = AsyncMock()
    client.get_state.return_value = {"entity_id": "cover.blinds", "state": "open", "attributes": {"current_position": 50, "access_token": "must-not-store"}}
    monkeypatch.setattr(homes, "client_for", AsyncMock(return_value=client))
    async def check():
        async with scope() as session:
            device = IoTHomeEntity(tenant_id=owner.tenant_id, home_id=identity, entity_id="cover.blinds", name="Blinds", domain="cover", state="closed", attributes={}, observed_at=households.now())
            session.add(device); await session.flush(); device_id = device.id
        with pytest.raises(HTTPException) as error:
            await homes.control(identity, device_id, homes.Command(service="set_cover_position", service_data={"position": 120}), owner)
        assert error.value.status_code == 422
        client.call_service.assert_not_awaited()
        assert (await homes.control(identity, device_id, homes.Command(service="set_cover_position", service_data={"position": 50}), owner))["ok"]
        client.call_service.assert_awaited_once_with("cover", "set_cover_position", {"position": 50}, target={"entity_id": "cover.blinds"})
        async with scope() as session:
            device = await session.get(IoTHomeEntity, device_id)
            assert device.attributes == {"current_position": 50}
            assert device.state == "open"
    asyncio.run(check())

