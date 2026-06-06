"""IoT automation routes — Full CRUD for automation definitions.

Provides endpoints for listing, reading, creating, updating, and deleting
IoT automations, plus enable/disable toggling, manual triggering, and
trigger event history.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from services.common.auth import AuthContext, get_auth_context
from services.iot.database import get_session
from services.iot.models import IoTAutomation, IoTEvent

router = APIRouter()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TRIGGER_TYPES = ["state_change", "schedule", "event", "webhook", "manual"]


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class AutomationCreate(BaseModel):
    """Schema for creating a new automation."""
    name: str = Field(..., max_length=255)
    description: Optional[str] = None
    trigger_type: str = Field(..., description=f"One of: {', '.join(TRIGGER_TYPES)}")
    trigger_config: Optional[Dict[str, Any]] = Field(default_factory=dict)
    conditions: Optional[Dict[str, Any]] = Field(default_factory=dict)
    actions: Optional[Dict[str, Any]] = Field(default_factory=dict)
    is_enabled: bool = True
    is_custom: bool = True
    ha_automation_id: Optional[str] = Field(None, max_length=128)


class AutomationUpdate(BaseModel):
    """Schema for updating an existing automation (all fields optional)."""
    name: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    trigger_type: Optional[str] = Field(None, description=f"One of: {', '.join(TRIGGER_TYPES)}")
    trigger_config: Optional[Dict[str, Any]] = None
    conditions: Optional[Dict[str, Any]] = None
    actions: Optional[Dict[str, Any]] = None
    is_enabled: Optional[bool] = None
    is_custom: Optional[bool] = None
    ha_automation_id: Optional[str] = Field(None, max_length=128)


class AutomationRead(BaseModel):
    """Schema for automation responses."""
    id: uuid.UUID
    tenant_id: uuid.UUID
    ha_automation_id: Optional[str]
    name: str
    description: Optional[str]
    trigger_type: str
    trigger_config: Optional[Dict[str, Any]]
    conditions: Optional[Dict[str, Any]]
    actions: Optional[Dict[str, Any]]
    is_enabled: bool
    is_custom: bool
    last_triggered: Optional[datetime]
    trigger_count: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PaginatedAutomationResponse(BaseModel):
    items: List[AutomationRead]
    total: int
    page: int
    page_size: int
    pages: int


class AutomationTriggerResponse(BaseModel):
    """Response from manually triggering an automation."""
    automation_id: uuid.UUID
    triggered: bool
    triggered_at: datetime
    trigger_count: int
    message: str


class EventRead(BaseModel):
    """Schema for IoT event responses."""
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
    page: int
    page_size: int
    pages: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _automation_to_read(automation: IoTAutomation) -> AutomationRead:
    """Convert an IoTAutomation ORM instance to an AutomationRead schema."""
    return AutomationRead.model_validate(automation)


def _event_to_read(event: IoTEvent) -> EventRead:
    """Convert an IoTEvent ORM instance to an EventRead schema."""
    return EventRead.model_validate(event)


async def _get_automation_or_404(
    session, automation_id: uuid.UUID, tenant_id: uuid.UUID
) -> IoTAutomation:
    """Fetch an automation by ID scoped to tenant, or raise 404."""
    stmt = select(IoTAutomation).where(
        IoTAutomation.id == automation_id,
        IoTAutomation.tenant_id == tenant_id,
    )
    result = await session.execute(stmt)
    automation = result.scalar_one_or_none()
    if not automation:
        raise HTTPException(status_code=404, detail="Automation not found")
    return automation


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("", response_model=PaginatedAutomationResponse)
async def list_automations(
    ctx: AuthContext = Depends(get_auth_context),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    trigger_type: Optional[str] = Query(None, description="Filter by trigger type"),
    is_enabled: Optional[bool] = Query(None, description="Filter by enabled state"),
    is_custom: Optional[bool] = Query(None, description="Filter by custom flag"),
    search: Optional[str] = Query(None, description="Search by name or description"),
):
    """List IoT automations with optional filters and pagination."""
    async with get_session() as session:
        # Base query scoped to tenant
        stmt = select(IoTAutomation).where(
            IoTAutomation.tenant_id == ctx.tenant_id
        )

        # Apply filters
        if trigger_type:
            stmt = stmt.where(IoTAutomation.trigger_type == trigger_type)
        if is_enabled is not None:
            stmt = stmt.where(IoTAutomation.is_enabled == is_enabled)
        if is_custom is not None:
            stmt = stmt.where(IoTAutomation.is_custom == is_custom)
        if search:
            search_term = f"%{search}%"
            stmt = stmt.where(
                IoTAutomation.name.ilike(search_term)
                | IoTAutomation.description.ilike(search_term)
            )

        # Count total with same filters
        count_stmt = select(func.count(IoTAutomation.id)).where(
            IoTAutomation.tenant_id == ctx.tenant_id
        )
        if trigger_type:
            count_stmt = count_stmt.where(IoTAutomation.trigger_type == trigger_type)
        if is_enabled is not None:
            count_stmt = count_stmt.where(IoTAutomation.is_enabled == is_enabled)
        if is_custom is not None:
            count_stmt = count_stmt.where(IoTAutomation.is_custom == is_custom)
        if search:
            count_stmt = count_stmt.where(
                IoTAutomation.name.ilike(search_term)
                | IoTAutomation.description.ilike(search_term)
            )

        total_result = await session.execute(count_stmt)
        total = total_result.scalar() or 0
        pages = max(1, (total + page_size - 1) // page_size)

        # Paginated query
        stmt = (
            stmt.order_by(IoTAutomation.name.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await session.execute(stmt)
        automations = result.scalars().all()

        return PaginatedAutomationResponse(
            items=[_automation_to_read(a) for a in automations],
            total=total,
            page=page,
            page_size=page_size,
            pages=pages,
        )


@router.get("/{automation_id}", response_model=AutomationRead)
async def get_automation(
    automation_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Get a single automation by ID."""
    async with get_session() as session:
        automation = await _get_automation_or_404(session, automation_id, ctx.tenant_id)
        return _automation_to_read(automation)


