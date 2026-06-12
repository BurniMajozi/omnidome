---
type: module-memory
module: agent-orchestration
service: services/agent_orchestrator
port: 8021
status: isolated
---

# Agent Orchestration

## Purpose

The agent orchestration service provides agent and tool APIs for the OmniDome web app and internal automations.

## Current Constraint

Hermes is the active project agent and owns Telegram interaction. `agent-orchestrator` can run in the default stack, but it must keep Telegram polling disabled so it does not compete with Hermes.

## Current Wiring

- Backend service: `services/agent_orchestrator`
- Compose service name: `agent-orchestrator`
- Compose startup: default stack
- Telegram polling: disabled through `AGENT_ORCHESTRATOR_ENABLE_TELEGRAM=false`
- Service port: `8021`
- Dockerfile: `services/agent_orchestrator/Dockerfile`

## Protocol Endpoints

- `GET /.well-known/agent-card.json`
- `POST /api/protocols/a2a/message`
- `POST /api/protocols/ag-ui/run`
- `POST /api/protocols/a2ui/validate`
- `GET /.well-known/ucp`
- `POST /api/protocols/ucp/checkout-sessions`
- `POST /api/protocols/ap2/intent-mandates`
- `POST /api/protocols/ap2/payment-mandates`
- `POST /api/protocols/ap2/payment-receipts`

## Operating Rule

Hermes owns Telegram polling. Do not pass `TELEGRAM_BOT_TOKEN` to `agent-orchestrator` unless ownership is intentionally moved from Hermes.

## Build Logs

- [[../10-build-log/2026-06-10-compliance-wiring-and-agent-isolation]]
- [[../10-build-log/2026-06-10-admin-frontend-module]]
