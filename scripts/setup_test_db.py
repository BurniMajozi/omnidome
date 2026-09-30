"""Build the throwaway database for DB-backed service tests.

    TEST_DATABASE_URL=postgresql://user:pass@localhost:5432/omnidome_test \
        python scripts/setup_test_db.py

Drops and recreates the database named in TEST_DATABASE_URL (it must end in
"_test"), loads config/master_schema.sql, then creates each service's own
tables the way the services do at start-up (init_tables). Run from the repo
root with the repo on PYTHONPATH.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402

from services.common.testdb import test_database_url  # noqa: E402


def main() -> None:
    url = test_database_url()
    if not url:
        sys.exit("Set TEST_DATABASE_URL (database name must end in _test)")
    target = make_url(url)
    admin = create_engine(target.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{target.database}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{target.database}"'))
    admin.dispose()
    print(f"created {target.database}")

    engine = create_engine(url)
    raw = engine.raw_connection()   # the schema has literal % signs: no parameter parsing
    try:
        with raw.cursor() as cur:
            cur.execute((REPO / "config" / "master_schema.sql").read_text(encoding="utf-8"))
        raw.commit()
    finally:
        raw.close()
    engine.dispose()
    print("loaded config/master_schema.sql")

    os.environ["DATABASE_URL"] = url
    from services.billing.database import init_tables as billing_tables
    from services.common.db import session_scope
    from services.communication.database import init_tables as communication_tables
    from services.crm.database import init_tables as crm_tables
    from services.tenant_memory.database import init_tables as memory_tables

    crm_tables()
    billing_tables()

    async def memory() -> None:
        async with session_scope() as session:
            await memory_tables(session)
        await communication_tables()   # same event loop: the async engine is cached and loop-bound

    asyncio.run(memory())
    print("created crm, billing, tenant_memory and communication tables")


if __name__ == "__main__":
    main()
