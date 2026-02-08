from __future__ import annotations

import os
import uuid
from datetime import datetime
from contextlib import asynccontextmanager
from contextvars import ContextVar
from functools import lru_cache
from typing import AsyncGenerator, Optional

from fastapi import HTTPException, status
from sqlalchemy import DateTime, create_engine, event, func
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, with_loader_criteria
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

DEFAULT_DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/postgres"

_tenant_context: ContextVar[Optional[uuid.UUID]] = ContextVar("tenant_id", default=None)


def set_tenant_context(tenant_id: Optional[uuid.UUID]) -> None:
    """Set the tenant context for automatic query scoping."""
    _tenant_context.set(tenant_id)


def get_tenant_context() -> Optional[uuid.UUID]:
    return _tenant_context.get()


class Base(DeclarativeBase):
    __abstract__ = True

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        index=True,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


@event.listens_for(Session, "do_orm_execute")
def _add_tenant_criteria(execute_state) -> None:
    if execute_state.execution_options.get("include_all_tenants", False):
        return
    tenant_id = execute_state.session.info.get("tenant_id") or get_tenant_context()
    if not tenant_id:
        return
    execute_state.statement = execute_state.statement.options(
        with_loader_criteria(
            Base,
            lambda cls: cls.tenant_id == tenant_id,
            include_aliases=True,
        )
    )


def _database_url() -> str:
    return os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)


def _async_database_url() -> str:
    url = make_url(_database_url())
    if url.drivername.startswith("postgresql") and "+asyncpg" not in url.drivername:
        url = url.set(drivername="postgresql+asyncpg")
    return str(url)


@lru_cache
def get_engine():
    return create_engine(_database_url(), pool_pre_ping=True)


@lru_cache
def get_async_engine() -> AsyncEngine:
    return create_async_engine(_async_database_url(), pool_pre_ping=True)


@lru_cache
def _get_async_session_factory() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_async_engine(), expire_on_commit=False)


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an AsyncSession scoped to the current tenant."""
    factory = _get_async_session_factory()
    async with factory() as session:
        tenant_id = get_tenant_context()
        if tenant_id:
            session.info["tenant_id"] = tenant_id
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def session_scope(tenant_id: Optional[uuid.UUID] = None) -> AsyncGenerator[AsyncSession, None]:
    """Async session context manager with automatic commit/rollback."""
    factory = _get_async_session_factory()
    async with factory() as session:
        if tenant_id:
            session.info["tenant_id"] = tenant_id
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def require_database_url() -> str:
    db_url = _database_url()
    if not db_url:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="DATABASE_URL not configured",
        )
    return db_url
