# Customer 360 / CX / CRM / CVM — View Design Document

## Overview

Four tabbed views in the operator dashboard (`apps/web`) that unify data from 8+ microservices into coherent customer profiles. All views share `customer_id` as the primary join key and `tenant_id` for multi-tenant scoping.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Operator Dashboard                          │
│                     apps/web/app/customer-360/                     │
├────────────┬────────────┬────────────┬────────────────────────────┤
│  Customer  │     CX     │    CRM     │          CVM              │
│  Details   │  (Journey) │  (Sales)   │  (Value & Risk)           │
├────────────┴────────────┴────────────┴────────────────────────────┤
│                    API Gateway (port 8000)                         │
├────────┬────────┬────────┬────────┬────────┬────────┬─────────────┤
│  CRM   │Billing │Journey │ Sales  │Support │Lifecycle│ Retention  │
│  8001  │  8003  │  8022  │  8002  │  8008  │  8018   │   8012     │
└────────┴────────┴────────┴────────┴────────┴────────┴─────────────┘
```

## Common Keys & Descriptions

| Key | Type | Description | Source Table |
|-----|------|-------------|--------------|
| `customer_id` | UUID | Primary join key across all views | `crm.customers.id` |
| `tenant_id` | UUID | Multi-tenant scoping | All tables |
| `account_number` | String | Customer-facing account identifier | `crm.customers.account_number` |
| `company_id` | UUID | Company link (corporate accounts) | `crm.companies.id` |
| `property_id` | UUID | Physical address/property | `crm.properties.id` |
| `billing_account_id` | UUID | Billing entity | `billing.billing_accounts.id` |
| `subscription_id` | UUID | Active service subscription | `billing.subscriptions.id` |
| `order_id` | UUID | Sales order | `customer_journey.orders.id` |
| `deal_id` | UUID | Sales deal | `sales.deals.id` |
| `ticket_id` | UUID | Support ticket | `support.tickets.id` |
| `lifecycle_id` | UUID | Lifecycle state | `lifecycle.customer_lifecycles.id` |
| `prediction_id` | UUID | Churn prediction | `retention.retention_predictions.id` |

---

## TAB 1: Customer Details

**Purpose:** Complete identity, contact, address, and account information.

### Data Sources & Tables

| Section | Service | Table | Key Fields | Join Key |
|---------|---------|-------|------------|----------|
| **Identity** | CRM | `customers` | `first_name`, `last_name`, `email`, `phone`, `id_number`, `rica_verified`, `status`, `account_number` | `customer_id` |
| **Company** | CRM | `companies` | `name`, `registration_number`, `industry`, `contact_person`, `billing_email`, `payment_terms`, `credit_limit_zar` | `customers.company_id` → `companies.id` |
| **Properties** | CRM | `properties` | `name`, `line1`, `line2`, `city`, `province`, `postal_code`, `gps_lat`, `gps_lng`, `property_type`, `is_active` | `customer_id` → `properties.owner_customer_id` |
| **Property Accounts** | CRM | `property_accounts` | `account_number`, `relationship_type`, `is_primary`, `is_active`, `activated_at`, `company_id` | `customer_id` → `property_accounts.customer_id` |
| **Service Addresses** | Journey | `customer_addresses` | `address_type` (service/physical/billing), `line1`, `city`, `postal_code`, `gps_lat`, `gps_lng`, `is_primary` | `customer_id` |
| **Billing Account** | Billing | `billing_accounts` | `account_number`, `account_name`, `billing_email`, `payment_method`, `payment_terms`, `credit_limit_zar`, `status`, `dunning_stage` | `billing_account_id` |
| **Subscriptions** | Billing | `subscriptions` | `plan`, `segment`, `status`, `billing_interval`, `base_price_zar`, `current_period_start`, `current_period_end` | `customer_id` |
| **Payment Methods** | Journey | `payment_methods` | `method_type`, `provider`, `last_four`, `card_brand`, `expiry_month`, `expiry_year`, `bank_name`, `is_default`, `is_active` | `customer_id` |
| **Handover History** | CRM | `account_handovers` | `from_customer_id`, `to_customer_id`, `property_id`, `status`, `trigger`, `equipment_stays`, `completed_at` | `customer_id` (from or to) |

### API Endpoint Design

```
GET /api/crm/customers/{customer_id}/360/details
```

**Response structure:**
```json
{
  "customer": { "id", "first_name", "last_name", "email", "phone", "id_number", "rica_verified", "status", "account_number", "company_id", "created_at" },
  "company": { "id", "name", "registration_number", "industry", "billing_email", "payment_terms", "credit_limit_zar" } | null,
  "properties": [{ "id", "name", "line1", "city", "province", "postal_code", "property_type", "is_active" }],
  "property_accounts": [{ "id", "account_number", "relationship_type", "is_primary", "is_active", "activated_at", "company_id" }],
  "service_addresses": [{ "id", "address_type", "line1", "city", "postal_code", "is_primary" }],
  "billing_account": { "id", "account_number", "account_name", "billing_email", "payment_terms", "credit_limit_zar", "status", "dunning_stage" } | null,
  "subscriptions": [{ "id", "plan", "segment", "status", "billing_interval", "base_price_zar", "property_id" }],
  "payment_methods": [{ "id", "method_type", "last_four", "card_brand", "is_default", "is_active" }],
  "handover_history": [{ "id", "property_id", "from_customer_id", "to_customer_id", "status", "trigger", "completed_at" }]
}
```

### Frontend Components

| Component | Description |
|-----------|-------------|
| `CustomerIdentityCard` | Name, email, phone, ID, RICA status badge |
| `CompanyAffiliationCard` | Company name, role, billing terms (if corporate) |
| `PropertiesTable` | List of owned/rented properties with addresses |
| `SubscriptionsTable` | Active subscriptions with plan, status, pricing |
| `PaymentMethodsList` | Stored payment instruments |
| `BillingAccountSummary` | Account number, terms, dunning stage, credit limit |
| `HandoverTimeline` | Visual timeline of tenant handovers |

---

## TAB 2: Customer Experience (CX)

**Purpose:** End-to-end journey tracking — orders, deliveries, installations, support, and activity timeline.

### Data Sources & Tables

| Section | Service | Table | Key Fields | Join Key |
|---------|---------|-------|------------|----------|
| **Orders** | Journey | `orders` | `order_number`, `status`, `total_zar`, `payment_status`, `promo_code`, `confirmed_at`, `completed_at` | `customer_id` |
| **Order Items** | Journey | `order_items` | `item_type`, `description`, `quantity`, `unit_price_zar`, `monthly_recurring_zar`, `serial_number` | `order_id` |
| **Deliveries** | Journey | `delivery_tracking` | `courier`, `tracking_number`, `status`, `scheduled_date`, `delivered_at`, `signed_by` | `order_id` |
| **Technician Visits** | Journey | `technician_visits` | `visit_type`, `status`, `scheduled_date`, `technician_name`, `customer_rating`, `work_completed` | `customer_id` |
| **Support Tickets** | Support | `tickets` | `subject`, `priority`, `status`, `category`, `assigned_to`, `is_fcr`, `resolved_at`, `created_at` | `customer_id` |
| **Ticket Replies** | Support | `ticket_replies` | `author_type`, `message`, `is_private`, `created_at` | `ticket_id` |
| **Activity Timeline** | Journey | `activity_timeline` | `event_type`, `event_category`, `summary`, `source_service`, `created_at` | `customer_id` |
| **Promotions** | Journey | `customer_promotions` | `promotion_id`, `promo_code`, `status`, `applied_at` | `customer_id` |
| **Announcements** | Journey | `announcements` | `announcement_type`, `title`, `content`, `sent_at` | By area/segment |
| **NPS / CSAT** | Sales | `contacts` | `nps_score` | `customer_id` → `contacts.id` |

### API Endpoint Design

```
GET /api/crm/customers/{customer_id}/360/cx
```

**Response structure:**
```json
{
  "orders": [{ "id", "order_number", "status", "total_zar", "payment_status", "confirmed_at", "completed_at", "items": [...] }],
  "deliveries": [{ "id", "order_id", "courier", "tracking_number", "status", "scheduled_date", "delivered_at" }],
  "technician_visits": [{ "id", "visit_type", "status", "scheduled_date", "technician_name", "customer_rating", "work_completed" }],
  "support_tickets": [{ "id", "subject", "priority", "status", "category", "is_fcr", "created_at", "resolved_at", "reply_count" }],
  "activity_timeline": [{ "id", "event_type", "event_category", "summary", "source_service", "created_at" }],
  "promotions": [{ "id", "promo_code", "status", "applied_at" }],
  "nps_score": 72,
  "cx_summary": {
    "total_orders": 3,
    "open_tickets": 1,
    "avg_technician_rating": 4.5,
    "last_interaction": "2026-06-07T14:30:00Z",
    "lifecycle_stage": "active"
  }
}
```

### Frontend Components

| Component | Description |
|-----------|-------------|
| `OrderHistoryTable` | All orders with status, totals, items |
| `DeliveryTracker` | Courier tracking with status timeline |
| `TechnicianVisitsTable` | Scheduled/completed visits with ratings |
| `SupportTicketsList` | Open/closed tickets with priority badges |
| `ActivityTimeline` | Unified chronological event feed (orders, tickets, visits, payments) |
| `CXScoreCard` | NPS, CSAT, ticket count, avg resolution time |
| `PromotionsApplied` | Active/used promotions |

---

## TAB 3: CRM

**Purpose** — Sales pipeline, deals, quotes, commissions, segments, and lead management.

### Data Sources & Tables

| Section | Service | Table | Key Fields | Join Key |
|---------|---------|-------|------------|----------|
| **Leads** | CRM | `leads` | `source`, `status`, `coverage_area`, `interested_package`, `assigned_to`, `converted_customer_id` | `customer_id` (converted) |
| **Deals** | Sales | `deals` | `name`, `amount`, `value_zar`, `status`, `stage_id`, `close_date`, `close_reason` | `contact_id` → customer |
| **Deal Stages** | Sales | `deal_stages` | `name`, `probability`, `sort_order` | `deal.stage_id` |
| **Quotes** | Sales | `quotes` | `items`, `total_monthly`, `total_once_off`, `term_months`, `status`, `valid_until`, `sent_at`, `accepted_at` | `customer_id` |
| **Commissions** | Sales | `commissions` | `agent_id`, `amount_zar`, `rate_percent`, `status` | `deal_id` |
| **Segments** | CRM | `segments` | `name`, `description` | Via `customer_segments` |
| **Customer Tags** | CRM | `customer_tags` | `tag` | `customer_id` |
| **Customer Notes** | CRM | `customer_notes` | `content`, `author_id`, `created_at` | `customer_id` |
| **Contacts** | Sales | `contacts` | `first_name`, `last_name`, `email`, `phone`, `lifecycle_stage`, `nps_score` | `customer_id` |
| **Lifecycle** | Lifecycle | `customer_lifecycles` | `current_stage`, `health_score`, `is_at_risk`, `churn_probability`, `monthly_recurring_revenue` | `customer_id` |
| **Lifecycle Events** | Lifecycle | `lifecycle_events` | `from_stage`, `to_stage`, `trigger_source`, `reason`, `created_at` | `customer_id` |

### API Endpoint Design

```
GET /api/crm/customers/{customer_id}/360/crm
```

**Response structure:**
```json
{
  "lead": { "id", "source", "status", "coverage_area", "interested_package", "converted_at" } | null,
  "deals": [{ "id", "name", "amount", "value_zar", "status", "stage", "probability", "close_date", "agent_id" }],
  "quotes": [{ "id", "total_monthly", "total_once_off", "term_months", "status", "valid_until", "sent_at", "accepted_at" }],
  "commissions": [{ "id", "agent_id", "amount_zar", "rate_percent", "status" }],
  "segments": [{ "id", "name" }],
  "tags": [{ "tag" }],
  "notes": [{ "id", "content", "author_id", "created_at" }],
  "lifecycle": {
    "current_stage": "active",
    "health_score": 78,
    "is_at_risk": false,
    "churn_probability": 0.12,
    "monthly_recurring_revenue": 899.00,
    "first_contact_at": "2025-01-15T10:00:00Z",
    "converted_at": "2025-02-01T14:00:00Z",
    "last_payment_at": "2026-06-01T00:00:00Z",
    "lifecycle_events": [{ "from_stage", "to_stage", "trigger_source", "created_at" }]
  },
  "crm_summary": {
    "total_deals_value": 15000.00,
    "active_deals": 2,
    "won_deals": 5,
    "lost_deals": 1,
    "quotes_sent": 3,
    "quotes_accepted": 2
  }
}
```

### Frontend Components

| Component | Description |
|-----------|-------------|
| `LeadOriginCard` | Lead source, coverage area, conversion date |
| `DealPipelineBoard` | Kanban-style deal stages with values |
| `QuotesTable` | Sent/accepted/expired quotes with terms |
| `CommissionsList` | Agent commissions per deal |
| `SegmentBadges` | Customer segment membership tags |
| `NotesThread` | Internal notes with author and timestamp |
| `LifecycleStageIndicator` | Current stage, health score, risk flags |
| `LifecycleTransitionHistory` | Stage change timeline |

---

## TAB 4: Customer Value Management (CVM)

**Purpose:** Financial value, churn risk, retention metrics, and lifetime value analysis.

### Data Sources & Tables

| Section | Service | Table | Key Fields | Join Key |
|---------|---------|-------|------------|----------|
| **Invoices** | Billing | `invoices` | `number`, `status`, `total_zar`, `amount_paid_zar`, `due_date`, `billing_period_start` | `customer_id` |
| **Payments** | Billing | `payments` | `amount_zar`, `method`, `status`, `reference`, `created_at` | `customer_id` |
| **Dunning** | Billing | `dunning_actions` | `action_type`, `scheduled_at`, `executed_at`, `result` | `invoice_id` |
| **Arrangements** | Billing | `payment_arrangements` | `total_owed_zar`, `installment_zar`, `installments_paid`, `status`, `next_due_date` | `customer_id` |
| **Churn Predictions** | Retention | `retention_predictions` | `risk_score`, `risk_level`, `churn_probability`, `nps_score`, `created_at` | `customer_id` |
| **Lifecycle** | Lifecycle | `customer_lifecycles` | `health_score`, `is_at_risk`, `churn_probability`, `monthly_recurring_revenue`, `first_payment_at`, `last_payment_at` | `customer_id` |
| **Subscriptions** | Billing | `subscriptions` | `plan`, `base_price_zar`, `segment`, `status`, `billing_interval` | `customer_id` |
| **Usage** | Billing | `subscription_usage` | `metric`, `quantity`, `unit_price_zar`, `recorded_at` | `subscription_id` |
| **Cancellations** | Billing | `cancellation_requests` | `cancel_type`, `cancel_reason`, `status`, `effective_date` | `customer_id` |
| **Termination Fees** | Billing | `termination_fees` | `total_etf_zar`, `router_charge_zar`, `paid_zar` | `customer_id` |
| **Router Returns** | Billing | `router_returns` | `serial_number`, `status`, `condition`, `refund_amount_zar` | `customer_id` |
| **Transfers** | Billing | `subscription_transfers` | `from_customer_id`, `to_customer_id`, `transfer_date`, `status`, `from_prorated_amount_zar`, `to_prorated_amount_zar` | `customer_id` (from or to) |
| **Collection Events** | Billing Collections | `collection_events` | `event_type`, `amount_zar`, `status`, `created_at` | `customer_id` |

### Computed Metrics

| Metric | Formula | Source |
|--------|---------|--------|
| **MRR** | Sum of active subscription `base_price_zar` | `subscriptions` |
| **ARR** | MRR × 12 | Computed |
| **LTV** | Sum of all `invoice.total_zar` (paid) | `invoices` |
| **ARPA** | LTV / months since first payment | Computed |
| **Payment Reliability** | `paid_invoices / total_invoices` × 100 | `invoices` |
| **Avg Days to Pay** | Avg(`paid_at - due_date`) for paid invoices | `invoices` + `payments` |
| **Churn Risk Score** | From retention model (0-100) | `retention_predictions` |
| **Health Score** | From lifecycle service (0-100) | `customer_lifecycles` |
| **Outstanding Balance** | Sum of `invoice.total_zar - amount_paid_zar` for unpaid | `invoices` |
| **Dunning Stage** | Current dunning level | `billing_accounts` |
| **NPS** | Latest NPS score | `retention_predictions` or `contacts` |

### API Endpoint Design

```
GET /api/crm/customers/{customer_id}/360/cvm
```

**Response structure:**
```json
{
  "financial_summary": {
    "mrr": 899.00,
    "arr": 10788.00,
    "ltv": 21576.00,
    "arpa": 899.00,
    "outstanding_balance": 0.00,
    "payment_reliability_pct": 98.5,
    "avg_days_to_pay": 3.2,
    "total_invoices": 24,
    "paid_invoices": 23,
    "overdue_invoices": 0
  },
  "invoices": [{ "id", "number", "status", "total_zar", "amount_paid_zar", "due_date", "created_at" }],
  "payments": [{ "id", "amount_zar", "method", "status", "reference", "created_at" }],
  "dunning_actions": [{ "id", "action_type", "scheduled_at", "executed_at", "result" }],
  "payment_arrangements": [{ "id", "total_owed_zar", "installment_zar", "installments_paid", "status", "next_due_date" }],
  "churn_prediction": {
    "risk_score": 25.0,
    "risk_level": "LOW",
    "churn_probability": 0.08,
    "nps_score": 72.0,
    "predicted_at": "2026-06-07T00:00:00Z"
  },
  "health": {
    "score": 78,
    "is_at_risk": false,
    "risk_reason": null,
    "monthly_recurring_revenue": 899.00,
    "first_payment_at": "2025-02-01T00:00:00Z",
    "last_payment_at": "2026-06-01T00:00:00Z"
  },
  "usage_summary": [{ "metric", "total_quantity", "total_cost_zar", "last_recorded" }],
  "cancellation_history": [{ "id", "cancel_type", "cancel_reason", "status", "effective_date" }],
  "transfer_history": [{ "id", "from_customer_id", "to_customer_id", "transfer_date", "status" }],
  "cvm_summary": {
    "customer_tier": "GOLD",
    "value_segment": "HIGH",
    "risk_segment": "LOW",
    "recommended_action": "UPSELL",
    "next_best_offer": "Fibre 200Mbps upgrade"
  }
}
```

### Frontend Components

| Component | Description |
|-----------|-------------|
| `FinancialKPICards` | MRR, ARR, LTV, Outstanding Balance |
| `PaymentReliabilityGauge` | Percentage with trend |
| `InvoiceHistoryTable` | All invoices with status badges |
| `PaymentTimeline` | Chronological payment history |
| `DunningStageIndicator` | Current dunning level with next action |
| `ChurnRiskMeter` | Risk score gauge (0-100) with color coding |
| `HealthScoreCard` | Health score with factor breakdown |
| `UsageChart` | Usage trends over time (data, API calls, etc.) |
| `CustomerTierBadge` | GOLD/SILVER/BRONZE based on value |
| `RecommendedActionsPanel` | AI-driven next-best-action suggestions |
| `CancellationHistory` | Past cancellation requests and outcomes |
| `TransferHistory` | Subscription transfer records |

---

## Implementation Plan

### Phase 1: Backend API Aggregation Layer

Create a new `customer_360` service (port 8025) that aggregates data from all services via internal API calls or direct DB reads.

**New service structure:**
```
services/customer_360/
  main.py                    — FastAPI app
  database.py                — Session management (read-only cross-service)
  models.py                  — Materialized view models (optional)
  routes/
    details.py               — Customer Details aggregation
    cx.py                    — CX aggregation
    crm.py                   — CRM aggregation
    cvm.py                   — CVM aggregation
  aggregators/
    billing.py               — Billing data fetcher
    journey.py               — Journey data fetcher
    sales.py                 — Sales data fetcher
    support.py               — Support data fetcher
    lifecycle.py             — Lifecycle data fetcher
    retention.py             — Retention data fetcher
