"""FNO Intelligence service — database setup."""

import os

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.engine.url import make_url
from sqlalchemy import text as _text

from services.fno_intelligence.models import Base

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/fno_intelligence",
)
ASYNC_POOL_SIZE = int(os.getenv("ASYNC_POOL_SIZE", "10"))

_engine = None
_session_factory = None


def _async_database_url() -> str:
    """Ensure an async driver is used (mirrors services.common.db logic).

    The shared DATABASE_URL is a sync ``postgresql://`` URL; create_async_engine
    requires ``postgresql+asyncpg://``.
    """
    url = make_url(DATABASE_URL)
    if url.drivername.startswith("postgresql") and "+asyncpg" not in url.drivername:
        url = url.set(drivername="postgresql+asyncpg")
    return url.render_as_string(hide_password=False)


def get_async_engine():
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            _async_database_url(), pool_size=ASYNC_POOL_SIZE, max_overflow=5,
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
        # Idempotently create PG enum types (CREATE TYPE IF NOT EXISTS) before
        # create_all. On a shared/reused database the enum types may already
        # exist, and create_all's native_enum DDL would otherwise raise a
        # duplicate-type IntegrityError. We manage enum creation ourselves and
        # tell the Enum columns not to emit their own CREATE TYPE.
        from sqlalchemy import Enum as _Enum
        seen = set()
        for table in Base.metadata.tables.values():
            for column in table.columns:
                if isinstance(column.type, _Enum) and column.type.name:
                    enum_name = column.type.name
                    if enum_name in seen:
                        continue
                    seen.add(enum_name)
                    values = [v for v in column.type.enums]
                    quoted = ", ".join(f"'{v}'" for v in values)
                    await conn.execute(
                        _text(f"DO $$ BEGIN\n"
                              f"  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = '{enum_name}') THEN\n"
                              f"    CREATE TYPE {enum_name} AS ENUM ({quoted});\n"
                              f"  END IF;\n"
                              f"END $$;")
                    )
        await conn.run_sync(Base.metadata.create_all)
