# Panel insights engine and JEV for retrieval

Two things live here: the **insights engine** that writes every panel's "AI recommendations" and the executive overview,
and **JEV for retrieval/augmentation** that makes the agents' memory retrieval judged, bounded and measurable.
Code: `services/agent_orchestrator/insights/**`, `services/agent_orchestrator/jev_retrieval.py`.

## 1. Insights engine

One pipeline for every panel, run with the **signed identity of the person looking at the panel**, so the briefing is
personal (their role, their panel access, their own tasks / escalations / schedule) and grounded (company knowledge cards and
deterministic metric facts), never hard-coded.

```
POST /api/insights/panel {module, scope?, refresh?}
   |  access: memory service /knowledge/access decides which panels the caller may open (403 + allowed list otherwise)
   |  gather (all signed calls to tenant_memory, all access-filtered there):
   |     E# knowledge cards for the panel          POST /knowledge/search       (metric_fact cards excluded here)
   |     F# metric facts + forecasts               POST /knowledge/search source_types=[metric_fact], per catalog metric
   |     P# the caller's own open items            POST /knowledge/personal/day  (only the caller; filtered to the panel)
   |     S  matching skills                        skills_runtime.select_for_turn (feature-detected; absent = none)
   |  fingerprint = hash(evidence ids + as_of + values + roles)   -> cache hit / invalidation
   |  narrative: LLM (INSIGHTS_MODEL | BI_AI_MODEL | shared OpenRouter chain), strict JSON, numbers only as {{F2}} tokens
   |  validate: tokens -> governed text, unsupported figures stripped, recs without supplied evidence dropped, links limited
   |  verify: JEV groundedness over the resolved text vs the supplied evidence; weak -> retry once with critique; failed -> template
   |  store (Postgres, memory fallback) and serve
```

