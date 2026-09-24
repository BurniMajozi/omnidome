# Spec: opportunity-finder

Module 2 of [CAPABILITY-MAP.md](CAPABILITY-MAP.md). Status: approved 2026-09-24 (user authorised building all three parts end-to-end).

## Objective

Give sales two real sources of **business** opportunities, next to the FNO
passed-homes section in Sales → lead sources:

1. **Companies** — find businesses in an area of interest, grounded on
   OpenStreetMap, review them, optionally look up missing contact details, and
   turn good ones into B2B sales leads.
2. **Tenders and RFQs** — the user pastes the URL of *any* procurement page
   (government portal, municipality, SOE, company supplier page). OmniDome
   scans it on a schedule, keeps a screenshot as evidence, and extracts each
   tender: title, issuer, reference, closing date, briefing session, required
   documents and document links. Sales tracks them (New → Reviewing → Bidding /
   Skipped) and can add one to the pipeline.

Users: sales/bid managers. Company data is public business information
(OpenStreetMap is ODbL: show "© OpenStreetMap contributors").

## Rules

### Companies
- Area → Nominatim (`q=<area>, South Africa`, first result) gives a centre and
  label; **422** "We couldn't find that area" if nothing matches.
- Search radius: 1, 2, 5 or 10 km around the centre (default 2).
- Categories map to OSM tag filters (fixed list, `CATEGORIES` in
  `opportunities.py`): all businesses, offices & professional services, retail,
  hospitality, healthcare, education, finance, industrial & manufacturing,
  estates & property. Only named features (`["name"]`).
- Overpass runs as a **background job** (it takes ~20 s); job status
  `queued → running → done | failed`. Endpoints tried in order
  (`overpass-api.de`, then mirrors), 60 s timeout each.
- Results de-duplicated by OSM type+id, sorted by distance, capped at 300.
  Address assembled from `addr:*`; phone/email/website from plain or
  `contact:*` tags.
- **Find contact details** (per company, on demand): Firecrawl search
  "<name> <suburb/city>", LLM extracts `{website, phone, email}` for that
  business only; never overwrites a value OSM already had; stored with
  `enriched_at`. Public business contact data only.
- Company status: `new`, `lead_created`, `dismissed`.

### Tenders
- Source URL must be `http(s)`, public host (no localhost / private IPs), and
  unique per tenant.
- A scan: Firecrawl scrape (`markdown` + `screenshot`) → store a snapshot
  (markdown, SHA-256, screenshot bytes) → LLM extracts a JSON list of tenders →
  for up to 10 newly-seen tenders with a detail URL, scrape the detail page and
  fill documents / briefing / closing details → upsert.
- De-dup key per source: normalised reference if present, else normalised
  title. Re-seen tenders update `last_seen_at` and any newly found fields;
  user-set status is never overwritten by a scan.
- Dates parsed from common SA formats ("15 October 2026 11:00",
  "2026/10/15", "15-10-2026") into timestamps; the raw text is kept too.
- Scheduling: each source has `scan_interval_hours` (12, 24 default, 168).
  A loop in the service checks every 10 minutes; a Postgres advisory lock
  per source stops the service's two workers scanning the same source twice.
- Scan failures are recorded on the source (`last_status`, `last_error`) and
  never delete existing tenders.
- Tender status: `new`, `reviewing`, `bidding`, `skipped`.

