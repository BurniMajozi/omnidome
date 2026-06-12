---
type: module-memory
module: tenant-memory
service: services/tenant_memory
port: 8025
status: active-development
---

# Tenant Memory

## Purpose

Tenant memory is the product-level memory system for each ISP using OmniDome. It stores tenant-scoped operational history, summaries, and recall context for agents and modules.

This is separate from `docs/omnidome-memory`, which records how OmniDome itself is built.

## Current Wiring

- Backend service: `services/tenant_memory`
- Service port: `8025`
- Dockerfile: `services/tenant_memory/Dockerfile`
- Gateway route: `/api/memory`
- Web proxy route: `/svc/memory/...`
- Module entitlement key: `memory`
- Migration: `config/migrations/20260610_add_tenant_memory.sql`

## Data Model

- `tenant_memory_entries`: timestamped memories, events, notes, and source-backed history.
- `tenant_memory_summaries`: compact scope summaries for agent recall.

Every row is scoped by `tenant_id`.

## API Shape

- `POST /api/v1/memories`
- `GET /api/v1/memories`
- `GET /api/v1/memories/{memory_id}`
- `PATCH /api/v1/memories/{memory_id}`
- `PUT /api/v1/summaries/{scope_key}`
- `GET /api/v1/summaries`
- `GET /api/v1/recall`

## Operating Rule

Agents should write raw events as memory entries and periodically promote stable context into summaries.

