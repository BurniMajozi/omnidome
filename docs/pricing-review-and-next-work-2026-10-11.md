# Pricing review and supplier cost reconciliation

## Stripe and Autumn

**Stripe is not required.** OminiDome's payment path remains Paystack. No Stripe credentials or paid Autumn attach calls were configured. Autumn's source contains Stripe-related functionality, but the proposed adapter only mirrors usage entitlements.

The other agent's concern about fit is supported by our local tests: the additional Autumn stack repeatedly made the 8 GB WSL environment unresponsive. Keep Postgres as the source of truth for tenant policies, allowances, operations and costs. Autumn is now an optional mirror, disabled by default with `AUTUMN_SYNC_ENABLED=false`. Provisioning and audited allowance overrides work locally without queuing a remote synchronization job. A disabled mirror worker exits without contacting the database or provider. Existing outbox records are retained as history. The stopped Autumn containers and data are retained for an optional future evaluation, not required for platform billing.

The public comparison no longer advertises Stripe as a supported gateway.

## Visible web bundles

The default pricing view previously showed only Professional and Enterprise. Starter and Growth were hidden under a separate audience view. Prices initially rendered as `R--`, and the Enterprise panel list was truncated to six entries.

The main view now shows all four bundles directly from the shared catalogue, renders prices immediately, includes every enabled panel, and offers a clear modular-plan alternative. It shows included seats, extra-seat price, monthly AI allowance, VAT exclusion and the annual cash total.

| Bundle | Monthly net price | Annual monthly equivalent | Annual net payment | Included seats |
|---|---:|---:|---:|---:|
| Starter | Free | Free | R0 | 1 |
| Growth | R999 | R799.20 | R9,590.40 | 3 |
| Professional | R3,500 | R2,800 | R33,600 | 6 |
| Enterprise | R9,500 | R7,600 | R91,200 | 8 |

These are existing catalogue prices, not a new provider price increase. VAT is calculated in the authoritative server quote at checkout. Annual values preserve cents rather than rounding a monthly equivalent to a whole rand. Modular panel prices use that same catalogue. Choosing a plan passes its bundle/modules, period and seats to the existing invoice/subscription journey through Paystack.

Phone navigation now exposes bundles, modular plans and product views. The modular builder stacks its summary below the selectors on narrow screens. An unwired contact-count input was removed because its value never reached checkout. Legacy SMTP estimates are clearly labelled as separate planning estimates, not software checkout prices or a new AgentMail offer. The detailed capability comparison remains indicative; do not treat it as enforced purchased provider capacity.

## Small deployment connection budget

A read-only diagnostic found 97 idle application connections and live requests failing because Postgres had reached its connection limit. The shared engine now supports configurable `DB_POOL_SIZE` and `DB_MAX_OVERFLOW`. Local Python images use one retained connection and one overflow connection per sync/async engine. Billing has a deployment override of two retained connections plus one overflow because startup table reflection exhausted the smaller pool; it is checked after that correction. Defaults outside the local overlay remain unchanged. An earlier post-review snapshot showed 19 idle application connections. This is an observed development snapshot, not a production load test. Other clients with their own engines and multiple worker processes need their own budget.

Shared commercial schema startup is serialized with a PostgreSQL transaction advisory lock so admin and billing can safely initialize tables/triggers together. Deployment backups and rollback scripts are retained; Autumn remains stopped. The final deployment restored services and the watchdog; billing reports healthy after its connection-budget correction.

## Continued work: supplier evidence and tenant allocations

The Platform Owner can record Deepgram, Firecrawl, Zernio and AgentMail supplier invoice evidence, then allocate its net cost across tenants. This is manual evidence entry, clearly distinguished from an automatically verified provider receipt.

- Supplier references are normalized and deduplicated. Repeating the same entry succeeds; changing the amount/currency/service period for an existing reference returns a conflict.
- Invoice amounts are stored in USD or ZAR, with an explicit service period. No inferred FX conversion or invented zero cost is applied.
- Allocation rows preserve a native capacity unit, quantity, amount, tenant and allocation basis. The invoice row is locked so concurrent tenants cannot overallocate a shared bill.
- Retry IDs are idempotent; mismatched retries fail. Supplier evidence and cost events remain immutable.
- Voiding an allocation appends an audited record, makes the amount available for reassignment and excludes the allocation from current cost totals. Original evidence remains intact. This is not a customer refund.
- Only Platform Owner access is allowed. Organisation Admins cannot view supplier invoices, allocate expenses or change procurement costs.
- The tenant usage screen now includes supplier invoice entry, allocation and correction controls. Cost summaries use entry posting time for their 30-day window; supplier service periods are stored separately. An incorrect master invoice requires reviewed replacement evidence with a distinct correction reference; this version does not rewrite master receipts.

No payment, customer invoice, entitlement or Finance journal is posted by this evidence workflow. Actual contribution margin remains unavailable until supplier evidence, allocations, FX, hosting, support and revenue periods reconcile.

API: `GET/POST /provider-costs/receipts`; `GET/POST /tenants/{tenant}/usage/cost-allocations`; `POST /tenants/{tenant}/usage/cost-allocations/{allocation}/void`.

## Verification

The review and supplier-evidence deployments passed the production web build and restored services and the watchdog. Pricing/provisioning/permission tests passed 31; optional mirror and connection-budget checks passed 5. Supplier allocation tests passed, including concurrent overallocation and correction. A subsequent supplier/commercial check passed 7. TypeScript checks passed. Public browser checks confirmed all four bundles, annual totals, and bundle/modular layouts at 375 px without horizontal overflow. The phone header now fits without overlapping its theme control.

The deployed supplier receipt and tenant allocation read endpoints returned HTTP 200 with no live evidence entered. Usage and cost reads returned HTTP 200, with charges disabled and actual margin unavailable. Live RAG retrieval returned HTTP 200 with five citations and nonempty context. The current browser account can read tenant usage but does not expose Platform Owner controls, so authenticated visual verification of supplier entry/allocation forms remains pending; their authorization and transaction paths are covered by tests.

Browser checkout verified Growth, annual billing, three seats and CRM/Sales panels carried through. It exposed a pre-existing server quote rounding to whole rand. That was corrected to cents, with regression coverage for annual Growth and modular CRM totals and gateway amounts. The affected pricing/provisioning suite then passed 28 tests. New Growth annual quotes are R9,590.40 net plus R1,438.56 VAT, R11,028.96 payable. Existing stored invoices are not rewritten. The final cents production build passed and browser checkout displayed R799.20 monthly equivalent and R11,028.96 annually payable. No customer invoice was created or payment submitted during browser verification. Pricing remains available in the retained browser tab with the temporary phone viewport reset.

## Remaining commercial boundaries

Provider draft prices and packs are still excluded from checkout. Managed-capacity purchasing, provider-specific reservations/top-ups, automatic provider-native receipt collection and enforcement remain separate work. Real supplier invoices and measured operating costs are needed before certifying margins. AI metering stays in shadow mode; no new overage charges are enabled. Optional Autumn validation is no longer a prerequisite for those native Postgres workflows.

See [provider pricing and profit floors](marketing-provider-pricing-2026-10-11.md). The website-builder and inventory backlogs are separate from this pricing review.

Delivery is local: changes are committed to this checkout and deployed to WSL. No remote push is included in this review. `.codex/` remains untracked.
