# OmniDome Daily Review — 2026-07-31 — services/analytics

## Today's plan
Component **analytics** (8 of 35 in rotation: 5 apps + 29 services + 1 integration). Previous: agent_orchestrator (2026-07-30).
Files reviewed: main.py (1386 lines), models.py, requirements.txt, Dockerfile.

## What was found / achieved

### Hardcoded / fake data presented as live metrics (highest concern)
In `_populate_widget_data` (main.py ~lines 745–1060), several dashboard widgets return hardcoded placeholder values with no data source:
- `network_uptime` → always `99.9%` (also hardcoded in `executive_summary` response, line ~300)
- `avg_health_score` → `72.5` with fake delta `+2.1`
- `nps` → `42.0` with fake delta `+5.3`
- `health_distribution` → static `[65, 20, 10, 5]`
- `retention_curve` → static `[100, 85, 74, 62, 51]`
- `avg_throughput` → `125.4 Mbps` with fake delta `+3.2`
- `mrr_movement` → static `[15000, 8000, -3000, -5000]`
These will render as real KPIs on customer/exec dashboards. Production blocker.

### Executive summary stub fields
`executive_summary` (line ~120) hardcodes `mrr_growth_pct=0`, `churn_rate_pct=0`, `nps_avg=0`, `ltv_estimate=0`, `network_uptime_pct=99.9`. MRR itself is a naive `total_revenue / days * 30` approximation, not true recurring revenue.

### Routing bug — templates endpoint unreachable
`GET /dashboards/templates` is declared **after** `GET /dashboards/{dashboard_id}` (UUID-typed). FastAPI matches routes in declaration order, so `/dashboards/templates` hits the UUID route and returns 422. Move the templates route above the parameterized one.

### Error handling
- Startup `create_all` wrapped in `except Exception: pass` (line ~48) — silent schema-creation failure.
- ~15 broad `try/except Exception` blocks silently coerce DB errors to zeros/empty lists — a broken schema or missing cross-service table looks identical to "no data". At minimum log at WARNING, not swallowed/DEBUG.

### Other
- Inconsistent payment status values: `executive_summary` uses `p.status = 'paid'` in one CASE while all other queries use `p.status = 'completed'` — one of these is wrong; revenue figures will disagree between endpoints.
- Dead code: `RevenueBreakdown`, `ChurnAnalytics`, `NetworkAnalytics`, `CustomerCohort` Pydantic schemas defined but never used; `CustomerCohort` cohort endpoint doesn't exist.
- Queries hit other services' tables directly (payments, invoices, customers, leads, tickets, retention_cases, radius_*, session_tracking, form_events) — assumes single shared Postgres schema; any drift in those services breaks analytics silently (see error-handling point).
- Dockerfile & Docker hygiene: good (non-root user, healthcheck, multistage). No hardcoded credentials found.

## Critical decisions / flags
1. **Fake KPI widgets**: decide whether to (a) wire nps/health/uptime/throughput/mrr_movement to real sources (NPS surveys, monitoring, RADIUS accounting, billing ledger) or (b) mark them "no data" in the UI until sources exist. Shipping fabricated numbers to execs/customers is a trust risk.
2. **Payment status vocabulary**: `'paid'` vs `'completed'` — needs one canonical value confirmed against the billing service schema.
3. **Shared-DB coupling**: confirm the intended architecture (shared schema vs per-service DB). If per-service, most of this service's queries need to move to API calls or a warehouse.
4. **Route fix** for `/dashboards/templates` is unambiguous — safe to fix any time.

## Tomorrow's component
**services/billing** (9 of 35).
