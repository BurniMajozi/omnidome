"""Billing Collections service — database setup."""

import os

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from services.billing_collections.models import Base

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/billing_collections",
)
ASYNC_POOL_SIZE = int(os.getenv("ASYNC_POOL_SIZE", "10"))

_engine = None
_session_factory = None


def get_async_engine():
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            DATABASE_URL,
            pool_size=ASYNC_POOL_SIZE,
            max_overflow=5,
            pool_pre_ping=True,
            echo=os.getenv("SQL_ECHO", "false").lower() == "true",
        )
    return _engine


def get_session_factory():
    global _session_factory
    if _session_factory is None:
        engine = get_async_engine()
        _session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return _session_factory


async def get_session() -> AsyncSession:
    factory = get_session_factory()
    async with factory() as session:
        yield session


async def init_tables():
    engine = get_async_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
