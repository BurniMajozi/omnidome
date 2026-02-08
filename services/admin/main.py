from datetime import datetime
from typing import Any, Dict, List, Optional
import uuid

from fastapi import Depends, FastAPI, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import bindparam, text

from services.common.auth import AuthContext, get_auth_context
from services.common.access import has_permission
from services.common.db import get_engine
from services.common.entitlements import EntitlementGuard


app = FastAPI(title="CoreConnect Admin Service", version="0.1.0")
guard = EntitlementGuard(module_id="")


@app.on_event("startup")
async def startup() -> None:
    guard.ensure_startup()


@app.middleware("http")
async def entitlement_middleware(request, call_next):
    return await guard.middleware(request, call_next)


class TenantCreate(BaseModel):
    name: str
    subdomain: str
    org_code: Optional[str] = None
    tier: str = "FREE"
    vat_number: Optional[str] = None
    status: str = "ACTIVE"
    admin_user_id: Optional[uuid.UUID] = None


class TenantUpdate(BaseModel):
    name: Optional[str] = None
    subdomain: Optional[str] = None
    org_code: Optional[str] = None
    tier: Optional[str] = None
    vat_number: Optional[str] = None
    status: Optional[str] = None


class ModuleEntitlementUpdate(BaseModel):
    status: str = Field(..., description="ENABLED, DISABLED, TRIAL")
    config: Optional[Dict[str, Any]] = None


class RoleCreate(BaseModel):
    name: str
    description: Optional[str] = None
    permissions: Optional[List[str]] = None


class RolePermissionsUpdate(BaseModel):
    permissions: List[str]


def _require_platform_admin(ctx: AuthContext) -> None:
    if ctx.is_platform_admin or has_permission(ctx, "platform.admin"):
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Platform admin required")


def _require_org_admin(ctx: AuthContext, tenant_id: uuid.UUID) -> None:
    if ctx.is_platform_admin or has_permission(ctx, "platform.admin"):
        return
    if ctx.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cross-tenant access denied")
    if not (has_permission(ctx, "org.admin") or has_permission(ctx, "org.manage")):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Org admin required")


def _sanitize_tenant_permissions(ctx: AuthContext, permissions: List[str]) -> List[str]:
    if ctx.is_platform_admin or has_permission(ctx, "platform.admin"):
        return permissions
    disallowed = [key for key in permissions if key.startswith("platform.") or key in {"module.manage", "org.manage"}]
    if disallowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Disallowed permissions for tenant role: {', '.join(disallowed)}",
        )
    return permissions


def _ensure_role_belongs_to_tenant(conn, tenant_id: uuid.UUID, role_id: uuid.UUID) -> Dict[str, Any]:
    row = conn.execute(
        text("select id, tenant_id, scope, name from roles where id = :role_id"),
        {"role_id": str(role_id)},
    ).mappings().one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
    if row["scope"] != "TENANT":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Platform role assignment not allowed here")
    if str(row["tenant_id"]) != str(tenant_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Role does not belong to tenant")
    return row


@app.get("/health")
async def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat() + "Z"}