### Leads
- "Add as lead" (company) and "Add to pipeline" (tender) create a Sales lead
  through the existing `POST /api/sales/leads` from the browser, then record
  the lead id on the company / tender (`PATCH`). Sources `COMPANY_SEARCH` and
  `TENDER` (added to the Sales channel list so they're labelled).

## Contract (prefix `/api/fno/opportunities`, tenant-scoped)

| Method + path | Purpose |
|---|---|
| `GET /company-categories` | `[{id, label}]` |
| `POST /company-searches` `{area, category, radius_km}` | 202, search `{id, status:"queued", area_label, center_lat, center_lng, …}`; 422 unknown area/category/radius |
| `GET /company-searches` | recent searches (newest first, 20) |
| `GET /company-searches/{id}` | search + `companies[]` |
| `POST /companies/{id}/enrich` | 200 updated company (Firecrawl + LLM); 503 if Firecrawl unavailable |
| `PATCH /companies/{id}` `{status?, sales_lead_id?}` | updated company |
| `GET /sources` | sources with `tender_count`, last scan info |
| `POST /sources` `{url, label?, scan_interval_hours?}` | 201 source (scan queued immediately); 409 duplicate; 422 bad URL |
| `PATCH /sources/{id}` `{label?, active?, scan_interval_hours?}` | updated source |
| `DELETE /sources/{id}` | 204 (its tenders and snapshots go too) |
| `POST /sources/{id}/scan` | 202 queued |
| `GET /tenders?status=&source_id=&include_closed=` | tenders, soonest closing first |
| `PATCH /tenders/{id}` `{status?, sales_lead_id?}` | updated tender |
| `GET /snapshots/{id}/screenshot` | `image/png` (or stored mime) |

## Data (new tables in `fno_intelligence`, migration `20260924_opportunity_finder.sql`)

`opp_company_searches`, `opp_companies`, `opp_sources`, `opp_snapshots`,
`opp_tenders` — columns as in `models.py`; unique constraints: companies
`(tenant_id, search_id, osm_type, osm_id)`, sources `(tenant_id, url)`,
tenders `(tenant_id, source_id, dedupe_key)`.

## UI (Sales → lead sources)

A segmented control at the top of the lead-sources area switches between
**Homes passed**, **Companies** and **Tenders & RFQs**. Every form sits
directly above the table it feeds and uses the same column rhythm.

- **Companies:** form row (Area, Radius, Category, Search) → progress while the
  job runs → results table (Company + category, Address, Phone, Website,
  Distance, Status, actions: Find contacts, Add as lead, Dismiss); recent
  searches as chips; OSM attribution under the table.
- **Tenders & RFQs:** sources form row (Source URL, Label, Scan every, Add
  source) above the sources table (Source, Last scan, Tenders, Status,
  actions: Scan now, Pause/Resume, Delete) → tenders table (Tender + issuer,
  Reference, Closes (date + countdown; red < 3 days; "Closed"), Briefing,
  Documents (count → expandable list with links), Evidence (screenshot), Status
  select, Add to pipeline). Filter: status + "show closed".

## Code Style / Testing / Commands

As in [SPEC-geo-segments.md](SPEC-geo-segments.md). Pure logic in
`services/fno_intelligence/opportunities.py` with unit tests in
`tests/test_opportunities.py` (no network: Overpass JSON, LLM output and
markdown fixtures are inline). Network flows (Nominatim, Overpass, Firecrawl,
OpenRouter) are live-verified against real sites.

## Boundaries

- Always: tenant-scope every query; validate source URLs; keep scans
  idempotent; store evidence screenshots; show OSM attribution.
- Ask first: paid APIs beyond the existing Firecrawl/OpenRouter keys; new
  containers.
- Never: scrape personal (non-business) contact data; bypass logins, CAPTCHAs
  or robots-style blocks on a source; invent tender data the page doesn't show.

## Success criteria

1. A company search for a real area returns real, named OSM businesses with
   distance, completes as a background job, and survives Overpass being slow.
2. "Find contact details" fills at least website/phone for a business that has
   a web presence, without overwriting OSM values.
3. Adding a real public tender page as a source produces tenders with title
   and closing date, a stored screenshot, and correct de-duplication on rescan.
4. Scheduled rescans run without duplicate scans across the two workers.
5. Add as lead / Add to pipeline create real Sales leads and mark the row.
6. pytest, tsc and lint clean; browser pass on the deployed app.
