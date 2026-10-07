# Portal and inventory continuation — 7 October 2026

## Implemented

- Public `/portal/<slug>` pages and `/portal/shared/<token>` draft previews render sanitized Portal Builder blocks. Published pages include a consent-required enquiry form; previews do not accept submissions. Tracking fields are bounded to backend limits. Unknown/unpublished pages and expired/revoked previews have explicit unavailable states.
- Portal Management has a Campaigns & records tab: create/list campaigns, track budgets and recorded spend, launch/complete their lifecycle, create/list SEO profiles, inspect page versions and paginate submissions. Backend role denials remain visible. Campaign creation cannot attach another tenant's page, and budgets reject negative/non-finite values.
- Field Sales calls the existing CRM, Billing and Inventory proxies rather than missing `/api` routes, handles paginated customer lists, and preserves API failures. Commission amounts are normalized from API decimal strings. No fabricated fallback tiers are shown.
- Technician uses existing service proxies, rejects explicitly simulated speed-test results, and does not create zero measurements when a test fails. The support service computes resolution time from recorded tickets and returns unavailable for ratings and revenue without a real source.
- Web Analytics and Journey proxies preserve backend HTTP errors. Journey context resolves the verified tenant through the proxy rather than a hardcoded development tenant. Unavailable data is shown as a request failure, with retry controls.
- Retention review selects an actual CRM customer and sends the backend's correct trigger/respond fields. It presents only returned offers, retains the real event ID, and reports a recorded decision only after successful persistence. Declining an offer does not falsely claim that service cancellation is complete. Cancellation requests and responses are tenant-scoped.
- Inventory has warehouse valuation, transit-aware reorder recommendations, order-cohort spend, catalogue margin, complete-result CSV exports, pagination and a pending approval inbox using existing signed purchasing review. See `inventory-reports-api.md` for financial definitions and limits.

## Validation

- Portal tests: **36 passed**.
- Inventory and support tests: **68 passed**, with six PostgreSQL tests excluded from that run.
- Separate disposable PostgreSQL inventory database run: **6 passed**; the test database was removed afterwards.
- Cancellation tenant scope: **2 passed**.
- Scoped TypeScript check includes Portal, Inventory, mobile apps, Commissions, Journeys, Analytics, public routes and Journey proxy: **passed**.
- Production Web builds and the final scoped TypeScript check: **passed**. Updated Web, Portal Builder and Inventory images are running locally. All originally running services were restored; the backend containers report healthy and the automatic watchdog is active.
- Live PostgreSQL report checks passed for JSON and CSV: valuation **R125.00**, reorder **11 units / R137.50**, approved-order spend **R115.00** with accepted receipts **R50.00 net / R7.50 VAT**, and prospective margin **37.5%**. CSV attachment headers, row counts and formula protection were checked through signed HTTP requests.
- Browser checks passed for the published page, consent-required submission and success message, draft shared preview without a form and with `noindex,nofollow`, and unavailable unpublished pages. Public form layouts had no horizontal overflow at **320, 768, 1024 and 1440px**.
- Campaign and SEO forms, page search, version/submission selectors, Inventory valuation/margin views and approval inbox rendered in the browser. Field Sales loaded actual database leads/deals and Commissions loaded configured tiers. No actual purchasing approval or customer retention decision was executed.
- The browser's CSV download-event capture timed out; export content and headers were verified separately against the deployed API.
- Disposable portal pages, preview, views, enquiry, inventory records, tenant and temporary module entitlement were removed. A follow-up query verified zero fixture records across all twelve scoped tables.

## Scope limits

Campaign launch updates its recorded lifecycle; it does not implement a new email delivery engine. The existing version API provides history, not version restoration. SEO profiles are created/listed because their backend has no update/delete contract. Rating, actual speed measurements and attributed technician revenue need real sources; they are shown as unavailable rather than invented. Valuation and margin use current catalogue prices, with their scope explicitly shown in the UI. Valuation excludes transit and technician holdings; spend represents the order cohort, not cash payments.

The local Support, Journey Engine and legacy Web Analytics services were already stopped and remain stopped. Support and Journey Engine images include the source changes, but their live write flows were not browser-tested. The browser verified explicit Technician service failure, Journey tenant-resolution failure and Analytics 503/retry states. Existing legacy Web Analytics aggregate queries still need tenant filtering before enabling that service for multiple tenants; the separate Portal Builder analytics are tenant-scoped.

Frontend fallback/demo results were removed or replaced with API-backed states. Existing persisted sample-looking lead and commission records were preserved; this change does not purge database seed data. Field/technician billing permissions retain the backend's existing role checks.

Local rollback tags are `pre-portal-inventory` for the initial rebuild and `pre-inventory-cleanup` for the final Web follow-up. Implementation commits are `76f79aac` and `5f5ab1c1`; the public-route work is in `e7f250d6`. The final verification report is committed separately.
