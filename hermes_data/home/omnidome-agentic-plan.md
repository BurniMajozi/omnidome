# OmniDome Agentic Layer — Architecture Design

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Design and implement an AI agent layer on top of OmniDome's microservices that enables autonomous, multi-agent orchestration for ISP operations — covering customer-facing agents (WhatsApp, voice), internal ops agents (retention, provisioning, support), and executive intelligence agents.

**Architecture:** A new `services/agent-orchestrator` microservice acts as the central agent runtime. It wraps the existing REST APIs as agent tools, runs multi-step reasoning loops, and channels responses through the existing gateway. Agents are stateless reasoning loops backed by a conversation store (Postgres). Communication channels (WhatsApp, voice/Sippy) plug into the orchestrator via webhook adapters.

**Tech Stack:** Python 3.11, FastAPI, LangGraph (agent runtime), PostgreSQL 15 (conversation + tool state), Redis (streaming/cache), Ollama (local LLM), Deepgram (STT/TTS), Twilio (WhatsApp/voice).

---

## Architecture

```
[WhatsApp] [Voice/Sippy] [Web/Next.js] [API]
      \         |              |          /
       \        |              |         /
        -----> GATEWAY (8000) <----
                    |
                    v
       AGENT ORCHESTRATOR (8020)
       +-----------------------+
       | Agent Engine (LangGraph)
       | Tool Registry (auto-discovered)
       | Conversation Manager
       +-----------------------+
       |  DomeBot (Customer)    |
       |  ChurnGuard (Retention)|
       |  ProvisionBot (Provisioning)|
       |  InsightBot (Executive)|
       |  SupportBot (Support)  |
       +-----------------------+
                    |
                    v
       EXISTING MICROSERVICES
       CRM(8001) Billing(8003) Network(8005)
       Sales(8002) Retention(8012) Support(8008)
       Analytics(8011) etc.
```

---

## Key Design Decisions

### 1. Agent Runtime: LangGraph
LangGraph supports cyclic graphs, human-in-the-loop, and multi-agent handoffs — essential for ISP workflows (e.g., retention agent escalates to human agent). Raw LangChain agents were rejected because they're linear.

### 2. LLM: Ollama (local) + OpenRouter fallback
Data sovereignty (SA POPIA compliance) — customer data stays on-prem. Ollama runs locally; OpenRouter as fallback for complex reasoning. Lightweight model (7b) for routing; heavier model (70b) for executive insights.

### 3. Tool Wrappers: REST → Agent Tools
Each OmniDome service API is wrapped as a typed agent tool. Tools are auto-discovered from OpenAPI specs at startup. Tool permissions map to OmniDome's existing RBAC.

### 4. Conversation Store: Postgres + Redis
Postgres for durable history + audit trail. Redis for streaming tokens + session cache.

### 5. Channel Adapters: Webhook-based
WhatsApp (Twilio), Voice (Sippy/Twilio), Web (SSE) — all plug in via webhook adapters.

---

## 5 Agents

### 1. DomeBot (Customer-Facing)
- **Channel:** WhatsApp, Web chat
- **LLM:** Ollama `qwen2.5:7b` (fast)
- **Tools:** crm.get_customer, billing.get_balance, billing.get_invoice, network.check_coverage, network.get_service_status, support.create_ticket, rica.verify_identity, sales.get_quote
- **Escalation:** sentiment < 0.3 or human requested → create ticket + notify call center

### 2. ChurnGuard (Retention)
- **Channel:** Internal (event-triggered)
- **LLM:** Ollama `llama3.1:70b` (complex reasoning)
- **Tools:** retention.*, crm.get_customer_360, billing.get_payment_history, sales.create_deal
- **Trigger:** Daily batch prediction → evaluates high-risk customers → autonomous action

### 3. ProvisionBot (Provisioning)
- **Channel:** Internal (sales deal closure)
- **LLM:** Ollama `qwen2.5:7b`
- **Tools:** sales.get_deal, network.check_coverage, network.provision_service, rica.verify_identity, crm.create_customer, billing.create_subscription, inventory.reserve_equipment, support.create_ticket
- **Workflow:** Deal Closed → Coverage Check → RICA → Create Customer → Reserve Equipment → Provision → Subscribe → Install Ticket

### 4. InsightBot (Executive)
- **Channel:** Dashboard, scheduled reports
- **LLM:** Ollama `llama3.1:70b`
- **Tools:** analytics.*, retention.get_metrics, billing.get_revenue_report, network.get_network_health, call_center.get_intelligence, crm.get_pipeline, finance.get_financial_summary
- **Output:** Daily 7am natural language executive briefing

### 5. SupportBot (Support)
- **Channel:** WhatsApp, Web, Email
- **LLM:** Ollama `qwen2.5:7b`
- **Tools:** support.*, network.run_diagnostics, knowledge_base.search, call_center.get_sentiment

---

## New Service: `services/agent-orchestrator/`

### Structure
```
services/agent-orchestrator/
├── main.py, config.py, requirements.txt, Dockerfile
├── agents/  ← agent definitions (base, registry, 5 agents)
├── tools/   ← tool wrappers per service + auto-discovery
├── channels/← whatsapp, voice, web, webhook adapters
├── conversation/ ← store (Postgres), memory (Redis), models
├── llm/     ← ollama client, openrouter fallback, router
└── routes/  ← agents, channels, conversations, health
```

### API Endpoints
```
POST /api/agents/invoke         # Sync agent invocation
POST /api/agents/invoke/stream  # SSE streaming
GET  /api/agents                # List agents
POST /api/channels/whatsapp     # Twilio webhook
POST /api/channels/voice        # Voice webhook
GET  /api/conversations/{id}    # Conversation history
GET  /health                    # Health check
```

### New Database Tables
```sql
agent_conversations  — tenant, agent_type, channel, external_id, status, context
agent_messages       — conversation_id, role, content, tool_calls, tool_results
agent_actions        — audit log of every tool call (compliance)
agent_configs        — per-tenant agent configuration
```

---

## Integration Changes

### Gateway (`services/gateway/main.py`)
Add route: `/api/agents` → `http://agent-orchestrator:8020`

### Docker Compose
Add `agent-orchestrator` service (port 8020) + `redis` service (port 6379)

### .env
```
AGENT_SERVICE_URL=http://agent-orchestrator:8020
REDIS_URL=redis://redis:6379
```

---

## POPIA Compliance
1. Ollama on-prem = data stays in SA
2. PII scrubbing before any external LLM call
3. Full audit trail in `agent_actions`
4. WhatsApp opt-in consent tracking
5. 90-day auto-delete for conversation history
6. RBAC inheritance — agents can't escalate privileges

---

## Implementation Phases (10 weeks)

**Phase 1 (W1-2):** Foundation — project structure, base agent, tool registry, conversation store, LLM router, Docker integration

**Phase 2 (W3-4):** Core Agents — DomeBot + all tool wrappers + unit/integration tests

**Phase 3 (W5-6):** Channels — WhatsApp, Web SSE, Voice adapters

**Phase 4 (W7-8):** Advanced Agents — ChurnGuard, ProvisionBot, InsightBot, SupportBot

**Phase 5 (W9-10):** Hardening — POPIA audit, PII scrubbing, rate limiting, monitoring, load testing
