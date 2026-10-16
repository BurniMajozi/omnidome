"""Customer-owned HA instances. No tenant-primary fallback or browser credentials."""
import re
import asyncio
import math
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import select, delete, func

from services.iot.access import effective_access, ADMIN_ROLES
from services.iot.ha_client import HARestClient, HAWebSocketClient, token_for_integration, describe_ha_error
from services.iot.models import IoTHome, IoTHomeSupport, IoTHomeAudit, IoTHomeEntity, IoTHomeReading, CustomerPortalAccount, IoTHomeRoom, IoTHomeRoomAssignment
from services.iot.routes.integrations import _checked_url
from services.iot.home_events import emit
from services.iot.managed_gateway import target_for

ENTITY = re.compile(r"^[a-z_]+\.[a-z0-9_]+$")
DOMAINS = {"sensor", "binary_sensor", "light", "switch", "climate", "fan", "camera", "scene", "lock", "alarm_control_panel", "media_player", "cover", "humidifier", "vacuum", "water_heater", "button", "select", "number"}
ATTRIBUTES = {"unit_of_measurement", "device_class", "state_class", "battery_level", "temperature", "current_temperature", "humidity", "brightness", "hvac_mode", "current_position", "supported_features"}
SUPPORT_ROLES = ADMIN_ROLES | {"technician", "support", "support_agent", "call_center", "call_centre", "iot_operator"}


def now():
    return datetime.now(timezone.utc)


def aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


async def staff_access(ctx):
    roles, permissions = await effective_access(ctx)
    return bool(roles & SUPPORT_ROLES or permissions & {"iot.support", "iot.admin"})


async def account_customer_for(session, ctx):
    account = await session.get(CustomerPortalAccount, ctx.user_id)
    if account:
        if account.tenant_id != ctx.tenant_id:
            raise HTTPException(404, "Customer account not found")
        return account.customer_id
    # Existing home assignments remain valid during migration.
    home = await session.scalar(select(IoTHome).where(IoTHome.tenant_id == ctx.tenant_id,
        IoTHome.owner_user_id == ctx.user_id).order_by(IoTHome.id).limit(1))
    if not home:
        raise HTTPException(403, "Ask your ISP to link your verified login to your customer account")
    return home.customer_id


async def bind_customer_account(session, ctx, user_id, customer_id):
    account = await session.get(CustomerPortalAccount, user_id, with_for_update=True)
    if account:
        if account.tenant_id != ctx.tenant_id or account.customer_id != customer_id:
            raise HTTPException(409, "This login is already linked to another customer")
        return
    other_home = await session.scalar(select(IoTHome.id).where(IoTHome.owner_user_id == user_id,
        (IoTHome.customer_id != customer_id) | (IoTHome.tenant_id != ctx.tenant_id)).limit(1))
    if other_home:
        raise HTTPException(409, "This login already owns a different customer's home")
    session.add(CustomerPortalAccount(user_id=user_id, tenant_id=ctx.tenant_id,
        customer_id=customer_id, created_by=ctx.user_id))
    from sqlalchemy.exc import IntegrityError
    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(409, "This login was linked concurrently; refresh and try again") from exc


async def home_for(session, ctx, home_id, scope=None, owner_only=False):
    # Serialises revocation with a command already in flight. Every route uses this boundary.
    home = await session.scalar(select(IoTHome).where(
        IoTHome.id == home_id, IoTHome.tenant_id == ctx.tenant_id).with_for_update())
    if not home:
        raise HTTPException(404, "Home not found")
    if home.owner_user_id == ctx.user_id:
        return home
    if owner_only or not await staff_access(ctx):
        raise HTTPException(404, "Home not found")
    if scope:
        grants = (await session.scalars(select(IoTHomeSupport).where(
            IoTHomeSupport.tenant_id == ctx.tenant_id, IoTHomeSupport.home_id == home.id,
            IoTHomeSupport.staff_user_id == ctx.user_id, IoTHomeSupport.status == "approved",
            IoTHomeSupport.expires_at > now()))).all()
        if not any(scope in grant.scopes for grant in grants):
            raise HTTPException(403, "Customer approval required or support access has expired")
    return home


def audit(session, home, actor, action, **details):
    session.add(IoTHomeAudit(tenant_id=home.tenant_id, home_id=home.id,
        actor_user_id=actor, action=action, details=details, created_at=now()))


def public_home(home, ctx):
    return {"id": str(home.id), "customer_id": str(home.customer_id), "name": home.name,
        "is_owner": home.owner_user_id == ctx.user_id, "status": home.status,
        "last_sync_at": home.last_sync_at, "last_error": home.last_error,
        "dashboard_url": None if home.managed_gateway_key else home.ha_url if home.owner_user_id == ctx.user_id else None,
        "managed_gateway": bool(home.managed_gateway_key)}


async def client_for(home):
    if not home.ha_url or not home.ha_token_encrypted:
        raise HTTPException(409, "Connect this home's Home Assistant first")
    # Recheck stored URLs and DNS before network access; existing SSRF policy still applies.
    managed = target_for(home)
    url = managed or await _checked_url(home.ha_url)
    return HARestClient(url, token_for_integration(home), managed_gateway=bool(managed))


