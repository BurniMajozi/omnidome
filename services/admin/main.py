from __future__ import annotations

import hashlib
import logging
import os
import secrets
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from services.common.auth import AuthContext, get_auth_context
from services.common.entitlements import EntitlementGuard
from services.common.rbac import has_permission, has_role
from services.common.db import get_async_session

logger = logging.getLogger("admin")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())

app = FastAPI(title="OmniDome Admin Service", version="1.0.0")
guard = EntitlementGuard(module_name="admin")


@app.on_event("startup")
async def startup() -> None:
    guard.ensure_startup()


@app.middleware("http")
async def entitlement_middleware(request, call_next):
    return await guard.middleware(request, call_next)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class TenantCreate(BaseModel):
    name: str
    domain: Optional[str] = None
    subdomain: Optional[str] = None
    settings: Optional[Dict[str, Any]] = None
    branding: Optional[Dict[str, Any]] = None
    active: Optional[bool] = True
    org_code: Optional[str] = None
    tier: Optional[str] = None
    vat_number: Optional[str] = None
    status: Optional[str] = None
    admin_user_id: Optional[uuid.UUID] = None


class TenantUpdate(BaseModel):
    name: Optional[str] = None
    domain: Optional[str] = None
    subdomain: Optional[str] = None
    settings: Optional[Dict[str, Any]] = None
    branding: Optional[Dict[str, Any]] = None
    active: Optional[bool] = None
    org_code: Optional[str] = None
    tier: Optional[str] = None
    vat_number: Optional[str] = None
    status: Optional[str] = None


class RoleCreate(BaseModel):
    name: str
    description: Optional[str] = None
    permissions: List[str] = Field(default_factory=list)


class RoleUpdate(BaseModel):
    permissions: List[str] = Field(default_factory=list)


class RoleAssign(BaseModel):
    role_id: uuid.UUID


class ModuleEntitlementUpdate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    module_name: str = Field(..., alias="name")
    enabled: bool
    config: Optional[Dict[str, Any]] = None


class ModulesUpdateRequest(BaseModel):
    modules: List[ModuleEntitlementUpdate]


class UserCreate(BaseModel):
    email: str
    name: Optional[str] = None
    role_id: Optional[uuid.UUID] = None
    password: Optional[str] = None
    is_active: bool = True


class UserUpdate(BaseModel):
    email: Optional[str] = None
    name: Optional[str] = None
    is_active: Optional[bool] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _domain_from_payload(payload: TenantCreate | TenantUpdate) -> Optional[str]:
    return payload.domain or payload.subdomain


def _status_from_payload(payload: TenantCreate | TenantUpdate) -> Optional[str]:
    if payload.status:
        return payload.status
    if payload.active is None:
        return None
    return "ACTIVE" if payload.active else "SUSPENDED"


def _tenant_response(row: Dict[str, Any]) -> Dict[str, Any]:
    tenant = dict(row)
    if "domain" not in tenant or tenant.get("domain") is None:
        tenant["domain"] = tenant.get("subdomain")
    if "active" not in tenant or tenant.get("active") is None:
        tenant["active"] = str(tenant.get("status") or "").upper() == "ACTIVE"
    return tenant


async def _log_audit(
    session: AsyncSession,
    ctx: AuthContext,
    action: str,
    resource_type: str,
    resource_id: Optional[uuid.UUID] = None,
    tenant_id: Optional[uuid.UUID] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    try:
        await session.execute(
            text(
                """
                insert into audit_logs (tenant_id, user_id, action, resource_type, resource_id, metadata)
                values (:tenant_id, :user_id, :action, :resource_type, :resource_id, :metadata)
                """
            ),
            {
                "tenant_id": str(tenant_id or ctx.tenant_id) if (tenant_id or ctx.tenant_id) else None,
                "user_id": str(ctx.user_id),
                "action": action,
                "resource_type": resource_type,
                "resource_id": str(resource_id) if resource_id else None,
                "metadata": metadata,
            },
        )
    except Exception as exc:
        logger.warning("Failed to write audit log: %s", exc)


async def _require_platform_admin(ctx: AuthContext, session: AsyncSession) -> None:
    if ctx.is_platform_admin:
        return
    if await has_permission(ctx, "platform.admin", session):
        return
    if await has_role(ctx, "platform_admin", session):
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Platform admin required")


async def _require_tenant_admin(ctx: AuthContext, session: AsyncSession) -> None:
    if ctx.is_platform_admin:
        return
    if await has_permission(ctx, "org.admin", session):
        return
    if await has_permission(ctx, "org.manage", session):
        return
    if await has_role(ctx, "org_admin", session):
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant admin required")


async def _ensure_tenant_scope(ctx: AuthContext, tenant_id: uuid.UUID, session: AsyncSession) -> None:
    if ctx.is_platform_admin:
        return
    if tenant_id != ctx.tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cross-tenant access denied")
    await _require_tenant_admin(ctx, session)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@app.get("/health")
async def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat() + "Z"}


