# BI Studio / Deck Studio API (backend contract)

Service: `fno_intelligence`. Base path `/api/fno/bi`, reached from the web app through the existing rewrite
`/svc/fno-intelligence/api/fno/bi/...` (same as `/api/fno/analytics`). All routes need the normal auth headers/JWT and
are tenant scoped. Source: `services/fno_intelligence/bi_*.py`.

## Roles (same helpers as Analytics & AI; `ANALYTICS_ENFORCE_ROLES=false` disables gates locally)

| Tier | Who | Can |
|---|---|---|
| viewer | any tenant member | datasets, query, chart suggestions, read brand kits / decks / versions / runs, resolve, export |
| analyst | analyst, manager, marketing, executive, ... and admins | create/edit/duplicate/restore/refresh decks, AI assist, suggest brand from URL |
| admin | owner, admin, org_admin, tenant_admin, analytics_admin | delete decks, publish/unpublish, create/edit/delete brand kits; only role that can edit a published deck |

Errors: `401` unauthenticated, `403` role, `404` not found / other tenant's object, `409` version conflict or cap, `422` validation
(message is user-presentable), `428` missing `If-Match`, `429` rate or daily cap, `502/503` upstream (model, Firecrawl, source table).

## 1. Semantic layer

There is no free SQL. A query is JSON validated against the registry; SQL is assembled only from registry fragments; every value is a
bound parameter; every query is constrained by `tenant_id`; statement timeout 8 s; times bucketed in `Africa/Johannesburg`.

### `GET /bi/datasets`
Returns `{datasets[], skipped[], grains[], filter_ops[], limits{}}`. Each dataset:
```json
{"id":"billing_invoices","label":"Billing: invoices","description":"...","category":"Billing","source_tables":["invoices","subscriptions"],
 "default_time_dimension":"created_at",
 "dimensions":[{"id":"created_at","label":"Invoice date","type":"time","grains":["day","week","month","quarter","year"],"filter_ops":["between","eq","gt","gte","is_null","lt","lte","not_null"]},
               {"id":"status","label":"Invoice status","type":"category","cardinality":"low","filter_ops":[...]}],
 "measures":[{"id":"invoiced","label":"Invoiced (incl. VAT)","agg":"sum","format":"currency_zar","unit":null,"additive":true,"description":""}]}
```
Dimension `type`: `time | category | number`. Measure `format`: `currency_zar | number | percent | duration` (percent values are fractions 0-1,
duration `unit` is `hours`). `additive` = safe to stack / pie / share. `cardinality` (low <= 8, medium <= 25, high) feeds chart suggestions.

### Datasets
`billing_invoices`, `billing_payments`, `billing_subscriptions` (MRR, ARPU), `crm_customers`, `sales_leads`, `sales_pipeline`, `support_tickets`,
`network_services`, `network_sla_breaches`, `marketing_campaigns`, `social_daily`, `social_posts`, `competitor_changes`, `competitor_scans`,
`campaign_sentiment`. Notable measures: invoices `invoiced, invoiced_ex_vat, vat, collected, outstanding, overdue_amount, collection_rate,
customers_billed, arpu, avg_invoice, invoice_count`; invoice dimensions include `aging_bucket` (Current, 1-30, 31-60, 61-90, 90+ days, Settled, ordered
correctly), `plan`, `segment`, `status`. `billing_subscriptions.mrr` is a *current snapshot* of active subscriptions normalised to a month.

Skipped (reasons are also returned in `skipped[]`): `network_usage` (no per-subscriber usage-volume table; `network_performance_metrics` mixes units),
`marketing_followers` (cumulative counts per day cannot be summed over a grain), `finance_gl` (ledger tables not verified), `competitor_plan_prices`
(prices live in JSON columns; only structured change rows are exposed). The CRM and Sales `leads` tables are one shared table; only the columns both
services write are used.

### `POST /bi/query` (viewer)
Query spec:
```json
{"dataset":"billing_invoices",
 "measures":["invoiced","outstanding"],
 "dimensions":["plan"],
 "filters":[{"field":"status","op":"in","value":["sent","paid"]}],
 "time":{"dimension":"created_at","grain":"month","from":"2026-01-01","to":"2026-06-30"},
 "order_by":[{"field":"invoiced","dir":"desc"}],
 "limit":500}
```
* `dimensions` take category/number dimensions only. Time dimensions go in `time`; `grain` omitted = just a date range filter (no grouping);
  `dimension` omitted = the dataset default; `from`/`to` inclusive dates.
