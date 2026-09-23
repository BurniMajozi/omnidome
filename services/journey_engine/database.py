"""Database session management for Journey Engine service."""

import logging
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
    # str(url) masks the password as "***" (SQLAlchemy's default repr/logging
    # safety behavior) -- every async connection this module makes was
    # literally authenticating with the 3-character string "***" instead of
    # the real password, failing with InvalidPasswordError. Found 2026-09-23
    # verifying the entitlements fix: this breaks get_db() (every request)
    # and _execute_fno_cancellation's own session equally. services/common/
    # db.py's equivalent function already does this correctly.
    return url.render_as_string(hide_password=False)


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


async def init_tables() -> None:
    from services.journey_engine.models import JourneyBase
    engine = get_engine()

    # CancellationWorkflow has real FK constraints to network_services.id and
    # fno_orders.id (services.network.models, a *different* declarative Base,
    # which itself has network_services.product_id -> inventory_products.id,
    # a THIRD service/Base) -- JourneyBase.metadata.create_all() can't
    # resolve any of this unless those tables already exist first. Found
    # 2026-09-23: startup crashed with NoReferencedTableError in any
    # environment where network/inventory hadn't already created their own
    # tables first (this environment doesn't run either by default). All
    # three services share one physical DB (see docker-compose.yaml), so
    # calling their own init_tables() here is safe and idempotent -- same
    # engine factory (network's), same target database throughout.
    # inventory's init_tables() is async; network's and this one are sync,
    # which is why this function is now async too (see main.py's startup()).
    try:
        from services.inventory.database import init_tables as _init_inventory_tables
        await _init_inventory_tables()
    except Exception:
        logging.getLogger("journey_engine").exception(
            "Failed to ensure services.inventory tables exist before creating "
            "network tables -- network_services.product_id's FK may fail."
        )

    try:
        from services.network.database import init_tables as _init_network_tables
        _init_network_tables()
    except Exception:
        logging.getLogger("journey_engine").exception(
            "Failed to ensure services.network tables exist before creating "
            "journey_engine tables -- CancellationWorkflow's FKs may fail."
        )

    # Creating network's tables above makes them exist in the DATABASE, but
    # ForeignKey("network_services.id")/("fno_orders.id") are string
    # references SQLAlchemy can only resolve against a Table object already
    # registered in *this same* MetaData -- JourneyBase.metadata has never
    # heard of network's tables, since they belong to a different
    # declarative Base entirely. Reflect the real (now-existing) tables into
    # JourneyBase's own metadata so create_all() can resolve the FKs;
    # create_all()'s default checkfirst=True then skips re-creating them
    # since they already exist.
    from sqlalchemy import Table
    for table_name in ("network_services", "fno_orders"):
        if table_name not in JourneyBase.metadata.tables:
            try:
                Table(table_name, JourneyBase.metadata, autoload_with=engine)
            except Exception:
                logging.getLogger("journey_engine").exception(
                    "Failed to reflect %s -- CancellationWorkflow's FK to it may fail", table_name
                )

    JourneyBase.metadata.create_all(bind=engine)
