-- Migration: 20260925_agent_hardening.sql
-- Description: Creates llm_calls, agent_turns, and agent_approvals tables for agent hardening & memory management (A7, A8)

CREATE TABLE IF NOT EXISTS llm_calls (
    id UUID PRIMARY KEY,
    tenant_id UUID,
    agent_type VARCHAR(50),
    channel VARCHAR(60),
    model VARCHAR(160),
    prompt_tokens INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    total_tokens INTEGER NOT NULL DEFAULT 0,
    latency_ms INTEGER NOT NULL DEFAULT 0,
    outcome VARCHAR(20) NOT NULL,
    purpose VARCHAR(20) NOT NULL DEFAULT 'round',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_llm_calls_tenant_time ON llm_calls (tenant_id, created_at DESC);

CREATE TABLE IF NOT EXISTS agent_turns (
    id UUID PRIMARY KEY,
    tenant_id UUID,
    agent_type VARCHAR(50),
    channel VARCHAR(60),
    rounds INTEGER NOT NULL DEFAULT 0,
    tool_calls INTEGER NOT NULL DEFAULT 0,
    total_tokens INTEGER NOT NULL DEFAULT 0,
    duration_ms INTEGER NOT NULL DEFAULT 0,
    stopped_by VARCHAR(20),
    unavailable BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_agent_turns_tenant_time ON agent_turns (tenant_id, created_at DESC);

CREATE TABLE IF NOT EXISTS agent_approvals (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    agent_type VARCHAR(50) NOT NULL,
    tool_name VARCHAR(100) NOT NULL,
    arguments JSONB NOT NULL DEFAULT '{}'::jsonb,
    conversation_id UUID,
    run_id UUID,
    requested_by VARCHAR(100),
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    rejection_reason TEXT,
    execution_result JSONB,
    executed_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ NOT NULL,
    decided_at TIMESTAMPTZ,
    decided_by VARCHAR(100),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_agent_approvals_tenant_status ON agent_approvals (tenant_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_agent_approvals_agent ON agent_approvals (tenant_id, agent_type, status);
