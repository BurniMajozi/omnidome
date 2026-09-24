# Spec: geo-segments

Module 1 of [CAPABILITY-MAP.md](CAPABILITY-MAP.md). Status: approved 2026-09-24; implemented (see tasks/todo.md).

## Objective

Turn an imported FNO "homes passed" list into a named, reusable **geo
segment**: the set of eligible homes matching a filter, summarised as target
areas. Downstream modules consume it: `marketing-audiences` (location-based
ads) and `field-territories` (door-to-door walk lists).

Passed-home data is **addresses only** — there is no person attached. A segment
therefore describes *places*, never people.

Users: the sales/marketing manager on the Sales → Lead sources tab.

User stories:
- As a sales manager, I pick an FNO, suburbs, a "passed since" date and dwelling
  types and immediately see how many homes match and how many were excluded
  (existing customers, duplicates, invalid, not yet geocoded).
- I save that filter as a named segment and see it in a list with its home count
  and areas.
- I export a segment's target areas as CSV or KML to use in any ad platform.
- The fake simulation panels on this tab are gone; everything shown is real data.

## Scope

In:
- New table `fno_geo_segments` (+ migration SQL).
- Pure-logic module `services/fno_intelligence/geo_segments.py`: eligibility
  rule, area summarisation (centroid, suggested radius), CSV/KML rendering.
- Endpoints under `/api/fno` (see Contract).
- Sales tab UI slice: "FNO passed homes" section (imports table, segment
  builder with live count, saved segments with export). Removes the
  "Simulate Digital Event & AI Warming", "AI Lead Warming Output" and
  "AI Lead Prospecting Generator" panels and their handlers.

Out (other modules):
- "Add to campaign audience" button and the Marketing Audiences tab →
  `marketing-audiences`.
- "Send to field sales", walk lists, per-address output → `field-territories`.
- Pushing to Google Ads / Meta.

## Rules

- **Eligible home** = `status == "normalized"`. Rows with status `raw`,
  `duplicate`, `invalid` or `suppressed_customer` never enter a segment.
- `geocoded_only` filter (default **true**): additionally requires
  `geocode_status == "geocoded"` with non-null coordinates. Exclusions are counted
  per reason so the UI can explain the gap.
- **Area** = group of eligible homes by (`suburb`, `city`, `postal_code`).
  For each area: `homes`, centroid (mean lat/lng of geocoded homes, null if
  none), `suggested_radius_km` = max haversine distance from centroid to a
  member, rounded **up** to 0.5 km, minimum **1.0 km** (the practical minimum
  radius ad platforms accept).
