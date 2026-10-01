"""Tenant IAM for the admin service: seats, invites, membership, role guardrails, mandatory audit.

Model (one tenant per email): membership is derived from `users` (tenant_id, is_active, is_owner),
so there is no separate memberships table. seats_used = active users + pending unexpired invites,
always derived, never stored. Every seat-consuming path takes `SELECT ... FOR UPDATE` on the tenant
row so concurrent requests cannot oversubscribe it.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from services.admin import supabase_sync
from services.admin.migrations import ADMIN_CAPABLE_ROLES, DEFAULT_SEAT_LIMIT, ROLE_RANKS, ensure_tenant_roles
from services.common.auth import AuthContext, get_auth_context
from services.common.db import get_async_session
from services.common.rate_limiter import RateLimiter, identity_key
from services.common.rbac import has_permission, has_role

logger = logging.getLogger("admin.iam")
router = APIRouter()

INVITE_TTL = timedelta(days=7)
RESERVED_ROLE_NAMES = {"platform_admin", "owner", "org_admin", "org_user"}
BILLING_STATUSES = {"active", "past_due", "suspended", "cancelled"}
invite_limiter = RateLimiter(max_requests=30, window_seconds=60, key_func=identity_key)
accept_limiter = RateLimiter(max_requests=20, window_seconds=60, key_func=identity_key)


def app_public_url() -> str:
    return os.getenv("APP_PUBLIC_URL", "http://localhost:3000").rstrip("/")


# ---------------------------------------------------------------------------
# Guards (shared with main.py)
# ---------------------------------------------------------------------------


async def require_platform_admin(ctx: AuthContext, session: AsyncSession) -> None:
    if ctx.is_platform_admin:
        return
    if await has_permission(ctx, "platform.admin", session):
        return
    if await has_role(ctx, "platform_admin", session):
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Platform admin required")


async def require_tenant_admin(ctx: AuthContext, session: AsyncSession) -> None:
    if ctx.is_platform_admin:
        return
    if await has_permission(ctx, "org.admin", session):
        return
    if await has_permission(ctx, "org.manage", session):
        return
    if await has_role(ctx, "org_admin", session):
        return
    if await has_role(ctx, "owner", session):
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant admin required")


async def ensure_tenant_scope(ctx: AuthContext, tenant_id: uuid.UUID, session: AsyncSession) -> None:
    """Platform admin: any tenant. Everyone else: only the tenant of the verified x-tenant-id, as an admin."""
    if ctx.is_platform_admin:
        return
    if tenant_id != ctx.tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cross-tenant access denied")
    await require_tenant_admin(ctx, session)


@dataclass
class Actor:
    rank: int
    platform: bool
    owner: bool


async def actor_info(ctx: AuthContext, session: AsyncSession) -> Actor:
    if ctx.is_platform_admin:
        return Actor(rank=ROLE_RANKS["platform_admin"], platform=True, owner=True)
    await has_role(ctx, "_", session)  # forces the RBAC load (ctx.roles from the DB)
    row = (
        await session.execute(
            text(
                """
                SELECT coalesce(max(r.role_rank), 0), coalesce(bool_or(r.name = 'owner'), false)
                FROM user_roles ur JOIN roles r ON r.id = ur.role_id
                WHERE ur.user_id = :u AND (ur.tenant_id = :t OR r.scope = 'PLATFORM')
                """
            ),
            {"u": str(ctx.user_id), "t": str(ctx.tenant_id)},
        )
    ).one()
    rank, owner = int(row[0]), bool(row[1])
    if os.getenv("AUTH_ENFORCE_RBAC", "true").lower() not in {"1", "true", "yes", "on"}:
        rank = max([rank] + [ROLE_RANKS.get(n, 0) for n in ctx.roles])
        owner = owner or "owner" in ctx.roles
    return Actor(rank=rank, platform=False, owner=owner)


# ---------------------------------------------------------------------------
# Mandatory audit (same transaction as the change; failure fails the request)
# ---------------------------------------------------------------------------


async def write_audit(
    session: AsyncSession,
    actor_id: Optional[uuid.UUID],
    action: str,
    resource_type: str,
    resource_id: Optional[uuid.UUID] = None,
    tenant_id: Optional[uuid.UUID] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    meta = dict(metadata or {})
    if actor_id:
        meta.setdefault("actor_id", str(actor_id))
    # user_id has an FK to users: platform admins / accepting users may not have a row yet.
    await session.execute(
        text(
            """
            INSERT INTO audit_logs (tenant_id, user_id, action, resource_type, resource_id, metadata)
            VALUES (:tenant_id, (SELECT id FROM users WHERE id = :uid), :action, :rtype, :rid, CAST(:meta AS jsonb))
            """
        ),
        {
            "tenant_id": str(tenant_id) if tenant_id else None,
            "uid": str(actor_id) if actor_id else None,
            "action": action,
            "rtype": resource_type,
            "rid": str(resource_id) if resource_id else None,
            "meta": json.dumps(meta, default=str),
        },
    )


async def audit(session, ctx: AuthContext, action, resource_type, resource_id=None, tenant_id=None, metadata=None):
    await write_audit(session, ctx.user_id, action, resource_type, resource_id, tenant_id or ctx.tenant_id, metadata)


# ---------------------------------------------------------------------------
# Seats
# ---------------------------------------------------------------------------


def seat_error(used: int, limit: Optional[int]) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"error": "seat_limit_reached", "seats_used": used, "seat_limit": limit},
    )


async def lock_tenant(session: AsyncSession, tenant_id: uuid.UUID) -> Dict[str, Any]:
    row = (
        await session.execute(
            text("SELECT id, name, status, seat_limit, seat_price, billing_status, owner_user_id FROM tenants WHERE id = :t FOR UPDATE"),
            {"t": str(tenant_id)},
        )
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return dict(row)


async def sweep_expired_invites(session: AsyncSession, tenant_id: Optional[uuid.UUID] = None) -> int:
    """Turn pending-but-past-expiry invites into 'expired' and emit the seat_event (-1, at the
    moment they expired) so the ledger always equals seats_used. Atomic via UPDATE ... RETURNING."""
    rows = (
        await session.execute(
            text(
                """
                UPDATE invites SET status = 'expired'
                WHERE status = 'pending' AND expires_at <= now()
                  AND (CAST(:t AS uuid) IS NULL OR tenant_id = CAST(:t AS uuid))
                RETURNING id, tenant_id, expires_at
                """
            ),
            {"t": str(tenant_id) if tenant_id else None},
        )
    ).fetchall()
    for _id, tid, exp in rows:
        await session.execute(
            text(
                """
                INSERT INTO seat_events (tenant_id, user_id, delta, reason, at, active_after, pending_after)
                VALUES (:t, NULL, -1, 'invite_expired', :at,
                    (SELECT count(*) FROM users WHERE tenant_id = :t AND is_active),
                    (SELECT count(*) FROM invites WHERE tenant_id = :t AND status = 'pending' AND expires_at > now()))
                """
            ),
            {"t": str(tid), "at": exp},
        )
    return len(rows)


async def seat_usage(session: AsyncSession, tenant_id: uuid.UUID) -> Dict[str, Any]:
    await sweep_expired_invites(session, tenant_id)
    row = (
        await session.execute(
            text(
                """
                SELECT t.seat_limit, t.seat_price, t.billing_status,
                  (SELECT count(*) FROM users u WHERE u.tenant_id = t.id AND u.is_active) AS active_users,
                  (SELECT count(*) FROM invites i WHERE i.tenant_id = t.id AND i.status = 'pending' AND i.expires_at > now()) AS pending_invites
                FROM tenants t WHERE t.id = :t
                """
            ),
            {"t": str(tenant_id)},
        )
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Tenant not found")
    used = int(row["active_users"]) + int(row["pending_invites"])
    limit = row["seat_limit"]
    return {
        "tenant_id": str(tenant_id),
        "current_seats": used,
        "seat_limit": limit,
        "seat_price": str(row["seat_price"]) if row["seat_price"] is not None else None,
        "billing_status": row["billing_status"],
        "active_users": int(row["active_users"]),
        "pending_invites": int(row["pending_invites"]),
        "seats_used": used,
        "seats_available": None if limit is None else max(limit - used, 0),
    }


async def require_seat(session: AsyncSession, tenant_id: uuid.UUID) -> Dict[str, Any]:
    """Caller must already hold the tenant row lock. 409 if a NEW seat (active + pending) is not free."""
    u = await seat_usage(session, tenant_id)
    if u["seat_limit"] is not None and u["seats_used"] >= u["seat_limit"]:
        raise seat_error(u["seats_used"], u["seat_limit"])
    return u


async def record_seat_event(session, tenant_id, user_id, delta: int, reason: str, actor_id=None) -> None:
    await session.execute(
        text(
            """
            INSERT INTO seat_events (tenant_id, user_id, delta, reason, actor_id, active_after, pending_after)
            VALUES (:t, :u, :d, :r, :a,
                (SELECT count(*) FROM users WHERE tenant_id = :t AND is_active),
                (SELECT count(*) FROM invites WHERE tenant_id = :t AND status = 'pending' AND expires_at > now()))
            """
        ),
        {"t": str(tenant_id), "u": str(user_id) if user_id else None, "d": delta, "r": reason, "a": str(actor_id) if actor_id else None},
    )


# ---------------------------------------------------------------------------
# Roles: resolution + guardrails
# ---------------------------------------------------------------------------


async def resolve_roles(session, tenant_id: uuid.UUID, names: List[str]) -> List[Dict[str, Any]]:
    names = list(dict.fromkeys(n.strip() for n in names if n and n.strip()))
    out = []
    for n in names:
        row = (
            await session.execute(
                text("SELECT id, name, scope, role_rank FROM roles WHERE name = :n AND (tenant_id = :t OR scope = 'PLATFORM')"),
                {"n": n, "t": str(tenant_id)},
            )
        ).mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail=f"Role not found: {n}")
        out.append(dict(row))
    return out


def check_can_grant(actor: Actor, roles: List[Dict[str, Any]]) -> None:
    for r in roles:
        if r["name"] == "platform_admin" or r["scope"] == "PLATFORM":
            if not actor.platform:
                raise HTTPException(status_code=403, detail="Only a platform admin may grant platform_admin")
            raise HTTPException(status_code=400, detail="platform_admin is not a tenant role; it is granted out of band")
        if r["name"] == "owner" and not (actor.owner or actor.platform):
            raise HTTPException(status_code=403, detail="Only an owner or platform admin may grant owner")
        if int(r["role_rank"]) > actor.rank and not actor.platform:
            raise HTTPException(status_code=403, detail=f"Cannot grant role '{r['name']}' above your own rank")


async def member_roles(session, tenant_id, user_id) -> List[Dict[str, Any]]:
    rows = (
        await session.execute(
            text(
                """
                SELECT r.id, r.name, r.scope, r.role_rank FROM user_roles ur JOIN roles r ON r.id = ur.role_id
                WHERE ur.user_id = :u AND (ur.tenant_id = :t OR r.scope = 'PLATFORM')
                """
            ),
            {"u": str(user_id), "t": str(tenant_id)},
        )
    ).mappings().all()
    return [dict(r) for r in rows]


SYSTEM_ROLE_NAMES = frozenset(RESERVED_ROLE_NAMES | set(ROLE_RANKS) | {"hr_manager", "manager"})
CUSTOM_ROLE_MAX_RANK = 40
FORBIDDEN_PERMISSION_NAMESPACES = ("org", "platform")


def check_custom_permissions(permissions: List[str], held: List[str], is_platform: bool) -> None:
    """Custom (tenant-defined) roles: never `*` wildcards or org.* / platform.* permissions, and a
    non-platform actor may only grant permissions it holds itself."""
    for p in permissions:
        if "*" in p:
            raise HTTPException(status_code=400, detail="Wildcard permissions are not allowed in custom roles")
        if p.split(".", 1)[0] in FORBIDDEN_PERMISSION_NAMESPACES:
            raise HTTPException(status_code=403, detail="org.* and platform.* permissions cannot be placed in a custom role")
    if not is_platform:
        missing = sorted(set(permissions) - set(held))
        if missing:
            raise HTTPException(status_code=403, detail=f"Cannot grant permissions you do not hold: {', '.join(missing)}")


def custom_role_rank(actor: "Actor") -> int:
    """Custom role rank: actor rank - 10, capped at 40. An actor too low-ranked to stay above it is refused."""
    rank = min(actor.rank - 10, CUSTOM_ROLE_MAX_RANK)
    if rank < 10:
        raise HTTPException(status_code=403, detail="Your rank is too low to manage custom roles")
    return rank


def check_can_manage_target(actor: Actor, target_roles: List[Dict[str, Any]]) -> None:
    if actor.platform:
        return
    top = max([int(r["role_rank"]) for r in target_roles] + [0])
    if top > actor.rank:
        raise HTTPException(status_code=403, detail="Cannot modify a user with a higher-ranked role")


async def _active_holders(session, tenant_id, names, exclude: Optional[uuid.UUID] = None) -> int:
    row = (
        await session.execute(
            text(
                """
                SELECT count(DISTINCT u.id) FROM users u
                JOIN user_roles ur ON ur.user_id = u.id AND ur.tenant_id = u.tenant_id
                JOIN roles r ON r.id = ur.role_id
                WHERE u.tenant_id = :t AND u.is_active AND r.name = ANY(:names)
                  AND (CAST(:ex AS uuid) IS NULL OR u.id <> CAST(:ex AS uuid))
                """
            ),
            {"t": str(tenant_id), "names": list(names), "ex": str(exclude) if exclude else None},
        )
    ).one()
    return int(row[0])


async def guard_last(session, tenant_id, user_id, current_names: List[str], keep_names: List[str]) -> None:
    """Refuse a change that would leave the tenant without an owner / admin it currently has."""
    if "owner" in current_names and "owner" not in keep_names:
        if await _active_holders(session, tenant_id, ["owner"], exclude=user_id) == 0:
            raise HTTPException(status_code=409, detail={"error": "last_owner", "message": "Transfer ownership first"})
    was_admin = any(n in ADMIN_CAPABLE_ROLES for n in current_names)
    stays_admin = any(n in ADMIN_CAPABLE_ROLES for n in keep_names)
    if was_admin and not stays_admin:
        if await _active_holders(session, tenant_id, ADMIN_CAPABLE_ROLES, exclude=user_id) == 0:
            raise HTTPException(status_code=409, detail={"error": "last_admin", "message": "Tenant needs at least one admin"})


async def apply_roles(session, ctx, actor: Actor, tenant_id, user_id, new_names: List[str]) -> Dict[str, List[str]]:
    target = (
        await session.execute(
            text("SELECT id, is_active FROM users WHERE id = :u AND tenant_id = :t FOR UPDATE"),
            {"u": str(user_id), "t": str(tenant_id)},
        )
    ).first()
    if not target:
        raise HTTPException(status_code=404, detail="Member not found")
    wanted = await resolve_roles(session, tenant_id, new_names)
    current = [r for r in await member_roles(session, tenant_id, user_id) if r["scope"] == "TENANT"]
    cur_names = {r["name"] for r in current}
    new_set = {r["name"] for r in wanted}
    add = [r for r in wanted if r["name"] not in cur_names]
    remove = [r for r in current if r["name"] not in new_set]
    if not add and not remove:
        return {"added": [], "removed": []}

    check_can_grant(actor, add)
    check_can_manage_target(actor, current)
    for r in remove:
        if int(r["role_rank"]) > actor.rank and not actor.platform:
            raise HTTPException(status_code=403, detail=f"Cannot remove role '{r['name']}' above your own rank")
    await guard_last(session, tenant_id, user_id, sorted(cur_names), sorted(new_set))

    for r in remove:
        await session.execute(
            text("DELETE FROM user_roles WHERE user_id = :u AND role_id = :r AND tenant_id = :t"),
            {"u": str(user_id), "r": str(r["id"]), "t": str(tenant_id)},
        )
    for r in add:
        await session.execute(
            text(
                """
                INSERT INTO user_roles (user_id, role_id, tenant_id, assigned_by)
                VALUES (:u, :r, :t, (SELECT id FROM users WHERE id = :by))
                ON CONFLICT DO NOTHING
                """
            ),
            {"u": str(user_id), "r": str(r["id"]), "t": str(tenant_id), "by": str(ctx.user_id)},
        )
    is_owner = "owner" in new_set
    await session.execute(text("UPDATE users SET is_owner = :o WHERE id = :u"), {"o": is_owner, "u": str(user_id)})
    if is_owner:
        await session.execute(
            text("UPDATE tenants SET owner_user_id = :u WHERE id = :t AND owner_user_id IS NULL"),
            {"u": str(user_id), "t": str(tenant_id)},
        )
    return {"added": sorted(r["name"] for r in add), "removed": sorted(r["name"] for r in remove)}


# ---------------------------------------------------------------------------
# Membership lifecycle
# ---------------------------------------------------------------------------


async def deactivate_member(session, ctx, actor: Actor, tenant_id, user_id) -> Dict[str, Any]:
    await lock_tenant(session, tenant_id)
    u = (
        await session.execute(
            text("SELECT id, email, is_active FROM users WHERE id = :u AND tenant_id = :t FOR UPDATE"),
            {"u": str(user_id), "t": str(tenant_id)},
        )
    ).mappings().first()
    if not u:
        raise HTTPException(status_code=404, detail="Member not found")
    if not u["is_active"]:
        return {"user_id": str(user_id), "is_active": False, "changed": False}
    roles = await member_roles(session, tenant_id, user_id)
    check_can_manage_target(actor, roles)
    await guard_last(session, tenant_id, user_id, [r["name"] for r in roles], [])
    await session.execute(
        text("UPDATE users SET is_active = false, deactivated_at = now() WHERE id = :u"), {"u": str(user_id)}
    )
    await record_seat_event(session, tenant_id, user_id, -1, "user_deactivated", ctx.user_id)
    await audit(session, ctx, "member.deactivate", "user", user_id, tenant_id, {"email": u["email"]})
    return {"user_id": str(user_id), "is_active": False, "changed": True}


async def reactivate_member(session, ctx, actor: Actor, tenant_id, user_id) -> Dict[str, Any]:
    tenant = await lock_tenant(session, tenant_id)
    if str(tenant["status"]).upper() in {"CLOSED", "SUSPENDED"}:
        raise HTTPException(status_code=409, detail="Tenant is not active")
    u = (
        await session.execute(
            text("SELECT id, email, is_active FROM users WHERE id = :u AND tenant_id = :t FOR UPDATE"),
            {"u": str(user_id), "t": str(tenant_id)},
        )
    ).mappings().first()
    if not u:
        raise HTTPException(status_code=404, detail="Member not found")
    if u["is_active"]:
        return {"user_id": str(user_id), "is_active": True, "changed": False}
    check_can_manage_target(actor, await member_roles(session, tenant_id, user_id))
    await require_seat(session, tenant_id)
    await session.execute(
        text("UPDATE users SET is_active = true, deactivated_at = NULL WHERE id = :u"), {"u": str(user_id)}
    )
    await record_seat_event(session, tenant_id, user_id, 1, "user_reactivated", ctx.user_id)
    await audit(session, ctx, "member.reactivate", "user", user_id, tenant_id, {"email": u["email"]})
    return {"user_id": str(user_id), "is_active": True, "changed": True}


# ---------------------------------------------------------------------------
# Invites
# ---------------------------------------------------------------------------


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _norm_email(email: str) -> str:
    e = (email or "").strip().lower()
    if "@" not in e or len(e) > 254 or " " in e:
        raise HTTPException(status_code=400, detail="Invalid email")
    return e


async def create_invite_row(session, ctx, actor: Actor, tenant_id, email: str, role_names: List[str]) -> Dict[str, Any]:
    email = _norm_email(email)
    tenant = await lock_tenant(session, tenant_id)
    await sweep_expired_invites(session, tenant_id)
    if str(tenant["status"]).upper() in {"CLOSED", "SUSPENDED"}:
        raise HTTPException(status_code=409, detail="Tenant is not active")
    roles = await resolve_roles(session, tenant_id, role_names or ["org_user"])
    check_can_grant(actor, roles)

    # Non-platform callers get one generic refusal: distinct messages would reveal whether an
    # email already has an account (or a pending invite) in ANOTHER tenant.
    generic = "This email cannot be invited to this organisation"
    existing = (await session.execute(text("SELECT tenant_id FROM users WHERE lower(email) = :e ORDER BY created_at, id LIMIT 1"), {"e": email})).first()
    if existing:
        raise HTTPException(status_code=409, detail="Email already belongs to a tenant" if actor.platform else generic)
    other = (
        await session.execute(
            text("SELECT tenant_id FROM invites WHERE lower(email) = :e AND status = 'pending' AND expires_at > now() LIMIT 1"), {"e": email}
        )
    ).first()
    if other:
        if actor.platform or str(other[0]) == str(tenant_id):
            raise HTTPException(status_code=409, detail="A pending invite already exists for this email")
        raise HTTPException(status_code=409, detail=generic)
    await require_seat(session, tenant_id)

    token = secrets.token_urlsafe(32)
    invite_id = uuid.uuid4()
    expires = datetime.now(timezone.utc) + INVITE_TTL
    await session.execute(
        text(
            """
            INSERT INTO invites (id, tenant_id, email, role_names, token_hash, status, expires_at, invited_by)
            VALUES (:id, :t, :e, :roles, :h, 'pending', :exp, :by)
            """
        ),
        {"id": str(invite_id), "t": str(tenant_id), "e": email, "roles": [r["name"] for r in roles], "h": hash_token(token), "exp": expires, "by": str(ctx.user_id)},
    )
    await record_seat_event(session, tenant_id, None, 1, "invite_created", ctx.user_id)
    await audit(session, ctx, "invite.create", "invite", invite_id, tenant_id, {"email": email, "roles": [r["name"] for r in roles]})
    return {"invite_id": invite_id, "token": token, "expires_at": expires, "email": email, "roles": [r["name"] for r in roles]}


async def deliver_invite(invite_id: uuid.UUID, email: str, token: str, send_email: bool) -> Dict[str, Any]:
    """After the invite transaction committed: ask Supabase to email it (best effort) and build the copyable link."""
    from services.common.db import session_scope

    link = f"{app_public_url()}/auth/accept?token={token}"
    result: Dict[str, Any] = {"accept_link": link, "email_requested": False, "email_error": None}
    client = supabase_sync.get_client() if send_email else None
    if send_email and client is None:
        result["email_error"] = "supabase_not_configured"
    if client is not None:
        try:
            resp = await client.invite(email, link)
            result["email_requested"] = True
            async with session_scope() as s:
                await s.execute(
                    text("UPDATE invites SET supabase_user_id = :sid, supabase_created = true WHERE id = :i"),
                    {"sid": resp.get("id"), "i": str(invite_id)},
                )
        except supabase_sync.SupabaseError as exc:
            result["email_error"] = str(exc)
        except Exception as exc:  # noqa: BLE001
            result["email_error"] = f"{type(exc).__name__}: {exc}"[:200]
    result["note"] = "Share accept_link with the invitee if email delivery is not configured (Supabase SMTP)."
    return result


def _effective_status(row) -> str:
    if row["status"] == "pending" and row["expires_at"] <= datetime.now(timezone.utc):
        return "expired"
    return row["status"]


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class SeatUpdate(BaseModel):
    seat_limit: Optional[int] = Field(None, ge=1, le=100000)
    seat_price: Optional[Decimal] = Field(None, ge=0)
    billing_status: Optional[str] = None


class InviteCreate(BaseModel):
    email: str = Field(..., min_length=3, max_length=254)
    roles: List[str] = Field(default_factory=list)
    send_email: bool = True


class InviteAccept(BaseModel):
    token: str = Field(..., min_length=10, max_length=200)


class MemberRoles(BaseModel):
    roles: List[str]


class TransferOwnership(BaseModel):
    new_owner_user_id: uuid.UUID


class TenantIdPath:  # tiny helper for readability
    pass


# ---------------------------------------------------------------------------
# Seat endpoints
# ---------------------------------------------------------------------------


@router.put("/tenants/{tenant_id}/seats")
async def set_seats(
    tenant_id: uuid.UUID,
    payload: SeatUpdate,
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_async_session),
):
    await require_platform_admin(ctx, session)
    fields = payload.model_fields_set
    if not fields:
        raise HTTPException(status_code=400, detail="No updates provided")
    if payload.billing_status is not None and payload.billing_status not in BILLING_STATUSES:
        raise HTTPException(status_code=400, detail=f"billing_status must be one of {sorted(BILLING_STATUSES)}")
    tenant = await lock_tenant(session, tenant_id)
    usage = await seat_usage(session, tenant_id)
    new_limit = payload.seat_limit if "seat_limit" in fields else tenant["seat_limit"]
    if new_limit is not None and new_limit < usage["seats_used"]:
        raise seat_error(usage["seats_used"], new_limit)
    price = payload.seat_price if "seat_price" in fields else tenant["seat_price"]
    bstatus = payload.billing_status or tenant["billing_status"]
    await session.execute(
        text("UPDATE tenants SET seat_limit = :l, seat_price = :p, billing_status = :b, updated_at = now() WHERE id = :t"),
        {"l": new_limit, "p": price, "b": bstatus, "t": str(tenant_id)},
    )
    if new_limit != tenant["seat_limit"]:
        await record_seat_event(session, tenant_id, None, 0, f"seat_limit_changed:{tenant['seat_limit']}->{new_limit}", ctx.user_id)
    await audit(
        session, ctx, "tenant.seats.update", "tenant", tenant_id, tenant_id,
        {"seat_limit": new_limit, "seat_price": price, "billing_status": bstatus, "previous_limit": tenant["seat_limit"]},
    )
    await session.commit()
    return await seat_usage(session, tenant_id)


def internal_key_ok(request: Request) -> bool:
    expected = os.getenv("INTERNAL_SERVICE_KEY", "")
    provided = request.headers.get("x-internal-key") or ""
    return bool(expected) and secrets.compare_digest(provided, expected)


@router.get("/tenants/{tenant_id}/seats")
async def get_seats(
    tenant_id: uuid.UUID,
    request: Request,
    since_days: int = 45,
    session: AsyncSession = Depends(get_async_session),
):
    """Seat snapshot + append-only ledger. Readable by tenant admins / platform admins, or by
    another service with the shared x-internal-key (billing). events[].delta tracks seats_used
    (active users + pending invites)."""
    if not internal_key_ok(request):
        ctx = await get_auth_context(request)
        await ensure_tenant_scope(ctx, tenant_id, session)
    usage = await seat_usage(session, tenant_id)
    ev = (
        await session.execute(
            text(
                """SELECT user_id, delta, reason, at, active_after, pending_after FROM seat_events
                   WHERE tenant_id = :t AND at >= now() - make_interval(days => :d) ORDER BY at, id"""
            ),
            {"t": str(tenant_id), "d": max(1, min(since_days, 400))},
        )
    ).mappings().all()
    usage["events"] = [{**dict(e), "user_id": str(e["user_id"]) if e["user_id"] else None, "at": e["at"].isoformat()} for e in ev]
    return usage


@router.get("/platform/seat-usage")
async def platform_seat_usage(
    request: Request,
    session: AsyncSession = Depends(get_async_session),
):
    if not internal_key_ok(request):
        ctx = await get_auth_context(request)
        await require_platform_admin(ctx, session)
    await sweep_expired_invites(session)
    rows = (
        await session.execute(
            text(
                """
                SELECT t.id, t.name, t.status, t.seat_limit, t.seat_price, t.billing_status,
                  (SELECT count(*) FROM users u WHERE u.tenant_id = t.id AND u.is_active) AS active_users,
                  (SELECT count(*) FROM invites i WHERE i.tenant_id = t.id AND i.status = 'pending' AND i.expires_at > now()) AS pending_invites
                FROM tenants t ORDER BY t.name
                """
            )
        )
    ).mappings().all()
    out = []
    for r in rows:
        used = int(r["active_users"]) + int(r["pending_invites"])
        out.append({
            "tenant_id": str(r["id"]), "name": r["name"], "status": r["status"],
            "seat_limit": r["seat_limit"], "seat_price": str(r["seat_price"]) if r["seat_price"] is not None else None,
            "billing_status": r["billing_status"], "active_users": int(r["active_users"]),
            "pending_invites": int(r["pending_invites"]), "seats_used": used, "current_seats": used,
            "seats_available": None if r["seat_limit"] is None else max(r["seat_limit"] - used, 0),
        })
    return {"tenants": out, "total_seats_used": sum(o["seats_used"] for o in out)}


# ---------------------------------------------------------------------------
# Invite endpoints
# ---------------------------------------------------------------------------


@router.post("/tenants/{tenant_id}/invites", status_code=status.HTTP_201_CREATED)
async def create_invite(
    tenant_id: uuid.UUID,
    payload: InviteCreate,
    request: Request,
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_async_session),
):
    await invite_limiter.check(request)
    await ensure_tenant_scope(ctx, tenant_id, session)
    actor = await actor_info(ctx, session)
    inv = await create_invite_row(session, ctx, actor, tenant_id, payload.email, payload.roles)
    await session.commit()
    delivery = await deliver_invite(inv["invite_id"], inv["email"], inv["token"], payload.send_email)
    return {"invite_id": str(inv["invite_id"]), "email": inv["email"], "roles": inv["roles"], "status": "pending", "expires_at": inv["expires_at"], **delivery}


@router.get("/tenants/{tenant_id}/invites")
async def list_invites(
    tenant_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_async_session),
):
    await ensure_tenant_scope(ctx, tenant_id, session)
    rows = (
        await session.execute(
            text(
                """SELECT id, email, role_names, status, expires_at, invited_by, created_at, accepted_at, revoked_at
                   FROM invites WHERE tenant_id = :t ORDER BY created_at DESC"""
            ),
            {"t": str(tenant_id)},
        )
    ).mappings().all()
    return [{**dict(r), "status": _effective_status(r), "roles": r["role_names"]} for r in rows]


async def _invite_for_admin(session, ctx, invite_id: uuid.UUID) -> Dict[str, Any]:
    row = (await session.execute(text("SELECT * FROM invites WHERE id = :i"), {"i": str(invite_id)})).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Invite not found")
    await ensure_tenant_scope(ctx, row["tenant_id"], session)
    return dict(row)


@router.delete("/invites/{invite_id}")
async def revoke_invite(
    invite_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_async_session),
):
    inv = await _invite_for_admin(session, ctx, invite_id)
    tenant_id = inv["tenant_id"]
    await check_invite_rank(session, await actor_info(ctx, session), tenant_id, inv)
    await lock_tenant(session, tenant_id)
    cur = (await session.execute(text("SELECT status FROM invites WHERE id = :i FOR UPDATE"), {"i": str(invite_id)})).one()
    if cur[0] != "pending":
        raise HTTPException(status_code=409, detail=f"Invite is {cur[0]}")
    await session.execute(text("UPDATE invites SET status = 'revoked', revoked_at = now() WHERE id = :i"), {"i": str(invite_id)})
    await record_seat_event(session, tenant_id, None, -1, "invite_revoked", ctx.user_id)
    await audit(session, ctx, "invite.revoke", "invite", invite_id, tenant_id, {"email": inv["email"]})
    await session.commit()
    await _cleanup_supabase_invitee(inv)
    return {"invite_id": str(invite_id), "status": "revoked"}


async def check_invite_rank(session, actor: Actor, tenant_id, inv: Dict[str, Any]) -> None:
    """Resend / revoke of an invite needs rank >= the invite's highest role (same rule as granting it)."""
    if actor.platform:
        return
    names = list(inv.get("role_names") or ["org_user"])
    rows = (
        await session.execute(
            text("SELECT coalesce(max(role_rank), 0) FROM roles WHERE name = ANY(:n) AND (tenant_id = :t OR scope = 'PLATFORM')"),
            {"n": names, "t": str(tenant_id)},
        )
    ).one()
    top = int(rows[0])
    if "owner" in names and not actor.owner:
        raise HTTPException(status_code=403, detail="Only an owner or platform admin may manage an owner invite")
    if top > actor.rank:
        raise HTTPException(status_code=403, detail="Cannot manage an invite for a role above your own rank")


