"""IoT event routes — Event log listing, retrieval, creation, and SSE streaming.

Provides endpoints for:
- GET /api/iot/events — List events with filters (device_id, event_type, from, to, limit)
- GET /api/iot/events/{id} — Get a single event by ID
- GET /api/iot/events/stream — SSE stream for real-time event notifications
- POST /api/iot/events — Create a manual event
"""

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from starlette.responses import StreamingResponse

from services.common.auth import AuthContext, get_auth_context
from services.iot.database import get_session
from services.iot.models import IoTEvent

router = APIRouter()

# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class EventCreate(BaseModel):
    """Schema for creating a manual event."""
    device_id: Optional[uuid.UUID] = Field(None, description="Associated device ID")
    event_type: str = Field(..., max_length=64, description="Event type identifier, e.g. manual, state_change, trigger, alert")
    source: str = Field("manual", max_length=64, description="Event source: manual, ha, automation, system")
    message: Optional[str] = Field(None, description="Human-readable event message")
    data: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Arbitrary JSON event payload")


class EventRead(BaseModel):
    """Schema for event responses."""
    id: uuid.UUID
    tenant_id: uuid.UUID
    device_id: Optional[uuid.UUID]
    automation_id: Optional[uuid.UUID]
    alert_id: Optional[uuid.UUID]
    event_type: str
    source: str
    message: Optional[str]
    data: Optional[Dict[str, Any]]
    created_at: datetime

    class Config:
        from_attributes = True


class PaginatedEventResponse(BaseModel):
    items: List[EventRead]
    total: int
    limit: int
    offset: int


# ---------------------------------------------------------------------------
# SSE event queue (in-memory pub/sub per process)
# ---------------------------------------------------------------------------

_event_queues: Dict[uuid.UUID, asyncio.Queue] = {}


def _get_queue(tenant_id: uuid.UUID) -> asyncio.Queue:
    """Get or create an event queue for the given tenant."""
    if tenant_id not in _event_queues:
        _event_queues[tenant_id] = asyncio.Queue(maxsize=1000)
    return _event_queues[tenant_id]


async def publish_event(event: IoTEvent) -> None:
    """Publish an event to the tenant's SSE stream (called by event producers)."""
    queue = _get_queue(event.tenant_id)
    payload = json.dumps(
        {
            "id": str(event.id),
            "device_id": str(event.device_id) if event.device_id else None,
            "automation_id": str(event.automation_id) if event.automation_id else None,
            "alert_id": str(event.alert_id) if event.alert_id else None,
            "event_type": event.event_type,
            "source": event.source,
            "message": event.message,
            "data": event.data,
            "created_at": event.created_at.isoformat() if event.created_at else None,
        },
        default=str,
    )
    try:
        queue.put_nowait(payload)
    except asyncio.QueueFull:
        # Drop oldest message to make room
        try:
            queue.get_nowait()
        except asyncio.QueueEmpty:
            pass
        try:
            queue.put_nowait(payload)
        except asyncio.QueueFull:
            pass


async def _sse_event_generator(tenant_id: uuid.UUID) -> AsyncGenerator[str, None]:
    """Yield SSE-formatted event payloads for the tenant's event stream."""
    queue = _get_queue(tenant_id)
    # Send initial connection event
    yield f"event: connected\ndata: {json.dumps({'tenant_id': str(tenant_id)})}\n\n"
    while True:
        try:
            payload = await asyncio.wait_for(queue.get(), timeout=30.0)
            yield f"event: iot_event\ndata: {payload}\n\n"
        except asyncio.TimeoutError:
            # Send keep-alive comment to prevent proxy timeouts
            yield ": keep-alive\n\n"


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("", response_model=PaginatedEventResponse)
async def list_events(
    ctx: AuthContext = Depends(get_auth_context),
    device_id: Optional[uuid.UUID] = Query(None, description="Filter by device ID"),
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    source: Optional[str] = Query(None, description="Filter by event source"),
    from_time: Optional[datetime] = Query(None, alias="from", description="Start of time range (inclusive)"),
    to_time: Optional[datetime] = Query(None, alias="to", description="End of time range (inclusive)"),
    limit: int = Query(50, ge=1, le=500, description="Maximum number of events to return"),
    offset: int = Query(0, ge=0, description="Number of events to skip"),
):
    """List IoT events with optional filters and pagination.

    Results are ordered by created_at descending (most recent first).
    All queries are scoped to the authenticated tenant.
    """
    async with get_session() as session:
        # Base query scoped to tenant
        stmt = select(IoTEvent).where(IoTEvent.tenant_id == ctx.tenant_id)

        # Apply filters
        if device_id:
            stmt = stmt.where(IoTEvent.device_id == device_id)
        if event_type:
            stmt = stmt.where(IoTEvent.event_type == event_type)
        if source:
            stmt = stmt.where(IoTEvent.source == source)
        if from_time:
            stmt = stmt.where(IoTEvent.created_at >= from_time)
        if to_time:
            stmt = stmt.where(IoTEvent.created_at <= to_time)

        # Count total matching rows
        count_stmt = select(func.count(IoTEvent.id)).where(
            IoTEvent.tenant_id == ctx.tenant_id
        )
        if device_id:
            count_stmt = count_stmt.where(IoTEvent.device_id == device_id)
        if event_type:
            count_stmt = count_stmt.where(IoTEvent.event_type == event_type)
        if source:
            count_stmt = count_stmt.where(IoTEvent.source == source)
        if from_time:
            count_stmt = count_stmt.where(IoTEvent.created_at >= from_time)
        if to_time:
            count_stmt = count_stmt.where(IoTEvent.created_at <= to_time)

        total_result = await session.execute(count_stmt)
        total = total_result.scalar() or 0

        # Paginated query — newest first
        stmt = (
            stmt.order_by(IoTEvent.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await session.execute(stmt)
        events = result.scalars().all()

        return PaginatedEventResponse(
            items=[EventRead.model_validate(e) for e in events],
            total=total,
            limit=limit,
            offset=offset,
        )


@router.get("/{event_id}", response_model=EventRead)
async def get_event(
    event_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Get a single IoT event by ID."""
    async with get_session() as session:
        stmt = select(IoTEvent).where(
            IoTEvent.id == event_id,
            IoTEvent.tenant_id == ctx.tenant_id,
        )
        result = await session.execute(stmt)
        event = result.scalar_one_or_none()
        if not event:
            raise HTTPException(status_code=404, detail="Event not found")
        return EventRead.model_validate(event)


@router.get("/stream")
async def stream_events(
    ctx: AuthContext = Depends(get_auth_context),
):
    """Server-Sent Events (SSE) stream for real-time IoT events.

    Streams new events as they are published via `publish_event()`.
    Sends a `connected` event on initial connection and periodic
    keep-alive comments to prevent proxy timeouts.

    SSE event types:
    - `connected` — sent once on connection
    - `iot_event` — sent for each new event
    """
    return StreamingResponse(
        _sse_event_generator(ctx.tenant_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("", response_model=EventRead, status_code=status.HTTP_201_CREATED)
async def create_event(
    body: EventCreate,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Create a manual event in the IoT event log.

    The event is scoped to the authenticated tenant and published
    to the SSE stream for real-time subscribers.
    """
    async with get_session() as session:
        event = IoTEvent(
            tenant_id=ctx.tenant_id,
            device_id=body.device_id,
            event_type=body.event_type,
            source=body.source,
            message=body.message,
            data=body.data or {},
        )
        session.add(event)
        await session.flush()
        await session.refresh(event)

        # Publish to SSE stream
        await publish_event(event)

        return EventRead.model_validate(event)
