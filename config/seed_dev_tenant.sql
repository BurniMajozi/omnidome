-- Dev-tenant seed for the OmniDome backend Postgres.
-- Idempotent. Creates the dev tenant, the test@omnidome.local backend users row
-- (login itself is via Supabase; this row maps email -> tenant for the backend),
-- and enables every module for the dev tenant so EntitlementGuard doesn't 403.
-- Runtime data, not part of master_schema.sql — re-run after a DB recreate.

INSERT INTO tenants (id, name, subdomain, tier, status, active)
VALUES ('00000000-0000-0000-0000-000000000001', 'Dev Tenant', 'dev', 'ENTERPRISE', 'ACTIVE', true)
ON CONFLICT (id) DO NOTHING;

-- Modules used by services (EntitlementGuard module_id) that master_schema.sql
-- never seeded — without these rows the guard 403s "Module not enabled".
INSERT INTO modules (key, name, description, is_core) VALUES
  ('agents', 'Agents', 'AI agent orchestrator', FALSE),
  ('communication', 'Communication', 'Team chat + communication hub', FALSE),
  ('compliance', 'Compliance', 'Compliance and audit', FALSE),
  ('customer_journey', 'Customer Journey', 'Journey orchestration', FALSE),
  ('journey_engine', 'Journey Engine', 'Journey execution engine', FALSE),
  ('lifecycle', 'Lifecycle', 'Customer lifecycle management', FALSE)
ON CONFLICT (key) DO NOTHING;

INSERT INTO users (id, tenant_id, email, full_name, role, hashed_password, is_active)
VALUES ('687fc528-cee6-4021-9e29-28344b3d6d0d',
        '00000000-0000-0000-0000-000000000001',
        'test@omnidome.local', 'Test User', 'ADMIN',
        'supabase-managed-no-local-login', true)
ON CONFLICT (id) DO NOTHING;

INSERT INTO tenant_modules (tenant_id, module_id, status, enabled_at)
SELECT '00000000-0000-0000-0000-000000000001'::uuid, id, 'ENABLED', now()
FROM modules
ON CONFLICT (tenant_id, module_id) DO UPDATE SET status = 'ENABLED', disabled_at = NULL;