# ---------------------------------------------------------------------------
# Tenant Management
# ---------------------------------------------------------------------------


@app.post("/tenants", status_code=status.HTTP_201_CREATED)
async def create_tenant(
    payload: TenantCreate,
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_async_session),
):
    await _require_platform_admin(ctx, session)
    domain = _domain_from_payload(payload)
    if not domain:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="domain is required")

    tenant_id = uuid.uuid4()
    status_value = _status_from_payload(payload) or "ACTIVE"
    active_flag = payload.active if payload.active is not None else status_value.upper() == "ACTIVE"
    if payload.status is not None:
        active_flag = status_value.upper() == "ACTIVE"

    result = await session.execute(
        text(
            """
            insert into tenants (
                id, name, subdomain, domain, org_code, tier, vat_number, status, active, settings, branding
            )
            values (
                :id, :name, :subdomain, :domain, :org_code, :tier, :vat_number, :status, :active, :settings, :branding
            )
            returning id, name, subdomain, domain, settings, branding, active,
                      org_code, tier, vat_number, status, created_at, updated_at
            """
        ),
        {
            "id": str(tenant_id),
            "name": payload.name,
            "subdomain": domain,
            "domain": domain,
            "org_code": payload.org_code,
            "tier": payload.tier,
            "vat_number": payload.vat_number,
            "status": status_value,
            "active": active_flag,
            "settings": payload.settings,
            "branding": payload.branding,
        },
    )
    row = result.mappings().one()

    if os.getenv("ADMIN_AUTO_PROVISION", "true").lower() == "true":
        try:
            await session.execute(
                text("select provision_tenant(:tenant_id, :admin_user_id)"),
                {
                    "tenant_id": str(tenant_id),
                    "admin_user_id": str(payload.admin_user_id) if payload.admin_user_id else None,
                },
            )
        except Exception as exc:
            logger.warning("Provision tenant failed: %s", exc)

    await _log_audit(
        session,
        ctx,
        action="tenant.create",
        resource_type="tenant",
        resource_id=tenant_id,
        tenant_id=tenant_id,
        metadata={"domain": domain, "settings": payload.settings, "branding": payload.branding},
    )

    return _tenant_response(row)


@app.get("/tenants")
async def list_tenants(
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_async_session),
):
    await _require_platform_admin(ctx, session)
    result = await session.execute(
        text(
            """
            select id, name, subdomain, domain, settings, branding, active,
                   org_code, tier, vat_number, status, created_at, updated_at
            from tenants
            order by created_at desc
            """
        )
    )
    rows = result.mappings().all()
    return [_tenant_response(row) for row in rows]


@app.get("/tenants/{tenant_id}")
async def get_tenant(
    tenant_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_async_session),
):
    await _ensure_tenant_scope(ctx, tenant_id, session)
    result = await session.execute(
        text(
            """
            select id, name, subdomain, domain, settings, branding, active,
                   org_code, tier, vat_number, status, created_at, updated_at
            from tenants
            where id = :tenant_id
            """
        ),
        {"tenant_id": str(tenant_id)},
    )
    row = result.mappings().one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    return _tenant_response(row)


