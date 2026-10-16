"""Residential IoT API. Owner identity is provisioned, never accepted from customer reads."""
import uuid
from datetime import date
from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, text

from services.common.auth import AuthContext, get_auth_context
from services.iot.access import require_tier, required_tier_for_control
from services.iot.database import get_session
from services.iot.ha_client import encrypt_token, ha_http_error
from services.iot.households import home_for, staff_access, public_home, audit, now, client_for, sync_home
from services.iot.models import IoTHome, IoTHomeEntity, IoTHomeReading, IoTHomeSupport, IoTHomeAudit
from services.iot.routes.integrations import _checked_url
from services.iot.home_events import emit, support_notice

async def enabled(ctx: AuthContext = Depends(get_auth_context)):
    # Residential customers are not platform staff seats. Check the ISP's IoT module,
    # then household ownership/consent separately; do not count household users as seats.
    from services.common.entitlements import EntitlementGuard
    guard = EntitlementGuard(module_id="iot")
    guard.dependency()
    if guard.enforce_modules and not ctx.is_platform_admin:
        state = await guard._check_tenant_module(str(ctx.tenant_id))
        if not state.enabled:
            raise HTTPException(402 if state.reason == "payment_required" else 403, "IoT is not enabled for this tenant")


router = APIRouter(dependencies=[Depends(enabled)])
account_router = APIRouter()
Scope = Literal["diagnostics", "control", "camera"]


