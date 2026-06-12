# OmniDome Agent Protocol Design

This document translates current AI agent protocol patterns into the OmniDome OS architecture.

Source reference: Google Developers Blog, "Developer's Guide to AI Agent Protocols", published March 18, 2026.

## Protocol Responsibilities

| Protocol | Role in OmniDome | First Implementation Target |
|---|---|---|
| MCP | Standard tool and data access | Tenant memory, CRM, billing, network, compliance tools |
| A2A | Agent discovery and agent-to-agent calls | `agent_orchestrator` Agent Card |
| UCP | Commerce and checkout flows | Product/package ordering and supplier procurement |
| AP2 | Payment authorization and audit mandates | Refunds, write-offs, purchases, subscription-changing actions |
| A2UI | Agent-composed UI components | Customer 360, compliance cards, retention recommendations |
| AG-UI | Typed streaming frontend events | Replace raw token SSE with structured agent run events |

## OmniDome Boundary Rules

- Every protocol request must preserve `tenant_id`.
- Every write action must include user identity or service identity.
- Every agent decision that affects billing, contracts, service state, or compliance must write tenant memory.
- Hermes remains the Telegram-facing agent unless explicitly changed.
- `agent-orchestrator` remains behind the `agents` Compose profile.

## Implemented Baseline

The first protocol layer is implemented in `services/agent_orchestrator`:

- A2A discovery:
  - `GET /.well-known/agent-card.json`
  - `GET /api/protocols/a2a/agents/{agent_type}/agent-card.json`
  - `POST /api/protocols/a2a/message`
- AG-UI-style typed streaming:
  - `POST /api/protocols/ag-ui/run`
- A2UI safe payload validation:
  - `POST /api/protocols/a2ui/validate`
- UCP-style commerce profile and checkout:
  - `GET /.well-known/ucp`
  - `POST /api/protocols/ucp/checkout-sessions`
  - `POST /api/protocols/ucp/checkout-sessions/{session_id}/complete`
- AP2-style mandates and receipts:
  - `POST /api/protocols/ap2/intent-mandates`
  - `POST /api/protocols/ap2/intent-mandates/{mandate_id}/sign`
  - `POST /api/protocols/ap2/payment-mandates`
  - `POST /api/protocols/ap2/payment-receipts`

Memory tools are now available to orchestrator agents:

   - `memory.recall`
   - `memory.write_entry`
   - `memory.upsert_summary`

`agent-orchestrator` is part of the default Compose stack again. Telegram ownership remains with Hermes because `TELEGRAM_BOT_TOKEN` is only wired to the `hermes` service and `AGENT_ORCHESTRATOR_ENABLE_TELEGRAM=false` is set on the orchestrator.

## Next Build

- Add a frontend AG-UI client for typed stream rendering.
- Add a frontend A2UI renderer for the safe component allow-list.
- Persist UCP/AP2 sessions in Postgres instead of in process memory.
- Attach protocol events to `tenant_memory_entries` with stronger correlation IDs.

## Reference Event Shape

```json
{
  "type": "TOOL_CALL_START",
  "run_id": "uuid",
  "tenant_id": "uuid",
  "tool_call_id": "uuid",
  "tool_name": "memory.recall",
  "timestamp": "2026-06-10T12:00:00Z"
}
```

## Reference Memory Entry

```json
{
  "source_type": "agent_run",
  "module": "support",
  "scope_key": "customer:00000000-0000-0000-0000-000000000001",
  "title": "Support agent diagnosed intermittent fibre issue",
  "content": "The support agent checked network status and found repeated ONT flaps.",
  "summary": "Customer has recurring ONT instability.",
  "importance": "high",
  "tags": ["support", "network", "diagnostics"]
}
```
