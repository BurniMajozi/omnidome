"""Role gates for the IoT service (same model as services/sales/access.py).

Roles come from the RBAC tables (AUTH_ENFORCE_RBAC, default on; an unreadable RBAC table fails
closed) or, with enforcement off, from the signed identity headers.

    viewer    any authenticated tenant member: every GET (devices, state, events, sensors, ...)
    operator  manager tier and up: control NON-critical domains with an allow-listed service,
              sync, activate scenes, manage rooms, post events, enable/disable alerts
    admin     owner / admin tier: control SECURITY domains (lock, alarm_control_panel, siren,
              camera), free-form services, create/update/delete devices, integrations,
              automations, scenes and alert definitions

IOT_ENFORCE_ROLES=false switches the gates off (local development only).
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Callable, Dict, Optional

from fastapi import Depends, HTTPException, status

from services.common import rbac
from services.common.auth import AuthContext, get_auth_context

logger = logging.getLogger("iot.access")

ADMIN_ROLES = frozenset({"platform_admin", "owner", "org_admin", "admin", "tenant_admin", "super_admin", "iot_admin"})
OPERATOR_ROLES = ADMIN_ROLES | {"manager", "iot_operator", "iot_manager", "operator"}
ADMIN_PERMS = frozenset({"iot.admin"})
OPERATOR_PERMS = ADMIN_PERMS | {"iot.operate", "iot.manage"}

TIERS = {
    "admin": (ADMIN_ROLES, ADMIN_PERMS),
    "operator": (OPERATOR_ROLES, OPERATOR_PERMS),
}

# Home Assistant domains whose services can open a door, disarm a house or expose a camera.
SECURITY_DOMAINS = frozenset({"lock", "alarm_control_panel", "siren", "camera"})
OPERATOR_DOMAINS = frozenset({
    "light", "switch", "climate", "cover", "fan", "media_player", "remote", "scene",
    "input_boolean", "humidifier", "vacuum", "water_heater",
})
OPERATOR_SERVICES = frozenset({
    "turn_on", "turn_off", "toggle", "set_temperature", "set_hvac_mode", "set_preset_mode",
    "set_fan_mode", "set_humidity", "open_cover", "close_cover", "stop_cover", "set_cover_position",
    "set_percentage", "increase_speed", "decrease_speed", "oscillate", "volume_set", "volume_up",
    "volume_down", "volume_mute", "media_play", "media_pause", "media_stop", "select_source",
    "start", "pause", "return_to_base",
})
# service_data keys an operator may send (anything else, or any key for admins that is a
# targeting key, is refused).
OPERATOR_DATA_KEYS = frozenset({
    "brightness", "brightness_pct", "brightness_step", "brightness_step_pct", "color_temp",
    "color_temp_kelvin", "kelvin", "rgb_color", "hs_color", "xy_color", "color_name", "transition",
    "effect", "flash", "temperature", "target_temp_high", "target_temp_low", "hvac_mode",
    "preset_mode", "fan_mode", "humidity", "position", "tilt_position", "percentage", "speed",
    "oscillating", "volume_level", "is_volume_muted", "source",
})
# Keys that would retarget the call at other entities and so bypass the per-device check.
FORBIDDEN_DATA_KEYS = frozenset({"entity_id", "device_id", "area_id", "floor_id", "label_id", "target"})
_SERVICE_RE = re.compile(r"^[a-z_]+$")


def roles_enforced() -> bool:
    return os.getenv("IOT_ENFORCE_ROLES", "true").strip().lower() not in {"0", "false", "no", "off"}


async def effective_access(auth: AuthContext) -> tuple[set, set]:
    """(roles, permissions), lower-cased. Fails closed when RBAC is enforced but unreadable."""
    if not auth.rbac_loaded:
        try:
            from services.iot.database import get_session
            async with get_session() as db:
                await rbac._load_rbac(auth, db)
        except Exception as exc:  # noqa: BLE001
            logger.warning("RBAC lookup failed for IoT authorization: %s", type(exc).__name__)
            if rbac._enforce_rbac():
                return set(), set()
    return {r.lower() for r in auth.roles or []}, {p.lower() for p in auth.permissions or []}


async def has_tier(auth: AuthContext, tier: str) -> bool:
    if tier == "viewer" or not roles_enforced() or auth.is_platform_admin:
        return True
    roles, perms = TIERS[tier]
    have_roles, have_perms = await effective_access(auth)
    return bool((have_roles & roles) or (have_perms & perms))


async def require(auth: AuthContext, tier: str) -> None:
    if not await has_tier(auth, tier):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail=f"This action needs an IoT {tier} role")


def require_tier(tier: str) -> Callable:
    """FastAPI dependency: `ctx: AuthContext = Depends(require_tier("admin"))`."""
    if tier not in TIERS:
        raise ValueError(f"unknown tier {tier!r}")

    async def dependency(auth: AuthContext = Depends(get_auth_context)) -> AuthContext:
        await require(auth, tier)
        return auth

    dependency.__name__ = f"require_iot_{tier}"
    return dependency


def required_tier_for_control(domain: str, service: str, service_data: Optional[Dict[str, Any]]) -> str:
    """Tier a control call needs ("operator" or "admin"). Raises 422 for malformed input.

    The domain is the device's own (from the database), never from the request body.
    """
    if not _SERVICE_RE.fullmatch(service or ""):
        raise HTTPException(status_code=422, detail="service must match ^[a-z_]+$")
    data = service_data or {}
    if not isinstance(data, dict):
        raise HTTPException(status_code=422, detail="service_data must be an object")
    bad = sorted(k for k in data if not isinstance(k, str) or k.lower() in FORBIDDEN_DATA_KEYS)
    if bad:
        raise HTTPException(status_code=422, detail="service_data may not retarget the call (entity_id/device_id/area_id/target)")
    if domain in SECURITY_DOMAINS or domain not in OPERATOR_DOMAINS:
        return "admin"
    if service not in OPERATOR_SERVICES:
        return "admin"
    if any(k not in OPERATOR_DATA_KEYS for k in data):
        return "admin"
    return "operator"
