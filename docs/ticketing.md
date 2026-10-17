# Unified ticketing (2026-10-16)

Every meaningful event in OmniDome becomes a ticket through **one** mechanism, and the Service panel has a
ticket desk to work them. No service carries its own ticket logic.

```
 source services ──publish──▶ Postgres event bus ──▶ support_tickets consumer ──▶ tickets (+ timeline)
 (iot, finance, billing,       (domain_events,         ticket_rules.resolve()          │
  call_center, agents,          idempotency keys)       ticketing.raise_ticket()        ├─▶ support.ticket.* events ─▶ orchestrator automations (draft-only)
  communication, any service)                                                          ├─▶ notifications bell (HIGH / URGENT)
 error hook (all services) ───▶ system.error.raised / system.job.failed                └─▶ knowledge indexer ("tickets" source) ─▶ memory / RAG
```

## Pieces

| Piece | File | Job |
| --- | --- | --- |
| Rule table | `services/support/ticket_rules.py` | Pure: event → `TicketSpec` (subject, category, priority, queue, dedupe key, link back). Noise filter. Per-tenant overrides. Repeat escalation. |
| Raise / dedupe | `services/support/ticketing.py` | The only code that inserts tickets. One **open** ticket per `(tenant, dedupe_key)`; repeats bump a counter. |
| Consumer | `services/support/consumer.py` | `EventConsumer("support_tickets")`, started in the support lifespan, subscribed to every rule key. |
| Desk API | `services/support/desk.py` | `/tickets/search`, `/tickets/summary`, `/tickets/meta`, `/tickets/assignees`, create, detail + timeline, comments, assign, status/priority/queue update, `/ticket-rules`. |
| Request helper | `services/common/ticket_events.py` | `request_ticket(...)` (explicit request, no domain event needed), event-type constants, `publish_standalone(...)`. |
| Error hook | `services/common/error_reporting.py` | Uncaught exceptions and failed background jobs → deduplicated, rate-limited, redacted tickets. |
| Redaction | `services/common/redaction.py` | Strips secrets/tokens/PII from every free-text field. Idempotent. |
| UI | `apps/web/components/modules/service/ticket-*.tsx`, `lib/support-api.ts`, `lib/support-derive.ts` | Service → **Ticket Desk** tab (default). |

## Mapping

Rule key = event type. Defaults below; a tenant can override `enabled`, `category`, `priority`, `queue`, default
assignee per rule at **Ticket Desk → Automatic rules** (`ticket_rule_overrides`, `PUT /ticket-rules/{key}`).

| Source | Event | Category / priority / queue | Dedupe key (one open ticket per…) | Links back to |
| --- | --- | --- | --- | --- |
| Inbound email | ✅ live-verified | The communication service's real `email.received` (`communication/mail_state.py`, the email-intelligence work) produced a ticket in the dev tenant, redacted, with the prompt-injection flag carried into the ticket. That publisher was not committed when this was written; outbound failure events (`email.send_failed`, `email.delivery_failed`) are mapped but were not triggered. |
| | `email.send_failed`, `email.delivery_failed` | GENERAL / NORMAL / support | message | communication |
| Agent tasks | `agents.run.failed` (agent jobs **and** workflow runs) | AGENT / NORMAL / agents | agent + error class (ids stripped) | `/dashboard/admin/agents` |
| | `agents.approval.requested`, `agents.task.needs_human` | AGENT / NORMAL / agents | approval / task id | agents |
| Call centre | `callcenter.call.missed` (inbound call ended unanswered/abandoned) | CALLS / NORMAL / calls | caller (hash, never the number) | call centre |
| | `callcenter.callback.requested` (session ended with outcome `CALLBACK`) | CALLS / NORMAL / calls | call session | call centre |
| Finance | `finance.payment.failed` (saved-card charge declined, billing) | BILLING / HIGH / finance | invoice | billing |
| | `finance.reconciliation.exception` (bank line saved as `review`) | BILLING / NORMAL / finance | statement line | finance |
| | `platform.billing.subscription.payment_failed`, `platform.billing.payment.review` | BILLING / HIGH / finance | subscription / order | billing |
| HomeDome / IoT | `iot.home.offline` | HOMEDOME / HIGH / technical | home | `/dashboard/home-dome` |
| | `iot.home.recovered` | *comments on the open offline ticket, never opens one* | home | |
| | `iot.support.requested` | HOMEDOME / HIGH / technical | home | home-dome |
| | `iot.gateway.failed`, `iot.integration.failed` | HOMEDOME / NORMAL / technical | home (+ integration) | home-dome |
| System | `system.error.raised` (uncaught exception), `system.job.failed` (background task crash, dead event delivery) | SYSTEM / NORMAL / platform | fingerprint | — |
| Anything | `ticket.requested` (`request_ticket(...)`) | from the payload | caller's `dedupe_key` | caller's `/dashboard…` link |

