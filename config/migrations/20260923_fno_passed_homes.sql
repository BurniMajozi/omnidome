-- Migration: FNO "homes passed" import tables (sales prospecting pipeline)
--
-- NOTE: services/fno_intelligence/database.py's init_tables() already creates
-- these tables + enums automatically and idempotently on every service boot
-- (it introspects Base.metadata and emits CREATE TYPE IF NOT EXISTS / CREATE
-- TABLE IF NOT EXISTS for whatever's missing). This file is a manual-apply
-- reference for anyone running raw SQL against a shared DB without going
-- through the app -- matches the existing convention of the other files in
-- this directory (they're not run automatically by anything either).
--
-- Depends on: fno_portal enum already existing (created by the base
-- fno_intelligence schema on first boot).

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'passed_home_import_status') THEN
        CREATE TYPE passed_home_import_status AS ENUM ('uploaded', 'parsing', 'imported', 'failed', 'partial');
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'passed_home_status') THEN
        CREATE TYPE passed_home_status AS ENUM ('raw', 'normalized', 'duplicate', 'invalid', 'suppressed_customer');
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'passed_home_dwelling') THEN
        CREATE TYPE passed_home_dwelling AS ENUM ('unknown', 'sdu', 'mdu_unit', 'complex', 'business', 'estate');
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS fno_passed_home_imports (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    fno_name VARCHAR(100) NOT NULL,
    fno_portal fno_portal NOT NULL,

    file_name VARCHAR(500) NOT NULL,
    file_size_bytes INTEGER NOT NULL,
    file_path VARCHAR(1000) NOT NULL,
    column_map JSONB,

    status passed_home_import_status NOT NULL DEFAULT 'uploaded',
    total_rows INTEGER DEFAULT 0,
    inserted_rows INTEGER DEFAULT 0,
    duplicate_rows INTEGER DEFAULT 0,
    invalid_rows INTEGER DEFAULT 0,
    suppressed_rows INTEGER DEFAULT 0,
    error_message TEXT,

    uploaded_by UUID,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    processed_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS ix_fno_passed_home_import_tenant_status
    ON fno_passed_home_imports(tenant_id, status);
CREATE INDEX IF NOT EXISTS ix_fno_passed_home_import_tenant_fno
    ON fno_passed_home_imports(tenant_id, fno_name);

CREATE TABLE IF NOT EXISTS fno_passed_homes (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    import_id UUID NOT NULL REFERENCES fno_passed_home_imports(id) ON DELETE CASCADE,
    fno_name VARCHAR(100) NOT NULL,
    fno_portal fno_portal NOT NULL,

    address_raw TEXT NOT NULL,
    address_line1 VARCHAR(255),
    suburb VARCHAR(200),
    city VARCHAR(100),
    province VARCHAR(50),
    postal_code VARCHAR(10),

    dwelling_type passed_home_dwelling NOT NULL DEFAULT 'unknown',
    unit_count INTEGER,
    date_passed DATE,

    status passed_home_status NOT NULL DEFAULT 'raw',
    dedup_key VARCHAR(500) NOT NULL,
    raw_row JSONB NOT NULL DEFAULT '{}'::jsonb,
    reject_reason VARCHAR(300),

    created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_fno_passed_home_tenant_status ON fno_passed_homes(tenant_id, status);
CREATE INDEX IF NOT EXISTS ix_fno_passed_home_dedup ON fno_passed_homes(tenant_id, fno_name, dedup_key);
CREATE INDEX IF NOT EXISTS ix_fno_passed_home_location ON fno_passed_homes(tenant_id, city, suburb);
CREATE INDEX IF NOT EXISTS ix_fno_passed_home_import ON fno_passed_homes(import_id);
CREATE INDEX IF NOT EXISTS ix_fno_passed_home_postal ON fno_passed_homes(postal_code);
