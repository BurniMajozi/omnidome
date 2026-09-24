# Spec: event-bus (Postgres message broker + notifications)

Module of `CAPABILITY-MAP-sales-lifecycle.md`. Build order 1 of 4.

## Objective

Give services a durable way to tell each other that something happened, so a
slow or stopped service delays work instead of losing it, and a busy one does
not block the caller. Give people one place to see what needs their attention
(the header bell).

Success looks like: sales records "send this lead an email" and returns in
milliseconds; the email goes out a moment later; if the mail provider is down,
delivery retries with back-off; after the last retry it lands in a dead-letter
state that is visible and retryable, and a notification says so.

## Design

**Transactional outbox + per-consumer deliveries**, all in the shared `coreconnect`
Postgres. No new container.

| Table | Purpose |
|---|---|
| `domain_events` | One row per fact: `id, tenant_id, event_type, source, subject_type, subject_id, payload jsonb, idempotency_key, created_at`. Unique `(tenant_id, idempotency_key)` when a key is given. |
| `event_subscriptions` | `(consumer, event_pattern)`; a pattern is an exact type, `prefix.*`, or `*`. Consumers upsert theirs at startup. |
| `event_deliveries` | One row per (event, consumer): `status pending/processing/delivered/dead, attempts, next_attempt_at, locked_until, last_error, delivered_at`. |
| `notifications` | Feed: `tenant_id, recipient_id (null = whole tenant), category, severity info/warning/critical, title, body, link, source, subject_type, subject_id, created_at, read_at`. |

`services/common/event_bus.py`:

- `await publish(session, tenant_id, event_type, payload, *, source, subject=None, idempotency_key=None) -> uuid`
  inserts the event **and** a delivery row for every matching subscription,
  using the caller's session, so it commits or rolls back with the business
  change. A repeated idempotency key returns the first event's id and adds nothing.
- `await notify(session, tenant_id, title, *, body, category, severity, link, recipient_id, source, subject)`.
- `EventConsumer(name, handlers)`: `handlers` maps patterns to `async fn(event: dict)`.
  `start()` upserts subscriptions and runs a loop that claims due deliveries with
  `FOR UPDATE SKIP LOCKED` (safe across uvicorn workers and replicas), calls the
  handler, then marks the delivery `delivered`, or re-queues it with back-off, or
  after `MAX_ATTEMPTS` marks it `dead` and writes a critical notification.
  A delivery stuck in `processing` past `locked_until` (worker crashed) is re-claimed.
- Pure helpers (unit-tested): `pattern_matches`, `retry_delay(attempts)`,
  `is_exhausted(attempts)`, `normalise_event_type`.

Retry schedule: 10 s, 30 s, 2 min, 10 min, 30 min, 1 h, 1 h; 8th failure → dead.

Delivery is **at least once**: handlers must be idempotent (they get the event id
to dedupe on). A consumer only receives events published after its subscription
exists.

## API (served by `agent_orchestrator`, web path `/api/orchestrator/...`)

| Method | Path | |
|---|---|---|
| GET | `/api/notifications?unread_only=&limit=` | feed, newest first, tenant-scoped |
| GET | `/api/notifications/unread-count` | `{count}` |
| POST | `/api/notifications/{id}/read` | mark one read |
| POST | `/api/notifications/read-all` | |
| GET | `/api/events/deliveries?status=dead` | operations view: failed deliveries with event + error |
| POST | `/api/events/deliveries/{id}/retry` | put a dead delivery back to pending |

Web: the header bell shows the unread count and a dropdown feed (poll every
30 s, and on open); clicking an item marks it read and follows its link.

## Commands

- Tests: `cd services/fno_intelligence && ../../.venv/Scripts/python.exe -m pytest tests/ -q`
  (helpers live in `services/common`; the fno suite already hosts common's tests).
- Orchestrator tests: `cd services/agent_orchestrator && ../../.venv/Scripts/python.exe -m pytest tests -q`
- Web: `npx tsc --noEmit -p tsconfig.json`, `npx eslint <files>`
- Migration: `config/migrations/20260925_event_bus.sql` (idempotent), applied to `coreconnect`.

## Boundaries

- Always: publish inside the caller's transaction; handlers idempotent; tenant-scope every read.
- Ask first: adding Redis/NATS; exposing the bus to the public internet.
- Never: send customer-facing messages from a retry loop without an idempotency guard; drop dead deliveries silently.

## Success criteria

- [x] Unit tests for pattern matching, back-off and exhaustion.
- [x] Live: an event published in a rolled-back transaction leaves no rows.
- [x] Live: a handler that fails twice then succeeds is delivered on attempt 3.
- [x] Live: a handler that always fails ends `dead` with a critical notification; retry endpoint re-queues it.
- [x] Two consumer loops never deliver the same row twice.
- [x] The bell shows real notifications and the unread count.
