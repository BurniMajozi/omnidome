---
type: adr
status: accepted-baseline
date: 2026-06-10
area:
  - agents
  - protocols
  - memory
---

# ADR-0002: Adopt Layered Agent Protocols For OmniDome OS

## Context

Google's developer guide to AI agent protocols separates the agent ecosystem into clear protocol responsibilities:

- MCP connects agents to tools and data.
- A2A connects agents to other agents through discoverable agent cards.
- UCP standardizes commerce and checkout flows.
- AP2 adds payment authorization mandates and receipts.
- A2UI lets agents return declarative UI layouts.
- AG-UI standardizes streamed agent events for frontends.

OmniDome already has:

- `services/agent_orchestrator` for internal agents and tool execution.
- `services/tenant_memory` for tenant-scoped operational memory.
- `services/gateway` as the API edge.
- `apps/web` as the dashboard and user-facing agent UI.
- Hermes as the active Telegram-facing project agent.

The protocol design must preserve tenant isolation. Hermes owns Telegram interaction; `agent-orchestrator` can run in the default stack only if Telegram polling remains disabled there.

## Decision

Adopt the protocols as layered capabilities, not as one monolithic agent framework migration.

## Protocol Mapping

### MCP: Tool And Data Access

Use MCP as the long-term standard adapter interface for tools and data sources.

Initial OmniDome mapping:

- Existing tool registry remains the internal adapter.
- Add an MCP-compatible facade later for selected tools.
- First MCP candidates:
  - tenant memory recall;
  - CRM customer 360;
  - billing account status;
  - network diagnostics;
  - compliance obligations.

Design rule:

Agents should not gain direct database access unless the MCP server is tenant-aware and enforces `tenant_id`.

### A2A: Agent Discovery And Agent-To-Agent Calls

Expose OmniDome agents with discoverable Agent Cards.

Initial OmniDome mapping:

- Add `/.well-known/agent-card.json` to `agent_orchestrator`.
- Describe internal agents such as support, retention, provisioning, executive, and compliance.
- Keep Telegram ownership with Hermes by not passing `TELEGRAM_BOT_TOKEN` to `agent-orchestrator`.

Design rule:

A2A requests must carry tenant context, user context, and an audit correlation ID.

### UCP: Commerce And Ordering Workflows

Use UCP for ISP commerce workflows, not general tool calls.

Initial OmniDome mapping:

- Product/package ordering.
- Add-on purchases.
- Router/CPE replacement orders.
- Field stock replenishment.
- FNO or supplier procurement.

Design rule:

UCP checkout should produce normal billing/order records, not bypass OmniDome billing.

### AP2: Payment Authorization And Guardrails

Use AP2-style mandates for actions that spend money or change customer billing state.

Initial OmniDome mapping:

- Auto-approval guardrails for low-risk renewals or stock purchases.
- Explicit approval for refunds, write-offs, large orders, or subscription cancellations.
- Store mandate and receipt artifacts in tenant memory and audit logs.

Design rule:

No autonomous payment, refund, cancellation, or contract commitment is valid without a recorded mandate or explicit approval trail.

### A2UI: Agent-Composed UI

Use A2UI-style declarative UI for agent-generated panels inside `apps/web`.

Initial OmniDome mapping:

- Customer 360 mini-panels.
- Compliance obligation cards.
- Supplier comparisons.
- Retention campaign recommendation forms.
- Network incident summaries.

Design rule:

The renderer must accept only a fixed allow-list of safe components and actions.

### AG-UI: Streaming Agent Events

Use AG-UI-style event streams for agent runs.

Initial OmniDome mapping:

- Replace raw token-only SSE with typed events:
  - `RUN_STARTED`
  - `TEXT_MESSAGE_CONTENT`
  - `TOOL_CALL_START`
  - `TOOL_CALL_RESULT`
  - `TOOL_CALL_END`
  - `MEMORY_WRITE`
  - `RUN_FINISHED`
  - `RUN_ERROR`

Design rule:

The frontend should render typed events and not parse arbitrary text to infer tool progress.

## Tenant Memory Integration

Every agent run should use tenant memory in three places:

1. Recall before planning:
   - query `GET /api/v1/recall`;
   - include relevant summaries and recent entries in agent context.
2. Write after meaningful events:
   - store user goals, tool decisions, approvals, incidents, and outcomes.
3. Compact after repeated history:
   - update `tenant_memory_summaries` by `scope_key`.

Recommended `scope_key` examples:

- `customer:{customer_id}`
- `ticket:{ticket_id}`
- `property:{property_id}`
- `module:compliance`
- `agent:support`
- `procurement:{supplier_id}`

## Implementation Phases

### Phase 1: Internal Protocol Surface

- Add A2A Agent Card endpoint. Implemented.
- Add AG-UI-compatible typed event stream while keeping current `/invoke/stream`. Implemented as `/api/protocols/ag-ui/run`.
- Add memory recall/write tools to `agent_orchestrator`. Implemented.
- Add audit correlation IDs to tool calls.

### Phase 2: MCP Facade

- Create an MCP server/facade for selected OmniDome capabilities.
- Start with read-only tools:
  - memory recall;
  - CRM customer lookup;
  - compliance overview;
  - network service status.
- Add write tools only after RBAC and audit behavior is verified.

### Phase 3: A2UI Renderer

- Add a safe renderer in `apps/web`.
- Start with cards, tables, text, badges, buttons, tabs, and simple forms.
- Bind actions back to gateway endpoints through allow-listed action names.

### Phase 4: UCP/AP2 Commerce Controls

- Model UCP checkout sessions for product ordering and supplier procurement.
- Model AP2-style intent mandates, payment mandates, and receipts.
- Connect mandates to approvals, audit logs, billing, and tenant memory.

## Open Questions

- Should A2A be exposed externally per tenant, or only internally through the gateway?
- Should the tenant memory service provide an MCP server directly, or should `agent_orchestrator` expose memory as a tool?
- Which OmniDome modules are allowed to emit A2UI payloads?
- Which financial actions require AP2-style mandates on day one?

## Links

- [[../30-modules/agent-orchestration]]
- [[../30-modules/tenant-memory]]
- [[../30-modules/compliance]]
