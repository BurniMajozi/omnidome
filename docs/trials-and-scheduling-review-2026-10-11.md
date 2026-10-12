# Trials and scheduling review — 11 October 2026

Scope corrected by the owner: this is OmniDome's own signup, trial and sales-demo journey. It does not add booking pages or trial subscriptions for tenants to sell to their customers. Reuse PostgreSQL, the existing calendar, the workflow scheduler and Communication/AgentMail for OmniDome's sales team. Keep Cal.diy as an optional experiment.

This is a review and implementation design. Trial provisioning and public demo booking have not been implemented or deployed by this review.

Follow-up: the six-panel permanent Free plan and a sourced tool-price comparison are now deployed locally. [Implementation and verification](free-plan-and-tool-comparison-2026-10-11.md). Automatic trial-to-Free expiry and the OmniDome demo booking page remain to build.

## What works today, and what the buttons promise

- Both “Start Your Free Trial” buttons in `apps/web/app/page.tsx` link to `/auth`. That page signs in existing users; it does not start a trial.
- Both homepage “Schedule a Demo” buttons have no link or click handler.
- ISP customer subscriptions support `trial_days` and `trial_ends_at` in `services/billing/routes/subscriptions.py`. Those are customers buying connectivity from a tenant. They must remain separate from tenants trying the OmniDome platform.
- Platform pricing already provisions tenant panels and usage allowances through `services/common/platform_commerce.py`. The reviewed platform commerce code has no tenant trial lifecycle.
- Communication has authenticated, tenant-scoped calendar CRUD in `services/communication/routes/schedule.py`, with timezone-aware start/end validation and tenant/user/channel access checks. `ScheduleEvent` requires a channel. Its create route does not reserve availability or prevent overlapping bookings.
- The orchestrator scheduler claims cron workflows using a PostgreSQL advisory lock, advances their next run, and runs them outside the transaction. It ticks every 60 seconds. That is useful for reminders and expiry checks, but it is not a public appointment booking service. A crash between advancing a schedule and executing it can lose that occurrence; important reminders need durable jobs and recovery.
- Live signed checks succeeded for tenant-owner usage, logs, orders and delivery controls. Memory/RAG hybrid recall returned three knowledge hits. Credit sales are still disabled, with a R50 minimum and no published per-credit selling price. A trial must have its own enforced budget even while paid credit charging is disabled.

## The trial journey

Proposed launch defaults: **14 days, no card required, three seats and 50 trial AI credits total**. These are conservative product proposals, not claimed industry standards or published commercial settings. Confirm provider cost per credit and configure a monetary spending ceiling before enabling external AI for trials.

1. The visitor chooses a bundle or modules, sees the paid price and the exact trial limits, then chooses “Start 14-day trial”. The homepage button opens this selection journey instead of sign-in.
2. Verify the email, create the tenant, and assign its creator the tenant Owner role. Trial registration must never grant Platform Owner access. Start the clock only when verification and provisioning complete successfully.
3. Snapshot the selected catalogue version, panels, trial quotas and UTC start/end timestamps. Use the same entitlement resolver as paid provisioning so the UI and backend agree. Overview and Admin stay available and free.
4. Show a persistent “Trial: 9 days left” banner. Platform Billing & Usage shows selected plan, paid price, credits allocated/used/remaining, usage by panel, expiry date and “Upgrade with Paystack”. Distinguish trial credits from purchased credits.
5. Deduplicate reminders at three days remaining, one day remaining and expiry. Owner notices are in-app by default. Transactional email requires an explicitly enabled communication policy and working sender configuration; marketing consent is separate.
6. At expiry, default the organisation's OmniDome subscription to the permanent Free plan: CRM, Services, Portal, Retention, Product and Stock, plus Overview and Admin. Remove trial-only paid grants and stop new paid operations; preserve records, invoices, audit history and purchased balances. Free includes one seat, 100 successful writes per panel per UTC month and 50 shared monthly AI credits. A purchased balance does not buy an advanced feature entitlement. Trial and monthly Free grants must have distinct, idempotent ledger keys. If a trial has more active members than Free permits, preserve their accounts and require the owner to select the active Free seat; expiry cannot rely on ordinary plan saving, which rejects excessive seat occupancy.
7. Upgrading shows the current quote and starts Paystack checkout. Only a verified, idempotently processed successful payment activates paid access and starts the paid billing period. Do not invoice the elapsed free trial. Subsequent paid plan changes use existing proration.