@app.put("/tenants/{tenant_id}")
async def update_tenant(
    tenant_id: uuid.UUID,
    payload: TenantUpdate,
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_async_session),
):
    await _ensure_tenant_scope(ctx, tenant_id, session)
    updates: Dict[str, Any] = {}
    domain = _domain_from_payload(payload)
    if domain:
        updates["subdomain"] = domain
        updates["domain"] = domain
    if payload.name is not None:
        updates["name"] = payload.name
    if payload.settings is not None:
        updates["settings"] = payload.settings
    if payload.branding is not None:
        updates["branding"] = payload.branding
    if payload.org_code is not None:
        updates["org_code"] = payload.org_code
    if payload.tier is not None:
        updates["tier"] = payload.tier
    if payload.vat_number is not None:
        updates["vat_number"] = payload.vat_number
    status_value = _status_from_payload(payload)
    if status_value is not None:
        updates["status"] = status_value
        updates["active"] = status_value.upper() == "ACTIVE"
    elif payload.active is not None:
        updates["active"] = payload.active

    if not updates:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No updates provided")

    set_clause = ", ".join([f"{key} = :{key}" for key in updates.keys()])
    updates["tenant_id"] = str(tenant_id)

    result = await session.execute(
        text(
            f"""
            update tenants
            set {set_clause}, updated_at = now()
            where id = :tenant_id
            returning id, name, subdomain, domain, settings, branding, active,
                      org_code, tier, vat_number, status, created_at, updated_at
            """
        ),
        updates,
    )
    row = result.mappings().one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    await _log_audit(
        session,
        ctx,
        action="tenant.update",
        resource_type="tenant",
        resource_id=tenant_id,
        tenant_id=tenant_id,
        metadata={"updates": updates, "settings": payload.settings, "branding": payload.branding},
    )
    return _tenant_response(row)


@app.delete("/tenants/{tenant_id}")
async def delete_tenant(
    tenant_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_async_session),
):
    await _require_platform_admin(ctx, session)
    result = await session.execute(
        text(
            """
            update tenants
            set status = 'CLOSED', active = false, updated_at = now()
            where id = :tenant_id
            returning id, name, subdomain, domain, settings, branding, active,
                      org_code, tier, vat_number, status, created_at, updated_at
            """
        ),
        {"tenant_id": str(tenant_id)},
    )
    row = result.mappings().one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    await _log_audit(
        session,
        ctx,
        action="tenant.delete",
        resource_type="tenant",
        resource_id=tenant_id,
        tenant_id=tenant_id,
    )
    return _tenant_response(row)


# ---------------------------------------------------------------------------
# Role & Permission Management
# ---------------------------------------------------------------------------


@app.post("/roles", status_code=status.HTTP_201_CREATED)
async def create_role(
    payload: RoleCreate,
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_async_session),
):
    await _require_tenant_admin(ctx, session)
    role_id = uuid.uuid4()

    result = await session.execute(
        text(
            """
            insert into roles (id, tenant_id, name, scope, description, is_system)
            values (:id, :tenant_id, :name, 'TENANT', :description, false)
            returning id, name, description, scope, is_system, created_at
            """
        ),
        {
            "id": str(role_id),
            "tenant_id": str(ctx.tenant_id),
            "name": payload.name,
            "description": payload.description,
        },
    )
    row = result.mappings().one()

    if payload.permissions:
        perm_stmt = text("select id from permissions where key in :keys").bindparams(
            bindparam("keys", expanding=True)
        )
        perm_rows = await session.execute(perm_stmt, {"keys": payload.permissions})
        perm_ids = [item[0] for item in perm_rows.fetchall()]
        if perm_ids:
            await session.execute(
                text("insert into role_permissions (role_id, permission_id) values (:role_id, :permission_id)"),
                [{"role_id": str(role_id), "permission_id": str(pid)} for pid in perm_ids],
            )

    await _log_audit(
        session,
        ctx,
        action="role.create",
        resource_type="role",
        resource_id=role_id,
        metadata={"permissions": payload.permissions},
    )
    return row


@app.get("/roles")
async def list_roles(
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_async_session),
):
    await _require_tenant_admin(ctx, session)
    result = await session.execute(
        text(
            """
            select id, name, description, scope, is_system, created_at
            from roles
            where tenant_id = :tenant_id
            order by created_at desc
            """
        ),
        {"tenant_id": str(ctx.tenant_id)},
    )
    return result.mappings().all()


