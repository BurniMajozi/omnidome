"""Conversation management routes — full CRUD with DB persistence.

Uses the AgentConversation, AgentMessage, and AgentAction models from
conversation/models.py for persistent conversation storage.
"""

import uuid
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select

from services.common.auth import AuthContext, get_auth_context
from services.common.db import session_scope as get_session
from services.agent_orchestrator.conversation.models import (
    AgentConversation,
    AgentMessage,
    AgentAction,
)
from services.agent_orchestrator.schemas import (
    ConversationRead,
    MessageRead,
    ConversationWithMessages,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# GET /api/conversations — List conversations
# ---------------------------------------------------------------------------

@router.get("")
async def list_conversations(
    ctx: AuthContext = Depends(get_auth_context),
    agent_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List conversations for the current tenant with pagination."""
    async with get_session() as session:
        stmt = select(AgentConversation).where(
            AgentConversation.tenant_id == ctx.tenant_id
        )

        if agent_type:
            stmt = stmt.where(AgentConversation.agent_type == agent_type)
        if status:
            stmt = stmt.where(AgentConversation.status == status)

        # Count total
        from sqlalchemy import func
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await session.execute(count_stmt)).scalar_one()

        # Fetch paginated
        stmt = (
            stmt.order_by(AgentConversation.updated_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await session.execute(stmt)
        items = result.scalars().all()

        # Batch query first user message and latest message for titles
        conv_ids = [c.id for c in items]
        title_map: dict[uuid.UUID, str] = {}
        last_msg_map: dict[uuid.UUID, str] = {}
        if conv_ids:
            msg_res = await session.execute(
                select(AgentMessage.conversation_id, AgentMessage.role, AgentMessage.content)
                .where(AgentMessage.conversation_id.in_(conv_ids))
                .order_by(AgentMessage.created_at.asc())
            )
            for cid, role, content in msg_res.all():
                if role == "user" and cid not in title_map and content:
                    title_map[cid] = content[:120]
                if content:
                    last_msg_map[cid] = content[:120]

        res_items = []
        for c in items:
            read_obj = ConversationRead.model_validate(c)
            fallback_title = c.context.get("title") if isinstance(c.context, dict) else None
            read_obj.title = title_map.get(c.id) or fallback_title or f"Chat with {c.agent_type}"
            read_obj.last_message = last_msg_map.get(c.id)
            res_items.append(read_obj)

    pages = max(1, (total + page_size - 1) // page_size)
    return {
        "items": res_items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": pages,
    }


# ---------------------------------------------------------------------------
# GET /api/conversations/{id} — Get conversation with messages
# ---------------------------------------------------------------------------

@router.get("/{conversation_id}", response_model=ConversationWithMessages)
async def get_conversation(
    conversation_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Get a conversation with all its messages and tool call history."""
    async with get_session() as session:
        result = await session.execute(
            select(AgentConversation).where(
                AgentConversation.id == conversation_id,
                AgentConversation.tenant_id == ctx.tenant_id,
            )
        )
        conv = result.scalar_one_or_none()

        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")

        # Explicitly query messages sorted by created_at asc
        msg_result = await session.execute(
            select(AgentMessage)
            .where(AgentMessage.conversation_id == conversation_id)
            .order_by(AgentMessage.created_at.asc())
        )
        messages = msg_result.scalars().all()

        conv_dict = {
            "id": conv.id,
            "tenant_id": conv.tenant_id,
            "agent_type": conv.agent_type,
            "channel": conv.channel,
            "external_id": conv.external_id,
            "status": conv.status,
            "context": conv.context or {},
            "created_at": conv.created_at,
            "updated_at": conv.updated_at,
            "messages": [MessageRead.model_validate(m) for m in messages],
        }
        return ConversationWithMessages.model_validate(conv_dict)


# ---------------------------------------------------------------------------
# DELETE /api/conversations/{id} — Delete a conversation
# ---------------------------------------------------------------------------

@router.delete("/{conversation_id}")
async def delete_conversation(
    conversation_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Delete a conversation and all its messages."""
    async with get_session() as session:
        result = await session.execute(
            select(AgentConversation).where(
                AgentConversation.id == conversation_id,
                AgentConversation.tenant_id == ctx.tenant_id,
            )
        )
        conv = result.scalar_one_or_none()

        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")

        await session.delete(conv)
        await session.flush()

    return {"status": "deleted", "id": str(conversation_id)}


# ---------------------------------------------------------------------------
# POST /api/conversations/{id}/messages — Add a message to a conversation
# ---------------------------------------------------------------------------

@router.post("/{conversation_id}/messages", response_model=MessageRead)
async def add_message(
    conversation_id: uuid.UUID,
    body: dict,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Add a message to an existing conversation."""
    async with get_session() as session:
        # Verify conversation exists and belongs to tenant
        conv_result = await session.execute(
            select(AgentConversation).where(
                AgentConversation.id == conversation_id,
                AgentConversation.tenant_id == ctx.tenant_id,
            )
        )
        conv = conv_result.scalar_one_or_none()
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")

        msg = AgentMessage(
            conversation_id=conversation_id,
            role=body.get("role", "user"),
            content=body.get("content"),
            tool_calls=body.get("tool_calls"),
            tool_results=body.get("tool_results"),
        )
        session.add(msg)

        # Update conversation timestamp
        conv.updated_at = __import__("datetime").datetime.now(
            tz=__import__("datetime").timezone.utc
        )

        await session.flush()
        await session.refresh(msg)

    return MessageRead.model_validate(msg)