class Provision(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    customer_id: uuid.UUID
    owner_user_id: uuid.UUID


class Connection(BaseModel):
    ha_url: str = Field(max_length=512)
    ha_token: str = Field(min_length=10, max_length=4096)


class PortalAccount(BaseModel):
    customer_id: uuid.UUID
    owner_user_id: uuid.UUID


class SupportRequest(BaseModel):
    reference: str = Field(min_length=1, max_length=128)
    reason: str = Field(min_length=5, max_length=500)
    scopes: list[Scope] = Field(default_factory=lambda: ["diagnostics"], min_length=1, max_length=3)

    @field_validator("scopes")
    @classmethod
    def diagnostics_required(cls, value):
        if "diagnostics" not in value:
            raise ValueError("Support access must include device diagnostics")
        return value


class Approval(BaseModel):
    scopes: list[Scope] = Field(min_length=1, max_length=3)
    minutes: int = Field(default=30, ge=5, le=60)

    @field_validator("scopes")
    @classmethod
    def diagnostics_required(cls, value):
        return SupportRequest.diagnostics_required(value)


class Command(BaseModel):
    service: str = Field(min_length=1, max_length=64)
    service_data: dict = Field(default_factory=dict)


class EnergyConfig(BaseModel):
    meters: dict[str, uuid.UUID] = Field(default_factory=dict, max_length=11)
    grid_tariff: float | None = Field(default=None, ge=0, le=1000, allow_inf_nan=False)


@router.get("/capabilities")
async def capabilities(ctx: AuthContext = Depends(get_auth_context)):
    from services.iot.access import has_tier
    from services.iot.managed_gateway import enabled, PUBLIC_URL
    provision = await has_tier(ctx, "admin")
    return {"can_provision": provision, "can_request_support": await staff_access(ctx),
        "can_assign_gateway": enabled() and ctx.is_platform_admin,
        "gateway_onboarding_url": None}  # customers and staff never open Home Assistant; HomeDome activates it


@account_router.post("/accounts")
async def link_portal_account(body: PortalAccount, ctx: AuthContext = Depends(get_auth_context)):
    from services.iot.access import effective_access, ADMIN_ROLES, ADMIN_PERMS
    from services.iot.households import bind_customer_account
    roles, permissions = await effective_access(ctx)
    if not (ctx.is_platform_admin or roles & ADMIN_ROLES or permissions & ADMIN_PERMS):
        raise HTTPException(403, "Only an administrator can link customer portal accounts")
    async with get_session() as session:
        customer = await session.scalar(text("SELECT id FROM customers WHERE id=:id AND tenant_id=:tenant"),
            {"id": str(body.customer_id), "tenant": str(ctx.tenant_id)})
        user = await session.scalar(text("SELECT id FROM users WHERE id=:id AND tenant_id=:tenant AND is_active=true AND supabase_user_id IS NOT NULL"),
            {"id": str(body.owner_user_id), "tenant": str(ctx.tenant_id)})
        if not customer or not user:
            raise HTTPException(422, "Select a customer and active verified login from this tenant")
        await bind_customer_account(session, ctx, body.owner_user_id, body.customer_id)
        return {"ok": True}


@account_router.get("/profile")
async def customer_profile(ctx: AuthContext = Depends(get_auth_context)):
    from services.iot.households import account_customer_for
    async with get_session() as session:
        active = await session.scalar(text("SELECT id FROM users WHERE id=:id AND tenant_id=:tenant AND is_active=true"),
            {"id": str(ctx.user_id), "tenant": str(ctx.tenant_id)})
        if not active:
            raise HTTPException(403, "Your customer login is inactive or not provisioned")
        customer_id = await account_customer_for(session, ctx)
        row = (await session.execute(text("SELECT first_name,last_name,email,phone,account_number,rica_verified,created_at FROM customers WHERE id=:id AND tenant_id=:tenant"),
            {"id": str(customer_id), "tenant": str(ctx.tenant_id)})).mappings().first()
        if not row:
            raise HTTPException(404, "Customer profile not found")
        return {"id": str(customer_id), "email": row["email"] or "", "phone": row["phone"] or "",
            "firstName": row["first_name"] or "", "lastName": row["last_name"] or "",
            "accountNumber": row["account_number"] or "", "ricaVerified": bool(row["rica_verified"]),
            "ricaStatus": "verified" if row["rica_verified"] else "pending", "contactChannel": "email",
            "createdAt": row["created_at"]}


@router.get("/staff-profile")
async def staff_profile(ctx: AuthContext = Depends(get_auth_context)):
    if not await staff_access(ctx):
        raise HTTPException(403, "Your account needs an IoT support role")
    async with get_session() as session:
        email = await session.scalar(text("SELECT email FROM users WHERE id=:id AND tenant_id=:tenant AND is_active=true"),
            {"id": str(ctx.user_id), "tenant": str(ctx.tenant_id)})
        if not email:
            raise HTTPException(403, "Your support account is inactive")
        return {"id": str(ctx.user_id), "email": email, "name": email, "role": "IoT support"}


@router.get("/{home_id}/energy/config")
async def read_energy_config(home_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context)):
    from services.iot.home_energy import SOURCES, POWER
    async with get_session() as session:
        home = await home_for(session, ctx, home_id, owner_only=True)
        rows = (await session.scalars(select(IoTHomeEntity).where(IoTHomeEntity.home_id == home.id,
            IoTHomeEntity.tenant_id == ctx.tenant_id))).all()
        ids = {row.entity_id: str(row.id) for row in rows}
        config = home.energy_config or {}
        return {"meters": {key: ids[value] for key, value in config.items()
            if key in SOURCES | POWER and value in ids}, "grid_tariff": config.get("grid_tariff")}


@router.get("/{home_id}/integrations")
async def integrations(home_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context)):
    from services.iot.integration_catalog import catalogue
    async with get_session() as session:
        home = await home_for(session, ctx, home_id, "diagnostics")
        return catalogue(home.components)


@router.put("/{home_id}/energy/config")
async def configure_energy(home_id: uuid.UUID, body: EnergyConfig, ctx: AuthContext = Depends(get_auth_context)):
    from services.iot.home_energy import SOURCES, POWER, factor
    async with get_session() as session:
        home = await home_for(session, ctx, home_id, owner_only=True)
        config = {}
        counters = [identity for source, identity in body.meters.items() if source in SOURCES]
        if len(counters) != len(set(counters)):
            raise HTTPException(422, "Use a separate cumulative meter for each source")
        for source, entity_id in body.meters.items():
            if source not in SOURCES | POWER:
                raise HTTPException(422, "Unknown energy source")
            entity = await entity_for(session, home, entity_id)
            unit = entity.attributes.get("unit_of_measurement")
            if entity.domain != "sensor" or (unit not in {"W", "kW"} if source in POWER else factor(source, unit) is None):
                raise HTTPException(422, "Select a meter with a compatible measurement unit")
            if source in SOURCES and entity.attributes.get("state_class") not in {"total", "total_increasing"}:
                raise HTTPException(422, "Select a cumulative meter (Home Assistant state class total or total_increasing)")
            config[source] = entity.entity_id
        config["grid_tariff"] = body.grid_tariff
        home.energy_config = config
        audit(session, home, ctx.user_id, "energy_configured", sources=sorted(body.meters))
        return {"ok": True}


