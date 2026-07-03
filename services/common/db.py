from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import datetime
from contextlib import asynccontextmanager
from contextvars import ContextVar
from functools import lru_cache
from typing import Any, AsyncGenerator, Awaitable, Callable, Optional

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


class SoftDeleteMixin:
    """Adds a nullable deleted_at column for soft-delete instead of physical DELETE.

    Mix into any model regardless of which DeclarativeBase it uses:
        class Supplier(Base, SoftDeleteMixin): ...

    Callers must filter `deleted_at.is_(None)` themselves in list/get queries —
    this mixin does not enforce row-level filtering the way tenant_id does.
    """

    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None


_tenant_scoped_bases: list[type] = []


def register_tenant_scoped_base(base: type) -> None:
    """Opt a service-local DeclarativeBase into the automatic tenant filter.

    Services that define their own ``Base(DeclarativeBase)`` instead of
    inheriting this module's ``Base`` are invisible to the ``do_orm_execute``
    tenant criteria below. Calling this next to the Base definition closes
    that gap. Every mapped subclass of ``base`` MUST have a ``tenant_id``
    column — the filter is applied unconditionally to all of them.
    """
    if base not in _tenant_scoped_bases:
        _tenant_scoped_bases.append(base)


@event.listens_for(Session, "do_orm_execute")
def _add_tenant_criteria(execute_state) -> None:
    if execute_state.execution_options.get("include_all_tenants", False):
        return
    tenant_id = execute_state.session.info.get("tenant_id") or get_tenant_context()
    if not tenant_id:
        return
    for scoped_base in (Base, *_tenant_scoped_bases):
        execute_state.statement = execute_state.statement.options(
            with_loader_criteria(
                scoped_base,
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
    return url.render_as_string(hide_password=False)


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


async def run_with_db_retry(
    fn: Callable[[], Awaitable[Any]],
    *,
    attempts: int = 30,
    delay: float = 5.0,
    logger: Optional[logging.Logger] = None,
) -> Any:
    """Run a startup-time DB operation, retrying while the database comes up.

    Without this, a uvicorn worker whose startup hook can't reach Postgres
    exits immediately and the parent respawns it in a tight loop — on this
    project's dev machine that fork storm has taken down Docker Desktop
    itself. Sleeping between attempts keeps the worker alive and idle until
    the database (or the network path to it) is ready.
    """
    log = logger or logging.getLogger("db.startup")
    for attempt in range(1, attempts + 1):
        try:
            return await fn()
        except Exception as exc:  # noqa: BLE001 — any connect error means "not ready yet"
            if attempt == attempts:
                raise
            log.warning(
                "DB startup attempt %d/%d failed (%s: %s); retrying in %.0fs",
                attempt, attempts, type(exc).__name__, exc, delay,
            )
            await asyncio.sleep(delay)


def require_database_url() -> str:
    db_url = _database_url()
    if not db_url:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="DATABASE_URL not configured",
        )
    return db_url
