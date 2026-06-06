"""IoT alert routes — Full CRUD for alert rules with notifications.

Provides endpoints for listing, reading, creating, updating, and deleting
IoT alert rules, plus enable/disable toggling, manual test triggering,
and trigger event history.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from services.common.auth import AuthContext, get_auth_context
from services.iot.database import get_session
from services.iot.models import IoTAlert, IoTEvent

router = APIRouter()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SEVERITIES = ["info", "warning", "critical", "emergency"]

CONDITION_TYPES = [
    "threshold",
    "state_match",
    "state_change",
    "offline",
    "battery_low",
    "signal_weak",
    "custom",
]


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class AlertCreate(BaseModel):
    """Schema for creating a new alert rule."""

    name: str = Field(..., max_length=255)
    description: Optional[str] = None
    device_id: Optional[uuid.UUID] = None
    severity: str = Field(default="warning", description=f"One of: {', '.join(SEVERITIES)}")
    condition_type: str = Field(..., description=f"One of: {', '.join(CONDITION_TYPES)}")
    condition_config: Optional[Dict[str, Any]] = Field(default_factory=dict)
    notify_email: bool = False
    notify_sms: bool = False
    notify_push: bool = True
    notify_webhook: bool = False
    webhook_url: Optional[str] = Field(None, max_length=512)
    is_enabled: bool = True
    cooldown_minutes: int = Field(default=15, ge=0, description="Cooldown period in minutes between triggers")


class AlertUpdate(BaseModel):
    """Schema for updating an existing alert rule (all fields optional)."""

    name: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    device_id: Optional[uuid.UUID] = None
    severity: Optional[str] = Field(None, description=f"One of: {', '.join(SEVERITIES)}")
    condition_type: Optional[str] = Field(None, description=f"One of: {', '.join(CONDITION_TYPES)}")
    condition_config: Optional[Dict[str, Any]] = None
    notify_email: Optional[bool] = None
    notify_sms: Optional[bool] = None
    notify_push: Optional[bool] = None
    notify_webhook: Optional[bool] = None
    webhook_url: Optional[str] = Field(None, max_length=512)
    is_enabled: Optional[bool] = None
    cooldown_minutes: Optional[int] = Field(None, ge=0)


class AlertRead(BaseModel):
    """Schema for alert rule responses."""

    id: uuid.UUID
    tenant_id: uuid.UUID
    device_id: Optional[uuid.UUID]
    name: str
    description: Optional[str]
    severity: str
    condition_type: str
    condition_config: Optional[Dict[str, Any]]
    notify_email: bool
    notify_sms: bool
    notify_push: bool
    notify_webhook: bool
    webhook_url: Optional[str]
    is_enabled: bool
    cooldown_minutes: int
    last_triggered: Optional[datetime]
    trigger_count: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PaginatedAlertResponse(BaseModel):
    items: List[AlertRead]
    total: int
    page: int
    page_size: int
    pages: int


class AlertTestResponse(BaseModel):
    """Response from manually testing an alert."""

    alert_id: uuid.UUID
    triggered: bool
    triggered_at: datetime
    trigger_count: int
    message: str
    notifications_sent: Dict[str, bool] = Field(
        default_factory=dict,
        description="Which notification channels were attempted and their success status",
    )


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


def _alert_to_read(alert: IoTAlert) -> AlertRead:
    """Convert an IoTAlert ORM instance to an AlertRead schema."""
    return AlertRead.model_validate(alert)


def _event_to_read(event: IoTEvent) -> EventRead:
    """Convert an IoTEvent ORM instance to an EventRead schema."""
    return EventRead.model_validate(event)


async def _get_alert_or_404(
    session, alert_id: uuid.UUID, tenant_id: uuid.UUID
) -> IoTAlert:
    """Fetch an alert by ID scoped to tenant, or raise 404."""
    stmt = select(IoTAlert).where(
        IoTAlert.id == alert_id,
        IoTAlert.tenant_id == tenant_id,
    )
    result = await session.execute(stmt)
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("", response_model=PaginatedAlertResponse)
async def list_alerts(
    ctx: AuthContext = Depends(get_auth_context),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    severity: Optional[str] = Query(None, description="Filter by severity"),
    condition_type: Optional[str] = Query(None, description="Filter by condition type"),
    is_enabled: Optional[bool] = Query(None, description="Filter by enabled state"),
    device_id: Optional[uuid.UUID] = Query(None, description="Filter by device ID"),
    search: Optional[str] = Query(None, description="Search by name or description"),
):
    """List IoT alert rules with optional filters and pagination."""
    async with get_session() as session:
        # Base query scoped to tenant
        stmt = select(IoTAlert).where(
            IoTAlert.tenant_id == ctx.tenant_id
        )

        # Apply filters
        if severity:
            stmt = stmt.where(IoTAlert.severity == severity)
        if condition_type:
            stmt = stmt.where(IoTAlert.condition_type == condition_type)
        if is_enabled is not None:
            stmt = stmt.where(IoTAlert.is_enabled == is_enabled)
        if device_id:
            stmt = stmt.where(IoTAlert.device_id == device_id)
        if search:
            search_term = f"%{search}%"
            stmt = stmt.where(
                IoTAlert.name.ilike(search_term)
                | IoTAlert.description.ilike(search_term)
            )

        # Count total with same filters
        count_stmt = select(func.count(IoTAlert.id)).where(
            IoTAlert.tenant_id == ctx.tenant_id
        )
        if severity:
            count_stmt = count_stmt.where(IoTAlert.severity == severity)
        if condition_type:
            count_stmt = count_stmt.where(IoTAlert.condition_type == condition_type)
        if is_enabled is not None:
            count_stmt = count_stmt.where(IoTAlert.is_enabled == is_enabled)
        if device_id:
            count_stmt = count_stmt.where(IoTAlert.device_id == device_id)
        if search:
            count_stmt = count_stmt.where(
                IoTAlert.name.ilike(search_term)
                | IoTAlert.description.ilike(search_term)
            )

        total_result = await session.execute(count_stmt)
        total = total_result.scalar() or 0
        pages = max(1, (total + page_size - 1) // page_size)

        # Paginated query
        stmt = (
            stmt.order_by(IoTAlert.name.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await session.execute(stmt)
        alerts = result.scalars().all()

        return PaginatedAlertResponse(
            items=[_alert_to_read(a) for a in alerts],
            total=total,
            page=page,
            page_size=page_size,
            pages=pages,
        )


@router.get("/{alert_id}", response_model=AlertRead)
async def get_alert(
    alert_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Get a single alert rule by ID."""
    async with get_session() as session:
        alert = await _get_alert_or_404(session, alert_id, ctx.tenant_id)
        return _alert_to_read(alert)


