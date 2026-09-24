# Tasks: import flow → opportunity-finder → marketing-audiences

Plan: [plan.md](plan.md). geo-segments v1 tasks (1–7) are complete; see git history.

Commands:
- `PYTEST` = `cd services/fno_intelligence && ../../.venv/Scripts/python.exe -m pytest tests/ -q`
- `TSC` = `cd apps/web && npx tsc --noEmit -p tsconfig.json`
- `LINT` = `cd apps/web && npx eslint <changed files>` (0 errors, no new warnings)
- Rebuild fno: `~/rebuild_fno.sh` in WSL (syncs `services/fno_intelligence` + migrations, grep-checks the build log)
- Rebuild web: sync changed web files into `~/omnidome`, `~/rebuild_web_getsession_fix.sh`, `docker compose up -d --no-deps web`
- Verify in the browser at `http://localhost:3000` (dev tenant `…0001`)

---

## A1: Backend — `address_raw` in passed-homes list + stuck-import sweep
**Status: DONE** — 5 new tests (97 total); live: 5 stuck imports swept to failed with the message (second worker found none), 0 left; `address_raw` returned.
**Acceptance:**
- [x] `GET /passed-homes` rows include `address_raw`.
- [x] Imports in `uploaded`/`parsing` older than 30 min become `failed` with the spec's message on service start; newer ones untouched (unit-tested cutoff).
**Verify:** PYTEST; live: the old stuck `passed_homes.csv` import shows Failed after restart.
**Files:** `services/fno_intelligence/routes.py`, `services/fno_intelligence/passed_homes.py`, `main.py`, tests. **Scope:** S

## A2: Import panel, progress, auto-geocode, statuses, view issues, template
**Status: DONE** — browser: validation (no file / wrong type), real CSV → Processing… → Placing on map 0/3 → Imported (4 rows: 3 new, 1 invalid), live count 8→11, new suburb chips, details show column mapping + rejected row. Commit 7325c5c2.
**Acceptance:**
- [x] "Import FNO file" opens an inline panel above the imports table (FNO select incl. Other + name; drop zone; recognised columns; Download template).
- [x] Wrong type / > 25 MB / missing FNO rejected inline before upload.
- [x] New import appears at the top immediately, polls to a terminal status, then geocodes with "Placing on map n/N"; builder data reloads after.
- [x] Status labels per spec; failed shows error; View issues lists invalid rows with reasons; column mapping visible.
**Verify:** TSC, LINT; browser at Checkpoint A.
**Files:** `apps/web/lib/fno-api.ts`, `apps/web/components/modules/sales-lead-sources.tsx` (+ a new `passed-home-import-panel.tsx`). **Scope:** M

### Checkpoint A
- [x] fno + web rebuilt (logs grepped)
- [x] CSV imported through the UI end-to-end (drop → imported → geocoded → count updates)
- [x] API upload path still works (curl multipart)

---

## B1: `opportunities.py` pure logic + tests
**Status: DONE** — 44 new tests (141 total).
**Acceptance:**
- [x] Categories → Overpass query (around centre, radius m, named features, `out center tags`).
- [x] Overpass elements → companies (address from `addr:*`, contact from plain/`contact:*`, distance, dedupe, sort, cap 300).
- [x] Source URL validation (http/https, no localhost/private IPs, normalised).
- [x] LLM tender JSON parsing (code fences / surrounding text tolerated), SA date parsing, dedupe key.
**Verify:** PYTEST. **Files:** `opportunities.py`, `tests/test_opportunities.py`. **Scope:** M

## B2: Models + migration (5 tables)
**Status: DONE** — migration applied twice; 5 tables + 3 unique constraints; service boots (verified on every rebuild since).
**Acceptance:**
- [x] `opp_company_searches`, `opp_companies`, `opp_sources`, `opp_snapshots`, `opp_tenders` with the spec's unique constraints; migration idempotent; service boots.
**Verify:** migration applied twice; `\d`; `/health`. **Files:** `models.py`, `config/migrations/20260924_opportunity_finder.sql`. **Scope:** S

## B3: Company search API
**Status: DONE** — live: Rosebank resolved correctly (Nominatim place preference), 15 real businesses in 13 s, 422s, isolation; enrich found website/phone/email via Firecrawl structured extraction (OpenRouter key expired — noted in spec); timeouts return 503, never 500. Commit 13891185.
**Acceptance:**
- [x] categories, create (422 unknown area), list, detail, enrich, patch endpoints per spec; search runs in background with Overpass fallbacks.
- [x] Live: a real SA area returns named businesses with distance; enrich fills contact data for a business with a website; tenant isolation.
**Verify:** PYTEST; live script. **Files:** `opportunity_routes.py`, `main.py`. **Scope:** M

## B4: Tender sources / scan / tenders / screenshot API + scheduler
**Status: DONE** — live 21/21: SITA ~94 tenders/scan with parsed closing times, screenshot served, rescan no duplicate references, user status kept, double scan-now = one scan, scheduler = one scan across both workers, eTenders scanned (relative dates). Commit 13891185.
**Acceptance:**
- [x] sources CRUD (409 dup, 422 bad URL), scan-now, tenders list/patch, screenshot endpoint.
- [x] Live: a real public tender page yields tenders with title + closing date and a stored screenshot; rescan does not duplicate and keeps user status.
- [x] Scheduler + advisory lock: due sources scanned once across both workers.
**Verify:** PYTEST; live script. **Files:** `opportunity_routes.py`, `opportunities.py`, `main.py`. **Scope:** M–L

