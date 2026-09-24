-- Migration: fno_geo_segments (geo-segments module, SPEC-geo-segments.md)
--
-- A saved filter over fno_passed_homes plus its cached area summary.
-- New table only: no existing passed-homes table or enum is altered.
-- services/fno_intelligence's create_all() would also create this table on
-- boot; this file exists so the DDL is explicit and can be applied to any DB
-- ahead of a service deploy. Idempotent.

CREATE TABLE IF NOT EXISTS fno_geo_segments (
    id            UUID PRIMARY KEY,
    tenant_id     UUID NOT NULL,
    name          VARCHAR(120) NOT NULL,
    filters       JSONB NOT NULL DEFAULT '{}'::jsonb,
    home_count    INTEGER NOT NULL DEFAULT 0,
    area_count    INTEGER NOT NULL DEFAULT 0,
    excluded      JSONB NOT NULL DEFAULT '{}'::jsonb,
    areas         JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_by    UUID,
    created_at    TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    refreshed_at  TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    CONSTRAINT uq_fno_geo_segment_tenant_name UNIQUE (tenant_id, name)
);

CREATE INDEX IF NOT EXISTS ix_fno_geo_segments_tenant_id ON fno_geo_segments(tenant_id);
