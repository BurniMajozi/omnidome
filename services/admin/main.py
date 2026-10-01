from __future__ import annotations

import asyncio
import bcrypt
import json
import logging
import os
import re
import secrets
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from services.common.auth import AuthContext, get_auth_context
from services.common.entitlements import EntitlementGuard, EntitlementState
from services.common.middleware import configure_production
from services.common.rbac import has_permission, has_role
from services.common.db import get_async_session
from services.common.rate_limiter import RateLimiter, identity_key, internal_key_exempt
from services.common.db import get_async_engine, run_with_db_retry
from services.admin import iam, migrations, supabase_sync
from services.admin.iam import (
    actor_info,
    apply_roles,
    check_can_grant,
    check_can_manage_target,
    deactivate_member,
    ensure_tenant_scope as _ensure_tenant_scope,
    guard_last,
    lock_tenant,
    member_roles,
    reactivate_member,
    record_seat_event,
    require_platform_admin as _require_platform_admin,
    require_seat,
    require_tenant_admin as _require_tenant_admin,
    resolve_roles,
)

logger = logging.getLogger("admin")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())

app = FastAPI(title="OmniDome Admin Service", version="1.0.0")
app.include_router(iam.router)
_SEAT_READ_RE = re.compile(r"^/(tenants/[0-9a-fA-F-]{36}/seats|platform/seat-usage)$")


class AdminGuard(EntitlementGuard):
    """Lets another service (billing) read seat data with only the shared x-internal-key."""

    async def _check_tenant_module(self, tenant_id):
        # The admin service IS the tenant-IAM platform surface; there is no `admin` row in the
        # module catalog, so gating on tenant_modules would 403 every non-platform admin.
        # Authorisation is done per endpoint (tenant admin / platform admin / rank guardrails).
        return EntitlementState(enabled=True)

    async def middleware(self, request, call_next):
        if request.method == "GET" and _SEAT_READ_RE.match(request.url.path) and iam.internal_key_ok(request):
            return await call_next(request)
        return await super().middleware(request, call_next)


guard = AdminGuard(module_name="admin", public_paths={"/internal/users/by-email", "/invites/accept"})

configure_production(app)

# Rate limiter for auth-sensitive endpoints (10 req/min per IP)
_auth_rate_limiter = RateLimiter(max_requests=10, window_seconds=60, key_func=identity_key)

# Global rate limiter middleware (100 req/min per IP)
_global_rate_limiter = RateLimiter(max_requests=100, window_seconds=60, key_func=identity_key)


def limiter_exempt(request: Request) -> bool:
    """/internal/* is service-to-service (the web proxy looks every active session up every ~5s, all
    from one container IP). A request carrying the valid INTERNAL_SERVICE_KEY skips the global bucket so
    identity enforcement cannot be starved by load. Without the key the per-IP limit still applies
    (key brute force stays throttled)."""
    return internal_key_exempt(request, "/internal/")


@app.middleware("http")
async def global_rate_limit_middleware(request: Request, call_next):
    if not limiter_exempt(request):
        await _global_rate_limiter.check(request)
    return await call_next(request)


