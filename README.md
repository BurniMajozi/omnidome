# OmniDome — ISP Operating System

OmniDome is a carrier-grade, microservice-based operations platform designed for South African ISPs. It unifies CRM, Sales, Billing, Network provisioning, Retention analytics, Support, and more into a single ecosystem backed by a multi-tenant RBAC framework.

---

## Architecture

```
apps/
  portal/        – Lightweight static customer-facing portal
  web/           – Next.js dashboard & marketing site (shadcn/ui)
services/
  admin/         – Platform & org admin (tenants, roles, modules)
  analytics/     – AI-powered executive insights
  billing/       – Invoicing, payments, collections
  finance/       – GAAP finance, FP&A, scenario planning
  call_center/   – Inbound/outbound calls, sentiment AI
  common/        – Shared auth, RBAC, entitlements, DB
  crm/           – Customer 360, lead management
  gateway/       – API gateway / BFF
  hr/            – Employee management, performance tracking
  inventory/     – Stock & supply chain management
  iot/           – Device telemetry, hardware control
  network/       – RADIUS, FNO adapters, provisioning
  retention/     – Churn prediction, retention campaigns
  rica/          – RICA identity verification (Smile ID)
  sales/         – Pipeline, deals, quoting
  support/       – Ticketing, SLA tracking, knowledge base
config/          – Master SQL schema
docs/            – Module licensing, Supabase schema & seeds
brand_guidelines/– Logo & default theme
licenses/        – License artifact (license.example.json)
docker-compose.yaml
```

---

## Modules

| Module | Service | Port | Description |
|--------|---------|------|-------------|
| CRM | `/services/crm` | 8001 | Customer 360, segmentation, lead tracking |
| Sales | `/services/sales` | 8002 | Pipeline management, quoting, commission |
| Billing | `/services/billing` | 8003 | Invoicing (ZAR), Paystack, auto-suspend |
| Finance | `/services/finance` | 8015 | GAAP statements, revenue recognition, FP&A |
| RICA | `/services/rica` | 8004 | Identity verification via Smile ID |
| Network | `/services/network` | 8005 | RADIUS, FNO adapters (Vumatel, Openserve, etc.) |
| IoT | `/services/iot` | 8006 | Device telemetry, CPE health monitoring |
| Call Center | `/services/call_center` | 8007 | Sentiment AI, agent whisperer |
| Support | `/services/support` | 8008 | SLA-driven ticketing, remote diagnostics |
| HR | `/services/hr` | 8009 | Performance tracking, staff sentiment |
| Inventory | `/services/inventory` | 8010 | Stock management, sales planning |
| Analytics | `/services/analytics` | 8011 | Executive insights, AI recommendations |
| Retention | `/services/retention` | 8012 | Churn prediction, campaign ROI |
| Admin | `/services/admin` | 8013 | Tenant management, RBAC, module entitlements |
| Gateway | `/services/gateway` | 8000 | API gateway / BFF for all services |

---

## Auth & RBAC

All services share a common auth & RBAC layer (`services/common/`):

- **AuthContext** — Extracted from JWT or development headers (`X-User-Id`, `X-Tenant-Id`, `X-Roles`).
- **Multi-tenant** — Every request is scoped to a tenant; platform admins can impersonate via `X-Org-Id`.
- **RBAC** — Roles and permissions are stored in Postgres and enforced per-request by the `EntitlementGuard` middleware.
- **Module entitlements** — Each service verifies its module is enabled for the tenant before processing.
- **License enforcement** — Signed Ed25519 license files control which modules are available (see `docs/module-licensing.md`).

### Environment Variables

| Variable | Description |
|----------|-------------|
| `AUTH_MODE` | `header` (dev) or `jwt` (production) |
| `AUTH_DB_ENFORCE` | Enable DB-backed RBAC lookups |
| `AUTH_ENFORCE_MODULES` | Enforce per-tenant module access |
| `AUTH_ENFORCE_RBAC` | Enforce per-request permission checks |
| `LICENSE_ENFORCEMENT` | `strict` or `warn` |

See `.env.example` for the full list.

---

## Frontend

### Dashboard (`apps/web`)

Next.js 14+ app with App Router, shadcn/ui components, and Supabase for real-time data.

- **Dashboard modules** — Sales, CRM, Service, Network, Call Center, Marketing, Compliance, Talent, Retention, Billing, Finance, Products, Portal.
- **AI Chat** — Ollama-backed assistant available across all modules.
- **Communication Hub** — Slack-style messaging with channels, threads, tasks, approvals, scheduling, and escalations.
- **Auth** — Supabase Auth with magic link, password, Google, and GitHub sign-in.

### Customer Portal (`apps/portal`)

Lightweight static HTML/CSS/JS portal for end-customer self-service.

---

## Supabase Integration

The communication module and dashboard data use Supabase Postgres.

1. Copy `.env.example` → `.env` and fill in your Supabase credentials.
2. Run `docs/supabase/schema.sql` in the Supabase SQL editor.
3. Seed dashboard data with `docs/supabase/seed_module_data.sql`.
4. Optionally apply `docs/supabase/retention.sql` for demo cleanup cron.
5. Hit `/api/supabase/health` to confirm connectivity.

---

## Getting Started

### Prerequisites

- Docker & Docker Compose
- Node.js 18+ and pnpm/npm (for the web app)
- Python 3.10+ (for direct service development)
- A Supabase project (free tier works)
- Ollama running locally (optional, for AI chat)

### Quick Start

```bash
# Clone
git clone https://github.com/BurniMajozi/omnidome.git
cd omnidome

# Configure
cp .env.example .env
# Edit .env with your credentials

# Start all services
docker compose up --build -d

# Start the web frontend (dev)
cd apps/web
npm install
npm run dev
```

The dashboard will be available at `http://localhost:3000` and the gateway at `http://localhost:8000`.

---

## Stack

| Layer | Technology |
|-------|------------|
| Backend | Python 3.11, FastAPI, SQLAlchemy |
| Database | PostgreSQL 15, Supabase |
| Frontend | Next.js 14, React 19, Tailwind CSS, shadcn/ui |
| AI | Ollama (local LLM), churn ML models |
| Auth | Supabase Auth, JWT, header-based dev mode |
| Infra | Docker Compose, per-service Dockerfiles |

---

## License

Proprietary — Antigravity AI for BurniWorld.

