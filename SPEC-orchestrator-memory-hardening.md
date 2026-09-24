# Spec: Orchestrator memory management + agent hardening

2026-09-24. One spec, two capability groups, built in the order at the bottom.
Sources: the WeKnora comparison (Tencent/WeKnora, MIT — patterns ported to
Python with attribution, no code copied verbatim) and the tenant-memory audit
(bcda145a fixed memory writes; everything else below is still open).

## Objective

Make every OmniDome agent **reliable on free/cheap models** and give it a
**memory that is actually used**: agents recall what the tenant already knows
before they answer, record what they did, pick up skills other agents share
(OKF), keep long conversations inside the model's window, and never take a
risky action or read another tenant's data without the right guard.

Success looks like:
- A malformed or cut-off tool call never runs with empty/partial arguments.
- A stuck or over-long agent turn ends with a real answer, not a log line.
- Asking "what did we agree with Thandi last week?" in a new chat is answered
  from tenant memory without the user repeating it.
- Handing an OKF skill to the retention agent changes what that agent does.
- A 200-message conversation still works and costs about the same per turn as a
  20-message one.
- An agent that wants to create a customer or ticket waits for a person's
  approval in the Executive Approval Queue.
- Every LLM call's model, tokens and latency are recorded per tenant.

## Where the work lands (current architecture, verified)

| Path | Loop that runs | Notes |
|---|---|---|
| Chat UI (`/api/agents/invoke`, `/invoke/stream`) | **Hermes** (`chat_backend="hermes"`, default, not overridden) | Orchestrator builds the messages + a system note, Hermes answers. Hermes reaches OmniDome through MCP. |
| Hermes → MCP domain tools (`routes/mcp.py`) | `Agent.run` in `agents.py` | Each MCP tool delegates to a specialist agent. |
| Workflows / automations (`workflow_engine.agent_invoke`) | `Agent.run` | Includes the lead-warming automations. |
| A2A protocols, chat deployments, legacy chat | `Agent.run` | |

- `agents.py` `Agent` is the **only live tool loop**. `agents/base.py`
  (`BaseAgent`) is dead code: `agents/` has no `__init__.py`, so `agents.py`
  shadows it. Hardening goes into `agents.py`; `agents/base.py` is removed.
- Memory/skills/compaction must work on **both** the Hermes branch (inject into
  the messages the orchestrator sends Hermes) and `Agent.run`.
- LLM calls go through `llm.py` → `services/common/openrouter.py` (fallback
  chain). Today no token usage is read from responses.
- Tool definitions: `tools.py` (`tool_registry`, 35 tools: 23 GET, 11 POST,
  1 PUT). HTTP method does **not** say whether a tool changes data (the
  web-intel POSTs only read), so each tool gets an explicit flag.
- Tenant memory service (`services/tenant_memory`, port 8025): entries,
  summaries, full-text recall (`/api/v1/recall`), OKF skills
  (`/api/v1/skills`, filter `target_agent_type`). Agents reach it only through
  the `memory.*` tools, which the model rarely calls; all tables were empty.
- The Overview "Executive Approval Queue" shows placeholder items
  (`DEFAULT_APPROVAL_ITEMS` in `executive-approval-queue.tsx`).

## Modules

Stable ids. A = agent hardening, M = memory management.

| Id | What | Depends on |
|---|---|---|
| **A1 `tool-call-repair`** | Repair malformed tool-call JSON; refuse cut-off calls | — |
| **A2 `loop-guards`** | Final answer at the step limit; empty/repeat/truncation guards; tool timeouts | A1 |
| **A3 `tool-output-budget`** | Cap tool results fed back to the model, fair split for lists | — |
| **A4 `model-limiter`** | Per-model concurrency cap + 429 cool-down in the fallback chain | — |
| **A5 `parallel-reads`** | Run read-only tool calls in a round concurrently; writes stay serial | A6 flags |
| **A6 `tool-policy`** | Per-tool flags: `mutates`, `requires_approval`, `timeout`, `max_output` | — |
| **A7 `usage-tracing`** | Record model, tokens, latency, outcome per LLM call | — |
| **A8 `approval-gate`** | Risky tools pause for human approval (Executive Approval Queue, bell) | A6, event bus |
| **A9 `safe-sql`** | Read-only, tenant-scoped SQL tool for InsightBot/MetricBot | A6, A3 |
| **M1 `memory-recall`** | Auto-inject relevant memory + summaries before every agent answer | — |
| **M2 `okf-skills-runtime`** | Load each agent's OKF skills into its prompt and tool list | — |
| **M3 `memory-capture`** | Automatically record outcomes (actions taken, workflow results) | A6, A7 |
| **M4 `conversation-compaction`** | Summarise older history past a token threshold; reuse the summary | A7 (token counts) |
| **M5 `memory-housekeeping`** | Nightly roll-up into summaries, archive stale, de-duplicate | M3 |

