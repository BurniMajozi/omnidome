"""Run inventory transaction/migration tests in a new dedicated local Postgres database.

Reads local credentials without displaying them. Never opens the live application database.
The test database is created for this run and removed in finally.
"""
import os
import subprocess
import sys
from pathlib import Path
from dotenv import dotenv_values
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url, URL

REPO = Path(__file__).resolve().parents[1]
config = dotenv_values(REPO / ".env")
if config.get("DATABASE_URL"):
    target = make_url(config["DATABASE_URL"]).set(drivername="postgresql+psycopg2", host="127.0.0.1", port=5432, database="coreconnect_inventory_test")
else:
    target = URL.create("postgresql+psycopg2", username=config.get("POSTGRES_USER"), password=config.get("POSTGRES_PASSWORD"), host="127.0.0.1", port=5432, database="coreconnect_inventory_test")
admin = create_engine(target.set(database="postgres"), isolation_level="AUTOCOMMIT", connect_args={"connect_timeout": 10})
created = False
try:
    with admin.connect() as conn:
        # Refuse to replace a database someone else may be using.
        conn.execute(text('CREATE DATABASE "coreconnect_inventory_test"'))
        created = True
    env = dict(os.environ, TEST_DATABASE_URL=target.render_as_string(hide_password=False), PYTHONPATH=str(REPO))
    result = subprocess.run([sys.executable, "-m", "pytest", "services/inventory/tests/test_stock_db.py", "-q", "--disable-warnings"], cwd=REPO, env=env)
    sys.exit(result.returncode)
finally:
    if created:
        with admin.connect() as conn:
            conn.execute(text('DROP DATABASE "coreconnect_inventory_test" WITH (FORCE)'))
    admin.dispose()
