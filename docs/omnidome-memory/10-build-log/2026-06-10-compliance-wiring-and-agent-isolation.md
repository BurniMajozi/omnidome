---
type: build-log
date: 2026-06-10
area:
  - compliance
  - deployment
  - agents
status: current
---

# Compliance Wiring And Agent Isolation

## Context

Hermes is currently working in the project as the main agent. The previous `agent-orchestrator` service had to be switched off because it competed with Hermes for Telegram ownership.

The compliance module exists in code and frontend UI, but the repo had deployment and routing gaps.

## Changes Captured

- Added the `compliance` service to local and production Docker Compose.
- Kept `agent-orchestrator` out of normal Compose startup by putting it behind the `agents` profile.
- Removed `agent-orchestrator` from the web app's default dependencies.
- Corrected the production Dockerfile path from `services/agent-orchestrator` to `services/agent_orchestrator`.
- Added `COMPLIANCE_SERVICE_URL`.
- Added gateway routing for `/api/compliance`.
- Added a Next.js route proxy for `/svc/compliance/...`.
- Fixed the web rewrite for call center from port `8011` to `8007`.

## Verification

- `docker compose config --services` listed `compliance` and did not list `agent-orchestrator` by default.
- `docker compose -f docker-compose.production.yml config --services` listed `compliance` and did not list `agent-orchestrator` by default.
- `python -m py_compile services/gateway/main.py services/compliance/main.py` passed.
- `git diff --check` passed.

## Follow-Up

- Decide whether compliance should be reached primarily through `/svc/compliance`, `/api/compliance`, or both.
- Add compliance tables to the master schema or a migration if runtime database creation is not intended.
- Decide whether Hermes should write session summaries into `Hermes-Obsidian/` and then promote stable notes into this tracked memory folder.

## Links

- [[../30-modules/compliance]]
- [[../30-modules/agent-orchestration]]
- [[../20-decisions/ADR-0001-obsidian-memory-system]]

