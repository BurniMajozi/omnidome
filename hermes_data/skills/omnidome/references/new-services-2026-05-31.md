# OmniDome — Agentic Layer & New Services (2026-05-31)

## New Services Created

All patch files are in `/opt/data/home/omnidome-patches/`. Copy into `/opt/data/workspace/omnidome/` to apply.

### Communication Service — port 8020, module: communication
- **Path:** `services/communication/`
- **Purpose:** Replaces Supabase for chat/messages/tasks/approvals/module_data
- **Key model:** `ModuleData` (module_name, payload JSONB) — dashboard data for Next.js
- **Files:** main.py, models.py, schemas.py, database.py, routes/ (7 files), Dockerfile, requirements.txt

### Agent Orchestrator — port 8021, module: agents
- **Path:** `services/agent-orchestrator/`
- **5 agents:** customer_facing (DomeBot/qwen2.5:7b), retention (ChurnGuard/llama3.1:70b), provisioning (ProvisionBot), executive (InsightBot), support (SupportBot)
- **LLM:** Ollama primary, OpenRouter fallback. 30s timeout. Streaming SSE.
- **Tool registry:** 14+ tools wrapping all OmniDome REST APIs
- **Reasoning loop:** LLM → tool execution → feed back → repeat (max 10 calls)
- **DB tables:** agent_conversations, agent_messages, agent_actions
- **System prompts:** Defined per agent type in `llm.py`

### Support Service — port 8008 (rebuilt)
- **Models:** SupportTicket (SLA deadline, status, priority, category), SupportTicketNote
- **SLA:** CRITICAL=4h, HIGH=24h, NORMAL=72h, LOW=1 week
- **Endpoints:** Full CRUD, assign, status, notes, sla/breaches

### Analytics Service — port 8011 (rebuilt)
- Cross-service aggregation via httpx from retention, billing, network, call_center, sales
- Executive summary: parallel aggregation from all services

### Common Utilities
- `services/common/circuit_breaker.py` — CLOSED→OPEN→HALF_OPEN, per-service, async-safe
- `services/common/http_client.py` — service_call() with circuit breaker + retry
- Patch files for CRM customers, billing collections, billing Paystack webhook

### Next.js Supabase Client — `apps/web/lib/supabase/`
- client.ts, server.ts, module-data.ts, realtime.ts, index.ts
- `app/api/modules/[id]/route.ts` — backward-compat REST endpoint

### Docker Compose Additions
- communication (8020), agent-orchestrator (8021), redis (6379)

## Subagent Timeout Pattern
Multi-file creation tasks (>15 files) timeout at 600s. Best pattern: 1-3 files per subagent task, or create directly with write_file. Use subagents for complex single-file rewrites, not bulk file creation.

## Project Ownership
`/opt/data/workspace/omnidome/` owned by uid 1000 — Hermes can't write there. Write patches to `/opt/data/home/omnidome-patches/` and copy in.

## Remaining Work
1. Apply circuit breaker patches to existing services
2. Implement: hr, iot, rica, call_center, retention (still empty)
3. Fix billing R0.00 invoices
4. Real FNO adapters (Vumatel + Openserve)
5. Fix SQL injection in CRM search
6. Audit sales (1495 lines) and marketing (792 lines)
