# Tasks: geo-segments

Plan: [plan.md](plan.md) · Spec: [SPEC-geo-segments.md](../SPEC-geo-segments.md)

Commands referenced below:
- `PYTEST` = `cd services/fno_intelligence && ../../.venv/Scripts/python.exe -m pytest tests/ -q`
- `TSC` = `cd apps/web && npx tsc --noEmit -p tsconfig.json`
- `LINT` = `cd apps/web && npm run lint`
- Service/web rebuild + migration: see the Commands section of the spec (run inside WSL, `~/omnidome` mirror, sync changed files first).

---

## Task 1: Pure logic module with unit tests

**Description:** Create `geo_segments.py` with the filter model and validation, the eligibility predicate, exclusion-reason classification, area grouping, centroid, haversine, `suggested_radius_km` (round up to 0.5 km, min 1.0) and CSV/KML rendering. No DB or network.

**Status: DONE** — 32 new tests, full suite 87 passed.

**Acceptance criteria:**
- [x] Eligibility: only `normalized` (+ `geocoded` with coordinates when `geocoded_only`); every other status maps to its exclusion reason.
- [x] Areas group by (suburb, city, postal code) with correct counts, centroid and radius (1.0 km floor, 0.5 km rounding, null centroid when no coordinates).
- [x] CSV has exactly the spec's columns and no address column; KML parses and skips centroid-less areas; invalid filters (date order, unknown dwelling type) raise.

**Verification:**
- [x] Tests pass: `PYTEST` (new `tests/test_geo_segments.py`, existing tests still green)

**Dependencies:** None

**Files likely touched:**
- `services/fno_intelligence/geo_segments.py`
- `services/fno_intelligence/tests/test_geo_segments.py`

**Estimated scope:** Small

---

## Task 2: `fno_geo_segments` model + migration

**Status: DONE** — migration applied twice (idempotent), unique constraint present, service boots healthy with the model.

**Description:** Add the `FNOGeoSegment` model (id, tenant_id, name, filters JSONB, home_count, area_count, excluded JSONB, areas JSONB, created_by, created_at, refreshed_at; unique `(tenant_id, name)`) and the matching migration SQL, applied to the dev DB.

