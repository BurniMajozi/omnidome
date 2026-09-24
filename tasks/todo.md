# Todo: Orchestrator memory management + agent hardening

## Stage 1 — agent hardening
- [x] A1 tool-call-repair — json_repair.py (18 tests), llm.py reports arguments_error, agent refuses; loop tests 2
- [x] A2 loop-guards — final answer at step limit (was returning tool JSON), empty retries, identical-call refusal, cut-off rounds stop, per-tool timeout; 6 tests
- [ ] A3 tool-output-budget
- [ ] A6 tool-policy
- [ ] A5 parallel-reads
- [ ] A4 model-limiter
- [ ] A7 usage-tracing
- [ ] Delete dead agents/base.py
- [ ] UI stage 1: Agent Manager tool policies + usage; Workflows event trigger + run history
- [ ] Checkpoint 1 (tests, rebuild, live workflow + MCP specialist, push, CI)

## Stage 2 — memory
- [ ] M1 memory-recall
- [ ] M2 okf-skills-runtime
- [ ] M3 memory-capture
- [ ] M4 conversation-compaction
- [ ] M5 memory-housekeeping
- [ ] UI stage 2: Agent Manager memory + OKF skills tabs; runs show memory writes
- [ ] Checkpoint 2

## Stage 3 — approvals + safe SQL
- [ ] A8 approval-gate (incl. refunds + campaign posting)
- [ ] A9 safe-sql (sqlglot; allowlist proposed first)
- [ ] UI stage 3: approvals in Agent Manager; runs awaiting approval in Workflows
- [ ] Checkpoint 3