@app.on_event("startup")
async def startup() -> None:
    guard.ensure_startup()
    if os.getenv("ADMIN_RUN_MIGRATIONS", "true").lower() == "true":
        # advisory-locked + idempotent: safe with several workers, safe to restart
        await run_with_db_retry(lambda: migrations.run_migrations(get_async_engine()), logger=logger)
    if os.getenv("ADMIN_SYNC_RETRY", "true").lower() == "true":
        app.state.sync_task = asyncio.create_task(supabase_sync.retry_loop())


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
    seat_limit: Optional[int] = Field(None, ge=1, le=100000)
    seat_price: Optional[Decimal] = Field(None, ge=0)
    owner_email: Optional[str] = Field(None, max_length=254)
    send_owner_invite_email: bool = True


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
    email: str = Field(..., min_length=3, max_length=254)
    name: Optional[str] = None
    role_id: Optional[uuid.UUID] = None
    password: Optional[str] = Field(None, min_length=8, max_length=128)
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
    """Mandatory audit: runs in the caller's transaction and RAISES on failure, so a change
    that cannot be audited is rolled back and the request fails."""
    await iam.audit(session, ctx, action, resource_type, resource_id, tenant_id, metadata)


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
    request: Request,
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_async_session),
):
    await _auth_rate_limiter.check(request)
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
                :id, :name, :subdomain, :domain, :org_code, :tier, :vat_number, :status, :active, CAST(:settings AS jsonb), CAST(:branding AS jsonb)
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
            "settings": json.dumps(payload.settings) if payload.settings is not None else None,
            "branding": json.dumps(payload.branding) if payload.branding is not None else None,
        },
    )
    row = result.mappings().one()

    if os.getenv("ADMIN_AUTO_PROVISION", "true").lower() == "true":
        # provision_tenant is part of the tenant: if it fails the whole request rolls back
        # (a tenant without roles cannot be invited into).
        await session.execute(
            text("select provision_tenant(:tenant_id, :admin_user_id)"),
            {
                "tenant_id": str(tenant_id),
                "admin_user_id": str(payload.admin_user_id) if payload.admin_user_id else None,
            },
        )
    conn = await session.connection()
    await migrations.ensure_tenant_roles(conn, tenant_id)
    seat_limit = payload.seat_limit if payload.seat_limit is not None else migrations.DEFAULT_SEAT_LIMIT
    await session.execute(
        text("update tenants set seat_limit = :l, seat_price = :p where id = :t"),
        {"l": seat_limit, "p": payload.seat_price, "t": str(tenant_id)},
    )

    owner_invite = None
    if payload.owner_email:
        actor = await actor_info(ctx, session)
        inv = await iam.create_invite_row(session, ctx, actor, tenant_id, payload.owner_email, ["owner"])
        owner_invite = inv

    await _log_audit(
        session,
        ctx,
        action="tenant.create",
        resource_type="tenant",
        resource_id=tenant_id,
        tenant_id=tenant_id,
        metadata={"domain": domain, "seat_limit": seat_limit, "owner_email": payload.owner_email},
    )
    await session.commit()

    response = _tenant_response(row)
    response["seat_limit"] = seat_limit
    response["seat_price"] = str(payload.seat_price) if payload.seat_price is not None else None
    if owner_invite:
        delivery = await iam.deliver_invite(
            owner_invite["invite_id"], owner_invite["email"], owner_invite["token"], payload.send_owner_invite_email
        )
        response["owner_invite"] = {"invite_id": str(owner_invite["invite_id"]), "email": owner_invite["email"], **delivery}
    return response


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
        updates["settings"] = json.dumps(payload.settings)
    if payload.branding is not None:
        updates["branding"] = json.dumps(payload.branding)
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
    # commercial / lifecycle fields belong to the platform, not the tenant admin
    if not ctx.is_platform_admin and {"tier", "status", "active", "org_code"} & set(updates):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only a platform admin may change tier, status or org_code")

    json_cols = {"settings", "branding"}
    set_clause = ", ".join(
        [f"{key} = CAST(:{key} AS jsonb)" if key in json_cols else f"{key} = :{key}" for key in updates.keys()]
    )
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
        metadata={"updates": sorted(k for k in updates if k != "tenant_id")},
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


async def _guard_permissions(ctx: AuthContext, permissions: List[str]) -> None:
    """Kept for callers: custom roles never carry platform.* / org.* / wildcard permissions."""
    iam.check_custom_permissions(permissions, [], True)


async def _set_role_permissions(session: AsyncSession, role_id: uuid.UUID, permissions: List[str]) -> None:
    if not permissions:
        return
    perm_stmt = text("select id from permissions where key in :keys").bindparams(bindparam("keys", expanding=True))
    perm_rows = await session.execute(perm_stmt, {"keys": sorted(set(permissions))})
    perm_ids = [item[0] for item in perm_rows.fetchall()]
    if perm_ids:
        await session.execute(
            text("insert into role_permissions (role_id, permission_id) values (:role_id, :permission_id)"),
            [{"role_id": str(role_id), "permission_id": str(pid)} for pid in perm_ids],
        )


async def _load_custom_role(session: AsyncSession, ctx: AuthContext, role_id: uuid.UUID, actor) -> Dict[str, Any]:
    """Fetch a tenant role for edit/delete: system roles are immutable (409); a non-platform actor may
    only touch custom roles within its own rank band."""
    row = (
        await session.execute(
            text("select id, name, role_rank, is_system from roles where id = :r and tenant_id = :t FOR UPDATE"),
            {"r": str(role_id), "t": str(ctx.tenant_id)},
        )
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
    if row["is_system"] or str(row["name"]).lower() in iam.SYSTEM_ROLE_NAMES:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="System roles cannot be modified")
    if not actor.platform and int(row["role_rank"]) > iam.custom_role_rank(actor):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot edit a role above your own rank")
    return dict(row)


