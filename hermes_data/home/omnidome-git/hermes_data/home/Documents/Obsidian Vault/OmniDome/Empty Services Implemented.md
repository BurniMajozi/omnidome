# OmniDome — Empty Services Implemented

> 2026-06-01 session. Completed implementation of all remaining empty services.

## Services Completed

### HR (port 8009) — 12 files
- **Models:** Employee (self-referential manager), Department, LeaveRequest, PerformanceReview
- **Features:** Employee CRUD, leave management (annual/sick/family), performance reviews, department management
- **Leave balance:** Annual 21d, sick 10d, family 5d (SA standard)

### IoT (port 8006) — 10 files
- **Models:** Device, TelemetryReading
- **Features:** Device registration, telemetry ingestion (single + batch), health monitoring, alert thresholds
- **Metrics:** signal_strength (dBm), uptime (s), throughput (Mbps), temperature (°C), packet_loss (%), latency (ms)
- **Alerts:** signal < -27dBm, packet_loss > 5%, temp > 70°C

### RICA (port 8004) — 9 files
- **Models:** RICAVerification, RICALog (audit trail)
- **Features:** ID verification (Luhn check), Smile ID integration (real or mock), webhook handler, 5-year expiry
- **Webhook:** Public endpoint for Smile ID async callbacks
- **SA RICA law compliant**

### Call Center (port 8007) — replaced mock data with real DB
- **Models:** CallCenterAgent, CallSession, CallScript, SentimentLog
- **Features:** Agent management (on/off duty), session tracking, sentiment analysis aggregation, script management
- **Preserved:** Deepgram STT/TTS integration from original code

### Retention (port 8012) — replaced mock data with real DB
- **Models:** CustomerRiskScore, RetentionCase, RetentionCampaign
- **Features:** Churn predictions, risk segmentation, retention cases, campaign management
- **Risk levels:** critical, high, medium, low, loyal
- **Churn reasons:** price_sensitivity, service_issues, competitor_offer, relocation, no_longer_needed, payment_issues

## Service Readiness (Updated)

| Service | Routes | Auth | DB | Real Logic | Ready? |
|---------|--------|------|-----|------------|--------|
| CRM | ✅ | ✅ | ✅ | ✅ | ✅ |
| Billing | ✅ | ✅ | ✅ | 🟡 (R0 invoices) | 🟡 |
| Network | ✅ | ✅ | ✅ | 🟡 (FNO stubs) | 🟡 |
| Sales | ✅ | ✅ | ✅ | 🟡 (unaudited) | 🟡 |
| Gateway | ✅ | ✅ | N/A | ✅ | ✅ |
| Communication | ✅ | ✅ | ✅ | ✅ | ✅ |
| Agent Orchestrator | ✅ | ✅ | ✅ | ✅ | ✅ |
| Support | ✅ | ✅ | ✅ | ✅ | ✅ |
| Analytics | ✅ | ✅ | ✅ | ✅ | ✅ |
| HR | ✅ | ✅ | ✅ | ✅ (NEW) | ✅ |
| IoT | ✅ | ✅ | ✅ | ✅ (NEW) | ✅ |
| RICA | ✅ | ✅ | ✅ | ✅ (NEW) | ✅ |
| Call Center | ✅ | ✅ | ✅ | ✅ (NEW) | ✅ |
| Retention | ✅ | ✅ | ✅ | ✅ (NEW) | ✅ |
| Finance | ✅ | ❌ | ❌ | 🟡 hardcoded | 🟡 |
| Marketing | ✅ | ✅ | ✅ | 🟡 (unaudited) | 🟡 |
| Admin | ✅ | ✅ | ✅ | 🟡 (unaudited) | 🟡 |

## Remaining Work
1. Fix billing invoice generation (R0.00 issue)
2. Audit sales service (1495 lines)
3. Audit marketing service (792 lines)
4. Audit admin service (1004 lines)
5. Implement real FNO adapters
6. Add Alembic migrations for all services

## Related Notes
- [[OmniDome — Implementation Status]]
- [[OmniDome — Code Audit Report]]
- [[OmniDome — Agentic Architecture]]