@router.get("/{home_id}/energy")
async def energy(home_id: uuid.UUID, day: date, ctx: AuthContext = Depends(get_auth_context)):
    from services.iot.home_energy import energy_report
    async with get_session() as session:
        home = await home_for(session, ctx, home_id, "diagnostics")
        audit(session, home, ctx.user_id, "energy_viewed", day=str(day))
        return await energy_report(session, home, day)


def support_read(row):
    status = row.status
    from services.iot.households import aware
    if status in {"pending", "approved"} and aware(row.expires_at) <= now():
        status = "expired"
    return {"id": str(row.id), "staff_user_id": str(row.staff_user_id), "reference": row.reference,
        "reason": row.reason, "scopes": row.scopes, "status": status,
        "requested_at": row.requested_at, "expires_at": row.expires_at}


@router.get("")
async def homes(ctx: AuthContext = Depends(get_auth_context), customer_id: uuid.UUID | None = None):
    async with get_session() as session:
        query = select(IoTHome).where(IoTHome.tenant_id == ctx.tenant_id)
        if not await staff_access(ctx):
            query = query.where(IoTHome.owner_user_id == ctx.user_id)
        if customer_id:
            query = query.where(IoTHome.customer_id == customer_id)
        return [public_home(home, ctx) for home in (await session.scalars(query.order_by(IoTHome.name).limit(200))).all()]


@router.post("", status_code=201)
async def provision(body: Provision, ctx: AuthContext = Depends(require_tier("admin"))):
    async with get_session() as session:
        # Cross-service IDs are deliberately checked in their tenant, not trusted UUIDs.
        customer = await session.scalar(text("SELECT id FROM customers WHERE id=:id AND tenant_id=:tenant"),
            {"id": str(body.customer_id), "tenant": str(ctx.tenant_id)})
        owner = await session.scalar(text("SELECT id FROM users WHERE id=:id AND tenant_id=:tenant AND is_active=true"),
            {"id": str(body.owner_user_id), "tenant": str(ctx.tenant_id)})
        if not customer or not owner:
            raise HTTPException(422, "Select a customer and active user from this tenant")
        other_customer = await session.scalar(select(IoTHome.id).where(IoTHome.tenant_id == ctx.tenant_id,
            IoTHome.owner_user_id == body.owner_user_id, IoTHome.customer_id != body.customer_id).limit(1))
        if other_customer:
            raise HTTPException(409, "This login is already linked to another customer")
        from services.iot.households import bind_customer_account
        await bind_customer_account(session, ctx, body.owner_user_id, body.customer_id)
        home = IoTHome(tenant_id=ctx.tenant_id, customer_id=body.customer_id,
            owner_user_id=body.owner_user_id, name=body.name.strip())
        if not home.name:
            raise HTTPException(422, "Home name is required")
        session.add(home)
        await session.flush()
        audit(session, home, ctx.user_id, "provisioned")
        return public_home(home, ctx)


@router.post("/{home_id}/gateway")
async def assign_gateway(home_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context)):
    from services.iot.access import effective_access
    from services.iot.models import IoTGatewayBinding
    from services.iot.managed_gateway import enabled, PUBLIC_URL
    from sqlalchemy.exc import IntegrityError
    await effective_access(ctx)
    if not ctx.is_platform_admin:
        raise HTTPException(403, "Only the Platform Owner can assign the pilot gateway")
    if not enabled():
        raise HTTPException(409, "Local gateway is not prepared on this deployment")
    async with get_session() as session:
        home = await home_for(session, ctx, home_id)
        binding = await session.get(IoTGatewayBinding, "local", with_for_update=True)
        if binding and (binding.home_id != home.id or binding.tenant_id != ctx.tenant_id):
            raise HTTPException(409, "The pilot gateway is already assigned to another home")
        if home.ha_token_encrypted and not home.managed_gateway_key:
            raise HTTPException(409, "Disconnect the existing Home Assistant before assigning the gateway")
        if not binding:
            session.add(IoTGatewayBinding(gateway_key="local", tenant_id=ctx.tenant_id, home_id=home.id))
            try:
                await session.flush()
            except IntegrityError as exc:
                raise HTTPException(409, "The pilot gateway was assigned concurrently; refresh and try again") from exc
        home.managed_gateway_key, home.ha_url = "local", PUBLIC_URL
        audit(session, home, ctx.user_id, "gateway_assigned")
        return {"ok": True, "onboarding_url": PUBLIC_URL}


