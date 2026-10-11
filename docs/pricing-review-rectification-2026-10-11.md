# Pricing review rectification — 11 October 2026

Implementation and verification record for `pricing-review-2026-10-11.md`. Paystack remains the payment provider. PostgreSQL remains the entitlement and usage authority. Autumn is optional and stopped; Stripe is not required.

## Supplier and VAT decision

The platform is **not VAT registered**. The default address is **9 Short Road, Zandspruit, Rooderport, 2169**, as supplied by the owner. The initial trading name is OmniDome; the Platform Owner can replace it with the supplier's legal or trading name in Admin → tenant → Plan, panels & invoices → Invoice details and VAT settings.

VAT registration and catalogue VAT inclusion are separate checkboxes. Unregistered suppliers charge **R0 VAT**, regardless of the inclusion checkbox. A registered supplier must supply a valid-format VAT number before saving. Inclusive pricing preserves the advertised gross price; exclusive pricing adds VAT at checkout. For Growth R599: unregistered total R599; registered inclusive net R520.87 + VAT R78.13 = R599; registered exclusive total R688.85.

Customer billing details have a separate form. Supplier/customer details, tax policy and amounts are frozen into each invoice. Updates affect future quotes, not issued invoices. Incomplete required details produce a clearly labelled pro forma. This does not constitute validation of a VAT number with SARS.

Existing recurring subscriptions retain their frozen contractual price and tax policy. If the supplier registers for VAT later, review and replace those subscriptions explicitly; changing the supplier checkbox does not silently change their Paystack plans.

## Review findings

| Finding | Rectification |
|---|---|
| 1. Payment failure/lapse | Paid access ends after the paid period plus seven days' grace. Backend guards return 402 thereafter. Overview/Admin stay available to resolve billing. Free plans and explicitly granted Platform Owner access stay available; legacy negotiated contracts are retained. Stale cancellation/failure events cannot change a replacement plan's billing status. |
| 2. Cosmetic module tiers/full shared allowance | Concrete existing feature endpoints are gated by each panel's tier. Monthly successful mutation-request budgets are enforced atomically: Free 100, Starter 1,000, Professional 10,000, Enterprise 50,000 per selected panel. Failed requests release their reservation. Modular AI allowances sum each selected module's allowance (50/300/1,000); bundles keep their fixed allowance plus add-ons, capped at 10,000. AI credits remain shadow measurements, not purchased credits or enforced token budgets. |
| 3. Missing panels | Analytics, Inventory, IoT and RICA are priced alongside the original 14 panels. Overview and Admin are always free and enabled. Backend module registration includes all 18 priced panels; runtime availability still depends on deploying each service. |
| 4. Manual grants dropped | Explicit extra panel grants are retained in the frozen selection and survive owner repricing. Owner changes remain immediate audited grants; tenant purchases require verified payment or credit settlement. |
| 5. Portal key mismatch | `portal-builder` resolves to canonical `portal`; related journey services use that entitlement. |
| 6. Bundle arbitrage | Growth is R599/month for three seats, below its equivalent Starter modular selection. Higher tiers have concrete feature and capacity gates; changing only the displayed tier no longer grants the highest shared credit pool. Existing invoices retain their previous prices. |
| 7. Plan changes | A plan change starts a new full billing period and deducts unused prepaid net value by time remaining, plus account credit. Excess credit stays on the account; no automatic cash refund. Quotes expire after 15 minutes. Previous recurring billing is disabled through Paystack. Prorated checkout charges the stored difference as a one-off; replacement recurrence uses the full new price from the new period end. Credit-funded paid plans reuse verified authorization where possible; missing authorization or ambiguous setup is explicitly reported. |
| 8. Invoice details | Supplier/customer snapshots, issuance date, quantities and sequential ODP-year-number references are included. A database trigger prevents changing an issued order's commercial snapshot. |
| 9. Add-on loses bundle | Adding modules keeps the bundle. Removing/changing an included panel switches to modular pricing explicitly. |
| 10. Seats/copy | Professional includes six seats; Enterprise eight. Extra seats are R45 for modular/other bundles and R75 for Enterprise. Comparison rows and card copy use the catalogue. |
| 11. Invalid replay | Selection validation precedes idempotency lookup; invalid tier overrides return 422. |
| 12. Cached checkout | Checkout links are reused for 15 minutes, then recreated with a fresh reference. Earlier attempts remain verifiable. |
| 13. Stuck measurement | Admin runs a cleanup task every minute: running operations older than two hours become abandoned without inventing usage charges or supplier costs. Usage reads also recover abandoned work. |
| 14. Public rounding | Public discount calculations operate on integer cents with half-up rounding, matching server invoice rounding. |
| 15. Oversized purchases | Online seat selection caps at 100. Larger deployments require a reviewed contract. |

## UX changes

