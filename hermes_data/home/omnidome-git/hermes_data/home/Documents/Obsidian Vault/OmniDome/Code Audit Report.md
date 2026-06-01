# OmniDome — Code Audit Report

> Full audit of all 16 microservice implementations. Date: 2026-05-31.

## Overall Assessment

The codebase is **well-architected for v0.1** — clean separation, consistent patterns, good use of FastAPI + SQLAlchemy 2.0. However, significant gaps exist across most services.

## Critical Gaps (Production Blockers)

### 1. 8 Services Have No Route Definitions
These services are **empty shells** with only mock/hardcoded data:
- `analytics` — 66 lines, no routes, no auth, hardcoded strings
- `call_center` — 369 lines, entirely mock data
- `finance` — 146 lines, hardcoded GAAP data (has routes but no DB)
- `hr` — 116 lines, no routes, no auth, mock employee data
- `inventory` — 142 lines, mock stock data
- `iot` — 104 lines with routes but all mock telemetry
- `rica` — 99 lines, mock identity verification
- `support` — 106 lines, mock ticket CRUD with no DB persistence

### 2. Synchronous DB Calls in Async Context (Fixed ✅)
- CRM `database.py` used `sessionmaker` (sync) in async FastAPI
- Fixed: converted to `async_sessionmaker` + `AsyncSession`

### 3. Billing Creates R0.00 Invoices
- `invoices.py` line 68-71: line items hardcoded to "0.00"
- No actual subscription/package lookup

### 4. Missing Service Endpoints
- Network has no `GET /services` endpoint (CRM 360 view calls it)
- Support, RICA, IoT have no actual DB persistence

## Major Gaps

### Cross-Service Calls Lack Resilience
- CRM calls billing/support/network synchronously
- Billing webhook calls network during webhook processing
- No circuit breaker, no retry (Fixed ✅ — added to `services/common/`)

### Inconsistent Pagination
- Some list endpoints return all results (CRM segments)
- No cursor-based navigation anywhere

### FNO Adapters All Stubbed
- Vumatel, Openserve, MetroFibre, Frogfoot, Octotel — all return mock data

## Service Readiness

| Service | Routes | Auth | DB | Real Logic | Ready? |
|---------|--------|------|-----|------------|--------|
| CRM | ✅ | ✅ | ✅ | ✅ | 🟡 |
| Billing | ✅ | ✅ | ✅ | 🟡 (R0 invoices) | 🟡 |
| Network | ✅ | ✅ | ✅ | 🟡 (FNO stubs) | 🟡 |
| Sales | ✅ | ✅ | ✅ | 🟡 (unaudited) | 🟡 |
| Gateway | ✅ | ✅ | N/A | ✅ | ✅ |
| Communication | ✅ | ✅ | ✅ | ✅ (NEW) | ✅ |
| Agent Orchestrator | ✅ | ✅ | ✅ | ✅ (NEW) | ✅ |
| Support | ✅ | ✅ | ✅ | ✅ (NEW) | ✅ |
| Analytics | ✅ | ✅ | ✅ | ✅ (NEW) | ✅ |
| Retention | ✅ | ✅ | ❌ | ❌ mock | 🔴 |
| Call Center | ✅ | ✅ | ❌ | ❌ mock | 🔴 |
| Finance | ✅ | ❌ | ❌ | 🟡 hardcoded | 🟡 |
| HR | ❌ | ❌ | ❌ | ❌ mock | 🔴 |
| Inventory | ❌ | ❌ | ❌ | ❌ mock | 🔴 |
| IoT | ✅ | ❌ | ❌ | ❌ mock | 🔴 |
| RICA | ❌ | ❌ | ❌ | ❌ mock | 🔴 |

## Related Notes

- [[OmniDome — Agentic Architecture]]
- [[OmniDome — Implementation Status]]
