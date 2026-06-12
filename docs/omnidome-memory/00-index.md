---
type: memory-index
project: OmniDome OS
updated: 2026-06-10
---

# OmniDome OS Memory Index

This is the home note for OmniDome OS memory.

## Current State

OmniDome is a multi-service ISP operating system with FastAPI services, a Next.js dashboard, Docker Compose orchestration, and South African ISP workflows including CRM, billing, network operations, RICA, POPIA, compliance, support, retention, and finance.

## Active Build Threads

- [[10-build-log/2026-06-10-173532-admin-frontend-module|admin frontend module]]
- [[10-build-log/2026-06-10-admin-frontend-module|admin frontend module]]
- [[10-build-log/2026-06-10-165135-agent-protocol-baseline-implementation|agent protocol baseline implementation]]
- [[10-build-log/2026-06-10-164334-agent-protocol-design-review|agent protocol design review]]
- [[10-build-log/2026-06-10-141817-tenant-memory-service-scaffold|tenant memory service scaffold]]
- [[10-build-log/2026-06-10-140456-initial-memory-snapshot|initial memory snapshot]]
- [[10-build-log/2026-06-10-compliance-wiring-and-agent-isolation]]

## Decisions

- [[20-decisions/ADR-0001-obsidian-memory-system]]
- [[20-decisions/ADR-0002-agent-protocol-architecture]]

## Modules

- [[30-modules/admin]]
- [[30-modules/compliance]]
- [[30-modules/agent-orchestration]]
- [[30-modules/tenant-memory]]

## How To Capture Current Logs

Run:

```bash
python scripts/memory_snapshot.py --title "short-session-title"
```

The script writes a timestamped note under `docs/omnidome-memory/10-build-log/` with Git status, recent commits, configured Docker Compose services, and optional notes.

