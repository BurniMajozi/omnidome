"""Idempotent schema changes for the lead lifecycle (SPEC-lead-lifecycle.md).

create_all() creates missing tables but never ALTERs existing ones, so the new
lead columns, the reference backfill and the one-off status migration run here
at startup (serialised by an advisory lock), mirrored in
config/migrations/20260925_lead_lifecycle.sql. Every statement is safe to re-run.
"""

from __future__ import annotations

import logging
import re

from sqlalchemy import text

LEAD_LIFECYCLE_SQL = """
ALTER TABLE leads ADD COLUMN IF NOT EXISTS ref_no INTEGER;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS owner_id UUID;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS owner_name VARCHAR(200);
ALTER TABLE leads ADD COLUMN IF NOT EXISTS priority VARCHAR(10) NOT NULL DEFAULT 'normal';
ALTER TABLE leads ADD COLUMN IF NOT EXISTS closed_at TIMESTAMPTZ;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS close_reason TEXT;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS escalated_at TIMESTAMPTZ;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS source_channel VARCHAR(50);

WITH top AS (
    SELECT tenant_id, max(ref_no) AS max_ref FROM leads GROUP BY tenant_id
), numbered AS (
    SELECT l.id,
           coalesce(top.max_ref, 0)
             + row_number() OVER (PARTITION BY l.tenant_id ORDER BY l.created_at, l.id) AS n
      FROM leads l JOIN top ON top.tenant_id = l.tenant_id
     WHERE l.ref_no IS NULL
)
UPDATE leads SET ref_no = numbered.n FROM numbered WHERE leads.id = numbered.id;

CREATE UNIQUE INDEX IF NOT EXISTS uq_leads_tenant_ref ON leads (tenant_id, ref_no);
CREATE INDEX IF NOT EXISTS ix_leads_tenant_status ON leads (tenant_id, status);
CREATE INDEX IF NOT EXISTS ix_leads_tenant_source_channel ON leads (tenant_id, source_channel);
CREATE INDEX IF NOT EXISTS ix_deals_lead_id ON deals (lead_id);

-- Mirrors lead_stages.normalize_channel: allow-listed values, WHOLE-WORD matches
-- (so BROADBAND is not "ad"), anything else is OTHER. A previous backfill that
-- stored raw/odd values is redone: rows outside the allow-list are reset first.
UPDATE leads SET source_channel = NULL
 WHERE source_channel IS NOT NULL
   AND source_channel NOT IN ('MARKETING', 'INBOUND_EMAIL', 'CALL_CENTER_INBOUND', 'CALL_CENTER_OUTBOUND',
                              'PORTAL_WEBSITE', 'FIELD_SALES', 'WALK_IN', 'REFERRAL', 'COMPANY_SEARCH', 'TENDER', 'OTHER');

UPDATE leads SET source_channel = CASE
    WHEN upper(regexp_replace(trim(source), '[^A-Za-z0-9]+', '_', 'g'))
         IN ('MARKETING', 'INBOUND_EMAIL', 'CALL_CENTER_INBOUND', 'CALL_CENTER_OUTBOUND', 'PORTAL_WEBSITE',
             'FIELD_SALES', 'WALK_IN', 'REFERRAL', 'COMPANY_SEARCH', 'TENDER', 'OTHER')
         THEN upper(regexp_replace(trim(source), '[^A-Za-z0-9]+', '_', 'g'))
    WHEN source ~* '(^|[^a-z0-9])(company)([^a-z0-9]|$)' THEN 'COMPANY_SEARCH'
    WHEN source ~* '(^|[^a-z0-9])(field|door|visit|canvass|canvassing)([^a-z0-9]|$)' THEN 'FIELD_SALES'
    WHEN source ~* '(^|[^a-z0-9])(call|calls|calling|phone)([^a-z0-9]|$)' AND source ~* '(^|[^a-z0-9])(inbound|in|incoming)([^a-z0-9]|$)' THEN 'CALL_CENTER_INBOUND'
    WHEN source ~* '(^|[^a-z0-9])(call|calls|calling|phone)([^a-z0-9]|$)' THEN 'CALL_CENTER_OUTBOUND'
    WHEN source ~* '(^|[^a-z0-9])(outbound|out|outgoing|tele|telesales|telemarketing|cold)([^a-z0-9]|$)' THEN 'CALL_CENTER_OUTBOUND'
    WHEN source ~* '(^|[^a-z0-9])(market|marketing|campaign|social|ad|ads|advert|adverts|advertising|advertisement)([^a-z0-9]|$)' THEN 'MARKETING'
    WHEN source ~* '(^|[^a-z0-9])(portal|web|website|webform|online|site)([^a-z0-9]|$)' THEN 'PORTAL_WEBSITE'
    WHEN source ~* '(^|[^a-z0-9])(tender|tenders|rfq|rfp|procurement)([^a-z0-9]|$)' THEN 'TENDER'
    WHEN source ~* '(^|[^a-z0-9])(email|mail|emails)([^a-z0-9]|$)' THEN 'INBOUND_EMAIL'
    WHEN source ~* '(^|[^a-z0-9])(walk|walkin|walkins|branch|store)([^a-z0-9]|$)' THEN 'WALK_IN'
    WHEN source ~* '(^|[^a-z0-9])(referral|referrals|refer|referred|partner|affiliate)([^a-z0-9]|$)' THEN 'REFERRAL'
    WHEN notes ILIKE '%company search%' THEN 'COMPANY_SEARCH'
    ELSE 'OTHER'
END
WHERE source_channel IS NULL;

CREATE TABLE IF NOT EXISTS lead_activities (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    lead_id UUID NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    kind VARCHAR(40) NOT NULL,
    summary VARCHAR(300) NOT NULL,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    actor_id UUID,
    actor_name VARCHAR(200),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_lead_activities_lead ON lead_activities (lead_id, created_at DESC);
-- record_activity(idempotency_key=...) stores the key in details, one row per (lead, kind, key).
CREATE UNIQUE INDEX IF NOT EXISTS uq_lead_activities_idem ON lead_activities (lead_id, kind, (details->>'idem_key'))
    WHERE details->>'idem_key' IS NOT NULL;

CREATE TABLE IF NOT EXISTS lead_tasks (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    lead_id UUID NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    title VARCHAR(200) NOT NULL,
    kind VARCHAR(20) NOT NULL DEFAULT 'task',
    due_at TIMESTAMPTZ,
    assignee_id UUID,
    assignee_name VARCHAR(200),
    status VARCHAR(20) NOT NULL DEFAULT 'open',
    created_by UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS ix_lead_tasks_lead ON lead_tasks (lead_id, status);
CREATE INDEX IF NOT EXISTS ix_lead_tasks_open ON lead_tasks (tenant_id, status, due_at);

-- One stage model (lead_stages.py): free-form pipeline statuses on leads without
-- a deal become QUALIFIED, and leads with a deal mirror the latest deal status.
UPDATE leads l SET status = 'QUALIFIED'
 WHERE l.status IN ('PROPOSAL', 'NEGOTIATION', 'CONVERTED')
   AND NOT EXISTS (SELECT 1 FROM deals d WHERE d.lead_id = l.id);
UPDATE leads l SET status = 'DISQUALIFIED', closed_at = coalesce(l.closed_at, l.updated_at, l.created_at)
 WHERE l.status = 'LOST'
   AND NOT EXISTS (SELECT 1 FROM deals d WHERE d.lead_id = l.id);
UPDATE leads l
   SET status = CASE d.status WHEN 'WON' THEN 'WON' WHEN 'LOST' THEN 'LOST' ELSE 'CONVERTED' END,
       closed_at = CASE WHEN d.status IN ('WON', 'LOST') THEN coalesce(l.closed_at, d.closed_at) ELSE l.closed_at END
  FROM (SELECT DISTINCT ON (lead_id) lead_id, status, closed_at
          FROM deals WHERE lead_id IS NOT NULL
         ORDER BY lead_id, created_at DESC) d
 WHERE d.lead_id = l.id
   AND l.status IS DISTINCT FROM CASE d.status WHEN 'WON' THEN 'WON' WHEN 'LOST' THEN 'LOST' ELSE 'CONVERTED' END
"""

