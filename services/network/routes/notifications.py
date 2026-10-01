"""Network notification management routes.

Provides:
- Notification CRUD and dispatch
- Notification preferences per customer
- Integration triggers for FNO outages, SLA breaches, billing events
"""

import html
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select, func

from starlette.concurrency import run_in_threadpool

from services.common import agentmail, suppression
from services.common.auth import AuthContext, get_auth_context
from services.common.url_safety import UnsafeUrl, validate_public_url
from services.common.background_tasks import schedule_background
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
        if not recipients:
            # No CRM contact lookup is wired: never invent a recipient.
            raise HTTPException(status_code=422, detail="recipients are required (no customer contact lookup is configured)")

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

        # Dispatch in background. No `await` anywhere in this function, so
        # it runs to completion -- including this `with` block's own
        # commit-on-exit -- before the event loop ever gets a chance to
        # start any task scheduled here.
        for n in notifications:
            schedule_background(_send_notification(n.id))

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

        schedule_background(_send_notification(notification.id))
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
    """Background task: deliver a notification and record what REALLY happened.

    Status is only "sent" when the channel actually delivered it (in_app inbox row, a provider-accepted
    email, a 2xx webhook). Channels without a provider are recorded as "queued_not_sent" /
    "skipped_no_provider" with the reason in error_message, never as sent.
    """
    from services.network.database import get_session as _get_session
    with _get_session() as session:
        notification = session.execute(
            select(NetworkNotification).where(NetworkNotification.id == notification_id)
        ).scalar_one_or_none()
        if not notification:
            return
        await deliver_notification(session, notification)
        session.flush()


def _webhook_allowed(url: str) -> str:
    """Return the URL if it is a public https URL (and on NETWORK_WEBHOOK_ALLOWED_HOSTS when set)."""
    from urllib.parse import urlsplit
    safe = validate_public_url(url)
    allow = {h.strip().lower() for h in os.getenv("NETWORK_WEBHOOK_ALLOWED_HOSTS", "").split(",") if h.strip()}
    if allow and (urlsplit(safe).hostname or "").lower() not in allow:
        raise UnsafeUrl("Webhook host is not on NETWORK_WEBHOOK_ALLOWED_HOSTS")
    return safe


async def deliver_notification(session, notification, *, email_sender=None, webhook_poster=None) -> None:
    now = datetime.now(timezone.utc)
    channel = notification.channel

    def mark(status_, error=None):
        notification.status = status_
        notification.error_message = error
        if status_ == "sent":
            notification.sent_at = now

    try:
        if channel == "in_app":
            mark("sent")  # the stored row IS the inbox entry
        elif channel == "email":
            if email_sender is None and not agentmail.is_configured():
                mark("skipped_no_provider", "no email provider configured; email was not sent")
                return
            _, suppressed = suppression.filter_suppressed_sync(
                session.connection(), notification.tenant_id, [notification.recipient])
            if suppressed:
                mark("dismissed", "recipient is on the suppression list; email was not sent")
                return
            sender = email_sender or agentmail.send_email
            await sender(notification.recipient, notification.title,
                         "<p>%s</p>" % html.escape(notification.message or ""))
            mark("sent")
        elif channel == "webhook":
            try:
                url = await run_in_threadpool(_webhook_allowed, notification.recipient)
            except UnsafeUrl as exc:
                mark("failed", f"webhook URL rejected: {exc}")
                return
            poster = webhook_poster or _post_webhook
            code = await poster(url, {"title": notification.title, "message": notification.message,
                                      "severity": notification.severity,
                                      "trigger_type": notification.trigger_type})
            if 200 <= code < 300:
                mark("sent")
            else:
                mark("failed", f"webhook returned HTTP {code}")
        elif channel in {"sms", "push"}:
            mark("queued_not_sent", f"no {channel} provider is integrated; notification was not sent")
        else:
            mark("skipped_no_provider", f"unsupported channel {channel!r}; not sent")
    except Exception as exc:  # noqa: BLE001
        mark("failed", f"{type(exc).__name__}: delivery failed")
        logger.error("Failed to send notification %s: %s", notification.id, type(exc).__name__)


async def _post_webhook(url: str, payload: dict) -> int:
    import httpx
    async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
        resp = await client.post(url, json=payload)
    return resp.status_code


# ---------------------------------------------------------------------------
# Trigger helpers (called by other services)
# ---------------------------------------------------------------------------

async def notify_fno_outage(tenant_id: uuid.UUID, fno_name: str, affected_areas: list[str],
                             severity: str, title: str, message: str):
    """Create notifications for all services affected by an FNO outage."""
    from services.network.database import get_session as _get_session
    # get_session() is a synchronous SQLAlchemy Session, not AsyncSession --
    # this and the two functions below previously used `async with` on it,
    # which raises immediately on every call regardless of who calls them.
    with _get_session() as session:
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
    with _get_session() as session:
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
    with _get_session() as session:
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