# --- Platform Admin Endpoints ---
@app.get("/tenants")
async def list_tenants(ctx: AuthContext = Depends(get_auth_context)):
    _require_platform_admin(ctx)
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                select id, name, subdomain, org_code, tier, vat_number, status, created_at, updated_at
                from tenants
                order by created_at desc
                """
            )
        ).mappings().all()
    return rows


@app.post("/tenants", status_code=status.HTTP_201_CREATED)
async def create_tenant(payload: TenantCreate, ctx: AuthContext = Depends(get_auth_context)):
    _require_platform_admin(ctx)
    engine = get_engine()
    tenant_id = uuid.uuid4()
    with engine.begin() as conn:
        row = conn.execute(
            text(
                """
                insert into tenants (id, name, subdomain, org_code, tier, vat_number, status)
                values (:id, :name, :subdomain, :org_code, :tier, :vat_number, :status)
                returning id, name, subdomain, org_code, tier, vat_number, status, created_at, updated_at
                """
            ),
            {
                "id": str(tenant_id),
                "name": payload.name,
                "subdomain": payload.subdomain,
                "org_code": payload.org_code,
                "tier": payload.tier,
                "vat_number": payload.vat_number,
                "status": payload.status,
            },
        ).mappings().one()
        conn.execute(
            text("select provision_tenant(:tenant_id, :admin_user_id)"),
            {"tenant_id": str(tenant_id), "admin_user_id": str(payload.admin_user_id) if payload.admin_user_id else None},
        )
    return row


@app.patch("/tenants/{tenant_id}")
async def update_tenant(
    tenant_id: uuid.UUID, payload: TenantUpdate, ctx: AuthContext = Depends(get_auth_context)
):
    _require_platform_admin(ctx)
    updates = {k: v for k, v in payload.dict().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No updates provided")
    set_clause = ", ".join([f"{key} = :{key}" for key in updates.keys()])
    updates["tenant_id"] = str(tenant_id)
    engine = get_engine()
    with engine.begin() as conn:
        row = conn.execute(
            text(
                f"""
                update tenants
                set {set_clause}, updated_at = now()
                where id = :tenant_id
                returning id, name, subdomain, org_code, tier, vat_number, status, created_at, updated_at
                """
            ),
            updates,
        ).mappings().one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    return row


@app.get("/modules")
async def list_modules(ctx: AuthContext = Depends(get_auth_context)):
    _require_platform_admin(ctx)
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text("select id, key, name, description, is_core, created_at from modules order by key")
        ).mappings().all()
    return rows


@app.get("/tenants/{tenant_id}/modules")
async def list_tenant_modules(tenant_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context)):
    _require_platform_admin(ctx)
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                select m.key, m.name, tm.status, tm.enabled_at, tm.disabled_at, tm.config
                from tenant_modules tm
                join modules m on m.id = tm.module_id
                where tm.tenant_id = :tenant_id
                order by m.key
                """
            ),
            {"tenant_id": str(tenant_id)},
        ).mappings().all()
    return rows


@app.put("/tenants/{tenant_id}/modules/{module_key}")
async def set_tenant_module(
    tenant_id: uuid.UUID,
    module_key: str,
    payload: ModuleEntitlementUpdate,
    ctx: AuthContext = Depends(get_auth_context),
):
    _require_platform_admin(ctx)
    if not (has_permission(ctx, "module.manage") or has_permission(ctx, "platform.admin") or ctx.is_platform_admin):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Module management permission required")
    status_value = payload.status.upper()
    if status_value not in {"ENABLED", "DISABLED", "TRIAL"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid module status")
    disabled_at = datetime.utcnow() if status_value == "DISABLED" else None
    engine = get_engine()
    with engine.begin() as conn:
        module_row = conn.execute(
            text("select id from modules where key = :key"), {"key": module_key}
        ).fetchone()
        if not module_row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Module not found")
        conn.execute(
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
                "module_id": str(module_row[0]),
                "status": status_value,
                "enabled_by": str(ctx.user_id),
                "disabled_at": disabled_at,
                "config": payload.config,
            },
        )
    return {"tenant_id": tenant_id, "module": module_key, "status": status_value}


@app.get("/permissions")
async def list_permissions(ctx: AuthContext = Depends(get_auth_context)):
    if not (ctx.is_platform_admin or has_permission(ctx, "platform.admin") or has_permission(ctx, "org.admin")):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin permission required")
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text("select key, description from permissions order by key")
        ).mappings().all()
    return rows


