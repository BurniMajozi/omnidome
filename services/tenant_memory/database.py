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
"""


async def init_tables(session: AsyncSession) -> None:
    for statement in [part.strip() for part in CREATE_TABLES_SQL.split(";") if part.strip()]:
        await session.execute(text(statement))

