# Ticket lifecycle, KPIs, user-defined rules and Jev routing

Builds on the unified ticketing in `services/support` (event bus in, one ticket per problem). A ticket is now a
timeline, not a status: every change is a row with who, when and what changed, and everything else (KPIs,
notifications, agent knowledge) is derived from that.

## The time dimension

`ticket_events` is an append-only log, written only through `services/support/lifecycle.py`. Event types: `created`,
`assigned`, `reassigned`, `unassigned`, `transferred` (queue), `modified` (priority/category), `status_changed`,
`note_added`, `reply_sent`, `customer_notified`, `escalated`, `resolved`, `closed`, `reopened`, `sla_breached`,
`repeated`, `jev_suggested`, `jev_applied`, `jev_review`. The ticket row keeps denormalised counters and timestamps
(`first_assigned_at`, `first_response_at`, `last_activity_at`, `assignment_count`, `modification_count`,
`transfer_count`, `reopen_count`) so lists and KPIs do not scan the log.

Notes: a note is internal (`note_added`) or customer-visible (`reply_sent`). Internal text is never sent to the
requester and never indexed for agents.

## KPI definitions (`services/support/kpi.py`, `GET /tickets/kpis?days=N`)

| KPI | Definition |
| --- | --- |
| time to respond | created to `first_response_at`: the first time a **person** assigned it, started it, or sent a customer-visible reply. System and requester events never count. |
| time to assign | created to `first_assigned_at` |
| time to resolve | created to `resolved_at` (mean and median); per person this is mean time to repair |
| first-touch resolution | resolved with at most one assignment, no queue transfer, no reopen |
| deadline met | `resolved_at <= sla_due_at` |
| time in stage | average hours in each status, from the status events |
| overdue / stale (now) | open past `sla_due_at` / open with no activity for 2h URGENT, 4h HIGH, 12h NORMAL, 36h LOW |

`GET /tickets/late` lists the overdue and stale tickets, worst first. Overdue is computed, never a manual state.
A background watcher (`watcher.py`, every 5 min) writes one `sla_breached` event per ticket and a bus event
`support.ticket.sla_breached`; a backlog older than 6 h is logged on the ticket without ringing the bell.

## Telling the requester

`notify.py` publishes `support.ticket.customer_update`; the communication service (`ticket_bridge.py`) sends it.
Triggers: assigned, priority changed, customer-visible reply, resolved (each switchable per workspace at
`/tickets/settings`, throttled to one per trigger per ticket per 10 minutes). Wording is fixed templates. The
channel is the one the request came in on (`reply_channel`/`reply_ref`). **Only email has a delivery path today.**
Other channels (call, agent task, system) record a `customer_notified` event with `delivery = no_outbound_path`;
tickets opened by hand with no requester channel record nothing.

## Rules a workspace adds itself

`ticket_automation_rules` (API `/ticket-automation`): any event pattern (`portal.cart.abandoned`, `sales.lead.*`),
up to 5 payload conditions, a title template, source, priority, category, queue, assignee and an outcome:
`ticket`, `task`, `escalation` or `schedule`. Built-in rules gained the same outcome control. The outcome is carried
by `support.ticket.outcome_requested`; the communication service creates the item in a shared "Tickets" channel,
once per ticket and outcome. Refused: `support.*`/`ticket.*` (a ticket opening a ticket), events a built-in rule
already handles, `*`, and noise. Managers create and switch off rules; deleting needs an admin.

## Jev

Jev (TypeSafe) is reached through the orchestrator (`agent_orchestrator/jev_ticket.py`, `/api/jev/tickets/*`), which
holds the key and the `JEV_DATA_EGRESS` / `jev_gate_enabled` switches. Per-workspace mode `off | suggest | auto`
(default `suggest`):

* **route**: queue, category, priority, outcome and assignee (opaque candidate ids with workload numbers, never
  names). `suggest` stores a proposal for a person to Apply; `auto` applies what is at least 90% sure
  (`JEV_TICKET_APPLY_AT`), suggests 60% and up, ignores the rest.
* **review at close**: was the resolution a proper one? Flags a vague or off-target note and rings the bell.
* **stage check**: for late or idle tickets, should a supervisor step in now? Escalation is applied only in `auto`
  at 90%+, otherwise suggested. Re-asked at most every 6 h per ticket.

Every proposal is a row in `ticket_jev_decisions` with its probabilities, and a `jev_*` event on the ticket. If Jev is
unavailable nothing happens (the built-in rules already route deterministically).

## What agents know

* `ticket` knowledge cards now carry assignee, deadline (and "past deadline when indexed"), time to first
  response, handling counts and the last 12 lifecycle events. Only customer-visible note text is quoted.
* `ticket_digest` (one rolling card per tenant, `tenant_memory/knowledge/cards`): open/unassigned/escalated/overdue/
  stale counts, 30-day KPIs, time in stage, load per queue and person, the 15 worst late tickets, and closed tickets
  Jev flagged. It is rebuilt every sweep and expires from retrieval after 2 days.
* Live: agent tools `support_get_late_tickets` and `support_get_ticket_kpis`; the safe-SQL tool may query `tickets`
  and `ticket_event_log` (the event log without its free-text columns).

## Tests

`services/support/tests/test_ticket_pure.py`, `test_ticket_lifecycle_db.py`;
`services/communication/tests/test_ticket_bridge_db.py`; `services/agent_orchestrator/tests/test_jev_ticket.py`;
`services/tenant_memory/knowledge/tests/test_ticket_cards*.py`; `apps/web/lib/support-derive.test.mjs`.
The DB tests need `TEST_DATABASE_URL` (a database whose name ends in `_test`, built by `scripts/setup_test_db.py`).
