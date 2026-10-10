# Dream state: the nightly self-maintenance of the memory system

Every night (default 02:30 Africa/Johannesburg, per-tenant window, one tenant at a time) the knowledge worker checks that what
the memory system *says* is still true and still useful, and repairs what it can. Code: `services/tenant_memory/knowledge/dream/`.
Admin UI: Agent Management > Memory > **Memory health / Dream state** (`apps/web/components/admin/dream-state.tsx`).

**Rules it never breaks**
* Writes only *derived* data: cards (chunks), embeddings, tags, importance, graph edges, and the `dream_*` log tables. It never
  writes a source (operational) table. The one exception is the existing consolidation/M5 job in phase 6, which is the code that
  already runs from the worker sweep (it archives old memory entries by the M5 rules; it does not delete).
* Every automated change is reversible or logged with before/after in `dream_findings` (`detail.before/after`, plus an `action`
  such as `set_importance` with the old value, or `refresh` that re-renders from the source).
* No LLM ever produces or edits a number. Numbers come from the governed `bi_semantic` queries (via fno_intelligence) only.
* VM friendly: concurrency 1, batches of `DREAM_BATCH_SIZE` (100) with `DREAM_SLEEP_S` (0.5 s) between them, a nightly card budget,
  tenants processed sequentially with `DREAM_TENANT_PAUSE_S`, resumable, kill switch, dry-run. The worker loop does nothing else
  while a night runs (same single-worker design as the sweep); an admin-queued job waits for the night to finish.

## Phases (each idempotent; results persisted per phase, so an interrupted night resumes at the first unfinished phase)

