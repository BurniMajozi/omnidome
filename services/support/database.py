"""Support service database layer — SQLAlchemy async models and session management."""

import uuid
from datetime import datetime
from typing import AsyncGenerator, Optional

from sqlalchemy import Boolean, Column, DateTime, FetchedValue, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from services.common.db import get_async_engine


class Base(DeclarativeBase):
    pass


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    # Optional: system-raised tickets (errors, failed jobs) have no customer.
    customer_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True, index=True)
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    priority: Mapped[str] = mapped_column(String(20), default="NORMAL")
    status: Mapped[str] = mapped_column(String(20), default="OPEN")
    category: Mapped[Optional[str]] = mapped_column(String(50))
    assigned_to: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True))
    external_fno_ref: Mapped[Optional[str]] = mapped_column(String(100))
    is_fcr: Mapped[bool] = mapped_column(Boolean, default=False)
    resolution_notes: Mapped[Optional[str]] = mapped_column(Text)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    # Product/hardware link
    # The physical FK is installed by the migration. Inventory uses separate
    # ORM metadata; declaring its table here breaks SQLAlchemy mapper flushes.
    product_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )
    serial_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Outcome of booking the job's recorded cost in finance (None = nothing was due / not attempted)
    finance_status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    finance_error: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Unified ticketing: where the ticket came from, how to find the originating record, and repeat handling.
    ticket_no: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, server_default=FetchedValue())       # BIGSERIAL, human reference "T-123"
    source: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)       # manual, email, iot, finance, ...
    source_ref_type: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    source_ref_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    source_link: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)  # in-app deep link to the record
    event_type: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    dedupe_key: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)   # one OPEN ticket per key
    occurrence_count: Mapped[int] = mapped_column(Integer, default=1)
    last_occurrence_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    queue: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    sla_due_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    first_response_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    context: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # Work-in-progress time dimension (maintained by lifecycle.record; the full history is in ticket_events).
    first_assigned_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_activity_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    escalated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    breach_logged_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    assignment_count: Mapped[int] = mapped_column(Integer, default=0)
    modification_count: Mapped[int] = mapped_column(Integer, default=0)
    transfer_count: Mapped[int] = mapped_column(Integer, default=0)
    reopen_count: Mapped[int] = mapped_column(Integer, default=0)
    # The channel the request arrived on and how to reach the requester there (email thread id, ...).
    reply_channel: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    reply_ref: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)


class TicketReply(Base):
    __tablename__ = "ticket_replies"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticket_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("tickets.id", ondelete="CASCADE"))
    author_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True))
    author_type: Mapped[str] = mapped_column(String(20), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    is_private: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    # Timeline: comment | event (system occurrence) | status | assignment
    kind: Mapped[str] = mapped_column(String(20), default="comment")
    data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)


# ── Session factory ────────────────────────────────────────────────────

_session_factory: Optional[async_sessionmaker] = None


def _get_session_factory() -> async_sessionmaker:
    global _session_factory
    if _session_factory is None:
        engine = get_async_engine()
        _session_factory = async_sessionmaker(engine, expire_on_commit=False)
    return _session_factory


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    factory = _get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


_SCHEMA_LOCK_KEY = 0x5_0_8_008

# create_all cannot be used: tickets.product_id references inventory_products (another service's
# table, created by config/master_schema.sql), so metadata alone raises NoReferencedTableError.
ADDITIVE_COLUMNS = (
    ("tickets", "resolution_notes", "TEXT"),
    ("tickets", "product_id", "UUID REFERENCES inventory_products(id) ON DELETE SET NULL"),
    ("tickets", "serial_number", "VARCHAR(100)"),
    ("tickets", "finance_status", "VARCHAR(20)"),
    ("tickets", "finance_error", "VARCHAR(500)"),
    ("tickets", "ticket_no", "BIGSERIAL"),
    ("tickets", "source", "VARCHAR(40)"),
    ("tickets", "source_ref_type", "VARCHAR(60)"),
    ("tickets", "source_ref_id", "VARCHAR(120)"),
    ("tickets", "source_link", "VARCHAR(300)"),
    ("tickets", "event_type", "VARCHAR(120)"),
    ("tickets", "dedupe_key", "VARCHAR(200)"),
    ("tickets", "occurrence_count", "INTEGER NOT NULL DEFAULT 1"),
    ("tickets", "last_occurrence_at", "TIMESTAMPTZ"),
    ("tickets", "queue", "VARCHAR(50)"),
    ("tickets", "sla_due_at", "TIMESTAMPTZ"),
    ("tickets", "first_response_at", "TIMESTAMPTZ"),
    ("tickets", "created_by", "UUID"),
    ("tickets", "context", "JSONB"),
    ("tickets", "first_assigned_at", "TIMESTAMPTZ"),
    ("tickets", "last_activity_at", "TIMESTAMPTZ"),
    ("tickets", "escalated_at", "TIMESTAMPTZ"),
    ("tickets", "breach_logged_at", "TIMESTAMPTZ"),
    ("tickets", "assignment_count", "INTEGER NOT NULL DEFAULT 0"),
    ("tickets", "modification_count", "INTEGER NOT NULL DEFAULT 0"),
    ("tickets", "transfer_count", "INTEGER NOT NULL DEFAULT 0"),
    ("tickets", "reopen_count", "INTEGER NOT NULL DEFAULT 0"),
    ("tickets", "reply_channel", "VARCHAR(30)"),
    ("tickets", "reply_ref", "VARCHAR(200)"),
    ("ticket_replies", "kind", "VARCHAR(20) NOT NULL DEFAULT 'comment'"),
    ("ticket_replies", "data", "JSONB"),
)