async def _cleanup_supabase_invitee(inv: Dict[str, Any]) -> None:
    """Delete the unconfirmed Supabase user our invite created (never one that has signed in)."""
    if not (inv.get("supabase_created") and inv.get("supabase_user_id")):
        return
    client = supabase_sync.get_client()
    if client is None:
        return
    try:
        u = await client.get_user(str(inv["supabase_user_id"]))
        if not u.get("last_sign_in_at"):
            await client.delete_user(str(inv["supabase_user_id"]))
    except Exception as exc:  # noqa: BLE001
        logger.info("invitee cleanup skipped: %s", exc)


@router.post("/invites/{invite_id}/resend")
async def resend_invite(
    invite_id: uuid.UUID,
    request: Request,
    send_email: bool = True,
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_async_session),
):
    await invite_limiter.check(request)
    inv = await _invite_for_admin(session, ctx, invite_id)
    tenant_id = inv["tenant_id"]
    await check_invite_rank(session, await actor_info(ctx, session), tenant_id, inv)
    await lock_tenant(session, tenant_id)
    await sweep_expired_invites(session, tenant_id)  # records the -1 for an invite that lapsed unseen
    cur = (await session.execute(text("SELECT status, expires_at FROM invites WHERE id = :i FOR UPDATE"), {"i": str(invite_id)})).mappings().one()
    eff = _effective_status(cur)
    if eff not in ("pending", "expired"):
        raise HTTPException(status_code=409, detail=f"Invite is {eff}")
    if eff == "expired":
        # Reviving must not collide with the unique (tenant, lower(email)) pending index, nor with an
        # email that has meanwhile become a user / got another pending invite: refuse cleanly.
        clash = (
            await session.execute(
                text(
                    """SELECT 1 FROM invites WHERE tenant_id = :t AND lower(email) = lower(:e) AND status = 'pending' AND id <> :i
                       UNION ALL SELECT 1 FROM users WHERE lower(email) = lower(:e)"""
                ),
                {"t": str(tenant_id), "e": inv["email"], "i": str(invite_id)},
            )
        ).first()
        if clash:
            raise HTTPException(status_code=409, detail="This invite can no longer be revived; create a new one")
        await require_seat(session, tenant_id)  # reviving an expired invite takes a seat again
    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + INVITE_TTL
    try:
        await session.execute(
            text("UPDATE invites SET token_hash = :h, expires_at = :e, status = 'pending' WHERE id = :i"),
            {"h": hash_token(token), "e": expires, "i": str(invite_id)},
        )
        if eff == "expired":
            await record_seat_event(session, tenant_id, None, 1, "invite_revived", ctx.user_id)
        await audit(session, ctx, "invite.resend", "invite", invite_id, tenant_id, {"email": inv["email"]})
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=409, detail="This invite can no longer be revived; create a new one")
    delivery = await deliver_invite(invite_id, inv["email"], token, send_email)
    return {"invite_id": str(invite_id), "status": "pending", "expires_at": expires, **delivery}