**Acceptance criteria:**
- [x] Migration applies cleanly to `coreconnect` and is idempotent (`IF NOT EXISTS`).
- [x] Service boots with the new model (create_all doesn't conflict with the migration).
- [x] No existing passed-homes table or enum is altered.

**Verification:**
- [x] `\d fno_geo_segments` shows the columns and the unique constraint
- [x] Service `/health` 200 after rebuild

**Dependencies:** None

**Files likely touched:**
- `services/fno_intelligence/models.py`
- `config/migrations/20260924_fno_geo_segments.sql`

**Estimated scope:** Small

---

## Task 3: Preview + filter-options endpoints

**Status: DONE** — live-verified vs SQL on 4 filter combos + 422s + tenant isolation (scratchpad verify_task3.py). Web path resolves to the dev tenant, which has only 2 homes; review data handled before Checkpoint B.

**Description:** Add the shared filter → query compiler and `POST /geo-segments/preview` and `GET /geo-segments/filter-options`, tenant-scoped. Confirm which tenant the web path resolves to versus the imported data's tenant.

**Acceptance criteria:**
- [x] Preview `home_count` and each `excluded` reason equal direct SQL counts for at least 3 different filter combinations.
- [x] Filter-options lists only values that have eligible homes, with counts.
- [x] Invalid filters return `422`.

**Verification:**
- [x] Tests pass: `PYTEST`
- [x] Manual: curl both endpoints inside WSL; compare with `psql` counts

**Dependencies:** Task 1

**Files likely touched:**
- `services/fno_intelligence/routes.py`
- `services/fno_intelligence/geo_segments.py` (query compiler, if not in routes)

**Estimated scope:** Small

---

## Checkpoint A: Foundation
- [x] `PYTEST` green
- [x] Service rebuilt and healthy; migration applied
- [x] Preview matches SQL; tenant question from Task 3 answered
- [x] Review with human before UI work

---

## Task 4: Segment builder UI with live count; fake panels deleted

**Status: DONE** — tsc + lint clean (0 errors; the 4 icon imports orphaned by the deletion removed); browser check at Checkpoint B.

**Description:** Create `fno-api.ts` (typed client for filter-options and preview) and `sales-lead-sources.tsx` with a past-imports table and the segment builder (FNO, import, city, suburbs, postcode, dwelling type with friendly labels, passed from/to, geocoded-only). Live count debounced ~400 ms with per-reason exclusions and an area list. Mount it in the `ai-engine` tab and delete the simulation / output / prospect-generator panels plus their state and handlers.

**Acceptance criteria:**
- [x] Dropdowns populate from `filter-options`; count updates on change without a full-section spinner; loading, empty and error states shown.
- [x] `handleRunAiWarmingSimulation`, `handleGenerateAiProspects`, their state and JSX are gone; `grep "Nexus Logistics"` returns 0.
- [x] Pipeline, channels and leads tabs unaffected.

**Verification:**
- [x] `TSC` and `LINT` clean
- [x] Manual (at Checkpoint B): builder shows real counts on `http://127.0.0.1:3000`

**Dependencies:** Task 3

**Files likely touched:**
- `apps/web/lib/fno-api.ts`
- `apps/web/components/modules/sales-lead-sources.tsx`
- `apps/web/components/modules/sales-module.tsx`

**Estimated scope:** Medium

---

## Task 5: Save / list / detail / delete (API + UI)

**Status: DONE** — backend live-verified (12/12: 201, summary == preview, 409 after trim, blank 422, list order, detail, other-tenant 404 x2, survives restart, 204, 404 after delete; scratchpad verify_task5.py); tsc + lint clean; browser check at Checkpoint B.

**Description:** `POST /geo-segments`, `GET /geo-segments`, `GET /geo-segments/{id}`, `DELETE /geo-segments/{id}`; UI "Save segment" (name input) and a saved-segments list with home count, area count and refreshed time; detail shows areas.

**Acceptance criteria:**
- [x] Save persists the summary computed by the same query as preview; duplicate name → `409` shown inline; other tenant's id → `404`.
- [x] Saved segment survives a service restart and appears newest first.
- [x] Delete removes it from the list without a page reload.

**Verification:**
- [x] `PYTEST`, `TSC`, `LINT`
- [x] Manual: curl create → list → detail → delete; restart service and list again

**Dependencies:** Tasks 2, 4

**Files likely touched:**
- `services/fno_intelligence/routes.py`
- `apps/web/lib/fno-api.ts`
- `apps/web/components/modules/sales-lead-sources.tsx`

**Estimated scope:** Medium

---

## Task 6: Refresh + CSV/KML export (API + UI)

**Status: DONE** — backend live-verified 13/13 in a throwaway tenant (refresh picks up a new home, refreshed_at advances, CSV/KML headers + content, no address text, 422s, cleanup = 0 rows; scratchpad verify_task6.py); tsc + lint + pytest clean; browser check at Checkpoint B.

**Description:** `POST /geo-segments/{id}/refresh` and `GET /geo-segments/{id}/export?format=csv|kml` with attachment headers; UI Refresh and Export CSV / Export KML buttons per saved segment.

**Acceptance criteria:**
- [x] Refresh recomputes counts and `refreshed_at` after the underlying data changes.
- [x] CSV/KML downloads match the spec (columns, no addresses, placemark per centroid area); bad `format` → `422`.

**Verification:**
- [x] `PYTEST`, `TSC`, `LINT`
- [x] Manual: curl both formats; parse KML; open CSV

**Dependencies:** Task 5

**Files likely touched:**
- `services/fno_intelligence/routes.py`
- `apps/web/lib/fno-api.ts`
- `apps/web/components/modules/sales-lead-sources.tsx`

**Estimated scope:** Small

---

## Checkpoint B: End-to-end
- [x] `fno_intelligence` and `web` rebuilt (build logs grepped for failures)
- [x] Browser pass on `http://127.0.0.1:3000`: filters → live count → save → list → refresh → both exports → delete
- [x] Pipeline / leads tabs still work; no console errors
- [x] Review with human

- Notes: first browser pass exposed that the local web image baked every `/svc/*` rewrite as localhost (apps/web/.env.local leaking into the Docker build) — fixed in c9aa7a6d by excluding it in .dockerignore. Review data for the dev tenant loaded through the real import + geocode endpoints (8 geocoded homes; 1 customer, 2 duplicates, 1 invalid excluded). Date inputs clipped at narrow widths — stacked below xl.
---

## Task 7: 10k-home performance check

**Status: DONE** — measured 2026-09-24 with 10,000 synthetic homes (200 suburbs; 85% eligible, 10% duplicate, 3% invalid, 2% customers) in throwaway tenant `…00f7`, while the web image was building (CPU contended):
- preview, all 10k: worst **0.785 s**, best 0.280 s (5 runs after warm-up) → home_count 8,500 (exact), 170 areas
- save, all 10k: worst 0.503 s, best 0.303 s
- preview filtered to 50 suburbs: 0.085 s
- no index needed; synthetic rows removed (0 left). Script: scratchpad `perf_task7.py`.

**Description:** Insert ~10,000 synthetic passed homes into a separate throwaway tenant, time `preview` and `save` (5 runs, take the worst), add an index only if needed, then delete the synthetic rows.

**Acceptance criteria:**
- [x] Preview < 1 s at 10k homes (spec criterion 4), measured and recorded in this file.
- [x] Synthetic tenant rows fully removed afterwards (count = 0).

**Verification:**
- [x] Timing output recorded; `select count(*)` for the throwaway tenant = 0

**Dependencies:** Task 6

**Files likely touched:**
- `services/fno_intelligence/models.py` / a migration (only if an index is needed)

**Estimated scope:** Small

---

## Checkpoint: Complete
- [x] Spec success criteria 1–5 all met (1: preview == SQL on 4 filter combos; 2: survives restart; 3: CSV/KML columns + no addresses; 4: 0.785 s worst at 10k; 5: section live, fake panels deleted, tsc/lint/pytest clean)
- [x] Commits per task on `main` (local); push on user approval
- [ ] Memory updated with anything non-obvious learned
