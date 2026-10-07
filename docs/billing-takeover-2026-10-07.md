# Billing takeover — 7 October 2026

Recovered Claude's final local session handoff and verified the two implementation commits against the working tree.

## Verified and published

- Backend: `ca552cc9`; UI: `08f520ee`. Both pushed to `origin/main`.
- Re-ran the billing suite on the committed code: **245 passed, 3 skipped** (SQLite harness).
- Fixed the local Compose command overriding the Dockerfile's `--no-access-log`: `40f55122`, pushed.
- Mirrored Billing, Common and Web source to the WSL runtime without copying environment files.
- Billing rebuilt using its existing dependency image, recreated, and passed its PostgreSQL-backed startup health check.
- Previous Billing and Web images retained as `pre-takeover` for rollback.
- Shared invoice/quote editor now uses labelled cards below the desktop breakpoint; fixed grid minimum widths that pushed phone dialogs sideways. Commit `3c1627d3`, pushed.
- Focused TypeScript check of the three changed editor files and their imports passed. The normal local check reports three stale `.next/types/validator.ts` references to removed portal routes. The container-wide check was stopped after several minutes; a full-project clean type check is not claimed.
- Both Web production builds passed and `/auth` returned HTTP 200 after recreation.
- Browser checks reached Invoices, Quotes, Items & Templates, Movements and the Fee policies simulator, plus Field Sales and Technician document tabs.
- Invoice preview: quantity 2 × R100 gives R200 net, R30 VAT, R230 total.
- At 375 × 812, the updated dialog's client width and scroll width both measured 358px; totals and save controls stay within the viewport. Temporary viewport override reset afterward.
- Public proxy smoke checks: invalid well-formed token returns 404; malformed/undocumented public calls require authentication (401).

## Local deployment complete

Web build logs: `/home/benedict/build_logs/web-takeover.log` and `/home/benedict/build_logs/phone-billing.log` in WSL.

The restart watchdog (`omnidome-watch.service`, user service) was restarting applications during shutdown. It was paused during the builds and re-enabled after restoring the original running stack.

Final restoration succeeded for Admin, Billing, Communication, CRM, Finance, Sales, Inventory, FNO Intelligence, Agent Orchestrator, Portal Builder and Web. Every service with a Docker health check reported healthy; Web reported running and its HTTP health check passed. Database and Hermes stayed running during the Web builds. The deployed Billing workspace is left open in the in-app browser.

## Verification limits

- The 245-test billing suite uses SQLite. Live startup and browser reads use the existing PostgreSQL runtime; real payment, email delivery and Finance posting transactions were not exercised.
- No invoice was saved or issued, no message sent, no payment made, and no fee policy seeded during browser verification.
- The documentation simulator needs an active policy in the current tenant. This tenant currently has none; the server returns no applicable policy. The canonical R1750 net / R2012.50 including VAT calculation is covered by the passing backend tests.

## Existing integration gaps from Claude's handoff

- Call-centre queue, mailer builder, upgrade/downgrade review and refund payout actions lack billing endpoints.
- Communication delivery/bounce callbacks are not integrated with Billing.
- PDF output uses browser printing.
- Field/technician create and send permissions need a separately designed role policy; permissions have not been expanded.
- Customer-app requests require a verified customer identity.
- Per-user invoice filtering needs follow-up; the phone layout is fixed and deployed.
- Hermes/ngrok credential rotation and Supabase SMTP/signup settings are separate configuration work.