@app.post("/roles", status_code=status.HTTP_201_CREATED)
async def create_role(
    payload: RoleCreate,
    request: Request,
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_async_session),
):
    await _auth_rate_limiter.check(request)
    await _require_tenant_admin(ctx, session)
    if payload.name.strip().lower() in iam.SYSTEM_ROLE_NAMES:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Reserved role name")
    actor = await actor_info(ctx, session)  # also loads ctx.permissions
    iam.check_custom_permissions(payload.permissions, ctx.permissions, actor.platform)
    rank = iam.custom_role_rank(actor)
    role_id = uuid.uuid4()

    result = await session.execute(
        text(
            """
            insert into roles (id, tenant_id, name, scope, description, is_system, role_rank)
            values (:id, :tenant_id, :name, 'TENANT', :description, false, :rank)
            returning id, name, description, scope, is_system, created_at
            """
        ),
        {
            "id": str(role_id),
            "tenant_id": str(ctx.tenant_id),
            "name": payload.name,
            "description": payload.description,
            "rank": rank,
        },
    )
    row = result.mappings().one()
    await _set_role_permissions(session, role_id, payload.permissions)
    # same transaction as the insert: if the audit row cannot be written the role is rolled back
    await _log_audit(
        session, ctx, action="role.create", resource_type="role", resource_id=role_id,
        metadata={"name": payload.name, "permissions": sorted(set(payload.permissions)), "role_rank": rank},
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


@app.get("/roles/{role_id}")
async def get_role(
    role_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_async_session),
):
    await _require_tenant_admin(ctx, session)
    result = await session.execute(
        text("select id, name, description, scope, is_system, created_at from roles where id = :role_id and tenant_id = :tenant_id"),
        {"role_id": str(role_id), "tenant_id": str(ctx.tenant_id)},
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
    return row


@app.delete("/roles/{role_id}")
async def delete_role(
    role_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_async_session),
):
    await _require_tenant_admin(ctx, session)
    actor = await actor_info(ctx, session)
    await lock_tenant(session, ctx.tenant_id)
    role = await _load_custom_role(session, ctx, role_id, actor)
    holders = [
        r[0]
        for r in (
            await session.execute(
                text("select distinct user_id from user_roles where role_id = :r and tenant_id = :t"),
                {"r": str(role_id), "t": str(ctx.tenant_id)},
            )
        ).fetchall()
    ]
    for uid in holders:
        names = await _current_role_names(session, ctx.tenant_id, uid)
        await guard_last(session, ctx.tenant_id, uid, names, [n for n in names if n != role["name"]])
    await session.execute(text("delete from user_roles where role_id = :r and tenant_id = :t"), {"r": str(role_id), "t": str(ctx.tenant_id)})
    await session.execute(text("delete from role_permissions where role_id = :r"), {"r": str(role_id)})
    await session.execute(text("delete from roles where id = :r and tenant_id = :t and is_system = false"), {"r": str(role_id), "t": str(ctx.tenant_id)})
    await _log_audit(
        session, ctx, action="role.delete", resource_type="role", resource_id=role_id,
        metadata={"name": role["name"], "affected_users": [str(u) for u in holders]},
    )
    await session.commit()
    sync = await supabase_sync.sync_users(holders, revoke=True) if holders else {}
    return {"status": "deleted", "id": str(role_id), "affected_users": [str(u) for u in holders], "supabase_sync": sync}


@app.put("/roles/{role_id}")
async def update_role_permissions(
    role_id: uuid.UUID,
    payload: RoleUpdate,
    request: Request,
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_async_session),
):
    await _auth_rate_limiter.check(request)
    await _require_tenant_admin(ctx, session)
    actor = await actor_info(ctx, session)
    role = await _load_custom_role(session, ctx, role_id, actor)
    iam.check_custom_permissions(payload.permissions, ctx.permissions, actor.platform)

    await session.execute(text("delete from role_permissions where role_id = :role_id"), {"role_id": str(role_id)})
    await _set_role_permissions(session, role_id, payload.permissions)
    await _log_audit(
        session, ctx, action="role.update", resource_type="role", resource_id=role_id,
        metadata={"name": role["name"], "permissions": sorted(set(payload.permissions))},
    )
    return {"role_id": role_id, "permissions": payload.permissions}


