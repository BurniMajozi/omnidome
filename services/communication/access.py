"""Access helpers for the communication service: role tiers and channel visibility.

Public channel  -> any member of the tenant.
Private channel -> its creator, a ChannelMember row, or a tenant admin tier.
Managing a channel (update/delete/members) -> channel owner or admin tier.
Deciding approvals needs the manager tier (admin tiers included).

COMM_ENFORCE_ROLES=false switches the role gates off (local development only).
"""

from __future__ import annotations

import logging
import os
import uuid
from typing import Any, Optional

from fastapi import HTTPException, status
from sqlalchemy import or_, select

from services.common import rbac
from services.common.auth import AuthContext
from services.communication.models import Channel, ChannelMember, Message

logger = logging.getLogger("communication.access")

ADMIN_ROLES = frozenset({"platform_admin", "owner", "org_admin", "admin", "tenant_admin", "super_admin"})
MANAGER_ROLES = ADMIN_ROLES | {"manager", "line_manager", "team_lead"}
ADMIN_PERMS = frozenset({"communication.admin"})
MANAGER_PERMS = ADMIN_PERMS | {"communication.manage"}
TIERS = {"admin": (ADMIN_ROLES, ADMIN_PERMS), "manager": (MANAGER_ROLES, MANAGER_PERMS)}


def roles_enforced() -> bool:
    return os.getenv("COMM_ENFORCE_ROLES", "true").strip().lower() not in {"0", "false", "no", "off"}


async def effective_access(ctx: AuthContext, session: Any) -> tuple[set, set]:
    if not ctx.rbac_loaded and session is not None:
        try:
            async with session.begin_nested():
                await rbac._load_rbac(ctx, session)
        except Exception as exc:  # noqa: BLE001
            logger.warning("RBAC lookup failed for communication authorization: %s", exc)
            if rbac._enforce_rbac():
                return set(), set()  # fail closed
    return {r.lower() for r in ctx.roles or []}, {p.lower() for p in ctx.permissions or []}


async def has_tier(ctx: AuthContext, session: Any, tier: str) -> bool:
    if not roles_enforced() or ctx.is_platform_admin:
        return True
    roles, perms = TIERS[tier]
    have_roles, have_perms = await effective_access(ctx, session)
    return bool((have_roles & roles) or (have_perms & perms))


async def require_tier(ctx: AuthContext, session: Any, tier: str, detail: Optional[str] = None) -> None:
    if not await has_tier(ctx, session, tier):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail or f"This action needs a {tier} role")


async def _is_member(session: Any, tenant_id: uuid.UUID, channel_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    row = (await session.execute(
        select(ChannelMember.id).where(
            ChannelMember.tenant_id == tenant_id,
            ChannelMember.channel_id == channel_id,
            ChannelMember.user_id == user_id,
        ).limit(1)
    )).first()
    return row is not None


async def channel_visible(session: Any, ctx: AuthContext, channel: Optional[Channel]) -> bool:
    if channel is None or channel.tenant_id != ctx.tenant_id:
        return False
    if not channel.is_private:
        return True
    if channel.created_by == ctx.user_id:
        return True
    if await _is_member(session, ctx.tenant_id, channel.id, ctx.user_id):
        return True
    return await has_tier(ctx, session, "admin")


async def get_visible_channel(session: Any, ctx: AuthContext, channel_id: Optional[uuid.UUID]) -> Channel:
    """Channel in this tenant that the caller may see, else 404 (existence of private channels is hidden)."""
    channel = None
    if channel_id is not None:
        channel = (await session.execute(
            select(Channel).where(Channel.id == channel_id, Channel.tenant_id == ctx.tenant_id)
        )).scalar_one_or_none()
    if not await channel_visible(session, ctx, channel):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Channel not found")
    return channel


async def can_manage_channel(session: Any, ctx: AuthContext, channel: Channel) -> bool:
    if channel.created_by == ctx.user_id:
        return True
    owner = (await session.execute(
        select(ChannelMember.id).where(
            ChannelMember.tenant_id == ctx.tenant_id,
            ChannelMember.channel_id == channel.id,
            ChannelMember.user_id == ctx.user_id,
            ChannelMember.role == "owner",
        ).limit(1)
    )).first()
    if owner:
        return True
    return await has_tier(ctx, session, "admin")


async def get_managed_channel(session: Any, ctx: AuthContext, channel_id: uuid.UUID) -> Channel:
    channel = await get_visible_channel(session, ctx, channel_id)
    if not await can_manage_channel(session, ctx, channel):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the channel owner or an admin can do this")
    return channel


async def visible_clause(session: Any, ctx: AuthContext):
    """SQL predicate over Channel limiting rows to those the caller can see."""
    if await has_tier(ctx, session, "admin"):
        return Channel.tenant_id == ctx.tenant_id
    member_of = select(ChannelMember.channel_id).where(
        ChannelMember.tenant_id == ctx.tenant_id, ChannelMember.user_id == ctx.user_id
    )
    return (Channel.tenant_id == ctx.tenant_id) & or_(
        Channel.is_private.is_(False),
        Channel.is_private.is_(None),
        Channel.created_by == ctx.user_id,
        Channel.id.in_(member_of),
    )


async def user_channel_access(tenant_id: uuid.UUID, user_id: uuid.UUID, channel_id: uuid.UUID, session: Any) -> bool:
    """Visibility check for callers that only have ids (websocket)."""
    ctx = AuthContext(user_id=user_id, tenant_id=tenant_id)
    channel = (await session.execute(
        select(Channel).where(Channel.id == channel_id, Channel.tenant_id == tenant_id)
    )).scalar_one_or_none()
    return await channel_visible(session, ctx, channel)


async def validate_tenant_users(session: Any, tenant_id: uuid.UUID, user_ids: list) -> list:
    """Return ids that are NOT users of this tenant. Uses the shared users table (tenant_id column)."""
    from sqlalchemy import text

    ids = [str(u) for u in set(user_ids)]
    if not ids:
        return []
    found: set = set()
    for scoped in (True, False):  # the users table may not carry tenant_id in every auth schema
        sql = "SELECT id FROM users WHERE id = ANY(:ids)" + (" AND tenant_id = :tid" if scoped else "")
        params: dict = {"ids": ids}
        if scoped:
            params["tid"] = str(tenant_id)
        try:
            async with session.begin_nested():
                found = {str(r[0]) for r in (await session.execute(text(sql), params)).fetchall()}
            break
        except Exception as exc:  # noqa: BLE001
            logger.warning("tenant user validation (scoped=%s) failed: %s", scoped, exc)
    else:
        return list(user_ids) if roles_enforced() else []
    return [u for u in user_ids if str(u) not in found]


async def validate_refs(
    session: Any, ctx: AuthContext, channel_id: uuid.UUID, message_id: Optional[uuid.UUID] = None
) -> Channel:
    """channel_id must be a visible channel of this tenant; message_id (if given) must be a message of that channel."""
    channel = await get_visible_channel(session, ctx, channel_id)
    if message_id is not None:
        ok = (await session.execute(
            select(Message.id).where(
                Message.id == message_id, Message.channel_id == channel_id, Message.tenant_id == ctx.tenant_id
            )
        )).first()
        if not ok:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Message not found")
    return channel
