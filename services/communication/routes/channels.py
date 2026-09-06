"""Channel routes — CRUD for communication channels."""

import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select, text

from services.common.auth import AuthContext, get_auth_context
from services.common.db import session_scope
from services.communication.models import Channel, ChannelMember, Message
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
        stmt = select(Channel).where(Channel.tenant_id == ctx.tenant_id)
        count_stmt = select(func.count(Channel.id)).where(
            Channel.tenant_id == ctx.tenant_id
        )

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
        stmt = (
            select(
                Message.channel_id,
                func.count(Message.id),
                func.max(Message.created_at),
            )
            .where(Message.tenant_id == ctx.tenant_id)
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
        stmt = select(Channel).where(
            Channel.id == channel_id, Channel.tenant_id == ctx.tenant_id
        )
        result = await session.execute(stmt)
        channel = result.scalar_one_or_none()
        if not channel:
            raise HTTPException(status_code=404, detail="Channel not found")
        return channel


@router.put("/{channel_id}", response_model=ChannelRead)
async def update_channel(
    channel_id: uuid.UUID,
    body: ChannelUpdate,
    ctx: AuthContext = Depends(get_auth_context),
):
    async with session_scope() as session:
        stmt = select(Channel).where(
            Channel.id == channel_id, Channel.tenant_id == ctx.tenant_id
        )
        result = await session.execute(stmt)
        channel = result.scalar_one_or_none()
        if not channel:
            raise HTTPException(status_code=404, detail="Channel not found")

        update_data = body.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(channel, field, value)
        await session.flush()
        await session.refresh(channel)
        return channel


@router.get("/{channel_id}/members")
async def list_members(channel_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context)):
    async with session_scope() as session:
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
            res = await session.execute(
                text("SELECT id, COALESCE(full_name, email) AS name FROM users WHERE id = ANY(:ids)"),
                {"ids": ids},
            )
            names = {str(row[0]): row[1] for row in res.fetchall()}
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
        channel = (
            await session.execute(
                select(Channel).where(Channel.id == channel_id, Channel.tenant_id == ctx.tenant_id)
            )
        ).scalar_one_or_none()
        if not channel:
            raise HTTPException(status_code=404, detail="Channel not found")
        existing = set(
            (
                await session.execute(
                    select(ChannelMember.user_id).where(ChannelMember.channel_id == channel_id)
                )
            ).scalars().all()
        )
        added = 0
        for uid in body.user_ids:
            if uid in existing:
                continue
            session.add(
                ChannelMember(
                    tenant_id=ctx.tenant_id, channel_id=channel_id, user_id=uid, role="member"
                )
            )
            added += 1
        await session.flush()
        return {"added": added}


@router.delete("/{channel_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_channel(
    channel_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    async with session_scope() as session:
        stmt = select(Channel).where(
            Channel.id == channel_id, Channel.tenant_id == ctx.tenant_id
        )
        result = await session.execute(stmt)
        channel = result.scalar_one_or_none()
        if not channel:
            raise HTTPException(status_code=404, detail="Channel not found")
        await session.delete(channel)
