"""Run backend suites with an isolated local Postgres database and remove it afterwards."""
import os
import re
import subprocess
import sys
import uuid
from pathlib import Path
from dotenv import dotenv_values
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url

REPO = Path(__file__).resolve().parents[1]
config = dotenv_values(REPO / ".env")
name = f"coreconnect_codex_{uuid.uuid4().hex[:8]}_test"
if config.get("DATABASE_URL"):
    target = make_url(config["DATABASE_URL"]).set(drivername="postgresql+psycopg2", host="127.0.0.1", port=5432, database=name)
else:
    target = URL.create("postgresql+psycopg2", username=config.get("POSTGRES_USER"), password=config.get("POSTGRES_PASSWORD"), host="127.0.0.1", port=5432, database=name)
env = dict(os.environ, TEST_DATABASE_URL=target.render_as_string(hide_password=False), PYTHONPATH=str(REPO))

def run(args):
    result = subprocess.run([sys.executable, *args], cwd=REPO, env=env, capture_output=True, text=True)
    output = result.stdout + result.stderr
    if result.returncode:
        # Hide URL credentials in diagnostic output, including unexpected tracebacks.
        print(re.sub(r'(postgres(?:ql)?(?:\+\w+)?://[^:\s]+:)[^@\s]+@', r'\1REDACTED@', output[-5000:]))
    else:
        summary = [line for line in output.splitlines() if re.search(r'\d+ passed|created |loaded ', line)]
        print(' | '.join(summary[-3:]))
    return result.returncode

admin = create_engine(target.set(database="postgres"), isolation_level="AUTOCOMMIT", connect_args={"connect_timeout": 10})
try:
    code = run(["scripts/setup_test_db.py"])
    if code:
        sys.exit(code)
    failed = []
    services = sys.argv[1:] or ("billing", "finance", "sales", "crm", "lifecycle", "communication", "iot", "support", "network", "call_center")
    for service in services:
        print(service, end=": ", flush=True)
        if run(["-m", "pytest", f"services/{service}/tests", "-q", "--disable-warnings"]):
            failed.append(service)
    sys.exit(bool(failed))
finally:
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
    admin.dispose()
