# Sim Bridge (Hosted Sim Studio ↔ OmniDome)

Sim Studio runs **hosted** (your Sim instance lives elsewhere — not in this
repo, not in `docker-compose.yaml`). OmniDome talks to it over HTTPS, and Sim
workflows call back into OmniDome's agent orchestrator over HTTPS. There is no
local Sim container to build or start.

## 1. Architecture

```
┌─────────────────────┐  HTTPS   ┌──────────────────────────────┐
│  Sim Studio (hosted) │ ───────▶ │ OmniDome agent-orchestrator  │
│  workflows / agents  │  invoke  │ :8021                        │
└─────────────────────┘ ◀─────── └──────────────────────────────┘
```

- **Sim → OmniDome (authenticated invoke).** Sim HTTP nodes call
  `POST {ORCHESTRATOR}/api/agents/invoke` with platform auth headers
  (`X-User-Id`, `X-Tenant-Id` in `header`/`dev` AUTH_MODE, or a JWT bearer
  token in `jwt` mode). Goes through the Next.js proxy
  (`/api/orchestrator/...`) or directly at the orchestrator.
- **Sim → OmniDome (public chat).** Sim HTTP nodes call
  `POST {ORCHESTRATOR}/api/chat/{identifier}` — no platform auth; the tenant
  is resolved from the chat-deployment row. Required only when the deployment
  has an access key: `key` in the body.
- **OmniDome → Sim.** Only two touchpoints: the `SIM_API_URL`/`SIM_API_KEY`
  env passthrough (so server-side code can reach the hosted instance when set)
  and the "Open in Sim Flow Builder" deep link on the Agent Manager detail
  page (gated on `NEXT_PUBLIC_SIM_URL`).

Relevant orchestrator routes (all that exist — nothing else is referenced here):

| Method & path                     | Auth              | Purpose                              |
|-----------------------------------|-------------------|--------------------------------------|
| `POST /api/agents/invoke`         | platform auth     | synchronous invoke, creates/continues conversation |
| `POST /api/agents/invoke/stream`  | platform auth     | SSE streaming invoke                 |
| `POST /api/chat/{identifier}`     | identifier (+key) | public deployable-chat invoke        |
| `GET  /api/agents/actions`        | platform auth     | newest-first AgentAction audit trail |
| `GET  /api/conversations`         | platform auth     | conversation list (proxy target)     |

## 2. Env wiring

| Var                  | Where set          | Consumed by                          | Notes |
|----------------------|--------------------|--------------------------------------|-------|
| `SIM_API_URL`        | `.env` (optional)  | `agent-orchestrator` container (passthrough) | Base URL of hosted Sim, e.g. `https://sim.your-domain.com`. Empty = no Sim calls. |
| `SIM_API_KEY`        | `.env` (optional)  | `agent-orchestrator` container (passthrough) | Service key for Sim→OmniDome calls. **Never commit real values.** |
| `SIM_WORKSPACE_ID`   | `.env` (optional)  | operator convenience only            | Default Sim workspace id for building deep links by hand. |
| `NEXT_PUBLIC_SIM_URL`| `.env` (optional)  | Next.js web client                   | Public base URL of hosted Sim. When set, the Agent Manager detail page shows "Open in Sim Flow Builder" (`{URL}/workspaces?agent={agent_type}`); when unset it shows muted helper text instead. |

`docker-compose.yaml` passes `SIM_API_URL`/`SIM_API_KEY` through to the
`agent-orchestrator` service as empty-when-unset (`${VAR:-}`), so a hosted
URL/key flows through when set and nothing breaks when not. No Sim service is
defined in compose — intentionally.

## 3. Reference flow: RICA check → CRM lookup → Slack alert

Scenario: a Sim workflow verifies a new subscriber (RICA), looks up the CRM
record, and posts a Slack alert — with OmniDome agents doing the reasoning at
each step.

1. **Trigger node (Sim side).** Webhook / schedule / manual trigger carrying
   `{{msisdn}}`, `{{id_number}}`, `{{tenant_id}}`, `{{user_id}}` variables.
2. **HTTP node 1 — RICA verify via OmniDome agent.** Calls the authenticated
   invoke path so tenant-scoped tools (RICA service) run with guardrails +
   audit:
   - `POST {ORCHESTRATOR}/api/agents/invoke`
   - headers: `Content-Type: application/json`, `X-User-Id: {{user_id}}`,
     `X-Tenant-Id: {{tenant_id}}`
   - body:
     ```json
     {
       "agent_type": "support",
       "message": "Run a RICA verification for MSISDN {{msisdn}} ID {{id_number}} and summarise the result.",
       "context": { "msisdn": "{{msisdn}}", "id_number": "{{id_number}}" }
     }
     ```
   - response: `{ "conversation_id": "<uuid>", "message": "<assistant reply>", "tool_calls": [], "agent_type": "support" }`
   - save `{{rica_conversation_id}}` and `{{rica_verdict}}` from the response.
3. **HTTP node 2 — CRM lookup (continue the conversation).** Same endpoint,
   passing `conversation_id` back so history is preserved:
   - `POST {ORCHESTRATOR}/api/agents/invoke`
   - headers: same as node 1
   - body:
     ```json
     {
       "agent_type": "support",
       "message": "Look up the CRM record for MSISDN {{msisdn}} and attach it to the verification summary.",
       "context": { "msisdn": "{{msisdn}}" },
       "conversation_id": "{{rica_conversation_id}}"
     }
     ```
