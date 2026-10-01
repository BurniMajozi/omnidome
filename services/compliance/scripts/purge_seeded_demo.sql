-- Purge the fabricated rows written by the removed `seed_demo_compliance_data` (cross_service.py)
-- and by the removed fake-filing / fake-FICA endpoints.
--
-- DO NOT run blindly: review the SELECT previews first (set :dry_run to 1 for counts only).
-- Idempotent: every statement matches exact seeded signatures, so re-running deletes nothing more.
-- Tenant parameterised and tenant-scoped on every statement; rows created before 2026-09-25 are never touched.
--
--   Preview:  psql "$DATABASE_URL" -v tenant=00000000-0000-0000-0000-000000000001 -v dry_run=1 -f purge_seeded_demo.sql
--   Purge:    psql "$DATABASE_URL" -v tenant=00000000-0000-0000-0000-000000000001 -v dry_run=0 -f purge_seeded_demo.sql
--
-- Real compliance scores could never have been stored before the fix (the insert omitted tenant_id, a NOT NULL
-- column), which is why exact seeded score tuples are safe to match.

\if :{?tenant}
\else
  \echo 'ERROR: pass -v tenant=<tenant uuid>'
  \quit
\endif
\if :{?dry_run}
\else
  \set dry_run 1
\endif

\echo 'Tenant:' :tenant ' dry_run:' :dry_run

BEGIN;

-- ── Previews (always printed) ────────────────────────────────────────────
WITH seeded_contracts(num, title, party, val) AS (VALUES
  ('CTR-2026-001', 'MetroFibre FNO Master SLA', 'MetroFibre Networx', 4800000.00),
  ('CTR-2026-002', 'Openserve Dark Fibre Backhaul Interconnect', 'Openserve (Telkom SA)', 9200000.00),
  ('CTR-2026-003', 'Vumatel NNI Master Services Agreement', 'Vumatel (Pty) Ltd', 6500000.00),
  ('CTR-2026-004', 'MTN Business Transit & Peering SLA', 'MTN South Africa', 3600000.00),
  ('CTR-2026-005', 'Commercial Guarding Enterprise Fiber SLA', 'ADT Fidelity Security', 1250000.00))
SELECT 'contracts to delete' AS what, count(*) AS n
FROM compliance_contracts c JOIN seeded_contracts s
  ON c.contract_number = s.num AND c.title = s.title AND c.counterparty_name = s.party AND c.value_zar = s.val
WHERE c.tenant_id = :'tenant' AND c.created_at >= TIMESTAMP '2026-09-25 00:00:00';

-- ── 1. Compliance scores (8 seeded tuples) ───────────────────────────────
WITH seeded(cat, score, st, issues, crit) AS (VALUES
  ('contract', 94.0, 'compliant', 1, 0), ('health_safety', 98.0, 'compliant', 0, 0),
  ('tax', 96.0, 'compliant', 0, 0),      ('bbbee', 92.0, 'compliant', 0, 0),
  ('popi', 95.0, 'compliant', 1, 0),     ('rica', 98.0, 'compliant', 0, 0),
  ('icasa', 93.0, 'compliant', 0, 0),    ('cipc', 100.0, 'compliant', 0, 0))
DELETE FROM compliance_scores cs
USING seeded s
WHERE :dry_run = 0
  AND cs.tenant_id = :'tenant'
  AND cs.calculated_at >= TIMESTAMP '2026-09-25 00:00:00'
  AND cs.category::text = s.cat AND cs.score = s.score AND cs.status::text = s.st
  AND coalesce(cs.issues_count, 0) = s.issues AND coalesce(cs.critical_issues, 0) = s.crit;

-- ── 2. Vehicle registrations (4) ─────────────────────────────────────────
WITH seeded(reg, vtype, make, model, driver) AS (VALUES
  ('CA 124-892', 'Light Delivery Vehicle', 'Toyota', 'Hilux 2.4 GD-6 Splicing Van', 'Musa Sithole'),
  ('GP 882-901', 'Installation Van', 'Nissan', 'NP200 ONT Drop Cable Unit', 'David Botha'),
  ('ND 441-209', 'Trench Ops Bakkie', 'Ford', 'Ranger 2.2 TDCi Civil Works', 'Sipho Khumalo'),
  ('CA 908-112', 'NOC Field Response', 'Volkswagen', 'Caddy Maxi 2.0 TDI', 'Tanya Jacobs'))
DELETE FROM compliance_vehicle_registrations v
USING seeded s
WHERE :dry_run = 0
  AND v.tenant_id = :'tenant'
  AND v.created_at >= TIMESTAMP '2026-09-25 00:00:00'
  AND v.registration_number = s.reg AND v.vehicle_type = s.vtype AND v.make = s.make
  AND v.model = s.model AND v.assigned_driver = s.driver;

