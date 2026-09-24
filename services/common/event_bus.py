"""Postgres message broker: transactional outbox + per-consumer deliveries.

SPEC-event-bus.md. Every service shares the `coreconnect` Postgres, so the
broker is three tables there instead of a new container:

    domain_events        one row per fact (written in the caller's transaction)
    event_subscriptions  which consumer wants which event types
    event_deliveries     one row per (event, consumer), with retry state

Producers call `publish(session, ...)` inside the transaction that makes the
business change, so an event exists if and only if the change committed.
Consumers run an `EventConsumer` loop that claims due deliveries with
FOR UPDATE SKIP LOCKED (safe across uvicorn workers and replicas), calls the
handler, and marks the delivery delivered, re-queued with back-off, or dead.
Delivery is at least once: handlers must be idempotent (they get the event id).

`notify(session, ...)` writes the in-app notifications feed behind the header bell.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from typing import Any, Awaitable, Callable, Mapping, Optional

from sqlalchemy import text

logger = logging.getLogger("omnidome.event_bus")

Handler = Callable[[dict], Awaitable[Any]]

EVENT_TYPE_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+)+$")
MAX_EVENT_TYPE_LEN = 120

# Seconds to wait before attempt n+1 after attempt n failed (n = 1..7).
RETRY_DELAYS = (10, 30, 120, 600, 1800, 3600, 3600)
MAX_ATTEMPTS = len(RETRY_DELAYS) + 1

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS domain_events (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    event_type VARCHAR(120) NOT NULL,
    source VARCHAR(60) NOT NULL,
    subject_type VARCHAR(60),
    subject_id VARCHAR(100),
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    idempotency_key VARCHAR(200),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_domain_events_idempotency
    ON domain_events (tenant_id, idempotency_key) WHERE idempotency_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_domain_events_subject
    ON domain_events (tenant_id, subject_type, subject_id, created_at);
CREATE INDEX IF NOT EXISTS ix_domain_events_type
    ON domain_events (tenant_id, event_type, created_at);

CREATE TABLE IF NOT EXISTS event_subscriptions (
    consumer VARCHAR(60) NOT NULL,
    event_pattern VARCHAR(120) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer, event_pattern)
);

CREATE TABLE IF NOT EXISTS event_deliveries (
    id UUID PRIMARY KEY,
    event_id UUID NOT NULL REFERENCES domain_events(id) ON DELETE CASCADE,
    consumer VARCHAR(60) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    locked_until TIMESTAMPTZ,
    last_error TEXT,
    delivered_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_event_deliveries_event_consumer UNIQUE (event_id, consumer)
);
CREATE INDEX IF NOT EXISTS ix_event_deliveries_due
    ON event_deliveries (consumer, next_attempt_at) WHERE status IN ('pending', 'processing');
CREATE INDEX IF NOT EXISTS ix_event_deliveries_status ON event_deliveries (status, created_at);

CREATE TABLE IF NOT EXISTS notifications (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    recipient_id UUID,
    category VARCHAR(40) NOT NULL DEFAULT 'general',
    severity VARCHAR(10) NOT NULL DEFAULT 'info',
    title VARCHAR(200) NOT NULL,
    body TEXT,
    link VARCHAR(300),
    source VARCHAR(60),
    subject_type VARCHAR(60),
    subject_id VARCHAR(100),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    read_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS ix_notifications_feed ON notifications (tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_notifications_unread ON notifications (tenant_id) WHERE read_at IS NULL;
"""

_SCHEMA_LOCK = 0x0E7B05  # advisory lock key: only one worker runs the DDL at a time


# ── Pure helpers ────────────────────────────────────────────────────────────

def normalise_event_type(raw: str) -> str:
    """Lower-case dotted name like `portal.cart.abandoned`; raises ValueError otherwise."""
    value = (raw or "").strip().lower()
    if len(value) > MAX_EVENT_TYPE_LEN or not EVENT_TYPE_RE.match(value):
        raise ValueError(
            "event type must be dotted lower-case words, e.g. portal.cart.abandoned"
        )
    return value


def pattern_matches(pattern: str, event_type: str) -> bool:
    """`*` matches everything, `a.b.*` matches anything under `a.b.`, else exact."""
    if pattern == "*":
        return True
    if pattern.endswith(".*"):
        return event_type.startswith(pattern[:-1])
    return pattern == event_type


def handler_for(handlers: Mapping[str, Any], event_type: str) -> Any:
    """The most specific handler: exact name, then the longest matching prefix, then `*`."""
    if event_type in handlers:
        return handlers[event_type]
    prefixes = [p for p in handlers if p.endswith(".*") and pattern_matches(p, event_type)]
    if prefixes:
        return handlers[max(prefixes, key=len)]
    return handlers.get("*")


def retry_delay_seconds(attempts: int) -> int:
    """Back-off before the next try, after `attempts` failed tries."""
    index = min(max(attempts, 1), len(RETRY_DELAYS)) - 1
    return RETRY_DELAYS[index]


