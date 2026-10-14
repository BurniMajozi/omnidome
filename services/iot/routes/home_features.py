"""Private household media, locations and tasks; never shared through diagnostics."""
import asyncio
import re
import uuid
from contextlib import asynccontextmanager
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from services.common.auth import AuthContext, get_auth_context
from services.iot.database import get_session
from services.iot.households import home_for, client_for
from services.iot.home_energy import numeric
from services.iot.ha_client import HAWebSocketClient, token_for_integration, ha_http_error
from services.iot.managed_gateway import target_for
from services.iot.routes.homes import enabled

router = APIRouter(dependencies=[Depends(enabled)])
ENTITY = re.compile(r"^[a-z_]+\.[a-z0-9_]+$")


@asynccontextmanager
async def household(home_id, ctx):
    async with get_session() as session:
        home = await home_for(session, ctx, home_id, owner_only=True)
        client = await client_for(home)
        try:
            yield home, client
        except HTTPException:
            raise
        except Exception as exc:
            raise ha_http_error(exc) from exc
        finally:
            await client.aclose()


async def command(home, kind, **fields):
    managed = target_for(home)
    websocket = HAWebSocketClient(managed or home.ha_url, token_for_integration(home), managed_gateway=bool(managed))
    try:
        async with asyncio.timeout(20):
            await websocket.connect()
            return await websocket.request(kind, **fields)
    finally:
        await websocket.close()


async def entity(client, identity, domain):
    if not ENTITY.fullmatch(identity) or not identity.startswith(domain + "."):
        raise HTTPException(422, "Invalid device or list")
    rows = await client.get_states()
    found = next((row for row in rows if row.get("entity_id") == identity), None)
    if not found:
        raise HTTPException(404, "Device or list not found in this home")
    if found.get("state") in {"unavailable", "unknown"}:
        raise HTTPException(409, "This device or list is currently unavailable")
    return found


def media_id(value):
    if value and (not value.startswith("media-source://") or len(value) > 2048 or any(ord(char) < 32 for char in value)):
        raise HTTPException(422, "Choose media from this home's library")
    return value


def media_node(row):
    return {key: row.get(key) for key in ["title", "media_content_id", "media_content_type", "can_play", "can_expand", "media_class"]}


@router.get("/{home_id}/media")
async def media(home_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context)):
    async with household(home_id, ctx) as (_, client):
        rows = await client.get_states()
        return {"players": [{"id": row["entity_id"], "name": row.get("attributes", {}).get("friendly_name", row["entity_id"]),
            "state": row.get("state"), "title": row.get("attributes", {}).get("media_title"),
            "artist": row.get("attributes", {}).get("media_artist"), "volume": row.get("attributes", {}).get("volume_level")}
            for row in rows if row.get("entity_id", "").startswith("media_player.")][:200]}


@router.get("/{home_id}/media/browse")
async def browse(home_id: uuid.UUID, content_id: str = Query(default="", max_length=2048), ctx: AuthContext = Depends(get_auth_context)):
    media_id(content_id)
    async with household(home_id, ctx) as (home, _):
        result = await command(home, "media_source/browse_media", media_content_id=content_id)
        return {**media_node(result), "children": [media_node(row) for row in result.get("children", [])[:1000]]}


class MediaAction(BaseModel):
    player: str = Field(max_length=128)
    action: Literal["play", "pause", "stop", "next", "previous", "volume", "play_item"]
    volume: float | None = Field(default=None, ge=0, le=1)
    content_id: str = Field(default="", max_length=2048)
    parent_id: str = Field(default="", max_length=2048)