_LOCK = 0x5A1E5  # advisory lock: one worker runs the DDL


async def ensure_lead_schema(session) -> None:
    await session.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _LOCK})
    for statement in LEAD_LIFECYCLE_SQL.split(";"):
        # Skip fragments that are only comments: asyncpg cannot execute them.
        if re.sub(r"--[^\n]*", "", statement).strip():
            await session.execute(text(statement))


# ── Pipeline / commission integrity (sales hardening) ─────────────────────────
# One default pipeline per tenant, unique stage names per pipeline, one live
# commission per deal. create_all() never adds an index to an existing table, so
# these run at startup under an advisory lock and are safe to re-run. Indexes
# that would fail on data that is already duplicated are skipped with a warning
# instead of keeping the service from starting.

logger = logging.getLogger("sales.schema")

_PIPELINE_LOCK = 0x5A1E6

DEDUPE_DEFAULT_PIPELINES_SQL = """
WITH ranked AS (
    SELECT p.id,
           row_number() OVER (
               PARTITION BY p.tenant_id
               ORDER BY (SELECT count(*) FROM deals d JOIN deal_stages s ON s.id = d.stage_id
                          WHERE s.pipeline_id = p.id) DESC, p.id
           ) AS rn
      FROM pipelines p
     WHERE p.is_default
)
UPDATE pipelines SET is_default = false FROM ranked WHERE ranked.id = pipelines.id AND ranked.rn > 1
"""

# (name, check for existing duplicates, create statement)
_GUARDED_UNIQUE_INDEXES = (
    (
        "uq_pipelines_one_default",
        "SELECT count(*) FROM (SELECT 1 FROM pipelines WHERE is_default GROUP BY tenant_id HAVING count(*) > 1) d",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_pipelines_one_default ON pipelines (tenant_id) WHERE is_default",
    ),
    (
        "uq_deal_stages_pipeline_name",
        "SELECT count(*) FROM (SELECT 1 FROM deal_stages GROUP BY pipeline_id, lower(name) HAVING count(*) > 1) d",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_deal_stages_pipeline_name ON deal_stages (pipeline_id, lower(name))",
    ),
    (
        "uq_commissions_deal_live",
        "SELECT count(*) FROM (SELECT 1 FROM commissions WHERE status <> 'CLAWBACK' GROUP BY deal_id HAVING count(*) > 1) d",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_commissions_deal_live ON commissions (deal_id) WHERE status <> 'CLAWBACK'",
    ),
)


async def ensure_pipeline_integrity(session) -> None:
    await session.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _PIPELINE_LOCK})
    demoted = await session.execute(text(DEDUPE_DEFAULT_PIPELINES_SQL))
    if demoted.rowcount:
        logger.warning("Demoted %d duplicate default pipeline(s); kept the one holding the most deals",
                       demoted.rowcount)
    for name, check_sql, create_sql in _GUARDED_UNIQUE_INDEXES:
        duplicates = (await session.execute(text(check_sql))).scalar() or 0
        if duplicates:
            logger.warning("Not creating %s: %d group(s) already hold duplicates; clean them up first", name,
                           duplicates)
            continue
        await session.execute(text(create_sql))
