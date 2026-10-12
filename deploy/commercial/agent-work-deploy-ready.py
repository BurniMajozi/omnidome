"""Protect ongoing managed tasks during orchestrator deployment; no prompt data printed."""
from sqlalchemy import text
from services.common.db import get_engine
with get_engine().connect() as db:
    count = db.execute(text("SELECT count(*) FROM agent_jobs WHERE status IN ('running','pause_requested','queued')")).scalar_one()
print("Active or queued managed tasks:",count)
raise SystemExit(1 if count else 0)