| # | key | what it does |
|---|---|---|
| 1 | `drift` | Re-renders a rotating sample (each card about once per `rotation_days`, plus every card with importance >= 0.75 every night, budget `max_cards_per_night`) from its live source with the **existing builders** and compares the content hash. Changed: refreshed (re-embedded). Source row gone: card tombstoned and its edges removed. Source table unreachable: **not** tombstoned, `source_table_missing` (high) instead. Cards older than their freshness SLA (`retrieval.STALE_AFTER_DAYS`, override per type with `DREAM_STALE_DAYS`) and not verified tonight get tag `dream:stale` (retrieval citations show `stale: true`; the tag is cleared when the card is verified or re-indexed). Graph edges whose origin card no longer exists are deleted; edges pointing at un-indexed cards are only reported. |
| 2 | `embeddings` | Scans stored vectors (rotating cursor, `DREAM_EMBED_SCAN`/night): missing, wrong dimension, NaN/inf, zero, outlier norm (< half or > double the batch median), different embedding model, duplicate vectors (identical text = info, different text = "embedding collapse" medium). Bad or old-model vectors are re-embedded from the stored text, at most `DREAM_REEMBED_PER_NIGHT`. Wrong dimension is reported, never forced (the pgvector column is fixed-size: rebuild). **Semantic drift**: cosine distance between the old and new embedding of every card phase 1 refreshed; beyond `semantic_drift` (0.25) it is recorded. **Canary**: the titles of the tenant's most important unique-titled cards are searched through the real hybrid retriever; the card must be in the top 3. Recall@3 is stored; an alert fires if it falls by `canary_alert_drop` (0.10) vs the previous run or below `canary_recall_floor` (0.60). |
| 3 | `numbers` | Snapshots stored ACTUAL metric facts, asks fno_intelligence to re-run the governed catalog queries (`POST /api/fno/bi/metrics/snapshot`, upserts in place), diffs: a changed value for a closed period beyond `metric_tolerance` (0.5%) is **data drift** (`metric_drift`, with every before/after). A `metric_fact` card that no longer matches its fact is refreshed. Scores past forecasts against actuals that have arrived: sMAPE, MASE vs naive, interval coverage; writes `meta.forecast_accuracy.<metric_key>` facts (`written_by=system`, method `dream:fcacc|smape|mase|cov|n|deg`) and raises `forecast_degraded` when realised sMAPE > max(2x, +10 pts) its own backtest, MASE > 1.5, or coverage < nominal - 30 pts, so the forecaster can reselect. |
| 4 | `relevance` | From `retrieval_log` (+ panel-insight feedback) computes per-card usefulness (cite rate 50%, use rate 20%, thumbs 20%, judge/grounded score 10%). Nudges the stored `importance` by at most +-0.05 a night and +-0.25 from the builder's base; compliance/legal/POPIA/critical cards can only go **up**; absolute floor 0.1; the base is remembered in `dream_card_state` so every step is explainable and reversible. Cards injected often but never cited lose priority; cards never retrieved in `decay_after_days` (60, only if the log is at least that old) decay and get `dream:cold` (archived by the M5 rules in phase 6, never deleted here). Cards the judge repeatedly found out of date are marked stale. Skills are knowledge cards, so their priority is the same mechanism (`skills_ranked` in the report). Near-duplicates (`near_duplicates`, cosine >= 0.90) with the same words but different figures/status become `conflict` review items; identical text is auto-merged (derived card tombstoned) only for `DREAM_AUTO_MERGE_IDENTICAL_TYPES` (`memory_entry`), otherwise it is a review item. |
| 5 | `adjudicate` | JEV, only for borderline items the earlier phases queued: *still current?* (stale card the source could not confirm), *do these two contradict?*, *worth keeping long term?* Acts only at p >= 0.90 or <= 0.10; the middle band stays a human review item. Cached 30 days (same card text = no new call), capped per tenant per night (`jev_max_calls`, `jev_max_cost_usd`), off unless `DREAM_JEV_ENABLED` / tenant setting **and** credentials. Dry run never calls JEV. |
| 6 | `consolidate` | The existing `consolidation.consolidate_tenant`: working -> long-term promotion, expired working memory deleted, near-duplicate memory merge, episodic -> semantic roll-up (uses the OpenRouter summariser already used by the sweep), M5 low-importance archive, tombstone purge. M4/M5 of the orchestrator via `DREAM_HOUSEKEEPING_VIA_ORCHESTRATOR=true` (off: its own scheduler already runs nightly). |
| 7 | `report` | Builds the health report (stored in `dream_runs.report`) and indexes it as card `memory_health:latest` (module `memory`, visible to tenant admins only), so an agent can answer "how healthy is our memory?". New high/critical findings, or a score under 60, create an in-app notification (`event_bus.notify`, category `memory`; `DREAM_NOTIFY=false` to silence). |

**Health score** (0-100, deterministic, `report.health_score`): 100 minus canary recall (30 x miss rate; 5 if unmeasured), stale ratio
(up to 20), invalid vectors (up to 15), open findings (critical 8, high 4, medium 1; up to 15), metric drift (10), degraded forecasts (5), errors (10).

## JEV: privacy and cost

JEV is an **external** service (TypeSafe `api.typesafe.ai/v1/systemone`, or OpenRouter `/api/alpha/decisions`), same credentials and wire
format as `agent_orchestrator/jev_gate.py` (`TYPESAFE_API_KEY`/`JEV_API_KEY`, else `OPENROUTER_API_KEY`). What leaves the platform: a card
title, kind, as_of/age and a <= 700-char excerpt after `textutil.scrub` (e-mail, phone, ID, card/bank numbers, secrets redacted; names are
already initials). Cards that are `private`, or in `DREAM_JEV_EXCLUDE_MODULES` (default `hr,finance,billing,compliance`), are never sent.
No tenant or user ids. The Settings form says this in plain words. Default **off**.

## Endpoints (admin tier; under `/api/v1`, proxied by the web app as `/svc/memory/api/v1`)

