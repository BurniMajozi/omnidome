"""Guided integration setup: drives Home Assistant's own config flow (e.g. Imou App ID / secret / region)
so customers never have to leave HomeDome. Secrets are forwarded to the customer's HA and never stored or logged."""
import asyncio
import re
import uuid
from typing import Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from services.common.auth import AuthContext, get_auth_context
from services.iot.database import get_session
from services.iot.ha_client import HAWebSocketClient, ha_http_error, token_for_integration
from services.iot.households import home_for, audit, client_for, sync_home
from services.iot.managed_gateway import target_for
from services.iot.models import IoTHomeEntity
from services.iot.routes.homes import enabled, entity_for

router = APIRouter(dependencies=[Depends(enabled)])

# Only integrations whose HA setup is a plain form (no OAuth redirect, hardware or discovery step).
GUIDED = {"imou", "onvif"}
FLOW_ID = re.compile(r"^[A-Za-z0-9]{16,64}$")
DIRECTIONS = ("up", "down", "left", "right")


class FlowInput(BaseModel):
    user_input: dict = Field(default_factory=dict, max_length=24)


class Ptz(BaseModel):
    direction: Literal["up", "down", "left", "right"]


def scalar(value):
    return value if isinstance(value, (str, int, float, bool)) and len(str(value)) <= 512 else None


def public_field(field):
    if not isinstance(field, dict) or not isinstance(field.get("name"), str):
        return None
    out = {"name": field["name"][:64], "type": str(field.get("type", "string"))[:24], "required": bool(field.get("required"))}
    if scalar(field.get("default")) is not None:
        out["default"] = field["default"]
    options = field.get("options")
    selector = field.get("selector")
    if isinstance(selector, dict) and isinstance(selector.get("select"), dict):
        options = selector["select"].get("options")
    if isinstance(options, list):
        clean = []
        for item in options[:50]:
            if isinstance(item, (list, tuple)) and len(item) == 2:
                clean.append({"value": str(item[0])[:64], "label": str(item[1])[:96]})
            elif isinstance(item, dict) and "value" in item:
                clean.append({"value": str(item["value"])[:64], "label": str(item.get("label", item["value"]))[:96]})
            elif isinstance(item, str):
                clean.append({"value": item[:64], "label": item.replace("_", " ")[:96]})
        if clean:
            out["options"] = clean
    return out


def public_step(data):
    """Whitelist what the browser may see from an HA flow response."""
    if not isinstance(data, dict):
        return {"type": "abort", "reason": "unknown"}
    errors = data.get("errors") if isinstance(data.get("errors"), dict) else {}
    return {
        "type": str(data.get("type", ""))[:24], "flow_id": str(data.get("flow_id", ""))[:64],
        "step_id": str(data.get("step_id", ""))[:64], "reason": str(data.get("reason", ""))[:64],
        "title": str(data.get("title", ""))[:128],
        "errors": {str(k)[:64]: str(v)[:64] for k, v in errors.items()},
        "fields": [f for f in (public_field(item) for item in (data.get("data_schema") or [])[:24]) if f],
        "menu_options": [str(item)[:64] for item in (data.get("menu_options") or [])[:20]] if isinstance(data.get("menu_options"), list) else [],
    }


def flow_failure(exc):
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        if code == 404:
            raise HTTPException(410, "This setup session expired. Start the setup again.") from exc
        if code in (401, 403):
            raise HTTPException(409, "The saved Home Assistant token is not an administrator token. Reconnect HomeDome with an administrator's token.") from exc
        if code == 400:
            raise HTTPException(422, "Home Assistant rejected the details. Check them and try again.") from exc
    raise ha_http_error(exc) from exc


def check_domain(domain):
    if domain not in GUIDED:
        raise HTTPException(404, "Guided setup is not available for this integration")


@router.post("/{home_id}/integrations/{domain}/setup")
async def start_setup(home_id: uuid.UUID, domain: str, ctx: AuthContext = Depends(get_auth_context)):
    check_domain(domain)
    async with get_session() as session:
        home = await home_for(session, ctx, home_id, owner_only=True)
        client = await client_for(home)
        audit(session, home, ctx.user_id, "integration_setup_started", integration=domain)
    try:
        return public_step(await client.config_flow("POST", body={"handler": domain, "show_advanced_options": False}))
    except Exception as exc:
        flow_failure(exc)
    finally:
        await client.aclose()


