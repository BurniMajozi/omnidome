"""Idempotent, locked schema upgrades for the CRM (create_all never ALTERs existing tables).

Runs at startup under a Postgres advisory lock so several replicas cannot race. Never raises:
a failure is logged and startup continues (the dedupe checks in the routes still work without
the unique indexes; the indexes are the safety net for concurrent writers).

  1. customers.phone_normalized  (new column, backfilled from customers.phone)
  2. customers.email             (NOT NULL dropped: a lead without e-mail converts to NULL, not '')
  3. unique (tenant_id, phone_normalized) WHERE phone_normalized IS NOT NULL
     unique (tenant_id, lower(email))     WHERE email IS NOT NULL AND email <> ''
     Each index is created only if the tenant data has no duplicates; otherwise the duplicate
     groups are logged (counts only, no PII) and the index is skipped.
"""

from __future__ import annotations

import logging

from sqlalchemy import text

from services.crm.normalize import normalize_phone

logger = logging.getLogger("crm.migrations")

LOCK_KEY = 726_014_001  # arbitrary, unique to the CRM schema upgrade
BACKFILL_BATCH = 500

INDEXES = {
    "uq_customers_tenant_phone_norm": (
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_customers_tenant_phone_norm "
        "ON customers (tenant_id, phone_normalized) WHERE phone_normalized IS NOT NULL",
        "SELECT count(*) FROM (SELECT 1 FROM customers WHERE phone_normalized IS NOT NULL "
        "GROUP BY tenant_id, phone_normalized HAVING count(*) > 1) d",
    ),
    "uq_customers_tenant_email_lower": (
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_customers_tenant_email_lower "
        "ON customers (tenant_id, lower(email)) WHERE email IS NOT NULL AND email <> ''",
        "SELECT count(*) FROM (SELECT 1 FROM customers WHERE email IS NOT NULL AND email <> '' "
        "GROUP BY tenant_id, lower(email) HAVING count(*) > 1) d",
    ),
}


def backfill_phone_normalized(conn) -> int:
    """Fill phone_normalized for rows that have a phone but no normalised value yet."""
    done = 0
    last_id = None
    while True:
        rows = conn.execute(
            text(
                "SELECT id, phone FROM customers WHERE phone IS NOT NULL AND phone_normalized IS NULL "
                "AND (:last IS NULL OR id::text > :last) ORDER BY id::text LIMIT :n"
            ),
            {"last": last_id, "n": BACKFILL_BATCH},
        ).all()
        if not rows:
            return done
        for row_id, phone in rows:
            norm = normalize_phone(phone)
            if norm:
                conn.execute(text("UPDATE customers SET phone_normalized = :p WHERE id = :i"),
                             {"p": norm, "i": row_id})
                done += 1
        last_id = str(rows[-1][0])


def ensure_schema(engine=None) -> None:
    try:
        if engine is None:
            from services.common.db import get_engine

            engine = get_engine()
        if engine.dialect.name != "postgresql":
            return
        with engine.connect() as conn:
            conn.execute(text("SELECT pg_advisory_lock(:k)"), {"k": LOCK_KEY})
            try:
                if conn.execute(text("SELECT to_regclass('public.customers')")).scalar() is None:
                    logger.info("customers table not present yet; CRM schema upgrade skipped")
                    return
                conn.execute(text("ALTER TABLE customers ADD COLUMN IF NOT EXISTS phone_normalized VARCHAR(20)"))
                conn.execute(text("ALTER TABLE customers ALTER COLUMN email DROP NOT NULL"))
                conn.commit()

                filled = backfill_phone_normalized(conn)
                conn.commit()
                if filled:
                    logger.info("CRM migration: phone_normalized backfilled for %d customers", filled)

                for name, (create_sql, dup_sql) in INDEXES.items():
                    dups = conn.execute(text(dup_sql)).scalar() or 0
                    if dups:
                        logger.warning("CRM migration: index %s skipped, %d duplicate groups exist "
                                       "(merge the duplicates, then restart)", name, dups)
                        continue
                    conn.execute(text(create_sql))
                    conn.commit()
            finally:
                conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": LOCK_KEY})
                conn.commit()
    except Exception as exc:  # noqa: BLE001 - never block startup
        logger.warning("CRM schema upgrade failed: %s: %s", type(exc).__name__, exc)