### Endpoints (web proxy: `/api/orchestrator/insights/...`)

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/insights/panel` | `{module, scope?, refresh?}`; `refresh` is `false`, `true` (forced, rate limited) or `"background"` (serve cache now, regenerate behind it) |
| GET | `/api/insights/panel?module=&scope=` | the stored briefing, no generation; `{"available": false}` when none |
| GET | `/api/insights/modules` | panels the caller may open |
| POST | `/api/insights/{id}/feedback` | `{verdict: helpful\|not_helpful\|dismissed\|acted, rec_id?, note?}` |

Modules: `overview, sales, billing, crm, retention, support (alias service), marketing, finance, network, call_center, inventory,
iot, compliance, hr (alias talent), analytics, products`. `overview` needs no particular panel; its evidence is still limited to
what the caller may read. Unknown module: 404 with the valid list. No access: 403 `{message, module, allowed: [...]}`.

### Response

```jsonc
{
  "id": "uuid", "module": "sales", "label": "Sales", "scope": "",
  "summary": "3-6 sentences; every figure came from a fact token",
  "recommendations": [{
    "id": "rec_ab12cd34ef", "title": "...", "why": "1-3 sentences",
    "priority": "high|medium|low", "effort": "...", "impact": "...", "owner_hint": "Collections lead",
    "suggested_action": {"kind": "open|draft_task|ask_agent", "label": "...", "link": "/dashboard?...", "draft": "...", "executes": false},
    "confidence": 0.8,
    "evidence": [{"id": "card:deal:...", "ref": "E1", "kind": "card|fact|personal", "title": "...", "as_of": "...", "deep_link": "...", "stale": false}]
  }],
  "kpis": [{"id": "card:metric_fact:...", "label": "...", "value": "R1,250,000.00", "delta": "+8.5% vs August 2026", "period": "September 2026", "kind": "actual|forecast", "as_of": "..."}],
  "risks": [{"text": "...", "evidence": [...]}],
  "evidence": [...every item the model was shown...],
  "generated_at": "...", "as_of": "latest data date", "stale": false, "degraded": null, "degraded_reasons": [],
  "model": "anthropic/claude-haiku-4.5", "source": "llm|template|none", "used_skills": ["Pipeline review brief"],
  "verified": true, "verification": {"status": "verified|weak|failed|unavailable|skipped", "probability": 0.93},
  "empty": false, "empty_reason": null, "cached": false, "age_s": 0, "refreshing": false, "notice": null
}
```

### Guarantees (enforced in code, covered by tests)

* **Numbers are never typed by the model.** The evidence lists each fact with a token (`{{F3}}`, `{{F3.delta}}`, `{{F3.period}}`,
  `{{P.overdue_tasks}}`); the engine substitutes the platform-formatted text from the metric-fact card. A literal figure in the
  model's prose that is not in the supplied evidence (or a small count <= 10 without currency/percent) removes that sentence; in a
  title it removes the recommendation. KPIs are built from facts directly, not from model output.
* **No evidence, no recommendation.** Each recommendation must cite at least one evidence ref that was actually supplied.
* **Drafts only.** `suggested_action.executes` is always false. The UI offers: a deep link into the panel (links are restricted
  to `/dashboard...` paths taken from the evidence), "Ask an agent" (opens the agent chat with a draft prompt), and "Draft task"
  (asks for confirmation before posting to `/api/chat/tasks`).
* **Access.** The memory service's panel access decides; if it cannot answer the engine falls back to the verified identity
  (admins: all; otherwise the modules in the token; otherwise none).
* **Degradation.** LLM down, unusable output, validation removing everything, daily budget used, or failed verification each
  produce a deterministic template briefing (facts + counts + simple rules, all citing evidence) with `degraded` saying why. If the
  knowledge layer is down or nothing is indexed, the response is `empty: true` with an honest `empty_reason`; the model is not called.
* **Cache.** Per (tenant, user, module, scope, role-set). A hit needs same fingerprint **and** age < `INSIGHTS_CACHE_TTL_MIN`. If the
  evidence changed it regenerates, but not more often than `INSIGHTS_MIN_REGEN_S`. Concurrent requests share one generation.
  Forced refresh is limited to `INSIGHTS_REFRESH_PER_10MIN` per person. Dismissed / not-helpful recommendations stay hidden for 14 days.
* **Budget.** `INSIGHTS_DAILY_LLM_CALLS` model calls per tenant per day (table `panel_insight_budget`).

### Feedback loop

Verdicts are stored in `panel_insight_feedback` (own insights only) and written to tenant memory as a **private** entry
(`source_type=insight_feedback`, importance acted=high, helpful=normal, not_helpful/dismissed=low, metadata with the insight,
rec and evidence ids) so priorities can be learned. Nothing leaves the tenant. If memory is unreachable the feedback is still
stored (`memory_signal: false`).

### Tables (created on first use)

`panel_insights(cache_key pk, id, tenant_id, user_id, module, doc jsonb, evidence_hash, generated_at)`,
`panel_insight_feedback(id, tenant_id, user_id, insight_id, rec_id, module, verdict, note, created_at)`,
`panel_insight_budget(tenant_id, day, calls)`. If the database is unreachable the cache and budget fall back to process memory.

## 2. JEV for retrieval and augmentation

JEV (TypeSafe "Jev System One") is a calibrated evaluator. It is already used for tool-call gating, triage and answer verification
(`jev_gate.py`). `jev_retrieval.py` adds four things.

1. **Relevance judge** (analytic questions only, not every turn). After `knowledge/context` returns the pack, the cards are scored
   in **one** JEV request with three propositions per card: *answers_question*, *is_current*, *applies_to_this_user*.
   `score = answers * (0.5 + 0.5*current) * (0.6 + 0.4*applies)`. Cards with `is_current < 0.25` or `score < JEV_RETRIEVAL_THRESHOLD`
   (0.35) are dropped; the rest are re-ordered by score (original `[n]` labels kept). Judgements are cached 1 h by
   (tenant, question, card id + as_of + excerpt). A proposition JEV does not answer counts as neutral-positive. Customer-facing
   agents are never judged (their card text is not sent out).
2. **Augmentation policy** from JEV's confidence (mean of the top three kept scores): >= 0.6 answer; otherwise widen once
   (graph neighbours + a 1.5x pack, then re-judge); still < 0.6: if < 0.3 and the question is <= 5 words, add a trusted note telling
   the agent to ask ONE clarifying question; otherwise add a note to answer with explicit uncertainty. The notes sit outside the
   untrusted knowledge wrapper.
3. **Answer verification sees the knowledge pack.** Before this change `verify_agent_response` received only the last five tool
   results, so an answer correctly based on an injected card looked ungrounded (log: `critique_and_retry (grounded_prob=0.05)`).
   Agents now pass `evidence` (the injected knowledge + memory blocks, scrubbed, <= 10 items x 450 chars) and the proposition says
   claims may be supported by `tool_records` **or** `evidence`.
4. **Telemetry** (`retrieval_log`, below).

All JEV calls here go through `jev_retrieval.jev_call`: same credentials/endpoint as the tool gate, 6 s timeout (12 s for the
insights check), circuit breaker (3 consecutive failures open it for 60 s), per-tenant daily budget (process memory), and every
failure returns "no judgement": **a turn is never blocked or failed by JEV**.

### Privacy: what leaves the platform

JEV is an external API (`api.typesafe.ai`, or OpenRouter `/api/alpha/decisions` when no TypeSafe key is set). For judging and
insights verification the request contains: the user's question text (<= 600 chars), the caller's role names, and per card: title,
module, as_of, and an excerpt <= 450 chars after scrubbing (markup removed, e-mail addresses and runs of 9+ digits masked).
For the insights check it contains the generated briefing text and the same kind of scrubbed evidence excerpts, including the
titles of the person's own tasks/escalations that the briefing cites (scrubbed the same way). Tenant and user ids are **not** sent.
`retrieval_log` stays in the platform. **`JEV_DATA_EGRESS=false` disables every JEV call that carries tenant data** (judge,
insights check, answer verification); the platform then relies on its local checks (citation and number validation, templates).
`JEV_RETRIEVAL_ENABLED=false` turns off the judge/augmentation only. The tool gate keeps its existing behaviour.

### `retrieval_log` (read by the nightly dream-state job)

One row per answered agent turn that went through knowledge grounding. No query text is stored.

| column | type | meaning |
|---|---|---|
| `id` | uuid pk | |
| `tenant_id` | uuid | |
| `user_id` | text | caller (null for system runs) |
| `agent_type` | text | |
| `conversation_key` | text | conversation id when there is one |
| `query_hash` | text | first 32 hex of sha256 of the normalised question |
| `query_chars` | int | length only |
| `analytic` | bool | whether the question qualified for judging |
| `cards` | jsonb | `[{card_id, module, rank, retrieval_score, judge: {answers_question, is_current, applies_to_user, score} \| null, used, cited}]`; `used` = injected into the prompt, dropped-by-judge cards have `used:false`; `cited` = the answer referenced the card id or its `[n]` label |
| `n_retrieved`, `n_kept`, `n_cited` | int | |
| `jev_status` | text | `judged` or `skipped:<reason>` (`disabled`, `egress_off`, `budget`, `breaker_open`, `timeout`, `http_NNN`, `not_analytic`, `no_credentials`) |
| `jev_confidence` | real | augmentation confidence |
| `action` | text | `answer\|widen\|clarify\|uncertain` |
| `widened` | bool | |
| `grounded_prob` | real | answer verifier's grounded probability for the final answer |
| `verdict` | text | verifier action (`accept\|critique_and_retry\|flag_for_review`) |
| `created_at` | timestamptz | index `(tenant_id, created_at desc)` |

Write: `jev_retrieval.write_retrieval_log(row)` / `log_turn_background(...)` (fire and forget; failures are logged and dropped).
Suggested learning signals: cards often `used` but never `cited` lose priority; cards `cited` in answers with high `grounded_prob`
gain; cards dropped by the judge as `is_current < 0.25` are candidates for re-indexing or expiry.

## 3. Is JEV still running?

Yes, in the orchestrator, using the **TypeSafe key** (`TYPESAFE_API_KEY` from the gitignored `.env`, read by `Settings`; compose
passes `.env` through `env_file`) against `https://api.typesafe.ai/v1/systemone`, model `jev-latest`. If that key were absent the
code would use `OPENROUTER_API_KEY` against OpenRouter's `/api/alpha/decisions` with model `typesafe/jev-1.13`. The off switch is
`JEV_GATE_ENABLED` (setting `jev_gate_enabled`).
Routing: `triage_inbound_inquiry` / `route_agent_intent` (agent routing + frustration/churn/escalation) in `jev_gate.py`; tool
gating in `evaluate_tool_call` (shadow mode: even high-confidence approvals still go to a human unless
`JEV_AUTO_APPROVAL_ENABLED=true`); answer verification in `Agent.run` (skipped for the mock LLM). The verification result is
returned and logged; it does not currently rewrite the answer.

