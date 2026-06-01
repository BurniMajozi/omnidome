# OmniDome — Agentic Architecture Design

> Architecture for the AI agent layer on top of OmniDome's microservices.

## Overview

New `services/agent-orchestrator` microservice (port 8021) acts as the central agent runtime. Wraps existing REST APIs as agent tools, runs multi-step reasoning loops, channels responses through the existing gateway.

**Tech Stack:** Python 3.11, FastAPI, PostgreSQL 15, Redis, Ollama (local LLM), OpenRouter (fallback).

## 5 Agents

| Agent | Role | Channel | LLM | Tools |
|-------|------|---------|-----|-------|
| **DomeBot** | Customer-facing | WhatsApp, Web | qwen2.5:7b | CRM, Billing, Network, Support |
| **ChurnGuard** | Retention | Internal (events) | llama3.1:70b | Retention, CRM, Billing, Analytics |
| **ProvisionBot** | Provisioning | Internal (sales) | qwen2.5:7b | Network, RICA, CRM, Billing, Support |
| **InsightBot** | Executive | Dashboard | llama3.1:70b | All services (read-only) |
| **SupportBot** | Support | WhatsApp, Web, Email | qwen2.5:7b | Support, CRM, Network, Call Center |

## Agent Reasoning Loop

```
User Message → LLM (with tools) → Tool Call? → Execute → Feed Result → LLM → ... → Final Response
Max 10 tool calls per invocation. Ollama primary, OpenRouter fallback (30s timeout).
```

## New Infrastructure

- `services/agent-orchestrator/` — port 8021, module: agents
- `services/communication/` — port 8020, module: communication (replaces Supabase)
- Redis service
- 4 new DB tables: agent_conversations, agent_messages, agent_actions

## API Endpoints

```
POST /api/agents/invoke         # Sync
POST /api/agents/invoke/stream  # SSE streaming
GET  /api/agents                # List agents + tools
GET  /api/tools                 # List all registered tools
POST /api/tools/invoke          # Direct tool invocation (debug)
GET  /api/conversations         # List conversations
```

## Tool Registry (14+ tools)

- CRM: get_customer, get_customer_360, create_customer
- Billing: get_balance, get_invoice, get_payment_history
- Network: check_coverage, get_service_status, run_diagnostics
- Support: create_ticket, get_tickets
- Retention: get_predictions, get_cases
- Analytics: get_executive_summary
- Sales: get_pipeline
- Finance: get_financial_summary
- Call Center: get_intelligence

## Related Notes

- [[OmniDome — Code Audit Report]]
- [[OmniDome — Communication Service]]
- [[OmniDome — Implementation Status]]
