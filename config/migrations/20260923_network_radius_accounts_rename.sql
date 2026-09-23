-- Migration: rename network's RadiusAccount table out of a real, discovered
-- table-name collision with config/master_schema.sql's own, unrelated
-- radius_accounts table (device_id/contact_id/subscription_id-based --
-- see the CREATE TABLE below and compare to services/network/models.py's
-- RadiusAccount, which is service_id/username/password_hash-based).
--
-- Whichever of the two same-named tables existed first silently "won" under
-- SQLAlchemy's checkfirst=True create_all() -- network's actual intended
-- RADIUS-account schema never successfully existed in any DB that also ran
-- master_schema.sql first. This does NOT touch or drop the existing
-- radius_accounts table (still owned by whatever created it in
-- master_schema.sql, with its own live FK dependent radius_accounting.
-- radius_account_id -- unrelated to network's radius_accounting table of the
-- same name, no collision there); it only creates network's table under its
-- own, correctly network_-prefixed name (matching every other table this
-- service owns: network_services, network_devices, network_notifications).
--
-- NOTE: services/network/database.py's init_tables() already creates this
-- table automatically and idempotently on every service boot (see
-- 20260923_fno_passed_homes.sql for the same convention). This file is a
-- manual-apply reference for anyone running raw SQL against a shared DB
-- without going through the app.

CREATE TABLE IF NOT EXISTS network_radius_accounts (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    service_id UUID NOT NULL UNIQUE REFERENCES network_services(id),

    username VARCHAR(100) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    framing_protocol VARCHAR(20) NOT NULL DEFAULT 'PPPoE',
    status radius_account_status NOT NULL DEFAULT 'active',

    profile_name VARCHAR(100) NOT NULL,
    mikrotik_rate_limit VARCHAR(100),

    nas_ip_address VARCHAR(45),
    nas_port_id VARCHAR(100),

    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_network_radius_accounts_tenant ON network_radius_accounts(tenant_id);
CREATE UNIQUE INDEX IF NOT EXISTS ix_network_radius_accounts_username ON network_radius_accounts(tenant_id, username);

-- network's own radius_accounting table (session records) previously
-- pointed its FK at the ambiguous/colliding radius_accounts.id. Repoint it
-- at network's real table. Safe on a fresh/empty radius_accounting table
-- (no orphaned rows to worry about); if a shared DB already has accounting
-- rows referencing the OLD table's ids, those rows should be reviewed
-- before running this on that environment.
ALTER TABLE radius_accounting DROP CONSTRAINT IF EXISTS radius_accounting_radius_account_id_fkey;
ALTER TABLE radius_accounting
    ADD CONSTRAINT radius_accounting_radius_account_id_fkey
    FOREIGN KEY (radius_account_id) REFERENCES network_radius_accounts(id) ON DELETE CASCADE;