## 4. Environment

| var | default | meaning |
|---|---|---|
| `INSIGHTS_ENABLED` | true | master switch (503 when off) |
| `INSIGHTS_MODEL` | (BI_AI_MODEL) | model for the briefing; `BI_AI_MODEL` defaults to `anthropic/claude-haiku-4.5`; empty = shared OpenRouter chain |
| `INSIGHTS_CACHE_TTL_MIN` | 30 | cache lifetime |
| `INSIGHTS_MIN_REGEN_S` | 60 | minimum gap between regenerations when evidence changes |
| `INSIGHTS_DAILY_LLM_CALLS` | 200 | model calls per tenant per day |
| `INSIGHTS_REFRESH_PER_10MIN` | 6 | forced refreshes per person |
| `INSIGHTS_VERIFY_ENABLED` | true | JEV check of the briefing |
| `INSIGHTS_VERIFY_MIN_GROUNDED` / `_FAIL_BELOW` | 0.6 / 0.4 | verified threshold / below this (after one retry) falls back to the template |
| `INSIGHTS_LLM_TIMEOUT_S`, `INSIGHTS_SOURCE_TIMEOUT_S` | 60 / 6 | |
| `INSIGHTS_STORE` | pg | `memory` keeps everything in process |
| `JEV_RETRIEVAL_ENABLED` | true | relevance judge + augmentation |
| `JEV_DATA_EGRESS` | true | false = no tenant data to JEV at all |
| `JEV_RETRIEVAL_THRESHOLD` | 0.35 | minimum judged score |
| `JEV_RETRIEVAL_TOP_N` | 8 | cards judged per turn |
| `JEV_RETRIEVAL_TIMEOUT_S` | 6 | |
| `JEV_RETRIEVAL_DAILY_CALLS` / `JEV_INSIGHTS_DAILY_CALLS` | 300 / 200 | per-tenant JEV budget (per process) |
| `JEV_RETRIEVAL_TELEMETRY` | true | write `retrieval_log` |

## 5. Web

`apps/web/lib/insights-api.ts` (types, calls, shared store + `useInsights`) and `components/dashboard/insights-card.tsx`
(`<InsightsCard>`, `<InsightsSummary>`, `<InsightsRecommendations>`). `ModuleLayout` takes `insightsModule` and renders the engine in
its Summary tab and AI Recommendations column (the old lists remain only as the fallback if the engine is unreachable).
