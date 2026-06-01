"""Event routes — create and list immutable events."""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select

from services.common.auth import AuthContext, get_auth_context
from services.common.db import session_scope
from services.communication.models import Event
from services.communication.schemas import (
    EventCreate,
    EventRead,
    PaginatedResponse,
)

router = APIRouter(prefix="/events", tags=["Events"])


@router.post("", response_model=EventRead, status_code=status.HTTP_201_CREATED)
async def create_event(
    body: EventCreate,
    ctx: AuthContext = Depends(get_auth_context),
):
    async with session_scope() as session:
        event = Event(
            tenant_id=ctx.tenant_id,
            channel_id=body.channel_id,
            user_id=ctx.user_id,
            event_type=body.event_type,
            payload=body.payload,
        )
        session.add(event)
        await session.flush()
        await session.refresh(event)
        return event


@router.get("", response_model=PaginatedResponse)
async def list_events(
    ctx: AuthContext = Depends(get_auth_context),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    channel_id: Optional[uuid.UUID] = Query(None),
    event_type: Optional[str] = Query(None),
):
    async with session_scope() as session:
        stmt = select(Event).where(Event.tenant_id == ctx.tenant_id)
        count_stmt = select(func.count(Event.id)).where(
            Event.tenant_id == ctx.tenant_id
        )

        if channel_id:
            stmt = stmt.where(Event.channel_id == channel_id)
            count_stmt = count_stmt.where(Event.channel_id == channel_id)
        if event_type:
            stmt = stmt.where(Event.event_type == event_type)
            count_stmt = count_stmt.where(Event.event_type == event_type)

        total_result = await session.execute(count_stmt)
        total = total_result.scalar() or 0
        pages = max(1, (total + page_size - 1) // page_size)

        stmt = (
            stmt.order_by(Event.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await session.execute(stmt)
        items = result.scalars().all()

        return PaginatedResponse(
            items=[EventRead.model_validate(e) for e in items],
            total=total,
            page=page,
            page_size=page_size,
            pages=pages,
        )