@router.post("/{home_id}/connection")
async def connect(home_id: uuid.UUID, body: Connection, ctx: AuthContext = Depends(get_auth_context)):
    async with get_session() as session:
        home = await home_for(session, ctx, home_id, owner_only=True)
        from services.iot.managed_gateway import target_for, PUBLIC_URL
        if target_for(home):
            if body.ha_url.rstrip("/") != PUBLIC_URL:
                raise HTTPException(422, "Use the prepared gateway URL for this home")
            url = PUBLIC_URL
        else:
            url = await _checked_url(body.ha_url)
        try:
            token = encrypt_token(body.ha_token)
        except Exception as exc:
            raise ha_http_error(exc) from exc
        home.ha_url, home.ha_token_encrypted = url, token
        audit(session, home, ctx.user_id, "connection_updated")
        return await sync_home(session, home, ctx.user_id)


@router.delete("/{home_id}/connection")
async def disconnect(home_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context)):
    async with get_session() as session:
        home = await home_for(session, ctx, home_id, owner_only=True)
        home.ha_token_encrypted, home.ha_url, home.status = None, None, "disconnected"
        requests = (await session.scalars(select(IoTHomeSupport).where(IoTHomeSupport.home_id == home.id,
            IoTHomeSupport.tenant_id == ctx.tenant_id, IoTHomeSupport.status.in_(["pending", "approved"])))).all()
        for request in requests:
            request.status = "revoked"
        audit(session, home, ctx.user_id, "disconnected")
        return {"ok": True}


@router.post("/{home_id}/sync")
async def sync(home_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context)):
    async with get_session() as session:
        home = await home_for(session, ctx, home_id, "diagnostics")
        return await sync_home(session, home, ctx.user_id)


@router.get("/{home_id}/devices")
async def devices(home_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context)):
    async with get_session() as session:
        home = await home_for(session, ctx, home_id, "diagnostics")
        audit(session, home, ctx.user_id, "devices_viewed")
        rows = (await session.scalars(select(IoTHomeEntity).where(IoTHomeEntity.home_id == home.id,
            IoTHomeEntity.tenant_id == ctx.tenant_id).order_by(IoTHomeEntity.name).limit(1000))).all()
        # No camera URLs, access tokens, IPs or full unfiltered HA attributes.
        return [{"id": str(row.id), "name": row.name, "domain": row.domain, "room": row.room, "state": row.state,
            "attributes": row.attributes, "observed_at": row.observed_at} for row in rows]


@router.get("/{home_id}/readings")
async def readings(home_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context),
                   limit: int = Query(100, ge=1, le=500)):
    async with get_session() as session:
        home = await home_for(session, ctx, home_id, "diagnostics")
        audit(session, home, ctx.user_id, "readings_viewed")
        rows = (await session.scalars(select(IoTHomeReading).where(IoTHomeReading.home_id == home.id,
            IoTHomeReading.tenant_id == ctx.tenant_id).order_by(IoTHomeReading.observed_at.desc()).limit(limit))).all()
        return [{"entity": row.entity_id, "state": row.state, "unit": row.unit, "observed_at": row.observed_at} for row in rows]


async def entity_for(session, home, entity_id):
    entity = await session.scalar(select(IoTHomeEntity).where(IoTHomeEntity.id == entity_id,
        IoTHomeEntity.home_id == home.id, IoTHomeEntity.tenant_id == home.tenant_id))
    if not entity:
        raise HTTPException(404, "Device not found")
    return entity


