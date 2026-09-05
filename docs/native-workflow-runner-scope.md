# Native Workflow / DAG Runner — Scope (option C)

**Goal:** Bring visual, executable multi-step agent workflows *natively* into
OmniDome — removing the last dependency on hosted Sim. This is the deferred
"option C (native DAG runner)" from the Sim integration plan. After this, the
Agent Command Center is 100% self-contained: agents, chat, guardrails, audit
**and** workflows all run on OmniDome's own stack.

**Status:** scoping only — not started. Sim dependency already dropped (SIM_*
env vars removed 2026-09-05); the "Open in Sim Flow Builder" link is retired.

**Where it lives:** `agent_orchestrator` (engine + API), `apps/web` Agent Manager
(visual editor + run views), Postgres (definitions + run history). Reuses the
existing guardrails, audit taxonomy, and per-agent invoke already built.

---

## What "native" means here
Sim gave us: a visual DAG canvas, a node library, triggers (schedule/webhook/
chat), and an execution engine. We reimplement the subset OmniDome needs against
our own services — no Sim code, no external runtime.

---

## Architecture

```
apps/web (Agent Manager)                 agent_orchestrator                Postgres
┌───────────────────────┐  REST  ┌──────────────────────────┐        ┌──────────────┐
│ Visual DAG editor      │ ─────▶ │ Workflow API (CRUD/run)  │ ─────▶ │ workflows     │
│ (React Flow canvas)    │        │ Execution engine (async) │        │ workflow_runs │
│ Run history + trail    │ ◀───── │ Triggers: cron/webhook   │ ◀───── │ run_steps     │
└───────────────────────┘        │ Node handlers            │        │ triggers      │
                                  │  → agents/invoke (native)│        └──────────────┘
                                  │  → http, condition, …    │  reuse guardrails+audit
                                  └──────────────────────────┘
```

## Data model (new tables, tenant-scoped)
- `workflows` — `id, tenant_id, name, description, definition (jsonb DAG), status, created/updated`
- `workflow_triggers` — `id, workflow_id, type (schedule|webhook|manual|chat), config (cron expr / webhook slug), enabled`
- `workflow_runs` — `id, workflow_id, tenant_id, trigger, status (queued|running|succeeded|failed|cancelled), input, output, started_at, finished_at, error`
- `run_steps` — `id, run_id, node_id, node_type, status, input, output, started_at, finished_at, error, attempt` (this IS the execution trail; mirrors the existing AgentAction pattern)

## DAG definition (jsonb)
- **nodes**: `{ id, type, name, config }`
- **edges**: `{ from, to, condition? }` (condition = expression on upstream output for branching)
- **node types (v1, deliberately small):**
  - `trigger` — entrypoint (schedule/webhook/manual/chat)
  - `agent_invoke` — call an OmniDome agent (`POST /api/agents/invoke`, tenant-scoped, guardrails applied)
  - `http_request` — outbound HTTP (allowlisted)
  - `condition` — branch on a predicate over prior outputs
  - `transform` — map/shape data between nodes (safe expression, no arbitrary code)
  - `end` — terminal
  - (later: `delay`, `human_approval`, `parallel/fan-out`, `sub_workflow`)

## Execution engine (`agent_orchestrator`, async Python)
- Topological execution with per-node input resolution from upstream outputs.
- Branching via `condition` edges; each node persists a `run_steps` row (status, io, timing, retries).
- Reuse existing **guardrails gate** on `agent_invoke` in/out and **audit taxonomy** (`workflow.started`, `node.executed`, `workflow.succeeded`, …).
- Failure policy per node (fail-fast | continue | retry N); overall run status derived.
- **Concurrency/reliability:** v1 runs in-process (asyncio) — fine for the pilot. If runs get long/heavy, move to a Postgres-backed job queue or Celery/RQ worker (called out as a Phase B decision, not v1).

## Triggers
- **manual/chat** — run from the UI or an agent chat (v1).
- **schedule** — cron via APScheduler (or a lightweight DB-polled ticker) firing runs (Phase B).
- **webhook** — public `POST /api/workflows/hooks/{slug}` starts a run with the body as input (Phase B).

## API (`agent_orchestrator`)
- `GET/POST/PUT/DELETE /api/workflows` (+ `/{id}`)
- `POST /api/workflows/{id}/run` (manual), `GET /api/workflows/{id}/runs`, `GET /api/runs/{run_id}` (steps/trail)
- `POST /api/workflows/hooks/{slug}` (webhook trigger)
- Proxied through the existing Next.js `/api/orchestrator/*` pattern; admin RBAC.

## Web UI (`apps/web`, Agent Manager)
- Workflow list under `dashboard/admin/agents/` (or a sibling `workflows/`).
- **Visual editor** using **React Flow (`@xyflow/react`)** — drag nodes, connect edges, edit node config in a side panel; save persists the `definition` jsonb.
- Run history + a **step-trail viewer** reusing the action-trail component from the Agent Manager.

---

## Phases & rough effort

| Phase | Deliverable | Est. |
|---|---|---|
| **A — Engine core** | tables + migration, DAG schema, async engine, `agent_invoke`/`condition`/`transform`/`http` handlers, CRUD+run API, run a JSON-defined workflow end-to-end (TDD) | ~3–5 days |
| **B — Triggers** | schedule (cron) + webhook + manual; run persistence/trail solid; queue decision if needed | ~2–3 days |
| **C — Visual editor** | React Flow canvas, node config panel, save/load, run-from-UI, trail viewer | ~4–6 days |
| **D — Library + ref flow** | expand node types (delay/approval/parallel), reimplement the "RICA check → CRM lookup → alert" reference flow natively, docs | ~2–3 days |

**Total:** ~2–3 focused weeks for a solid v1. Phase A alone gives you runnable
native workflows (JSON-defined) — the visual editor (C) is the biggest single
chunk and can follow.

## Risks / decisions to make
- **Execution model:** in-process async (simple, v1) vs. a worker/queue (durable, survives restarts). Recommend in-process for v1, revisit in B.
- **React Flow** adds ~100–150KB to the web bundle — acceptable for an admin-only section; confirm OK.
- **Expression safety** for `condition`/`transform`: use a sandboxed mini-expression evaluator, never `eval`.
- **Tenant scoping + guardrails**: reuse existing helpers so workflows inherit the same PII/audit posture as direct invokes.
- **Railway footprint:** the engine lives inside the existing `agent_orchestrator` service — no new always-on service, so no extra RAM against the 8GB Hobby cap (a separate worker in Phase B would add one).

## Not in v1 (defer)
- Marketplace/templates, versioning/rollback of definitions, multi-tenant sharing, a public flow gallery, non-HTTP integrations (Slack/email nodes beyond `http_request`).

---

*Next step when you greenlight: turn Phase A into a task-by-task TDD plan (same
format as `.hermes/plans/…sim-omnidome-integration.md`) so it can be implemented
incrementally — ideally on its own branch, not stacked on the Railway line.*
