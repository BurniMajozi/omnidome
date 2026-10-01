"""Database session management for the IoT service.

Uses SQLAlchemy 2.0 async sessions with tenant-scoped query helpers.
"""

import logging
import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Dict, Iterable, List, Optional, Set, Tuple

from sqlalchemy import Enum as SAEnum, inspect, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from services.common.db import get_async_engine
from services.iot.models import Base


logger = logging.getLogger(__name__)

_session_factory: async_sessionmaker | None = None


def _get_session_factory() -> async_sessionmaker:
    global _session_factory
    if _session_factory is None:
        engine = get_async_engine()
        _session_factory = async_sessionmaker(engine, expire_on_commit=False)
    return _session_factory


# Arbitrary constant: serialises startup DDL across uvicorn workers (same idea as
# services/billing/database.py). Session-level advisory lock, held on its own
# connection for the duration of the migration.
_SCHEMA_LOCK_KEY = 0x10_7_0_06

_LEGACY_MARKER = ("device_name", "ha_entity_id")  # (present in legacy, absent in model)


def is_legacy_iot_devices(columns: Iterable[str]) -> bool:
    """True for the pre-IoT-service `iot_devices` from config/master_schema.sql
    (device_name / firmware_version / metadata, no ha_entity_id)."""
    cols = set(columns)
    return _LEGACY_MARKER[0] in cols and _LEGACY_MARKER[1] not in cols


def _server_default_sql(col, dialect) -> Optional[str]:
    sd = col.server_default
    if sd is None:
        return None
    arg = getattr(sd, "arg", None)
    if arg is None:
        return None
    if hasattr(arg, "compile"):
        return str(arg.compile(dialect=dialect))
    return "'" + str(arg).replace("'", "''") + "'"


def missing_column_ddl(
    existing: Dict[str, Set[str]], metadata=None, dialect=None
) -> List[Tuple[str, str, object]]:
    """ALTER TABLE ... ADD COLUMN IF NOT EXISTS statements for every model column
    that an already-existing table lacks (create_all never ALTERs).

    `existing` maps table name -> set of column names actually in the database;
    tables absent from it are skipped (create_all builds those). New columns are
    NOT NULL only when the model gives a server default (otherwise existing rows
    could not be backfilled), so they are added nullable. Foreign keys are not
    re-declared on the added column. Returns (table, sql, column) triples.
    """
    metadata = metadata if metadata is not None else Base.metadata
    dialect = dialect if dialect is not None else postgresql.dialect()
    out: List[Tuple[str, str, object]] = []
    for table in metadata.sorted_tables:
        have = existing.get(table.name)
        if have is None:
            continue
        for col in table.columns:
            if col.name in have:
                continue
            ddl = f'ALTER TABLE "{table.name}" ADD COLUMN IF NOT EXISTS "{col.name}" {col.type.compile(dialect=dialect)}'
            default = _server_default_sql(col, dialect)
            if default is not None:
                ddl += f" DEFAULT {default}"
                if not col.nullable:
                    ddl += " NOT NULL"
            out.append((table.name, ddl, col))
    return out


def rebuild_decision(columns: Iterable[str], row_count: int, dependents: List[str]) -> str:
    """"skip" (not legacy), "refuse_rows", "refuse_dependents" or "rebuild"."""
    if not is_legacy_iot_devices(columns):
        return "skip"
    if row_count:
        return "refuse_rows"
    if dependents:
        return "refuse_dependents"
    return "rebuild"


def _legacy_dependents(conn) -> List[str]:
    """Views, RLS policies and (non-internal) triggers on iot_devices. DROP ... CASCADE would
    silently take views with it and would lose policies/triggers, so their presence blocks the rebuild."""
    out: List[str] = []
    out += [f"view:{r[0]}" for r in conn.execute(text("""
        SELECT DISTINCT c.relname FROM pg_depend d
          JOIN pg_rewrite r ON r.oid = d.objid
          JOIN pg_class c ON c.oid = r.ev_class
         WHERE d.refobjid = 'iot_devices'::regclass AND c.oid <> 'iot_devices'::regclass
    """)).all()]
    out += [f"policy:{r[0]}" for r in conn.execute(text(
        "SELECT polname FROM pg_policy WHERE polrelid = 'iot_devices'::regclass")).all()]
    out += [f"trigger:{r[0]}" for r in conn.execute(text(
        "SELECT tgname FROM pg_trigger WHERE tgrelid = 'iot_devices'::regclass AND NOT tgisinternal")).all()]
    return out


