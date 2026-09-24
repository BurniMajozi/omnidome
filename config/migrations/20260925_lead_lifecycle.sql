-- Lead lifecycle (SPEC-lead-lifecycle.md): reference numbers, owner, priority,
-- closed/escalated dates, activity timeline, tasks, one stage model. Idempotent.
-- Also applied at sales startup by services/sales/schema.ensure_lead_schema()
-- (keep the two identical).
ALTER TABLE leads ADD COLUMN IF NOT EXISTS ref_no INTEGER;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS owner_name VARCHAR(200);
ALTER TABLE leads ADD COLUMN IF NOT EXISTS priority VARCHAR(10) NOT NULL DEFAULT 'normal';
ALTER TABLE leads ADD COLUMN IF NOT EXISTS closed_at TIMESTAMPTZ;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS close_reason TEXT;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS escalated_at TIMESTAMPTZ;

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
CREATE INDEX IF NOT EXISTS ix_deals_lead_id ON deals (lead_id);

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
   AND l.status IS DISTINCT FROM CASE d.status WHEN 'WON' THEN 'WON' WHEN 'LOST' THEN 'LOST' ELSE 'CONVERTED' END;
