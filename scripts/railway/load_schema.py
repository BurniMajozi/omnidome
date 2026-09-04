#!/usr/bin/env python
"""Load config/master_schema.sql into the Railway Postgres.

psql isn't required. Run it with Railway's Postgres variables injected:

    railway run --service Postgres -- .venv/Scripts/python.exe scripts/railway/load_schema.py

Prefers DATABASE_PUBLIC_URL (reachable from your laptop) over the internal
DATABASE_URL. Idempotent to the extent master_schema.sql is (IF NOT EXISTS etc.).
"""
import os
import sys
from pathlib import Path

import psycopg2

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT / "config" / "master_schema.sql"


def main() -> int:
    if not SCHEMA.exists():
        print(f"ERROR: schema not found at {SCHEMA}", file=sys.stderr)
        return 2
    sql = SCHEMA.read_text(encoding="utf-8")

    # Prefer an explicit URL; otherwise connect via discrete params (libpq PG*
    # env vars), which avoids URL-encoding issues with special chars in the
    # password. Set PGHOST/PGPORT to the tunnel when running through one.
    url = os.environ.get("DATABASE_PUBLIC_URL") or os.environ.get("DATABASE_URL")
    if url:
        where = url.split("@", 1)[-1].split("/", 1)[0]
        connect = lambda: psycopg2.connect(url)
    else:
        host = os.environ.get("PGHOST")
        port = os.environ.get("PGPORT", "5432")
        user = os.environ.get("PGUSER")
        password = os.environ.get("PGPASSWORD")
        dbname = os.environ.get("PGDATABASE") or os.environ.get("POSTGRES_DB")
        if not (host and user and dbname):
            print("ERROR: no DATABASE_URL and PGHOST/PGUSER/PGDATABASE not all set.",
                  file=sys.stderr)
            return 2
        where = f"{host}:{port}/{dbname}"
        connect = lambda: psycopg2.connect(
            host=host, port=port, user=user, password=password, dbname=dbname)

    print(f"[load_schema] connecting to {where}, applying {SCHEMA.name} "
          f"({len(sql)} bytes)…")
    conn = connect()
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(sql)
        print("[load_schema] done.")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