async def _current_role_names(session, tenant_id, user_id) -> List[str]:
    return sorted(r["name"] for r in await member_roles(session, tenant_id, user_id) if r["scope"] == "TENANT")


@app.post("/users/{user_id}/roles")
async def assign_role(
    user_id: uuid.UUID,
    payload: RoleAssign,
    request: Request,
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_async_session),
):
    await _auth_rate_limiter.check(request)
    await _require_tenant_admin(ctx, session)
    actor = await actor_info(ctx, session)

    role_row = await session.execute(
        text("select name from roles where id = :role_id and tenant_id = :tenant_id"),
        {"role_id": str(payload.role_id), "tenant_id": str(ctx.tenant_id)},
    )
    found = role_row.first()
    if not found:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")

    await lock_tenant(session, ctx.tenant_id)
    current = await _current_role_names(session, ctx.tenant_id, user_id)
    if found[0] not in current:
        await apply_roles(session, ctx, actor, ctx.tenant_id, user_id, current + [found[0]])

    await _log_audit(
        session,
        ctx,
        action="role.assign",
        resource_type="user",
        resource_id=user_id,
        metadata={"role_id": str(payload.role_id), "role": found[0]},
    )
    await session.commit()
    sync = await supabase_sync.sync_user(user_id, revoke=True)
    return {"user_id": user_id, "role_id": payload.role_id, "tenant_id": ctx.tenant_id, "supabase_sync": sync}


@app.delete("/users/{user_id}/roles/{role_id}")
async def remove_role(
    user_id: uuid.UUID,
    role_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_async_session),
):
    await _require_tenant_admin(ctx, session)
    actor = await actor_info(ctx, session)
    role_row = await session.execute(
        text("select name from roles where id = :r and tenant_id = :t"), {"r": str(role_id), "t": str(ctx.tenant_id)}
    )
    found = role_row.first()
    if not found:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
    await lock_tenant(session, ctx.tenant_id)
    current = await _current_role_names(session, ctx.tenant_id, user_id)
    if found[0] in current:
        await apply_roles(session, ctx, actor, ctx.tenant_id, user_id, [n for n in current if n != found[0]])
    await _log_audit(
        session,
        ctx,
        action="role.remove",
        resource_type="user",
        resource_id=user_id,
        metadata={"role_id": str(role_id), "role": found[0]},
    )
    await session.commit()
    sync = await supabase_sync.sync_user(user_id, revoke=True)
    return {"user_id": user_id, "role_id": role_id, "tenant_id": ctx.tenant_id, "status": "removed", "supabase_sync": sync}


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
    # Enabling modules is an entitlement (paid) decision: platform admins only, never the tenant itself.
    await _require_platform_admin(ctx, session)

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
                "enabled_by": str(ctx.user_id) if (await session.execute(text("select 1 from users where id = :u"), {"u": str(ctx.user_id)})).first() else None,
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


