# OmniDome Agent Architecture — Reference

## Agent Types

| Agent | Type Key | LLM | Channel | Purpose |
|-------|----------|-----|---------|---------|
| DomeBot | `customer_facing` | qwen2.5:7b | WhatsApp, Web | Customer self-service |
| ChurnGuard | `retention` | llama3.1:70b | Internal (event) | Autonomous churn prevention |
| ProvisionBot | `provisioning` | qwen2.5:7b | Internal (sales trigger) | Auto-provisioning workflow |
| InsightBot | `executive` | llama3.1:70b | Dashboard, scheduled | Executive briefings |
| SupportBot | `support` | qwen2.5:7b | WhatsApp, Web, Email | Ticket management |

## LLM Routing

Primary: Ollama (local). Fallback: OpenRouter. Timeout: 30s.

```
customer_facing → qwen2.5:7b (fallback: openrouter/owl-alpha)
retention      → llama3.1:70b (fallback: openrouter/owl-alpha)
provisioning   → qwen2.5:7b (fallback: openrouter/owl-alpha)
executive      → llama3.1:70b (fallback: openrouter/owl-alpha)
support        → qwen2.5:7b (fallback: openrouter/owl-alpha)
```

## Tool Registry — 14+ Tools

CRM: crm_get_customer, crm_get_customer_360, crm_create_customer
Billing: billing_get_balance, billing_get_invoice, billing_get_payment_history
Network: network_check_coverage, network_get_service_status, network_run_diagnostics
Support: support_create_ticket, support_get_tickets
Retention: retention_get_predictions, retention_get_cases
Analytics: analytics_get_executive_summary
Sales: sales_get_pipeline
Finance: finance_get_financial_summary
Call Center: call_center_get_intelligence

## Agent Reasoning Loop

```
user message → LLM(tools) → tool_calls?
  ├── no  → return final response
  └── yes → execute tools → append results → LLM(tools) → ... (max 10 iterations)
```

## API Endpoints

```
GET  /health
GET  /api/agents                    # List agents
POST /api/agents/invoke             # Sync invocation
POST /api/agents/invoke/stream      # SSE streaming
GET  /api/conversations             # List conversations
GET  /api/conversations/{id}        # Get with messages
DEL  /api/conversations/{id}        # Delete
GET  /api/tools                     # List tools
POST /api/tools/invoke              # Direct tool call
```

## Files (Patches at /opt/data/home/omnidome-patches/services/agent-orchestrator/)

main.py, agents.py, llm.py, tools.py, models.py, schemas.py
routes/agents.py, routes/conversations.py, routes/tools.py
requirements.txt, Dockerfile
