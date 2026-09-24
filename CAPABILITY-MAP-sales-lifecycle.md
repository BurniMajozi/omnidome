# Capability Map: Sales Lead Lifecycle, Event Bus and Automations

2026-09-25. Follows the Lead Sources initiative (`CAPABILITY-MAP.md`). The user
asked to "use the skill to answer and execute", so this map and the module
specs are the recorded decisions rather than a gate. Module ids are stable.

## What the user reported / asked

1. Leads added from Lead sources (company search, tenders/RFQs) never reach the
   Pipeline Board.
2. "Adjust Lead Stage" and the board are two unconnected stage models.
3. Leads have no owner, reference number, created/modified/closed dates.
4. A per-lead action menu like Communication's: send to outbound agent, send to
   marketing campaign, send email, create task, escalate, etc.
5. "Do we have something that handles notifications, or a message broker
   between APIs, so things don't break or bottleneck?"
6. (Previous turn) Endpoints for the event triggers on the AI Lead Warming tab
   (abandoned basket, quote request, registration inactive) that start the
   Agentic Flow Orchestrator; is Redis needed?

## What exists today

- `sales`: leads, deals, 6 deal stages (Prospecting, Qualified, Proposal,
  Negotiation, Closed Won, Closed Lost). Leads carry their own 7-value status
  with no link to the deal's stage; `convert` creates a Prospecting deal.
- No broker. Cross-service calls are fire-and-forget HTTP (`_emit_webhook`,
  `schedule_background`): a down service silently loses the message.
- The header bell is decorative. `communication` has tasks/escalations but they
  are bound to chat channels and the container is not part of the local stack.
- `agent_orchestrator` has a workflow engine (trigger / agent_invoke /
  http_request / condition nodes), runs + steps tables, and a cron scheduler
  using an advisory lock. No event triggers.
- Marketing has real campaigns + audiences + AgentMail email sending.
- HR `employees` (16 rows) is the only populated people directory locally.

## Modules

| Module id | Responsibility | Depends on |
|---|---|---|
| `event-bus` | Postgres message broker: transactional outbox, per-consumer delivery with retries/back-off/dead-letter, fan-out by subscription; in-app notifications feed + bell | — |
| `lead-lifecycle` | Lead record (reference no., owner, created/modified/closed, priority, activity timeline, tasks); one stage model shared with the board; Lead sources land on the board | `event-bus` |
| `lead-actions` | Action menu + record panel: assign owner, note, email, task, escalate, send to outbound agent, send to marketing campaign, move stage / mark lost | `lead-lifecycle`, `event-bus` |
| `lead-automations` | Event intake endpoint on the orchestrator, event-triggered workflows, the three warming rules as real workflows, sales automation endpoint | `event-bus`, `lead-lifecycle` |

Build order: `event-bus` → `lead-lifecycle` → `lead-actions` → `lead-automations`.

## Why Postgres and not Redis/RabbitMQ/NATS (answer to 5 and 6)

- Every service already shares one Postgres. An outbox row written in the same
  transaction as the business change means an event exists if and only if the
  change committed: no lost or phantom messages, which a separate broker cannot
  give without the same outbox anyway.
- `FOR UPDATE SKIP LOCKED` claiming lets any number of workers/containers
  consume without double delivery (same pattern as the tender scanner).
- Volume is tens to hundreds of events a minute; Postgres handles thousands per
  second. Redis would add a container to a fragile local Docker and a paid
  Railway service, and it is not durable by default.
- Revisit when sustained volume passes ~1k events/s, or live push to browsers is
  needed (then add Redis pub/sub or NATS behind the same `publish()` API).