def _rebuild_empty_legacy_devices(conn) -> bool:
    """Drop the legacy `iot_devices` (only while EMPTY and with no dependents other than foreign
    keys) so create_all rebuilds it in the model's shape. Foreign keys other tables had to it are
    restored afterwards. The table is locked ACCESS EXCLUSIVE first, in the same transaction as
    the emptiness check and the drop, so no row can appear in between. Returns True if rebuilt."""
    insp = inspect(conn)
    if not insp.has_table("iot_devices"):
        return False
    cols = {c["name"] for c in insp.get_columns("iot_devices")}
    if not is_legacy_iot_devices(cols):
        return False
    conn.execute(text("LOCK TABLE iot_devices IN ACCESS EXCLUSIVE MODE"))
    rows = conn.execute(text("SELECT count(*) FROM iot_devices")).scalar()
    dependents = _legacy_dependents(conn) if not rows else []
    decision = rebuild_decision(cols, rows or 0, dependents)
    if decision == "refuse_rows":
        logger.error(
            "iot_devices is in the legacy shape and has %s rows; adding missing columns "
            "only — migrate it by hand", rows,
        )
        return False
    if decision == "refuse_dependents":
        logger.error(
            "iot_devices is in the legacy shape but has dependents (%s); not dropping it. "
            "Adding missing columns only — rebuild it by hand", ", ".join(dependents),
        )
        return False
    keep = conn.execute(text("""
        SELECT conrelid::regclass::text AS tbl, conname, pg_get_constraintdef(oid) AS def
          FROM pg_constraint
         WHERE contype = 'f'
           AND confrelid = 'iot_devices'::regclass
           AND conrelid <> 'iot_devices'::regclass
    """)).mappings().all()
    conn.execute(text("DROP TABLE iot_devices CASCADE"))
    Base.metadata.create_all(conn, tables=[Base.metadata.tables["iot_devices"]])
    for fk in keep:
        conn.execute(text(f'ALTER TABLE {fk["tbl"]} ADD CONSTRAINT "{fk["conname"]}" {fk["def"]}'))
    logger.warning("rebuilt legacy iot_devices in the model's shape (%d foreign keys restored)", len(keep))
    return True


def _migrate(conn) -> None:
    """Idempotent schema upgrade (runs under the advisory lock)."""
    if conn.dialect.name == "postgresql":
        _rebuild_empty_legacy_devices(conn)
    Base.metadata.create_all(conn)
    if conn.dialect.name != "postgresql":
        return
    insp = inspect(conn)
    existing = {t.name: {c["name"] for c in insp.get_columns(t.name)}
                for t in Base.metadata.sorted_tables if insp.has_table(t.name)}
    for table, ddl, col in missing_column_ddl(existing, dialect=conn.dialect):
        if isinstance(col.type, SAEnum):
            col.type.create(conn, checkfirst=True)
        logger.warning("iot migration: %s", ddl)
        conn.execute(text(ddl))
    # Indexes the model declares on iot_devices that create_all skips for an existing table.
    conn.execute(text('CREATE INDEX IF NOT EXISTS ix_iot_devices_product ON iot_devices (product_id)'))
    conn.execute(text('CREATE INDEX IF NOT EXISTS ix_iot_devices_tenant_id ON iot_devices (tenant_id)'))
    conn.execute(text('CREATE INDEX IF NOT EXISTS ix_iot_devices_device_type ON iot_devices (device_type)'))
    conn.execute(text(
        'CREATE UNIQUE INDEX IF NOT EXISTS ix_iot_devices_tenant_ha_entity '
        'ON iot_devices (tenant_id, ha_entity_id)'
    ))


async def init_tables() -> None:
    """Create all IoT tables and bring pre-existing ones up to the model.

    create_all() never ALTERs an existing table, and `iot_devices` predates this
    service (config/master_schema.sql), so this adds any missing columns and
    rebuilds the still-empty legacy shape. Serialised across workers with a
    Postgres advisory lock.
    """
    engine = get_async_engine()
    is_pg = engine.dialect.name == "postgresql"
    async with engine.connect() as lock_conn:
        if is_pg:
            await lock_conn.execute(text("SELECT pg_advisory_lock(:k)"), {"k": _SCHEMA_LOCK_KEY})
            await lock_conn.commit()
        try:
            async with engine.begin() as conn:
                await conn.run_sync(_migrate)
        finally:
            if is_pg:
                try:
                    await lock_conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _SCHEMA_LOCK_KEY})
                    await lock_conn.commit()
                except Exception:  # noqa: BLE001 - connection close releases the lock anyway
                    logger.warning("could not release iot schema lock explicitly", exc_info=True)


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


def get_session_factory() -> async_sessionmaker:
    """Return the session factory for dependency injection."""
    return _get_session_factory()
