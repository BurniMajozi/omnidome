"""Message state routes for persistent pinning."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from services.common.auth import AuthContext, get_auth_context
from services.common.db import session_scope
from services.communication.models import Message
from services.communication.schemas import MessagePinUpdate, MessageRead

router = APIRouter(prefix="/messages", tags=["Message State"])


@router.patch("/{message_id}/pin", response_model=MessageRead)
async def pin_message(
    message_id: uuid.UUID,
    body: MessagePinUpdate,
    ctx: AuthContext = Depends(get_auth_context),
):
    async with session_scope() as session:
        stmt = select(Message).where(Message.id == message_id)
        result = await session.execute(stmt)
        message = result.scalar_one_or_none()
        if not message:
            raise HTTPException(status_code=404, detail="Message not found")
        if message.channel_id is None:
            raise HTTPException(status_code=404, detail="Message not found")
        message.is_pinned = body.is_pinned
        await session.flush()
        await session.refresh(message)
        return message
