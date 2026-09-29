-- Migration: 20260929_lead_source_channel_and_funnel.sql
-- Description: Adds source_channel to leads table and backfills canonical sales channels

ALTER TABLE leads ADD COLUMN IF NOT EXISTS source_channel VARCHAR(50);
CREATE INDEX IF NOT EXISTS ix_leads_tenant_source_channel ON leads (tenant_id, source_channel);

UPDATE leads SET source_channel = CASE
    WHEN source ILIKE '%field%' OR source ILIKE '%door%' OR source ILIKE '%visit%' THEN 'FIELD_SALES'
    WHEN source ILIKE '%call%in%' OR source ILIKE '%inbound%call%' THEN 'CALL_CENTER_INBOUND'
    WHEN source ILIKE '%call%out%' OR source ILIKE '%outbound%call%' OR source ILIKE '%tele%' THEN 'CALL_CENTER_OUTBOUND'
    WHEN source ILIKE '%market%' OR source ILIKE '%campaign%' OR source ILIKE '%social%' OR source ILIKE '%ad%' THEN 'MARKETING'
    WHEN source ILIKE '%portal%' OR source ILIKE '%web%' OR source ILIKE '%site%' THEN 'PORTAL_WEBSITE'
    WHEN source ILIKE '%tender%' OR source ILIKE '%rfq%' THEN 'TENDER'
    WHEN source ILIKE '%company%' OR notes ILIKE '%company search%' THEN 'COMPANY_SEARCH'
    WHEN source ILIKE '%email%' OR source ILIKE '%mail%' THEN 'INBOUND_EMAIL'
    WHEN source ILIKE '%walk%' OR source ILIKE '%branch%' THEN 'WALK_IN'
    WHEN source ILIKE '%refer%' OR source ILIKE '%partner%' THEN 'REFERRAL'
    ELSE COALESCE(NULLIF(source, ''), 'OTHER')
END
WHERE source_channel IS NULL;
