"""HomeDome room layout, independently editable before gateway pairing."""
import uuid
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from services.common.auth import AuthContext, get_auth_context
from services.iot.database import get_session
from services.iot.households import home_for, audit
from services.iot.models import IoTHomeRoom, IoTHomeRoomAssignment, IoTHomeEntity
from services.iot.routes.homes import enabled, entity_for

router = APIRouter(dependencies=[Depends(enabled)])
class RoomInput(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    kind: Literal["living", "kitchen", "bedroom", "bathroom", "office", "garage", "garden", "energy", "other"] = "other"
    @field_validator("name")
    @classmethod
    def clean_name(cls, value):
        value = " ".join(value.split())
        if not value or any(ord(char) < 32 for char in value):
            raise ValueError("Enter a room name")
        return value

def room_dict(row):
    return {"id": str(row.id), "name": row.name, "kind": row.kind, "source": "gateway" if row.ha_area_id else "homedome"}

@router.get("/{home_id}/rooms")
async def rooms(home_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context)):
    async with get_session() as session:
        home = await home_for(session, ctx, home_id, "diagnostics")
        rows = (await session.scalars(select(IoTHomeRoom).where(IoTHomeRoom.tenant_id == ctx.tenant_id,
            IoTHomeRoom.home_id == home.id).order_by(IoTHomeRoom.name))).all()
        return [room_dict(row) for row in rows]

@router.post("/{home_id}/rooms")
async def create_room(home_id: uuid.UUID, body: RoomInput, ctx: AuthContext = Depends(get_auth_context)):
    async with get_session() as session:
        home = await home_for(session, ctx, home_id, owner_only=True)
        rows = (await session.scalars(select(IoTHomeRoom).where(IoTHomeRoom.tenant_id == ctx.tenant_id,
            IoTHomeRoom.home_id == home.id))).all()
        if any(row.name.casefold() == body.name.casefold() for row in rows):
            raise HTTPException(409, "A room with this name already exists")
        if len(rows) >= 100:
            raise HTTPException(422, "This home already has 100 rooms")
        row = IoTHomeRoom(tenant_id=ctx.tenant_id, home_id=home.id, name=body.name, kind=body.kind)
        session.add(row)
        await session.flush()
        audit(session, home, ctx.user_id, "room_created", room=str(row.id))
        return room_dict(row)

@router.put("/{home_id}/rooms/{room_id}/devices/{entity_id}")
async def assign_room(home_id: uuid.UUID, room_id: uuid.UUID, entity_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context)):
    async with get_session() as session:
        home = await home_for(session, ctx, home_id, owner_only=True)
        room = await session.scalar(select(IoTHomeRoom).where(IoTHomeRoom.id == room_id,
            IoTHomeRoom.home_id == home.id, IoTHomeRoom.tenant_id == ctx.tenant_id))
        if not room:
            raise HTTPException(404, "Room not found in this home")
        entity = await entity_for(session, home, entity_id)
        assignment = await session.get(IoTHomeRoomAssignment, entity.id)
        if assignment is None:
            assignment = IoTHomeRoomAssignment(entity_id=entity.id, home_id=home.id, tenant_id=ctx.tenant_id, room_id=room.id)
            session.add(assignment)
        else:
            assignment.room_id = room.id
        entity.room = room.name
        audit(session, home, ctx.user_id, "device_room_changed", device=str(entity.id), room=str(room.id))
        return {"ok": True}

async def import_areas(session, home, areas):
    rows = (await session.scalars(select(IoTHomeRoom).where(IoTHomeRoom.tenant_id == home.tenant_id,
        IoTHomeRoom.home_id == home.id))).all()
    by_area = {row.ha_area_id: row for row in rows if row.ha_area_id}
    for area in areas[:100]:
        if not isinstance(area, dict):
            continue
        identity, name = area.get("area_id"), area.get("name")
        if not isinstance(identity, str) or not identity or len(identity) > 128 or not isinstance(name, str) or not name.strip():
            continue
        name = " ".join(name.split())[:128]
        row = by_area.get(identity) or next((row for row in rows if row.name.casefold() == name.casefold() and not row.ha_area_id), None)
        if row is None:
            if len(rows) >= 100:
                break
            row = IoTHomeRoom(tenant_id=home.tenant_id, home_id=home.id, name=name, kind="other", ha_area_id=identity)
            session.add(row); rows.append(row)
        else:
            row.name, row.ha_area_id = name, identity
        by_area[identity] = row
    await session.flush()

