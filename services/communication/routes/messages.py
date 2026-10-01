"""Message routes — CRUD, threading, history (keyset) and reactions for channel messages.

Every route resolves the channel through access.get_visible_channel (tenant + private-channel
membership) and scopes message queries by tenant_id as well as channel_id.
"""

import os
import re
import unicodedata
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.exc import IntegrityError

from services.common.auth import AuthContext, get_auth_context
from services.common.db import session_scope
from services.common.rate_limiter import RateLimiter
from services.communication.access import get_visible_channel
from services.communication.models import Message, MessageReaction
from services.communication.realtime import spawn_broadcast
from services.communication.schemas import (
    MessageCreate,
    MessagePage,
    MessageRead,
    MessageUpdate,
)

router = APIRouter(prefix="/channels/{channel_id}/messages", tags=["Messages"])

_EMOJI_SHORTCODE = re.compile(r"^:?[a-z0-9_+\-]{1,30}:?$")
EMOJI_MAX_LEN = 32


def valid_emoji(emoji: str) -> bool:
    """Shortcode (+1, :tada:, thumbs_up) or a short run of emoji characters; no whitespace, controls
    or markup characters, at most 32 characters."""
    if not emoji or len(emoji) > EMOJI_MAX_LEN:
        return False
    if emoji.isascii():
        return bool(_EMOJI_SHORTCODE.match(emoji))
    for ch in emoji:
        if ch == "‍":  # zero width joiner used by emoji sequences
            continue
        cat = unicodedata.category(ch)
        if cat[0] in ("Z", "C") or ch in "<>&\"'":
            return False
    return True


def max_message_chars() -> int:
    try:
        return max(1, int(os.getenv("MESSAGE_MAX_CHARS", "") or 8000))
    except ValueError:
        return 8000


_limiters: dict = {}


def check_send_rate(ctx: AuthContext) -> None:
    try:
        per_min = max(1, int(os.getenv("MESSAGE_RATE_PER_MIN", "") or 120))
    except ValueError:
        per_min = 120
    limiter = _limiters.get(per_min)
    if limiter is None:
        limiter = _limiters[per_min] = RateLimiter(max_requests=per_min, window_seconds=60.0)
    limiter.check_key(f"msg:{ctx.tenant_id}:{ctx.user_id}")


@router.post("", response_model=MessageRead, status_code=status.HTTP_201_CREATED)
async def send_message(
    channel_id: uuid.UUID,
    body: MessageCreate,
    response: Response,
    ctx: AuthContext = Depends(get_auth_context),
):
    if len(body.content) > max_message_chars():
        raise HTTPException(status_code=422, detail=f"Message exceeds {max_message_chars()} characters")
    check_send_rate(ctx)

    created = False
    async with session_scope() as session:
        await get_visible_channel(session, ctx, channel_id)

        if body.client_msg_id:
            existing = await _find_by_client_id(session, ctx, channel_id, body.client_msg_id)
            if existing is not None:
                response.status_code = status.HTTP_200_OK
                return MessageRead.model_validate(existing)

        if body.thread_parent_id:
            parent = (await session.execute(
                select(Message.id).where(
                    Message.id == body.thread_parent_id,
                    Message.channel_id == channel_id,
                    Message.tenant_id == ctx.tenant_id,
                )
            )).first()
            if not parent:
                raise HTTPException(status_code=404, detail="Parent message not found")

        message = Message(
            tenant_id=ctx.tenant_id,
            channel_id=channel_id,
            user_id=ctx.user_id,
            content=body.content,
            thread_parent_id=body.thread_parent_id,
            client_msg_id=body.client_msg_id,
        )
        try:
            async with session.begin_nested():
                session.add(message)
                await session.flush()
            created = True
        except IntegrityError:
            # concurrent retry with the same client_msg_id: hand back the winner
            existing = await _find_by_client_id(session, ctx, channel_id, body.client_msg_id or "")
            if existing is None:
                raise
            response.status_code = status.HTTP_200_OK
            return MessageRead.model_validate(existing)
        await session.refresh(message)
        result = MessageRead.model_validate(message)

    # The session_scope exit committed; only now tell websocket clients.
    if created:
        spawn_broadcast(str(ctx.tenant_id), str(channel_id), result.model_dump(mode="json"))
    return result


async def _find_by_client_id(session, ctx: AuthContext, channel_id: uuid.UUID, client_msg_id: str):
    return (await session.execute(
        select(Message).where(
            Message.tenant_id == ctx.tenant_id,
            Message.channel_id == channel_id,
            Message.client_msg_id == client_msg_id,
        )
    )).scalar_one_or_none()


