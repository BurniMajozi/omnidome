# OmniDome API Documentation Index

> Auto-generated reference of all microservice API endpoints.
> Each service exposes its full OpenAPI spec at `/openapi.json`.
> The gateway aggregates all routes under `/api/{service-name}`.

## Services

| Service | Port | API Prefix | OpenAPI | Status |
|---------|------|------------|---------|--------|
| Gateway | 8000 | `/api/*` | `/openapi.json` | ✅ |
| CRM | 8001 | `/api/crm` | `/api/crm/openapi.json` | ✅ |
| Sales | 8002 | `/api/sales` | `/api/sales/openapi.json` | ✅ |
| Billing | 8003 | `/api/billing` | `/api/billing/openapi.json` | ✅ |
| Finance | 8015 | `/api/finance` | `/api/finance/openapi.json` | ✅ |
| RICA | 8004 | `/api/rica` | `/api/rica/openapi.json` | ✅ |
| Network | 8005 | `/api/network` | `/api/network/openapi.json` | ✅ |
| IoT | 8006 | `/api/iot` | `/api/iot/openapi.json` | ✅ |
| Call Center | 8007 | `/api/call-center` | `/api/call-center/openapi.json` | ✅ |
| Support | 8008 | `/api/support` | `/api/support/openapi.json` | ✅ |
| HR | 8009 | `/api/hr` | `/api/hr/openapi.json` | ✅ |
| Inventory | 8010 | `/api/inventory` | `/api/inventory/openapi.json` | ✅ |
| Analytics | 8011 | `/api/analytics` | `/api/analytics/openapi.json` | ✅ |
| Retention | 8012 | `/api/retention` | `/api/retention/openapi.json` | ✅ |
| Admin | 8013 | `/api/admin` | `/api/admin/openapi.json` | ✅ |
| Marketing | 8014 | `/api/marketing` | `/api/marketing/openapi.json` | ✅ |
| Web Analytics | 8016 | `/api/web-analytics` | `/api/web-analytics/openapi.json` | ✅ |
| Journey Engine | 8017 | `/api/journey-engine` | `/api/journey-engine/openapi.json` | ✅ |
| Lifecycle | 8018 | `/api/lifecycle` | `/api/lifecycle/openapi.json` | ✅ |
| Communication | 8020 | `/api/communication` | `/api/communication/openapi.json` | ✅ |
| Agent Orchestrator | 8021 | `/api/agent` | `/api/agent/openapi.json` | ✅ |

## Authentication

All API requests require tenant context via headers:
- `X-Tenant-ID: <uuid>` — Tenant identifier
- `X-Dev-Email: <email>` — User email (dev mode)
- `Authorization: Bearer <jwt>` — JWT token (production)

## Rate Limiting

- Gateway: 120 req/min per tenant per module (configurable via `RATE_LIMIT_*` env vars)
- Admin auth endpoints: 10 req/min per IP (user/role mutations)

## Health Checks

- Gateway aggregate: `GET /health` — Returns status of all services
- Per-service: `GET /health` on each service
- Prometheus metrics: `GET /metrics` on gateway

## Cross-Service Flows

### Customer Lifecycle
```
CRM (create customer) → Journey Engine (snapshot sync) → Lifecycle (stage tracking)
Sales (deal close-won) → Lifecycle (stage update)
Portal cancel → Journey Engine (cancel-to-save) → Lifecycle (stage update)
```

### Technician Job Dispatch
```
Support (new ticket) → SSE stream → Technician App (real-time notification)
Technician (accept/start/resolve) → Support (ticket update)
```

### FNO Order Flow
```
Sales (quote) → Network (FNO order) → FNO API (Vumatel/Openserve)
Network (provision) → FNO API (activate service) → RADIUS (account creation)
```