Trials should be one per verified organisation under a documented eligibility policy. Repeated clicks, retries, invitations and creating another user must not replenish credits or reset expiry. Platform Owner can extend a trial with a reason and an audit entry. Selecting another plan during a trial can change the previewed panels within policy, but not reset its clock or budget.

Do not offer unbounded Deepgram calls, outbound campaigns, Firecrawl research or hosted agent runtime in the trial. Give each billable provider an explicit allowance and monetary cap, or require prepaid purchase before live use. Reservations must be enforced before work starts. Trial credits should be non-transferable, expire once, and never receive monthly refills.

Expiry must be checked by backend entitlement checks on every protected request. A delayed scheduler must not extend paid access. Handle operations crossing expiry with a documented reservation deadline and charge policy rather than retroactively cancelling completed work.

## The scheduling journey

The first release supports OmniDome sales demos only. Tenant consultations, technician appointments and tenant-branded booking products are outside this request.

- Public “Schedule a Demo” opens a booking page: meeting type → available date/time → name, email and optional company → confirmation. No tenant account is required to request a platform demo. The server resolves the platform sales tenant and host from the public event-type identifier; visitors cannot supply authority headers or an arbitrary tenant ID.
- Admin scheduling settings define hosts, working hours, IANA timezone, days off, duration, before/after buffers, minimum notice, booking horizon and capacity. Start with one explicitly assigned host; add team rotation only when needed.
- OmniDome sales staff see a calendar/list, availability settings, cancellations, reschedules and delivery status. Platform Owner manages OmniDome demo types and authorised hosts. Tenant owners do not receive booking administration for this platform sales calendar.
- Store booking times in UTC and display the visitor's timezone, defaulting to Africa/Johannesburg when appropriate. Public slots expose availability, not attendees, event titles or internal notes.
- Recheck availability inside the booking transaction. Prevent overlaps with a database constraint or consistent per-resource lock that also covers internal calendar edits, external busy-time imports and reschedules. A frontend slot check alone cannot prevent double bookings.
- Use expiring holds and idempotent booking requests. Cancellation/rescheduling links use scoped, expiring tokens whose values are redacted from logs. Recheck the new slot before releasing the old reservation.
- Publish booking confirmed/rescheduled/cancelled facts through the existing transactional outbox. A booking can succeed while email is pending; show and retry delivery separately.
- Add durable scheduled actions for reminders, such as 24 hours and one hour before a meeting. Claim due jobs with leases, retry boundedly and deduplicate by booking/version/action. Rescheduling invalidates old reminder jobs. Deterministic reminders need no LLM call.

Reuse `schedule_events` as the staff calendar projection, with explicit channel permissions; add booking-specific records rather than exposing its authenticated CRUD publicly. Suggested new records: event types, host availability/exceptions, bookings/holds, provider mappings and scheduled actions. Proposed public endpoints provide event-type details, slots, booking and token-scoped cancellation/rescheduling; authenticated endpoints manage settings and internal appointments.

## AgentMail can help more than just sending email