@router.post("/{home_id}/media")
async def media_action(home_id: uuid.UUID, body: MediaAction, ctx: AuthContext = Depends(get_auth_context)):
    async with household(home_id, ctx) as (home, client):
        await entity(client, body.player, "media_player")
        services = {"play": "media_play", "pause": "media_pause", "stop": "media_stop", "next": "media_next_track", "previous": "media_previous_track", "volume": "volume_set", "play_item": "play_media"}
        data = {}
        if body.action == "volume":
            if body.volume is None:
                raise HTTPException(422, "Choose a volume")
            data["volume_level"] = body.volume
        if body.action == "play_item":
            if not media_id(body.content_id):
                raise HTTPException(422, "Choose a playable item")
            result = await command(home, "media_source/browse_media", media_content_id=media_id(body.parent_id))
            chosen = next((row for row in result.get("children", []) if row.get("media_content_id") == body.content_id and row.get("can_play")), None)
            if not chosen:
                raise HTTPException(422, "Choose a playable item from this home's library")
            data = {"media_content_id": body.content_id, "media_content_type": chosen["media_content_type"]}
        await client.call_service("media_player", services[body.action], data, target={"entity_id": body.player})
        return {"ok": True}


def location(row):
    attributes = row.get("attributes", {})
    latitude, longitude = numeric(attributes.get("latitude")), numeric(attributes.get("longitude"))
    if latitude is None or longitude is None or not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        return None
    if row.get("state") in {"unavailable", "unknown"}:
        return None
    return {"id": row["entity_id"], "name": attributes.get("friendly_name", row["entity_id"]),
        "state": row.get("state"), "latitude": latitude, "longitude": longitude, "updated": row.get("last_updated")}


@router.get("/{home_id}/map")
async def map_locations(home_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context)):
    async with household(home_id, ctx) as (_, client):
        rows = await client.get_states()
        return {"locations": [point for row in rows if row.get("entity_id", "").split(".")[0] in {"person", "device_tracker", "zone"} and (point := location(row)) is not None][:200]}


async def items(home, identity):
    result = await command(home, "call_service", domain="todo", service="get_items", service_data={},
        target={"entity_id": identity}, return_response=True)
    return (result.get("response") or {}).get(identity, {}).get("items", [])[:1000]


@router.get("/{home_id}/todo")
async def todos(home_id: uuid.UUID, list_id: str = Query(default="", max_length=128), ctx: AuthContext = Depends(get_auth_context)):
    async with household(home_id, ctx) as (home, client):
        rows = await client.get_states()
        lists = [{"id": row["entity_id"], "name": row.get("attributes", {}).get("friendly_name", row["entity_id"]), "state": row.get("state")} for row in rows if row.get("entity_id", "").startswith("todo.")]
        if not list_id:
            return {"lists": lists, "items": []}
        await entity(client, list_id, "todo")
        return {"lists": lists, "items": [{key: row.get(key) for key in ["uid", "summary", "status", "due"]} for row in await items(home, list_id)]}


class TodoAction(BaseModel):
    list_id: str = Field(max_length=128)
    action: Literal["add", "complete", "reopen", "remove", "rename"]
    item: str = Field(default="", max_length=256)
    summary: str = Field(default="", max_length=500)


@router.post("/{home_id}/todo")
async def todo_action(home_id: uuid.UUID, body: TodoAction, ctx: AuthContext = Depends(get_auth_context)):
    async with household(home_id, ctx) as (home, client):
        await entity(client, body.list_id, "todo")
        if body.action == "add":
            if not body.summary.strip():
                raise HTTPException(422, "Enter a task")
            service, data = "add_item", {"item": body.summary.strip()}
        else:
            existing = await items(home, body.list_id)
            if not body.item or not any(row.get("uid") == body.item for row in existing):
                raise HTTPException(404, "Task not found in this list")
            service, data = "update_item", {"item": body.item}
            if body.action == "remove":
                service = "remove_item"
            elif body.action == "rename":
                if not body.summary.strip():
                    raise HTTPException(422, "Enter a task")
                data["rename"] = body.summary.strip()
            else:
                data["status"] = "completed" if body.action == "complete" else "needs_action"
        await client.call_service("todo", service, data, target={"entity_id": body.list_id})
        return {"ok": True}