```

**Alternative:** Add 360 endpoints to the existing CRM service (port 8001) since it already owns the customer domain. This is simpler and avoids a new service.

**Recommended approach:** Add to CRM service. The CRM service already has `customer_id` as its primary key and can aggregate from other services via shared DB reads (all services share the same Supabase Postgres instance).

### Phase 2: Frontend Tabbed Interface

**New page:** `apps/web/app/customer-360/[customer_id]/page.tsx`

```
customer-360/
  [customer_id]/
    page.tsx                 — Tab container
    components/
      CustomerDetailsTab.tsx — Tab 1
      CXTab.tsx              — Tab 2
      CRMTab.tsx             — Tab 3
      CVMTab.tsx             — Tab 4
  components/
    CustomerSearch.tsx       — Customer lookup
    CustomerHeader.tsx       — Shared header with name, status, tier
```

### Phase 3: Cross-Service Data Access

Since all services share the same Supabase Postgres instance, the CRM service can read from other services' tables directly:

```python
# In CRM service, read from billing tables
from services.billing.models import Invoice, Subscription, BillingAccount
from services.customer_journey.models import Order, DeliveryTracking, TechnicianVisit, ActivityTimeline
from services.sales.models import Deal, Quote, Commission
from services.support.database import Ticket
from services.lifecycle.models import CustomerLifecycle, LifecycleEvent
from services.retention.batch_churn import RetentionPrediction
```

**Important:** Use read-only sessions. Never write to other services' tables from the 360 service.

### Phase 4: Caching & Performance

- Cache 360 data per customer with 5-minute TTL
- Use `selectinload` for relationship loading
- Paginate large datasets (invoices, timeline events)
- Lazy-load tabs (fetch data only when tab is activated)

---

## Database Views (Optional Optimization)

For performance, create materialized views that pre-join common 360 queries:

```sql
-- Customer 360 summary view
CREATE MATERIALIZED VIEW mv_customer_360_summary AS
SELECT
  c.id AS customer_id,
  c.tenant_id,
  c.first_name || ' ' || c.last_name AS full_name,
  c.email,
  c.phone,
  c.account_number,
  c.status AS customer_status,
  c.company_id,
  comp.name AS company_name,
  cl.current_stage AS lifecycle_stage,
  cl.health_score,
  cl.is_at_risk,
  cl.churn_probability,
  cl.monthly_recurring_revenue,
  ba.account_number AS billing_account_number,
  ba.status AS billing_status,
  ba.dunning_stage,
  ba.credit_limit_zar,
  rp.risk_score AS churn_risk_score,
  rp.risk_level AS churn_risk_level,
  rp.nps_score,
  (SELECT COUNT(*) FROM support_tickets t WHERE t.customer_id = c.id) AS total_tickets,
  (SELECT COUNT(*) FROM support_tickets t WHERE t.customer_id = c.id AND t.status = 'OPEN') AS open_tickets,
  (SELECT COUNT(*) FROM orders o WHERE o.customer_id = c.id) AS total_orders,
  (SELECT SUM(i.total_zar) FROM invoices i WHERE i.customer_id = c.id AND i.status = 'paid') AS lifetime_value,
  (SELECT SUM(i.total_zar - i.amount_paid_zar) FROM invoices i WHERE i.customer_id = c.id AND i.status NOT IN ('paid', 'voided')) AS outstanding_balance,
  (SELECT COUNT(*) FROM subscriptions s WHERE s.customer_id = c.id AND s.status = 'active') AS active_subscriptions,
  (SELECT MAX(at.created_at) FROM activity_timeline at WHERE at.customer_id = c.id) AS last_activity_at
