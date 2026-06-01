# Journey Engine — Session 4 Implementation Detail

## What was built

A complete cancel-to-save retention journey engine.

### Cancel Flow

1. Customer clicks "Cancel Service" in portal
2. Portal calls POST /cancel/trigger with customer_snapshot
3. Rule Engine evaluates ALL active journeys against customer attributes
4. Highest-priority matching journey selected
5. Offer chosen (primary or fallback based on eligibility)
6. CancelEvent recorded, offer shown to customer
7. Customer responds → POST /cancel/respond {accept/reject}
8. JourneyOutcome recorded → ML feedback loop

### Rule Engine

- 12 customer attributes: risk_score, segment, tenure_months, monthly_spend_zar,
  payment_days_overdue, num_support_tickets_30d, plan_type, region, usage_trend,
  churn_reason, competitor_mention, autopay_enabled
- 10 operators: eq, ne, gt, gte, lt, lte, between, in, not_in, contains
- Rule groups: AND within group, OR between groups
- Priority-based journey selection (highest wins)

### Offer Types

percentage_discount, fixed_discount, plan_downgrade, service_pause,
free_months, loyalty_reward, personal_outreach

### File Locations

Backend: /opt/data/home/omnidome-patches/services/journey_engine/
Frontend: /opt/data/home/omnidome-patches/apps/web/
  - components/modules/journey-builder/journey-builder-dashboard.tsx
  - lib/journey-api.ts
  - app/api/journey-engine/[...path]/route.ts

### Key Decisions

- Standalone service (own database.py, not common/db.py)
- Async SQLAlchemy throughout
- Rule evaluation is synchronous (pure Python, in-memory)
- Offer eligibility checked after journey matching