# create_all never ALTERs, so these run explicitly. System tickets have no customer.
EXTRA_DDL = (
    "ALTER TABLE tickets ALTER COLUMN customer_id DROP NOT NULL",
    # One OPEN ticket per dedupe key and tenant: concurrent consumers cannot both create it.
    """CREATE UNIQUE INDEX IF NOT EXISTS uq_tickets_open_dedupe ON tickets (tenant_id, dedupe_key)
       WHERE dedupe_key IS NOT NULL AND status NOT IN ('CLOSED', 'RESOLVED')""",
    "CREATE INDEX IF NOT EXISTS ix_tickets_tenant_status ON tickets (tenant_id, status, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS ix_tickets_source_ref ON tickets (tenant_id, source_ref_type, source_ref_id)",
    "CREATE INDEX IF NOT EXISTS ix_ticket_replies_ticket ON ticket_replies (ticket_id, created_at)",
    """CREATE TABLE IF NOT EXISTS ticket_rule_overrides (
        tenant_id UUID NOT NULL,
        rule_key VARCHAR(120) NOT NULL,
        enabled BOOLEAN,
        category VARCHAR(50),
        priority VARCHAR(20),
        queue VARCHAR(50),
        assigned_to UUID,
        updated_by UUID,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        PRIMARY KEY (tenant_id, rule_key)
    )""",
    "ALTER TABLE ticket_rule_overrides ADD COLUMN IF NOT EXISTS outcome VARCHAR(20)",
    # Append-only lifecycle log: one row per thing that happened to a ticket, with who, when and what changed.
    # Every ticket KPI (time to respond/resolve, first-touch resolution, time in stage) is computed from this
    # table plus the denormalised timestamps on tickets.
    """CREATE TABLE IF NOT EXISTS ticket_events (
        id UUID PRIMARY KEY,
        tenant_id UUID NOT NULL,
        ticket_id UUID NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
        event_type VARCHAR(40) NOT NULL,
        actor_id UUID,
        actor_type VARCHAR(20) NOT NULL DEFAULT 'system',
        from_value VARCHAR(200),
        to_value VARCHAR(200),
        note TEXT,
        visibility VARCHAR(10) NOT NULL DEFAULT 'internal',
        channel VARCHAR(30),
        data JSONB,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )""",
    "CREATE INDEX IF NOT EXISTS ix_ticket_events_ticket ON ticket_events (ticket_id, created_at)",
    "CREATE INDEX IF NOT EXISTS ix_ticket_events_tenant_type ON ticket_events (tenant_id, event_type, created_at DESC)",
    # Tickets that predate the log get a synthetic created (and resolved) event so stage times have an anchor.
    """INSERT INTO ticket_events (id, tenant_id, ticket_id, event_type, actor_type, to_value, created_at, data)
       SELECT gen_random_uuid(), t.tenant_id, t.id, 'created', 'system', 'OPEN', t.created_at, '{"backfilled": true}'::jsonb
         FROM tickets t
        WHERE NOT EXISTS (SELECT 1 FROM ticket_events e WHERE e.ticket_id = t.id AND e.event_type = 'created')""",
    """INSERT INTO ticket_events (id, tenant_id, ticket_id, event_type, actor_type, from_value, to_value, created_at, data)
       SELECT gen_random_uuid(), t.tenant_id, t.id, CASE t.status WHEN 'CLOSED' THEN 'closed' ELSE 'resolved' END,
              'system', 'OPEN', t.status, t.resolved_at, '{"backfilled": true}'::jsonb
         FROM tickets t
        WHERE t.resolved_at IS NOT NULL AND t.status IN ('RESOLVED', 'CLOSED')
          AND NOT EXISTS (SELECT 1 FROM ticket_events e WHERE e.ticket_id = t.id AND e.event_type IN ('resolved', 'closed'))""",
    # What agents may query (the safe-SQL tool): the lifecycle log WITHOUT the free-text note and data columns, so
    # internal notes stay as private to agents as ticket_replies already are.
    """CREATE OR REPLACE VIEW ticket_event_log AS
       SELECT id, tenant_id, ticket_id, event_type, actor_type, actor_id, from_value, to_value, visibility, channel, created_at
         FROM ticket_events""",
    # Per-tenant switches: who gets told what, and how far Jev may act on its own.
    """CREATE TABLE IF NOT EXISTS ticket_settings (
        tenant_id UUID PRIMARY KEY,
        notify_enabled BOOLEAN NOT NULL DEFAULT true,
        notify_on_assigned BOOLEAN NOT NULL DEFAULT true,
        notify_on_modified BOOLEAN NOT NULL DEFAULT true,
        notify_on_note BOOLEAN NOT NULL DEFAULT true,
        notify_on_resolved BOOLEAN NOT NULL DEFAULT true,
        jev_routing_mode VARCHAR(10) NOT NULL DEFAULT 'suggest',
        jev_review_on_close BOOLEAN NOT NULL DEFAULT true,
        updated_by UUID,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )""",
    # Rules the tenant adds themselves: any event on the bus -> a ticket (and optionally a task, escalation or
    # schedule item), routed to a source, category, priority, queue and person of their choosing.
    """CREATE TABLE IF NOT EXISTS ticket_automation_rules (
        id UUID PRIMARY KEY,
        tenant_id UUID NOT NULL,
        name VARCHAR(120) NOT NULL,
        event_pattern VARCHAR(120) NOT NULL,
        conditions JSONB NOT NULL DEFAULT '[]'::jsonb,
        source VARCHAR(40) NOT NULL DEFAULT 'api',
        category VARCHAR(50) NOT NULL DEFAULT 'GENERAL',
        priority VARCHAR(20) NOT NULL DEFAULT 'NORMAL',
        queue VARCHAR(50) NOT NULL DEFAULT 'support',
        outcome VARCHAR(20) NOT NULL DEFAULT 'ticket',
        assigned_to UUID,
        title_template VARCHAR(200),
        enabled BOOLEAN NOT NULL DEFAULT true,
        created_by UUID,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )""",
    "CREATE INDEX IF NOT EXISTS ix_ticket_automation_rules_tenant ON ticket_automation_rules (tenant_id, enabled)",
    # What Jev proposed for a ticket, with its probabilities, and what was done with the proposal.
    """CREATE TABLE IF NOT EXISTS ticket_jev_decisions (
        id UUID PRIMARY KEY,
        tenant_id UUID NOT NULL,
        ticket_id UUID NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
        stage VARCHAR(20) NOT NULL,
        proposal JSONB NOT NULL DEFAULT '{}'::jsonb,
        confidence JSONB NOT NULL DEFAULT '{}'::jsonb,
        disposition VARCHAR(20) NOT NULL,
        reason VARCHAR(400),
        evaluated_by_jev BOOLEAN NOT NULL DEFAULT false,
        decided_by UUID,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        decided_at TIMESTAMPTZ
    )""",
    "CREATE INDEX IF NOT EXISTS ix_ticket_jev_ticket ON ticket_jev_decisions (ticket_id, created_at DESC)",
)


async def init_tables():
    """Add the columns this service introduced to the master-schema `tickets` table (idempotent,
    serialised across workers by a transaction advisory lock). Tables themselves come from
    config/master_schema.sql."""
    from sqlalchemy import text

    engine = get_async_engine()
    if engine.dialect.name != "postgresql":
        return
    async with engine.begin() as conn:
        await conn.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _SCHEMA_LOCK_KEY})
        for table, column, ddl in ADDITIVE_COLUMNS:
            exists = (await conn.execute(text("SELECT to_regclass(:t)"), {"t": table})).scalar()
            if exists is None:
                continue
            await conn.execute(text(f'ALTER TABLE "{table}" ADD COLUMN IF NOT EXISTS "{column}" {ddl}'))
        if (await conn.execute(text("SELECT to_regclass('tickets')"))).scalar() is not None:
            for statement in EXTRA_DDL:
                await conn.execute(text(statement))
