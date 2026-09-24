# Todo: Orchestrator memory management + agent hardening

## Stage 1 — agent hardening
- [x] A1 tool-call-repair — json_repair.py (18 tests), llm.py reports arguments_error, agent refuses; loop tests 2
- [ ] A2 loop-guards
- [ ] A3 tool-output-budget
- [ ] A6 tool-policy
- [ ] A5 parallel-reads
- [ ] A4 model-limiter
- [ ] A7 usage-tracing
- [ ] Delete dead agents/base.py
- [ ] Checkpoint 1 (tests, rebuild, live workflow + MCP specialist, push, CI)

## Stage 2 — memory
- [ ] M1 memory-recall
- [ ] M2 okf-skills-runtime
- [ ] M3 memory-capture
- [ ] M4 conversation-compaction
- [ ] M5 memory-housekeeping
- [ ] Checkpoint 2

## Stage 3 — approvals + safe SQL
- [ ] A8 approval-gate (incl. refunds + campaign posting)
- [ ] A9 safe-sql (sqlglot; allowlist proposed first)
- [ ] Checkpoint 3