def is_exhausted(attempts: int) -> bool:
    return attempts >= MAX_ATTEMPTS


def _json(value: Any) -> str:
    return json.dumps(value or {}, default=str)


# ── Schema ──────────────────────────────────────────────────────────────────

async def ensure_schema(session) -> None:
    """Create the broker tables if missing (idempotent; mirrors
    config/migrations/20260925_event_bus.sql). Serialised with an advisory lock
    because several workers start at once."""
    await session.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _SCHEMA_LOCK})
    for statement in SCHEMA_SQL.split(";"):
        if statement.strip():
            await session.execute(text(statement))


# ── Producer side ───────────────────────────────────────────────────────────

async def publish(
    session,
    tenant_id: uuid.UUID | str,
    event_type: str,
    payload: Optional[dict] = None,
    *,
    source: str,
    subject: Optional[tuple[str, Any]] = None,
    idempotency_key: Optional[str] = None,
) -> uuid.UUID:
    """Record an event and queue it for every subscribed consumer, inside the
    caller's transaction. A repeated idempotency key returns the first event's
    id and queues nothing new."""
    event_type = normalise_event_type(event_type)
    event_id = uuid.uuid4()
    subject_type, subject_id = (subject[0], str(subject[1])) if subject else (None, None)
    row = (await session.execute(
        text("""
            INSERT INTO domain_events
                (id, tenant_id, event_type, source, subject_type, subject_id, payload, idempotency_key)
            VALUES (:id, :tenant_id, :event_type, :source, :subject_type, :subject_id,
                    CAST(:payload AS jsonb), :idempotency_key)
            ON CONFLICT (tenant_id, idempotency_key) WHERE idempotency_key IS NOT NULL DO NOTHING
            RETURNING id
        """),
        {
            "id": event_id, "tenant_id": str(tenant_id), "event_type": event_type,
            "source": source, "subject_type": subject_type, "subject_id": subject_id,
            "payload": _json(payload), "idempotency_key": idempotency_key,
        },
    )).first()
    if row is None:
        existing = (await session.execute(
            text("SELECT id FROM domain_events WHERE tenant_id = :t AND idempotency_key = :k"),
            {"t": str(tenant_id), "k": idempotency_key},
        )).scalar_one()
        return existing

    subscriptions = (await session.execute(
        text("SELECT consumer, event_pattern FROM event_subscriptions")
    )).all()
    consumers = sorted({c for c, p in subscriptions if pattern_matches(p, event_type)})
    for consumer in consumers:
        await session.execute(
            text("""
                INSERT INTO event_deliveries (id, event_id, consumer)
                VALUES (:id, :event_id, :consumer)
                ON CONFLICT (event_id, consumer) DO NOTHING
            """),
            {"id": uuid.uuid4(), "event_id": event_id, "consumer": consumer},
        )
    return event_id


async def notify(
    session,
    tenant_id: uuid.UUID | str,
    title: str,
    *,
    body: Optional[str] = None,
    category: str = "general",
    severity: str = "info",
    link: Optional[str] = None,
    recipient_id: Optional[uuid.UUID | str] = None,
    source: Optional[str] = None,
    subject: Optional[tuple[str, Any]] = None,
) -> uuid.UUID:
    """Add an item to the notifications feed (recipient None = whole tenant)."""
    notification_id = uuid.uuid4()
    await session.execute(
        text("""
            INSERT INTO notifications
                (id, tenant_id, recipient_id, category, severity, title, body, link,
                 source, subject_type, subject_id)
            VALUES (:id, :tenant_id, :recipient_id, :category, :severity, :title, :body, :link,
                    :source, :subject_type, :subject_id)
        """),
        {
            "id": notification_id, "tenant_id": str(tenant_id),
            "recipient_id": str(recipient_id) if recipient_id else None,
            "category": category, "severity": severity if severity in ("info", "warning", "critical") else "info",
            "title": title[:200], "body": body, "link": (link or None) and link[:300], "source": source,
            "subject_type": subject[0] if subject else None,
            "subject_id": str(subject[1]) if subject else None,
        },
    )
    return notification_id


# ── Consumer side ───────────────────────────────────────────────────────────

