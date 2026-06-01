"""Database session management for Lifecycle service."""

import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

DEFAULT_DATABASE_URL = "postgresql://postgres:***@localhost:5432/postgres"


def _database_url() -> str:
    return os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)


_sync_engine = None
_async_engine = None
_async_session_factory = None


def get_engine():
    global _sync_engine
    if _sync_engine is None:
        _sync_engine = create_engine(_database_url(), pool_pre_ping=True)
    return _sync_engine


def _async_database_url() -> str:
    url = make_url(_database_url())
    if url.drivername.startswith("postgresql") and "+asyncpg" not in url.drivername:
        url = url.set(drivername="postgresql+asyncpg")
    return str(url)


def get_async_engine():
    global _async_engine
    if _async_engine is None:
        _async_engine = create_async_engine(_async_database_url(), pool_pre_ping=True)
    return _async_engine


def get_async_session_factory():
    global _async_session_factory
    if _async_session_factory is None:
        _async_session_factory = async_sessionmaker(get_async_engine(), expire_on_commit=False)
    return _async_session_factory


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    factory = get_async_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency."""
    factory = get_async_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def init_tables() -> None:
    from services.lifecycle.models import LifecycleBase
    engine = get_engine()
    LifecycleBase.metadata.create_all(bind=engine)
