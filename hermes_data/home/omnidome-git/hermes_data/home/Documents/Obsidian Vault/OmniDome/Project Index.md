# OmniDome — Project Index

> ISP Operating System | South Africa | Fibre-focused | Agentic AI

## What is OmniDome?

OmniDome is a carrier-grade, microservice-based operations platform designed for South African ISPs. It unifies CRM, Sales, Billing, Network provisioning, Retention analytics, Support, and more into a single ecosystem backed by a multi-tenant RBAC framework.

**GitHub:** `BurniMajozi/omnidome`
**Stack:** Python 3.11, FastAPI, SQLAlchemy, PostgreSQL 15, Next.js 14, React 19, Tailwind CSS, Ollama, Docker Compose
**License:** Proprietary — Antigravity AI for BurniWorld
**Author:** Bene Majozi — Snr Manager Business Performance & Insight, Cell C South Africa

## Architecture

- 16 microservices, each with own Dockerfile + DB schema
- API gateway (port 8000) for routing, rate-limiting, auth
- Multi-tenant RBAC with JWT or header-based dev mode
- Ed25519 license enforcement per tenant module

## Services

| Service | Port | Module | Description |
|---------|------|--------|-------------|
| Gateway | 8000 | gateway | API gateway / BFF |
| CRM | 8001 | crm | Customer 360, segmentation, leads |
| Sales | 8002 | sales | Pipeline, quoting, commissions |
| Billing | 8003 | billing | Invoicing (ZAR), Paystack, auto-suspend |
| RICA | 8004 | rica | Identity verification via Smile ID |
| Network | 8005 | network | RADIUS, FNO adapters, provisioning |
| IoT | 8006 | iot | Device telemetry, CPE health |
| Call Center | 8007 | call_center | Sentiment AI, agent whisperer |
| Support | 8008 | support | SLA-driven ticketing |
| HR | 8009 | hr | Performance tracking |
| Inventory | 8010 | inventory | Stock management |
| Analytics | 8011 | analytics | Executive insights, AI recommendations |
| Retention | 8012 | retention | Churn prediction, campaigns |
| Admin | 8013 | admin | Tenant management, RBAC |
| Marketing | 8014 | marketing | Campaign management |
| Finance | 8015 | finance | GAAP statements, FP&A |
| Communication | 8020 | communication | Chat, messages, tasks (NEW) |
| Agent Orchestrator | 8021 | agents | AI agent runtime (NEW) |

## Key Notes

- [[Agentic Architecture]] — AI agent layer design
- [[Code Audit Report]] — Full audit of all 16 services
- [[Communication Service]] — Chat/messages/tasks service (replaces Supabase)
- [[Implementation Status]] — Current state + next steps
- [[Session 2026-05-31]] — Full session log: architecture, audit, implementation

## Dashboard Modules

Sales, CRM, Service, Network, Call Center, Marketing, Compliance, Talent, Retention, Billing, Finance, Products, Portal

## Integrations

- **Paystack** — Payment processing (ZAR)
- **Smile ID** — RICA identity verification
- **Deepgram** — Voice AI (STT/TTS/sentiment)
- **Twilio** — WhatsApp + Voice channels
- **Sippy** — Voice/telephony
- **Ollama** — Local LLM inference
- **OpenRouter** — LLM fallback

## POPIA Compliance

1. Ollama on-prem = data stays in SA
2. PII scrubbing before external LLM calls
3. Full audit trail in agent_actions table
4. 90-day auto-delete for conversation history
5. RBAC inheritance — agents can't escalate privileges