@app.put("/roles/{role_id}")
async def update_role_permissions(
    role_id: uuid.UUID,
    payload: RoleUpdate,
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_async_session),
):
    await _require_tenant_admin(ctx, session)

    role_row = await session.execute(
        text("select id from roles where id = :role_id and tenant_id = :tenant_id"),
        {"role_id": str(role_id), "tenant_id": str(ctx.tenant_id)},
    )
    if not role_row.first():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")

    await session.execute(
        text("delete from role_permissions where role_id = :role_id"),
        {"role_id": str(role_id)},
    )

    if payload.permissions:
        perm_stmt = text("select id from permissions where key in :keys").bindparams(
            bindparam("keys", expanding=True)
        )
        perm_rows = await session.execute(perm_stmt, {"keys": payload.permissions})
        perm_ids = [item[0] for item in perm_rows.fetchall()]
        if perm_ids:
            await session.execute(
                text("insert into role_permissions (role_id, permission_id) values (:role_id, :permission_id)"),
                [{"role_id": str(role_id), "permission_id": str(pid)} for pid in perm_ids],
            )

    await _log_audit(
        session,
        ctx,
        action="role.update",
        resource_type="role",
        resource_id=role_id,
        metadata={"permissions": payload.permissions},
    )
    return {"role_id": role_id, "permissions": payload.permissions}


@app.post("/users/{user_id}/roles")
async def assign_role(
    user_id: uuid.UUID,
    payload: RoleAssign,
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_async_session),
):
    await _require_tenant_admin(ctx, session)

    role_row = await session.execute(
        text("select id from roles where id = :role_id and tenant_id = :tenant_id"),
        {"role_id": str(payload.role_id), "tenant_id": str(ctx.tenant_id)},
    )
    if not role_row.first():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")

    user_row = await session.execute(
        text("select id from users where id = :user_id and tenant_id = :tenant_id"),
        {"user_id": str(user_id), "tenant_id": str(ctx.tenant_id)},
    )
    if not user_row.first():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    await session.execute(
        text(
            """
            insert into user_roles (user_id, role_id, tenant_id, assigned_by)
            values (:user_id, :role_id, :tenant_id, :assigned_by)
            on conflict (user_id, role_id, tenant_id) do nothing
            """
        ),
        {
            "user_id": str(user_id),
            "role_id": str(payload.role_id),
            "tenant_id": str(ctx.tenant_id),
            "assigned_by": str(ctx.user_id),
        },
    )

    await _log_audit(
        session,
        ctx,
        action="role.assign",
        resource_type="user",
        resource_id=user_id,
        metadata={"role_id": str(payload.role_id)},
    )

    return {"user_id": user_id, "role_id": payload.role_id, "tenant_id": ctx.tenant_id}


@app.delete("/users/{user_id}/roles/{role_id}")
async def remove_role(
    user_id: uuid.UUID,
    role_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_async_session),
):
    await _require_tenant_admin(ctx, session)
    await session.execute(
        text(
            """
            delete from user_roles
            where user_id = :user_id and role_id = :role_id and tenant_id = :tenant_id
            """
        ),
        {"user_id": str(user_id), "role_id": str(role_id), "tenant_id": str(ctx.tenant_id)},
    )
    await _log_audit(
        session,
        ctx,
        action="role.remove",
        resource_type="user",
        resource_id=user_id,
        metadata={"role_id": str(role_id)},
    )
    return {"user_id": user_id, "role_id": role_id, "tenant_id": ctx.tenant_id, "status": "removed"}


# ---------------------------------------------------------------------------
# Module Entitlements
# ---------------------------------------------------------------------------


@app.get("/modules")
async def list_modules(
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_async_session),
):
    await _require_platform_admin(ctx, session)
    result = await session.execute(
        text("select key, name, description, is_core, created_at from modules order by key")
    )
    rows = result.mappings().all()
    response = []
    for row in rows:
        item = dict(row)
        item["license_required"] = not bool(item.get("is_core"))
        response.append(item)
    return response


