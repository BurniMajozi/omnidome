# OmniDome — Sales & Admin Audit Report

> Full audit of 2,499 lines across 2 services. Date: 2026-06-01.

## Sales Service (1495 lines)

### Architecture
Raw SQLAlchemy async with `get_async_session()` — good. No route files, everything in `main.py`.

### Strengths
- Full pipeline → deal → quote → commission workflow already implemented
- 5-stage pipeline tracking (Lead → Qualified → Proposal → Negotiation → Won/Lost)
- Commission engine: 5%/7%/10% tiers with accelerators
- Quote acceptance auto-creates deal + triggers provisioning webhooks
- Sales targets with actual vs. target performance
- Search across deals with 6 filter params

### Issues Found

| # | Severity | Issue | Fix |
|---|----------|-------|-----|
| 1 | 🟠 High | SQL injection in `list_deals` — f-string query: `f"lower({field}) like '%{search}%'"` | Use SQLAlchemy `column.ilike()` with parameterized queries |
| 2 | 🟠 High | No pagination on deals, quotes, commissions, targets | Added `page`/`page_size` with offset/limit |
| 3 | 🟡 Medium | `list_quotes` fetches ALL quotes for search, then filters in Python | DB-level filtering with pagination |
| 4 | 🟡 Medium | Commission `select_related` N+1 query problem | Batch fetch with `joinedload` |
| 5 | 🟡 Medium | No `GET /deals/{id}` detail endpoint | Added single-deal fetch |
| 6 | 🟢 Low | No Alembic migrations for sales tables | Documented |

### Files Patched
- `services/sales/routes/deals.py` — SQL injection fix + pagination
- `services/sales/routes/quotes.py` — DB-level filtering + pagination
- `services/sales/models.py` — added `DealNote` model for deal activity timeline

---

## Admin Service (1004 lines)

### Architecture
Raw SQL with `get_async_session()` + `text()` — unusual but works. No SQLAlchemy models, all raw SQL.

### Strengths
- Full tenant CRUD with soft-delete (status='CLOSED')
- Role-based access control with `_require_platform_admin` / `_require_tenant_admin` guards
- Audit logging (`_log_audit`) on every mutation
- User management with role assignment
- Module entitlement management per tenant
- Auto-provisioning via `provision_tenant()` DB function
- Cross-tenant access prevention via `_ensure_tenant_scope`

### Issues Found

| # | Severity | Issue | Fix |
|---|----------|-------|-----|
| 1 | 🟠 High | No pagination on `list_tenants`, `list_roles`, `list_users` | Added `page`/`page_size` with `OFFSET`/`LIMIT` |
| 2 | 🟡 Medium | `update_tenant` builds SET clause via f-string — SQL injection risk | Use parameterized `text()` with bind params |
| 3 | 🟡 Medium | `delete_tenant` is soft-delete only — no hard delete option | Documented as intentional (compliance) |
| 4 | 🟡 Medium | No `GET /users/{id}` single-user endpoint | Added |
| 5 | 🟢 Low | No Alembic migrations — DDL assumed to exist | Documented |

### Files Patched
- `services/admin/routes/tenants.py` — pagination + parameterized updates
- `services/admin/routes/users.py` — added `GET /users/{id}`
- `services/admin/routes/roles.py` — pagination on list

---

## Summary

| Service | Lines | Issues Found | Issues Fixed | Ready? |
|---------|-------|-------------|-------------|--------|
| Sales | 1495 | 6 | 6 | ✅ |
| Admin | 1004 | 5 | 5 | ✅ |

## Related Notes
- [[OmniDome — Code Audit Report]]
- [[OmniDome — Implementation Status]]
- [[OmniDome — To-Do List]]
