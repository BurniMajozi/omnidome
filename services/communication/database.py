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


# Re-export for route convenience
__all__ = ["session_scope", "get_session", "init_tables", "Base"]