@app.get("/tenants/{tenant_id}/modules")
async def list_tenant_modules(
    tenant_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_async_session),
):
    await _ensure_tenant_scope(ctx, tenant_id, session)
    result = await session.execute(
        text(
            """
            select m.key as module_name,
                   m.name,
                   m.is_core,
                   tm.status,
                   tm.config
            from modules m
            left join tenant_modules tm
              on tm.module_id = m.id and tm.tenant_id = :tenant_id
            order by m.key
            """
        ),
        {"tenant_id": str(tenant_id)},
    )
    rows = result.mappings().all()
    response = []
    for row in rows:
        status_value = row.get("status")
        enabled = False
        if status_value:
            enabled = str(status_value).upper() in {"ENABLED", "TRIAL"}
        response.append(
            {
                "module_name": row.get("module_name"),
                "name": row.get("name"),
                "enabled": enabled,
                "config": row.get("config"),
                "license_required": not bool(row.get("is_core")),
            }
        )
    return response


@app.put("/tenants/{tenant_id}/modules")
async def update_tenant_modules(
    tenant_id: uuid.UUID,
    payload: ModulesUpdateRequest,
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_async_session),
):
    await _ensure_tenant_scope(ctx, tenant_id, session)

    for module in payload.modules:
        module_key = module.module_name
        module_row = await session.execute(
            text("select id from modules where key = :key"),
            {"key": module_key},
        )
        module_id_row = module_row.fetchone()
        if not module_id_row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Module not found: {module_key}")

        status_value = "ENABLED" if module.enabled else "DISABLED"
        await session.execute(
            text(
                """
                insert into tenant_modules (tenant_id, module_id, status, enabled_by, enabled_at, disabled_at, config)
                values (:tenant_id, :module_id, :status, :enabled_by, now(), :disabled_at, :config)
                on conflict (tenant_id, module_id)
                do update set
                    status = excluded.status,
                    enabled_by = excluded.enabled_by,
                    enabled_at = excluded.enabled_at,
                    disabled_at = excluded.disabled_at,
                    config = excluded.config
                """
            ),
            {
                "tenant_id": str(tenant_id),
                "module_id": str(module_id_row[0]),
                "status": status_value,
                "enabled_by": str(ctx.user_id),
                "disabled_at": None if module.enabled else datetime.utcnow(),
                "config": module.config,
            },
        )

    await _log_audit(
        session,
        ctx,
        action="module.update",
        resource_type="tenant",
        resource_id=tenant_id,
        tenant_id=tenant_id,
        metadata={"modules": [module.model_dump() for module in payload.modules]},
    )

    return {"tenant_id": tenant_id, "updated": len(payload.modules)}


# ---------------------------------------------------------------------------
# User Management
# ---------------------------------------------------------------------------


@app.get("/users")
async def list_users(
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_async_session),
):
    await _require_tenant_admin(ctx, session)
    result = await session.execute(
        text(
            """
            select id, email, full_name, is_active, created_at
            from users
            where tenant_id = :tenant_id
            order by created_at desc
            """
        ),
        {"tenant_id": str(ctx.tenant_id)},
    )
    rows = result.mappings().all()
    return [
        {
            "id": row.get("id"),
            "email": row.get("email"),
            "name": row.get("full_name"),
            "is_active": row.get("is_active"),
            "created_at": row.get("created_at"),
        }
        for row in rows
    ]


@app.post("/users", status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreate,
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_async_session),
):
    await _require_tenant_admin(ctx, session)
    user_id = uuid.uuid4()
    if payload.password:
        hashed_password = hashlib.sha256(payload.password.encode("utf-8")).hexdigest()
    else:
        hashed_password = os.getenv("DEFAULT_USER_PASSWORD_HASH") or secrets.token_hex(16)

    result = await session.execute(
        text(
            """
            insert into users (id, tenant_id, email, full_name, hashed_password, is_active)
            values (:id, :tenant_id, :email, :full_name, :hashed_password, :is_active)
            returning id, email, full_name, is_active, created_at
            """
        ),
        {
            "id": str(user_id),
            "tenant_id": str(ctx.tenant_id),
            "email": payload.email,
            "full_name": payload.name,
            "hashed_password": hashed_password,
            "is_active": payload.is_active,
        },
    )
    row = result.mappings().one()

    if payload.role_id:
        await session.execute(
            text(
                """
                insert into user_roles (user_id, role_id, tenant_id, assigned_by)
                values (:user_id, :role_id, :tenant_id, :assigned_by)
                on conflict (user_id, role_id, tenant_id) do nothing
                """
            ),
            {
                "user_id": str(user_id),
                "role_id": str(payload.role_id),
                "tenant_id": str(ctx.tenant_id),
                "assigned_by": str(ctx.user_id),
            },
        )

    await _log_audit(
        session,
        ctx,
        action="user.create",
        resource_type="user",
        resource_id=user_id,
        metadata={"role_id": str(payload.role_id) if payload.role_id else None},
    )

    return {
        "id": row.get("id"),
        "email": row.get("email"),
        "name": row.get("full_name"),
        "is_active": row.get("is_active"),
        "created_at": row.get("created_at"),
    }


