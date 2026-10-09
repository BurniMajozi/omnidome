# Analytics & AI API (Research, Competitors, Campaign analysis, Credit usage)

Service: `fno_intelligence` (port 8024). Base path: `/api/fno/analytics`. From the web app use the existing proxy:
`/svc/fno-intelligence/api/fno/analytics/...`. All endpoints are tenant scoped by the signed identity headers.
Long work (research, scans, analyses) is asynchronous: the POST returns `202` with the row, then poll the GET.

Powered by Firecrawl (v2 API only: search / scrape / map; no Agent/Interact/browser features, so a self-hosted
Firecrawl via `FIRECRAWL_API_BASE_URL` works) and the existing OpenRouter model chain. Nothing here calls any
other provider. Presenton studio is untouched.

## Roles

| Tier | Roles (any) | May |
|---|---|---|
| viewer | any authenticated tenant member | every `GET` |
| analyst | analyst, manager, marketing, marketing_manager, sales_manager, strategy, executive, admin tier | `POST` research / scans / analyses / refresh, create + edit competitors |
| admin | owner, admin, org_admin, tenant_admin, super_admin, platform_admin, analytics_admin | `DELETE`, `PUT /usage/limits` |

Also permission keys `analytics.run`/`analytics.write` (analyst) and `analytics.admin`. Wrong tier gives `403`
`{"detail": "This action needs an analytics analyst role"}`. `ANALYTICS_ENFORCE_ROLES=false` disables the gates (dev only).

## Common behaviour