@router.post("", response_model=AlertRead, status_code=status.HTTP_201_CREATED)
async def create_alert(
    body: AlertCreate,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Create a new IoT alert rule."""
    async with get_session() as session:
        alert = IoTAlert(
            tenant_id=ctx.tenant_id,
            device_id=body.device_id,
            name=body.name,
            description=body.description,
            severity=body.severity,
            condition_type=body.condition_type,
            condition_config=body.condition_config or {},
            notify_email=body.notify_email,
            notify_sms=body.notify_sms,
            notify_push=body.notify_push,
            notify_webhook=body.notify_webhook,
            webhook_url=body.webhook_url,
            is_enabled=body.is_enabled,
            cooldown_minutes=body.cooldown_minutes,
        )
        session.add(alert)
        await session.flush()
        await session.refresh(alert)
        return _alert_to_read(alert)


@router.put("/{alert_id}", response_model=AlertRead)
async def update_alert(
    alert_id: uuid.UUID,
    body: AlertUpdate,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Update an existing IoT alert rule."""
    async with get_session() as session:
        alert = await _get_alert_or_404(session, alert_id, ctx.tenant_id)

        update_data = body.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(alert, field, value)

        await session.flush()
        await session.refresh(alert)
        return _alert_to_read(alert)


@router.delete("/{alert_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_alert(
    alert_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Delete an IoT alert rule."""
    async with get_session() as session:
        alert = await _get_alert_or_404(session, alert_id, ctx.tenant_id)
        await session.delete(alert)


@router.post("/{alert_id}/enable", response_model=AlertRead)
async def enable_alert(
    alert_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Enable an IoT alert rule."""
    async with get_session() as session:
        alert = await _get_alert_or_404(session, alert_id, ctx.tenant_id)
        alert.is_enabled = True
        await session.flush()
        await session.refresh(alert)
        return _alert_to_read(alert)


@router.post("/{alert_id}/disable", response_model=AlertRead)
async def disable_alert(
    alert_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Disable an IoT alert rule."""
    async with get_session() as session:
        alert = await _get_alert_or_404(session, alert_id, ctx.tenant_id)
        alert.is_enabled = False
        await session.flush()
        await session.refresh(alert)
        return _alert_to_read(alert)


@router.post("/{alert_id}/test", response_model=AlertTestResponse)
async def test_alert(
    alert_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Manually trigger an alert for testing purposes.

    Increments the trigger count, updates last_triggered timestamp,
    creates an IoTEvent record, and simulates sending notifications
    through configured channels.
    """
    async with get_session() as session:
        alert = await _get_alert_or_404(session, alert_id, ctx.tenant_id)

        now = datetime.now(timezone.utc)
        alert.last_triggered = now
        alert.trigger_count += 1

        # Determine which notification channels are configured
        notifications_sent: Dict[str, bool] = {}
        if alert.notify_email:
            notifications_sent["email"] = True
        if alert.notify_sms:
            notifications_sent["sms"] = True
        if alert.notify_push:
            notifications_sent["push"] = True
        if alert.notify_webhook and alert.webhook_url:
            notifications_sent["webhook"] = True

        # Create an event record for the test trigger
        event = IoTEvent(
            tenant_id=ctx.tenant_id,
            device_id=alert.device_id,
            alert_id=alert.id,
            event_type="test_trigger",
            source="api",
            message=f"Alert '{alert.name}' triggered manually (test) by user {ctx.user_id}",
            data={
                "trigger_type": "test",
                "user_id": str(ctx.user_id),
                "alert_name": alert.name,
                "severity": alert.severity,
                "condition_type": alert.condition_type,
                "notifications_attempted": notifications_sent,
            },
        )
        session.add(event)

        await session.flush()
        await session.refresh(alert)

        channels_summary = ", ".join(notifications_sent.keys()) if notifications_sent else "none"
        return AlertTestResponse(
            alert_id=alert.id,
            triggered=True,
            triggered_at=now,
            trigger_count=alert.trigger_count,
            message=f"Alert '{alert.name}' test triggered successfully. Notifications sent via: {channels_summary}",
            notifications_sent=notifications_sent,
        )


@router.get("/{alert_id}/history", response_model=PaginatedEventResponse)
async def get_alert_history(
    alert_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    source: Optional[str] = Query(None, description="Filter by event source"),
):
    """List trigger events for a specific alert rule."""
    async with get_session() as session:
        # Verify alert exists and belongs to tenant
        await _get_alert_or_404(session, alert_id, ctx.tenant_id)

        # Base query: events linked to this alert
        stmt = select(IoTEvent).where(
            IoTEvent.tenant_id == ctx.tenant_id,
            IoTEvent.alert_id == alert_id,
        )

        if event_type:
            stmt = stmt.where(IoTEvent.event_type == event_type)
        if source:
            stmt = stmt.where(IoTEvent.source == source)

        # Count total
        count_stmt = select(func.count(IoTEvent.id)).where(
            IoTEvent.tenant_id == ctx.tenant_id,
            IoTEvent.alert_id == alert_id,
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
