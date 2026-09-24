# Spec: lead-automations (event listeners → Agentic Flow Orchestrator)

Module of `CAPABILITY-MAP-sales-lifecycle.md`. Build order 4 of 4.

## Objective

Make the three cards on Sales → AI Lead Warming real: when the portal or website
reports an abandoned basket, a quote request, or an inactive registration, the
orchestrator moves the lead's stage and has DomeBot draft the warm-up message.

## Design

1. **Intake**: `POST /api/events` on the orchestrator (tenant headers, same auth
   as every service; web path `/api/orchestrator/events`) takes
   `{type, payload, idempotency_key?}`, validates the type
   (`^[a-z][a-z0-9_]*(\.[a-z0-9_]+)+$`) and publishes it on the bus. Returns 202
   with the event id. Repeating an idempotency key is a no-op.
2. **Event-triggered workflows**: `workflows.trigger_event` (new column). The
   orchestrator's `EventConsumer("orchestrator")` subscribes to `*`; for each
   event it runs every `active` workflow of that tenant whose `trigger_event`
   matches, with `input = {event: {...}}`, run trigger `event`.
3. **Engine**: `http_request` nodes resolve `{{...}}` templates inside the body
   (recursively) and accept `service: "sales"` (base URL from
   `SALES_SERVICE_URL`) which also adds the tenant/user headers.
4. **Sales automation endpoint**: `POST /automation/lead-events`
   `{event_type, contact{first_name,last_name,email,phone,address}, source,
   target{status | stage_name}, value_zar?, note}` upserts the lead by email then
   phone, applies the stage through the `lead-lifecycle` rules (only forwards,
   never backwards), writes a timeline entry, returns the lead.
5. **Templates**: `POST /api/workflows/templates/lead-warming` installs (idempotent
   by name) three active workflows:

| Card | trigger_event | Stage | AI step |
|---|---|---|---|
| Abandoned basket (>2 h) | `portal.cart.abandoned` | NEW → CONTACTED | DomeBot drafts a recovery message (voucher FIBERWARM15 + free installation) |
| Instant quotation request | `portal.quote.requested` | → pipeline **Proposal** (deal created with the quoted value) | DomeBot drafts the quote cover note + follow-up |
| Registration inactive (>24 h) | `portal.registration.inactive` | → QUALIFIED | Concierge drafts a friendly coverage-check message |

   Each: trigger → `http_request` (sales automation endpoint) → `agent_invoke`
   (draft) → `http_request` (save the draft on the lead's timeline as
   "AI draft — review and send").

6. **Web**: the three cards show real state — installed/active, runs in the last
   7 days, last run status — with "Install automations" when missing and
   "Send test event" per card (payload clearly marked as a test).

## Not in v1 (documented follow-ups)

- Detecting abandonment/inactivity by polling `customer_journey` carts and
  portal accounts. Linking a cart to a person needs the customer's contact from
  billing/customer services that are not running locally. v1 accepts these
  events from whichever system knows (portal, website, customer_journey later)
  through the intake endpoint.
- Auto-sending AI messages to customers: drafts only until an approval step exists.

## Success criteria

- [ ] Test event for each card → lead created/advanced, workflow run succeeded,
      AI draft on the timeline (or a clear "AI unavailable" step when every
      model is rate-limited), notification in the bell.
- [ ] Same idempotency key twice → one run.
- [ ] Orchestrator stopped while events arrive → they run when it is back.
- [ ] Cards show real run counts.