@app.get("/users/{user_id}")
async def get_user(
    user_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_async_session),
):
    await _require_tenant_admin(ctx, session)
    result = await session.execute(
        text("select id, email, full_name, is_active, created_at from users where id = :uid and tenant_id = :tid"),
        {"uid": str(user_id), "tid": str(ctx.tenant_id)},
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return row


@app.get("/internal/users/by-email")
async def internal_get_user_by_email(
    request: Request,
    email: str = Query(...),
    session: AsyncSession = Depends(get_async_session),
):
    """Service-to-service identity bootstrap lookup.

    Used by apps/web's orchestrator proxy to resolve a verified Supabase
    user's email into this platform's {user_id, tenant_id} -- the only join
    key, since no supabase_id column exists on `users`. Gated by a shared
    secret, not get_auth_context, since the caller has no tenant context yet.
    """
    expected = os.getenv("INTERNAL_SERVICE_KEY", "")
    provided = request.headers.get("x-internal-key") or ""
    if not expected or not secrets.compare_digest(provided, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid internal key")

    result = await session.execute(
        text("select id, tenant_id, is_active, is_owner, supabase_synced from users where lower(email) = lower(:email) order by is_active desc, created_at asc, id asc limit 1"),
        {"email": email},
    )
    row = result.mappings().first()
    if not row or not row["tenant_id"]:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    roles = await member_roles(session, row["tenant_id"], row["id"])
    return {
        "user_id": str(row["id"]),
        "tenant_id": str(row["tenant_id"]),
        "roles": sorted({r["name"] for r in roles}),
        "is_active": bool(row["is_active"]),
        "seat_status": "active" if row["is_active"] else "suspended",
        "is_owner": bool(row["is_owner"]),
        "synced": bool(row["supabase_synced"]),
    }


def _user_out(row) -> Dict[str, Any]:
    return {
        "id": row.get("id"),
        "email": row.get("email"),
        "name": row.get("full_name"),
        "is_active": row.get("is_active"),
        "created_at": row.get("created_at"),
    }


@app.post("/users", status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreate,
    request: Request,
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_async_session),
):
    """Direct user creation: PLATFORM ADMIN ONLY (break-glass / provisioning). Tenant admins get 409
    use_invites and must use POST /tenants/{id}/invites. Consumes a seat (the limit applies)."""
    await _auth_rate_limiter.check(request)
    await _require_tenant_admin(ctx, session)
    actor = await actor_info(ctx, session)
    tenant_id = ctx.tenant_id
    if not actor.platform:
        # Pre-provisioning an arbitrary email lets a tenant squat the address (the proxy keys identity on
        # email). Invitees prove ownership of the address by signing in, so tenant admins must invite.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "use_invites",
                "message": "Direct user creation is disabled for tenant admins; invite the person instead",
                "invite_endpoint": f"/tenants/{tenant_id}/invites",
            },
        )
    email = payload.email.strip().lower()
    user_id = uuid.uuid4()
    if payload.password:
        hashed_password = bcrypt.hashpw(payload.password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")
    else:
        hashed_password = os.getenv("DEFAULT_USER_PASSWORD_HASH") or secrets.token_hex(16)

    tenant = await lock_tenant(session, tenant_id)
    if str(tenant["status"]).upper() in {"CLOSED", "SUSPENDED"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Tenant is not active")
    if (await session.execute(text("select 1 from users where lower(email) = :e"), {"e": email})).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already belongs to a tenant")
    if (
        await session.execute(text("select 1 from invites where lower(email) = :e and status = 'pending' and expires_at > now()"), {"e": email})
    ).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A pending invite already exists for this email")
    if payload.is_active:
        await require_seat(session, tenant_id)  # under the tenant lock taken above

    role = None
    if payload.role_id:
        # Only a role of the caller's tenant, and only one the caller is allowed to grant.
        role_row = await session.execute(
            text("select name from roles where id = :role_id and tenant_id = :tenant_id"),
            {"role_id": str(payload.role_id), "tenant_id": str(tenant_id)},
        )
        found = role_row.first()
        if not found:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
        role = (await resolve_roles(session, tenant_id, [found[0]]))[0]
        check_can_grant(actor, [role])

    result = await session.execute(
        text(
            """
            insert into users (id, tenant_id, email, full_name, hashed_password, is_active, is_owner)
            values (:id, :tenant_id, :email, :full_name, :hashed_password, :is_active, :is_owner)
            returning id, email, full_name, is_active, created_at
            """
        ),
        {
            "id": str(user_id),
            "tenant_id": str(tenant_id),
            "email": email,
            "full_name": payload.name,
            "hashed_password": hashed_password,
            "is_active": payload.is_active,
            "is_owner": bool(role and role["name"] == "owner"),
        },
    )
    row = result.mappings().one()

    if role:
        await session.execute(
            text(
                """
                insert into user_roles (user_id, role_id, tenant_id, assigned_by)
                values (:user_id, :role_id, :tenant_id, (select id from users where id = :by))
                on conflict (user_id, role_id, tenant_id) do nothing
                """
            ),
            {"user_id": str(user_id), "role_id": str(role["id"]), "tenant_id": str(tenant_id), "by": str(ctx.user_id)},
        )
    if payload.is_active:
        await record_seat_event(session, tenant_id, user_id, 1, "user_created", ctx.user_id)

    await _log_audit(
        session,
        ctx,
        action="user.create",
        resource_type="user",
        resource_id=user_id,
        metadata={"role_id": str(payload.role_id) if payload.role_id else None, "email": email},
    )
    await session.commit()
    await supabase_sync.sync_user(user_id, revoke=False)
    return _user_out(row)


@app.put("/users/{user_id}")
async def update_user(
    user_id: uuid.UUID,
    payload: UserUpdate,
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_async_session),
):
    await _require_tenant_admin(ctx, session)
    actor = await actor_info(ctx, session)
    if payload.email is None and payload.name is None and payload.is_active is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No updates provided")
    tenant_id = ctx.tenant_id
    if payload.email is not None and not actor.platform:
        # the email is the identity key shared with Supabase; changing it is a platform decision
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only a platform admin may change a user's email")
    if payload.email is not None or payload.name is not None:
        if not (await session.execute(text("select 1 from users where id = :u and tenant_id = :t"), {"u": str(user_id), "t": str(tenant_id)})).first():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        check_can_manage_target(actor, await member_roles(session, tenant_id, user_id))

    # activation state changes go through the seat-aware paths
    changed_state = False
    if payload.is_active is False:
        out = await deactivate_member(session, ctx, actor, tenant_id, user_id)
        changed_state = out["changed"]
    elif payload.is_active is True:
        out = await reactivate_member(session, ctx, actor, tenant_id, user_id)
        changed_state = out["changed"]

    updates: Dict[str, Any] = {}
    if payload.email is not None:
        new_email = payload.email.strip().lower()
        if (await session.execute(text("select 1 from users where lower(email) = :e and id <> :u"), {"e": new_email, "u": str(user_id)})).first():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already belongs to a tenant")
        if (
            await session.execute(text("select 1 from invites where lower(email) = :e and status = 'pending' and expires_at > now()"), {"e": new_email})
        ).first():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A pending invite already exists for this email")
        # Supabase first: the proxy resolves identity by email, so both stores must change together
        client = supabase_sync.get_client()
        if client is None:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Auth provider not configured")
        cur = (await session.execute(text("select email, supabase_user_id from users where id = :u"), {"u": str(user_id)})).mappings().first()
        sid = str(cur["supabase_user_id"] or user_id)
        try:
            try:
                await client.set_email(sid, new_email)
            except supabase_sync.SupabaseError as exc:
                if exc.status not in (404, 422):
                    raise
                found = await client.find_by_email(cur["email"])
                if not found:
                    raise
                await client.set_email(found["id"], new_email)
        except supabase_sync.SupabaseError as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Auth provider rejected the email change ({exc.status})")
        updates["email"] = new_email
    if payload.name is not None:
        updates["full_name"] = payload.name
    if updates:
        set_clause = ", ".join([f"{key} = :{key}" for key in updates.keys()])
        if "email" in updates:
            set_clause += ", supabase_synced = false"
        await session.execute(
            text(f"update users set {set_clause} where id = :user_id and tenant_id = :tenant_id"),
            {**updates, "user_id": str(user_id), "tenant_id": str(tenant_id)},
        )
    result = await session.execute(
        text("select id, email, full_name, is_active, created_at from users where id = :u and tenant_id = :t"),
        {"u": str(user_id), "t": str(tenant_id)},
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
        metadata={"updates": sorted(updates), "is_active": payload.is_active},
    )
    await session.commit()
    if changed_state or "email" in updates:
        await supabase_sync.sync_user(user_id, revoke=payload.is_active is False)
    return _user_out(row)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except (ValueError, TypeError):
        return False


@app.delete("/users/{user_id}")
async def deactivate_user(
    user_id: uuid.UUID,
    request: Request,
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_async_session),
):
    await _auth_rate_limiter.check(request)
    await _require_tenant_admin(ctx, session)
    actor = await actor_info(ctx, session)
    out = await deactivate_member(session, ctx, actor, ctx.tenant_id, user_id)
    row = (
        await session.execute(
            text("select id, email, full_name, is_active, created_at from users where id = :u and tenant_id = :t"),
            {"u": str(user_id), "t": str(ctx.tenant_id)},
        )
    ).mappings().one()
    await session.commit()
    if out["changed"]:
        await supabase_sync.sync_user(user_id, revoke=True)
    return _user_out(row)