-- ── 3. POPIA DSARs (3 seeded subjects) ───────────────────────────────────
WITH seeded(ref, rtype, name, email) AS (VALUES
  ('DSAR-001', 'access', 'Hendrik van der Merwe', 'hendrik.vdm@outlook.com'),
  ('DSAR-002', 'deletion', 'Fatima Patel', 'fatima.patel@gmail.com'),
  ('DSAR-003', 'objection', 'Thabo Molefe', 'thabo.molefe@icloud.com'))
DELETE FROM compliance_popi_dsar d
USING seeded s
WHERE :dry_run = 0
  AND d.tenant_id = :'tenant'
  AND d.created_at >= TIMESTAMP '2026-09-25 00:00:00'
  AND d.request_reference = s.ref AND d.request_type = s.rtype
  AND d.data_subject_name = s.name AND d.data_subject_email = s.email
  AND d.description = 'Customer requested personal data review under Section 23 POPIA';

-- ── 4. Tax returns: the 2 seeded 'paid' rows + the fabricated EMP201 "filings" ──
DELETE FROM compliance_tax_returns t
WHERE :dry_run = 0
  AND t.tenant_id = :'tenant'
  AND t.created_at >= TIMESTAMP '2026-09-25 00:00:00'
  AND t.status::text = 'paid'
  AND (
        -- seeder rows: no SARS reference at all
        (t.tax_type::text = 'vat'  AND t.amount_payable = 142500.00 AND t.sars_reference IS NULL AND t.filing_reference IS NULL)
     OR (t.tax_type::text = 'paye' AND t.amount_payable = 89400.00  AND t.sars_reference IS NULL AND t.filing_reference IS NULL)
        -- removed emp201/file endpoint: invented PRN suffix + invented receipt prefix
     OR (t.tax_type::text = 'paye' AND t.sars_reference LIKE 'PRN-%-9827361524' AND t.filing_reference LIKE 'SARS-REC-%')
  );

-- ── 5. Fabricated "FICA clearance" documents (removed endpoint; claimed AML/CIPC checks that never ran) ──
DELETE FROM compliance_documents d
WHERE :dry_run = 0
  AND d.tenant_id = :'tenant'
  AND d.created_at >= TIMESTAMP '2026-09-25 00:00:00'
  AND d.tags = 'fica,vetting'
  AND d.file_path LIKE '/compliance/fica/FICA-%.json'
  AND d.title LIKE 'FICA Clearance: %';

-- ── 6. Seeded contracts last (skipped when anything references them) ─────
WITH seeded(num, title, party, val) AS (VALUES
  ('CTR-2026-001', 'MetroFibre FNO Master SLA', 'MetroFibre Networx', 4800000.00),
  ('CTR-2026-002', 'Openserve Dark Fibre Backhaul Interconnect', 'Openserve (Telkom SA)', 9200000.00),
  ('CTR-2026-003', 'Vumatel NNI Master Services Agreement', 'Vumatel (Pty) Ltd', 6500000.00),
  ('CTR-2026-004', 'MTN Business Transit & Peering SLA', 'MTN South Africa', 3600000.00),
  ('CTR-2026-005', 'Commercial Guarding Enterprise Fiber SLA', 'ADT Fidelity Security', 1250000.00))
DELETE FROM compliance_contracts c
USING seeded s
WHERE :dry_run = 0
  AND c.tenant_id = :'tenant'
  AND c.created_at >= TIMESTAMP '2026-09-25 00:00:00'
  AND c.contract_number = s.num AND c.title = s.title AND c.counterparty_name = s.party AND c.value_zar = s.val
  AND NOT EXISTS (SELECT 1 FROM compliance_contract_slas x WHERE x.contract_id = c.id)
  AND NOT EXISTS (SELECT 1 FROM compliance_documents x WHERE x.contract_id = c.id)
  AND NOT EXISTS (SELECT 1 FROM compliance_contract_audit_logs x WHERE x.contract_id = c.id)
  AND NOT EXISTS (SELECT 1 FROM compliance_popi_dsar x WHERE x.contract_id = c.id)
  AND NOT EXISTS (SELECT 1 FROM compliance_icasa_submissions x WHERE x.contract_id = c.id)
  AND NOT EXISTS (SELECT 1 FROM compliance_contracts x WHERE x.parent_contract_id = c.id);

-- NOT purged (manual review): the single H&S incident created on 2026-09-25 came from the incident-log endpoint
-- (INC-xxxxxx, status 'investigating', description prefixed "[<employee>]"). It is a test entry, not seeder data:
--   SELECT id, incident_number, description FROM compliance_hs_incidents
--   WHERE tenant_id = :'tenant' AND incident_number LIKE 'INC-%' AND created_at >= TIMESTAMP '2026-09-25';

\if :dry_run
  \echo 'dry_run=1: rolling back (nothing was deleted)'
  ROLLBACK;
\else
  COMMIT;
\endif
