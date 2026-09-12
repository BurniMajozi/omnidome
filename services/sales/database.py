"""Sales service async database layer (mirrors services/iot/database.py).

Engine comes from services.common.db.get_async_engine() — single source of
truth for DATABASE_URL handling (plain postgresql:// accepted, +asyncpg
driver appended transparently). Do NOT build our own engine here.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from services.common.db import get_async_engine
from services.sales.models import Base


_session_factory: async_sessionmaker | None = None


def _get_session_factory() -> async_sessionmaker:
    global _session_factory
    if _session_factory is None:
        engine = get_async_engine()
        _session_factory = async_sessionmaker(engine, expire_on_commit=False)
    return _session_factory


async def init_tables() -> None:
    """Create all sales tables if they don't exist (dev/AUTO_CREATE path)."""
    engine = get_async_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield a transactional async DB session."""
    factory = _get_session_factory()
    session = factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency — same transactional session as get_session()."""
    async with get_session() as session:
        yield session