# ---------------------------------------------------------------------------
# Commission Tiers
# ---------------------------------------------------------------------------


class CommissionTierCreate(BaseModel):
    tier_name: str = Field(..., max_length=100)
    min_deals: int = Field(0, ge=0)
    max_deals: Optional[int] = Field(None, ge=0)
    rate_percent: Decimal = Field(Decimal("5.00"), ge=0, le=Decimal("100"))
    is_active: bool = True
    sort_order: int = 0


class CommissionTierUpdate(BaseModel):
    tier_name: Optional[str] = Field(None, max_length=100)
    min_deals: Optional[int] = Field(None, ge=0)
    max_deals: Optional[int] = Field(None, ge=0)
    rate_percent: Optional[Decimal] = Field(None, ge=0, le=Decimal("100"))
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None


@app.get("/commission-tiers")
async def list_commission_tiers(
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_async_session),
):
    await _require_tenant_admin(ctx, session)
    result = await session.execute(
        text(
            """
            select id, tenant_id, tier_name, min_deals, max_deals,
                   rate_percent, is_active, sort_order, created_at, updated_at
            from commission_tiers
            where tenant_id = :tid and is_active = true
            order by sort_order asc, min_deals asc
            """
        ),
        {"tid": str(ctx.tenant_id)},
    )
    return result.mappings().all()


