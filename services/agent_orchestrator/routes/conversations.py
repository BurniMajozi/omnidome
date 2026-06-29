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

    pages = max(1, (total + page_size - 1) // page_size)
    return {
        "items": [ConversationRead.model_validate(c) for c in items],
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

        # Eager load messages
        await session.refresh(conv, ["messages"])

    return ConversationWithMessages.model_validate(conv)


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
