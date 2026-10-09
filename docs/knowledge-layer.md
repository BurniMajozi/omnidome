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
OKF skills (description/tools only, never `guidance_prompt`), metric facts.

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

## Not covered yet (follow-ups)

Compliance documents (no verified document table), HR (module access defaults exist, no builder), network/IoT alerts, inventory,
call-centre transcripts, finance journals, RICA, subscription/invoice-level cards (only digests and the customer card), entity extraction
for graph edges beyond foreign keys and `scope_key`, per-user scoping of conversation memory, a UI for coverage, orchestrator wiring,
the forecasting service, and any caller that writes `bi_semantic` metric facts from query runs.