## B5: UI — segmented control + Companies view
**Status: DONE** — browser: Sea Point hospitality 1 km → 92 businesses (Nominatim fallback while Overpass returned 504), failed state + Try again shown earlier, Find contacts found The Glen's phone, Add as lead → real Sales lead (COMPANY_SEARCH), dismiss/show dismissed/restore. Form columns align over the results table.
**Acceptance:**
- [x] Homes passed / Companies / Tenders & RFQs switcher; existing homes-passed content unchanged under it.
- [x] Search form row aligned above results table; job progress; results with Find contacts / Add as lead / Dismiss; recent searches; OSM attribution.
- [x] Add as lead creates a real Sales lead (source `COMPANY_SEARCH`) and marks the company.
**Verify:** TSC, LINT; browser at Checkpoint B. **Files:** `fno-api.ts`, `sales-lead-sources.tsx`, new `opportunity-companies.tsx`, `sales-api.ts` (channels). **Scope:** M

## B6: UI — Tenders & RFQs view
**Status: DONE** — browser: 2 sources (SITA 97, eTenders 10), 25 open tenders soonest-closing first, countdown '22h left' red, expand row, evidence screenshot 1920x1385, status → Bidding saved, Add to pipeline → real Sales lead (TENDER). Found + fixed: source name lost after a status edit.
**Acceptance:**
- [x] Source form row aligned above the sources table; Scan now / Pause / Delete; scan status.
- [x] Tenders table with closing countdown, briefing, documents list, screenshot evidence, status select, Add to pipeline (Sales lead source `TENDER`); status filter + show closed.
**Verify:** TSC, LINT; browser at Checkpoint B. **Files:** `fno-api.ts`, new `opportunity-tenders.tsx`. **Scope:** M

### Checkpoint B
- [x] fno + web rebuilt; real area search and real tender URL work in the browser; leads created

---

## C1: Marketing API — fix jsonb bug, upsert, detail, delete, type filter
**Status: DONE** — bug reproduced (500 syntax error) then fixed; create/upsert/type filter/detail/delete/validation pass live; isolation = 403 entitlement guard + tenant-filtered SQL (404 path not exercisable: only dev tenant has marketing). Commit 3a92bca0.
**Acceptance:**
- [x] Bug reproduced (POST /segments fails) then fixed.
- [x] Upsert on same `source` + `source_id`; `GET /segments?type=`, `GET /segments/{id}`, `DELETE`; validation; tenant isolation.
**Verify:** live script before/after. **Files:** `services/marketing/main.py`. **Scope:** S

## C2: Sales — "Add to audience"
**Status: DONE** — browser: saved segment → 'In Marketing · Google Ads'; company search → 'In Marketing · Meta' (92 businesses).
**Acceptance:**
- [x] Saved geo segment row → platform + name → homes audience (areas only); row shows "In Marketing".
- [x] Company search → business audience with non-dismissed businesses.
**Verify:** TSC, LINT; browser at Complete. **Files:** new `apps/web/lib/audiences-api.ts` (or marketing-api additions), `sales-lead-sources.tsx`, `opportunity-companies.tsx`. **Scope:** S–M

## C3: Marketing → Audiences real
**Status: DONE** — browser: fake cards gone; real cards (2 homes / Google Ads, 92 businesses / Meta); homes detail + areas-only note; CSV export (brackenfell-review.csv, spec columns); businesses detail 92 rows; New Audience validation + custom save. Delete exposed a proxy bug (204 → 502) fixed in 9b1fef89 across 10 proxies; re-verified after final rebuild.
**Acceptance:**
- [x] Hard-coded audience fixtures removed; cards from API with type/platform/count/source/updated; empty state.
- [x] Detail with areas or businesses, Export CSV, Delete.
- [x] New Audience modal aligned (type, source picker, platform, description; custom regions) creating real records.
**Verify:** TSC, LINT; browser. **Files:** `apps/web/components/modules/marketing-module.tsx` (+ new `marketing-audiences.tsx`). **Scope:** M

### Checkpoint: Complete
- [x] All tasks above ticked with evidence; every success criterion in the three specs verified
- [x] Final rebuild of fno, marketing and web; full browser pass; pushed

Verification summary (2026-09-24): pytest 163 passed; tsc + eslint clean on all changed web files; every
success criterion in SPEC-geo-segments (v2 6–9), SPEC-opportunity-finder (1–6) and SPEC-marketing-audiences
(1–4) verified live in the browser or against the running services. Final re-check after the last rebuild:
audience delete 204 via proxy, tender lead named after its source after a status edit, recent searches
de-duplicated, no ward names as suburbs, >25 MB and "Other FNO" validation, New Audience for homes (upsert)
and businesses. Known external limit: the OpenRouter key has expired (Firecrawl extraction used instead).
