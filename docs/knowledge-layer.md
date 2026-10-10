# Knowledge layer (RAG for the platform)

Operational data is turned into markdown **knowledge cards**, embedded **locally**, and retrieved with hybrid search so agents,
the orchestrator and BI Studio (Deck Studio) get grounded context. Code: `services/tenant_memory/knowledge/`.

## Design principle: vectors give context, SQL gives numbers

Cards carry **context, history and narrative**. They may contain figures "as of" a date, but **aggregate numbers in answers/decks
come from governed SQL** (the BI semantic layer, `services/fno_intelligence/bi_semantic.py`). Every citation exposes `as_of`,
`age_days` and `stale`; the context pack tells the model to name the card and its date and to use governed queries for reportable
figures. Metric facts (below) bridge the two: the number is stored deterministically *and* referenced to its governed query.

## Architecture decisions

| Decision | Why |
|---|---|
| Separate `knowledge_db` (pgvector/pgvector:pg16, verified tag) | Main DB is `postgres:15-alpine` without pgvector. Derived, fully rebuildable data stays out of the system of record. No published port, own volume, 512 MB limit. |
| Indexer is a **module inside tenant_memory**, run as a second compose service (`knowledge_indexer`, same image, different command) | Shares auth/entitlements, card/memory code and the Dockerfile; no new image to build on a fragile VM. Embedding CPU load stays out of the 2 API workers agents call every turn. A separate service would only add a build and a deploy. |
| Local embeddings: Ollama `nomic-embed-text`, 768-dim, CPU | Tenant text never leaves the platform. Only Firecrawl goes to the web. Dimension is checked on every response and at migration. |
| Vector SQL behind `KnowledgeStore` | `store_pg.PgVectorStore` (prod) / `store_memory.MemoryStore` (unit tests). |
| Short-term memory in Postgres (`tenant_memory_working`) | No Redis in this stack. TTL + purge by the consolidation job. |
| Tenant isolation twice | Explicit `tenant_id` filter in every statement **and** forced row-level security (`app.tenant_id` set per transaction; the app connects as non-superuser `knowledge_app`). |
| Graph = `knowledge_edges` + recursive CTE | Edges come from foreign keys (customer-subscription-invoice-ticket-campaign...). Depth capped (`GRAPH_MAX_DEPTH`, max 4), cycle-safe. No Apache AGE. |

## Data model (knowledge_db)

`knowledge_chunks` (tenant_id, id, source_type, source_id, chunk_no, source_ref JSON incl. `deep_link`, module, title, markdown,
content_hash, embedding vector(768), tsv, visibility private|team|tenant|system, required_roles[], required_permission, owner_id,
as_of, valid_to, importance, tags, created_at/updated_at, deleted_at). Unique `(tenant_id, source_type, source_id, chunk_no)`;
HNSW (cosine, m=12, ef_construction=48, partial on live rows), GIN on tsv and tags, btree `(tenant_id, module, source_type)`.
Also `knowledge_edges`, `knowledge_watermarks`, `knowledge_failures`, `knowledge_jobs` (admin queue). Migrations are idempotent and
run under an advisory lock by the worker. `content_hash` is computed over the card **minus volatile frontmatter** (`as_of`) plus the
model name, so a rebuild that changes only a timestamp never re-embeds.

Cards: YAML frontmatter (`source`, `source_id`, `module`, ids, `as_of`, `tags`) + readable body with `[[kind:id]]` links.

## Sources covered (verified against models/schema)

customers (+subscriptions, balance, last tickets, tags), leads, deals, pipeline digests, billing digests (month x segment),
support tickets (public replies only), marketing campaigns, social analytics digests (month x platform), BI research runs,
competitors (latest snapshot + changes + source URLs), campaign analyses, tenant memory entries, memory summaries,
OKF skills (description/tools only, never `guidance_prompt`), metric facts - plus the broad-coverage sources in the table further down.

PII minimisation: per-builder allow-lists (`KNOWLEDGE_FIELDS_<SOURCE>=a,b,c` can only **narrow**), a hard `NEVER_INDEX` set
(email, phone, id_number, address, passwords/tokens/keys, bank/card, Paystack refs...), people shown as "Thandi M.", all free text
scrubbed (emails, phones, SA ID numbers, card/account numbers, credentials) and clipped. Module visibility: billing, finance and hr cards
are `team` with role tags (defaults in `cards/base.py`, override with `KNOWLEDGE_MODULE_ACCESS` JSON). Tenant/platform admins see
role-tagged cards; **private** means the owner only, admins included. Re-run with `force` after changing access settings.