**Not tickets (by design):** `system.health.*`, `*.heartbeat`, `*.ping`, `*.debug`, anything with `level: debug|info`,
`iot.gateway.activated`, `iot.integration.connected`, and unmapped events. Only relative `/dashboard…` links are kept.

## Dedupe, repeats, escalation

* Partial unique index `uq_tickets_open_dedupe (tenant_id, dedupe_key) WHERE dedupe_key IS NOT NULL AND status NOT IN ('CLOSED','RESOLVED')`.
  `INSERT … ON CONFLICT DO NOTHING` means two consumers racing on one key cannot both create it (tested with 8 concurrent writers).
* A repeat adds a system timeline entry (repeats 2–5, then every 10th, so a hot loop cannot flood the timeline), bumps
  `occurrence_count` / `last_occurrence_at`, and raises priority at 10 (HIGH) and 50 (URGENT) occurrences. Priority never drops.
* A closed ticket is **not** silently reopened by a recurrence: a new ticket opens and links the previous one
  (`context.previous_ticket_id`). Agents can still reopen a ticket by hand (refused with 409 if a newer open ticket tracks the same key).
* Events are at-least-once; redelivery folds into the same open ticket.

## Error hook

`configure_production(app)` (every service) installs it on the 500 handler; `schedule_background` reports crashed
background tasks; `EventConsumer` reports dead deliveries.

* Fingerprint = `sha1(service | exception type | innermost in-repo frame file:function)`; the message does not matter.
* Rate limit: one published report per fingerprint per `ERROR_REPORT_WINDOW_SECONDS` (default 300), suppressed repeats are counted and
  carried on the next report, plus `ERROR_REPORT_MAX_PER_MINUTE` (default 20) per process. The bus idempotency key adds the same window across workers.
  So `occurrence_count` on a system ticket counts *reports*, not every crash; `suppressed` is in the timeline text.
* Never leaks: message passed through `redact_text`, traceback reduced to `file:line in function` frames (no locals, no source lines),
  route is the template (`/items/{item_id}`), never the raw URL. Ignored: cancellations, client disconnects, any exception with a 4xx `status_code`.
* Where the ticket lands: `PLATFORM_OPS_TENANT_ID` if set (recommended: one ops tenant sees all system bugs), else the tenant of the
  verified request, else `DEFAULT_TENANT_ID`. With none of those, nothing is filed (and nothing breaks). `ERROR_TICKETS_ENABLED=false` turns it off.
* The ExceptionGroup that `BaseHTTPMiddleware` wraps around the real error is unwrapped before fingerprinting.

## Redaction

Bearer/JWT/API-key shapes, `password=`/`token=`-style assignments, URL credentials and secret query params, private keys, long hex/base64 blobs,
e-mail addresses, SA ID numbers, card numbers, bank account numbers, phone numbers. Structured data: values under secret-looking keys are dropped,
values under personal-detail keys (`email`, `phone`, `name`…) are replaced. It is applied at the hook, in the rule table **and** on insert
(so a source that forgets still cannot leak), and is idempotent. Phone numbers never travel on the bus: the call centre publishes a hash and the last 3 digits.

