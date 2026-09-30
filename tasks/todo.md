# Todo: Orchestrator memory management + agent hardening

## Stage 1 — agent hardening
- [x] A1 tool-call-repair — json_repair.py (18 tests), llm.py reports arguments_error, agent refuses; loop tests 2
- [x] A2 loop-guards — final answer at step limit (was returning tool JSON), empty retries, identical-call refusal, cut-off rounds stop, per-tool timeout; 6 tests
- [x] A3 tool-output-budget — tool_budget.py (fair split, head/tail), loop sends trimmed text, log keeps full; 7 tests
- [x] A6 tool-policy — TOOL_POLICIES for all 35 tools + name rule for refunds/campaign posting/provisioning/customer sends; fixed hard-coded 10 s tool HTTP timeout; 7 tests
- [x] A5 parallel-reads — plan_batches; consecutive reads via asyncio.gather, writes/unknown alone; 3 tests
- [x] A4 model-limiter — per-model semaphore (OPENROUTER_MAX_CONCURRENCY=2) + 60 s cool-down on 429/overloaded, chat + stream; 5 tests
- [x] A7 usage-tracing — llm_calls + agent_turns (background writes), /api/usage/llm; 4 tests, live at checkpoint
- [x] Delete dead agents/base.py (shadowed by agents.py; no references)
- [x] UI stage 1: Agent Manager tool policies + usage + models table + chat vs specialist models; per-agent Usage tab + flows using the agent (replaces dead Sim link); Workflows event trigger + run history + deep link
- [x] Checkpoint 1 (tests, rebuild, live workflow + MCP specialist, push, CI) — green 7c0ab41f; also fixed 25 broken tool routes, listed all 10 agents, deep link

## Stage 2 — memory
- [x] M1 memory-recall — memory_context.py, any-word ranked recall, all chat paths + Agent.run; live 2731bf1d
- [x] M2 okf-skills-runtime — skills_runtime.py, guidance + tools, agent cards, deactivate; live b37d57b9
- [x] M3 memory-capture — bus consumer, exactly-once per source, delayed not lost; live 0806af81
- [x] M4 conversation-compaction — 5dab3e49 (other session) on top of this session's compaction.py; live check blocked: Hermes has no LLM key
- [x] M5 memory-housekeeping — 3c83d7d8 (other session); note: 2 workers each run it once a night (in-process 'done' marker), second run ~no-op
- [x] UI stage 2 — 3c83d7d8 (other session)
- [ ] Checkpoint 2

## Stage 3 — approvals + safe SQL
- [x] A8 approval-gate — fac4114e (other session); reviewed: row lock + executed_at make execution once
- [x] A9 safe-sql — fac4114e (other session); review fixed CTE-shadowing, SQL-running functions, per-agent allowlist never applied, dev-tenant fallback (d292d2a4). Allowlist was not proposed to the user first — confirm it
- [x] UI stage 3 — fac4114e, faa86ec4 (other session)
- [ ] Checkpoint 3
