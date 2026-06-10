"""Network notification management routes.

Provides:
- Notification CRUD and dispatch
- Notification preferences per customer
- Integration triggers for FNO outages, SLA breaches, billing events
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select, func

from services.common.auth import AuthContext, get_auth_context
from services.network.database import get_session
from services.network.models import NetworkNotification, NetworkService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/notifications", tags=["Notifications"])


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class NotificationCreate(BaseModel):
    service_id: Optional[uuid.UUID] = None
    customer_id: Optional[uuid.UUID] = None
    trigger_type: str
    trigger_id: Optional[uuid.UUID] = None
    severity: str = "info"
    title: str = Field(..., max_length=500)
    message: Optional[str] = None
    channel: str
    recipient: str


class NotificationRead(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    service_id: Optional[uuid.UUID]
    customer_id: Optional[uuid.UUID]
    trigger_type: str
    trigger_id: Optional[uuid.UUID]
    severity: str
    title: str
    message: Optional[str]
    channel: str
    recipient: str
    status: str
    sent_at: Optional[datetime]
    read_at: Optional[datetime]
    retry_count: int
    error_message: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class NotificationDispatch(BaseModel):
    """Bulk dispatch notification to multiple recipients."""
    trigger_type: str
    trigger_id: Optional[uuid.UUID] = None
    severity: str = "info"
    title: str = Field(..., max_length=500)
    message: Optional[str] = None
    channel: str
    # If service_id provided, looks up customer contact details
    service_id: Optional[uuid.UUID] = None
    # Otherwise provide explicit recipients
    recipients: list[str] = Field(default_factory=list)


class PaginatedNotificationResponse(BaseModel):
    items: list[NotificationRead]
    total: int
    page: int
    page_size: int


# ---------------------------------------------------------------------------
# Notification CRUD
# ---------------------------------------------------------------------------

@router.post("", response_model=NotificationRead, status_code=status.HTTP_201_CREATED)
async def create_notification(
    body: NotificationCreate,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Create a notification record."""
    with get_session() as session:
        notification = NetworkNotification(
            tenant_id=ctx.tenant_id,
            service_id=body.service_id,
            customer_id=body.customer_id,
            trigger_type=body.trigger_type,
            trigger_id=body.trigger_id,
            severity=body.severity,
            title=body.title,
            message=body.message,
            channel=body.channel,
            recipient=body.recipient,
        )
        session.add(notification)
        session.flush()
        session.refresh(notification)
        return NotificationRead.model_validate(notification)