async def verify_bearer(token: str) -> Dict[str, Any]:
    """Resolve a Supabase access token to {id, email}. Replaced in tests."""
    client = supabase_sync.get_client()
    if client is None:
        raise HTTPException(status_code=503, detail="Auth provider not configured")
    try:
        u = await client.verify_token(token)
    except supabase_sync.SupabaseError:
        raise HTTPException(status_code=401, detail="Invalid token")
    if not u.get("id") or not u.get("email"):
        raise HTTPException(status_code=401, detail="Invalid token")
    if not (u.get("email_confirmed_at") or u.get("confirmed_at")):
        # an unconfirmed address proves nothing about who owns it
        raise HTTPException(status_code=401, detail="Email not confirmed")
    return {"id": u["id"], "email": u["email"], "name": (u.get("user_metadata") or {}).get("full_name") or (u.get("user_metadata") or {}).get("name")}


@router.post("/invites/accept")
async def accept_invite(
    payload: InviteAccept,
    request: Request,
    authorization: Optional[str] = Header(None),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        return await _accept_invite(payload, request, authorization, session)
    except IntegrityError:
        # two tenants invited the same email and both were accepted in parallel (users pk / lower(email) unique)
        await session.rollback()
        raise HTTPException(status_code=409, detail="This invitation can no longer be accepted")


async def _accept_invite(payload: InviteAccept, request: Request, authorization: Optional[str], session: AsyncSession):
    """The caller proves who they are with their Supabase access token (Authorization: Bearer);
    the invite must be addressed to that verified email."""
    # per caller identity + invite token (not global): one flooder cannot lock out other acceptors
    accept_limiter.check_key(f"{identity_key(request)}|{hash_token(payload.token)[:16]}")
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Bearer token required")
    who = await verify_bearer(authorization[7:].strip())
    sid = uuid.UUID(str(who["id"]))
    email = who["email"].strip().lower()

    row = (await session.execute(text("SELECT id, tenant_id FROM invites WHERE token_hash = :h"), {"h": hash_token(payload.token)})).first()
    if not row:
        raise HTTPException(status_code=404, detail="Invite not found")
    tenant_id = row[1]

    await lock_tenant(session, tenant_id)  # serialisation point: seat check + insert happen under this lock
    inv = (await session.execute(text("SELECT * FROM invites WHERE id = :i FOR UPDATE"), {"i": str(row[0])})).mappings().one()
    if inv["status"] == "accepted" and str(inv["accepted_user_id"]) == str(sid):
        return {"status": "already_accepted", "tenant_id": str(tenant_id), "user_id": str(sid)}
    if inv["status"] != "pending":
        raise HTTPException(status_code=410, detail=f"Invite is {inv['status']}")
    if inv["expires_at"] <= datetime.now(timezone.utc):
        await sweep_expired_invites(session, tenant_id)
        await session.commit()
        raise HTTPException(status_code=410, detail="Invite expired")
    if inv["email"].lower() != email:
        raise HTTPException(status_code=403, detail="This invite was issued to a different email")

    existing = (
        await session.execute(text("SELECT id, tenant_id, is_active FROM users WHERE lower(email) = :e FOR UPDATE"), {"e": email})
    ).mappings().first()
    if existing and existing["tenant_id"] and existing["tenant_id"] != tenant_id:
        raise HTTPException(status_code=409, detail="Email already belongs to another tenant")

    needs_seat = not (existing and existing["is_active"])
    if needs_seat:
        usage = await seat_usage(session, tenant_id)
        # this invite's own reservation converts into the seat; only ACTIVE users compete with it
        if usage["seat_limit"] is not None and usage["active_users"] >= usage["seat_limit"]:
            raise seat_error(usage["seats_used"], usage["seat_limit"])

    role_names = list(inv["role_names"] or ["org_user"])
    roles = await resolve_roles(session, tenant_id, role_names)
    is_owner = "owner" in role_names
    if existing:
        user_id = existing["id"]
        if not existing["is_active"]:
            # a previously deactivated user re-invited: the invite's roles replace whatever they held before
            await session.execute(text("DELETE FROM user_roles WHERE user_id = :u"), {"u": str(user_id)})
        await session.execute(
            text("UPDATE users SET tenant_id = :t, is_active = true, deactivated_at = NULL, supabase_user_id = :s, is_owner = :o WHERE id = :u"),
            {"t": str(tenant_id), "s": str(sid), "o": is_owner, "u": str(user_id)},
        )
    else:
        user_id = sid
        await session.execute(
            text(
                """INSERT INTO users (id, tenant_id, email, full_name, hashed_password, is_active, supabase_user_id, is_owner)
                   VALUES (:id, :t, :e, :n, 'supabase-managed-no-local-login', true, :id, :o)"""
            ),
            {"id": str(sid), "t": str(tenant_id), "e": email, "n": who.get("name"), "o": is_owner},
        )
    for r in roles:
        await session.execute(
            text(
                """INSERT INTO user_roles (user_id, role_id, tenant_id, assigned_by)
                   VALUES (:u, :r, :t, (SELECT id FROM users WHERE id = :by)) ON CONFLICT DO NOTHING"""
            ),
            {"u": str(user_id), "r": str(r["id"]), "t": str(tenant_id), "by": str(inv["invited_by"]) if inv["invited_by"] else None},
        )
    if is_owner:
        await session.execute(text("UPDATE tenants SET owner_user_id = :u WHERE id = :t AND owner_user_id IS NULL"), {"u": str(user_id), "t": str(tenant_id)})
    await session.execute(
        text("UPDATE invites SET status = 'accepted', accepted_at = now(), accepted_user_id = :u WHERE id = :i"),
        {"u": str(user_id), "i": str(inv["id"])},
    )
    # pending -> active keeps seats_used unchanged (0); if the user already held an active seat the
    # invite's reservation is simply released (-1)
    await record_seat_event(session, tenant_id, user_id, 0 if needs_seat else -1, "invite_accepted", sid)
    await write_audit(session, sid, "invite.accept", "invite", inv["id"], tenant_id, {"email": email, "roles": role_names})
    await session.commit()
    sync = await supabase_sync.sync_user(user_id, revoke=False)
    return {"status": "accepted", "tenant_id": str(tenant_id), "user_id": str(user_id), "roles": role_names, "supabase_sync": sync}


# ---------------------------------------------------------------------------
# Member endpoints
# ---------------------------------------------------------------------------


@router.get("/tenants/{tenant_id}/members")
async def list_members(
    tenant_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_async_session),
):
    await ensure_tenant_scope(ctx, tenant_id, session)
    rows = (
        await session.execute(
            text(
                """
                SELECT u.id, u.email, u.full_name, u.is_active, u.is_owner, u.created_at, u.supabase_synced,
                       CASE WHEN u.supabase_synced THEN 'synced'
                            WHEN u.supabase_sync_error IS NULL THEN 'pending'
                            WHEN u.supabase_sync_error = 'no_supabase_user' THEN 'no_supabase_user'
                            WHEN u.supabase_sync_error = 'supabase_not_configured' THEN 'not_configured'
                            ELSE 'error' END AS sync_status,
                       coalesce(array_agg(DISTINCT r.name) FILTER (WHERE r.name IS NOT NULL), '{}') AS roles
                FROM users u
                LEFT JOIN user_roles ur ON ur.user_id = u.id AND ur.tenant_id = u.tenant_id
                LEFT JOIN roles r ON r.id = ur.role_id
                WHERE u.tenant_id = :t GROUP BY u.id ORDER BY u.created_at
                """
            ),
            {"t": str(tenant_id)},
        )
    ).mappings().all()
    return [{**dict(r), "name": r["full_name"], "seat_status": "active" if r["is_active"] else "suspended"} for r in rows]


