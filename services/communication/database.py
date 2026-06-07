"""Database session management for the Communication Service."""

from services.communication.models import Base
from services.common.db import get_async_engine, session_scope


async def init_tables() -> None:
    """Create all Communication tables if they don't exist (dev convenience)."""
    engine = get_async_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# Re-export for route convenience
__all__ = ["session_scope", "init_tables", "Base"]
