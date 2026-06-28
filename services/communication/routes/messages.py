"""Message routes — CRUD, threading, and reactions for channel messages."""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select

from services.common.auth import AuthContext, get_auth_context
from services.common.db import session_scope
from services.communication.models import Channel, Message, MessageReaction
from services.communication.realtime import broadcast_message
from services.communication.schemas import (
    MessageCreate,
    MessageRead,
    MessageUpdate,
    PaginatedResponse,
)

router = APIRouter(prefix="/channels/{channel_id}/messages", tags=["Messages"])


@router.post("", response_model=MessageRead, status_code=status.HTTP_201_CREATED)
async def send_message(
    channel_id: uuid.UUID,
    body: MessageCreate,
    ctx: AuthContext = Depends(get_auth_context),
):
    async with session_scope() as session:
        # Verify channel exists and belongs to tenant
        ch_stmt = select(Channel).where(
            Channel.id == channel_id, Channel.tenant_id == ctx.tenant_id
        )
        ch_result = await session.execute(ch_stmt)
        channel = ch_result.scalar_one_or_none()
        if not channel:
            raise HTTPException(status_code=404, detail="Channel not found")

        # If threading, verify parent message exists
        if body.thread_parent_id:
            parent_stmt = select(Message).where(
                Message.id == body.thread_parent_id,
                Message.channel_id == channel_id,
            )
            parent_result = await session.execute(parent_stmt)
            parent = parent_result.scalar_one_or_none()
            if not parent:
                raise HTTPException(status_code=404, detail="Parent message not found")

        message = Message(
            channel_id=channel_id,
            user_id=ctx.user_id,
            content=body.content,
            thread_parent_id=body.thread_parent_id,
        )
        session.add(message)
        await session.flush()
        await session.refresh(message)

        # Broadcast to connected WebSocket clients — fire-and-forget, never blocks the response
        msg_data = MessageRead.model_validate(message).model_dump(mode="json")
        import asyncio
        asyncio.create_task(
            broadcast_message(str(ctx.tenant_id), str(channel_id), msg_data)
        )

        return message


@router.get("", response_model=PaginatedResponse)
async def list_messages(
    channel_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    async with session_scope() as session:
        # Verify channel exists
        ch_stmt = select(Channel).where(
            Channel.id == channel_id, Channel.tenant_id == ctx.tenant_id
        )
        ch_result = await session.execute(ch_stmt)
        channel = ch_result.scalar_one_or_none()
        if not channel:
            raise HTTPException(status_code=404, detail="Channel not found")

        stmt = select(Message).where(Message.channel_id == channel_id)
        count_stmt = select(func.count(Message.id)).where(
            Message.channel_id == channel_id
        )

        total_result = await session.execute(count_stmt)
        total = total_result.scalar() or 0
        pages = max(1, (total + page_size - 1) // page_size)

        stmt = (
            stmt.order_by(Message.created_at.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await session.execute(stmt)
        items = result.scalars().all()

        return PaginatedResponse(
            items=[MessageRead.model_validate(m) for m in items],
            total=total,
            page=page,
            page_size=page_size,
            pages=pages,
        )


@router.get("/{message_id}", response_model=MessageRead)
async def get_message(
    channel_id: uuid.UUID,
    message_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    async with session_scope() as session:
        stmt = select(Message).where(
            Message.id == message_id, Message.channel_id == channel_id
        )
        result = await session.execute(stmt)
        message = result.scalar_one_or_none()
        if not message:
            raise HTTPException(status_code=404, detail="Message not found")
        return message


@router.put("/{message_id}", response_model=MessageRead)
async def update_message(
    channel_id: uuid.UUID,
    message_id: uuid.UUID,
    body: MessageUpdate,
    ctx: AuthContext = Depends(get_auth_context),
):
    async with session_scope() as session:
        stmt = select(Message).where(
            Message.id == message_id, Message.channel_id == channel_id
        )
        result = await session.execute(stmt)
        message = result.scalar_one_or_none()
        if not message:
            raise HTTPException(status_code=404, detail="Message not found")

        # Only the author can edit
        if message.user_id != ctx.user_id:
            raise HTTPException(
                status_code=403, detail="Not authorised to edit this message"
            )

        update_data = body.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(message, field, value)
        await session.flush()
        await session.refresh(message)
        return message


@router.delete("/{message_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_message(
    channel_id: uuid.UUID,
    message_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    async with session_scope() as session:
        stmt = select(Message).where(
            Message.id == message_id, Message.channel_id == channel_id
        )
        result = await session.execute(stmt)
        message = result.scalar_one_or_none()
        if not message:
            raise HTTPException(status_code=404, detail="Message not found")

        # Only the author can delete
        if message.user_id != ctx.user_id:
            raise HTTPException(
                status_code=403, detail="Not authorised to delete this message"
            )
        await session.delete(message)


@router.post("/{message_id}/react", status_code=status.HTTP_201_CREATED)
async def add_reaction(
    channel_id: uuid.UUID,
    message_id: uuid.UUID,
    emoji: str,
    ctx: AuthContext = Depends(get_auth_context),
):
    async with session_scope() as session:
        # Verify message exists
        msg_stmt = select(Message).where(
            Message.id == message_id, Message.channel_id == channel_id
        )
        msg_result = await session.execute(msg_stmt)
        msg = msg_result.scalar_one_or_none()
        if not msg:
            raise HTTPException(status_code=404, detail="Message not found")

        reaction = MessageReaction(
            message_id=message_id,
            user_id=ctx.user_id,
            emoji=emoji,
        )
        session.add(reaction)
        await session.flush()
        await session.refresh(reaction)
        return {"message_id": reaction.message_id, "user_id": reaction.user_id, "emoji": reaction.emoji}