@router.put("/tenants/{tenant_id}/members/{user_id}/roles")
async def set_member_roles(
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    payload: MemberRoles,
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_async_session),
):
    await ensure_tenant_scope(ctx, tenant_id, session)
    actor = await actor_info(ctx, session)
    await lock_tenant(session, tenant_id)
    diff = await apply_roles(session, ctx, actor, tenant_id, user_id, payload.roles)
    await audit(session, ctx, "member.roles.set", "user", user_id, tenant_id, {"roles": payload.roles, **diff})
    await session.commit()
    sync = await supabase_sync.sync_user(user_id, revoke=bool(diff["added"] or diff["removed"]))
    return {"user_id": str(user_id), "roles": sorted(payload.roles), **diff, "supabase_sync": sync}


@router.post("/tenants/{tenant_id}/members/{user_id}/deactivate")
async def deactivate_member_ep(
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_async_session),
):
    await ensure_tenant_scope(ctx, tenant_id, session)
    actor = await actor_info(ctx, session)
    out = await deactivate_member(session, ctx, actor, tenant_id, user_id)
    await session.commit()
    if out["changed"]:
        out["supabase_sync"] = await supabase_sync.sync_user(user_id, revoke=True)
    return out


@router.post("/tenants/{tenant_id}/members/{user_id}/reactivate")
async def reactivate_member_ep(
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_async_session),
):
    await ensure_tenant_scope(ctx, tenant_id, session)
    actor = await actor_info(ctx, session)
    out = await reactivate_member(session, ctx, actor, tenant_id, user_id)
    await session.commit()
    if out["changed"]:
        out["supabase_sync"] = await supabase_sync.sync_user(user_id, revoke=False)
    return out


