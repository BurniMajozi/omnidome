# Implementation Plan: Orchestrator memory management + agent hardening

Spec: `SPEC-orchestrator-memory-hardening.md` (decisions recorded there).
Previous plans archived in `tasks/archive/`.

## Stage 1 — agent hardening (this run)
Order: A1 → A2 → A3 → A6 → A5 → A4 → A7, then Checkpoint 1 (tests, rebuild,
live checks, push, CI).

- A1 `tool-call-repair`: `services/agent_orchestrator/json_repair.py`; llm.py
  keeps the raw arguments + a repair verdict; agents.py refuses invalid/cut-off
  calls with a tool error.
- A2 `loop-guards`: final synthesis at the step limit (today it returns the last
  tool message's JSON as the answer — bug), empty-answer retries, repeated-answer
  and consecutive-truncation stops, per-tool timeout.
- A3 `tool-output-budget`: `tool_budget.py` cap + fair split + marker.
- A6 `tool-policy`: `mutates / requires_approval / timeout_s / max_output_chars`
  on every Tool; completeness test.
- A5 `parallel-reads`: group consecutive read-only calls; writes are barriers.
- A4 `model-limiter`: per-model semaphore + 429 cool-down in common/openrouter.py.
- A7 `usage-tracing`: usage/model/latency from responses → `llm_calls`;
  `/api/usage/llm`.
- Cleanup: delete dead `agents/base.py`.

## Stage 2 — memory (next run): M1 → M2 → M3 → M4 → M5
## Stage 3 — approvals + safe SQL: A8 → A9

## Risks
| Risk | Mitigation |
|---|---|
| Loop changes break workflows/MCP specialists | scripted fake-LLM unit tests + live workflow + MCP call after rebuild |
| Free models stay rate-limited during live checks | cool-down proves itself; accept a failed-AI step as long as it fails visibly |
| Slow pip inside WSL rebuilds | requirements unchanged in stage 1 (no new deps) so layers are cached |