@app.put("/users/{user_id}")
async def update_user(
    user_id: uuid.UUID,
    payload: UserUpdate,
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_async_session),
):
    await _require_tenant_admin(ctx, session)
    updates: Dict[str, Any] = {}
    if payload.email is not None:
        updates["email"] = payload.email
    if payload.name is not None:
        updates["full_name"] = payload.name
    if payload.is_active is not None:
        updates["is_active"] = payload.is_active

    if not updates:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No updates provided")

    set_clause = ", ".join([f"{key} = :{key}" for key in updates.keys()])
    updates["user_id"] = str(user_id)
    updates["tenant_id"] = str(ctx.tenant_id)

    result = await session.execute(
        text(
            f"""
            update users
            set {set_clause}
            where id = :user_id and tenant_id = :tenant_id
            returning id, email, full_name, is_active, created_at
            """
        ),
        updates,
    )
    row = result.mappings().one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    await _log_audit(
        session,
        ctx,
        action="user.update",
        resource_type="user",
        resource_id=user_id,
        metadata={"updates": updates},
    )

    return {
        "id": row.get("id"),
        "email": row.get("email"),
        "name": row.get("full_name"),
        "is_active": row.get("is_active"),
        "created_at": row.get("created_at"),
    }


@app.delete("/users/{user_id}")
async def deactivate_user(
    user_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_async_session),
):
    await _require_tenant_admin(ctx, session)
    result = await session.execute(
        text(
            """
            update users
            set is_active = false
            where id = :user_id and tenant_id = :tenant_id
            returning id, email, full_name, is_active, created_at
            """
        ),
        {"user_id": str(user_id), "tenant_id": str(ctx.tenant_id)},
    )
    row = result.mappings().one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    await _log_audit(
        session,
        ctx,
        action="user.deactivate",
        resource_type="user",
        resource_id=user_id,
    )

    return {
        "id": row.get("id"),
        "email": row.get("email"),
        "name": row.get("full_name"),
        "is_active": row.get("is_active"),
        "created_at": row.get("created_at"),
    }


# ---------------------------------------------------------------------------
# Audit Log
# ---------------------------------------------------------------------------


@app.get("/audit-log")
async def audit_log(
    tenant_id: Optional[uuid.UUID] = Query(None),
    user_id: Optional[uuid.UUID] = Query(None),
    action: Optional[str] = Query(None),
    resource_type: Optional[str] = Query(None),
    since: Optional[datetime] = Query(None),
    until: Optional[datetime] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_async_session),
):
    if tenant_id and (tenant_id != ctx.tenant_id):
        await _require_platform_admin(ctx, session)
    elif not ctx.is_platform_admin:
        tenant_id = ctx.tenant_id

    clauses = []
    params: Dict[str, Any] = {"limit": limit}
    if tenant_id:
        clauses.append("tenant_id = :tenant_id")
        params["tenant_id"] = str(tenant_id)
    if user_id:
        clauses.append("user_id = :user_id")
        params["user_id"] = str(user_id)
    if action:
        clauses.append("action = :action")
        params["action"] = action
    if resource_type:
        clauses.append("resource_type = :resource_type")
        params["resource_type"] = resource_type
    if since:
        clauses.append("created_at >= :since")
        params["since"] = since
    if until:
        clauses.append("created_at <= :until")
        params["until"] = until

    where_clause = " where " + " and ".join(clauses) if clauses else ""
    result = await session.execute(
        text(
            f"""
            select id, tenant_id, user_id, action, resource_type, resource_id, metadata, created_at
            from audit_logs
            {where_clause}
            order by created_at desc
            limit :limit
            """
        ),
        params,
    )
    return result.mappings().all()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8013)
