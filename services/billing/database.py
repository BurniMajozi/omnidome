"""Database session management for the Billing service."""

import logging
import uuid
from contextlib import contextmanager
from decimal import Decimal
from typing import Generator, List

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session, sessionmaker

from services.common.db import get_engine
from services.billing.models import Base, InvoiceSequence


logger = logging.getLogger("billing.database")
_session_factory: sessionmaker | None = None
VAT_RATE = Decimal("0.15")


def _get_session_factory() -> sessionmaker:
    global _session_factory
    if _session_factory is None:
        engine = get_engine()
        _session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    return _session_factory


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """Yield a transactional DB session and commit on success."""
    factory = _get_session_factory()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


_SCHEMA_LOCK_KEY = 0x0B111_5EA7  # arbitrary constant: serialises startup DDL across workers


def init_tables() -> None:
    """Create all Billing tables if they don't exist (dev convenience).

    Runs under a Postgres advisory lock so several uvicorn workers starting at
    once don't deadlock on the ALTERs.
    """
    engine = get_engine()
    is_pg = engine.dialect.name == "postgresql"
    lock_conn = engine.connect() if is_pg else None
    try:
        if lock_conn is not None:
            lock_conn.execute(text("SELECT pg_advisory_lock(:k)"), {"k": _SCHEMA_LOCK_KEY})
            lock_conn.commit()
        reconcile_legacy_tables(engine)
        Base.metadata.create_all(bind=engine)
        with engine.begin() as conn:
            for statement in _RESTORED_COLUMNS + _SEAT_BILLING_COLUMNS:
                conn.execute(text(statement))
    finally:
        if lock_conn is not None:
            try:
                lock_conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _SCHEMA_LOCK_KEY})
                lock_conn.commit()
            finally:
                lock_conn.close()


# Per-seat billing columns on tables that may predate them (create_all never
# ALTERs). seat_billing_runs / seat_proration_charges are new tables, so
# create_all builds them.
_SEAT_BILLING_COLUMNS = [
    "ALTER TABLE billing_plans ADD COLUMN IF NOT EXISTS pricing_model VARCHAR(20) NOT NULL DEFAULT 'flat'",
    "ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS quantity INTEGER NOT NULL DEFAULT 1",
    "ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS current_period_start DATE",
    "ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS current_period_end DATE",
]


# Columns that went missing from billing-shaped tables and came back
# (create_all never adds a column to an existing table).
_RESTORED_COLUMNS = [
    "ALTER TABLE invoices ADD COLUMN IF NOT EXISTS line_items JSONB",
    "ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS plan VARCHAR(100) NOT NULL DEFAULT ''",
]


# Before 2026-09-30, config/master_schema.sql created subscriptions / invoices /
# payments in an older shape (invoice_number, amount, start_date, gateway, ...)
# and create_all() never alters an existing table, so on any database built
# from it billing's invoicing, payments and subscriptions could not work.
# master_schema.sql now matches billing's models; this upgrades databases built
# before that. A legacy table is rebuilt only while it is EMPTY (it always was:
# nothing could write to it); one with rows is left alone and logged.
_LEGACY_MARKERS = {"payments": "gateway", "invoices": "invoice_number", "subscriptions": "start_date"}


def reconcile_legacy_tables(engine) -> List[str]:
    """Rebuild empty legacy-shaped billing tables in billing's shape, keeping
    every foreign key other tables had to them. Returns the rebuilt tables."""
    insp = inspect(engine)
    rebuild: List[str] = []
    with engine.begin() as conn:
        for table, marker in _LEGACY_MARKERS.items():
            if not insp.has_table(table):
                continue
            cols = {c["name"] for c in insp.get_columns(table)}
            if marker not in cols or "customer_id" in cols:
                continue
            rows = conn.execute(text(f"SELECT count(*) FROM {table}")).scalar()
            if rows:
                logger.error("billing table %s is in the legacy shape and has %s rows; migrate it by hand", table, rows)
                continue
            rebuild.append(table)
        if not rebuild:
            return []
        # Foreign keys from other tables into the ones being rebuilt (DROP ... CASCADE removes them).
        keep = conn.execute(text("""
            SELECT conrelid::regclass::text AS tbl, conname, pg_get_constraintdef(oid) AS def
              FROM pg_constraint
             WHERE contype = 'f'
               AND confrelid::regclass::text = ANY(:targets)
               AND NOT (conrelid::regclass::text = ANY(:targets))
        """), {"targets": rebuild}).mappings().all()
        for table in rebuild:          # payments -> invoices -> subscriptions
            conn.execute(text(f"DROP TABLE {table} CASCADE"))
    Base.metadata.create_all(bind=engine, tables=[Base.metadata.tables[t] for t in rebuild])
    with engine.begin() as conn:
        for fk in keep:
            conn.execute(text(f'ALTER TABLE {fk["tbl"]} ADD CONSTRAINT "{fk["conname"]}" {fk["def"]}'))
    logger.warning("rebuilt legacy billing tables %s in billing's shape (%d foreign keys restored)", rebuild, len(keep))
    return rebuild


def next_invoice_number(session: Session, tenant_id: uuid.UUID) -> str:
    """Generate the next sequential invoice number for a tenant.

    Uses a `FOR UPDATE` lock on the sequence row to prevent duplicates
    under concurrent generation.
    """
    seq = (
        session.query(InvoiceSequence)
        .filter(InvoiceSequence.tenant_id == tenant_id)
        .with_for_update()
        .first()
    )
    if seq is None:
        seq = InvoiceSequence(tenant_id=tenant_id, last_number=0)
        session.add(seq)
        session.flush()

    seq.last_number += 1
    session.flush()

    short_tenant = str(tenant_id).split("-")[0].upper()[:4]
    return f"INV-{short_tenant}-{seq.last_number:06d}"


def compute_vat(subtotal: Decimal) -> Decimal:
    """Compute 15% SA VAT on a subtotal."""
    return (subtotal * VAT_RATE).quantize(Decimal("0.01"))
