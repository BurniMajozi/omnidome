---
type: build-log
date: 2026-06-10
area: []
status: captured
---

# admin frontend module

## Notes

Added Admin dashboard module, /api/admin proxy, admin API client expansion, sidebar/dashboard wiring, and admin memory graph notes.

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
 M apps/web/app/dashboard/page.tsx
 M apps/web/components/dashboard/sidebar.tsx
 M apps/web/lib/admin-api.ts
 M apps/web/lib/entitlements.ts
 M apps/web/next.config.mjs
 M config/master_schema.sql
 M docker-compose.production.yml
 M docker-compose.yaml
 M services/agent_orchestrator/config.py
 M services/agent_orchestrator/main.py
 M services/agent_orchestrator/routes/agents.py
 M services/agent_orchestrator/tools.py
 M services/gateway/main.py
?? apps/web/app/api/admin/
?? apps/web/app/svc/
?? apps/web/components/modules/admin-module.tsx
?? config/migrations/20260610_add_tenant_memory.sql
?? docs/agent-protocols-design.md
?? docs/omnidome-memory/
?? scripts/memory_snapshot.py
?? services/agent_orchestrator/protocols.py
?? services/agent_orchestrator/routes/protocols.py
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

### `docker compose config --services`

```text
db
journey_engine
lifecycle
marketing
sales
tenant_memory
billing
call_center
fno_intelligence
retention
web_analytics
hr
agent-orchestrator
billing_collections
inventory
portal
crm
customer_journey
gateway
support
compliance
finance
iot
network
rica
admin
hermes
web
communication
WARNING: Error loading config file: open C:\Users\BMajozi\.docker\config.json: Access is denied.
WARNING: Error loading config file: open C:\Users\BMajozi\.docker\config.json: Access is denied.
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"LICENSE_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"LICENSE_PUBLIC_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"LICENSE_ENFORCEMENT\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"LICENSE_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"LICENSE_PUBLIC_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"LICENSE_ENFORCEMENT\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"LICENSE_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"LICENSE_PUBLIC_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"LICENSE_ENFORCEMENT\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"ML_MODEL_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"LICENSE_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"LICENSE_PUBLIC_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"LICENSE_ENFORCEMENT\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"LICENSE_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"LICENSE_PUBLIC_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"LICENSE_ENFORCEMENT\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"PAYSTACK_SECRET_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"LICENSE_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"LICENSE_PUBLIC_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"LICENSE_ENFORCEMENT\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"LICENSE_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"LICENSE_PUBLIC_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"LICENSE_ENFORCEMENT\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"NEXT_PUBLIC_GATEWAY_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"LICENSE_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"LICENSE_PUBLIC_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"LICENSE_ENFORCEMENT\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"LICENSE_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"LICENSE_PUBLIC_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"LICENSE_ENFORCEMENT\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"OPENROUTER_API_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"TELEGRAM_BOT_TOKEN\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"TELEGRAM_ALLOWED_USERS\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"LICENSE_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"LICENSE_PUBLIC_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"LICENSE_ENFORCEMENT\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"LICENSE_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"LICENSE_PUBLIC_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"LICENSE_ENFORCEMENT\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"LICENSE_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"LICENSE_PUBLIC_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"LICENSE_ENFORCEMENT\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"LICENSE_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"LICENSE_PUBLIC_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"LICENSE_ENFORCEMENT\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"LICENSE_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"LICENSE_PUBLIC_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"LICENSE_ENFORCEMENT\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"LICENSE_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"LICENSE_PUBLIC_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"LICENSE_ENFORCEMENT\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"LICENSE_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"LICENSE_PUBLIC_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"LICENSE_ENFORCEMENT\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"LICENSE_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"LICENSE_PUBLIC_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"LICENSE_ENFORCEMENT\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"OPENROUTER_API_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"POSTGRES_DB\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"POSTGRES_USER\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"POSTGRES_PASSWORD\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"LICENSE_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"LICENSE_PUBLIC_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"LICENSE_ENFORCEMENT\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"POSTGRES_DB\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"LICENSE_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"LICENSE_PUBLIC_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"LICENSE_ENFORCEMENT\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"LICENSE_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"LICENSE_PUBLIC_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"LICENSE_ENFORCEMENT\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"SMILE_ID_PARTNER_ID\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"SMILE_ID_API_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"LICENSE_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"LICENSE_PUBLIC_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"LICENSE_ENFORCEMENT\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"LICENSE_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"LICENSE_PUBLIC_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"LICENSE_ENFORCEMENT\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:32+02:00" level=warning msg="C:\\Users\\BMajozi\\Documents\\Codex\\2026-06-10\\github-plugin-github-openai-curated-burnimajozi\\work\\omnidome\\docker-compose.yaml: the attribute `version` is obsolete, it will be ignored, please remove it to avoid potential confusion"
```