* Filter `field` is any dimension id (time dimensions included; measures are not filterable). Ops by type: category `eq neq in not_in contains is_null not_null`,
  number `eq neq gt gte lt lte between in is_null not_null`, time `eq gt gte lt lte between is_null not_null` (dates `YYYY-MM-DD`; `between` takes `[a,b]`; `in` max 100 values).
* `order_by.field` must be a selected column. Default order: time ascending, else first measure descending. `limit` 1-1000 (default 500). Max 12 measures, 4 dimensions, 20 filters.
* Anything unknown -> `422` with the offending id; unreadable source table or timeout -> `503`; per-tenant rate limit (`BI_QUERY_RATE_PER_MIN`) -> `429`.

Response:
```json
{"columns":[{"id":"created_at","label":"Invoice date","kind":"time","type":"time","grain":"month"},
            {"id":"plan","label":"Plan","kind":"dimension","type":"category"},
            {"id":"invoiced","label":"Invoiced (incl. VAT)","kind":"measure","type":"number","format":"currency_zar","agg":"sum","additive":true}],
 "rows":[["2026-01-01","Fibre 100",1000.0]],
 "totals":{"invoiced":3900.0},
 "meta":{"dataset":"billing_invoices","generated_at":"...","row_count":1,"truncated":false,"timezone":"Africa/Johannesburg",
         "time":{"dimension":"created_at","grain":"month","from":null,"to":null},"query_key":"ab12..."}}
```
Time cells are the bucket start `YYYY-MM-DD`. `totals` is computed over the whole filter slice (not just returned rows) and is correct for ratios/averages.
Rows are arrays aligned with `columns`. `truncated=true` means more rows than `limit` existed.

### Chart suggestions (deterministic, no LLM)
`POST /bi/chart-suggestions` `{dataset, measures[], dimensions[], time?{dimension?,grain}, row_count?}` or
`GET /bi/chart-suggestions?dataset=&measures=a,b&dimensions=x&grain=month&time_dimension=&row_count=`.
```json
{"dataset":"billing_invoices","recommended":"line",
 "suggestions":[{"type":"line","score":90,"reason":"A trend over time reads best as a line","series_mapping":{"x":"created_at","y":["invoiced"],"series":null}}, ... ,{"type":"table","score":20,...}]}
```
Types: `kpi, line, area, column, bar, stacked_column, combo, pie, donut, scatter, waterfall, table`. `series_mapping` can be pasted into a chart block's `series`.

### `GET /bi/meta` -> layouts, chart types, block types, token formats, limits.

## 2. Brand kits (`/bi/brand-kits`)

| Route | Role | Notes |
|---|---|---|
| `GET /brand-kits/options` | viewer | safe fonts with export fallbacks, layouts, default palette, logo limits |
| `GET /brand-kits` | viewer | list (no logo payload; `has_logo`), default first |
| `GET /brand-kits/default` | viewer | `{kit}` or `{kit:null}` |
| `GET /brand-kits/{id}` | viewer | includes `logo_data_url` |
| `POST /brand-kits` | admin | create; first kit becomes default; max 10 per tenant; name unique |
| `PUT /brand-kits/{id}` | admin | partial; nested objects merge; `remove_logo`, `make_default` |
| `POST /brand-kits/{id}/default` | admin | |
| `DELETE /brand-kits/{id}` | admin | decks keep working with theme defaults |
| `POST /brand-kits/suggest-from-url` | analyst | `{url}` -> suggestion only, nothing saved |

Shape (create/update body and response):
```json
{"name":"Main","company_name":"Acme Fibre","tagline":"Fast and fair",
 "palette":{"primary":"#0B5FFF","secondary":"#1F2A44","accent":"#F5A623","background":"#FFFFFF","text":"#1B1F2A",
            "chart":["#0B5FFF","#F5A623","#2BB673","#E5484D","#8E4EC6","#12A594"]},
 "fonts":{"heading":"Calibri","body":"Calibri"},
 "voice":{"formality":"neutral","jargon_level":"medium","banned_words":[],"notes":""},
 "footer_text":"","slide_numbers":true,
 "layout_prefs":{"default_layout":"content","title_align":"left","density":"comfortable","show_logo":true,"logo_position":"top_right"},
 "logo_data_url":"data:image/png;base64,...","remove_logo":false,"make_default":false}
```
Hex colours are validated and normalised to `#RRGGBB` (3-digit accepted). Fonts must be from the safe list (Calibri, Arial, Georgia, Inter, Roboto, Montserrat,
Helvetica, Times New Roman, Verdana, Open Sans, Lato, Segoe UI, Cambria, Tahoma, Trebuchet MS, Poppins, Source Sans Pro); `options` returns the fallback
the exporter should use when a font is not installed. Logo: PNG/JPEG/SVG data URL, <= 512 KB decoded, magic bytes checked; SVG is rebuilt from an
allow-list (no scripts, event handlers, foreignObject, external references, DOCTYPE/entities). Stored sanitised, served back as a data URL.