FROM customers c
LEFT JOIN companies comp ON c.company_id = comp.id
LEFT JOIN customer_lifecycles cl ON c.id = cl.customer_id
LEFT JOIN billing_accounts ba ON c.id = ba.customer_id
LEFT JOIN LATERAL (
  SELECT risk_score, risk_level, nps_score
  FROM retention_predictions rp
  WHERE rp.customer_id = c.id
  ORDER BY rp.created_at DESC
  LIMIT 1
) rp ON true;

CREATE INDEX idx_mv_360_tenant ON mv_customer_360_summary(tenant_id);
CREATE INDEX idx_mv_360_customer ON mv_customer_360_summary(customer_id);
CREATE INDEX idx_mv_360_risk ON mv_customer_360_summary(tenant_id, churn_risk_score);
CREATE INDEX idx_mv_360_stage ON mv_customer_360_summary(tenant_id, lifecycle_stage);

-- Refresh every 5 minutes
-- REFRESH MATERIALIZED VIEW CONCURRENTLY mv_customer_360_summary;
```

---

## Summary: Tables per View

| View | Tables | Services |
|------|--------|----------|
| **Customer Details** | `customers`, `companies`, `properties`, `property_accounts`, `customer_addresses`, `billing_accounts`, `subscriptions`, `payment_methods`, `account_handovers` | CRM, Billing, Journey |
| **CX** | `orders`, `order_items`, `delivery_tracking`, `technician_visits`, `tickets`, `ticket_replies`, `activity_timeline`, `customer_promotions`, `announcements`, `contacts` | Journey, Support, Sales |
| **CRM** | `leads`, `deals`, `deal_stages`, `quotes`, `commissions`, `segments`, `customer_tags`, `customer_notes`, `contacts`, `customer_lifecycles`, `lifecycle_events` | CRM, Sales, Lifecycle |
| **CVM** | `invoices`, `payments`, `dunning_actions`, `payment_arrangements`, `retention_predictions`, `customer_lifecycles`, `subscriptions`, `subscription_usage`, `cancellation_requests`, `termination_fees`, `router_returns`, `subscription_transfers`, `collection_events` | Billing, Retention, Lifecycle, Billing Collections |

**Total unique tables:** 35+ tables across 8 services
**Common join key:** `customer_id` (UUID)
**Multi-tenant scoping:** `tenant_id` on all queries