# --- Org Admin Endpoints ---
@app.get("/tenants/{tenant_id}/roles")
async def list_roles(tenant_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context)):
    _require_org_admin(ctx, tenant_id)
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                select id, name, description, scope, is_system, created_at
                from roles
                where tenant_id = :tenant_id
                order by created_at desc
                """
            ),
            {"tenant_id": str(tenant_id)},
        ).mappings().all()
    return rows


@app.post("/tenants/{tenant_id}/roles", status_code=status.HTTP_201_CREATED)
async def create_role(
    tenant_id: uuid.UUID, payload: RoleCreate, ctx: AuthContext = Depends(get_auth_context)
):
    _require_org_admin(ctx, tenant_id)
    engine = get_engine()
    role_id = uuid.uuid4()
    with engine.begin() as conn:
        row = conn.execute(
            text(
                """
                insert into roles (id, tenant_id, name, scope, description, is_system)
                values (:id, :tenant_id, :name, 'TENANT', :description, false)
                returning id, name, description, scope, is_system, created_at
                """
            ),
            {
                "id": str(role_id),
                "tenant_id": str(tenant_id),
                "name": payload.name,
                "description": payload.description,
            },
        ).mappings().one()
        if payload.permissions:
            permissions = _sanitize_tenant_permissions(ctx, payload.permissions)
            perm_stmt = text("select id from permissions where key in :keys").bindparams(
                bindparam("keys", expanding=True)
            )
            perm_rows = conn.execute(perm_stmt, {"keys": permissions}).fetchall()
            perm_ids = [row[0] for row in perm_rows]
            if perm_ids:
                conn.execute(
                    text("insert into role_permissions (role_id, permission_id) values (:role_id, :permission_id)"),
                    [{"role_id": str(role_id), "permission_id": str(pid)} for pid in perm_ids],
                )
    return row


@app.put("/tenants/{tenant_id}/roles/{role_id}/permissions")
async def set_role_permissions(
    tenant_id: uuid.UUID,
    role_id: uuid.UUID,
    payload: RolePermissionsUpdate,
    ctx: AuthContext = Depends(get_auth_context),
):
    _require_org_admin(ctx, tenant_id)
    engine = get_engine()
    with engine.begin() as conn:
        _ensure_role_belongs_to_tenant(conn, tenant_id, role_id)
        conn.execute(text("delete from role_permissions where role_id = :role_id"), {"role_id": str(role_id)})
        if payload.permissions:
            permissions = _sanitize_tenant_permissions(ctx, payload.permissions)
            perm_stmt = text("select id from permissions where key in :keys").bindparams(
                bindparam("keys", expanding=True)
            )
            perm_rows = conn.execute(perm_stmt, {"keys": permissions}).fetchall()
            perm_ids = [row[0] for row in perm_rows]
            if perm_ids:
                conn.execute(
                    text("insert into role_permissions (role_id, permission_id) values (:role_id, :permission_id)"),
                    [{"role_id": str(role_id), "permission_id": str(pid)} for pid in perm_ids],
                )
    return {"role_id": role_id, "permissions": payload.permissions}


@app.post("/tenants/{tenant_id}/users/{user_id}/roles/{role_id}")
async def assign_role(
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    role_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    _require_org_admin(ctx, tenant_id)
    engine = get_engine()
    with engine.begin() as conn:
        _ensure_role_belongs_to_tenant(conn, tenant_id, role_id)
        user = conn.execute(
            text("select id from users where id = :user_id and tenant_id = :tenant_id"),
            {"user_id": str(user_id), "tenant_id": str(tenant_id)},
        ).fetchone()
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found in tenant")
        conn.execute(
            text(
                """
                insert into user_roles (user_id, role_id, tenant_id, assigned_by)
                values (:user_id, :role_id, :tenant_id, :assigned_by)
                on conflict (user_id, role_id, tenant_id) do nothing
                """
            ),
            {
                "user_id": str(user_id),
                "role_id": str(role_id),
                "tenant_id": str(tenant_id),
                "assigned_by": str(ctx.user_id),
            },
        )
    return {"user_id": user_id, "role_id": role_id, "tenant_id": tenant_id}


@app.delete("/tenants/{tenant_id}/users/{user_id}/roles/{role_id}")
async def remove_role(
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    role_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    _require_org_admin(ctx, tenant_id)
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                delete from user_roles
                where user_id = :user_id and role_id = :role_id and tenant_id = :tenant_id
                """
            ),
            {"user_id": str(user_id), "role_id": str(role_id), "tenant_id": str(tenant_id)},
        )
    return {"user_id": user_id, "role_id": role_id, "tenant_id": tenant_id, "status": "removed"}


@app.get("/tenants/{tenant_id}/users/{user_id}/roles")
async def list_user_roles(
    tenant_id: uuid.UUID, user_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context)
):
    _require_org_admin(ctx, tenant_id)
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                select r.id, r.name, r.description, r.scope
                from user_roles ur
                join roles r on r.id = ur.role_id
                where ur.user_id = :user_id and ur.tenant_id = :tenant_id
                """
            ),
            {"user_id": str(user_id), "tenant_id": str(tenant_id)},
        ).mappings().all()
    return rows


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8013)