- A segment stores its **filters** plus a **cached summary** computed at save
  time. `POST /geo-segments/{id}/refresh` recomputes it (e.g. after a new
  import). No per-home membership table (walk-list snapshots are
  `field-territories`' job).
- Exports contain areas only: **no `address_line1`, no per-home rows.**

## Contract (prefix `/api/fno`, tenant-scoped via `get_current_tenant_id`)

Filters object (all optional, AND-combined; list fields are OR within the list):

```json
{
  "fno_names": ["Vumatel"],
  "import_ids": ["uuid"],
  "cities": ["Johannesburg"],
  "suburbs": ["Rosebank", "Parkhurst"],
  "postal_codes": ["2196"],
  "dwelling_types": ["sdu", "estate"],
  "date_passed_from": "2026-08-01",
  "date_passed_to": null,
  "geocoded_only": true
}
```

| Method + path | Purpose | Response |
|---|---|---|
| `GET /geo-segments/filter-options` | Populate filter dropdowns | `{fno_names[], cities[], suburbs[{suburb, city, homes}], dwelling_types[], imports[{id, file_name, fno_name, created_at}]}` — counts are eligible homes only |
| `POST /geo-segments/preview` | Live count, no write | `{home_count, excluded: {suppressed_customer, duplicate, invalid, raw, not_geocoded}, areas: [Area]}` (`raw` = imported but not yet normalized) |
| `POST /geo-segments` | Save `{name, filters}` | `201` Segment |
| `GET /geo-segments` | List, newest first | `[Segment]` (without `areas`) |
| `GET /geo-segments/{id}` | Detail | Segment with `areas` |
| `POST /geo-segments/{id}/refresh` | Recompute cached summary | Segment |
| `DELETE /geo-segments/{id}` | Remove | `204` |
| `GET /geo-segments/{id}/export?format=csv\|kml` | Download areas | `text/csv` or `application/vnd.google-earth.kml+xml`, `Content-Disposition: attachment` |

`dwelling_types` values are the existing `passed_home_dwelling` enum:
`sdu` (single dwelling unit), `mdu_unit`, `complex`, `business`, `estate`,
`unknown`. The UI shows friendly labels (e.g. "Freestanding house" for `sdu`).

`Area = {suburb, city, postal_code, homes, centroid_lat, centroid_lng, suggested_radius_km}`

`Segment = {id, name, filters, home_count, area_count, excluded, areas?, created_at, refreshed_at}`

Validation: `name` 1–120 chars, unique per tenant (`409` on clash); unknown
`dwelling_types` → `422`; `date_passed_from > date_passed_to` → `422`;
segment of another tenant → `404`. `format` other than csv/kml → `422`.

CSV columns: `suburb,city,postal_code,homes,centroid_lat,centroid_lng,suggested_radius_km`.
KML: one `Placemark` per area with a centroid `Point`, name = suburb, description = homes + radius; areas without a centroid are omitted from KML (still in CSV).

## Tech Stack

- Backend: FastAPI + SQLAlchemy 2 async (existing `fno_intelligence`, Python 3.11), PostgreSQL.
- Frontend: Next.js 16 / React 19, existing `apps/web` components (`Card`, `Button`, `Badge`, Tailwind), reached via the `/svc/fno-intelligence/*` rewrite in `next.config.mjs`.
- No new dependencies (KML/CSV rendered with the standard library).

## Commands

```
Backend tests:   cd services/fno_intelligence && ../../.venv/Scripts/python.exe -m pytest tests/ -q   (repo .venv = Python 3.11 with pytest; the system Python has no pytest)
Web type-check:  cd apps/web && npx tsc --noEmit -p tsconfig.json
Web lint:        cd apps/web && npm run lint
Apply migration: docker exec -i omnidome-db-1 psql -U admin -d coreconnect < config/migrations/20260924_fno_geo_segments.sql   (inside WSL)
Rebuild service: DOCKER_BUILDKIT=0 docker compose build fno_intelligence && docker compose up -d --no-deps fno_intelligence   (inside WSL, ~/omnidome mirror; grep the build log for failure markers)
Rebuild web:     ~/rebuild_web_getsession_fix.sh then docker compose up -d --no-deps web   (inside WSL)
```

## Project Structure

```
services/fno_intelligence/geo_segments.py        → pure logic: eligibility, area summary, radius, CSV/KML
services/fno_intelligence/models.py              → + FNOGeoSegment model
services/fno_intelligence/routes.py              → + /geo-segments endpoints
services/fno_intelligence/tests/test_geo_segments.py → unit tests for geo_segments.py
config/migrations/20260924_fno_geo_segments.sql  → table DDL (create_all never ALTERs)
apps/web/lib/fno-api.ts                          → typed client for the endpoints (new)
apps/web/components/modules/sales-lead-sources.tsx → new "FNO passed homes" section (new)
apps/web/components/modules/sales-module.tsx     → mount the section, delete the fake panels + handlers
```

## Code Style

Follow the existing `fno_intelligence` conventions: pure functions in their own
module, tested without DB/network; routes stay thin.

```python
def suggested_radius_km(centroid: tuple[float, float] | None,
                        points: list[tuple[float, float]]) -> float:
    """Max distance from centroid to any point, rounded up to 0.5 km, min 1.0."""
    if centroid is None or not points:
        return MIN_RADIUS_KM
    furthest = max(haversine_km(centroid, p) for p in points)
    return max(MIN_RADIUS_KM, math.ceil(furthest * 2) / 2)
```

Frontend: data comes only from `fno-api.ts`; no fixtures, no `setTimeout`
fakes; loading / empty / error states for every fetch; the live count is
debounced (~400 ms) and never flashes the whole section.

## Testing Strategy

- **Unit (pytest, no DB):** eligibility predicate for every status /
  geocode combination; area grouping; centroid; radius rounding and the 1 km
  floor; homes without coordinates; CSV header/rows and absence of any
  address column; KML well-formedness (parse with `xml.etree`) and omission
  of centroid-less areas; filter validation (date order, unknown dwelling type).
- **Live (running service, manual, same convention as T1–T3):** preview
  counts cross-checked against a direct SQL count on the dev DB; create →
  list → detail → refresh → export → delete; `409` duplicate name; other
  tenant's id → `404`.
- **Web:** `tsc` + `lint` clean; browser check on `http://127.0.0.1:3000`
  (not `localhost`): filters populate from real data, count updates on change,
  save appears in the list, both exports download, no "Nexus Logistics"
  fixture text anywhere (`grep` returns 0).

## Boundaries

- **Always:** tenant-filter every query; exclude non-`normalized` homes; keep
  individual addresses out of exports and segment responses; ship the
  migration SQL with the model change; run pytest + tsc before committing;
  grep Docker build logs for failures instead of trusting the exit code.
- **Ask first:** adding a dependency; changing existing passed-homes tables or
  enums; exposing per-address data; pushing to `main`.
- **Never:** send addresses to a third-party platform; render invented data in
  the UI; commit `.env` files or secrets.

## Success Criteria

1. `POST /geo-segments/preview` returns `home_count` equal to a direct SQL count
   of eligible homes for the same filters on the dev DB, with correct
   per-reason exclusion counts.
2. A saved segment survives a service restart and appears in `GET /geo-segments`.
3. CSV export has exactly the listed columns, one row per area, and no
   address column; KML parses and has one placemark per area with a centroid.
4. Preview responds in < 1 s for 10,000 passed homes on this machine.
5. The Sales tab shows the new section with real data; the three fake panels and
   their handlers are deleted; `tsc`, `lint` and pytest all pass.

## Open Questions

- Segment scope when a new import arrives: stays on the cached summary until
  someone clicks Refresh (proposed), or auto-refreshes on the next import?
- Default "passed since" window in the builder: none (proposed) or last 90 days?
