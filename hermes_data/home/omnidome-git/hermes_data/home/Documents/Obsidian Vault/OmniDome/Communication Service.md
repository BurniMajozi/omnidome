# OmniDome — Communication Service

> Replacement for Supabase. Provides chat, messages, tasks, approvals, escalations, and module_data for the Next.js dashboard.

## Overview

**Port:** 8020 | **Module:** communication | **Language:** Python 3.11 + FastAPI + SQLAlchemy 2.0

Implements the communication hub schema that was previously planned as Supabase tables. Now a proper microservice with full CRUD.

## Database Tables

| Table | Purpose | Tenant-Scoped? |
|-------|---------|----------------|
| `channels` | Slack-style channels | ✅ |
| `messages` | Chat messages with threading | Via channel |
| `tasks` | Tasks created from messages | ✅ |
| `approvals` | Approval workflows | ✅ |
| `escalations` | Escalation tickets | ✅ |
| `events` | Immutable event log | ✅ |
| `module_data` | **Dashboard data for Next.js** ❌ (global) |

## API Endpoints

```
Channels:
  POST   /api/v1/channels
  GET    /api/v1/channels
  GET    /api/v1/channels/{id}
  PUT    /api/v1/channels/{id}
  DELETE /api/v1/channels/{id}

Messages:
  POST   /api/v1/channels/{id}/messages
  GET    /api/v1/channels/{id}/messages
  PUT    /api/v1/channels/{id}/messages/{id}
  DELETE /api/v1/channels/{id}/messages/{id}
  POST   /api/v1/channels/{id}/messages/{id}/react

Tasks:
  POST   /api/v1/tasks
  GET    /api/v1/tasks
  GET    /api/v1/tasks/{id}
  PUT    /api/v1/tasks/{id}
  PATCH  /api/v1/tasks/{id}/status

Approvals:
  POST   /api/v1/approvals
  GET    /api/v1/approvals
  GET    /api/v1/approvals/{id}
  POST   /api/v1/approvals/{id}/decide

Escalations:
  POST   /api/v1/escalations
  GET    /api/v1/escalations
  PATCH  /api/v1/escalations/{id}/assign
  PATCH  /api/v1/escalations/{id}/status

Events:
  POST   /api/v1/events
  GET    /api/v1/events

Module Data (replaces Supabase for dashboard):
  POST   /api/v1/module-data          # upsert
  GET    /api/v1/module-data          # list all
  GET    /api/v1/module-data/{name}   # get by name
  PUT    /api/v1/module-data/{name}   # update
  DELETE /api/v1/module-data/{name}   # delete
```

## Module Data — Dashboard Bridge

The `module_data` table stores JSONB payloads keyed by module name. The Next.js dashboard fetches from this instead of Supabase.

**Module names:** sales, crm, service, retention, network, call_center, marketing, compliance, talent, billing, finance, products, portal

**API pattern:**
```
GET  /api/v1/module-data/sales     → { data: {...}, updated_at: "..." }
POST /api/v1/module-data           → { module_name: "sales", payload: {...} }
```

## Next.js Client Library

Located at `apps/web/lib/supabase/`:
- `client.ts` — browser Supabase client
- `server.ts` — server-side client with service role
- `module-data.ts` — CRUD helpers for module_data
- `realtime.ts` — polling-based live updates (SSE)

## Why Not Supabase?

1. Data sovereignty — everything stays on-prem (POPIA)
2. Unified auth — uses existing OmniDome JWT/header auth
3. Single database — no split between Supabase and Postgres
4. Microservice pattern consistency

## Related Notes

- [[OmniDome — Agentic Architecture]]
- [[OmniDome — Implementation Status]]
