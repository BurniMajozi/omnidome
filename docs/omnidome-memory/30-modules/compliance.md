---
type: module-memory
module: compliance
service: services/compliance
port: 8019
status: active-development
---

# Compliance Module

## Purpose

The compliance module manages South African telecom and ISP compliance workflows, including contracts, SLAs, tax, health and safety, CIPC, bylaws, BBBEE, leave, vehicle registrations, foreign worker permits, travel readiness, DR/BCP, ICASA, POPI, RICA, breach registers, and funding opportunities.

## Current Wiring

- Backend service: `services/compliance`
- Service port: `8019`
- Dockerfile: `services/compliance/Dockerfile`
- Gateway route: `/api/compliance`
- Web proxy route: `/svc/compliance/...`
- Web API client: `apps/web/lib/compliance-api.ts`
- Dashboard module: `apps/web/components/modules/compliance-module.tsx`

## Current Notes

- The service is now wired into local and production Compose.
- The frontend compliance API client calls `/svc/compliance`.
- The gateway can route `/api/compliance` to the service.

## Open Questions

- Should the service create its tables at startup, or should compliance schema changes live in `config/master_schema.sql` or migrations?
- Should compliance be exposed directly through the web `/svc` proxy, gateway `/api`, or both?

## Build Logs

- [[../10-build-log/2026-06-10-compliance-wiring-and-agent-isolation]]

