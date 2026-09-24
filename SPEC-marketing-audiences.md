# Spec: marketing-audiences

Module 3 of [CAPABILITY-MAP.md](CAPABILITY-MAP.md). Status: approved 2026-09-24 (user authorised building all three parts end-to-end).

## Objective

Make Marketing → Audiences real and the destination for both kinds of
targeting Sales builds:

- **Homes audiences** from a geo segment (areas + home counts, never
  addresses) for location-based ads.
- **Business audiences** from a company search (named public businesses with
  location and contact details) for B2B campaigns.

Today the Audiences tab renders three hard-coded cards and "Save Audience"
only updates page state, while the marketing service's `POST /segments` is
broken (`:rules::jsonb` in a SQLAlchemy `text()` is not bound).

## Rules

- Stored in `marketing_audience_segments` (`name`, `description`, `rules`
  JSONB, `member_count`). No schema change; `rules` carries:

```json
{
  "type": "homes | businesses | custom",
  "source": "fno_geo_segment | company_search | manual",
  "source_id": "uuid or null",
  "source_name": "Brackenfell review",
  "platform": "google_ads | meta | linkedin | custom",
  "areas": [ { "suburb": "…", "city": "…", "postal_code": "…", "homes": 2,
               "centroid_lat": -33.9, "centroid_lng": 18.7, "suggested_radius_km": 1.0 } ],
  "businesses": [ { "name": "…", "category": "…", "address": "…", "phone": "…",
                    "website": "…", "lat": -26.1, "lng": 28.0 } ],
  "regions": ["…"], "interest": "…"
}
```

- `member_count` = homes (homes audiences) or businesses (business
  audiences); custom audiences keep 0 until a real count exists.
- Pushing the same source again (same `source` + `source_id`) **updates** the
  existing audience instead of creating a duplicate (response says `updated`).
- Homes audiences never contain individual addresses (only areas).

## Contract (marketing service, via `/svc/marketing`)

| Method + path | Purpose |
|---|---|
| `GET /segments?type=` | list, newest first |
| `POST /segments` `{name, description?, rules, member_count?}` | 201 created, or 200 with `updated: true` on same source |
| `GET /segments/{id}` | detail |
| `DELETE /segments/{id}` | 204 |

Validation: `name` 1–255 chars; `rules.type` in the three kinds; `platform`
in the four values; 404 across tenants.

## UI

- **Sales → Homes passed → saved segment row:** "Add to audience" → small
  inline form (platform, name prefilled) → pushes; the row then shows
  "In Marketing" with the platform.
- **Sales → Companies → search results:** "Add to audience" pushes the search's
  non-dismissed businesses as a business audience.
- **Marketing → Audiences:** cards from `GET /segments` (name, type badge
  Homes/Businesses/Custom, platform badge, member count and unit, source,
  updated date); click opens detail (areas table or businesses table) with
  **Export CSV** and **Delete**; empty state explains how audiences arrive.
- **New Audience** modal aligned to the same fields: Name, Audience type
  (Homes from FNO segment / Businesses from company search / Custom regions),
  Source picker (loads saved geo segments or company searches), Platform,
  Description. Custom keeps the regions + interest fields.

## Testing / Commands / Boundaries

As in the other specs. Marketing has no pure-logic module worth isolating;
verification is live (create/upsert/list/detail/delete via the API, including
the jsonb bug reproduction first) plus tsc/lint and a browser pass.
Never: put home addresses in an audience; call a real ad platform API.

## Success criteria

1. `POST /segments` works (bug reproduced, then fixed) and upserts per source.
2. A geo segment and a company search each land in Marketing → Audiences with
   correct counts from one click in Sales.
3. The Audiences tab shows only real data; New Audience creates real records
   for all three types; export and delete work.
4. tsc, lint clean; browser pass on the deployed app.

## Implementation notes (2026-09-24)

- Bug reproduced first: `POST /segments` returned 500 (`syntax error at or near
  ":"`), so no audience had ever been saved. Fixed with `CAST(:rules AS jsonb)`.
- One additive column, `updated_at`, so re-pushing a source shows a fresh date
  (added idempotently by the service's table-ensure DDL).
- Isolation: other tenants get 403 from the marketing entitlement guard before
  the route runs, and every query also filters on `tenant_id`; the 404
  cross-tenant path couldn't be exercised live because only the dev tenant has
  marketing enabled.
