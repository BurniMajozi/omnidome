-- Migration: Add protocol persistence tables for UCP checkout sessions and AP2 mandates
-- Depends on: 20260610_add_tenant_memory.sql

CREATE TABLE IF NOT EXISTS ucp_checkout_sessions (
    id VARCHAR(36) PRIMARY KEY,
    tenant_id UUID NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'created',
    currency VARCHAR(3) NOT NULL DEFAULT 'ZAR',
    total DOUBLE PRECISION NOT NULL,
    merchant VARCHAR(200) NOT NULL,
    purpose VARCHAR(500) NOT NULL,
    line_items JSONB NOT NULL DEFAULT '[]'::jsonb,
    payment_mandate_id VARCHAR(200),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ucp_checkout_sessions_tenant
    ON ucp_checkout_sessions(tenant_id, created_at DESC);

CREATE TABLE IF NOT EXISTS ap2_intent_mandates (
    id VARCHAR(36) PRIMARY KEY,
    tenant_id UUID NOT NULL,
    natural_language_description TEXT NOT NULL,
    merchants JSONB NOT NULL DEFAULT '[]'::jsonb,
    max_amount DOUBLE PRECISION NOT NULL,
    currency VARCHAR(3) NOT NULL DEFAULT 'ZAR',
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    requires_user_confirmation BOOLEAN NOT NULL DEFAULT TRUE,
    signed BOOLEAN NOT NULL DEFAULT FALSE,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ap2_intent_mandates_tenant
    ON ap2_intent_mandates(tenant_id, created_at DESC);

CREATE TABLE IF NOT EXISTS ap2_payment_mandates (
    id VARCHAR(36) PRIMARY KEY,
    tenant_id UUID NOT NULL,
    intent_mandate_id VARCHAR(36) NOT NULL,
    payment_details_id VARCHAR(200) NOT NULL,
    merchant_agent VARCHAR(200) NOT NULL,
    amount DOUBLE PRECISION NOT NULL,
    currency VARCHAR(3) NOT NULL DEFAULT 'ZAR',
    label VARCHAR(500) NOT NULL,
    signed_authorization TEXT,
    status VARCHAR(20) NOT NULL DEFAULT 'pending_signature',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ap2_payment_mandates_tenant
    ON ap2_payment_mandates(tenant_id, created_at DESC);

CREATE TABLE IF NOT EXISTS ap2_payment_receipts (
    id VARCHAR(36) PRIMARY KEY,
    tenant_id UUID NOT NULL,
    payment_mandate_id VARCHAR(36) NOT NULL,
    payment_id VARCHAR(200) NOT NULL,
    amount DOUBLE PRECISION NOT NULL,
    currency VARCHAR(3) NOT NULL DEFAULT 'ZAR',
    merchant_confirmation_id VARCHAR(200) NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ap2_payment_receipts_tenant
    ON ap2_payment_receipts(tenant_id, created_at DESC);
