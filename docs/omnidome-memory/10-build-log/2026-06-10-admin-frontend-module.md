---
type: build-log
project: OmniDome OS
date: 2026-06-10
topic: admin frontend module
---

# Admin Frontend Module

## Summary

Added the admin service into the Next.js dashboard as a first-class frontend module.

## Changes

- Added `/api/admin/[...path]` as a Next.js proxy to the `admin` service on port `8013`.
- Expanded `apps/web/lib/admin-api.ts` for tenants, modules, tenant module entitlements, users, audit logs, and commission tiers.
- Added `apps/web/components/modules/admin-module.tsx` with tabs for tenants, modules, users, audit, and commission.
- Wired `Admin` into the dashboard route switch, sidebar navigation, and entitlement map.

## Operational Notes

- The proxy injects local development admin headers when auth context is missing only outside production, or when `ADMIN_PROXY_ALLOW_DEV_HEADERS=true` is explicitly set.
- Tenant module toggles call `PUT /tenants/{tenant_id}/modules`.
- The admin module entitlement key is `admin`.

## Related Notes

- [[../30-modules/admin]]
- [[../30-modules/agent-orchestration]]
