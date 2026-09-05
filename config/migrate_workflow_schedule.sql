-- Add cron-schedule columns to the existing workflows table.
-- create_all() never ALTERs existing tables, so this backfills the columns
-- introduced with the workflow scheduler. Idempotent — safe to re-run.

ALTER TABLE workflows ADD COLUMN IF NOT EXISTS schedule_cron    VARCHAR(120);
ALTER TABLE workflows ADD COLUMN IF NOT EXISTS schedule_enabled BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE workflows ADD COLUMN IF NOT EXISTS last_run_at      TIMESTAMPTZ;
ALTER TABLE workflows ADD COLUMN IF NOT EXISTS next_run_at      TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS ix_workflows_next_run ON workflows (next_run_at);
