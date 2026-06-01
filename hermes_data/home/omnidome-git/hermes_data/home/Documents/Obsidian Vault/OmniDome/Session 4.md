# Session 4 — 2026-06-01 (Night, continued)

## Work Completed

### 1. Lifecycle Service (`lifecycle` — port 8018)

Full customer lifecycle tracking — Lead → Customer → Active → At-Risk → Churned.

**Backend (5 tables):**
- `lifecycle_stages` — configurable stages per tenant (Lead, Qualified, Proposal, Converted, Onboarding, Active, At Risk, Churned, Reactivated)
- `lifecycle_events` — audit trail of every state transition with trigger_source (sale, journey_engine, manual)
- `customer_lifecycles` — current lifecycle state per customer with health_score, MRR, risk flags
- `customer_segment_assignments` — segment membership tracking
- `lifecycle_summaries` — aggregated metrics for dashboards

**API Endpoints (15+):**
- `POST /lifecycle/stages` — create default stages for tenant
- `POST /lifecycle/transition` — move customer to new stage
- `GET /lifecycle/events` — list transition events
- `GET /lifecycle/customer/{id}` — get customer lifecycle state
- `GET /lifecycle/customers` — list all lifecycles with filtering
- `GET /lifecycle/dashboard` — aggregated metrics
- `GET /lifecycle/funnel` — stage transition funnel
- `POST /lifecycle/from-sale` — bridge from sales service (deal close-won)
- `POST /lifecycle/from-journey` — bridge from journey engine (cancel outcome)

### 2. Lifecycle Dashboard (Frontend)

`apps/web/components/modules/lifecycle/lifecycle-dashboard.tsx`
- 4 tabs: Overview, Funnel, Customers, Activity Feed
- KPI cards: Active Customers, Total MRR, At Risk, Events, Health
- Stage distribution bar chart, Risk pie chart, MRR by stage
- Funnel visualization with stage flow
- Customer list with stage filter + health scores + risk flags
- Activity feed with recent transitions

### 3. Cross-Service Bridges

**Journey Engine → Lifecycle:**
- Added lifecycle bridge call in cancel_respond endpoint
- On accept: customer stays Active, health boost
- On reject: customer marked Churned, churn_probability = 100%
- On expired: customer marked At Risk, churn_probability = 75%

**Sales → Lifecycle (patch):**
- SALES_LIFECYCLE_BRIDGE_PATCH.md documents the integration
- close_deal_won → POST /lifecycle/from-sale → customer stage = Converted

### 4. Files Created/Modified

| File | Type | Description |
|------|------|-------------|
| `lifecycle/models.py` | NEW | 5 tables: stages, events, lifecycles, segments, summaries |
| `lifecycle/main.py` | NEW | 15+ API endpoints + sale/journey bridges |
| `lifecycle/database.py` | NEW | Async SQLAlchemy sessions |
| `services/lifecycle/` | NEW | Dockerfile + requirements + __init__.py |
| `apps/web/lib/lifecycle-api.ts` | NEW | Typed API client |
| `apps/web/components/modules/lifecycle/` | NEW | Lifecycle Dashboard UI |
| `apps/web/app/api/lifecycle/` | NEW | API proxy route |
| `docker-compose-lifecycle.yaml` | NEW | Port 8018 |
| `journey_engine/main.py` | MODIFIED | Added lifecycle bridge call in cancel_respond |
| `SALES_LIFECYCLE_BRIDGE_PATCH.md` | NEW | Patch guide for sales → lifecycle integration |

## Complete Service Architecture (21 services)

```
Sales (8002) ──deal close──→ Lifecycle (8018) ←──cancel outcome── Journey Engine (8017)
CRM (8001) ←──customer ──── Lifecycle (8018)                        ↑
Billing (8003) ←──────────── Lifecycle (8018)              Portal cancel button
```

## Next Steps

### Remaining for full lifecycle integration:
1. Apply: `bash omnidome-patches/apply-all-patches.sh`
2. Rebuild: `docker compose up -d --build journey_engine web_analytics lifecycle`
3. Wire portal cancel button → Journey Engine → Lifecycle
4. Convert Sales service raw SQL → async SQLAlchemy
5. Add CRM 360 lifecycle panel (show stage + funnel in customer view)

## Related Notes
- [[OmniDome — Project Index]]
- [[OmniDome — Implementation Status]]
- [[Session 2026-06-01]]