`suggest-from-url` is SSRF-checked (`url_safety`), metered through the Firecrawl credit ledger (5 credits, feature `bi_brand`, respects tenant caps, `429`
when capped) and returns `{company_name, tagline, palette{primary?,secondary?,accent?}, fonts|null, logo_url|null, source_url, credits_used, saved:false}`.
All extracted values are validated; the backend never downloads `logo_url` (ask the user to upload the image).

## 3. Decks (`/bi/decks`)

### Deck document (schema_version 1)
```json
{"schema_version":1,"title":"Q1 Review","brand_kit_id":"<uuid|null, set by the server>",
 "theme":{"palette":{"primary":"#112233"},"fonts":{"heading":"Georgia"},"footer_text":"Confidential","slide_numbers":true},
 "settings":{"strict_numbers":false},
 "queries":{"rev":{ "<query spec>" }},
 "slides":[{"id":"s2","layout":"chart_plus_text","title":"Revenue","subtitle":"optional","notes":"Total {{tot.invoiced|currency}}",
   "blocks":[ ... ]}]}
```
* `layout`: `title section content two_column chart_full chart_plus_text kpi_strip table comparison closing`.
* Ids (`^[A-Za-z0-9_-]{1,40}$`) are unique per deck across slides, blocks and query aliases.
* `theme` holds *overrides* of the brand kit (palette keys incl. `chart`, fonts, footer, slide numbers); `export` returns the merged `theme`.
* Every block may carry `slot` (layout slot hint) and `frame` `{x,y,w,h}` in percent of the slide for manual positioning.
* `settings.strict_numbers=true` rejects (422) any save with a literal figure outside a token. Otherwise saves succeed and return
  `warnings.ungrounded_numbers:[{where,literal}]`.

Blocks (`type`):
```json
{"type":"text","id":"t1","role":"body|callout|quote|caption","align":"left","items":[{"text":"Invoiced {{rev.invoiced.last}}","bullet":true,"level":0,"bold":false}]}
{"type":"kpi","id":"k1","label":"Outstanding","value_ref":"tot.outstanding","delta_ref":"rev.outstanding.delta","format":"currency","delta_format":"signed_currency","caption":"","good_direction":"up|down"}
{"type":"chart","id":"c1","chart_type":"column|bar|line|area|pie|donut|stacked_column|combo|scatter|waterfall","title":"...",
 "query_ref":"rev",                       // or an inline "query": {spec} (then the block id is its alias); not both
 "series":{"x":"created_at","y":["invoiced"],"y2":[],"series":null},
 "axis":{"x_title":"","y_title":"","y_format":"currency_zar","y_min":null,"y_max":null,"sort":"data|value_desc|value_asc"},
 "labels":false,"legend":"none|top|bottom|right","colors":["#0B5FFF"]}
{"type":"table","id":"tb1","title":"By plan","query_ref":"x","columns":[{"field":"plan","label":"Plan","format":"text"},{"field":"invoiced"}],"max_rows":15}
{"type":"image","id":"im1","source":{"kind":"brand_logo"}|{"kind":"url","url":"https://..."},"alt":"","fit":"contain|cover"}
{"type":"shape","id":"sh1","shape":"divider|rect|accent_bar","color":"primary|secondary|accent|text|background|#RRGGBB"}
```
Validation on every save: queries against the registry; `series.x` must be the query's time/dimension, `series.y/y2` its measures, `series.series` another
dimension; pie/donut/waterfall take one measure; combo needs `y2`; scatter needs two measures; empty `series.y`/`x`/table `columns` are filled from the query;
tokens statically checked (alias, measure, statistic, format); image URLs must be `https` and pass the SSRF check (the backend never fetches images).
Caps: 60 slides, 12 blocks per slide, 300 blocks, 60 queries, 20 image URLs, 1.5 MB document, 4000 chars notes, 500 decks per tenant, 1000 versions per deck.

