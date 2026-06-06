# OmniDome — Production Deployment Guide

## Quick Start

```bash
# 1. Clone and configure
git clone https://github.com/BurniMajozi/omnidome.git
cd omnidome
cp .env.example .env
# Edit .env with your production values

# 2. Deploy all services
docker compose -f docker-compose.production.yml up -d --build

# 3. Verify health
curl http://localhost:8000/health
```

## Architecture

- **25 microservices** — Python 3.12 + FastAPI + SQLAlchemy async
- **2 frontends** — Next.js 16 admin dashboard (port 3000) + customer portal PWA (port 3001)
- **API Gateway** — Reverse proxy with rate limiting + JWT auth (port 8000)
- **PostgreSQL 15** — Single database with schema-per-service isolation

## Service Ports

| Service | Port | Dockerfile |
|---------|------|------------|
| Gateway | 8000 | services/gateway/Dockerfile |
| CRM | 8001 | services/crm/Dockerfile |
| Sales | 8002 | services/sales/Dockerfile |
| Billing | 8003 | services/billing/Dockerfile |
| RICA | 8004 | services/rica/Dockerfile |
| Network | 8005 | services/network/Dockerfile |
| IoT | 8006 | services/iot/Dockerfile |
| Call Center | 8007 | services/call_center/Dockerfile |
| Support | 8008 | services/support/Dockerfile |
| HR | 8009 | services/hr/Dockerfile |
| Inventory | 8010 | services/inventory/Dockerfile |
| Analytics | 8011 | services/analytics/Dockerfile |
| Retention | 8012 | services/retention/Dockerfile |
| Admin | 8013 | services/admin/Dockerfile |
| Marketing | 8014 | services/marketing/Dockerfile |
| Finance | 8015 | services/finance/Dockerfile |
| Web Analytics | 8016 | services/web_analytics/Dockerfile |
| Journey Engine | 8017 | services/journey_engine/Dockerfile |
| Lifecycle | 8018 | services/lifecycle/Dockerfile |
| Communication | 8020 | services/communication/Dockerfile |
| Agent Orchestrator | 8021 | services/agent-orchestrator/Dockerfile |
| Customer Journey | 8022 | services/customer_journey/Dockerfile |
| Billing Collections | 8023 | services/billing_collections/Dockerfile |
| FNO Intelligence | 8024 | services/fno_intelligence/Dockerfile |
| Admin Dashboard | 3000 | apps/web/Dockerfile |
| Customer Portal | 3001 | apps/customer-portal/Dockerfile |

## Production Checklist

- [ ] Change all default passwords in `.env`
- [ ] Set `AUTH_JWT_VERIFY=true` and configure `AUTH_JWT_PUBLIC_KEY`
- [ ] Set `LICENSE_ENFORCEMENT=strict`
- [ ] Set `CORS_ORIGINS` to your actual frontend domains
- [ ] Configure `PAYSTACK_SECRET_KEY` for live payments
- [ ] Configure `SMILE_ID_API_KEY` for RICA verification
- [ ] Set `DATABASE_URL` with production credentials
- [ ] Enable HTTPS (use Nginx/Caddy reverse proxy)
- [ ] Configure log aggregation (stdout → ELK/Loki)
- [ ] Set up database backups
- [ ] Configure monitoring (Prometheus + Grafana)

## Environment Variables

See `.env.example` for all required variables. Key production variables:

| Variable | Description | Example |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection | `postgresql://user:pass@db:5432/omnidome` |
| `AUTH_JWT_VERIFY` | Enable JWT signature verification | `true` |
| `AUTH_JWT_PUBLIC_KEY` | RSA/HS256 public key | `-----BEGIN PUBLIC KEY-----...` |
| `AUTH_ENFORCE_MODULES` | Enforce module entitlements | `true` |
| `AUTH_ENFORCE_RBAC` | Enforce RBAC | `true` |
| `CORS_ORIGINS` | Allowed CORS origins | `https://app.yourdomain.com` |
| `LICENSE_ENFORCEMENT` | License check mode | `strict` |
| `RATE_LIMIT_DEFAULT` | Default rate limit per minute | `120` |
| `LOG_LEVEL` | Logging level | `INFO` |

## Health Checks

Every service exposes `/health`:
```bash
curl http://localhost:8001/health  # CRM
curl http://localhost:8003/health  # Billing
# ... etc
```

Response: `{"status": "ok", "service": "<name>"}`

## Resource Limits (Default)

| Service | Memory | CPU |
|---------|--------|-----|
| Database | 512M | 1.0 |
| Gateway | 256M | 0.5 |
| Backend services | 256M | 0.5 |
| ML services (retention, fno) | 512M | 1.0 |
| Frontend (web, portal) | 512M | 1.0 |