@router.post("/tenants/{tenant_id}/transfer-ownership")
async def transfer_ownership(
    tenant_id: uuid.UUID,
    payload: TransferOwnership,
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_async_session),
):
    await ensure_tenant_scope(ctx, tenant_id, session)
    actor = await actor_info(ctx, session)
    if not (actor.platform or actor.owner):
        raise HTTPException(status_code=403, detail="Only an owner or platform admin may transfer ownership")
    await lock_tenant(session, tenant_id)
    new = (
        await session.execute(
            text("SELECT id, is_active FROM users WHERE id = :u AND tenant_id = :t FOR UPDATE"),
            {"u": str(payload.new_owner_user_id), "t": str(tenant_id)},
        )
    ).mappings().first()
    if not new or not new["is_active"]:
        raise HTTPException(status_code=404, detail="New owner must be an active member of this tenant")
    olds = [
        r[0]
        for r in (
            await session.execute(
                text(
                    """SELECT DISTINCT u.id FROM users u JOIN user_roles ur ON ur.user_id = u.id AND ur.tenant_id = u.tenant_id
                       JOIN roles r ON r.id = ur.role_id AND r.name = 'owner' WHERE u.tenant_id = :t AND u.id <> :n"""
                ),
                {"t": str(tenant_id), "n": str(payload.new_owner_user_id)},
            )
        ).fetchall()
    ]
    role_ids = {
        n: i
        for n, i in (await session.execute(text("SELECT name, id FROM roles WHERE tenant_id = :t AND name IN ('owner','org_admin')"), {"t": str(tenant_id)})).fetchall()
    }
    async def grant(uid, rname):
        await session.execute(
            text("INSERT INTO user_roles (user_id, role_id, tenant_id, assigned_by) VALUES (:u, :r, :t, (SELECT id FROM users WHERE id = :by)) ON CONFLICT DO NOTHING"),
            {"u": str(uid), "r": str(role_ids[rname]), "t": str(tenant_id), "by": str(ctx.user_id)},
        )
    await grant(payload.new_owner_user_id, "owner")
    await session.execute(text("UPDATE users SET is_owner = true WHERE id = :u"), {"u": str(payload.new_owner_user_id)})
    for old in olds:
        await session.execute(
            text("DELETE FROM user_roles WHERE user_id = :u AND role_id = :r AND tenant_id = :t"),
            {"u": str(old), "r": str(role_ids["owner"]), "t": str(tenant_id)},
        )
        await session.execute(text("UPDATE users SET is_owner = false WHERE id = :u"), {"u": str(old)})
        await grant(old, "org_admin")
    await session.execute(text("UPDATE tenants SET owner_user_id = :u WHERE id = :t"), {"u": str(payload.new_owner_user_id), "t": str(tenant_id)})
    await audit(session, ctx, "tenant.transfer_ownership", "tenant", tenant_id, tenant_id,
                {"new_owner": str(payload.new_owner_user_id), "previous_owners": [str(o) for o in olds]})
    await session.commit()
    sync = await supabase_sync.sync_users([payload.new_owner_user_id, *olds], revoke=True)
    return {"tenant_id": str(tenant_id), "owner_user_id": str(payload.new_owner_user_id), "previous_owners": [str(o) for o in olds], "supabase_sync": sync}


