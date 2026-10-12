# Dome naming, free entry points and demo buttons

The web copy now uses **Try it For Free** for OmniDome's free entry points and **Dome** for its product names, including Sales Dome, Marketing Dome, CRM Dome, Service Dome, Communication Dome and the other previously labelled Hubs.

The wording sweep covered product and solution pages, pricing, the landing page, dashboard labels, partner resources, communication pages, module text, catalogue names and related web assets/comments. No standalone Hub or free trial phrase remains in the web source. HubSpot retains its external brand name; its marketing plan is described without relabelling it as an OmniDome product.

All ten demo navigation buttons on the public web pages now lead to `/demo`. This includes buttons that previously did nothing and buttons that incorrectly led to sign-in. Free entry buttons previously labelled Start Free Trial or Get Started Free now use Try it For Free and link to the invitation request journey where appropriate. Existing commercial plan-selection actions remain functional.

## Demo flow

- If the Platform Owner has configured a sales host and availability, visitors select a slot and book using the existing booking implementation.
- Until a calendar is configured, `/demo` offers a working **Request your demo** form. It stores a real request with the visitor's name, organisation and email and confirms receipt; it does not claim that an appointment is already booked.
- The Platform Owner sees demo requests in Platform Billing & Usage → Trial requests and OmniDome demos. Contact visitor opens their email client; Mark contacted persists the request's handling status.
- Repeated submissions for the same pending email are deduplicated. Public submissions have a ten-per-minute limiter. Requests and staff actions remain private to Platform Owners.
- No live sales host was selected automatically, calendar availability invented or customer message sent during verification.

Catalogue module names are also reconciled in the backend, so admin lists and new quotes use Dome labels. Technical module IDs, API routes and saved historical invoices retain their existing identifiers and frozen billing details.

## Checks

- A TypeScript AST check verified all ten demo buttons have a `/demo` destination.
- The source TypeScript check passed, excluding only the previously stale generated `.next/dev` harness imports.
- Existing trial/pricing checks passed; the initial new request test reached the shared anonymous limiter because earlier tests reused its request window. Isolating that window per test preserved the production limiter.
- The four demo/onboarding integration tests passed against PostgreSQL, covering concurrent booking, invitation acceptance, request deduplication/privacy and rate limiting.
- Live RAG recall before this change returned three knowledge matches, and existing owner billing endpoints passed.

The release is deployed locally. The production Next.js build passed, and live checks verified the new free CTA and `/demo` links, Sales Dome on the public product page, the demo and free invitation pages, public form validation and anonymous denial of the private admin endpoint. The demo request endpoint responds through the public web proxy; no calendar is configured, so the request form is the available journey.

Live deployment backups are tagged `before-20261012104245`. Previously stopped services were preserved in their stopped state, and the startup watchdog is active. PostgreSQL and WSL were not restarted for this release.

Post-deployment verification caught a dropped knowledge database URL when Compose recreated tenant memory. The existing configuration was recovered without printing or committing credentials. Deployment now preserves those settings in the child environment, and hybrid RAG recall again returned three knowledge matches. Existing tenant-owner billing/usage/invoice endpoints also passed after recovery.

Interactive browser checks remain unavailable under the earlier browser security restriction. Refresh the existing browser tab to load the new web build. No live request, booking or invitation was created during verification, and no message was sent.
