# OmniDome Free plan and pricing comparison — 11 October 2026

The scope is OmniDome's own pricing, signup trial and demo journey. This change does not add trials or public appointment products for tenants to sell to their customers.

## Free software access

The commercial catalogue now labels the zero-price bundle **Free** and includes CRM, Services, Portal, Retention, Product and Stock. Overview and Admin remain always available and free. The existing internal bundle ID `starter` is retained for link compatibility; its panel tiers are now explicitly `free` rather than paid Starter tiers.

- One included user seat; additional seats retain the existing R45 monthly price.
- 100 successful writes per Free panel per UTC month.
- 50 shared AI credits per month, not 50 for each of the six panels. No allowance increase was introduced by adding panels.
- Existing concrete feature gates remain: for example Portal campaigns/SEO and inventory reports require Professional, and inventory approvals require Enterprise.
- Provider email, voice, research and social capacity remain separate. This change does not enable automatic card recharge or publish a credit-selling rate.

Current enforcement distinction: panel write budgets are enforced. The 50 AI credits are the configured allowance, but the live global credit policy remains disabled, so reservation-based AI credit deductions and credit exhaustion stops are not active yet. Publishing credit pricing/enforcement is separate work; this expansion must not be described as having activated a hard provider-cost cap.

Paid bundles also retain these basic Free panels where they do not include a paid version of the panel. A paid bundle's included modules retain their paid tier and allowance. For example Growth remains R599 with 500 shared credits: CRM and Sales are Starter; Product and Stock remain Free with 100 writes each. Paid bundle prices have not changed.

Both the public modular selector and Admin pricing selector now offer Free only for the six eligible panels. Selecting a paid tier charges that panel's existing price. Platform Owner checkbox changes preserve deliberate removals rather than automatically adding a removed Free panel back during repricing. Quote calculations reject Free access for unrelated paid panels, such as Billing or Network.

Provisioning writes actual `pricing_tier=free` and write budgets into module configuration. Member access inherits the organisation's enabled panels. This is software access; it does not claim that every unfinished feature or demo screen in those panels has been completed.

Existing activated quotes and invoices are retained. Deploying a new catalogue does not silently replace every live organisation's agreement. Existing organisations can select the new Free bundle explicitly; automatic trial expiry will need a dedicated transition that also handles excess trial seats without deleting accounts.

## Trial and demo scope

The trial design now ends on the permanent Free bundle instead of leaving only Overview/Admin available. Data and purchased credits are retained, while trial-only paid features expire. Trial expiry automation and public demo booking are still design work; they are not implemented by this catalogue change. See [the corrected design](trials-and-scheduling-review-2026-10-11.md).

Demo booking is for OmniDome's sales team only. Tenant-branded booking, customer trials and technician dispatch have been removed from the proposed scope.

## Comparison on the public pricing page

The bundle pricing view now includes a responsive “Compare prices with other tools” section with official source links. Prices remain in their original currencies and identify the billing period. The comparison does not claim equal features or guaranteed savings.

| Tool | Free access | Paid reference price | Basis and limitations |
| --- | --- | --- | --- |
| OmniDome | R0 software fee, one seat and the six Free panels | Growth R599/month, three seats | Free limits above; provider capacity, higher tiers and additional seats separate. Tax is shown using live settings at checkout. |
| HubSpot | Free CRM and selected basic tools | Smart CRM Starter from US$20/seat/month; Marketing Professional from US$890/month with three Core Seats | Marketing contacts and onboarding can add costs. [Official catalogue](https://legal.hubspot.com/hubspot-product-and-services-catalog) |
| Zoho Inventory | 50 orders, one user, one location | Standard US$29/organisation/month, billed annually | Inventory product; additional users, orders and locations cost extra; local taxes excluded. [Official pricing](https://www.zoho.com/us/inventory/pricing/) |
| Shopify | Promotional trial, rather than a permanent free Basic plan | Basic US$39/month or US$29/month billed annually | Ecommerce storefront; payment fees and apps may add costs. [Official pricing](https://www.shopify.com/pricing) |

Supplier prices were checked on 11 October 2026 and should be reviewed before using them in a purchase decision. Promotions and local-currency offers can differ from these list prices. No unverified exchange rate or percentage-saving claim is displayed.

## Verification

- 31 quote, usage and proration tests passed.
- 12 PostgreSQL tenant pricing tests passed, including six-panel Free provisioning and inheritance.
- The expanded PostgreSQL check also removes and re-enables Stock through Platform Owner checkboxes, preserving R0 and the shared 50-credit allowance. It caught and verified a fix for an empty-line, VAT-inclusive zero-price calculation.
- Source TypeScript check passed. The ordinary check still reports the two existing missing `deck-harness` references in generated `.next/dev` files; the source check excluded only that generated dev directory.
- Deployed locally and checked live at 21:36 SAST. The public quote returns R0, six explicit Free panel tiers, a 50-credit shared allowance and 100 writes per panel. The production pricing-page response contains the comparison section and all three supplier names.
- Admin, Billing and the orchestrator are healthy; Web is running and serves the pricing page. The service watcher is active. Rollback image suffix: `before-20261011192905`.
- The live catalogue confirms no VAT registration and VAT-inclusive display preference. Those existing live settings were not changed.
- No production balance, paid contract, supplier tax setting or provider-selling rate was changed during test execution. Browser interaction remains unverified.

The first staging attempt encountered a WSL connection timeout and was stopped before confirmed activation. The corrected retry completed its build, activation and API checks. Its PowerShell stdin wrapper emitted a trailing-carriage-return shell error after the success message; independent live checks confirmed successful activation and watcher restoration. Future invocations should run the saved shell script directly in WSL rather than pipe PowerShell text into `bash -s`.