4. **HTTP node 3 — Slack alert (public-chat alternative).** If the alert copy
   should come from a deployable agent instead of the authed path:
   - `POST {ORCHESTRATOR}/api/chat/{{chat_identifier}}`
   - headers: `Content-Type: application/json`
   - body: `{ "message": "Draft a Slack alert: {{rica_verdict}} for {{msisdn}}.", "key": "{{chat_access_key}}" }`
     (`key` only when the deployment has one; omit `conversation_id` to start
     fresh, or pass one to continue.)
   - response: `{ "identifier": "...", "conversation_id": "<uuid>", "message": "<draft>", "agent_type": "<agent>" }`
   - then a Sim Slack node posts `{{message}}` to the channel.

Example workflow JSON skeleton (placeholders only — no real secrets):

```json
{
  "name": "RICA check → CRM lookup → Slack alert",
  "trigger": { "type": "webhook", "inputs": ["msisdn", "id_number", "tenant_id", "user_id"] },
  "nodes": [
    {
      "id": "rica-verify",
      "type": "http",
      "method": "POST",
      "url": "{{ORCHESTRATOR}}/api/agents/invoke",
      "headers": {
        "Content-Type": "application/json",
        "X-User-Id": "{{user_id}}",
        "X-Tenant-Id": "{{tenant_id}}"
      },
      "body": {
        "agent_type": "support",
        "message": "Run a RICA verification for MSISDN {{msisdn}} ID {{id_number}} and summarise the result.",
        "context": { "msisdn": "{{msisdn}}", "id_number": "{{id_number}}" }
      }
    },
    {
      "id": "crm-lookup",
      "type": "http",
      "method": "POST",
      "url": "{{ORCHESTRATOR}}/api/agents/invoke",
      "headers": {
        "Content-Type": "application/json",
        "X-User-Id": "{{user_id}}",
        "X-Tenant-Id": "{{tenant_id}}"
      },
      "body": {
        "agent_type": "support",
        "message": "Look up the CRM record for MSISDN {{msisdn}} and attach it to the verification summary.",
        "context": { "msisdn": "{{msisdn}}" },
        "conversation_id": "{{rica_conversation_id}}"
      }
    },
    {
      "id": "slack-alert",
      "type": "http",
      "method": "POST",
      "url": "{{ORCHESTRATOR}}/api/chat/{{chat_identifier}}",
      "headers": { "Content-Type": "application/json" },
      "body": {
        "message": "Draft a Slack alert: {{rica_verdict}} for {{msisdn}}.",
        "key": "{{chat_access_key}}"
      }
    }
  ]
}
```

## 4. Guardrails & audit

- Every invoke (authed or public) runs the **pre-gate** on the inbound message
  (block → HTTP 422, no conversation/LLM side effects) and the **post-gate**
  on the assistant output (mask or withhold).
- Tool executions persist as **AgentAction** rows — review per agent in the
  Agent Manager detail page "Action Trail" tab, or via
  `GET /api/agents/actions?agent_type=...` (newest-first, do not re-sort).
- Public-chat conversations are pinned to their deployment (`external_id` =
  identifier, channel `chat_deploy`); one identifier cannot continue another
  deployment's conversation.
- Blocked inputs return 422 with `{ "error": ..., "hits": ... }` — Sim
  workflows should branch on non-2xx from the HTTP nodes.

## 5. Local verification without Sim

No Sim instance needed — these curls prove both invoke paths against a local
orchestrator (`localhost:8021`). Substitute real UUIDs for `X-User-Id` /
`X-Tenant-Id`.

Authenticated invoke (creates a conversation):

```bash
curl -s -X POST http://localhost:8021/api/agents/invoke \
  -H 'Content-Type: application/json' \
  -H 'X-User-Id: <user-uuid>' \
  -H 'X-Tenant-Id: <tenant-uuid>' \
  -d '{"agent_type":"support","message":"ping","context":{}}'
# → {"conversation_id":"<uuid>","message":"...","tool_calls":[],"agent_type":"support"}
```

Continue the conversation:

```bash
curl -s -X POST http://localhost:8021/api/agents/invoke \
  -H 'Content-Type: application/json' \
  -H 'X-User-Id: <user-uuid>' \
  -H 'X-Tenant-Id: <tenant-uuid>' \
  -d '{"agent_type":"support","message":"follow-up","context":{},"conversation_id":"<uuid-from-above>"}'
```

Public chat (needs a chat deployment created first via
`POST /api/chat-deployments` with platform auth):

```bash
curl -s -X POST http://localhost:8021/api/chat/<identifier> \
  -H 'Content-Type: application/json' \
  -d '{"message":"hello"}'
# with access key: -d '{"message":"hello","key":"<secret>"}'
# → {"identifier":"...","conversation_id":"<uuid>","message":"...","agent_type":"..."}
```

Audit trail for the agent:

```bash
curl -s 'http://localhost:8021/api/agents/actions?agent_type=support&limit=20' \
  -H 'X-User-Id: <user-uuid>' -H 'X-Tenant-Id: <tenant-uuid>'
```