class EventConsumer:
    """Delivers events to this service's handlers.

    handlers: {"sales.lead.email_requested": fn, "portal.*": fn, "*": fn}
    Each handler gets the event as a dict (id, tenant_id, type, source,
    subject_type, subject_id, payload, created_at, attempt) and raises to ask
    for a retry.
    """

    def __init__(
        self,
        name: str,
        handlers: Mapping[str, Handler],
        *,
        batch_size: int = 20,
        idle_seconds: float = 2.0,
        lock_seconds: int = 300,
    ) -> None:
        self.name = name
        self.handlers = dict(handlers)
        self.batch_size = batch_size
        self.idle_seconds = idle_seconds
        self.lock_seconds = lock_seconds
        self._task: Optional[asyncio.Task] = None

    async def ensure_subscriptions(self) -> None:
        from services.common.db import session_scope

        async with session_scope() as session:
            await ensure_schema(session)
            for pattern in self.handlers:
                await session.execute(
                    text("""
                        INSERT INTO event_subscriptions (consumer, event_pattern)
                        VALUES (:c, :p) ON CONFLICT DO NOTHING
                    """),
                    {"c": self.name, "p": pattern},
                )

    async def _claim(self) -> list[dict]:
        from services.common.db import session_scope

        async with session_scope() as session:
            rows = (await session.execute(
                text("""
                    UPDATE event_deliveries d
                       SET status = 'processing',
                           attempts = d.attempts + 1,
                           locked_until = now() + make_interval(secs => :lock)
                      FROM domain_events e
                     WHERE d.event_id = e.id
                       AND d.id IN (
                           SELECT id FROM event_deliveries
                            WHERE consumer = :consumer
                              AND ((status = 'pending' AND next_attempt_at <= now())
                                   OR (status = 'processing' AND locked_until < now()))
                            ORDER BY next_attempt_at
                            LIMIT :n
                            FOR UPDATE SKIP LOCKED)
                    RETURNING d.id AS delivery_id, d.attempts, e.id, e.tenant_id, e.event_type,
                              e.source, e.subject_type, e.subject_id, e.payload, e.created_at
                """),
                {"consumer": self.name, "n": self.batch_size, "lock": self.lock_seconds},
            )).mappings().all()
        return [dict(r) for r in rows]

    async def _finish(self, row: dict, error: Optional[str]) -> None:
        from services.common.db import session_scope

        async with session_scope() as session:
            if error is None:
                await session.execute(
                    text("""
                        UPDATE event_deliveries
                           SET status = 'delivered', delivered_at = now(), locked_until = NULL, last_error = NULL
                         WHERE id = :id
                    """),
                    {"id": row["delivery_id"]},
                )
                return
            if is_exhausted(row["attempts"]):
                await session.execute(
                    text("""
                        UPDATE event_deliveries
                           SET status = 'dead', locked_until = NULL, last_error = :err
                         WHERE id = :id
                    """),
                    {"id": row["delivery_id"], "err": error[:2000]},
                )
                await notify(
                    session, row["tenant_id"],
                    f"Delivery failed: {row['event_type']}",
                    body=f"{self.name} gave up after {row['attempts']} attempts: {error[:300]}",
                    category="system", severity="critical", source=self.name,
                    subject=("event_delivery", row["delivery_id"]),
                )
                logger.error("[%s] %s dead after %s attempts: %s",
                             self.name, row["event_type"], row["attempts"], error[:200])
                return
            delay = retry_delay_seconds(row["attempts"])
            await session.execute(
                text("""
                    UPDATE event_deliveries
                       SET status = 'pending', locked_until = NULL, last_error = :err,
                           next_attempt_at = now() + make_interval(secs => :delay)
                     WHERE id = :id
                """),
                {"id": row["delivery_id"], "err": error[:2000], "delay": delay},
            )
            logger.warning("[%s] %s attempt %s failed, retry in %ss: %s",
                           self.name, row["event_type"], row["attempts"], delay, error[:200])

    async def run_once(self) -> int:
        """Claim and process one batch. Returns how many deliveries were handled."""
        rows = await self._claim()
        for row in rows:
            handler = handler_for(self.handlers, row["event_type"])
            event = {
                "id": str(row["id"]), "tenant_id": str(row["tenant_id"]), "type": row["event_type"],
                "source": row["source"], "subject_type": row["subject_type"],
                "subject_id": row["subject_id"], "payload": row["payload"] or {},
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                "attempt": row["attempts"],
            }
            error: Optional[str] = None
            if handler is not None:
                try:
                    await handler(event)
                except Exception as exc:  # noqa: BLE001 - any failure means retry
                    error = f"{type(exc).__name__}: {exc}" or type(exc).__name__
            await self._finish(row, error)
        return len(rows)

    async def run_forever(self) -> None:
        while True:
            try:
                await self.ensure_subscriptions()
                break
            except Exception:
                logger.exception("[%s] could not register subscriptions; retrying in 15s", self.name)
                await asyncio.sleep(15)
        logger.info("[%s] event consumer started for %s", self.name, sorted(self.handlers))
        while True:
            try:
                handled = await self.run_once()
            except Exception:
                logger.exception("[%s] event consumer tick failed", self.name)
                handled = 0
            if handled == 0:
                await asyncio.sleep(self.idle_seconds)

    def start(self) -> asyncio.Task:
        from services.common.background_tasks import schedule_background

        if self._task is None or self._task.done():
            self._task = schedule_background(self.run_forever())
        return self._task
