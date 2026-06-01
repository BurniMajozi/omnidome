"""Conversation management routes."""

import uuid
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from services.common.auth import AuthContext, get_auth_context
from agent_orchestrator.schemas import ConversationWithMessages

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("")
async def list_conversations(
    ctx: AuthContext = Depends(get_auth_context),
    agent_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List conversations for the current tenant."""
    # For v1, return empty list — DB persistence layer comes in Phase 2
    return {"items": [], "total": 0, "page": page, "page_size": page_size, "pages": 0}


@router.get("/{conversation_id}")
async def get_conversation(
    conversation_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Get a conversation with its messages."""
    raise HTTPException(status_code=501, detail="Conversation persistence not yet implemented — coming in Phase 2")


@router.delete("/{conversation_id}")
async def delete_conversation(
    conversation_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Delete a conversation."""
    return {"status": "not_implemented", "detail": "Conversation persistence coming in Phase 2"}
