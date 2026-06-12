---
type: module-memory
module: admin
service: services/admin
frontend: apps/web/components/modules/admin-module.tsx
port: 8013
status: integrated
---

# Admin

## Purpose

The admin module is the platform control plane for tenants, module entitlements, users, audit logs, and commission tiers.

## Current Wiring

- Backend service: `services/admin`
- Compose service name: `admin`
- Service port: `8013`
- Frontend module: `apps/web/components/modules/admin-module.tsx`
- Web proxy: `apps/web/app/api/admin/[...path]/route.ts`
- Client API: `apps/web/lib/admin-api.ts`
- Dashboard route: `admin`
- Sidebar label: `Admin`
- Entitlement module key: `admin`

## Frontend Capabilities

- Lists tenants and active tenant counts.
- Lists catalog modules.
- Shows and toggles tenant module entitlements.
- Lists scoped users.
- Shows recent audit events.
- Shows commission tiers.

## Notes

The web proxy injects local development admin headers when upstream auth headers are absent only outside production, or when `ADMIN_PROXY_ALLOW_DEV_HEADERS=true` is explicitly set. Production should pass real auth context through the gateway or identity layer.

## Build Logs

- [[../10-build-log/2026-06-10-admin-frontend-module]]
