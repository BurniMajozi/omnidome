"""FNO Intelligence service — database setup."""

import os

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from services.fno_intelligence.models import Base

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/fno_intelligence",
)
ASYNC_POOL_SIZE = int(os.getenv("ASYNC_POOL_SIZE", "10"))

_engine = None
_session_factory = None


def get_async_engine():
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            DATABASE_URL, pool_size=ASYNC_POOL_SIZE, max_overflow=5,
            pool_pre_ping=True, echo=os.getenv("SQL_ECHO", "false").lower() == "true",
        )
    return _engine


def get_session_factory():
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(get_async_engine(), class_=AsyncSession, expire_on_commit=False)
    return _session_factory


async def get_session() -> AsyncSession:
    async with get_session_factory()() as session:
        yield session


async def init_tables():
    async with get_async_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
