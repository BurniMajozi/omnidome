from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS tenant_memory_entries (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    source_type VARCHAR(80) NOT NULL,
    source_id VARCHAR(160),
    module VARCHAR(80),
    scope_key VARCHAR(160),
    title VARCHAR(240) NOT NULL,
    content TEXT NOT NULL,
    summary TEXT,
    visibility VARCHAR(20) NOT NULL DEFAULT 'tenant',
    importance VARCHAR(20) NOT NULL DEFAULT 'normal',
    tags TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_by UUID REFERENCES users(id) ON DELETE SET NULL,
    occurred_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    archived_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CHECK (visibility IN ('private', 'team', 'tenant', 'system')),
    CHECK (importance IN ('low', 'normal', 'high', 'critical'))
);

CREATE INDEX IF NOT EXISTS idx_memory_entries_tenant_time
    ON tenant_memory_entries(tenant_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_memory_entries_scope
    ON tenant_memory_entries(tenant_id, scope_key, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_memory_entries_module
    ON tenant_memory_entries(tenant_id, module, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_memory_entries_tags
    ON tenant_memory_entries USING gin(tags);
CREATE INDEX IF NOT EXISTS idx_memory_entries_search
    ON tenant_memory_entries USING gin(
        to_tsvector('english', coalesce(title, '') || ' ' || coalesce(summary, '') || ' ' || coalesce(content, ''))
    );

CREATE TABLE IF NOT EXISTS tenant_memory_summaries (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    scope_key VARCHAR(160) NOT NULL,
    module VARCHAR(80),
    title VARCHAR(240) NOT NULL,
    summary TEXT NOT NULL,
    source_entry_ids UUID[] NOT NULL DEFAULT ARRAY[]::UUID[],
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_by UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (tenant_id, scope_key)
);

CREATE INDEX IF NOT EXISTS idx_memory_summaries_tenant
    ON tenant_memory_summaries(tenant_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_memory_summaries_module
    ON tenant_memory_summaries(tenant_id, module, updated_at DESC);

CREATE TABLE IF NOT EXISTS tenant_agent_skills (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    skill_name VARCHAR(120) NOT NULL,
    description TEXT NOT NULL,
    category VARCHAR(80) NOT NULL DEFAULT 'operational',
    source_agent_type VARCHAR(80) NOT NULL,
    target_agent_types TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    protocol_schema JSONB NOT NULL DEFAULT '{}'::jsonb,
    tools_required TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    guidance_prompt TEXT NOT NULL,
    version VARCHAR(20) NOT NULL DEFAULT '1.0.0',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (tenant_id, skill_name, version)
);

CREATE INDEX IF NOT EXISTS idx_tenant_agent_skills_tenant
    ON tenant_agent_skills(tenant_id, is_active, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_tenant_agent_skills_source
    ON tenant_agent_skills(tenant_id, source_agent_type);

-- Short-term (working) memory: per-session scratchpad with a TTL. Promoted into
-- tenant_memory_entries by the consolidation job (explicit pin, importance, repetition).
CREATE TABLE IF NOT EXISTS tenant_memory_working (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    session_key VARCHAR(160) NOT NULL,
    kind VARCHAR(20) NOT NULL DEFAULT 'note',
    module VARCHAR(80),
    title VARCHAR(240),
    content TEXT NOT NULL,
    importance VARCHAR(20) NOT NULL DEFAULT 'normal',
    pinned BOOLEAN NOT NULL DEFAULT FALSE,
    repeat_count INT NOT NULL DEFAULT 1,
    content_key VARCHAR(64) NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_by UUID,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    promoted_entry_id UUID,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CHECK (kind IN ('turn', 'state', 'context_ref', 'note')),
    CHECK (importance IN ('low', 'normal', 'high', 'critical'))
);
CREATE INDEX IF NOT EXISTS idx_memory_working_session ON tenant_memory_working(tenant_id, session_key, created_at);
CREATE INDEX IF NOT EXISTS idx_memory_working_expiry ON tenant_memory_working(expires_at);
CREATE INDEX IF NOT EXISTS idx_memory_working_key ON tenant_memory_working(tenant_id, content_key);

-- Deterministic metric facts. Written ONLY by deterministic code (BI semantic-layer runs, forecast
-- jobs) - never by an LLM. Cards rendered from these rows are embedded for context; exact values are
-- always re-fetched through the governed query referenced in source_query.
CREATE TABLE IF NOT EXISTS tenant_metric_facts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    metric_key VARCHAR(120) NOT NULL,
    label VARCHAR(160),
    dimensions JSONB NOT NULL DEFAULT '{}'::jsonb,
    dimensions_hash VARCHAR(32) NOT NULL,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    grain VARCHAR(10),
    value NUMERIC(24, 6) NOT NULL,
    unit VARCHAR(20) NOT NULL DEFAULT 'count',
    kind VARCHAR(10) NOT NULL DEFAULT 'actual',
    lower_bound NUMERIC(24, 6),
    upper_bound NUMERIC(24, 6),
    interval_level REAL,
    model_name VARCHAR(120),
    model_version VARCHAR(60) NOT NULL DEFAULT '',
    method VARCHAR(80) NOT NULL,
    confidence REAL,
    source_query JSONB,
    source_query_key VARCHAR(64),
    as_of TIMESTAMP WITH TIME ZONE NOT NULL,
    written_by VARCHAR(30) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CHECK (kind IN ('actual', 'forecast', 'target')),
    CHECK (written_by IN ('bi_semantic', 'forecast_run', 'system')),
    CHECK (period_end >= period_start),
    CHECK (kind <> 'forecast' OR (model_name IS NOT NULL AND model_version <> ''))
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_metric_facts_identity
    ON tenant_metric_facts(tenant_id, metric_key, dimensions_hash, period_start, period_end, kind, model_version);
CREATE INDEX IF NOT EXISTS idx_metric_facts_updated ON tenant_metric_facts(tenant_id, updated_at);
"""


async def init_tables(session: AsyncSession) -> None:
    for statement in [part.strip() for part in CREATE_TABLES_SQL.split(";") if part.strip()]:
        await session.execute(text(statement))

