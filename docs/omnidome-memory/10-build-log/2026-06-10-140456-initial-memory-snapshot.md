---
type: build-log
date: 2026-06-10
area: []
status: captured
---

# initial memory snapshot

## Notes

Scaffolded Obsidian-style project memory under docs/omnidome-memory and captured the current repo state after compliance wiring and agent isolation changes.

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
 M docker-compose.production.yml
 M docker-compose.yaml
 M services/gateway/main.py
?? apps/web/app/svc/
?? docs/omnidome-memory/
?? scripts/memory_snapshot.py
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
fno_intelligence
gateway
iot
network
portal
billing
communication
compliance
marketing
retention
rica
sales
crm
finance
web
hr
billing_collections
customer_journey
inventory
web_analytics
hermes
journey_engine
lifecycle
support
admin
call_center
WARNING: Error loading config file: open C:\Users\BMajozi\.docker\config.json: Access is denied.
WARNING: Error loading config file: open C:\Users\BMajozi\.docker\config.json: Access is denied.
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"POSTGRES_DB\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"POSTGRES_USER\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"POSTGRES_PASSWORD\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_PUBLIC_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_ENFORCEMENT\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_PUBLIC_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_ENFORCEMENT\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_PUBLIC_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_ENFORCEMENT\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"OPENROUTER_API_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"NEXT_PUBLIC_GATEWAY_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_PUBLIC_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_ENFORCEMENT\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_PUBLIC_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_ENFORCEMENT\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_PUBLIC_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_ENFORCEMENT\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_PUBLIC_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_ENFORCEMENT\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"OPENROUTER_API_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"TELEGRAM_BOT_TOKEN\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"TELEGRAM_ALLOWED_USERS\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_PUBLIC_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_ENFORCEMENT\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_PUBLIC_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_ENFORCEMENT\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_PUBLIC_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_ENFORCEMENT\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_PUBLIC_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_ENFORCEMENT\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_PUBLIC_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_ENFORCEMENT\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_PUBLIC_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_ENFORCEMENT\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_PUBLIC_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_ENFORCEMENT\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_PUBLIC_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_ENFORCEMENT\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"POSTGRES_DB\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"PAYSTACK_SECRET_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_PUBLIC_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_ENFORCEMENT\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"SMILE_ID_PARTNER_ID\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"SMILE_ID_API_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_PUBLIC_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_ENFORCEMENT\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_PUBLIC_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_ENFORCEMENT\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_PUBLIC_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_ENFORCEMENT\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"ML_MODEL_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_PUBLIC_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_ENFORCEMENT\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_PUBLIC_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_ENFORCEMENT\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="C:\\Users\\BMajozi\\Documents\\Codex\\2026-06-10\\github-plugin-github-openai-curated-burnimajozi\\work\\omnidome\\docker-compose.yaml: the attribute `version` is obsolete, it will be ignored, please remove it to avoid potential confusion"
```

### `docker compose -f docker-compose.production.yml config --services`

```text
db
compliance
finance
hr
inventory
sales
web_analytics
admin
call_center
gateway
retention
analytics
customer_journey
fno_intelligence
iot
lifecycle
rica
support
billing
communication
crm
journey_engine
marketing
network
web
billing_collections
WARNING: Error loading config file: open C:\Users\BMajozi\.docker\config.json: Access is denied.
WARNING: Error loading config file: open C:\Users\BMajozi\.docker\config.json: Access is denied.
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"PAYSTACK_SECRET_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_PUBLIC_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_ENFORCEMENT\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_PUBLIC_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_ENFORCEMENT\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_PUBLIC_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_ENFORCEMENT\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_PUBLIC_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_ENFORCEMENT\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_PUBLIC_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_ENFORCEMENT\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_PUBLIC_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_ENFORCEMENT\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"SMILE_ID_PARTNER_ID\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"SMILE_ID_API_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_PUBLIC_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_ENFORCEMENT\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_PUBLIC_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_ENFORCEMENT\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_PUBLIC_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_ENFORCEMENT\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_PUBLIC_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_ENFORCEMENT\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_PUBLIC_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_ENFORCEMENT\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"OPENROUTER_API_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_PUBLIC_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_ENFORCEMENT\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_PUBLIC_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_ENFORCEMENT\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_PUBLIC_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_ENFORCEMENT\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_PUBLIC_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_ENFORCEMENT\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_PUBLIC_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_ENFORCEMENT\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_PUBLIC_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_ENFORCEMENT\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_PUBLIC_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_ENFORCEMENT\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_PUBLIC_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_ENFORCEMENT\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"ML_MODEL_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_PUBLIC_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_ENFORCEMENT\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_PUBLIC_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_ENFORCEMENT\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"DATABASE_URL\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_PATH\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_PUBLIC_KEY\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="The \"LICENSE_ENFORCEMENT\" variable is not set. Defaulting to a blank string."
time="2026-06-10T14:04:56+02:00" level=warning msg="C:\\Users\\BMajozi\\Documents\\Codex\\2026-06-10\\github-plugin-github-openai-curated-burnimajozi\\work\\omnidome\\docker-compose.production.yml: the attribute `version` is obsolete, it will be ignored, please remove it to avoid potential confusion"
```

## Links

- [[../00-index]]