## Ticket events (automations) and memory

* The support service publishes `support.ticket.created | repeated | closed | reopened | assigned`. They, and all source events above, are in
  `services/agent_orchestrator/workflow_catalog.py::EVENT_LABELS`, so a workflow can trigger on them. Automations stay draft-only.
* The knowledge indexer's existing `tickets` source (`tenant_memory/knowledge/cards/sources.py::fetch_tickets`) re-indexes a ticket whenever
  `updated_at` moves, so repeats, comments, assignment and closure all reach memory. Cards now carry source, queue, occurrence count and the originating record.
  Internal notes and system timeline entries are private and are not indexed; the card deep link is `/dashboard?section=service&ticket=<id>`.

## Data model (additive; `init_tables()` runs the ALTERs at support startup)

`tickets`: `ticket_no` (BIGSERIAL, shown as `T-123`), `source`, `source_ref_type/id`, `source_link`, `event_type`, `dedupe_key`, `occurrence_count`,
`last_occurrence_at`, `queue`, `sla_due_at`, `first_response_at`, `created_by`, `context` (JSONB); `customer_id` is now optional (system tickets).
`ticket_replies`: `kind` (`comment | event | status | assignment`), `data`. New table `ticket_rule_overrides`.
SLA hours by priority: URGENT 4, HIGH 8, NORMAL 24, LOW 72 (`ticketing.SLA_HOURS`); state is computed (`ok | due_soon | breached | met | missed`).

## Status of each source

| Source | Wired | Notes |
| --- | --- | --- |
| HomeDome / IoT | ✅ live-verified | Real `emit()`/`report_failure()` publishers. New: `iot.gateway.failed`, `iot.integration.failed` (gateway activation and guided setup, customer-input errors excluded). |
| Agent runs | ✅ live-verified | Real `failure_events` publishers on job + workflow failure. Approvals reuse `agents.approval.requested`. `agents.task.needs_human` has a publisher helper but no caller yet. |
| Finance: reconciliation | ✅ live-verified | Real `POST /bank-items` with status `review`. There is no auto-matching engine, so plain `unmatched` lines are not tickets. |
| Finance: failed payments | ✅ code + unit-tested | Hook is in `billing/routes/payment_methods.py` (saved-card charge declined). Not live-triggered (needs a Paystack decline). Paystack `invoice.payment_failed` webhooks are not wired yet. |
| Inbound email | ✅ consumer live-verified with the real event shape | The publisher (`communication/mail_state.py` → `email.received`) belongs to the in-flight email-intelligence work; it was not deployed when this was verified, so the live test published the same payload shape directly. |
| Call centre | ✅ code + unit-tested | Hooks in `telephony/bridge.py` (missed) and `main.py` (callback outcome). Needs a real Asterisk call to trigger live. |
| System errors | ✅ live-verified | Real middleware + bus + consumer; six crashes → one redacted ticket. Worker failures: same path, unit-tested. |
| Support requests / manual | ✅ | Desk create; `request_ticket()` for any service. |
| Compliance, RICA, lifecycle | ❌ not wired | No event publishers yet. Add one `publish(...)` and one rule entry each; nothing else changes. |
| Attachments | ❌ | The support service has no file storage; the desk does not offer attachments. |

## Operating notes

* Set `PLATFORM_OPS_TENANT_ID` in `.env` to collect system errors on one tenant.
* The consumer runs inside the support service, which must stay a single worker (SSE fan-out is process-local); the bus claims are safe across workers anyway.
* The web image could not be rebuilt on this machine (C: below the 3 GiB free-disk guard), so the backend was deployed by copying the changed files into
  the running containers; the next image build picks everything up. The Service → Ticket Desk UI needs a web rebuild/redeploy to appear on :3000.
