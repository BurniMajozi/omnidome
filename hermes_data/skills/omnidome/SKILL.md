---
name: omnidome
description: "OmniDome ISP Operating System — codebase knowledge, architecture, gaps, and conventions."
version: 1.2.0
author: Hermes Agent
platforms: [linux]
metadata:
  hermes:
    tags: [isp, telecom, saas, fastapi, python, microservices, south-africa]
---

# OmniDome — ISP Operating System

## Project Overview

OmniDome is a carrier-grade, microservice-based operations platform for South African ISPs. It unifies CRM, Sales, Billing, Network provisioning, Retention analytics, Support, and more into a single ecosystem with multi-tenant RBAC.

**Repo:** `https://github.com/BurniMajozi/omnidome`
**Local path (VM):** `/opt/data/workspace/omnidome`
**Patches:** `/opt/data/home/omnidome-patches/`

## Architecture

```
apps/web/          — Next.js 14 dashboard + portal (port 3000)
services/
  admin/           — Platform admin, RBAC (port 8013)
  analytics/       — AI executive insights (port 8011)
  billing/         — Invoicing, payments, collections (port 8003)
  call_center/     — Voice AI, sentiment, agents (port 8007)
  common/          — Shared auth, RBAC, entitlements, DB
  communication/   — Team comms, module data (port 8020)
  crm/             — Customer 360, leads, segmentation (port 8001)
  finance/         — GAAP finance (port 8015)
  gateway/         — API gateway / BFF (port 8000)
  hr/              — Employee management (port 8009)
  inventory/       — Stock & supply chain (port 8010)
  iot/             — Device telemetry (port 8006)
  journey_engine/  — Retention journey engine (port 8017)
  lifecycle/       — Customer lifecycle tracking (port 8018)
  marketing/       — Campaign management (port 8014)
  network/         — RADIUS, FNO adapters (port 8005)
  retention/       — Churn prediction, campaigns (port 8012)
  rica/            — RICA identity verification (port 8004)
  sales/           — Pipeline, deals, quoting (port 8002)
  support/         — SLA ticketing (port 8008)
  web_analytics/   — Web analytics + dashboard (port 8016)
```

## Cross-Service Integration Map

```
Portal cancel → Journey Engine (8017) → rule matching → offer
                     ↓                              ↓
              Lifecycle (8018) ←──outcome──── Customer stage update
                     ↑
Sales (8002) ──deal close──→ Lifecycle (8018) → stage = Converted
                     ↑
CRM (8001) ←──customer ───── Lifecycle (8018)
```

## Tech Stack

- **Backend:** Python 3.12, FastAPI, SQLAlchemy 2.0 (async)
- **Database:** PostgreSQL (Supabase for Auth + Realtime only)
- **Frontend:** Next.js 16, React 19, Tailwind CSS 4, shadcn/ui, Recharts
- **AI:** Ollama (local), OpenRouter fallback
- **Auth:** Supabase Auth, JWT, header-based dev mode
- **Payments:** Paystack (ZAR)
- **Infra:** Docker Compose V2, per-service Dockerfiles

## Service Readiness (21 services)

| Service | Port | Status |
|---------|------|--------|
| gateway | 8000 | ✅ |
| crm | 8001 | 🟡 async fix applied |
| sales | 8002 | 🟡 raw SQL, needs async |
| billing | 8003 | 🟡 R0 fix applied |
| rica | 8004 | 🟡 stub |
| network | 8005 | 🟡 FNO stubs |
| iot | 8006 | 🟡 stub |
| call_center | 8007 | 🟡 mock voice |
| support | 8008 | ✅ |
| hr | 8009 | 🟡 stub |
| inventory | 8010 | 🔴 empty |
| analytics | 8011 | ✅ |
| retention | 8012 | 🟡 mock ML |
| admin | 8013 | 🟡 unaudited |
| marketing | 8014 | 🟡 needs audit |
| finance | 8015 | 🟡 no DB |
| web_analytics | 8016 | ✅ first-party GA |
| journey_engine | 8017 | ✅ cancel-to-save |
| lifecycle | 8018 | ✅ lead→churn tracking |
| communication | 8020 | ✅ |
| agent-orchestrator | 8021 | ✅ |

## Session Continuity Pattern

When the tool-calling limit is hit mid-session and the user says "Continue":
1. **Read vault notes first** to reload context (Session N.md, Implementation Status.md, To-Do List.md)
2. **Re-read source files** that were being modified
3. **Pick up from last completed TODO** — do NOT re-explain what was built
4. Do not re-describe completed work

## Vault as Mid-Term Memory