@router.post("/{home_id}/devices/{entity_id}/control")
async def control(home_id: uuid.UUID, entity_id: uuid.UUID, body: Command,
                  ctx: AuthContext = Depends(get_auth_context)):
    async with get_session() as session:
        home = await home_for(session, ctx, home_id, "control")
        entity = await entity_for(session, home, entity_id)
        # Pilot deliberately has no lock, alarm, camera-restart or unrestricted service execution.
        tier = required_tier_for_control(entity.domain, body.service, body.service_data)
        if tier == "admin" or entity.domain not in {"light", "switch", "fan", "climate", "scene", "cover"}:
            raise HTTPException(403, "This device action requires the customer's Home Assistant dashboard")
        if entity.domain == "cover":
            if body.service not in {"open_cover", "close_cover", "stop_cover", "set_cover_position"}:
                raise HTTPException(422, "Unsupported blind control")
            position = body.service_data.get("position")
            if body.service == "set_cover_position" and (isinstance(position, bool) or not isinstance(position, (int, float)) or not 0 <= position <= 100):
                raise HTTPException(422, "Blind position must be between 0 and 100")
        client = await client_for(home)
        try:
            await client.call_service(entity.domain, body.service, body.service_data,
                target={"entity_id": entity.entity_id})
            audit(session, home, ctx.user_id, "command_sent", device=str(entity.id), service=body.service)
            # Confirm the targeted entity without a full-home registry sync. Failure
            # here does not mark an already-sent command as failed or retry it.
            try:
                from services.iot.households import ATTRIBUTES
                import math
                raw = await client.get_state(entity.entity_id)
                state = raw.get("state")
                if raw.get("entity_id") == entity.entity_id and isinstance(state, str) and len(state) <= 512:
                    attrs = raw.get("attributes", {})
                    attrs = attrs if isinstance(attrs, dict) else {}
                    entity.state, entity.observed_at = state, now()
                    entity.attributes = {key: value for key, value in attrs.items() if key in ATTRIBUTES
                        and isinstance(value, (str, int, float, bool)) and len(str(value)) <= 64
                        and (not isinstance(value, float) or math.isfinite(value))}
            except Exception:
                pass
        except Exception as exc:
            # Commit a sanitized failure audit, rather than rolling it back with a raised exception.
            audit(session, home, ctx.user_id, "command_failed", device=str(entity.id), service=body.service)
            return {"ok": False, "message": "Home Assistant did not confirm the command. Refresh before retrying."}
        finally:
            await client.aclose()
        return {"ok": True, "message": "Command sent; refresh to verify the device state"}


@router.get("/{home_id}/devices/{entity_id}/snapshot")
async def snapshot(home_id: uuid.UUID, entity_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context)):
    async with get_session() as session:
        home = await home_for(session, ctx, home_id, "camera")
        entity = await entity_for(session, home, entity_id)
        if entity.domain != "camera":
            raise HTTPException(422, "Select a camera")
        client = await client_for(home)
        try:
            content = await client.get_camera_image(entity.entity_id)
        except Exception as exc:
            raise ha_http_error(exc) from exc
        finally:
            await client.aclose()
        if len(content) > 10 * 1024 * 1024:
            raise HTTPException(502, "Camera image too large")
        mime = "image/jpeg" if content.startswith(b"\xff\xd8\xff") else "image/png" if content.startswith(b"\x89PNG\r\n\x1a\n") else None
        if not mime:
            raise HTTPException(502, "Camera returned an unsupported image")
        audit(session, home, ctx.user_id, "camera_viewed", device=str(entity.id))
        return Response(content, media_type=mime, headers={"Cache-Control": "no-store, private", "X-Content-Type-Options": "nosniff"})


@router.get("/{home_id}/support")
async def support(home_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context)):
    async with get_session() as session:
        home = await home_for(session, ctx, home_id)
        query = select(IoTHomeSupport).where(IoTHomeSupport.home_id == home.id, IoTHomeSupport.tenant_id == ctx.tenant_id)
        if home.owner_user_id != ctx.user_id:
            query = query.where(IoTHomeSupport.staff_user_id == ctx.user_id)
        result = []
        for row in (await session.scalars(query.order_by(IoTHomeSupport.requested_at.desc()).limit(50))).all():
            item = support_read(row)
            item["staff_name"] = await session.scalar(text("SELECT email FROM users WHERE id=:id AND tenant_id=:tenant"),
                {"id": str(row.staff_user_id), "tenant": str(ctx.tenant_id)}) or "Support staff"
            result.append(item)
        return result


