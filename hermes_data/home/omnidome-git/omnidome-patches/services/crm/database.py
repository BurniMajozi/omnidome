"""Database session management for the CRM service.

Uses the async engine and sessionmaker from services/common/db.py
(AsyncEngine + async_sessionmaker) so DB calls don't block the FastAPI
event loop.
"""

import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from services.common.db import get_async_engine
from services.crm.models import Base


_async_session_factory: async_sessionmaker | None = None


def _get_async_session_factory() -> async_sessionmaker:
    global _async_session_factory
    if _async_session_factory is None:
        engine = get_async_engine()
        _async_session_factory = async_sessionmaker(engine, expire_on_commit=False)
    return _async_session_factory


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield a transactional async DB session and commit on success."""
    factory = _get_async_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def init_tables() -> None:
    """Create all CRM tables if they don't exist (dev convenience)."""
    from services.common.db import get_engine as _get_sync_engine

    engine = _get_sync_engine()
    Base.metadata.create_all(bind=engine)


def generate_account_number(tenant_id: uuid.UUID) -> str:
    """Generate a unique account number for a customer."""
    short_tenant = str(tenant_id).split("-")[0].upper()[:4]
    short_id = uuid.uuid4().hex[:8].upper()
    return f"ACC-{short_tenant}-{short_id}"
