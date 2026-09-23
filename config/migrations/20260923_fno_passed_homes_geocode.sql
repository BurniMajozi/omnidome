-- Migration: geocoding columns for fno_passed_homes (Ticket 2 of the fibre
-- prospecting pipeline: geocode worker filling gps_lat/gps_lng)
--
-- NOTE: unlike a brand-new table, services/fno_intelligence/database.py's
-- init_tables() will NOT retroactively add these columns to the existing
-- fno_passed_homes table on service boot -- SQLAlchemy's create_all() only
-- creates tables that don't exist yet, it never ALTERs an existing one. The
-- new enum type IS created automatically (init_tables() scans all mapped
-- columns for enum types before running create_all()), but this file's
-- ALTER TABLE statements must be applied manually against any DB that
-- already has fno_passed_homes from Ticket 1.
--
-- Depends on: fno_passed_homes already existing (20260923_fno_passed_homes.sql).

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'passed_home_geocode_status') THEN
        CREATE TYPE passed_home_geocode_status AS ENUM ('pending', 'geocoded', 'failed');
    END IF;
END $$;

ALTER TABLE fno_passed_homes ADD COLUMN IF NOT EXISTS gps_lat NUMERIC(10, 8);
ALTER TABLE fno_passed_homes ADD COLUMN IF NOT EXISTS gps_lng NUMERIC(11, 8);
ALTER TABLE fno_passed_homes ADD COLUMN IF NOT EXISTS geocode_status passed_home_geocode_status NOT NULL DEFAULT 'pending';
ALTER TABLE fno_passed_homes ADD COLUMN IF NOT EXISTS geocode_provider VARCHAR(50);
ALTER TABLE fno_passed_homes ADD COLUMN IF NOT EXISTS geocode_precision VARCHAR(20);
ALTER TABLE fno_passed_homes ADD COLUMN IF NOT EXISTS geocoded_at TIMESTAMP WITH TIME ZONE;

CREATE INDEX IF NOT EXISTS ix_fno_passed_home_geocode
    ON fno_passed_homes(tenant_id, status, geocode_status);