The Obsidian vault at `~/Documents/Obsidian Vault/OmniDome/` is the agent's persistent memory:
- **Read at session start:** Latest session notes + Implementation Status
- **Update at session end:** Create session note, update Implementation Status
- **Push:** `git add -A && git commit -m "..." && git push origin main` from vault dir
- **Remote:** `BurniMajozi/Hermes-Obsidian` (works with PAT)

## File Write Gotchas

1. `~` does NOT expand in `write_file` — use `/opt/data/home/`
2. Project dir owned by uid 1000 — write to `/opt/data/home/omnidome-patches/`
3. **Docker build context:** Files MUST be in `services/<name>/` subdirectory. Writing to flat patches dir is NOT enough.
4. **Dual-service deploy:** Single `apply-all-patches.sh` per session
5. **Verify:** Always `ls -la` target dir after copying

## User Preferences

- **Concise, direct, efficient.** No preamble.
- **Domain expert** — knows SA ISP/teleco. No basics explanations.
- **Doctorate in Data Science & AI** — discuss ML/research directly.
- **Parallel implementation** OK — build and report.
- **"Continue"** = resume, don't re-explain.

## Per-Service Convention

```
services/<name>/
  main.py        — FastAPI app, guard setup
  models.py      — SQLAlchemy models
  database.py    — Session factory, init_tables()
  schemas.py     — Pydantic models
  routes/        — APIRouter modules
  Dockerfile
  requirements.txt
```

### Standalone Service Pattern (journey_engine, lifecycle, web_analytics)

These services do NOT use `services/common/db.py`. They have their own `database.py` with direct engine management. Use this pattern when a service needs independent deployment or has no dependency on the common tenant-scoped query filtering.

## Cross-Service Bridge Pattern

```python
# Fire-and-forget bridge from service A to service B:
try:
    async with httpx.AsyncClient(timeout=5) as client:
        await client.post(f"{service_b_url}/endpoint", json=payload)
except Exception:
    pass  # Don't fail the caller if bridge target is down
```

## Cancel Flow Integration (Backend Complete, Portal Not Yet Wired)

The backend chain is fully built:
1. Portal cancel → `POST journey_engine/cancel/trigger` (customer snapshot returned)
2. Journey Engine evaluates rules → returns best offer
3. Customer responds → `POST journey_engine/cancel/respond`
4. Journey Engine → `POST lifecycle/from-journey` (auto-updates customer stage)
5. Journey Engine records `JourneyOutcome` for ML feedback

Still to wire: portal cancel button display + offer presentation UI.

## New Services Reference

See `references/` directory:
- `journey-engine-service.md` — cancel-to-save rule engine + offer management
- `lifecycle-service.md` — lead→churn lifecycle tracking + bridges
- `web-analytics-service.md` — first-party analytics (GA alternative)
- `subagent-patterns.md` — subagent usage patterns
- `agent-architecture.md` — AI agent orchestrator details

## Key Files

### Common
- `services/common/auth.py` — AuthContext, JWT decode
- `services/common/db.py` — Engine factory, async sessions, tenant filtering
- `services/common/entitlements.py` — EntitlementGuard middleware

### Frontend
- `apps/web/app/layout.tsx` — Root layout with AnalyticsProvider + Vercel Analytics
- `apps/web/components/dashboard/sidebar.tsx` — Navigation with lifecycle/journey children
- `apps/web/components/modules/` — Per-module dashboard components
- `apps/web/lib/analytics/tracker.ts` — First-party tracking SDK
- `apps/web/lib/lifecycle-api.ts` — Lifecycle API client
- `apps/web/lib/journey-api.ts` — Journey Engine API client

### Cancel Flow
- `services/journey_engine/main.py` — Rule engine, cancel trigger/respond, offer selection
- `services/journey_engine/rule_engine.py` — Rule evaluation (AND/OR groups)
- `services/journey_engine/journey_manager.py` — Customer snapshot, offer eligibility
- `services/lifecycle/main.py` — Lifecycle stages, from-sale bridge, from-journey bridge
- `services/lifecycle/models.py` — 5 lifecycle tables

## Known Gaps

1. Portal cancel button not yet wired to Journey Engine (offer display UI)
2. Sales service uses raw SQL (not async SQLAlchemy)
3. CRM/leads/notes routes still use sync `session.query()`
4. Inventory service has no routes/auth/DB
5. Finance service needs DB persistence
6. FNO adapters all stubbed
7. No circuit breaker on cross-service calls (journey→lifecycle bridge has basic try/except)
8. Web portal cannot be built/run on VM (resource-constrained). Must use local machine or Docker.
