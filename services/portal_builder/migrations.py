"""Idempotent, advisory-locked startup migrations for the portal builder.

create_all never ALTERs existing tables, so columns added after first deploy are applied here with
ADD COLUMN IF NOT EXISTS, under a Postgres advisory lock so several workers starting at once do not
race on DDL. Safe to run on every boot.
"""

from __future__ import annotations

import logging

from sqlalchemy import text

logger = logging.getLogger("portal_builder.migrations")

SCHEMA_LOCK_KEY = 0x0907A1B1  # arbitrary constant, unique to this service

COLUMN_STATEMENTS = [
    "ALTER TABLE portal_pages ADD COLUMN IF NOT EXISTS unpublished_at TIMESTAMPTZ",
    "ALTER TABLE portal_pages ADD COLUMN IF NOT EXISTS published_version INTEGER",
    "ALTER TABLE portal_page_versions ADD COLUMN IF NOT EXISTS reason VARCHAR(30)",
    "ALTER TABLE portal_submissions ADD COLUMN IF NOT EXISTS consent_given BOOLEAN NOT NULL DEFAULT FALSE",
    "ALTER TABLE portal_submissions ADD COLUMN IF NOT EXISTS consent_at TIMESTAMPTZ",
    "ALTER TABLE portal_submissions ADD COLUMN IF NOT EXISTS consent_text VARCHAR(500)",
    "CREATE INDEX IF NOT EXISTS ix_portal_page_versions_page_num ON portal_page_versions (page_id, version_number)",
]

# Run separately: creation fails if legacy data already has two published pages with one slug.
# In that case public resolution refuses ambiguous slugs (404) until an operator unpublishes one.
GUARDED_STATEMENTS = [
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_portal_pages_published_slug ON portal_pages (lower(slug)) WHERE status = 'published'",
]


def run_migrations() -> None:
    from services.common.db import Base, get_engine
    import services.portal_builder.main  # noqa: F401  (registers models on Base)

    engine = get_engine()
    if engine.dialect.name != "postgresql":
        Base.metadata.create_all(bind=engine)
        return
    lock_conn = engine.connect()
    try:
        lock_conn.execute(text("SELECT pg_advisory_lock(:k)"), {"k": SCHEMA_LOCK_KEY})
        lock_conn.commit()
        Base.metadata.create_all(bind=engine)
        with engine.begin() as conn:
            for stmt in COLUMN_STATEMENTS:
                conn.execute(text(stmt))
        for stmt in GUARDED_STATEMENTS:
            try:
                with engine.begin() as conn:
                    conn.execute(text(stmt))
            except Exception as exc:  # noqa: BLE001
                logger.error("portal_builder: could not apply %r (%s); duplicate published slugs exist?",
                             stmt[:60], type(exc).__name__)
    finally:
        try:
            lock_conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": SCHEMA_LOCK_KEY})
            lock_conn.commit()
        finally:
            lock_conn.close()
