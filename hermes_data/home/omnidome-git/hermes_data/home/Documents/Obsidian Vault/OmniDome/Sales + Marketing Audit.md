# Sales + Marketing Audit Report

> Dedicated review of Sales (1495 lines) and Marketing (792 lines). Date: 2026-05-31.

---

## Sales Service (port 8002) — 1495 Lines

### Assessment: 🟢 Well-Implemented — Production Ready with Minor Gaps

This is the **most complete service** in the entire codebase. It uses raw SQL (not SQLAlchemy models) with `text()` queries, which is actually fine for a read-heavy analytical service.

### What's Done Well

- **Full pipeline management** — stages, deals, quotes, commissions, targets
- **Quote-to-deal workflow** → accept quote auto-creates deal → close-won triggers commission + provisioning webhook → `BackgroundTasks` async dispatch
- **Commission engine** with tiered rates (5% / 7% / 10% based on monthly deal count)
- **Sales targets** with actual vs. target performance per agent/team
- **Webhook dispatch** to billing + network + custom provisioning URLs (env-driven)
- **Raw SQL throughout** — consistent pattern using `text()` with parameterised queries

### Gaps Found

| # | Gap | Severity | Fix |
|---|-----|----------|-----|
| 1 | No pagination on `GET /deals` — returns ALL deals | 🟡 Medium | Add LIMIT/OFFSET |
| 2 | `GET /deals` builds SQL via f-string concat — SQL injection risk if filters are user-controlled | 🟠 High | Use SQLAlchemy parameterized queries or validate inputs |
| 3 | No `GET /deals/{deal_id}` single-resource endpoint exists | 🟢 Low | Add or document if intentional |
| 4 | `contact_id` / `amount` are legacy column names alongside `customer_id` / `value_zar` — confusing duality | 🟢 Low | Clean up schema |
| 5 | No Alembic migration — DDL inline in code | 🟡 Medium | Extract to migration files |
| 6 | Uses `get_engine()` sync directly — not the async `get_async_session()` pattern from `common/db.py` | 🟡 Medium | Convert to async |

### Sales DB Schema (inferred from SQL)

```
pipelines (id, tenant_id, name, is_default)
deal_stages (id, pipeline_id, name, probability, sort_order)
deals (id, tenant_id, contact_id, lead_id, agent_id, stage_id, package_id, name, amount, value_zar, status, close_date, closed_at, close_reason, notes, created_at, updated_at)
quotes (id, tenant_id, deal_id, customer_id, lead_id, agent_id, package_id, items JSON, total_monthly, total_once_off, term_months, valid_until, status, terms, created_at, sent_at, accepted_at)
commissions (id, tenant_id, deal_id, agent_id, amount_zar, rate_percent, status, created_at, updated_at)
sales_targets (id, tenant_id, agent_id, team_id, period_type, period_start, period_end, target_value_zar)
```

---

## Marketing Service (port 8014) — 792 Lines

### Assessment: 🟢 Well-Implemented — Most Complete Marketing Module

Excellent architecture with DDL auto-creation, email batching, webhook events, A/B testing, lead scoring, and automation triggers.

### What's Done Well

- **Self-bootstrapping DDL** — `_ensure_marketing_tables()` creates all 7 tables + indexes on startup (idempotent `IF NOT EXISTS`)
- **Full campaign lifecycle** — create, update, delete, list with channel/status filters
- **Email batching with delivery tracking** — queued → sent → delivered/opened/clicked/bounced
- **Webhook endpoint** for email provider callbacks (UniOne/SendGrid pattern)
- **A/B testing** — variant A/B with split %, metric selection, winner tracking
- **Lead scoring** — per-contact score with audit trail
- **Automation engine** — trigger-based (event/schedule/lead_score) with configurable actions
- **Template management** — HTML email templates with categories

### Gaps Found

