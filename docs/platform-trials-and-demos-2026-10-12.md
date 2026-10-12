# OmniDome trials and sales demos

This is OmniDome's own acquisition and platform billing journey. It does not change tenant ISP customer subscriptions or introduce tenant booking products.

## Trial journey

- The home page trial buttons open `/trial`. A visitor requests an invitation with their name, organisation and email. Existing verified organisation owners can start an eligible trial in Platform Billing & Usage.
- Platform Owner → Platform Billing & Usage → **Trial requests and OmniDome demos** reviews requests and provisions an organisation with an owner invitation. New invitations use the existing email code and verified account acceptance flow; requesting a trial alone grants no anonymous account access.
- A new organisation's trial remains pending until its owner accepts the invitation. The full 14 days begin at acceptance. Existing owners' trials start immediately.
- One trial per organisation: three seats, Professional features across the priced panels and **50 shared total trial AI credits**, without a payable trial invoice, card requirement or automatic expiry charge.
- Trial credit reservations are enforced even while paid top-up rates remain unpublished. These are the project's current AI metering units, not free Deepgram minutes, email capacity or a guarantee of actual supplier spend.
- The admin sweep expires trials every minute. Shared panel guards, credit reservations, pricing reads and usage reads also reconcile expiry, so a stopped scheduler does not grant indefinite trial access.
- Expiry provisions permanent Free: CRM, Services, Portal, Retention, Product and Stock, plus Overview and Admin. Free's included AI allowance continues in monthly windows rather than expiring after its first month.
- Records, members, invitations and purchased credits remain. The included Free business-panel seat defaults to the active owner. Additional members retain their identities and appropriate Admin access. The owner chooses the included member in Billing & Usage, or buys more seats. Trial expiry does not delete or deactivate people.
- Paid and negotiated plans cannot be replaced by a trial. Direct tenant settings edits cannot reset or extend trial state.
- Upgrades use the existing invoice/Paystack verification flow. Redirects alone never activate paid access. An already-issued upgrade invoice can cross the trial deadline without being invalidated solely by Free fallback. Successful plan activation supersedes the trial.

## Demo journey

- Home page **Schedule a Demo** opens `/demo`. The Platform Owner configures OmniDome's dedicated sales host, IANA timezone, weekday working hours and optional HTTPS meeting link. The UI selects a named member rather than requiring a user ID.
- Public booking remains closed until a real host is configured. No existing user was automatically assigned as a sales host.
- The initial calendar is deliberately narrow: one host, Monday–Friday, 30-minute meetings, 15-minute buffers, two hours' notice and a 30-day horizon. Device-local times are shown to visitors; host working hours use the configured timezone.
- Booking rechecks availability while holding a database resource lock. Communication calendar creates and edits use the same host lock and reject collisions with demo bookings. Public slots contain no attendee identities or internal event descriptions.
- Booking requests are idempotent. Expiring private management links allow cancellation or moving an existing meeting; a failed move rolls back and preserves the previous booking. Tokens live in URL fragments and POST bodies, rather than access-log paths.
- When no sales host is configured, the public demo page offers a real request form instead. Platform Owners review those requests, contact the visitor and persist the contacted status. Receiving a request does not confirm an appointment.
- Confirmation, cancellation, reschedule and 24-hour/one-hour reminder jobs are stored durably. Rescheduling invalidates pending jobs from the previous version. Delivery is independent of booking success.
- AgentMail sends transactional notices when configured. A provider timeout or ambiguous partial delivery is marked `unknown` for owner review, rather than blindly sending duplicate emails. Test databases are explicitly excluded from external demo-email delivery.
- These are calendar reservations and email notices. Google/Outlook busy-time sync, AgentMail Calendar beta, ICS invitations, team rotation, weekend/custom day schedules and automatic meeting-link generation are not implemented or advertised.

## Validation and deployment

- PostgreSQL trial, onboarding and existing pricing suite: **17 passed**. This includes simultaneous booking, invalid management tokens, failed moves, shared-calendar conflict checks, invitation retry safety and activation only after verified acceptance.
- Trial, demo and existing wallet suite after the final lifecycle changes: **11 passed**.
- Existing credit/pricing checks: **28 passed**, followed by a corrected test fixture and passing trial budget test; production code was not the cause of that fixture failure.
- Permanent Free credit rollover and common usage checks: **5 passed**.
- Communication regression checks: **36 passed**.
- Source TypeScript passed with only the existing generated `.next/dev/deck-harness` files excluded. The ordinary check reported two stale generated imports in that unrelated harness.
- Local deployment is staged with image backups and checks for concurrent deployments. The shared guard must be updated across API panels, not only billing. PostgreSQL, Ollama and WSL are not restarted.
- Interactive browser verification remains unavailable under the earlier browser security policy. Responsive layouts and build/API checks do not substitute for a visual acceptance check.

The initial shared-guard deployment was interrupted when WSL became unresponsive. After the owner-authorised recovery, the trial/demo release and Dome branding changes were deployed locally on 12 October. Production build and live public/private API checks passed. Memory configuration lost during Compose recreation was restored, and RAG recall again returned three knowledge matches. No live trial was started, booking created, invitation sent, credit price published or automatic recharge enabled during verification.

## Setup

The Platform Owner configures the sales host and working hours in the onboarding section. Ensure `APP_PUBLIC_URL` points to the public OmniDome origin before sending invitations or demo management links. Keep internal signing and invitation secrets configured. Paid credit top-ups still require separately publishing a selling price; the existing minimum remains R50.

Code is in the shared workspace alongside earlier pricing and workflow changes. No blanket commit or staging was performed while those changes remain shared.
