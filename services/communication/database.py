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


# Re-export for route convenience
__all__ = ["session_scope", "get_session", "init_tables", "Base"]
