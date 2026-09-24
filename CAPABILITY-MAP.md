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
| `geo-segments` | Build a segment from passed homes (FNO, import, suburbs, date passed, dwelling type); only eligible homes (existing customers, duplicates and invalid rows excluded). Outputs a home count and area targets (suburb / postcode / centroid + radius), never people. | existing passed-homes pipeline |
| `marketing-audiences` | Wire Marketing → Audiences to the real `/segments` API (it is currently hard-coded). Sales "Add to campaign audience" pushes a geo segment there; the "New Audience" modal gets geo fields that match. Ad platforms: stored in OmniDome + CSV/KML export first; live Google/Meta push later. | `geo-segments` |
| `field-territories` | Endpoint the Sales Field app (`apps/field-sales-app`) pulls: a segment's addresses as a location-ordered walk list, door outcomes recorded per home; "interested" creates a real sales lead immediately. | `geo-segments` |
| `opportunity-finder` | Sales section with two modes. Companies: area + industry → Firecrawl search → review → B2B lead. Tenders and RFQs: user-added source URLs → scheduled scrape with screenshot → extracted tender (title, issuer, reference, closing date, briefing date, required documents, attachments) → track / add to pipeline. | shared Firecrawl client (`services/common/firecrawl.py`) |
| `market-signals` | Shared watch list (competitor pricing, regulations, FNO notices) → snapshot + screenshot diffs → typed signals consumed by Compliance, Products and Service. Not shown in the Sales tab. | shared Firecrawl client; reuses `opportunity-finder`'s source/snapshot tables |

Build order: `geo-segments` → `marketing-audiences`, `field-territories` →
`opportunity-finder` → `market-signals`

## Decisions taken at approval

1. Ad platforms: audiences are stored in OmniDome with CSV/KML export; the
   live Google Ads / Meta push is a later module (needs provider API approval).
2. `opportunity-finder` and `market-signals` live inside `fno_intelligence`
   (no new container; this machine's WSL stack is unstable above ~8 containers).
3. Company search uses Firecrawl only; Google Places can be added later if
   results are too thin.
4. A field "interested" door outcome creates the sales lead immediately.
5. Tender seed sources: still to be supplied by the user (asked when
   `opportunity-finder` is specced).
6. The UI is built in the app's own components, one slice per module; no
   dead buttons for modules that are not built yet.
