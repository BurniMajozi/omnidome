-- Add tenant metadata columns for domain/settings/branding/active.
-- Safe to run multiple times.

ALTER TABLE tenants
    ADD COLUMN IF NOT EXISTS domain TEXT UNIQUE,
    ADD COLUMN IF NOT EXISTS active BOOLEAN DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS settings JSONB DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS branding JSONB DEFAULT '{}'::jsonb;

-- Backfill defaults for existing rows.
UPDATE tenants
SET domain = subdomain
WHERE domain IS NULL AND subdomain IS NOT NULL;

UPDATE tenants
SET active = CASE
    WHEN status IS NULL THEN TRUE
    WHEN upper(status) = 'ACTIVE' THEN TRUE
    ELSE FALSE
END
WHERE active IS NULL;
