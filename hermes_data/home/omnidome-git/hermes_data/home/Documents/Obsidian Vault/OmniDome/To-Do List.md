# OmniDome — Comprehensive To-Do List

> Master task list. Updated 2026-06-01 (Session 3).

## ✅ Completed

### Services Implemented (20/20 have routes + auth + DB)

| Service | Status | Session |
|---------|--------|---------|
| Gateway | ✅ Port 8000 | 1 |
| CRM | 🟡 Async fix applied | 1 |
| Billing | 🟡 R0 fix applied | 2 |
| Sales | 🟡 Needs audit (1495 lines) | — |
| Communication | ✅ Full hub | 1 |
| Agent Orchestrator | ✅ 5 agents, 14+ tools | 1 |
| Support | ✅ SLA ticketing | 1 |
| Analytics | ✅ Executive summary, churn | 1 |
| HR | ✅ Employee management | 2 |
| IoT | ✅ Device telemetry | 2 |
| RICA | ✅ Smile ID verification | 2 |
| Call Center | ✅ DB-backed agents/sessions | 2 |
| Retention | ✅ DB-backed risk/cases/campaigns | 2 |
| Finance | ✅ DB persistence, scenarios | 2 |
| Marketing | ✅ Webhook auth, pagination fix | 2 |
| Network | 🟡 FNO adapters stubbed | — |
| Admin | 🟡 Needs audit (1004 lines) | — |
| Portal Builder | ✅ Landing pages, SEO | 2 |
| **Journey Engine** | ✅ Cancel-to-save, rule engine, offers | 3 |
| **Web Analytics** | ✅ Traffic, clicks, forms, devices, locations | 3 |

### Infrastructure (Session 3)
- Journey Engine service — rule evaluator, offer manager, outcome tracker
- Web Analytics service — tracking ingestion, dashboard API
- AnalyticsProvider in app layout — auto page view tracking
- Journey Builder UI — rule editor, offer config, funnel, ROI
- Web Analytics Dashboard — traffic, pages, devices, locations, forms
- Sidebar: Website Analytics + Journey Builder navigation
- Retention module: journeys tab → Journey Builder
- Portal module: Website Analytics tab added

### Cancel-to-Save Flow (Session 3)
```
Cancel click → POST /cancel/trigger → Rule Engine → Best Offer → Portal
Customer decides → POST /cancel/respond → Outcome → ML feedback (90d/180d)
```

---

## 🔴 Critical (Production Blockers)

### 1. Apply Patches
```bash
bash omnidome-patches/apply-all-patches.sh
docker compose up -d --build journey_engine web_analytics
```

### 2. CRM — Convert remaining routes to async
- `routes/leads.py` — still sync `session.query()`
- `routes/notes_tags.py` — still sync
- `routes/segments.py` — still sync

### 3. Wire Portal Cancel Button → Journey Engine
- Portal cancel flow must call `POST /cancel/trigger` with customer snapshot
- Display returned offer to customer
- Call `POST /cancel/respond` on accept/reject
- Integrate with CRM/Billing for customer data

### 4. Billing — Subscription integration
- Link invoices to actual customer subscriptions
- Per-segment pricing
- Usage-based billing (RADIUS → billing)

---

## 🟠 High Priority (Pre-Launch)

### 5. Journey Engine — Outcome Batch Job
- Daily job to check 90d/180d retention flags
- Update `journey_outcomes` table
- FeedRetention model retraining

### 6. Retention — Real Churn Model Pipeline
- Connect to actual churn model (scikit-learn/TensorFlow)
- Daily batch prediction job
- Real features: tenure, payment history, usage, sentiment

### 7. Sales Service Audit
- Review deal→quote→commission flow
- Check for sync DB calls
- Validate commission tier logic

### 8. Admin Service Audit
- Review tenant management flows
- Check RBAC permission enforcement

### 9. Network — Real FNO Adapters
- `adapters/vumatel.py` — Vumatel API
- `adapters/openserve.py` — Openserve API
- At minimum: check_availability, place_order, provision_service

---

## 🟡 Medium Priority (Post-Launch)

### 10. CRM → Journey Engine Data Sync
- Auto-sync customer snapshots on cancel trigger
- Real risk_score from retention service
- Real segment/tenure/usage from CRM + billing + network

### 11. Journey Engine — A/B Testing
- Already scaffolded in schema (`ab_test_enabled`, `ab_test_config`)
- Build UI for configuring A/B test variants
- Statistical significance calculator

### 12. Web Analytics — Custom Dashboards
- Save custom dashboard configurations
- Scheduled reports (PDF/email)
- Anomaly detection on traffic patterns

### 13. Mobile Apps
- Technician app (job management, CPE diagnostics)
- Field sales app (lead capture, quotes, e-signatures)

---

## 🟢 Nice-to-Have (Future)

### 14. AI Agent Upgrades
- Upgrade from raw loop to full LangGraph
- Multi-agent handoffs
- Agent memory (long-term context)
- WhatsApp + Voice channel adapters

### 15. Portal Builder — Advanced
- Multi-language pages
- Dynamic content (CRM-driven personalization)
- E-commerce integration
- Blog/content marketing module

### 16. Network — Advanced
- RADIUS accounting → billing integration
- Coverage map (visual FNO availability)
- SLA monitoring and alerting

---

## 📊 Progress

| Metric | Count |
|--------|-------|
| Total microservices | 20 |
| Fully implemented | 10 (gateway, comms, agents, support, analytics, journey, web_analytics, portal, retention DB, call_center DB) |
| Partial (needs work) | 7 (crm, billing, sales, network, admin, marketing, finance) |
| Stub only | 3 (hr, iot, rica) |
| Total files created | 150+ |
| Vault notes | 14 |

## Related Notes
- [[OmniDome — Project Index]]
- [[OmniDome — Implementation Status]]
- [[Session 2026-05-31]]
- [[Session 2026-06-01]]
