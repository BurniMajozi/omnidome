"""Schedule Event routes — CRUD for calendar / scheduling."""

import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from services.common.auth import AuthContext, get_auth_context
from services.communication.access import get_visible_channel, has_tier, validate_refs, validate_tenant_users, visible_clause
from services.communication.database import get_session
from services.communication.models import ScheduleEvent
from services.communication.schemas import (
    PaginatedResponse,
    ScheduleEventCreate,
    ScheduleEventRead,
    ScheduleEventUpdate,
)

router = APIRouter(prefix="/schedule", tags=["Schedule"])


def _validate_times(start: datetime, end: datetime) -> None:
    if start.tzinfo is None or end.tzinfo is None:
        raise HTTPException(status_code=422, detail="start_time and end_time must include a timezone")
    if end <= start:
        raise HTTPException(status_code=422, detail="end_time must be after start_time")


# ---------------------------------------------------------------------------
# POST /schedule — Create a schedule event
# ---------------------------------------------------------------------------

@router.post("", response_model=ScheduleEventRead, status_code=status.HTTP_201_CREATED)
async def create_event(
    body: ScheduleEventCreate,
    ctx: AuthContext = Depends(get_auth_context),
):
    _validate_times(body.start_time, body.end_time)

    async with get_session() as session:
        # access check, validation and write share one session/transaction
        await validate_refs(session, ctx, body.channel_id, body.source_message_id)
        owner_id = ctx.user_id
        if body.user_id and body.user_id != ctx.user_id:
            if not await has_tier(ctx, session, "admin"):
                raise HTTPException(status_code=403, detail="Only admins can schedule events for another user")
            if await validate_tenant_users(session, ctx.tenant_id, [body.user_id]):
                raise HTTPException(status_code=422, detail="User does not belong to this tenant")
            owner_id = body.user_id
        event = ScheduleEvent(
            tenant_id=ctx.tenant_id,
            channel_id=body.channel_id,
            user_id=owner_id,
            title=body.title,
            type=body.type,
            start_time=body.start_time,
            end_time=body.end_time,
            date_label=body.date_label,
            time_label=body.time_label,
            notes=body.notes,
            source_message_id=body.source_message_id,
            linked_task_id=body.linked_task_id,
            status=body.status or "upcoming",
            created_by=ctx.user_id,
        )
        session.add(event)
        await session.flush()
        await session.refresh(event)
        return event


# ---------------------------------------------------------------------------
# GET /schedule — List events (filter by channel, time range, status)
# ---------------------------------------------------------------------------

@router.get("", response_model=PaginatedResponse)
async def list_events(
    ctx: AuthContext = Depends(get_auth_context),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    channel_id: Optional[uuid.UUID] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    start_from: Optional[datetime] = Query(None),
    start_to: Optional[datetime] = Query(None),
):
    from sqlalchemy import select, func

    async with get_session() as session:
        from services.communication.models import Channel

        vis = select(Channel.id).where(await visible_clause(session, ctx))
        stmt = select(ScheduleEvent).where(ScheduleEvent.tenant_id == ctx.tenant_id, ScheduleEvent.channel_id.in_(vis))
        count_stmt = select(func.count(ScheduleEvent.id)).where(
            ScheduleEvent.tenant_id == ctx.tenant_id, ScheduleEvent.channel_id.in_(vis)
        )

        if channel_id:
            stmt = stmt.where(ScheduleEvent.channel_id == channel_id)
            count_stmt = count_stmt.where(ScheduleEvent.channel_id == channel_id)
        if status_filter:
            stmt = stmt.where(ScheduleEvent.status == status_filter)
            count_stmt = count_stmt.where(ScheduleEvent.status == status_filter)
        if start_from:
            stmt = stmt.where(ScheduleEvent.start_time >= start_from)
            count_stmt = count_stmt.where(ScheduleEvent.start_time >= start_from)
        if start_to:
            stmt = stmt.where(ScheduleEvent.start_time <= start_to)
            count_stmt = count_stmt.where(ScheduleEvent.start_time <= start_to)

        total_result = await session.execute(count_stmt)
        total = total_result.scalar() or 0
        pages = max(1, (total + page_size - 1) // page_size)

        stmt = (
            stmt.order_by(ScheduleEvent.start_time.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await session.execute(stmt)
        items = result.scalars().all()

        return PaginatedResponse(
            items=[ScheduleEventRead.model_validate(e) for e in items],
            total=total,
            page=page,
            page_size=page_size,
            pages=pages,
        )


# ---------------------------------------------------------------------------
# GET /schedule/{event_id} — Get a single event
# ---------------------------------------------------------------------------

@router.get("/{event_id}", response_model=ScheduleEventRead)
async def get_event(
    event_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    from sqlalchemy import select

    async with get_session() as session:
        stmt = select(ScheduleEvent).where(
            ScheduleEvent.id == event_id, ScheduleEvent.tenant_id == ctx.tenant_id
        )
        result = await session.execute(stmt)
        event = result.scalar_one_or_none()
        if not event:
            raise HTTPException(status_code=404, detail="Schedule event not found")
        await get_visible_channel(session, ctx, event.channel_id)
        return event


# ---------------------------------------------------------------------------
# PUT /schedule/{event_id} — Update an event
# ---------------------------------------------------------------------------

@router.put("/{event_id}", response_model=ScheduleEventRead)
async def update_event(
    event_id: uuid.UUID,
    body: ScheduleEventUpdate,
    ctx: AuthContext = Depends(get_auth_context),
):
    from sqlalchemy import select

    async with get_session() as session:
        stmt = select(ScheduleEvent).where(
            ScheduleEvent.id == event_id, ScheduleEvent.tenant_id == ctx.tenant_id
        )
        result = await session.execute(stmt)
        event = result.scalar_one_or_none()
        if not event:
            raise HTTPException(status_code=404, detail="Schedule event not found")
        await get_visible_channel(session, ctx, event.channel_id)

        update_data = body.model_dump(exclude_unset=True)
        if "channel_id" in update_data and update_data["channel_id"] != event.channel_id:
            await validate_refs(session, ctx, update_data["channel_id"])
        _validate_times(update_data.get("start_time", event.start_time), update_data.get("end_time", event.end_time))
        for field, value in update_data.items():
            setattr(event, field, value)
        await session.flush()
        await session.refresh(event)
        return event


# ---------------------------------------------------------------------------
# DELETE /schedule/{event_id} — Delete an event
# ---------------------------------------------------------------------------

@router.delete("/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_event(
    event_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    from sqlalchemy import select

    async with get_session() as session:
        stmt = select(ScheduleEvent).where(
            ScheduleEvent.id == event_id, ScheduleEvent.tenant_id == ctx.tenant_id
        )
        result = await session.execute(stmt)
        event = result.scalar_one_or_none()
        if not event:
            raise HTTPException(status_code=404, detail="Schedule event not found")
        await get_visible_channel(session, ctx, event.channel_id)
        await session.delete(event)