@router.post("/{home_id}/support", status_code=201)
async def request_support(home_id: uuid.UUID, body: SupportRequest, ctx: AuthContext = Depends(get_auth_context)):
    if not await staff_access(ctx):
        raise HTTPException(403, "An IoT support role is required")
    async with get_session() as session:
        home = await home_for(session, ctx, home_id)
        if home.owner_user_id == ctx.user_id:
            raise HTTPException(422, "Support requests must come from another staff member")
        pending = await session.scalar(select(IoTHomeSupport).where(IoTHomeSupport.home_id == home.id,
            IoTHomeSupport.tenant_id == ctx.tenant_id, IoTHomeSupport.staff_user_id == ctx.user_id,
            IoTHomeSupport.status == "pending", IoTHomeSupport.expires_at > now()))
        if pending:
            raise HTTPException(409, "A support request is already awaiting customer approval")
        row = IoTHomeSupport(tenant_id=ctx.tenant_id, home_id=home.id, staff_user_id=ctx.user_id,
            reference=body.reference.strip(), reason=body.reason.strip(), scopes=sorted(set(body.scopes)),
            requested_at=now(), expires_at=now() + timedelta(hours=24))
        session.add(row)
        await session.flush()
        audit(session, home, ctx.user_id, "support_requested", request=str(row.id))
        await emit(session, home, "iot.support.requested", str(row.id))
        await support_notice(session, home, home.owner_user_id, "HomeDome: a staff member is requesting your approval")
        return support_read(row)


@router.post("/{home_id}/support/{request_id}/approve")
async def approve(home_id: uuid.UUID, request_id: uuid.UUID, body: Approval,
                  ctx: AuthContext = Depends(get_auth_context)):
    async with get_session() as session:
        home = await home_for(session, ctx, home_id, owner_only=True)
        row = await session.scalar(select(IoTHomeSupport).where(IoTHomeSupport.id == request_id,
            IoTHomeSupport.home_id == home.id, IoTHomeSupport.tenant_id == ctx.tenant_id))
        if not row:
            raise HTTPException(404, "Support request not found")
        if support_read(row)["status"] != "pending" or row.staff_user_id == ctx.user_id:
            raise HTTPException(409, "This request cannot be approved")
        if not set(body.scopes).issubset(row.scopes):
            raise HTTPException(422, "Choose only permissions requested by this staff member")
        row.scopes, row.status, row.expires_at = sorted(set(body.scopes)), "approved", now() + timedelta(minutes=body.minutes)
        audit(session, home, ctx.user_id, "support_approved", request=str(row.id), scopes=row.scopes)
        await support_notice(session, home, row.staff_user_id, "HomeDome: customer-approved support access is ready")
        return support_read(row)


@router.delete("/{home_id}/support/{request_id}")
async def revoke(home_id: uuid.UUID, request_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context)):
    async with get_session() as session:
        home = await home_for(session, ctx, home_id)
        row = await session.scalar(select(IoTHomeSupport).where(IoTHomeSupport.id == request_id,
            IoTHomeSupport.home_id == home.id, IoTHomeSupport.tenant_id == ctx.tenant_id))
        if not row or home.owner_user_id != ctx.user_id and row.staff_user_id != ctx.user_id:
            raise HTTPException(404, "Support request not found")
        row.status = "revoked"
        audit(session, home, ctx.user_id, "support_revoked", request=str(row.id))
        return {"ok": True}


@router.get("/{home_id}/audit")
async def history(home_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context)):
    async with get_session() as session:
        home = await home_for(session, ctx, home_id, owner_only=True)
        rows = (await session.scalars(select(IoTHomeAudit).where(IoTHomeAudit.home_id == home.id,
            IoTHomeAudit.tenant_id == ctx.tenant_id).order_by(IoTHomeAudit.created_at.desc()).limit(100))).all()
        return [{"action": row.action, "actor_user_id": row.actor_user_id, "details": row.details,
            "created_at": row.created_at} for row in rows]
