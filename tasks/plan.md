# Implementation Plan: import flow → opportunity-finder → marketing-audiences

Specs: [SPEC-geo-segments.md](../SPEC-geo-segments.md) (v2 amendment),
[SPEC-opportunity-finder.md](../SPEC-opportunity-finder.md),
[SPEC-marketing-audiences.md](../SPEC-marketing-audiences.md) ·
Map: [CAPABILITY-MAP.md](../CAPABILITY-MAP.md) · Tasks: [todo.md](todo.md)

Previously completed: **geo-segments v1** (Tasks 1–7, commits c67980bf..496ba8e1,
all spec criteria met — see git history and SPEC-geo-segments.md).

## Overview

Three parts, in the order the user set: (A) a manual import flow on top of the
existing passed-homes upload API; (B) opportunity-finder — OpenStreetMap
company search and URL-driven tender/RFQ tracking with screenshots; (C)
marketing-audiences — real Marketing → Audiences fed by both home and business
segments. The user authorised building all three end-to-end without stopping
between tasks; each task is still verified against its acceptance criteria and
committed on its own.

## Architecture decisions

- **Import UI reuses the existing API unchanged**; progress comes from polling
  the import detail and geocode-status endpoints. Two small backend additions:
  `address_raw` in the passed-homes list and a startup sweep for stuck imports.
- **Opportunity-finder lives in `fno_intelligence`** (no new container), in a
  new `opportunity_routes.py` router (routes.py is already ~1,800 lines) and a
  pure `opportunities.py` module.
- **Slow external calls run as background jobs** (`schedule_background`):
  Overpass company searches (~20 s) and tender scans (Firecrawl + LLM).
  The UI polls job status; requests never hang.
- **Overpass fallbacks**: main instance first, then mirrors; 60 s timeouts.
- **Tender extraction = Firecrawl markdown + screenshot → OpenRouter JSON**,
  reusing `web_intel._reason`. Screenshots are downloaded and stored as bytes
  in Postgres (durable, no volume dependency), served by an endpoint.
- **Scheduler**: a startup loop per worker every 10 min; a Postgres advisory
  lock per source prevents the two uvicorn workers from double-scanning.
- **Leads are created from the browser** through the existing Sales API, then
  the company/tender is patched with the lead id (no service-to-service write).
- **Audiences**: the marketing service's existing table + `rules` JSONB carry
  both segment kinds; the `:rules::jsonb` bind bug is fixed with `CAST(:rules AS jsonb)`.
- **UI**: segmented control (Homes passed / Companies / Tenders & RFQs) in the
  lead-sources area; every form sits directly above the table it feeds.
- **Web rebuilt at checkpoints only** (~10–15 min per build on this machine).

## Task list

### Part A — import flow
- [ ] A1: Backend: `address_raw` in passed-homes list + stuck-import sweep
- [ ] A2: Import panel, progress, auto-geocode, statuses, view issues, template
### Checkpoint A
- [ ] fno + web rebuilt; a CSV imported via the UI end-to-end; API upload still works

### Part B — opportunity-finder
- [ ] B1: `opportunities.py` pure logic + tests
- [ ] B2: Models + migration (5 tables)
- [ ] B3: Company search API (background Overpass job, enrich, patch)
- [ ] B4: Tender sources / scan / tenders / screenshot API + scheduler
- [ ] B5: UI: segmented control + Companies view (+ Add as lead)
- [ ] B6: UI: Tenders & RFQs view (+ Add to pipeline)
### Checkpoint B
- [ ] Real area search and a real tender page work in the browser

### Part C — marketing-audiences
- [ ] C1: Marketing API: fix jsonb bug, upsert per source, detail, delete, type filter
- [ ] C2: Sales: "Add to audience" for geo segments and company searches
- [ ] C3: Marketing → Audiences real cards, detail/export/delete, aligned New Audience modal
### Checkpoint: Complete
- [ ] Every task checked against its acceptance criteria; all spec success criteria verified; pushed

## Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Overpass is slow / 504s | Med | Background job, mirrors, clear failed state with retry |
| OSM contact coverage is thin (~9%) | Med | On-demand Firecrawl contact lookup |
| Tender pages vary wildly / JS-rendered | High | Firecrawl renders JS; strict-JSON LLM extraction; raw snapshot + screenshot kept; tested on real portals |
| LLM returns malformed JSON | Med | Tolerant parser (code fences, trailing text) with unit tests; scan marked failed with reason, nothing deleted |
| Two uvicorn workers double-scan | Med | Advisory lock per source |
| Concurrent sessions editing fno_intelligence (upload volume, geocoder fix) | Med | New code in new files where possible; check git state before commits; re-verify endpoints after their merges |
| Web rebuild time | Low | Rebuild at checkpoints only |