async def _parse_cursor(session, ctx: AuthContext, channel_id: uuid.UUID, before: str):
    """before = a message id (keyset on created_at,id) or an ISO-8601 timestamp (created_at only)."""
    try:
        mid = uuid.UUID(before)
    except ValueError:
        mid = None
    if mid is not None:
        row = (await session.execute(
            select(Message.created_at, Message.id).where(
                Message.id == mid, Message.channel_id == channel_id, Message.tenant_id == ctx.tenant_id
            )
        )).first()
        if row is None:
            raise HTTPException(status_code=422, detail="Unknown 'before' cursor")
        return and_(or_(
            Message.created_at < row[0],
            and_(Message.created_at == row[0], Message.id < row[1]),
        ))
    try:
        ts = datetime.fromisoformat(before.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(status_code=422, detail="'before' must be a message id or ISO timestamp")
    return Message.created_at < ts


@router.get("", response_model=MessagePage)
async def list_messages(
    channel_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    limit: Optional[int] = Query(None, ge=1, le=200),
    before: Optional[str] = Query(None, max_length=64),
):
    """Newest-first paging. Without params you get the NEWEST page_size messages (ascending inside the
    page). `before=<message id | ISO ts>` (+ `limit`) walks backwards; `next_before` / `has_more` tell
    the client how. Legacy `page` N still works: page 1 = newest, page 2 = the page before it, ..."""
    async with session_scope() as session:
        await get_visible_channel(session, ctx, channel_id)

        size = limit or page_size
        base = [Message.channel_id == channel_id, Message.tenant_id == ctx.tenant_id]
        total = (await session.execute(select(func.count(Message.id)).where(*base))).scalar() or 0
        pages = max(1, (total + size - 1) // size)

        stmt = select(Message).where(*base)
        if before:
            stmt = stmt.where(await _parse_cursor(session, ctx, channel_id, before))
            offset = 0
        else:
            offset = (page - 1) * size
        stmt = stmt.order_by(Message.created_at.desc(), Message.id.desc()).offset(offset).limit(size + 1)
        rows = list((await session.execute(stmt)).scalars().all())
        has_more = len(rows) > size
        rows = rows[:size]
        next_before = str(rows[-1].id) if (rows and has_more) else None
        items = list(reversed(rows))  # ascending for display

        names: dict = {}
        user_ids = list({m.user_id for m in items})
        if user_ids:
            try:
                async with session.begin_nested():
                    name_rows = await session.execute(
                        text("SELECT id, COALESCE(full_name, email) AS name FROM users WHERE id = ANY(:ids)"),
                        {"ids": user_ids},
                    )
                    names = {str(r[0]): r[1] for r in name_rows}
            except Exception:
                names = {}

        reads = []
        for m in items:
            r = MessageRead.model_validate(m)
            r.author_name = names.get(str(m.user_id))
            reads.append(r)

        return MessagePage(
            items=reads,
            total=total,
            page=page,
            page_size=size,
            pages=pages,
            next_before=next_before,
            has_more=has_more,
        )


async def _load_message(session, ctx: AuthContext, channel_id: uuid.UUID, message_id: uuid.UUID) -> Message:
    await get_visible_channel(session, ctx, channel_id)
    message = (await session.execute(
        select(Message).where(
            Message.id == message_id,
            Message.channel_id == channel_id,
            Message.tenant_id == ctx.tenant_id,
        )
    )).scalar_one_or_none()
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    return message


@router.get("/{message_id}", response_model=MessageRead)
async def get_message(
    channel_id: uuid.UUID,
    message_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    async with session_scope() as session:
        return MessageRead.model_validate(await _load_message(session, ctx, channel_id, message_id))


@router.put("/{message_id}", response_model=MessageRead)
async def update_message(
    channel_id: uuid.UUID,
    message_id: uuid.UUID,
    body: MessageUpdate,
    ctx: AuthContext = Depends(get_auth_context),
):
    if len(body.content) > max_message_chars():
        raise HTTPException(status_code=422, detail=f"Message exceeds {max_message_chars()} characters")
    async with session_scope() as session:
        message = await _load_message(session, ctx, channel_id, message_id)
        if message.user_id != ctx.user_id:
            raise HTTPException(status_code=403, detail="Not authorised to edit this message")
        message.content = body.content
        await session.flush()
        await session.refresh(message)
        return MessageRead.model_validate(message)


@router.delete("/{message_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_message(
    channel_id: uuid.UUID,
    message_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    async with session_scope() as session:
        message = await _load_message(session, ctx, channel_id, message_id)
        if message.user_id != ctx.user_id:
            raise HTTPException(status_code=403, detail="Not authorised to delete this message")
        await session.delete(message)


@router.post("/{message_id}/react", status_code=status.HTTP_201_CREATED)
async def add_reaction(
    channel_id: uuid.UUID,
    message_id: uuid.UUID,
    emoji: str,
    ctx: AuthContext = Depends(get_auth_context),
):
    if not valid_emoji(emoji):
        raise HTTPException(status_code=422, detail="Invalid emoji")
    async with session_scope() as session:
        await _load_message(session, ctx, channel_id, message_id)
        reaction = (await session.execute(
            select(MessageReaction).where(
                MessageReaction.message_id == message_id,
                MessageReaction.user_id == ctx.user_id,
                MessageReaction.emoji == emoji,
            )
        )).scalar_one_or_none()
        if reaction is None:  # idempotent: one reaction per (message, user, emoji)
            reaction = MessageReaction(
                tenant_id=ctx.tenant_id,
                message_id=message_id,
                channel_id=channel_id,
                user_id=ctx.user_id,
                emoji=emoji,
            )
            session.add(reaction)
            await session.flush()
            await session.refresh(reaction)
        return {"message_id": reaction.message_id, "user_id": reaction.user_id, "emoji": reaction.emoji}


@router.delete("/{message_id}/react", status_code=status.HTTP_204_NO_CONTENT)
async def remove_reaction(
    channel_id: uuid.UUID,
    message_id: uuid.UUID,
    emoji: str,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Reactions can only be removed by their author."""
    async with session_scope() as session:
        await _load_message(session, ctx, channel_id, message_id)
        reaction = (await session.execute(
            select(MessageReaction).where(
                MessageReaction.message_id == message_id,
                MessageReaction.user_id == ctx.user_id,
                MessageReaction.emoji == emoji,
            )
        )).scalar_one_or_none()
        if reaction is None:
            raise HTTPException(status_code=404, detail="Reaction not found")
        await session.delete(reaction)