@router.post("", response_model=AutomationRead, status_code=status.HTTP_201_CREATED)
async def create_automation(
    body: AutomationCreate,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Create a new IoT automation."""
    async with get_session() as session:
        automation = IoTAutomation(
            tenant_id=ctx.tenant_id,
            name=body.name,
            description=body.description,
            trigger_type=body.trigger_type,
            trigger_config=body.trigger_config or {},
            conditions=body.conditions or {},
            actions=body.actions or {},
            is_enabled=body.is_enabled,
            is_custom=body.is_custom,
            ha_automation_id=body.ha_automation_id,
        )
        session.add(automation)
        await session.flush()
        await session.refresh(automation)
        return _automation_to_read(automation)


@router.put("/{automation_id}", response_model=AutomationRead)
async def update_automation(
    automation_id: uuid.UUID,
    body: AutomationUpdate,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Update an existing IoT automation."""
    async with get_session() as session:
        automation = await _get_automation_or_404(session, automation_id, ctx.tenant_id)

        update_data = body.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(automation, field, value)

        await session.flush()
        await session.refresh(automation)
        return _automation_to_read(automation)


@router.delete("/{automation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_automation(
    automation_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Delete an IoT automation."""
    async with get_session() as session:
        automation = await _get_automation_or_404(session, automation_id, ctx.tenant_id)
        await session.delete(automation)


@router.post("/{automation_id}/enable", response_model=AutomationRead)
async def enable_automation(
    automation_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Enable an IoT automation."""
    async with get_session() as session:
        automation = await _get_automation_or_404(session, automation_id, ctx.tenant_id)
        automation.is_enabled = True
        await session.flush()
        await session.refresh(automation)
        return _automation_to_read(automation)


@router.post("/{automation_id}/disable", response_model=AutomationRead)
async def disable_automation(
    automation_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Disable an IoT automation."""
    async with get_session() as session:
        automation = await _get_automation_or_404(session, automation_id, ctx.tenant_id)
        automation.is_enabled = False
        await session.flush()
        await session.refresh(automation)
        return _automation_to_read(automation)


@router.post("/{automation_id}/trigger", response_model=AutomationTriggerResponse)
async def trigger_automation(
    automation_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Manually trigger an automation.

    Increments the trigger count, updates last_triggered timestamp,
    and creates an IoTEvent record for the manual trigger.
    """
    async with get_session() as session:
        automation = await _get_automation_or_404(session, automation_id, ctx.tenant_id)

        if not automation.is_enabled:
            raise HTTPException(
                status_code=400,
                detail="Cannot trigger a disabled automation. Enable it first.",
            )

        now = datetime.now(timezone.utc)
        automation.last_triggered = now
        automation.trigger_count += 1

        # Create an event record for the manual trigger
        event = IoTEvent(
            tenant_id=ctx.tenant_id,
            automation_id=automation.id,
            event_type="manual_trigger",
            source="api",
            message=f"Automation '{automation.name}' triggered manually by user {ctx.user_id}",
            data={
                "trigger_type": "manual",
                "user_id": str(ctx.user_id),
                "automation_name": automation.name,
            },
        )
        session.add(event)

        await session.flush()
        await session.refresh(automation)

        return AutomationTriggerResponse(
            automation_id=automation.id,
            triggered=True,
            triggered_at=now,
            trigger_count=automation.trigger_count,
            message=f"Automation '{automation.name}' triggered successfully",
        )


@router.get("/{automation_id}/history", response_model=PaginatedEventResponse)
async def get_automation_history(
    automation_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    source: Optional[str] = Query(None, description="Filter by event source"),
):
    """List trigger events for a specific automation."""
    async with get_session() as session:
        # Verify automation exists and belongs to tenant
        await _get_automation_or_404(session, automation_id, ctx.tenant_id)

        # Base query: events linked to this automation
        stmt = select(IoTEvent).where(
            IoTEvent.tenant_id == ctx.tenant_id,
            IoTEvent.automation_id == automation_id,
        )

        if event_type:
            stmt = stmt.where(IoTEvent.event_type == event_type)
        if source:
            stmt = stmt.where(IoTEvent.source == source)

        # Count total
        count_stmt = select(func.count(IoTEvent.id)).where(
            IoTEvent.tenant_id == ctx.tenant_id,
            IoTEvent.automation_id == automation_id,
        )
        if event_type:
            count_stmt = count_stmt.where(IoTEvent.event_type == event_type)
        if source:
            count_stmt = count_stmt.where(IoTEvent.source == source)

        total_result = await session.execute(count_stmt)
        total = total_result.scalar() or 0
        pages = max(1, (total + page_size - 1) // page_size)

        # Paginated query, newest first
        stmt = (
            stmt.order_by(IoTEvent.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await session.execute(stmt)
        events = result.scalars().all()

        return PaginatedEventResponse(
            items=[_event_to_read(e) for e in events],
            total=total,
            page=page,
            page_size=page_size,
            pages=pages,
        )