@app.post("/commission-tiers")
async def create_commission_tier(
    payload: CommissionTierCreate,
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_async_session),
):
    await _require_tenant_admin(ctx, session)
    tier_id = uuid.uuid4()
    now = datetime.utcnow()
    await session.execute(
        text(
            """
            insert into commission_tiers
                (id, tenant_id, tier_name, min_deals, max_deals, rate_percent, is_active, sort_order, created_at, updated_at)
            values
                (:id, :tid, :name, :min_d, :max_d, :rate, :active, :sort, :now, :now)
            """
        ),
        {
            "id": str(tier_id), "tid": str(ctx.tenant_id),
            "name": payload.tier_name, "min_d": payload.min_deals,
            "max_d": payload.max_deals, "rate": str(payload.rate_percent),
            "active": payload.is_active, "sort": payload.sort_order,
            "now": now,
        },
    )
    await _log_audit(session, ctx, action="commission_tier.create", resource_type="commission_tier", resource_id=tier_id)
    return {"id": str(tier_id), "tier_name": payload.tier_name, "rate_percent": str(payload.rate_percent)}


@app.put("/commission-tiers/{tier_id}")
async def update_commission_tier(
    tier_id: uuid.UUID,
    payload: CommissionTierUpdate,
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_async_session),
):
    await _require_tenant_admin(ctx, session)
    updates: Dict[str, Any] = {}
    if payload.tier_name is not None:
        updates["tier_name"] = payload.tier_name
    if payload.min_deals is not None:
        updates["min_deals"] = payload.min_deals
    if payload.max_deals is not None:
        updates["max_deals"] = payload.max_deals
    if payload.rate_percent is not None:
        updates["rate_percent"] = str(payload.rate_percent)
    if payload.is_active is not None:
        updates["is_active"] = payload.is_active
    if payload.sort_order is not None:
        updates["sort_order"] = payload.sort_order
    if not updates:
        raise HTTPException(status_code=400, detail="No updates provided")
    updates["updated_at"] = datetime.utcnow()
    updates["id"] = str(tier_id)
    updates["tid"] = str(ctx.tenant_id)
    set_clause = ", ".join(f"{k} = :{k}" for k in updates if k not in ("id", "tid"))
    result = await session.execute(
        text(f"update commission_tiers set {set_clause} where id = :id and tenant_id = :tid"),
        updates,
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Tier not found")
    await _log_audit(session, ctx, action="commission_tier.update", resource_type="commission_tier", resource_id=tier_id)
    return {"status": "updated"}


@app.delete("/commission-tiers/{tier_id}")
async def delete_commission_tier(
    tier_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_async_session),
):
    await _require_tenant_admin(ctx, session)
    result = await session.execute(
        text("delete from commission_tiers where id = :id and tenant_id = :tid"),
        {"id": str(tier_id), "tid": str(ctx.tenant_id)},
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Tier not found")
    await _log_audit(session, ctx, action="commission_tier.delete", resource_type="commission_tier", resource_id=tier_id)
    return {"status": "deleted"}


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
        await _require_tenant_admin(ctx, session)
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