### Routes
| Route | Role | Notes |
|---|---|---|
| `GET /decks?status=&q=&limit=&offset=` | viewer | summaries `{id,title,status,version,slide_count,brand_kit_id,created_by,updated_by,updated_at,...}` + `total` |
| `POST /decks` | analyst | `{title, doc?, brand_kit_id?}`; no doc -> starter title slide; default brand kit applied when none given; max 500 decks |
| `GET /decks/{id}` | viewer | full deck incl. `doc`, `version` |
| `PUT /decks/{id}` | analyst | `{title?, doc?, brand_kit_id?, clear_brand_kit?, note?, base_version?}` with header `If-Match: <version>` (or `base_version`). Missing -> 428; stale -> 409 `{detail:{message,current_version}}`. Returns deck + `warnings`. Published decks: admin only |
| `DELETE /decks/{id}` | admin | removes versions and runs |
| `POST /decks/{id}/duplicate` | analyst | "Copy of ..." as a new draft |
| `POST /decks/{id}/publish` | admin | `{published:true|false}` |
| `GET /decks/{id}/versions`, `GET .../versions/{n}` | viewer | insert-only history (every save is a version) |
| `POST /decks/{id}/versions/{n}/restore` | analyst | needs `If-Match`; creates a NEW version with the old content |
| `POST /decks/{id}/refresh` | analyst | runs every block query (deduplicated), stores a snapshot (last 10 kept); the document is NOT modified. `{run_id, doc_version, as_of, queries[], errors{alias:msg}, blocks{block_id:alias}, data{alias:result}}` |
| `GET /decks/{id}/runs`, `GET .../runs/{run_id}` | viewer | snapshots ("data as of ...") |
| `POST /decks/{id}/resolve` | viewer | body `{run_id?, refresh?}`; default = latest snapshot of the current version, else a new one is taken. `refresh:true` needs analyst |
| `GET /decks/{id}/export/json?run_id=&refresh=` | viewer | full bundle for the PPTX exporter |

`resolve` response: `{deck_id,title,version,run_id,stale_data,as_of,theme,slides[],unresolved[],query_errors{}}` where each slide is
`{id,layout,title,subtitle,notes,blocks[]}` with all tokens replaced by display strings. Resolved block fields: text `items[].text`; kpi `label, value,
delta, delta_direction (up|down|flat), delta_is_good, caption`; chart `title, chart_type, series, axis, labels, legend, colors, query_alias`; table
`title, columns, query_alias, max_rows`; image/shape as stored. Chart/table rows are in `data[query_alias]` (export bundle) or the run.

`export/json`: `{format:"omnidome-deck/1", exported_at, deck{id,title,version,status}, doc, brand_kit (with logo_data_url) | null, theme, as_of, run_id,
stale_data, slides[] (resolved), unresolved[], query_errors, data{alias: query result}}`. Build the editable .pptx client-side from `slides` + `data` + `theme`;
show `as_of` as "Data as of ..." in footers.

## 4. Numbers by reference (the integrity rule)

Narrative text may contain a figure only through a token, resolved server-side from stored query results:

```
{{ alias.path | format }}      alias = a deck.queries key, or the id of a chart/table block with an inline query
```
| Path | Meaning |
|---|---|
| `alias.measure` / `alias.measure.total` / `alias.total` | whole-slice total of the measure (default measure = first) |
| `.first .last .prev` | value in first / last / second-to-last row (time series: oldest / latest / previous period) |
| `.first.label .last.label .prev.label` | the row's dimension/period label (e.g. `2026-03-01`) |
| `.delta` / `.delta_pct` | last minus prev / (last-prev)/abs(prev) as a fraction; error if prev is 0 |
| `.max .min .avg` | over rows |
| `.top1.value .top1.label .top1.share` (also `bottomN`, `rowN` where N is 1-based row) | ranked / indexed rows; `share` of total for additive measures |
| `alias.rows` | row count |

Formats: `currency` (R1 234 568), `currency_compact` (R1.2m), `number`, `number_compact`, `percent` (45.7%), `percent0`, `duration` (hours -> min/h/days),
`text`, and `signed_currency|signed_number|signed_percent` (+/-). Omitted format = the measure's own (delta_pct = `signed_percent`).
Unresolvable tokens render as an em dash and are listed in `unresolved`. The placeholder `{{?}}` renders `[add figure]` and is listed too.