## Indexing

Incremental by `(updated_at, id)` keyset watermark per tenant+source; customers also refresh when their invoices/tickets/subscriptions
change; a daily full reconcile tombstones rows that vanished at the source (tombstones are purged after `KNOWLEDGE_TOMBSTONE_DAYS`=30).
Idempotent upserts by content hash, embeddings reused by hash. Gentle: `INDEX_BATCH_SIZE`, `INDEX_CONCURRENCY` (1-2), `INDEX_SLEEP_S`,
DB sessions closed before embedding. Per tenant+source advisory lock. Cross-service reads use explicit column lists, a tenant filter
and `begin_nested()`. One bad card is recorded in `knowledge_failures` and skipped; an embedding outage stops the run cleanly without
moving the watermark.

## Retrieval

`POST /api/v1/knowledge/search`: vector + full-text (OR semantics) fused by Reciprocal Rank Fusion (k=60), bounded importance/recency
boost, identical-content dedupe, MMR (lambda 0.7; cosine when embeddings are present, word-overlap otherwise), optional graph expansion,
role/tenant filtering in SQL and again in Python. If Ollama is down the vector leg is dropped and `degraded` says so.
`POST /api/v1/knowledge/context {query, budget_tokens, modules[]}` returns a token-budgeted pack with numbered citations
(`source_type, source_id, title, as_of, score, deep_link, stale, ref`). `GET /api/v1/recall?mode=hybrid` is the existing M1 recall plus a
`knowledge` list (default `mode=keyword` is unchanged). `GET /api/v1/knowledge/graph?source_type&source_id&depth`.
These are the hooks for the orchestrator (`knowledge.context`, `memory.recall`); the orchestrator is not rewired here.

## Memory tiers

* **Short-term**: `POST/GET/DELETE /api/v1/memory/working[/{session_key}]`, `POST .../{id}/pin`. Kinds turn|state|context_ref|note, TTL
  `WORKING_MEMORY_TTL_MINUTES` (240). Repeats of the same note count up instead of duplicating.
* **Long-term**: episodic (`tenant_memory_entries`), semantic (`tenant_memory_summaries`), procedural (OKF skills) - all embedded.
* **Consolidation** (nightly per tenant, or `POST /knowledge/admin/consolidate {dry_run}`): promote working items (pinned, high/critical,
  or seen >= 3 times) to entries; merge near-duplicate entries (cosine >= 0.97, keep most important/earliest, archive the rest with
  `merged_into`); roll up old episodic entries into semantic summaries with provenance `source_entry_ids` (OpenRouter chain, deterministic
  fallback) - runs `ROLLUP_GRACE_DAYS` after M5 so it is a safety net; decay retrieval importance and archive old low-importance entries
  (M5 env `MEMORY_ROLLUP_DAYS`, `MEMORY_LOW_IMPORTANCE_DAYS` honoured).
* **Forget**: `POST /knowledge/admin/erase {source_type?, source_id?, module?, entire_tenant?, confirm:"ERASE"}` hard-deletes chunks, edges
  and bookkeeping (POPIA erasure, offboarding). Delete the operational rows in their own service too, or the next index would recreate them.

## Metric facts (numbers connected to memory)

Table `tenant_metric_facts` (main DB, created by `init_tables`): metric_key, label, dimensions JSON, period_start/end, grain, value, unit,
kind actual|forecast|target, lower/upper bound + interval_level, model_name/model_version (required for forecasts), method, confidence,
`source_query` (a bi_semantic `QuerySpec`) + `source_query_key`, as_of, `written_by`. **Only deterministic writers**: DB CHECK limits
`written_by` to `bi_semantic | forecast_run | system`; `POST /api/v1/metrics/facts` needs the `metrics.write` permission (platform admin
or a service identity), never granted to agent tools; validation forbids forecasts without a model, actuals from forecast runs, etc.
Each fact becomes a card: *"Revenue, March 2026: R1,080,000.00, +8.0% vs February 2026 ... Source query: dataset billing, measures
[revenue], query key ..."*, embedded for retrieval. Agents must re-fetch the exact value through the governed query tool using the
referenced spec. The forecasting service that writes `forecast` rows does not exist yet.

