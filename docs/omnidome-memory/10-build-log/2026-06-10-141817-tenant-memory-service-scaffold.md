---
type: build-log
date: 2026-06-10
area: []
status: captured
---

# tenant memory service scaffold

## Notes

Added tenant-scoped memory service, schema, migration, gateway route, Compose wiring, and Obsidian project memory note. Did not start containers or disturb Hermes.

## Snapshot

### `git branch --show-current`

```text
main
```

### `git rev-parse --short HEAD`

```text
ef7e084
```

### `git status --short`

```text
M .env.example
 M .github/workflows/ci.yml
 M PRODUCTION.md
 M README.md
 M apps/web/next.config.mjs
 M config/master_schema.sql
 M docker-compose.production.yml
 M docker-compose.yaml
 M services/gateway/main.py
?? apps/web/app/svc/
?? config/migrations/20260610_add_tenant_memory.sql
?? docs/omnidome-memory/
?? scripts/memory_snapshot.py
?? services/tenant_memory/
```

### `git log --oneline -10`

```text
ef7e084 compliance frontend: 44 API functions + 7-tab module with visual dashboards
b903d44 remove compliance summary from references (sensitive folder)
35a60b2 add compliance v2 summary
41ff6b9 compliance v2: full compliance service â€” 22 tables, 105 routes, 5 route modules
d0b6538 refactor(compliance): rebuild around contract management
8a78ae8 feat(compliance): new service â€” RICA, POPI, ICASA, contact management, SLA (port 8019)
5e51b0c feat(network): Phase 4 â€” property linkage, DPI, ONT provisioning, Wi-Fi push session recording, lead generation
a2da4bb feat(network): Phase 3 â€” topology, bandwidth, SLA compliance, device config, typography
51c5c12 feat(network): Phase 1+2 â€” performance monitoring, notifications, devices, KML import, fault reporting, cancellation workflow
17ba45f feat(zernio): webhook receiver, signature patch, setup script
```

## Links

- [[../00-index]]