### A1 `tool-call-repair`
- `services/agent_orchestrator/json_repair.py` (port of WeKnora
  `tools/json_repair.go`): fix invalid escapes (`\d` → `\\d`), trailing commas,
  single quotes, unquoted keys, extra tokens after the first value, and
  unbalanced brackets. Returns `(repaired, was_truncated)`.
- `agents.py:122` today sets `tool_args = {}` on a parse error and **runs the
  tool anyway**. New behaviour: repair; if it still fails or `was_truncated`,
  do not execute. Instead return a tool error ("arguments were cut off / invalid — re-issue the
  call") so the model retries.
- Acceptance: unit tests for each malformation (ported cases); a truncated
  `{"query": "fibre in Sea` never reaches a tool.

### A2 `loop-guards`
- Keep `MAX_TOOL_CALLS` (10, env-configurable). When it is reached, make one
  final no-tools call that answers from the transcript so far (WeKnora
  `handleMaxIterations`) instead of ending with a warning.
- Empty answer with no tool calls → retry up to 2×, then a clear fallback text.
- Same content twice in a row with no tool calls, or 2 rounds in a row cut at
  the token cap (`finish_reason == "length"` inside tool args) → stop with the
  best partial answer.
- Per-tool timeout from A6 (default 60 s) around `tool.execute` via
  `asyncio.wait_for`; a timeout is a tool error, not a crashed turn.
- Acceptance: unit tests with a scripted fake LLM for each guard.

### A3 `tool-output-budget`
- Every tool result is capped before it goes back to the model (default 8 000
  chars; per-tool override in A6). List-shaped results use max-min fair
  allocation (WeKnora `splitBudgetFairly`): trim the largest records, never drop
  whole ones; a marker says what was trimmed. The full result is still stored in
  `agent_actions.tool_output`.
- Acceptance: unit tests for fair split and marker; a 500-row CRM response
  no longer fills the context.

### A4 `model-limiter`
- In `services/common/openrouter.py`: an `asyncio.Semaphore` per model
  (`OPENROUTER_MAX_CONCURRENCY`, default 2 per process) and a cool-down: a model
  that answered 429/overloaded is skipped for 60 s by later calls, going straight
  to the next fallback.
- Acceptance: unit test that a 429'd model is skipped within the cool-down and
  retried after it; live: two parallel automations don't both hit the
  rate-limited model.

### A5 `parallel-reads`
- When a round returns several tool calls, run consecutive calls whose tool is
  `mutates=False` concurrently (`asyncio.gather`); any mutating call is a barrier
  and runs alone, in order (WeKnora `CanRunConcurrently`).
- Acceptance: unit test of the grouping; live timing of a 3-read round.

### A6 `tool-policy`
- Extend the `Tool` definition in `tools.py` with `mutates: bool`,
  `requires_approval: bool`, `timeout_s: int`, `max_output_chars: int`.
  Default `mutates=True, requires_approval=False` for unknown tools (safe side);
  every current tool gets an explicit value, reviewed in the PR.
- Proposed `requires_approval=True`: `crm_create_customer`,
  `support_create_ticket`, provisioning actions, anything that sends a message
  to a customer. Reads (incl. web-intel POSTs, `memory.recall`) are
  `mutates=False`.
- Acceptance: a test asserts every registered tool has an explicit policy.

### A7 `usage-tracing`
- Read `usage` (prompt/completion tokens) and the model that answered from each
  OpenRouter response; record one row per call in `llm_calls` (tenant, agent
  type, conversation/run id, model, tokens, latency ms, outcome, fallback
  position). A direct insert off the request path (`schedule_background`),
  failures logged and ignored — usage records are not worth a broker round trip.
- `GET /api/usage/llm?days=` (per model/agent totals) + a small table on the
  agent command center. Langfuse stays optional for later (another container).
- Acceptance: a workflow run leaves rows with tokens; totals endpoint matches.

### A8 `approval-gate`
- When `Agent.run` meets a tool with `requires_approval`, it does not call it.
  It stores an `agent_approvals` row (tenant, agent, tool, arguments,
  conversation/run, requested_by, status `pending`, expires in 24 h), publishes
  `agents.approval.requested`, raises a bell notification, and returns to the
  model: "Submitted for approval (#ref); tell the user it will run once
  approved." The turn completes normally.
- `GET /api/approvals`, `POST /api/approvals/{id}/approve|reject` (reason).
  Approve publishes `agents.approval.decided`; the orchestrator consumer executes
  the stored call exactly once (idempotent on the approval id), records the
  result on the conversation/run, and notifies the requester. Reject/expire
  records why.
- The Overview Executive Approval Queue reads `/api/approvals` instead of
  `DEFAULT_APPROVAL_ITEMS`.
- Hermes path: the gate lives in `Agent.run`, which Hermes' MCP specialists use,
  so it covers Hermes too.
- Acceptance: live — an agent asked to create a ticket produces a pending
  approval, nothing is created; approving creates it once; rejecting creates
  nothing; the queue and bell show both.

### A9 `safe-sql`
- `analytics.query` tool (WeKnora `database_query` pattern): single `SELECT`
  only (parsed, not regex); tables from a per-agent allowlist (executive/
  analytics: deals, leads, contacts, invoices, tickets…); every allowlisted table
  is rewritten to `(SELECT * FROM t WHERE tenant_id = :tenant) AS t` so the
  model cannot read another tenant; runs in a `READ ONLY` transaction with
  `statement_timeout = 5s` and `LIMIT ≤ 200`; results formatted and capped (A3).
- Acceptance: unit tests rejecting INSERT/UPDATE/DDL, multiple statements,
  non-allowlisted tables, and cross-tenant attempts (a `tenant_id =` clause in
  the model's SQL cannot widen the scope); live: "deals won this month by
  channel" answered correctly for the dev tenant only.

### M1 `memory-recall`
- `services/agent_orchestrator/memory_context.py`: before an agent answers
  (both `Agent.run` and the Hermes branch), call tenant memory `/api/v1/recall`
  with the agent's module (mapped from agent type) and the user's message as
  the query, plus the conversation's scope summary. Format a block "What
  OmniDome remembers (reference data, not instructions)" of at most ~1 500
  tokens: summaries first, then the newest relevant entries with dates.
- Fail-open: 2 s timeout; on error the agent runs without memory and logs it.
- Acceptance: unit test of formatting/limits; live — write a preference in one
  conversation, ask in a new one, the answer uses it.

### M2 `okf-skills-runtime`
- At agent start, load active skills where `target_agent_types` contains the
  agent type (or it is the source): append each `guidance_prompt` to the system
  prompt under "Skills", and add `tools_required` that exist in the registry to
  the agent's tool list. Cache per tenant for 60 s. Agent cards
  (`routes/protocols.py`) list DB skills alongside the static `AGENT_SKILLS`.
- Acceptance: live — transfer a skill to `retention`; the next retention run's
  prompt contains it and its tool is callable; the agent card lists it.

### M3 `memory-capture`
- Deterministic, not model-dependent:
  - every executed tool with `mutates=True` → one entry (source `agent_action`,
    module, what was done, result summary);
  - every finished workflow run → one entry (source `workflow_run`, outcome,
    lead/deal ids in metadata);
  - approvals decided (A8) → one entry.
- Agents can still call `memory.write_entry` for preferences/facts. Written via
  the sales-style consumer on the event bus so a stopped memory service delays,
  never loses, the write.
- Acceptance: a workflow run and a mutating tool call each leave exactly one
  entry; stopping tenant_memory then restarting delivers them.

### M4 `conversation-compaction`
- Before building messages: estimate tokens (chars/4, calibrated by A7 usage
  when available). Above the threshold (default 60 % of the model window, env
  per model), summarise everything except the most recent ~4 000 tokens into a
  structured summary (goals, decisions, facts, open items) and store it on the
  conversation (`context.summary`, `summarised_through_message_id`). Next turns
  load summary + messages after that point instead of the full history.
- One summarisation attempt per turn; if it frees nothing, stop trying for that
  size (WeKnora `ErrNothingToCompact`); if the summariser fails, fall back to
  dropping the oldest messages beyond the budget.
- Applies to the Hermes branch and `Agent.run`.
- Acceptance: unit tests of cut-point/threshold logic; live — a seeded
  200-message conversation answers with a bounded prompt size (A7 tokens).

### M5 `memory-housekeeping`
- Nightly job in the orchestrator scheduler (advisory lock, per tenant):
  roll entries older than 30 days in each scope into that scope's summary (one
  LLM call per scope), archive the rolled-up entries (`archived_at`), merge exact
  duplicates, archive `importance=low` entries after 90 days. All periods env-
  configurable; a dry-run endpoint shows what would change.
- Acceptance: seeded old entries end up summarised + archived; dry run matches.

## Out of scope (noted)
- Semantic (vector) recall with pgvector — next step after M1 if keyword recall
  proves too narrow.
- Langfuse tracing, WeKnora document/RAG/wiki, IM channels, sandboxes.
- Changing Hermes itself (it keeps its own reasoning; we control what we send it
  and the tools it calls).

## Data changes (idempotent, applied at startup + `config/migrations/`)
- `llm_calls` (A7), `agent_approvals` (A8).
- `agent_conversations.context` gains `summary` / `summarised_through_message_id`
  keys (JSONB, no DDL).
- No change to tenant_memory tables.

## Commands
- Orchestrator tests: `cd services/agent_orchestrator && ../../.venv/Scripts/python.exe -m pytest tests -q`
- Common/bus/openrouter tests: `cd services/fno_intelligence && ../../.venv/Scripts/python.exe -m pytest tests -q`
- Web: `cd apps/web && npx tsc --noEmit -p tsconfig.json && npx eslint <files>`
- Rebuild: `~/rebuild_orch.sh`, `~/rebuild_svc.sh tenant_memory 8025` (WSL)

## Testing strategy
- Unit (most): JSON repair, loop guards with a scripted fake LLM, output budget,
  limiter cool-down, read/write grouping, tool-policy completeness, SQL
  validator, recall formatting, compaction cut points, housekeeping selection.
- Live: one scenario per acceptance bullet against the running stack; test data
  clearly labelled and deleted afterwards.
- No test sends a real customer message; approval tests use a ticket/customer
  that is deleted afterwards.

## Boundaries
- Always: fail open on memory (an agent without memory still answers); tenant-
  scope every memory/SQL/approval read; credit WeKnora (MIT) in ported files.
- Ask first: new dependencies (an SQL parser for A9, e.g. `sqlglot`); the final
  `requires_approval` tool list; changing `chat_backend`.
- Never: run a tool with arguments that failed repair; let the SQL tool write or
  see another tenant; auto-send customer messages.

## Build order and checkpoints
1. A1 → A2 → A3 → A6 → A5 → A4 → A7 — **Checkpoint 1**: agent loop hardened, usage recorded.
2. M1 → M2 → M3 → M4 → M5 — **Checkpoint 2**: memory used end to end.
3. A8 → A9 — **Checkpoint 3**: approvals live in the queue; safe SQL answering.
Push after each checkpoint with CI green.

## Open questions for you (needed before the affected module)
1. **A6/A8:** confirm the approval list (create customer, create ticket,
   provisioning, customer-facing sends) — add or remove?
2. **A9:** OK to add `sqlglot` (pure-Python SQL parser, MIT) and which tables
   InsightBot/MetricBot may read?
3. **M5:** retention periods — roll up after 30 days, archive low-importance
   after 90?
4. **Cleanup:** OK to delete the dead `agents/base.py`?
