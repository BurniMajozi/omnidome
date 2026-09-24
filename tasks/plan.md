# Implementation Plan: geo-segments

Spec: [SPEC-geo-segments.md](../SPEC-geo-segments.md) · Map: [CAPABILITY-MAP.md](../CAPABILITY-MAP.md)
Task list: [tasks/todo.md](todo.md)

## Overview

Add saved "geo segments" over FNO passed homes to `services/fno_intelligence`
(pure logic module + one table + eight endpoints under `/api/fno/geo-segments`)
and replace the three simulated panels in Sales → "AI Lead Warming &
Automations" with a real "FNO passed homes" section: past imports, a segment
builder with a live count, and saved segments with CSV/KML export.

## Architecture Decisions

- **Pure logic in `geo_segments.py`, thin routes.** Eligibility, area grouping,
  centroid/radius and CSV/KML rendering are plain functions tested without a
  DB, matching `suppression.py` / `geocoding.py` and their tests.
- **Filters are compiled to one SQLAlchemy query** used by preview, save and
  refresh, so the live count and the saved count can't drift apart.
- **Area aggregation in Python over a narrow column select** (suburb, city,
  postal code, lat, lng) rather than SQL `GROUP BY` + trig: the radius needs
  per-point distances to the centroid. Fine at 10k rows; Task 7 measures it.
- **Cached summary on the segment row** (`home_count`, `excluded`, `areas`
  JSONB, `refreshed_at`); manual refresh per the approved spec. No membership
  table.
- **Uniqueness** via a `(tenant_id, name)` unique constraint → `409`.
- **Web reaches the service via the existing `/svc/fno-intelligence/*`
  rewrite**; a new `apps/web/lib/fno-api.ts` client. The new UI is its own
  component (`sales-lead-sources.tsx`) so `sales-module.tsx` (1,900 lines)
  only loses code.
- **Backend verified per task with curl inside WSL; web rebuilt only at
  checkpoints** (each `web` rebuild is ~5 min on this machine).

## Dependency graph

```
geo_segments.py (logic + tests) ──┐
FNOGeoSegment model + migration ──┼── preview / filter-options endpoints ── fno-api.ts + builder UI
                                  └── save / list / detail / delete ── refresh / export ── perf check
```

## Task List

### Phase 1: Foundation
- [x] Task 1: Pure logic module with unit tests
- [x] Task 2: `fno_geo_segments` model + migration
- [x] Task 3: Preview + filter-options endpoints (live-verified against SQL)

### Checkpoint A: Foundation
- [x] pytest green; service rebuilt; preview count matches direct SQL count

### Phase 2: Core flow
- [x] Task 4: Segment builder UI with live count; fake panels deleted
- [x] Task 5: Save / list / detail / delete (API + UI)
- [x] Task 6: Refresh + CSV/KML export (API + UI)

### Checkpoint B: End-to-end
- [ ] web + service rebuilt; full browser pass on `http://127.0.0.1:3000`

### Phase 3: Hardening
- [x] Task 7: 10k-home performance check (throwaway tenant, cleaned up)

### Checkpoint: Complete
- [ ] All five spec success criteria met; ready for review

## Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Only 11 eligible / 8 geocoded homes in the dev DB | Med — weak live coverage of areas and radius | Unit tests cover the maths; live checks compare against SQL; Task 7 adds synthetic volume in a separate tenant |
| WSL/Docker instability during rebuilds | Med | Keep-alive running; one container rebuilt at a time; grep build logs for failure markers |
| Tenant mismatch between web requests and the imported data | Med — empty builder | Task 3 confirms which tenant the web path resolves to vs the data's `tenant_id` before UI work |
| `sales-module.tsx` is large; deleting handlers may break shared state | Low | Delete only the simulation/prospect state + handlers; `tsc` must pass; pipeline/leads tabs smoke-tested at Checkpoint B |
| Web rebuild time | Low | Batch web verification at checkpoints, not per task |

## Decisions (answered 2026-09-24, plan approved)

1. The "Architecture explainer" card and the three "Active automation rules"
   cards **stay** for now; Task 4 removes only the simulation, output and
   prospect-generator panels.
2. Task 7 may insert ~10,000 synthetic passed homes into a separate throwaway
   tenant, then must delete them.
3. Commit per task locally; push only when the user says so.