AI-written text is sanitised: invalid tokens and every numeric literal (digits, `%`, `R...`, `5k`, "two million") outside a token become `{{?}}` and the
originals are returned in `ungrounded_numbers` (`[{where,literal}]`) / `invalid_tokens`. Years, `Q1-Q4`, `H1/H2`, `FY25`, `4G/5G`, `24/7` and list numbering are allowed.

## 5. AI assist (`/bi/ai`, analyst)

All drafts; nothing is saved. Models via the existing OpenRouter chain. Each call is counted in the credit ledger (feature `bi_ai`, 0 Firecrawl credits) against a
per-tenant daily cap (`BI_AI_DAILY_CALLS`, `429` when reached, counted before the model is called). `GET /ai/usage` (viewer) -> `{ai_calls_today:{used,cap,remaining}}`.
Brief, audience, instruction and all scraped/research/competitor content are passed as delimited untrusted data with injection phrases neutralised; brand voice banned words are
removed from output.

* `POST /ai/outline` `{brief, audience?, tone?, slide_count(2-20), dataset_ids[1-6], research_run_ids?[<=3], competitor_ids?[<=5], campaign_analysis_ids?[<=3], brand_kit_id?}`
  -> `{deck (a valid deck document), dropped{queries[{alias,reason}],blocks[...]}, ungrounded_numbers[], invalid_tokens[], citations[{slide,tag,title,url}], queries_tested, queries_kept, model, ai_calls_today}`.
  Every proposed query is registry-validated **and test-executed**; failures and empty results are dropped with a reason, as are blocks that reference them or fail deck validation.
  Research sources are cited in slide notes (`Source: title - url`, URLs only from stored research runs). Selecting competitors / campaign analyses adds the matching datasets.
* `POST /ai/slide` `{deck_id, slide_id, instruction, include_doc?}` -> `{patch[], slide, dropped[], ungrounded_numbers[], invalid_tokens[], base_version, doc_after?, model}`.
  `patch` is JSON-Patch style (`add /queries/<alias>`, `replace /slides/<index>`); it was validated by applying it to the current document. Apply by saving `doc_after` (or the
  patched doc) with `PUT /decks/{id}` + `If-Match: base_version`. New or changed queries are test-executed; block ids are kept unique.
* `POST /ai/narrative` `{deck_id, slide_id, refresh?}` -> `{insights[{alias,kind,measure,sentence,sentence_resolved,data}], notes, notes_resolved, takeaways[], takeaways_resolved[], ungrounded_numbers[], invalid_tokens[], unresolved[], llm_used, model, as_of, run_id}`.
  Period-over-period, shares, trend direction, outliers and extremes are computed in code (`bi_insights.py`); the model only rephrases finished token sentences. With no model available the
  deterministic sentences are returned (`llm_used:false`). Save `notes` (token form), not the resolved text.

## 6. Tables (created by `init_tables` / `create_all`, new tables only)

`analytics_brand_kits`, `analytics_decks` (tenant, title, status, brand_kit_id, doc JSONB, version, created_by/updated_by, published_by/at),
`analytics_deck_versions` (insert-only, unique per deck+version), `analytics_deck_runs` (data snapshots). AI calls use `analytics_credit_ledger`.

## 7. Environment

| Variable | Default | Meaning |
|---|---|---|
| `BI_QUERY_RATE_PER_MIN` | 120 | per-tenant query rate (process-local sliding window; deck refresh counts one per distinct query) |
| `BI_AI_DAILY_CALLS` | 150 | per-tenant AI calls per day (outline, slide, narrative) |
| `ANALYTICS_ENFORCE_ROLES` | true | role gates (shared with Analytics & AI) |
| `ANALYTICS_ALLOW_HTTP` | false | allow `http://` in SSRF-checked URLs (dev only) |
| `FIRECRAWL_TENANT_MONTHLY_CREDITS` / `_DAILY_CREDITS` | 2000 / 400 | brand-from-URL spend caps (shared ledger) |
| `ANALYTICS_LLM_TIMEOUT` | 90 | model call timeout (s) |
| `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`, `OPENROUTER_FALLBACK_MODELS` | | existing model chain |

## 8. Known gaps

* Rate limiting is per process (like the gateway limiter); multiple replicas multiply the effective limit.
* Cross-service SQL was verified against the model definitions, not against a live PostgreSQL in this change; the SQLite test harness exercises every measure/dimension/grain.
* `social_daily` assumes `attribution='publish'`, `platform='all'` rows (what the analytics sync worker writes).
* Charts, tables and PPTX rendering are the frontend's job; the backend supplies resolved text plus data.