## Environment

| Var | Default | Notes |
|---|---|---|
| `KNOWLEDGE_DB_PASSWORD` | none | Owner password for `knowledge_db`. **Empty = container refuses to start (fail closed).** Use hex (`openssl rand -hex 24`). |
| `KNOWLEDGE_APP_PASSWORD` | none | Password for the RLS-bound `knowledge_app` role (created by the worker's migration). |
| `KNOWLEDGE_DB_URL` | empty = layer off | `postgresql://knowledge_app:<app pw>@knowledge_db:5432/knowledge` (tenant_memory + worker) |
| `KNOWLEDGE_DB_ADMIN_URL` | falls back to KNOWLEDGE_DB_URL | `postgresql://knowledge_owner:<db pw>@knowledge_db:5432/knowledge` (worker only; migrations) |
| `EMBEDDING_MODEL` / `EMBEDDING_DIM` | nomic-embed-text / 768 | Changing dim needs a rebuild (drop table, reindex). Prefixes `EMBEDDING_DOC_PREFIX/QUERY_PREFIX` default to nomic's. |
| `OLLAMA_BASE_URL` | http://ollama:11434 | |
| `INDEX_BATCH_SIZE` 50, `INDEX_CONCURRENCY` 1, `INDEX_SLEEP_S` 1.0, `INDEX_POLL_SECONDS` 30, `INDEX_RECONCILE_HOURS` 24, `EMBED_BATCH_SIZE` 16 | | VM friendliness |
| `HNSW_M` 12, `HNSW_EF_CONSTRUCTION` 48, `HNSW_EF_SEARCH` 40 | | small on purpose |
| `KNOWLEDGE_TENANTS` | all active | comma list to restrict the worker |
| `KNOWLEDGE_MODULE_ACCESS`, `KNOWLEDGE_FIELDS_<SOURCE>` | | see above |
| `KNOWLEDGE_SOURCES` | empty = all | comma list of source names to index (`invoices,leads`), or `all,-hr_org` to remove some. Names: see the broad-coverage table and `GET /knowledge/admin/coverage` (`sources_available`). Applies to the sweep, manual reindex and coverage. |
| `KNOWLEDGE_DIGEST_MONTHS` | 3 | months looked back by the monthly digest sources (1-24) |

## Start it (exact commands)

```bash
# 1. secrets in the gitignored .env (never commit): KNOWLEDGE_DB_PASSWORD, KNOWLEDGE_APP_PASSWORD, KNOWLEDGE_DB_URL, KNOWLEDGE_DB_ADMIN_URL
# 2. embedding model (ollama service already exists; the tests never download anything)
docker compose up -d ollama
docker compose exec ollama ollama pull nomic-embed-text
# 3. store + worker (profile "knowledge"; start one at a time on the fragile VM)
docker compose --profile knowledge up -d knowledge_db
docker compose --profile knowledge up -d --build knowledge_indexer tenant_memory
# 4. backfill everything (or just let the worker sweep): POST /api/v1/knowledge/admin/reindex {"full": true}  (admin)
# 5. watch: GET /api/v1/knowledge/admin/coverage   |   docker compose logs -f knowledge_indexer
```

## Tests

`python -m pytest services/tenant_memory -q` (no network, no DB; fake `HashEmbedder`, in-memory store). Optional real-server test:
`KNOWLEDGE_TEST_DB_URL=... EMBEDDING_DIM=64 python -m pytest services/tenant_memory/knowledge/tests/test_pg_integration.py`.

## Broad-coverage sources (added 2026-10-10)

All verified against the owning service's models (and, where the same table is also in `config/master_schema.sql` with an older
shape - `iot_devices`, `inventory_*`, `rica_verifications`, `employees`, `journal_entries`, `knowledge_base` - only columns present
in both shapes or added by that service's startup migration are read). Code: `cards/sources_ext.py` (readers), `cards/builders_ext.py`
(cards). Each reader uses explicit column lists, an explicit tenant filter on every query/join, `begin_nested()`, and a
`to_regclass` guard: a table that does not exist yet (its service never started) yields an empty page, and reconcile **refuses** to run
against a missing table so it can never tombstone indexed cards. Sources run one at a time, in `INDEX_BATCH_SIZE` pages, with the
usual sleep between them; digests are recomputed windows (last `KNOWLEDGE_DIGEST_MONTHS` months) deduplicated by content hash.
The worker sweep now isolates failures per source (a broken source is recorded in `knowledge_failures` and the rest continue).
`GET /knowledge/admin/coverage` lists every source (`sources_available`: name, module, card types, enabled, snapshot) and the skipped list
(`sources_skipped`); `POST /knowledge/admin/reindex {"sources":[...]}` accepts any of the names below.

| Source name (`KNOWLEDGE_SOURCES`) | Card types | Visibility / role tags | Notes and exclusions |
|---|---|---|---|
| `compliance_documents` | `compliance_document` | team: compliance, compliance_officer, legal, risk | OCR text split into `## Section N` blocks, legal wording kept as written (identifiers scrubbed only), capped at 40k chars. NOT read: file path, uploader, extracted_data JSON, file size |
| `compliance_obligations`, `compliance_breaches` | `compliance_obligation`, `compliance_breach` | same | NOT read: responsible person, evidence_provided, regulator reference numbers |
| `compliance_cipc`, `compliance_tax_returns`, `compliance_tax_registrations` | `cipc_filing`, `tax_return`, `tax_registration` | same | NOT read: tax/registration numbers, SARS/CIPC/filing/confirmation references |
| `compliance_emp201` | `emp201` | team: compliance + finance + hr_manager | company totals per period only. NOT read: PRN, receipt reference, preparer, payroll run ids, assumptions |
| `compliance_consents` | `consent_digest` | compliance roles | POPIA consents as counts per purpose. NOT read: data-subject name/id, notes. DSAR table skipped (identities) |
| `hr_org` | `hr_org` | team: hr, hr_manager, hr_admin | headcount per department x role title of active staff. No names |
| `hr_training` | `training_course` | hr roles | course facts + aggregate enrolled/completed. NOT read: individual enrolments, progress, scores |
| `hr_company_kpi` | `company_kpi` | hr roles | company-level objectives for a fiscal year (budget vs actual). Individual KPI sheets are not indexed |
| `network_services` | `network_service` | tenant | status, technology, speed, city/province, FNO provider, customer link. NOT read: street address, GPS, FNO order/account ids, ONT serial |
| `network_sla_digests`, `network_incident_digests` | `sla_digest`, `incident_digest` | tenant | monthly SLA breach counts/duration, FNO SLA measurement breaches/penalties, notification counts by trigger/severity |
| `network_fleet` | `fleet_digest` | tenant | counts by type/manufacturer/model/status + "not seen in 24h" for network and IoT devices. NOT read: serials, MACs, IPs, firmware strings, credentials, attributes. IoT uses only columns common to both table shapes |
| `rica_digests` | `rica_digest` | tenant | monthly verification and RICA-flow status counts. NOT read: ID numbers, names, addresses, job ids, response payloads |
| `inventory_products`, `inventory_packages` | `product`, `package` | tenant | catalogue (SKU, name, category, RRP, active). NOT read: cost price, markup, barcode, weight, preferred supplier |
| `stock_levels`, `stock_movement_digests` | `stock_digest`, `stock_movement_digest` | tenant | per warehouse levels + lowest-vs-reorder products; movements per month by type |
| `purchase_orders`, `inventory_suppliers` | `purchase_order`, `supplier` | team: inventory, inventory_manager, procurement, procurement_officer, finance, finance_manager | NOT read: supplier contact person/e-mail/phone/address/tax id/spend limit/notes, creator/approver ids, send metadata, approval hash. Suppliers carry PO count/total |
| `finance_chart`, `journal_digests` | `chart_of_accounts`, `journal_digest` | team: finance, finance_manager, accountant | COA code+name; posted journals per month by account group and busiest accounts; line descriptions and references are not read |
| `invoices`, `subscriptions`, `payment_arrangements`, `dunning_digests` | `invoice`, `subscription`, `payment_arrangement`, `dunning_digest` | team: billing, finance, billing_admin, finance_manager, accountant | invoice lines (<= 12), customer link. Drafts/voided have no card. NOT read: invoice notes, payment refs, Paystack codes/tokens, subscription metadata, arrangement notes |
| `call_sessions` | `call_session` | team: call_center, call_center_agent, call_center_manager, supervisor | transcript scrubbed and indexed **only** when `recording_consent` is `given`/`not_required` and the retention window has not passed (gate applied in SQL, so other transcripts never leave the DB). Agents shown as initials. NOT read: recording URL, live transcript, provider/external ids, phone numbers |
| `call_center_digest` | `call_center_digest` | same | queue state, agent CSAT/MTTR (initials), monthly call volume |
| `kb_articles` | `kb_article` | tenant | published articles of the tenant only (the shared system-tenant KB is not duplicated per tenant). `knowledge_base` has no `updated_at`: edits are picked up by the daily full reconcile |
| `retention_journeys`, `retention_offers`, `lifecycle_summaries`, `cancellation_digests` | `retention_journey`, `retention_offer`, `lifecycle_summary`, `cancellation_digest` | tenant | cancellation digest = reasons, workflow states, offer outcomes per month. NOT read: customer ids/snapshots/features, router serials, FNO references, internal notes |
| `churn_batches` | `churn_batch` | team: retention, customer_success, sales_manager, support_manager, manager | per completed batch (last 120 days): level counts, reasons, top 15 at-risk customers as `[[customer:id]]` links. NOT read: customer name, contact data, risk factor payloads |
| `portal_pages` | `portal_page` | tenant (public copy) | published pages only; visible copy of the published version. NOT read: custom CSS/JS, URLs, images, SEO/share tokens |
| `portal_submission_digests` | `portal_submissions_digest` | tenant | monthly counts per page/utm source of **consented** submissions only. NOT read: form payload, IP hash, consent text |
| `audience_segments` | `audience_segment` | tenant | name, description, rules, member count (`marketing_audience_segments` has no `updated_at`: refreshed on the daily reconcile) |

Graph edges added (foreign keys only, existing edge writer): invoice->customer/subscription/credited invoice, subscription->customer,
payment_arrangement->customer, network_service->customer, call_session->customer, purchase_order->supplier/product, package->product,
stock_digest->low-stock product, churn_batch->customer, retention_journey->offers, portal digest->page. The existing
campaign->audience_segment edge now resolves to the new segment cards.

Role tags are defaults in `cards/base.py` `DEFAULT_MODULE_ACCESS` (keys `compliance`, `compliance.payroll_tax`, `call_center`,
`inventory.procurement`, `retention`, `hr`, `billing`, `finance`; a card can name a finer `access_key`) and can be overridden with
`KNOWLEDGE_MODULE_ACCESS`; re-run with `force` after changing them. Admins always pass.

### Skipped (and why)

| Source | Reason |
|---|---|
| Communication / AgentMail threads | No thread or summary table: `agent_emails` holds only raw bodies and the agent's raw reply, so nothing safe to index. Raw e-mail bodies are never indexed |
| HR individual records (payroll, payslips, performance reviews, employee KPI sheets, disciplinary, exits, leave, schedules, employees' own rows) | Named-individual or sensitive data; no tenant-visibility marker for the talent module was found, so HR cards default to hr/admin roles and contain org facts only |
| Compliance DSAR / anonymisation logs | Identify data subjects; only the consent digest is indexed |
| Campaign -> lead edges | No verified foreign key (leads carry a free-text `source`; portal submissions carry `utm_campaign` text, not an id) |
| Anything not listed | Orders, store, loyalty, web analytics etc. were not verified and are not indexed |

All of the above is verified against code and unit-tested with fakes; it has **not** been run against a live database. First reindex per
source with `POST /knowledge/admin/reindex {"sources":["<name>"],"full":true}` and watch `knowledge_failures` and `GET /knowledge/admin/coverage`.

## Not covered yet (follow-ups)

Entity extraction for graph edges beyond foreign keys and `scope_key`, per-user scoping of conversation memory, a UI for coverage,
orchestrator wiring, the forecasting service, any caller that writes `bi_semantic` metric facts from query runs, and the unverified tables above.
