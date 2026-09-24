# Implementation Plan: Sales lead lifecycle, event bus, automations

Specs: `SPEC-event-bus.md`, `SPEC-lead-lifecycle.md`, `SPEC-lead-actions.md`,
`SPEC-lead-automations.md`. Map: `CAPABILITY-MAP-sales-lifecycle.md`.
Previous plan archived in `tasks/archive/`.

## Architecture decisions

- Broker = Postgres outbox + per-consumer deliveries (`services/common/event_bus.py`);
  no new container. Notifications live beside it; the orchestrator serves the API.
- Once a lead has a deal, the deal stage is the single source of truth; the lead
  table and the board call the same server rules (`services/sales/lead_stages.py`).
- Actions that touch other services publish events; sales and orchestrator run consumers.
- Automations are ordinary orchestrator workflows with a `trigger_event`.
- Schema changes are idempotent SQL migrations in `config/migrations/` (create_all never ALTERs).
- Commit per task; push at the end after live verification (the user asked to push).

## Tasks

### Phase 1 — event-bus
- T1 Pure helpers + tests (pattern match, back-off, exhaustion) — `services/common/event_bus.py`, fno tests.
- T2 Migration + publish/notify/EventConsumer; live test (rollback, retry, dead, concurrency).
- T3 Orchestrator notifications + deliveries API; header bell wired.

### Checkpoint A: bus delivers, bell shows notifications.

### Phase 2 — lead-lifecycle
- T4 `lead_stages.py` rules + tests.
- T5 Migration (lead columns, ref_no backfill, activities, tasks, status migration) + models.
- T6 Sales API: create-with-pipeline, stage endpoint, detail, owners, board→lead sync, events.
- T7 Web: lead table (reference/owner/dates, grouped stage dropdown), Lead sources → board, unified modal linked, board card ref/owner.

### Checkpoint B: add company → board; board ↔ table agree; build + tests green.

### Phase 3 — lead-actions
- T8 Sales action endpoints + sales consumer (email via AgentMail, campaign audience).
- T9 Web: ⋯ menu + right-click, record slide-over (details, timeline, tasks), action forms.

### Checkpoint C: every action on the timeline; email to own inbox; marketing-down retry.

### Phase 4 — lead-automations
- T10 Orchestrator: trigger_event, intake endpoint, orchestrator consumer, engine templating/service calls, templates endpoint; sales automation endpoint.
- T11 Web: real rule cards (install, runs, send test event).

### Checkpoint D: three test events run end-to-end; push; CI green.

## Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Free LLMs rate-limited | AI draft step fails | fallback chain; workflow records the failure; stage move still happens first |
| Email to real businesses during testing | High | only send to own AgentMail inbox |
| Two uvicorn workers × consumers | Double delivery | SKIP LOCKED claim + unique (event, consumer) |
| Lead status migration | Medium | idempotent SQL; only PROPOSAL/NEGOTIATION without deal change |
| Docker/WSL instability | Delays | rebuild one service at a time |