### `docker compose -f docker-compose.production.yml config --services`

```text
db
agent-orchestrator
inventory
rica
sales
gateway
web
web_analytics
admin
billing_collections
iot
lifecycle
marketing
network
retention
analytics
compliance
crm
customer_journey
finance
hr
journey_engine
support
billing
call_center
communication
fno_intelligence
tenant_memory
WARNING: Error loading config file: open C:\Users\BMajozi\.docker\config.json: Access is denied.
WARNING: Error loading config file: open C:\Users\BMajozi\.docker\config.json: Access is denied.
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"SMILE_ID_PARTNER_ID\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"SMILE_ID_API_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"LICENSE_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"LICENSE_PUBLIC_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"LICENSE_ENFORCEMENT\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"LICENSE_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"LICENSE_PUBLIC_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"LICENSE_ENFORCEMENT\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"LICENSE_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"LICENSE_PUBLIC_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"LICENSE_ENFORCEMENT\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"LICENSE_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"LICENSE_PUBLIC_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"LICENSE_ENFORCEMENT\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"LICENSE_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"LICENSE_PUBLIC_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"LICENSE_ENFORCEMENT\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"LICENSE_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"LICENSE_PUBLIC_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"LICENSE_ENFORCEMENT\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"LICENSE_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"LICENSE_PUBLIC_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"LICENSE_ENFORCEMENT\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"LICENSE_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"LICENSE_PUBLIC_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"LICENSE_ENFORCEMENT\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"LICENSE_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"LICENSE_PUBLIC_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"LICENSE_ENFORCEMENT\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"LICENSE_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"LICENSE_PUBLIC_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"LICENSE_ENFORCEMENT\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"LICENSE_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"LICENSE_PUBLIC_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"LICENSE_ENFORCEMENT\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"ML_MODEL_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"LICENSE_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"LICENSE_PUBLIC_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"LICENSE_ENFORCEMENT\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"LICENSE_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"LICENSE_PUBLIC_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"LICENSE_ENFORCEMENT\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"LICENSE_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"LICENSE_PUBLIC_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"LICENSE_ENFORCEMENT\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"LICENSE_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"LICENSE_PUBLIC_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"LICENSE_ENFORCEMENT\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"OPENROUTER_API_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"LICENSE_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"LICENSE_PUBLIC_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"LICENSE_ENFORCEMENT\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"LICENSE_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"LICENSE_PUBLIC_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"LICENSE_ENFORCEMENT\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"LICENSE_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"LICENSE_PUBLIC_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"LICENSE_ENFORCEMENT\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"LICENSE_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"LICENSE_PUBLIC_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"LICENSE_ENFORCEMENT\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"LICENSE_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"LICENSE_PUBLIC_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"LICENSE_ENFORCEMENT\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"LICENSE_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"LICENSE_PUBLIC_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"LICENSE_ENFORCEMENT\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"LICENSE_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"LICENSE_PUBLIC_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"LICENSE_ENFORCEMENT\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"PAYSTACK_SECRET_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"LICENSE_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"LICENSE_PUBLIC_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="The \"LICENSE_ENFORCEMENT\" variable is not set. Defaulting to a blank string."
time="2026-06-10T17:35:33+02:00" level=warning msg="C:\\Users\\BMajozi\\Documents\\Codex\\2026-06-10\\github-plugin-github-openai-curated-burnimajozi\\work\\omnidome\\docker-compose.production.yml: the attribute `version` is obsolete, it will be ignored, please remove it to avoid potential confusion"
```

## Links

- [[../00-index]]
