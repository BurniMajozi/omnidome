# Lifecycle Service — Port 8018

## Purpose
Centralized customer lifecycle state machine. Tracks every customer's journey from Lead → Churned → Reactivated.

## Models (5 tables)

| Table | Purpose |
|-------|---------|
| `lifecycle_stages` | Configurable stages per tenant (Lead, Qualified, Proposal, Converted, Onboarding, Active, At Risk, Churned, Reactivated) |
| `lifecycle_events` | Audit trail of every state transition with trigger_source |
| `customer_lifecycles` | Current state per customer (health_score, MRR, churn_probability) |
| `customer_segment_assignments` | Segment membership tracking |
| `lifecycle_summaries` | Aggregated metrics (new/churned/reactivated per period) |

## API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/lifecycle/stages?tenant_id=` | Create default stages (idempotent) |
| GET | `/lifecycle/stages?tenant_id=` | List tenant stages |
| PUT | `/lifecycle/stages/{id}?tenant_id=` | Update stage |
| POST | `/lifecycle/transition?tenant_id=` | Move customer to new stage |
| GET | `/lifecycle/events?tenant_id=` | List transition events |
| GET | `/lifecycle/customer/{id}?tenant_id=` | Get customer lifecycle state |
| GET | `/lifecycle/customers?tenant_id=` | List lifecycles (filter by stage, risk, health) |
| GET | `/lifecycle/dashboard?tenant_id=` | Aggregated metrics |
| GET | `/lifecycle/funnel?tenant_id=` | Stage transition funnel |
| POST | `/lifecycle/from-sale` | Sales bridge (deal close-won) |
| POST | `/lifecycle/from-journey` | Journey Engine bridge (cancel outcome) |
| GET | `/lifecycle/context/{customer_id}?tenant_id=` | Full lifecycle + events + available stages |

## Cross-Service Bridges

### Sales → Lifecycle (from-sale)
Called when deal closes. Sets customer stage = "Converted", records MRR, timestamps.

### Journey Engine → Lifecycle (from-journey)
Called on cancel outcome:
- **accept** → stage = "Active", health +15, churn_prob = 10%
- **reject** → stage = "Churned", churn_prob = 100%
- **expired** → stage = "At Risk", churn_prob = 75%

## File Locations
- Backend: `services/lifecycle/` (models, database, main, Dockerfile, requirements)
- Frontend: `apps/web/components/modules/lifecycle/`
- API client: `apps/web/lib/lifecycle-api.ts`
- Proxy: `apps/web/app/api/lifecycle/`
- Docker Compose: appended to `docker-compose.yaml`