| # | Gap | Severity | Fix |
|---|-----|----------|-----|
| 1 | `_ensure_marketing_tables()` called on EVERY request (list_campaigns, create_campaign, etc.) | 🟠 High | Call once on startup only, or use Alembic |
| 2 | `DELETE /campaigns/{id}` returns 204 but doesn't cascade delete related batches/events | 🟡 Medium | Add cascade or document as intentional |
| 3 | `GET /templates` has no pagination | 🟡 Medium | Add limit/offset |
| 4 | `POST /email/webhook` has no auth — any caller can inject events | 🟠 High | Add webhook signature verification |
| 5 | No `GET /automations` or `GET /ab-tests` list endpoints | 🟡 Medium | Add list/detail endpoints |
| 6 | No `PATCH /automations/{id}/toggle` to enable/disable | 🟢 Low | Add toggle endpoint |
| 7 | All raw SQL with f-string query building | 🟡 Medium | Consider SQLAlchemy Core for type safety |
| 8 | No integration with CRM audience segments (segment UUID stored but never resolved) | 🟡 Medium | Cross-service call to CRM |

### Marketing DB Schema (from DDL)

```
marketing_campaigns (id, tenant_id, name, channel, status, description, budget_zar, start_date, end_date, audience_segment_id, total_sent/delivered/opened/clicked/conversions, created_at, updated_at)
marketing_email_batches (id, tenant_id, campaign_id, subject, from_name, from_email, total_queued/sent/delivered/bounced/opened/clicked, status, created_at)
marketing_email_events (id, tenant_id, batch_id, recipient_email, event_type, event_data JSONB, created_at)
marketing_templates (id, tenant_id, name, subject, body_html, category, created_at, updated_at)
marketing_audience_segments (id, tenant_id, name, description, rules JSONB, member_count, created_at)
marketing_lead_scores (id, tenant_id, contact_id, score, last_scored_at, UNIQUE(tenant_id, contact_id))
marketing_automations (id, tenant_id, name, trigger_type, trigger_config JSONB, actions JSONB, is_active, total_triggered, created_at)
marketing_ab_tests (id, tenant_id, campaign_id, variant_a JSONB, variant_b JSONB, split_pct, metric, duration_hours, status, winner, created_at)
```

---

## Cross-Cutting Concerns

### 🔴 SQL Injection Risk (Both Services)
Both Sales and Marketing build SQL queries using f-string interpolation:
```python
# Sales line 596
where_clause = " and ".join(conditions)
# ...
f"select ... where {where_clause}"

# Marketing line 294  
filters += " AND channel = :ch"
text(f"SELECT * FROM marketing_campaigns {filters} LIMIT :lim OFFSET :off")
```

While the parameters themselves are bound safely, the **structure** is built via string concatenation. If any user input makes it into the `conditions`/`filters` strings (not just the params dict), it's injectable.

**Fix:** Use SQLAlchemy Core `select()` / `where()` builders, or a query builder library.

### 🟡 No Async DB (Both Services)
Both use `get_engine()` (sync SQLAlchemy) with `with engine.begin() as conn:` — blocking the event loop. Same issue as the CRM service had. Should use `get_async_session()` from `common/db.py`.

### 🟡 No Alembic Migrations
Both services have DDL embedded in Python code. Sales has inline `INSERT`/`UPDATE` Marketing has `_ensure_marketing_tables()`. Neither uses proper migration management.

---

## Priority Fixes

1. **Add webhook auth** to Marketing `POST /email/webhook` — currently open to abuse
2. **Move `_ensure_marketing_tables()` to startup** — don't run on every request
3. **Fix SQL injection surface** in Sales `list_deals` f-string query building
4. **Convert both to async DB** — use `get_async_session()` from common/db
5. **Add pagination** to Sales deals list and Marketing templates list
6. **Delete cascade** for Marketing campaigns → batches → events

## Related Notes

- [[OmniDome — Code Audit Report]]
- [[OmniDome — Implementation Status]]
- [[Sales Service — API Reference]]