The comparison grid uses valid CSS grid column syntax, restoring horizontal plan columns. Its overflow is confined to the table on small screens. The plan selector uses authenticated tenant previews for proration, retains bundles with add-ons, and shows tax treatment and credit breakdown. Monthly panel usage appears beside the measured AI allowance. Checkout reports unconfirmed recurring authorization/setup rather than claiming automatic renewal is active.

## Boundaries

Mutation budgets count successful authenticated POST/PUT/PATCH/DELETE requests per panel per UTC calendar month. They are not storage, contact, seat, message or provider-credit counters. Public forms/webhooks remain outside that budget. An interrupted request can conservatively retain its write reservation. Platform Owners bypass panel gates when administering the platform; endpoint RBAC and tenant scope still apply.

AI credits, Deepgram, Zernio, Firecrawl and AgentMail billing remain in the previously configured shadow/review workflow. This change does not enable automatic overage charges or claim a hard ceiling on supplier runtime costs. Optional Autumn services are not needed for these gates.

Payment and recurring-provider regression tests use fakes against a dedicated PostgreSQL test database. No real Paystack payment is made by these checks. Unknown subscription-create outcomes require reconciliation rather than an automatic duplicate request. A new cycle and account-credit policy is implemented; automated cash refunds and statutory credit-note issuance remain separate work.

Verified locally: the PostgreSQL-backed admin/pricing/usage suite, common pricing and proration tests, and Paystack webhook regressions passed **123 tests, zero failures**. A focused follow-up covering the free-core licence startup path passed **5 tests**. The frontend TypeScript check passed using the repository's existing `.codex/tsconfig-tenant-pricing.json` (which excludes stale generated Next route references).

The production Next.js build passed. The initial version-3 rollout completed across the web and 21 core services. The live public API returned 18 priced panels, VAT registration false, inclusive pricing true, and Growth total R599.00 with R0.00 VAT, 500 measured monthly AI credits and 1,000 monthly writes per included panel.

A subsequent review found that editing an already-paid tenant as Platform Owner could replace its payment contract with an indefinite owner grant. The follow-up code preserves the paid deadline and credits unused time on the owner-issued invoice. Manual unpriced grants change no commercial price; they survive verified renewals. The follow-up regression run passed 14 cases, then stopped on a PostgreSQL connection reset (`WinError 64`) before reaching the new owner-edit case. That case still needs verification, and this last backend patch has not yet been confirmed deployed.

Browser verification failed repeatedly with browser-control timeouts. WSL subsequently rejected final deployment commands with `Wsl/Service/0x8007274c`, despite the app's public API responding. Windows briefly had about 300 MB free RAM. Build caches were reclaimed and the deployment watcher was paused during diagnosis. The user reports that another agent is working on the platform; this is not authorization to restart the shared Ubuntu runtime. No WSL restart was performed. Do not treat the browser layout, all service health, or final owner-proration deployment as verified yet.

## Shared-workspace handoff

Leave Ubuntu and shared services running while the other agent works. The `omnidome-watch.service` user deployment watcher remains paused from diagnosis; coordinate restoring it so it does not interrupt the other agent's deployment. Admin (8013) and Billing (8003) health checks returned HTTP 200; Memory (8025) and Agent (8021) were unavailable at the latest check. The earlier read-only RAG context lookup succeeded, but memory availability has not been reconfirmed after rollout.

Concurrent payment-gateway changes appeared in `services/billing/database.py`, `main.py`, `routes/paystack.py`, the SQLite/access tests, and new gateway modules/tests, together with `docs/paystack-alignment-review-2026-10-11.md`. Those belong to the other agent and must be preserved. Avoid staging the entire working tree or deploying the whole Billing directory from this snapshot.

The remaining deployment helper is `deploy/commercial/finalize-review.sh`, using `finalize-review.Dockerfile`. It overlays only shared commercial code, the pricing catalogue, Admin pricing routes and Billing platform-checkout routes, then recreates Admin and Billing. Its last attempted run failed with the WSL connection timeout; it has not confirmed deployment of the final owner-proration correction. Review the shared `platform_checkout.py` boundary with the gateway agent before running it. Once runtime access is stable, run the owner-edit regression in `services/admin/tests/test_pricing_review.py`, deploy the correction, and verify pricing, tenant editing, VAT settings and checkout in the browser. Restore the watcher after coordinated deployment.

## Sources

Provider behavior checked against [Paystack transaction API](https://paystack.com/docs/api/transaction/), [subscription API](https://paystack.com/docs/api/subscription/) and [subscriptions guide](https://paystack.com/docs/payments/subscriptions/). Invoice fields checked against the [SARS tax invoice checklist](https://www.sars.gov.za/wp-content/uploads/Docs/Government/Tax-Invoice-Checklist-Version-2-29032016.pdf).