# ---------------------------------------------------------------------------
# Supabase reconcile
# ---------------------------------------------------------------------------


@router.post("/admin/sync/reconcile")
async def reconcile_endpoint(
    apply: bool = False,
    adopt_orphans: bool = False,
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_async_session),
):
    """Compare admin-DB truth with Supabase app_metadata. Dry-run unless ?apply=true.
    adopt_orphans=true (with apply) also creates DB users for Supabase-only users that already
    carry a tenant_id in app_metadata."""
    await require_platform_admin(ctx, session)
    try:
        result = await supabase_sync.reconcile(apply=apply, adopt_orphans=adopt_orphans, actor_id=ctx.user_id)
    except supabase_sync.SupabaseError as exc:
        raise HTTPException(status_code=502 if exc.status != 503 else 503, detail=str(exc))
    await write_audit(session, ctx.user_id, "sync.reconcile", "system", None, None,
                      {"apply": apply, "drift": len(result["drift"]), "orphans": len(result["orphans_in_supabase_only"]), "adopted": result["adopted"], "adopt_skipped": len(result.get("adopt_skipped", []))})
    return result


# ---------------------------------------------------------------------------
# Platform admins (app_metadata only; never implicit)
# ---------------------------------------------------------------------------

PLATFORM_ADMIN_LOCK_KEY = 74190202


