# Capability Map: Lead Sources and Market Intelligence

Approved 2026-09-24. Module ids are stable: specs, plans and tasks refer to
work by these ids. Each module gets its own `SPEC-<module-id>.md` in this
directory, written in build order.

Replaces the simulated panels in Sales → "AI Lead Warming & Automations"
(`handleRunAiWarmingSimulation` / `handleGenerateAiProspects` in
`apps/web/components/modules/sales-module.tsx`, which render hard-coded
fixtures via `setTimeout`) with real flows built on the FNO passed-homes
pipeline (`services/fno_intelligence`, imports → normalize/dedupe → geocode →
customer suppression).

| Module id | Responsibility | Depends on |
|---|---|---|
| `geo-segments` | Build a segment from passed homes (FNO, import, suburbs, date passed, dwelling type); only eligible homes (existing customers, duplicates and invalid rows excluded). Outputs a home count and area targets (suburb / postcode / centroid + radius), never people. **v2 adds the manual import flow** (upload form alongside the existing API). | existing passed-homes pipeline |
| `opportunity-finder` | Sales section with two modes. Companies: area + category → OpenStreetMap (Nominatim + Overpass) → review → optional Firecrawl contact lookup → B2B lead. Tenders and RFQs: user pastes any source URL → scheduled Firecrawl scrape with screenshot → LLM-extracted tenders (title, issuer, reference, closing date, briefing, required documents, document links) → track / add to pipeline. | shared Firecrawl client (`services/common/firecrawl.py`), OpenStreetMap |
| `marketing-audiences` | Wire Marketing → Audiences to the real `/segments` API (currently hard-coded). Two segment kinds: **homes** (from a geo segment) and **businesses** (from a company search). Sales "Add to campaign audience" pushes either; the "New Audience" modal is aligned to the same fields. Ad platforms: stored in OmniDome + export first; live Google/Meta push later. | `geo-segments`, `opportunity-finder` |
| `field-territories` | Endpoint the Sales Field app (`apps/field-sales-app`) pulls: a segment's addresses as a location-ordered walk list, door outcomes recorded per home; "interested" creates a real sales lead immediately. | `geo-segments` |
| `market-signals` | Shared watch list (competitor pricing, regulations, FNO notices) → snapshot + screenshot diffs → typed signals consumed by Compliance, Products and Service. Not shown in the Sales tab. | shared Firecrawl client; reuses `opportunity-finder`'s source/snapshot tables |

Build order (revised 2026-09-24 by the user): `geo-segments` (+ import flow) →
`opportunity-finder` → `marketing-audiences` → `field-territories` → `market-signals`

## Decisions taken at approval

1. Ad platforms: audiences are stored in OmniDome with CSV/KML export; the
   live Google Ads / Meta push is a later module (needs provider API approval).
2. `opportunity-finder` and `market-signals` live inside `fno_intelligence`
   (no new container; this machine's WSL stack is unstable above ~8 containers).
3. Company search uses Firecrawl only; Google Places can be added later if
   results are too thin.
4. A field "interested" door outcome creates the sales lead immediately.
5. Tender sources: no fixed list — the user pastes any site URL (government
   or company procurement page) and the module handles it generically.
7. Company search is grounded per area with OpenStreetMap (Nominatim for the
   area, Overpass for businesses) for now.
8. The passed-homes API upload stays; the UI adds a manual upload on top.
6. The UI is built in the app's own components, one slice per module; no
   dead buttons for modules that are not built yet.