* Errors: `{"detail": "..."}`. `422` bad input / rejected URL, `404` unknown id (also for another tenant's id),
  `409` conflict (already running, duplicate), `429` credit cap or too many concurrent runs, `502/503` Firecrawl problems.
* **Credit caps**: every Firecrawl call is metered. When a cap would be exceeded the API answers `429` with a message
  such as `Firecrawl credit monthly cap reached (2000 of 2000 credits used, this action needs about 12). Ask an admin to raise the cap or wait for the next month.`
  Runs that hit a cap mid-way end `failed` with the same text in `error`.
* **URLs you supply** (competitor website/pricing/promo/social, campaign `sources`) must be public `https` URLs, max
  2000 chars, default port, no credentials, no private/internal hosts (SSRF checked, `http` only with `ANALYTICS_ALLOW_HTTP=true`).
  Violations: `422 {"detail": "website: URL rejected: Host resolves to a non-public address"}`.
* Scraped web text is treated as untrusted data (instruction-like text is removed before prompting, it can never change
  parameters). Nothing is labelled "verified" except that an extracted price/quote literally appears in the fetched page.
* Pagination: `limit` + `offset`; list responses are `{"total", "limit", "offset", "items": [...]}`.
* Use Firecrawl responsibly: only public pages, respect each site's terms of service and robots rules; sites that block
  scraping simply return nothing and are reported in `limitations`/`coverage`.

---

## A. Research

### `POST /research` (analyst) -> 202
```json
{ "question": "How is Starlink affecting South African fibre uptake?", "depth": "standard",
  "max_sources": 6, "country": "za", "recency": "month" }
```
`depth`: `quick` (3 sources) | `standard` (6, default) | `deep` (10). `max_sources` 1-15 optional. `country` 2 letters
(default `za`). `recency`: `day|week|month|year` optional. `question` 8-500 chars.

Response (run, no report yet):
```json
{ "id": "uuid", "question": "...", "depth": "standard", "params": {"max_sources": 6, "country": "za", "recency": "month"},
  "status": "queued", "error": null, "credits_used": 0, "model_used": null, "source_count": 0, "summary": null,
  "created_at": "2026-10-09T10:00:00+00:00", "started_at": null, "finished_at": null, "report": null, "sources": null }
```
`status`: `queued | running | done | failed`. Errors: 429 (cap, or 3 runs already active), 403.

### `GET /research?status=&limit=25&offset=0` (viewer)
List without the heavy report: each item has `id, question, depth, status, error, summary, source_count, credits_used, created_at, finished_at`.

### `GET /research/{id}` (viewer)
```json
{ "id": "uuid", "status": "done", "credits_used": 10, "model_used": "vendor/model",
  "report": {
    "summary": "Fibre uptake is still growing [S1]. Satellite is mostly rural [S2].",
    "key_findings": [ { "claim": "Fibre uptake is rising", "source_ids": ["S1"],
                        "quote": {"text": "verbatim excerpt, max 25 words", "source_id": "S1"} } ],
    "limitations": ["Only two sources", "Based only on the pages listed under sources; ..."],
    "stripped_claims": 2,
    "cited_source_ids": ["S1", "S2"] },
  "sources": [ { "id": "S1", "title": "Page title", "url": "https://...", "domain": "example.com",
                 "fetched_at": "2026-10-09T10:00:05+00:00", "snippet": "first ~240 chars" } ] }
```
Guarantees: every claim has at least one valid `source_ids` entry; summary sentences carry `[S#]` markers (render them
as links to `sources[]`); `quote` appears only if it is literally in the cited page; `url`s are only ones Firecrawl
returned; `stripped_claims` counts model statements removed for lacking a valid source. `quote` is optional.

### `GET /research/{id}/export` (viewer)
`text/markdown` attachment (summary, findings with quotes, limitations, sources). `409` unless `status=done`.

### `DELETE /research/{id}` (admin) -> 204

---

## B. Competitor analysis

### Competitor object
```json
{ "id": "uuid", "name": "Rival ISP", "website": "https://www.rival.example",
  "pricing_page_url": "https://rival.example/pricing", "promo_page_url": null, "social_urls": [],
  "active": true, "scan_status": "ok", "last_error": null,
  "last_scanned_at": "2026-10-09T10:00:00+00:00", "created_at": "..." }
```
`scan_status`: `never | scanning | ok | no_data | failed`.

* `POST /competitors` (analyst) -> 201. Body `{name, website, pricing_page_url?, promo_page_url?, social_urls?[<=6]}`.
  `409` duplicate name or limit (`ANALYTICS_MAX_COMPETITORS_PER_TENANT`, default 25). If pricing/promo URLs are omitted the scan discovers them.
* `GET /competitors` (viewer) -> `[Competitor]`
* `GET /competitors/{id}` (viewer)
* `PUT /competitors/{id}` (analyst): same fields, all optional, plus `active`. `null` for pricing/promo URL clears it.
* `DELETE /competitors/{id}` (admin) -> 204 (removes snapshots and changes).

### `POST /competitors/{id}/scan` (analyst) -> 202
```json
{ "competitor_id": "uuid", "scan_status": "scanning", "estimated_credits": 16, "message": "Scan started; poll GET /competitors/{id}." }
```
`409` if a scan is already running, `429` if the estimate would breach a cap. Poll `GET /competitors/{id}` until
`scan_status` is `ok | no_data | failed` (`last_error` explains). A scan: map (1 credit, only when pages not supplied) +
up to 2 pricing pages + 1 promo page, each scraped once with markdown + JSON extraction (5 credits).

### `GET /competitors/{id}/snapshots?limit=20&offset=0` (viewer) - immutable history, newest first
```json
{ "total": 2, "items": [ {
  "id": "uuid", "competitor_id": "uuid", "scanned_at": "...", "content_hash": "sha256", "extraction_method": "firecrawl_json",
  "plans_count": 2, "promotions_count": 1,
  "pages": [ { "url": "https://rival.example/pricing", "kind": "pricing", "fetched_at": "...", "status": "ok", "error": null,
               "chars": 5120, "content_hash": "sha256 of page markdown", "excerpt_hash": "sha256 of first 2000 normalised chars",
               "extraction": "firecrawl_json" } ],
  "plans": [ { "plan_key": "fibre 50|monthly", "plan_name": "Fibre 50", "price_amount": 799.0, "price_text": "R799 per month",
               "currency": "ZAR", "billing_period": "monthly", "speed_text": null, "speed_down_mbps": 50.0, "data_text": null,
               "contract_term": null, "setup_fee_amount": null, "setup_fee_text": null, "setup_fee_verified": null,
               "promo_text": null, "valid_until": null, "price_verified": true, "source_url": "https://rival.example/pricing" } ],
  "promotions": [ { "promo_key": "winter special", "title": "Winter Special", "description": null, "discount_text": "free installation",
                    "valid_until": "31 August", "title_on_page": true, "source_url": "https://rival.example/specials" } ] } ] }
```
`price_verified=false` means the extracted price was NOT found literally in the scraped page text: show it with a warning.
`extraction_method` is `firecrawl_json`, or `llm_markdown` when Firecrawl returned no JSON and our LLM extracted from the page text.

### `GET /competitors/{id}/changes?change_type=&limit=50&offset=0` (viewer)
```json
{ "total": 1, "items": [ { "id": "uuid", "competitor_id": "uuid", "competitor_name": "Rival ISP",
  "snapshot_id": "uuid", "previous_snapshot_id": "uuid",
  "change_type": "price_up", "subject": "Fibre 50", "old_value": "799", "new_value": "849",
  "abs_change": 50.0, "pct_change": 6.26, "currency": "ZAR", "verified": true,
  "source_url": "https://rival.example/pricing", "detected_at": "..." } ] }
```
`change_type`: `price_up | price_down | new_plan | removed_plan | new_promotion | ended_promotion | promotion_changed | plan_attribute_change`.
`abs_change`/`pct_change` only on price changes. `verified` = the price(s) involved were found in the page text.
A plan/promo is reported removed/ended only if its source page was successfully re-read in that scan.

### `GET /competitors/{id}/pricing-history?limit=120` (viewer)
```json
{ "competitor_id": "uuid", "snapshots_considered": 5, "plans": [ { "plan_key": "fibre 50|monthly", "plan_name": "Fibre 50", "currency": "ZAR",
  "points": [ {"scanned_at": "...", "snapshot_id": "uuid", "price_amount": 799.0, "price_verified": true, "source_url": "..."} ] } ] }
```
Points are oldest first (chart-ready).

### `GET /competitors/{id}/promotions` (viewer)
```json
{ "as_of": "...", "active": [ /* promotions from the latest snapshot */ ],
  "plan_promos": [ {"plan_name": "...", "promo_text": "...", "valid_until": null, "source_url": "..."} ],
  "ended": [ {"title": "Winter Special", "ended_detected_at": "...", "last_seen_value": "free installation"} ] }
```

### `GET /competitors/overview` (viewer)
```json
{ "count": 1, "competitors": [ { /* Competitor fields */ "plans_count": 6, "promotions_count": 1,
  "latest_snapshot_at": "...", "latest_changes": [ /* up to 3 change objects */ ] } ] }
```

### `GET /competitors/activity?limit=50` (viewer)
Newest-first mixed feed: `{"items": [ {"kind": "change", "at": "...", ...change fields} , {"kind": "scan", "at": "...", "competitor_id", "competitor_name", "snapshot_id", "plans_count", "promotions_count"} ]}`.

Optional daily re-scan scheduler: off by default (`ANALYTICS_COMPETITOR_SCHEDULER_ENABLED=true` to enable).

---

## C. Campaign analysis

### `POST /campaign-analyses` (analyst) -> 202
```json
{ "name": "Winter push vs Rival", "subject": "Rival Fibre", "own_campaign_id": null,
  "keywords": ["uncapped", "installation"], "sources": "auto", "competitor_id": null, "country": "za" }
```
* `subject`: free-text brand/campaign name, or give `own_campaign_id` (a `marketing_campaigns` id of this tenant; its name becomes the subject unless `subject` is also sent; `404` if not found).
* `sources`: `"auto"` (default; Firecrawl search for reviews, Hellopeter, forums/Reddit, news) or a list of up to 10 URLs (only those pages are read, no search).
* `competitor_id` (optional, must be this tenant's) adds the competitor's name to the search.
* Errors: `422` (no subject, bad URL), `404`, `429` (cap, or 3 analyses running).

Response is the analysis (see below) with `status: "queued"`; poll `GET /campaign-analyses/{id}`.

### `GET /campaign-analyses/{id}` (viewer)
```json
{ "id": "uuid", "name": "...", "subject": "Rival Fibre", "own_campaign_id": null, "competitor_id": null, "keywords": ["uncapped"],
  "sources": "auto", "status": "done", "error": null, "item_count": 42, "credits_used": 28, "run_count": 1,
  "last_run_at": "...", "created_at": "...",
  "aggregate": {
    "total_items": 42,
    "overall": { "label": "negative", "avg_score": -0.31,
                 "split": { "positive": {"count": 10, "pct": 23.8}, "neutral": {"count": 8, "pct": 19.0}, "negative": {"count": 24, "pct": 57.1} } },
    "top_praised_themes":   [ { "theme": "speed", "count": 9, "avg_score": 0.62, "positive": 8, "negative": 1, "polarity": "praised",
                                "examples": [ {"excerpt": "verbatim quote", "url": "https://...", "domain": "hellopeter.com", "sentiment": "positive", "date": "2026-05-10T00:00:00+00:00"} ] } ],
    "top_complained_themes": [ /* same shape, polarity "complained" */ ],
    "all_themes": [ /* up to 30, same shape */ ],
    "trend": [ { "period": "2026-05", "count": 12, "avg_score": -0.1, "positive": 4, "neutral": 3, "negative": 5 } ],
    "undated_items": 7,
    "volume_by_source": [ {"domain": "hellopeter.com", "count": 20} ],
    "volume_by_type": { "review_site": 20, "forum": 12, "news": 10 },
    "ratings": { "count": 15, "avg": 2.9 },
    "coverage": { "queries": 4, "pages_read": 11, "pages_failed": 2, "pages_skipped_blocked": 3, "pages_unchanged": 0 },
    "last_run_new_items": 42 },
  "limitations": [ "Only publicly readable web pages ...", "Google Maps/Google reviews, Facebook, Instagram, X/Twitter, LinkedIn and TikTok are generally not available ...", "..." ] }
```
Always show `limitations`. `aggregate` is null until the first run finishes. `polarity`: `praised | complained | mixed`.

### `GET /campaign-analyses/{id}/items?sentiment=&domain=&theme=&source_type=&limit=50&offset=0` (viewer)
```json
{ "total": 42, "limit": 50, "offset": 0, "items": [ { "id": "uuid", "url": "https://hellopeter.com/...", "domain": "hellopeter.com",
  "source_type": "review_site", "excerpt": "verbatim text from the page (<=400 chars)", "rating": 1.0, "date": "2026-06-02T00:00:00+00:00",
  "sentiment": "negative", "sentiment_score": -0.8, "themes": ["customer service"], "fetched_at": "..." } ] }
```
`source_type`: `review_site | forum | news | social | other`. Every excerpt was checked to occur in the fetched page; `rating`
is set only if that number appears on the page; `date` may be null.

### `GET /campaign-analyses` (viewer): paginated list, items omit `aggregate` and add `overall` (label).
### `POST /campaign-analyses/{id}/refresh` (analyst) -> 202
Re-runs search + extraction; items are de-duplicated by (url, excerpt hash); pages whose text did not change since
the last run are not re-extracted. `409` if already running.
### `DELETE /campaign-analyses/{id}` (admin) -> 204

---

## D. Usage and credit caps

Credits are estimated from Firecrawl's published costs: scrape/map/crawl page = 1; search = 2 per 10 results (+1 per
result when its page is also scraped, as research/campaigns do); JSON extraction = +4 per page. A failed Firecrawl call is refunded in the ledger.

### `GET /usage` (viewer)
```json
{ "period": "2026-10", "month": {"used": 120, "cap": 2000, "remaining": 1880}, "day": {"used": 30, "cap": 400, "remaining": 370},
  "custom_limits": false, "by_feature": {"research": 60, "competitor": 40, "campaign": 20},
  "by_endpoint": {"search": 30, "scrape": 10, "scrape_json": 80}, "note": "Credits are estimates ..." }
```
Month and day are UTC calendar periods.

### `GET /usage/ledger?limit=50` (viewer)
`{"items": [ {"id", "endpoint", "credits", "feature", "ref_id", "note", "created_at"} ]}` (negative credits = refund).

### `PUT /usage/limits` (admin)
```json
{ "monthly_cap": 1000, "daily_cap": 200 }
```
`null` = use the platform default. A tenant admin may only lower caps below the platform default (`403` otherwise);
a platform admin may set any value (use `X-Org-Id` to target a tenant). Returns the same body as `GET /usage`.

---

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `FIRECRAWL_API_KEY` | (empty) | Firecrawl key; keyless free tier works for search/scrape/map with low rate limits |
| `FIRECRAWL_API_BASE_URL` | `https://api.firecrawl.dev/v2` | Point at a self-hosted Firecrawl |
| `FIRECRAWL_TENANT_MONTHLY_CREDITS` | `2000` | Platform default monthly cap per tenant |
| `FIRECRAWL_TENANT_DAILY_CREDITS` | `400` | Platform default daily cap per tenant |
| `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`, `OPENROUTER_FALLBACK_MODELS` | existing | LLM model chain (shared with the rest of the platform) |
| `ANALYTICS_ENFORCE_ROLES` | `true` | `false` disables role gates (dev only) |
| `ANALYTICS_ALLOW_HTTP` | `false` | allow `http://` user URLs |
| `ANALYTICS_MAX_COMPETITORS_PER_TENANT` | `25` | competitor limit |
| `ANALYTICS_COMPETITOR_SCHEDULER_ENABLED` | `false` | daily re-scan worker |
| `ANALYTICS_COMPETITOR_SCAN_INTERVAL_HOURS` | `24` | re-scan age threshold |
| `ANALYTICS_COMPETITOR_SCHEDULER_PERIOD_SECONDS` | `3600` | scheduler tick |
| `ANALYTICS_CAMPAIGN_MAX_QUERIES` / `_MAX_PAGES` / `_MAX_ITEMS` | `4` / `12` / `300` | campaign analysis bounds |
| `ANALYTICS_LLM_TIMEOUT` | `90` | seconds per LLM call |

## Tables (created at startup by `create_all`; new tables only)

`analytics_credit_ledger`, `analytics_credit_limits`, `analytics_research_runs`, `analytics_competitors`,
`analytics_competitor_snapshots` (insert-only), `analytics_competitor_changes`, `analytics_campaign_analyses`,
`analytics_campaign_items`. Runs left `queued/running` by a restart are marked `failed` at startup.

## Known limits

* Credit amounts are estimates; the Firecrawl dashboard is the source of truth for billing.
* Cap check + ledger insert is one short transaction serialised per tenant by a Postgres advisory lock (not exercised by the SQLite unit tests). A run's Firecrawl spend is charged call-by-call, so a run can stop part-way at the cap.
* Review coverage depends on what search returns and what sites allow; Google/Facebook reviews are not available.
