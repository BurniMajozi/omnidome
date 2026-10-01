"""Message state routes for persistent pinning."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from services.common.auth import AuthContext, get_auth_context
from services.common.db import session_scope
from services.communication.access import channel_visible
from services.communication.models import Channel, Message
from services.communication.schemas import MessagePinUpdate, MessageRead

router = APIRouter(prefix="/messages", tags=["Message State"])


@router.patch("/{message_id}/pin", response_model=MessageRead)
async def pin_message(
    message_id: uuid.UUID,
    body: MessagePinUpdate,
    ctx: AuthContext = Depends(get_auth_context),
):
    async with session_scope() as session:
        row = (await session.execute(
            select(Message, Channel)
            .join(Channel, Message.channel_id == Channel.id)
            .where(
                Message.id == message_id,
                Message.tenant_id == ctx.tenant_id,
                Channel.tenant_id == ctx.tenant_id,
            )
        )).first()
        # hide messages of channels the caller cannot see behind the same 404
        if not row or not await channel_visible(session, ctx, row[1]):
            raise HTTPException(status_code=404, detail="Message not found")
        message = row[0]
        message.is_pinned = body.is_pinned
        await session.flush()
        await session.refresh(message)
        return MessageRead.model_validate(message)