| | |
|---|---|
| `GET  /knowledge/dream/status` | last run + health, trend (14 runs), open findings by severity, settings/overrides, next window, JEV + kill-switch state. `ready:false` + note when the dream tables do not exist yet. |
| `GET  /knowledge/dream/runs`, `/runs/{id}` | history; one run with per-phase counts/notes/errors and its report |
| `GET  /knowledge/dream/findings?status&severity&phase&type&run_id&limit` | findings |
| `POST /knowledge/dream/run {dry_run=true, phases?, inline=false}` | queues `knowledge_jobs.kind='dream'` for the worker (`inline:true` runs inside the request; small tenants/debugging). **Dry run is the default.** 409 while the kill switch is on. |
| `POST /knowledge/dream/findings/{id}/resolve {action: accept\|dismiss\|apply}` | `apply` runs the stored fix (refresh, tombstone derived card, clear stale, restore importance, delete edges); findings without an automatic fix return 400 |
| `GET/PUT /knowledge/dream/settings` | per tenant: enabled, window_start/hours, timezone, max_cards_per_night, rotation_days, semantic_drift, canary_*, metric_tolerance, decay_after_days, jev_enabled/max_calls/max_cost_usd/approve/reject (approve >= 0.80, reject <= 0.20: can only be made stricter), stale_days. `null` resets a key to the env default. |

Finding statuses: `open` (needs a human) · `proposed` (dry run: nothing was applied) · `auto_applied` (done, logged) · `applied` / `accepted` / `dismissed`.
A finding recurring with the same `dedupe_key` is folded into one row (`occurrences`); a dismissed one is not re-raised.

## Environment

| var | default | |
|---|---|---|
| `DREAM_ENABLED` | false | schedule on (tenant setting `enabled` overrides). Manual runs work regardless. |
| `DREAM_KILL_SWITCH` | false | emergency stop; checked before each phase and between batches (needs a worker restart to pick up a changed env) |
| `DREAM_WINDOW_START` / `DREAM_WINDOW_HOURS` / `DREAM_TIMEZONE` | 02:30 / 3 / Africa/Johannesburg | |
| `DREAM_TICK_SECONDS` | 300 | how often the worker checks whether a window is open |
| `DREAM_BATCH_SIZE` / `DREAM_SLEEP_S` / `DREAM_TENANT_PAUSE_S` | 100 / 0.5 / 30 | |
| `DREAM_MAX_CARDS` / `DREAM_ROTATION_DAYS` / `DREAM_HIGH_IMPORTANCE` | 1500 / 7 / 0.75 | phase 1 budget |
| `DREAM_RENDER_MAX_CARDS_PER_SOURCE` | 2000 | cards re-rendered per source per night (oldest-updated first; the rest are "unverifiable", never "gone") |
| `DREAM_EMBED_SCAN` / `DREAM_REEMBED_PER_NIGHT` / `DREAM_SEMANTIC_DRIFT` | 2000 / 200 / 0.25 | |
| `DREAM_CANARY_N` / `DREAM_CANARY_FLOOR` / `DREAM_CANARY_ALERT_DROP` | 20 / 0.60 / 0.10 | |
| `DREAM_METRIC_LOOKBACK_DAYS` / `DREAM_METRIC_TOLERANCE` | 100 / 0.005 | |
| `DREAM_METRICS_URL` or `FNO_INTELLIGENCE_SERVICE_URL` | unset | where to ask for the governed snapshot; unset = no data-drift check (honest note in the run) |
| `DREAM_IMPORTANCE_STEP` / `DREAM_IMPORTANCE_DRIFT` / `DREAM_MIN_SAMPLES` / `DREAM_TELEMETRY_DAYS` / `DREAM_DECAY_AFTER_DAYS` / `DREAM_MAX_ADJUSTMENTS` | 0.05 / 0.25 / 5 / 30 / 60 / 300 | |
| `DREAM_CONFLICT_COSINE` / `DREAM_AUTO_MERGE_IDENTICAL_TYPES` | 0.90 / memory_entry | |
| `DREAM_JEV_ENABLED` / `DREAM_JEV_MAX_CALLS` / `DREAM_JEV_MAX_COST_USD` / `DREAM_JEV_APPROVE` / `DREAM_JEV_REJECT` | false / 20 / 0.50 / 0.90 / 0.10 | |
| `DREAM_JEV_EXCLUDE_MODULES` / `DREAM_JEV_EST_COST_USD` | hr,finance,billing,compliance / 0.002 | cost assumed when the provider reports none |
| `DREAM_HOUSEKEEPING_VIA_ORCHESTRATOR` / `DREAM_NOTIFY` | false / true | |

