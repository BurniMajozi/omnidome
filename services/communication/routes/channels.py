"""Channel routes — CRUD for communication channels."""

import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import delete, func, select, text, update

from services.common.auth import AuthContext, get_auth_context
from services.common.db import session_scope
from services.communication.access import (
    get_managed_channel,
    get_visible_channel,
    validate_tenant_users,
    visible_clause,
)
from services.communication.models import (
    Approval,
    Channel,
    ChannelMember,
    ChannelPreference,
    CommunicationSession,
    Escalation,
    Event,
    Message,
    MessageReaction,
    ScheduleEvent,
    Task,
)
from services.communication.schemas import (
    ChannelCreate,
    ChannelRead,
    ChannelUpdate,
    PaginatedResponse,
)

router = APIRouter(prefix="/channels", tags=["Channels"])


class MembersAdd(BaseModel):
    user_ids: List[uuid.UUID]


@router.post("", response_model=ChannelRead, status_code=status.HTTP_201_CREATED)
async def create_channel(
    body: ChannelCreate,
    ctx: AuthContext = Depends(get_auth_context),
):
    async with session_scope() as session:
        channel = Channel(
            tenant_id=ctx.tenant_id,
            name=body.name,
            description=body.description,
            is_private=body.is_private,
            created_by=ctx.user_id,
        )
        session.add(channel)
        await session.flush()
        # Creator is the channel owner.
        session.add(
            ChannelMember(
                tenant_id=ctx.tenant_id, channel_id=channel.id, user_id=ctx.user_id, role="owner"
            )
        )
        await session.refresh(channel)
        return channel


@router.get("", response_model=PaginatedResponse)
async def list_channels(
    ctx: AuthContext = Depends(get_auth_context),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    async with session_scope() as session:
        vis = await visible_clause(session, ctx)
        stmt = select(Channel).where(vis)
        count_stmt = select(func.count(Channel.id)).where(vis)

        total_result = await session.execute(count_stmt)
        total = total_result.scalar() or 0
        pages = max(1, (total + page_size - 1) // page_size)

        stmt = (
            stmt.order_by(Channel.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await session.execute(stmt)
        items = result.scalars().all()

        return PaginatedResponse(
            items=[ChannelRead.model_validate(c) for c in items],
            total=total,
            page=page,
            page_size=page_size,
            pages=pages,
        )


@router.get("/summary")
async def channels_summary(ctx: AuthContext = Depends(get_auth_context)):
    """Per-channel message counts + latest timestamp for unread badges.

    Declared before /{channel_id} so the literal path wins. The client keeps a
    per-channel last-seen count locally; unread = message_count - last_seen.
    """
    async with session_scope() as session:
        vis = await visible_clause(session, ctx)
        stmt = (
            select(
                Message.channel_id,
                func.count(Message.id),
                func.max(Message.created_at),
            )
            .where(Message.tenant_id == ctx.tenant_id, Message.channel_id.in_(select(Channel.id).where(vis)))
            .group_by(Message.channel_id)
        )
        rows = (await session.execute(stmt)).all()
        return {
            "items": [
                {
                    "channel_id": str(cid),
                    "message_count": int(cnt or 0),
                    "last_message_at": ts.isoformat() if ts else None,
                }
                for cid, cnt, ts in rows
            ]
        }


@router.get("/{channel_id}", response_model=ChannelRead)
async def get_channel(
    channel_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    async with session_scope() as session:
        return await get_visible_channel(session, ctx, channel_id)


@router.put("/{channel_id}", response_model=ChannelRead)
async def update_channel(
    channel_id: uuid.UUID,
    body: ChannelUpdate,
    ctx: AuthContext = Depends(get_auth_context),
):
    async with session_scope() as session:
        channel = await get_managed_channel(session, ctx, channel_id)

        update_data = body.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(channel, field, value)
        await session.flush()
        await session.refresh(channel)
        return channel


@router.get("/{channel_id}/members")
async def list_members(channel_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context)):
    async with session_scope() as session:
        await get_visible_channel(session, ctx, channel_id)
        rows = (
            await session.execute(
                select(ChannelMember).where(
                    ChannelMember.channel_id == channel_id,
                    ChannelMember.tenant_id == ctx.tenant_id,
                )
            )
        ).scalars().all()
        names: dict = {}
        ids = [str(r.user_id) for r in rows]
        if ids:
            try:
                async with session.begin_nested():
                    res = await session.execute(
                        text("SELECT id, COALESCE(full_name, email) AS name FROM users WHERE id = ANY(:ids)"),
                        {"ids": ids},
                    )
                    names = {str(row[0]): row[1] for row in res.fetchall()}
            except Exception:
                names = {}
        return {
            "items": [
                {"user_id": str(r.user_id), "name": names.get(str(r.user_id)), "role": r.role}
                for r in rows
            ]
        }


@router.post("/{channel_id}/members", status_code=status.HTTP_201_CREATED)
async def add_members(
    channel_id: uuid.UUID, body: MembersAdd, ctx: AuthContext = Depends(get_auth_context)
):
    async with session_scope() as session:
        await get_managed_channel(session, ctx, channel_id)
        unknown = await validate_tenant_users(session, ctx.tenant_id, body.user_ids)
        if unknown:
            raise HTTPException(status_code=422, detail="Some users do not belong to this tenant")
        existing = set(
            (
                await session.execute(
                    select(ChannelMember.user_id).where(
                        ChannelMember.channel_id == channel_id,
                        ChannelMember.tenant_id == ctx.tenant_id,
                    )
                )
            ).scalars().all()
        )
        added = 0
        for uid in body.user_ids:
            if uid in existing:
                continue
            existing.add(uid)
            session.add(
                ChannelMember(
                    tenant_id=ctx.tenant_id, channel_id=channel_id, user_id=uid, role="member"
                )
            )
            added += 1
        await session.flush()
        return {"added": added}


@router.delete("/{channel_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    channel_id: uuid.UUID, user_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context)
):
    async with session_scope() as session:
        channel = await get_visible_channel(session, ctx, channel_id)
        if user_id != ctx.user_id:  # leaving yourself is always allowed
            channel = await get_managed_channel(session, ctx, channel_id)
        if user_id == channel.created_by:
            raise HTTPException(status_code=409, detail="The channel creator cannot be removed")
        await session.execute(
            delete(ChannelMember).where(
                ChannelMember.channel_id == channel_id,
                ChannelMember.tenant_id == ctx.tenant_id,
                ChannelMember.user_id == user_id,
            )
        )


@router.delete("/{channel_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_channel(
    channel_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    async with session_scope() as session:
        channel = await get_managed_channel(session, ctx, channel_id)
        # Explicit deletes in one transaction: do not rely on the FK cascades existing in every deployed schema.
        for model in (
            ScheduleEvent, Task, Approval, Escalation, Event, CommunicationSession,
            MessageReaction, ChannelPreference, ChannelMember,
        ):
            await session.execute(delete(model).where(model.channel_id == channel_id))
        await session.execute(update(Message).where(Message.channel_id == channel_id).values(thread_parent_id=None))
        await session.execute(delete(Message).where(Message.channel_id == channel_id))
        await session.delete(channel)