@router.post("/{home_id}/integrations/setup/{flow_id}")
async def continue_setup(home_id: uuid.UUID, flow_id: str, body: FlowInput, ctx: AuthContext = Depends(get_auth_context)):
    if not FLOW_ID.fullmatch(flow_id):
        raise HTTPException(422, "Invalid setup session")
    values = {str(k)[:64]: v for k, v in body.user_input.items() if scalar(v) is not None}
    async with get_session() as session:
        home = await home_for(session, ctx, home_id, owner_only=True)
        client = await client_for(home)
    try:
        step = public_step(await client.config_flow("POST", flow_id, values))
    except Exception as exc:
        flow_failure(exc)
    finally:
        await client.aclose()
    if step["type"] == "create_entry":
        async with get_session() as session:
            home = await home_for(session, ctx, home_id, owner_only=True)
            audit(session, home, ctx.user_id, "integration_setup_completed", title=step["title"])
            # Devices appear once HA's first cloud refresh finishes; the panel offers a re-sync too.
            await asyncio.sleep(3)
            await sync_home(session, home, ctx.user_id)
    return step


@router.delete("/{home_id}/integrations/setup/{flow_id}")
async def cancel_setup(home_id: uuid.UUID, flow_id: str, ctx: AuthContext = Depends(get_auth_context)):
    if not FLOW_ID.fullmatch(flow_id):
        raise HTTPException(422, "Invalid setup session")
    async with get_session() as session:
        home = await home_for(session, ctx, home_id, owner_only=True)
        client = await client_for(home)
    try:
        await client.config_flow("DELETE", flow_id)
    except Exception:
        pass  # already finished or expired
    finally:
        await client.aclose()
    return {"ok": True}


@router.get("/{home_id}/integrations/{domain}/entities")
async def integration_entities(home_id: uuid.UUID, domain: str, ctx: AuthContext = Depends(get_auth_context)):
    """Synced entities that belong to one HA integration (e.g. every Imou camera, PTZ button and sensor)."""
    check_domain(domain)
    async with get_session() as session:
        home = await home_for(session, ctx, home_id, "diagnostics")
        if not home.ha_url or not home.ha_token_encrypted:
            return {"entities": [], "connected": False}
        managed = target_for(home)
        ws = HAWebSocketClient(managed or home.ha_url, token_for_integration(home), managed_gateway=bool(managed))
        try:
            async with asyncio.timeout(10):
                await ws.connect()
                registry = await ws.request("config/entity_registry/list")
        except Exception:
            registry = []
        finally:
            await ws.close()
        ids = {row.get("entity_id") for row in registry if isinstance(row, dict) and row.get("platform") == domain}
        rows = (await session.scalars(select(IoTHomeEntity).where(IoTHomeEntity.home_id == home.id,
            IoTHomeEntity.tenant_id == ctx.tenant_id, IoTHomeEntity.entity_id.in_(ids or {""})).order_by(IoTHomeEntity.name))).all() if ids else []
        out = []
        for row in rows:
            ptz = next((d for d in DIRECTIONS if row.domain == "button" and re.search(rf"ptz_{d}(_\d+)?$", row.entity_id)), None)
            out.append({"id": str(row.id), "name": row.name, "domain": row.domain, "state": row.state,
                "attributes": row.attributes, "ptz": ptz})
        return {"entities": out, "connected": True}


@router.post("/{home_id}/devices/{entity_id}/ptz")
async def move_camera(home_id: uuid.UUID, entity_id: uuid.UUID, body: Ptz, ctx: AuthContext = Depends(get_auth_context)):
    """Short PTZ nudge. Needs the customer's *camera* permission, separate from device control."""
    async with get_session() as session:
        home = await home_for(session, ctx, home_id, "camera")
        entity = await entity_for(session, home, entity_id)
        if entity.domain != "button" or not re.search(rf"ptz_{body.direction}(_\d+)?$", entity.entity_id):
            raise HTTPException(422, "Select a camera movement button")
        client = await client_for(home)
        try:
            await client.call_service("button", "press", target={"entity_id": entity.entity_id})
            audit(session, home, ctx.user_id, "camera_moved", device=str(entity.id), direction=body.direction)
        except Exception:
            audit(session, home, ctx.user_id, "camera_move_failed", device=str(entity.id))
            return {"ok": False, "message": "The camera did not confirm the movement. Check it is online."}
        finally:
            await client.aclose()
        return {"ok": True, "message": "Camera moved"}