Tables (`knowledge_db`, RLS like the knowledge tables, created by the worker at startup): `dream_runs`, `dream_findings`,
`dream_settings`, `dream_jev_cache`, `dream_card_state`.

## Verified vs not

**Verified** (system Python, `python -m pytest services/tenant_memory -q`; in-memory store, hash embedder, fake renderer/ops/metrics/JEV, no network):
drift refresh/tombstone/missing-table/unverifiable, rotation and cross-night cursor, stale marking/clearing and its retrieval flag, orphan edges;
vector anomaly detection, rate-limited re-embedding, model change, dimension mismatch, collapse, semantic drift, canary recall and drop alert;
metric drift with before/after and card contradiction refresh, sMAPE/MASE/coverage scoring and accuracy facts, degradation flags;
importance bounds, floors, protected cards, decay window, builder reset, telemetry parsing (`retrieval_log` shape and insight feedback), conflicts and identical-merge rules;
JEV thresholds, middle band, per-night call/cost caps, cache, off switch, dry run, privacy exclusions and scrubbing, wire format against a mock transport;
resume after interruption (between and inside phases), dry run changes nothing, tenant isolation, kill switch, windows (local time), once-per-night, report determinism, health score, admin card access, all endpoints incl. validation.

**NOT verified live**
* `PgDreamStore` and the pgvector SQL (scan with row-value comparison, tag array ops, `set_embedding`, dangling edges, DDL/RLS/grants): only the DDL builder is asserted. Run once against a real `knowledge_db` (`KNOWLEDGE_TEST_DB_URL`).
* `SqlOps` against the operational DB (metric facts read, `retrieval_log` and `panel_insight_feedback` joins, `event_bus.notify`) and `SourceCardRenderer` against the real `SOURCES` (only exercised with fake sources and the error classifier).
* The real JEV endpoint (request/response shape copied from `jev_gate.py`; cost field name is an assumption, hence the `DREAM_JEV_EST_COST_USD` fallback).
* The fno_intelligence snapshot call: the service identity headers (`X-Roles: service,admin`, `X-Permissions: analytics.admin`) must be accepted by that endpoint's auth; same for the orchestrator housekeeping call.
* The worker integration end to end (startup schema, the 5-minute tick, a night's wall-clock duration on this VM) and the web section (type-checked only; not rendered).
* Re-embedding after a model change relies on the model being available in Ollama; a changed *dimension* needs the documented rebuild.

## First-night rollout

1. Deploy; the worker creates the dream tables at startup (check its log; `GET /status` shows `ready:true`).
2. Admin panel > Dream state > **Run now (dry run)**. Read the report and the proposed findings. Nothing was changed.
3. Check `retrieval_log` telemetry exists (relevance says "no retrieval telemetry yet" otherwise) and that `FNO_INTELLIGENCE_SERVICE_URL` is set for the knowledge worker if you want the data-drift check.
4. Run once for real from the panel (Confirm: apply changes) during the day on one tenant; review `auto_applied` findings, try Re-apply/revert on one.
5. Turn on the schedule for that tenant (Settings > Run every night), leave JEV off for the first week. Watch the 02:30 run's health score and canary recall.
6. Enable JEV for one tenant with a low cap (`jev_max_calls` 10) only after reading the privacy paragraph above; keep it off for tenants whose cards must not leave the platform.
7. Roll out tenant by tenant. `DREAM_KILL_SWITCH=true` plus a worker restart stops everything.