AgentMail now documents a **Calendar beta**: each inbox has a calendar, can create events and invitations, receive emailed invitations, and emit start/end webhooks. It requires an organisation admin to enable Labs and is currently available on the US production endpoint, not EU. Our existing integration has not been verified as having that access. [AgentMail Calendar](https://docs.agentmail.to/calendar)

Use it as an optional invitation/calendar adapter. OmniDome remains the authority for bookings and resource conflicts. An inbox calendar does not establish that a staff member's Google/Outlook calendar is free; external busy-time integration must be built and tested explicitly.

Use a stable booking ID as the provider `client_id`, and conditional updates with ETags. Invitation emails consume send limits per recipient; provider update retries can resend email. Keep provider state, revision and delivery attempts locally. [Calendar concurrency and limits](https://docs.agentmail.to/calendar-reference)

If Calendar Labs is unavailable, regular email plus an ICS download is a viable first release. AgentMail supports attachments, but our Communication attachment schema currently allows only PDFs, so ICS support needs a bounded, validated extension. [AgentMail attachments](https://docs.agentmail.to/attachments)

## Cal.diy comparison

| Consideration | Native OmniDome scheduling | Cal.diy |
| --- | --- | --- |
| OmniDome staff identity and permissions | Reuses current user and role model | Needs staff account linking and a booking-to-CRM bridge |
| Public booking UI | Must build the narrow initial journey | Existing scheduling application to evaluate |
| Teams and organisations | Can use our existing membership model | Removed according to the README; not needed for a single-host demo pilot |
| Workflow automation | Reuses our event bus and scheduler | README says its Workflows feature was removed |
| Hosting | Extends existing services/database | Sample Compose includes web, API, PostgreSQL and Redis; Studio is optional |
| Email | Existing Communication/AgentMail API | SMTP configuration can potentially use AgentMail |
| Trials, credit limits and Paystack | Integrates with our platform commerce | Still requires our own platform billing integration |

Cal.diy is MIT licensed. Its maintainers describe it as a personal, non-production self-hosted edition and direct commercial users to Cal.com. This materially affects its suitability for OmniDome; the licence itself is not the reason to reject it. [Repository and feature differences](https://github.com/calcom/cal.diy), [MIT licence](https://github.com/calcom/cal.diy/blob/main/LICENSE)

With the corrected OmniDome-only scope, Cal.diy could technically serve a single sales host. Multi-tenant booking and missing enterprise features are no longer the deciding objections. The recommendation to build the narrow native journey rests on reuse of our deployed services, the extra hosting and integration work, and the project's stated production suitability.

The supplied deployment adds a separate application stack and exposes ports that overlap our existing services. On the shared 8 GB host, assess actual memory and build requirements before any pilot; no capacity benchmark was run in this review. Sample environment files also retain enterprise/Stripe settings despite the README's removals, so those settings are not evidence that the advertised commercial features work. [Compose configuration](https://github.com/calcom/cal.diy/blob/main/docker-compose.yml)

Cal.diy's SMTP configuration and AgentMail's documented SMTP support make email integration plausible without replacing Paystack. It has not been tested. Use TLS, an authorised inbox From address and secrets outside source control. SMTP credentials alone do not connect calendar availability or tenant usage billing. [Cal.diy email settings](https://github.com/calcom/cal.diy/blob/main/.env.example), [AgentMail SMTP](https://docs.agentmail.to/imap-smtp)

## Delivery order and acceptance checks

1. Build verified tenant trial provisioning, shared entitlement enforcement and the Billing & Usage trial state. Test retry safety, expiry with the scheduler down, budget exhaustion, role separation and upgrade webhook replay.
2. Build the public demo journey plus host availability settings. Test simultaneous booking, buffers, timezone/DST conversions, cross-tenant access, internal-event conflicts and rescheduling while a reminder is claimed.
3. Connect transactional notices and the AgentMail adapter. Test provider outages, stale ETags, duplicate webhooks and email failure independently of booking success. Confirm a provider invitation appears in a real calendar before advertising calendar sync.
4. Add Google/Outlook busy-time adapters when OmniDome sales staff need them. Tenant appointment and technician dispatch products are outside this request.

Use a phone-width browser acceptance check for both journeys before launch. This review inspected source and live APIs; it did not visually verify a new trial or booking UI, enable AgentMail Labs, install Cal.diy, send invitations, publish credit rates or change live tenant access.

One additional configuration issue was observed: the checked-out `apps/web/lib/platform-pricing.json` contains VAT registration enabled and a placeholder VAT number, contrary to the owner's instruction that the business is not registered. Subsequent live verification confirmed the persisted supplier settings override the catalogue: VAT registration is false and VAT-inclusive display preference is true. Those live settings were preserved. Reconcile the catalogue fallback before a fresh installation; this review did not overwrite another agent's tax-default changes.