async def rooms_for(home):
    """Optional registry metadata. A restricted HA user can still sync entity states."""
    managed = target_for(home)
    websocket = HAWebSocketClient(managed or home.ha_url, token_for_integration(home), managed_gateway=bool(managed))
    try:
        async with asyncio.timeout(10):
            await websocket.connect()
            areas = await websocket.request("config/area_registry/list")
            devices = await websocket.request("config/device_registry/list")
            entities = await websocket.request("config/entity_registry/list")
            if not all(isinstance(rows, list) for rows in [areas, devices, entities]):
                return {}
            names = {row.get("area_id"): " ".join(str(row.get("name", "")).split())[:128] for row in areas if isinstance(row, dict)}
            device_areas = {row.get("id"): row.get("area_id") for row in devices if isinstance(row, dict)}
            return {"__areas__": areas, **{row.get("entity_id"): names.get(row.get("area_id") or device_areas.get(row.get("device_id")))
                for row in entities if isinstance(row, dict)}}
    except Exception:
        return {}
    finally:
        await websocket.close()


async def sync_home(session, home, actor=None):
    client = None
    previous_status = home.status
    try:
        client = await client_for(home)
        states = await client.get_states()
        config = await client.get_config()
        if not isinstance(config, dict) or not isinstance(config.get("components", []), list):
            raise ValueError("Invalid Home Assistant configuration response")
        components = config.get("components", []) if isinstance(config, dict) else []
        home.components = [item for item in components if isinstance(item, str) and re.fullmatch(r"[a-z0-9_.]+", item)][:2000]
        if not isinstance(states, list) or len(states) > 10000:
            raise ValueError("Invalid Home Assistant states response")
        stamp = now()
        rooms = await rooms_for(home)
        from services.iot.routes.home_rooms import import_areas
        await import_areas(session, home, rooms.get("__areas__", []))
        assignments = dict((await session.execute(select(IoTHomeRoomAssignment.entity_id, IoTHomeRoom.name)
            .join(IoTHomeRoom, IoTHomeRoom.id == IoTHomeRoomAssignment.room_id)
            .where(IoTHomeRoomAssignment.home_id == home.id, IoTHomeRoomAssignment.tenant_id == home.tenant_id,
                IoTHomeRoom.home_id == home.id, IoTHomeRoom.tenant_id == home.tenant_id))).all())
        last_readings = dict((await session.execute(select(IoTHomeReading.entity_id, func.max(IoTHomeReading.observed_at))
            .where(IoTHomeReading.home_id == home.id, IoTHomeReading.tenant_id == home.tenant_id)
            .group_by(IoTHomeReading.entity_id))).all())
        existing = {e.entity_id: e for e in (await session.scalars(select(IoTHomeEntity).where(
            IoTHomeEntity.home_id == home.id, IoTHomeEntity.tenant_id == home.tenant_id))).all()}
        seen = set()
        for raw in states:
            if not isinstance(raw, dict):
                continue
            identity = raw.get("entity_id")
            if not isinstance(identity, str) or len(identity) > 255 or not ENTITY.fullmatch(identity):
                continue
            if identity in seen:
                continue
            domain = identity.split(".", 1)[0]
            if domain not in DOMAINS:
                continue
            state = raw.get("state")
            if not isinstance(state, str) or len(state) > 512:
                continue
            attrs = raw.get("attributes")
            attrs = attrs if isinstance(attrs, dict) else {}
            safe = {key: value for key, value in attrs.items() if key in ATTRIBUTES
                and isinstance(value, (str, int, float, bool)) and len(str(value)) <= 64
                and (not isinstance(value, float) or math.isfinite(value))}
            name = str(attrs.get("friendly_name", identity))[:255]
            row = existing.get(identity)
            if row is None:
                row = IoTHomeEntity(tenant_id=home.tenant_id, home_id=home.id, entity_id=identity)
                session.add(row)
            changed = row.state != state
            row.name, row.domain, row.state, row.attributes, row.observed_at = name, domain, state, safe, stamp
            row.room = assignments.get(row.id, rooms.get(identity))
            seen.add(identity)
            latest = last_readings.get(identity)
            if domain in {"sensor", "binary_sensor"} and (changed or latest is None or aware(latest) < stamp - timedelta(minutes=5)):
                session.add(IoTHomeReading(tenant_id=home.tenant_id, home_id=home.id, entity_id=identity,
                    state=state, unit=str(safe["unit_of_measurement"])[:32] if "unit_of_measurement" in safe else None,
                    observed_at=stamp))
        for identity, row in existing.items():
            if identity not in seen:
                row.state, row.observed_at = "unavailable", stamp
        # Thirty-day telemetry retention; camera frames are never retained.
        await session.execute(delete(IoTHomeReading).where(IoTHomeReading.home_id == home.id,
            IoTHomeReading.tenant_id == home.tenant_id, IoTHomeReading.observed_at < stamp - timedelta(days=30)))
        home.status, home.last_error, home.last_sync_at = "connected", None, stamp
        if previous_status == "error":
            await emit(session, home, "iot.home.recovered", str(home.id) + ":recovered:" + stamp.isoformat())
        audit(session, home, actor, "sync", entities=len(seen))
        return {"ok": True, "entities": len(seen), "observed_at": stamp}
    except HTTPException as exc:
        home.status, home.last_error = "error", "connection_not_ready"
        if previous_status == "connected":
            await emit(session, home, "iot.home.offline", str(home.id) + ":offline:" + now().isoformat())
        audit(session, home, actor, "sync_failed", code="connection_not_ready")
        return {"ok": False, "message": str(exc.detail)}
    except Exception as exc:
        code, _ = describe_ha_error(exc)
        home.status, home.last_error = "error", code
        if previous_status == "connected":
            await emit(session, home, "iot.home.offline", str(home.id) + ":offline:" + now().isoformat())
        audit(session, home, actor, "sync_failed", code=code)
        return {"ok": False, "message": "Home Assistant could not be reached. Check the connection and token."}
    finally:
        if client:
            await client.aclose()