async def _change_platform_admin(user_id: uuid.UUID, grant: bool, ctx: AuthContext, session: AsyncSession) -> Dict[str, Any]:
    await require_platform_admin(ctx, session)
    client = supabase_sync.get_client()
    if client is None:
        raise HTTPException(status_code=503, detail="Auth provider not configured")
    await session.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": PLATFORM_ADMIN_LOCK_KEY})
    sid = str(user_id)
    try:
        await client.get_user(sid)
    except supabase_sync.SupabaseError as exc:
        if exc.status in (404, 422):
            # the admin DB id may differ from the Supabase id: resolve through users.supabase_user_id
            row = (await session.execute(text("SELECT supabase_user_id FROM users WHERE id = :u"), {"u": sid})).first()
            if not row or not row[0]:
                raise HTTPException(status_code=404, detail="User not found")
            sid = str(row[0])
        else:
            raise HTTPException(status_code=502, detail="Auth provider error")
    if not grant and await supabase_sync.count_platform_admins(client, exclude=sid) == 0:
        current = await client.get_user(sid)
        if "platform_admin" in ((current.get("app_metadata") or {}).get("roles") or []):
            raise HTTPException(status_code=409, detail={"error": "last_platform_admin", "message": "Cannot remove the last platform admin"})
    await write_audit(session, ctx.user_id, "platform_admin.grant" if grant else "platform_admin.revoke", "user", user_id, None, {"supabase_user_id": sid})
    try:
        result = await supabase_sync.set_platform_admin(client, sid, grant)
    except supabase_sync.SupabaseError as exc:
        raise HTTPException(status_code=502, detail=f"Auth provider error ({exc.status})")
    return {"user_id": str(user_id), **result}


@router.put("/platform/admins/{user_id}")
async def grant_platform_admin(
    user_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_async_session),
):
    """Explicit, audited grant of platform_admin (stored in Supabase app_metadata only)."""
    return await _change_platform_admin(user_id, True, ctx, session)


@router.delete("/platform/admins/{user_id}")
async def revoke_platform_admin(
    user_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_async_session),
):
    """Explicit, audited removal of platform_admin. Refuses to remove the last platform admin."""
    return await _change_platform_admin(user_id, False, ctx, session)
