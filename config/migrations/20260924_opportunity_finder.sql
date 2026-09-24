-- Migration: opportunity-finder tables (SPEC-opportunity-finder.md)
--
-- Company search (OpenStreetMap) + tender/RFQ sources, snapshots and tenders
-- for services/fno_intelligence. New tables only; nothing existing is
-- altered. Statuses are VARCHAR (validated by the service), not enums.
-- create_all() would also create these on boot; this file makes the DDL
-- explicit for any DB set up ahead of a deploy. Idempotent.

CREATE TABLE IF NOT EXISTS opp_company_searches (
    id            UUID PRIMARY KEY,
    tenant_id     UUID NOT NULL,
    area_query    VARCHAR(200) NOT NULL,
    area_label    TEXT,
    category      VARCHAR(40) NOT NULL,
    radius_km     INTEGER NOT NULL,
    center_lat    DOUBLE PRECISION NOT NULL,
    center_lng    DOUBLE PRECISION NOT NULL,
    status        VARCHAR(20) NOT NULL DEFAULT 'queued',
    error_message TEXT,
    result_count  INTEGER NOT NULL DEFAULT 0,
    created_by    UUID,
    created_at    TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    finished_at   TIMESTAMP WITH TIME ZONE
);
CREATE INDEX IF NOT EXISTS ix_opp_company_searches_tenant_id ON opp_company_searches(tenant_id);

CREATE TABLE IF NOT EXISTS opp_companies (
    id             UUID PRIMARY KEY,
    tenant_id      UUID NOT NULL,
    search_id      UUID NOT NULL REFERENCES opp_company_searches(id) ON DELETE CASCADE,
    osm_type       VARCHAR(10) NOT NULL,
    osm_id         BIGINT NOT NULL,
    name           VARCHAR(300) NOT NULL,
    category_label VARCHAR(120),
    address_line   VARCHAR(300),
    suburb         VARCHAR(200),
    city           VARCHAR(200),
    postal_code    VARCHAR(20),
    phone          VARCHAR(80),
    email          VARCHAR(200),
    website        VARCHAR(500),
    lat            DOUBLE PRECISION NOT NULL,
    lng            DOUBLE PRECISION NOT NULL,
    distance_km    DOUBLE PRECISION NOT NULL DEFAULT 0,
    status         VARCHAR(20) NOT NULL DEFAULT 'new',
    sales_lead_id  UUID,
    enriched_at    TIMESTAMP WITH TIME ZONE,
    enrichment     JSONB,
    created_at     TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    CONSTRAINT uq_opp_company_osm UNIQUE (tenant_id, search_id, osm_type, osm_id)
);
CREATE INDEX IF NOT EXISTS ix_opp_companies_tenant_id ON opp_companies(tenant_id);
CREATE INDEX IF NOT EXISTS ix_opp_companies_search_id ON opp_companies(search_id);

CREATE TABLE IF NOT EXISTS opp_sources (
    id                  UUID PRIMARY KEY,
    tenant_id           UUID NOT NULL,
    url                 TEXT NOT NULL,
    label               VARCHAR(200),
    kind                VARCHAR(20) NOT NULL DEFAULT 'tenders',
    active              BOOLEAN NOT NULL DEFAULT true,
    scan_interval_hours INTEGER NOT NULL DEFAULT 24,
    last_scanned_at     TIMESTAMP WITH TIME ZONE,
    next_scan_at        TIMESTAMP WITH TIME ZONE,
    last_status         VARCHAR(20) NOT NULL DEFAULT 'queued',
    last_error          TEXT,
    last_tender_count   INTEGER NOT NULL DEFAULT 0,
    created_at          TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    CONSTRAINT uq_opp_source_tenant_url UNIQUE (tenant_id, url)
);
CREATE INDEX IF NOT EXISTS ix_opp_sources_tenant_id ON opp_sources(tenant_id);

CREATE TABLE IF NOT EXISTS opp_snapshots (
    id              UUID PRIMARY KEY,
    tenant_id       UUID NOT NULL,
    source_id       UUID NOT NULL REFERENCES opp_sources(id) ON DELETE CASCADE,
    url             TEXT NOT NULL,
    fetched_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    content_hash    VARCHAR(64) NOT NULL,
    markdown        TEXT,
    screenshot      BYTEA,
    screenshot_mime VARCHAR(40),
    tender_count    INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_opp_snapshots_tenant_id ON opp_snapshots(tenant_id);
CREATE INDEX IF NOT EXISTS ix_opp_snapshots_source_id ON opp_snapshots(source_id);

CREATE TABLE IF NOT EXISTS opp_tenders (
    id                 UUID PRIMARY KEY,
    tenant_id          UUID NOT NULL,
    source_id          UUID NOT NULL REFERENCES opp_sources(id) ON DELETE CASCADE,
    snapshot_id        UUID REFERENCES opp_snapshots(id) ON DELETE SET NULL,
    dedupe_key         VARCHAR(500) NOT NULL,
    title              TEXT NOT NULL,
    reference          VARCHAR(200),
    issuer             VARCHAR(300),
    description        TEXT,
    closing_at         TIMESTAMP WITH TIME ZONE,
    closing_text       VARCHAR(200),
    briefing_at        TIMESTAMP WITH TIME ZONE,
    briefing_text      VARCHAR(300),
    briefing_location  TEXT,
    required_documents JSONB NOT NULL DEFAULT '[]'::jsonb,
    document_links     JSONB NOT NULL DEFAULT '[]'::jsonb,
    detail_url         TEXT,
    contact            TEXT,
    status             VARCHAR(20) NOT NULL DEFAULT 'new',
    sales_lead_id      UUID,
    detail_scanned     BOOLEAN NOT NULL DEFAULT false,
    first_seen_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    last_seen_at       TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    updated_at         TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    CONSTRAINT uq_opp_tender_dedupe UNIQUE (tenant_id, source_id, dedupe_key)
);
CREATE INDEX IF NOT EXISTS ix_opp_tenders_tenant_id ON opp_tenders(tenant_id);
CREATE INDEX IF NOT EXISTS ix_opp_tenders_source_id ON opp_tenders(source_id);
CREATE INDEX IF NOT EXISTS ix_opp_tender_closing ON opp_tenders(tenant_id, closing_at);