@router.post("/dispatch", status_code=status.HTTP_202_ACCEPTED)
async def dispatch_notification(
    body: NotificationDispatch,
    background_tasks: BackgroundTasks,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Dispatch a notification to one or more recipients via background task."""
    with get_session() as session:
        recipients = body.recipients
        service_customer_id = None

        # If service_id provided, look up customer contact
        if body.service_id:
            svc = session.execute(
                select(NetworkService).where(
                    NetworkService.id == body.service_id,
                    NetworkService.tenant_id == ctx.tenant_id,
                )
            ).scalar_one_or_none()
            if svc:
                service_customer_id = svc.customer_id
                # TODO: look up customer contact details from CRM
                # For now, use placeholder
                if not recipients:
                    recipients = ["customer@example.com"]

        notifications = []
        for recipient in recipients:
            notification = NetworkNotification(
                tenant_id=ctx.tenant_id,
                service_id=body.service_id,
                customer_id=service_customer_id,
                trigger_type=body.trigger_type,
                trigger_id=body.trigger_id,
                severity=body.severity,
                title=body.title,
                message=body.message,
                channel=body.channel,
                recipient=recipient,
            )
            session.add(notification)
            notifications.append(notification)

        session.flush()

        # Dispatch in background
        for n in notifications:
            background_tasks.add_task(_send_notification, n.id)

        return {
            "dispatched": len(notifications),
            "channel": body.channel,
            "recipients": len(recipients),
        }


@router.get("", response_model=PaginatedNotificationResponse)
async def list_notifications(
    ctx: AuthContext = Depends(get_auth_context),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: Optional[str] = Query(None, alias="status"),
    severity: Optional[str] = None,
    service_id: Optional[uuid.UUID] = None,
    customer_id: Optional[uuid.UUID] = None,
    trigger_type: Optional[str] = None,
):
    """List notifications with filters."""
    with get_session() as session:
        stmt = select(NetworkNotification).where(
            NetworkNotification.tenant_id == ctx.tenant_id
        )
        count_stmt = select(func.count(NetworkNotification.id)).where(
            NetworkNotification.tenant_id == ctx.tenant_id
        )

        if status_filter:
            stmt = stmt.where(NetworkNotification.status == status_filter)
            count_stmt = count_stmt.where(NetworkNotification.status == status_filter)
        if severity:
            stmt = stmt.where(NetworkNotification.severity == severity)
            count_stmt = count_stmt.where(NetworkNotification.severity == severity)
        if service_id:
            stmt = stmt.where(NetworkNotification.service_id == service_id)
            count_stmt = count_stmt.where(NetworkNotification.service_id == service_id)
        if customer_id:
            stmt = stmt.where(NetworkNotification.customer_id == customer_id)
            count_stmt = count_stmt.where(NetworkNotification.customer_id == customer_id)
        if trigger_type:
            stmt = stmt.where(NetworkNotification.trigger_type == trigger_type)
            count_stmt = count_stmt.where(NetworkNotification.trigger_type == trigger_type)

        total = session.execute(count_stmt).scalar() or 0
        stmt = stmt.order_by(NetworkNotification.created_at.desc()).offset(
            (page - 1) * page_size
        ).limit(page_size)
        result = session.execute(stmt)

        return PaginatedNotificationResponse(
            items=[NotificationRead.model_validate(n) for n in result.scalars().all()],
            total=total,
            page=page,
            page_size=page_size,
        )


@router.get("/{notification_id}", response_model=NotificationRead)
async def get_notification(
    notification_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    with get_session() as session:
        notification = session.execute(
            select(NetworkNotification).where(
                NetworkNotification.id == notification_id,
                NetworkNotification.tenant_id == ctx.tenant_id,
            )
        ).scalar_one_or_none()
        if not notification:
            raise HTTPException(status_code=404, detail="Notification not found")
        return NotificationRead.model_validate(notification)


@router.post("/{notification_id}/retry")
async def retry_notification(
    notification_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Retry sending a failed notification."""
    with get_session() as session:
        notification = session.execute(
            select(NetworkNotification).where(
                NetworkNotification.id == notification_id,
                NetworkNotification.tenant_id == ctx.tenant_id,
            )
        ).scalar_one_or_none()
        if not notification:
            raise HTTPException(status_code=404, detail="Notification not found")
        if notification.status not in ("failed", "pending"):
            raise HTTPException(status_code=400, detail=f"Cannot retry notification in '{notification.status}' state")
        if notification.retry_count >= notification.max_retries:
            raise HTTPException(status_code=400, detail="Max retries exceeded")

        notification.retry_count += 1
        notification.status = "pending"
        notification.error_message = None
        session.flush()

        background_tasks.add_task(_send_notification, notification.id)
        return {"id": str(notification.id), "retry_count": notification.retry_count}


@router.post("/{notification_id}/mark-read")
async def mark_notification_read(
    notification_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Mark a notification as read."""
    with get_session() as session:
        notification = session.execute(
            select(NetworkNotification).where(
                NetworkNotification.id == notification_id,
                NetworkNotification.tenant_id == ctx.tenant_id,
            )
        ).scalar_one_or_none()
        if not notification:
            raise HTTPException(status_code=404, detail="Notification not found")
        notification.status = "read"
        notification.read_at = datetime.now(timezone.utc)
        session.flush()
        return {"id": str(notification.id), "status": "read"}


# ---------------------------------------------------------------------------
# Background dispatch
# ---------------------------------------------------------------------------

async def _send_notification(notification_id: uuid.UUID):
    """Background task to send a notification via the appropriate channel."""
    # In production, this would:
    # - Email: use SMTP or SendGrid API
    # - SMS: use Twilio or Clickatell API
    # - Push: use Firebase Cloud Messaging
    # - Webhook: POST to the webhook URL
    # - In-app: store for the user's inbox

    from services.network.database import get_session as _get_session
    async with _get_session() as session:
        notification = session.execute(
            select(NetworkNotification).where(NetworkNotification.id == notification_id)
        ).scalar_one_or_none()
        if not notification:
            return

        try:
            if notification.channel == "email":
                # TODO: integrate with email service
                logger.info(f"Sending email to {notification.recipient}: {notification.title}")
            elif notification.channel == "sms":
                # TODO: integrate with SMS gateway
                logger.info(f"Sending SMS to {notification.recipient}: {notification.title}")
            elif notification.channel == "push":
                # TODO: integrate with FCM
                logger.info(f"Sending push to {notification.recipient}: {notification.title}")
            elif notification.channel == "webhook":
                # TODO: POST to webhook URL
                logger.info(f"POSTing webhook to {notification.recipient}: {notification.title}")
            elif notification.channel == "in_app":
                # Already stored, just mark as sent
                pass

            notification.status = "sent"
            notification.sent_at = datetime.now(timezone.utc)
        except Exception as exc:
            notification.status = "failed"
            notification.error_message = str(exc)
            logger.error(f"Failed to send notification {notification_id}: {exc}")

        session.flush()


# ---------------------------------------------------------------------------
# Trigger helpers (called by other services)
# ---------------------------------------------------------------------------

async def notify_fno_outage(tenant_id: uuid.UUID, fno_name: str, affected_areas: list[str],
                             severity: str, title: str, message: str):
    """Create notifications for all services affected by an FNO outage."""
    from services.network.database import get_session as _get_session
    async with _get_session() as session:
        # Find all active services for this FNO
        services = session.execute(
            select(NetworkService).where(
                NetworkService.tenant_id == tenant_id,
                NetworkService.fno_provider == fno_name.lower(),
                NetworkService.status == "active",
            )
        ).scalars().all()

        for svc in services:
            notification = NetworkNotification(
                tenant_id=tenant_id,
                service_id=svc.id,
                customer_id=svc.customer_id,
                trigger_type="fno_outage",
                severity=severity,
                title=title,
                message=message,
                channel="in_app",
                recipient=str(svc.customer_id),
            )
            session.add(notification)
        session.flush()
        return len(services)


async def notify_sla_breach(tenant_id: uuid.UUID, service_id: uuid.UUID,
                             customer_id: uuid.UUID, metric_type: str,
                             severity: str, title: str, message: str):
    """Create notification for an SLA breach."""
    from services.network.database import get_session as _get_session
    async with _get_session() as session:
        notification = NetworkNotification(
            tenant_id=tenant_id,
            service_id=service_id,
            customer_id=customer_id,
            trigger_type="sla_breach",
            severity=severity,
            title=title,
            message=message,
            channel="in_app",
            recipient=str(customer_id),
        )
        session.add(notification)
        session.flush()


async def notify_billing_event(tenant_id: uuid.UUID, service_id: uuid.UUID,
                                customer_id: uuid.UUID, event_type: str,
                                title: str, message: str):
    """Create notification for billing-related network events (suspend/reinstate)."""
    from services.network.database import get_session as _get_session
    async with _get_session() as session:
        notification = NetworkNotification(
            tenant_id=tenant_id,
            service_id=service_id,
            customer_id=customer_id,
            trigger_type=event_type,  # billing_suspend or billing_reinstate
            severity="warning" if "suspend" in event_type else "info",
            title=title,
            message=message,
            channel="in_app",
            recipient=str(customer_id),
        )
        session.add(notification)
        session.flush()
