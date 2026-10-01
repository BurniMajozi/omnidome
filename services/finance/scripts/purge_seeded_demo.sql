-- Purge the fabricated demo GL entries that the removed _ensure_sample_data() seeded.
--
--   psql -v tenant="'<tenant uuid>'" -f purge_seeded_demo.sql            (dry run: default)
--   psql -v tenant="'<tenant uuid>'" -v dry_run=0 -f purge_seeded_demo.sql   (soft-deletes)
--
-- Idempotent. Matches ONLY the six exact seeded entries (reference, description, source, date
-- 2026-04-01, and the exact line amounts) and ONLY while they are still UNPOSTED and not already
-- deleted. Posted entries are immutable: reverse those through the API instead (they are listed
-- by the final report query). Rows are soft-deleted (deleted_at), never physically removed.
\if :{?dry_run}
\else
\set dry_run 1
\endif

CREATE TEMP TABLE _seed_spec (ref text, descr text, src text, acct_d text, amt_d numeric, acct_c text, amt_c numeric);
INSERT INTO _seed_spec VALUES
 ('JE-2026-001','Monthly subscription revenue recognition','BILLING','1100',48000000,'4000',48000000),
 ('JE-2026-002','FNO access cost recognition','BILLING','5000',14000000,'2000',14000000),
 ('JE-2026-003','Salaries and wages','PAYROLL','6000',8000000,'1000',8000000),
 ('JE-2026-004','Depreciation - network infrastructure','ADJUSTMENT','6400',500000,'1600',500000),
 ('JE-2026-005','Interest expense on long-term debt','ADJUSTMENT','8000',150000,'1000',150000),
 ('JE-2026-006','Income tax provision','ADJUSTMENT','9000',2856000,'2600',2856000);

CREATE TEMP TABLE _seed_match AS
SELECT je.id, je.is_posted, je.reference
  FROM journal_entries je
  JOIN _seed_spec sp ON sp.ref = je.reference AND sp.descr = je.description AND sp.src = je.source
 WHERE je.tenant_id = :tenant::uuid
   AND je.entry_date = DATE '2026-04-01'
   AND je.source_id IS NULL
   AND je.deleted_at IS NULL
   AND (SELECT count(*) FROM journal_entry_lines l WHERE l.journal_entry_id = je.id) = 2
   AND EXISTS (SELECT 1 FROM journal_entry_lines l WHERE l.journal_entry_id = je.id
                AND l.account_code = sp.acct_d AND l.debit = sp.amt_d AND l.credit = 0)
   AND EXISTS (SELECT 1 FROM journal_entry_lines l WHERE l.journal_entry_id = je.id
                AND l.account_code = sp.acct_c AND l.credit = sp.amt_c AND l.debit = 0);

SELECT reference, CASE WHEN is_posted THEN 'POSTED (not purged, reverse via API)' ELSE 'unposted (purgeable)' END AS state
  FROM _seed_match ORDER BY reference;

\if :dry_run
\echo DRY RUN: nothing changed. Re-run with -v dry_run=0 to soft-delete the unposted matches.
\else
UPDATE journal_entries SET deleted_at = now()
 WHERE id IN (SELECT id FROM _seed_match WHERE NOT is_posted) AND is_posted = false AND deleted_at IS NULL;
\echo Soft-deleted the unposted seeded entries listed above.
\endif
