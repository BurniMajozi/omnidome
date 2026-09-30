"""Sales service async database layer (mirrors services/iot/database.py).

Engine comes from services.common.db.get_async_engine() — single source of
truth for DATABASE_URL handling (plain postgresql:// accepted, +asyncpg
driver appended transparently). Do NOT build our own engine here.
"""

import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from services.common.db import get_async_engine
from services.sales.models import Base


logger = logging.getLogger("sales.database")

_session_factory: async_sessionmaker | None = None

POST_COMMIT_KEY = "post_commit"


def after_commit(session: Any, hook: Callable[[], Awaitable[None]]) -> None:
    """Run `hook` (an async callable) only once this session's transaction has
    committed. Side effects that reach other services (finance journal,
    lifecycle, provisioning webhooks) go here, so a rolled-back close never
    posts anything and a committed one posts exactly once."""
    session.info.setdefault(POST_COMMIT_KEY, []).append(hook)


async def run_after_commit_hooks(session: Any) -> None:
    hooks = session.info.pop(POST_COMMIT_KEY, [])
    for hook in hooks:
        try:
            await hook()
        except Exception:  # noqa: BLE001 - the change is committed; a bridge failure must not undo it
            logger.exception("post-commit hook failed")


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
        session.info.pop(POST_COMMIT_KEY, None)
        await session.rollback()
        raise
    else:
        await run_after_commit_hooks(session)
    finally:
        await session.close()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency — same transactional session as get_session()."""
    async with get_session() as session:
        yield session
