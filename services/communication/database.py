"""Database session management for the Communication Service."""

from services.communication.models import Base
from services.common.db import get_async_engine, session_scope

# `get_session` is an alias for the shared `session_scope` async context
# manager. services.common.db does not export a `get_session`; the schedule
# routes use `async with get_session() as session:`, which session_scope
# (an @asynccontextmanager taking an optional tenant_id) satisfies directly.
get_session = session_scope


async def init_tables() -> None:
    """Create all Communication tables if they don't exist (dev convenience)."""
    engine = get_async_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _repoint_schedule_task_fk(conn)
        await _ensure_mailbox_email_unique(conn)
    await ensure_message_schema()


_MESSAGE_SCHEMA_LOCK_KEY = 74_210_004
MESSAGE_SCHEMA_STATEMENTS = (
    "ALTER TABLE messages ADD COLUMN IF NOT EXISTS client_msg_id VARCHAR(64)",
    "CREATE INDEX IF NOT EXISTS ix_messages_channel_created_id ON messages (channel_id, created_at, id)",
    "CREATE INDEX IF NOT EXISTS ix_messages_tenant_channel ON messages (tenant_id, channel_id)",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_messages_channel_client_msg ON messages (channel_id, client_msg_id) "
    "WHERE client_msg_id IS NOT NULL",
)


async def ensure_message_schema() -> None:
    """Idempotent upgrade for tables that predate create_all(): idempotency column + history indexes.
    Never fails startup."""
    import logging
    from sqlalchemy import text

    log = logging.getLogger("communication.database")
    try:
        async with get_async_engine().begin() as conn:
            await conn.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _MESSAGE_SCHEMA_LOCK_KEY})
            for stmt in MESSAGE_SCHEMA_STATEMENTS:
                try:
                    async with conn.begin_nested():
                        await conn.execute(text(stmt))
                except Exception as exc:  # noqa: BLE001
                    log.warning("message schema upgrade step failed (%s): %s", stmt[:60], exc)
    except Exception as exc:  # noqa: BLE001
        log.warning("Could not apply message schema upgrades: %s", exc)


async def _repoint_schedule_task_fk(conn) -> None:
    """Idempotent: schedule_events.linked_task_id was created (by master_schema.sql)
    with an FK to the CRM `tasks` table; communication tasks live in `comm_tasks`."""
    import logging
    from sqlalchemy import text

    log = logging.getLogger("communication.database")
    try:
        async with conn.begin_nested():
            row = (await conn.execute(text(
                "SELECT c.conname FROM pg_constraint c "
                "WHERE c.conrelid = 'schedule_events'::regclass AND c.contype = 'f' "
                "AND c.confrelid = 'tasks'::regclass"
            ))).first()
            if row:
                await conn.execute(text(f'ALTER TABLE schedule_events DROP CONSTRAINT "{row[0]}"'))
                await conn.execute(text(
                    "ALTER TABLE schedule_events ADD CONSTRAINT schedule_events_linked_task_id_fkey "
                    "FOREIGN KEY (linked_task_id) REFERENCES comm_tasks(id) ON DELETE SET NULL"
                ))
    except Exception as exc:  # never block startup
        log.warning("Could not repoint schedule_events.linked_task_id FK: %s", exc)


MAILBOX_UNIQUE_INDEX = "uq_agent_mailboxes_email_address"
_MAILBOX_LOCK_KEY = 74_210_003  # pg_advisory_xact_lock key: serialises concurrent replicas' startups


async def _ensure_mailbox_email_unique(conn) -> None:
    """Idempotent: globally unique agent_mailboxes.email_address (a mailbox address must map to
    exactly one tenant or inbound mail routing is ambiguous/hijackable). If duplicate rows already
    exist the index is NOT created (a warning names the addresses); startup never fails."""
    import logging
    from sqlalchemy import text

    log = logging.getLogger("communication.database")
    try:
        async with conn.begin_nested():
            await conn.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _MAILBOX_LOCK_KEY})
            dupes = (await conn.execute(text(
                "SELECT email_address, count(*) FROM agent_mailboxes "
                "GROUP BY email_address HAVING count(*) > 1 LIMIT 20"
            ))).all()
            if dupes:
                log.warning(
                    "agent_mailboxes has duplicate email_address rows (%s); NOT creating unique index %s. "
                    "Resolve the duplicates (mail for these addresses is dropped as ambiguous) and restart.",
                    ", ".join(f"{r[0]} x{r[1]}" for r in dupes), MAILBOX_UNIQUE_INDEX)
                return
            await conn.execute(text(
                f"CREATE UNIQUE INDEX IF NOT EXISTS {MAILBOX_UNIQUE_INDEX} ON agent_mailboxes (email_address)"))
    except Exception as exc:  # never block startup
        log.warning("Could not ensure unique index on agent_mailboxes.email_address: %s", exc)


# Re-export for route convenience
__all__ = ["session_scope", "get_session", "init_tables", "ensure_message_schema", "Base"]
