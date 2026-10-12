# Tenant platform billing and usage

Built in the shared Windows checkout on 11 October 2026. Changes are not yet confirmed deployed.

Tenant owners and Organisation Admins now have **Admin → Platform Billing & Usage**, plus `/platform-billing` for direct access and payment returns. Platform Owners can select an organisation. The view shows the active plan, seats, panels, service-period end, recurring status, included credit allocation, usage, prepaid remaining balance, running reservations, panel totals, monthly write limits, paginated operation logs and paginated platform invoices. Tenant-customer ISP invoices and provider costs are separate.

## Top-ups

The tenant chooses a gross payment from **R50 to R100,000**, in cents. A Platform Owner publishes the rand price per AI credit and operation reservation limit. No selling price is invented or enabled automatically: the current meter used draft rates, and the user's R50 instruction sets the purchase minimum rather than a rand-to-credit exchange rate.

Invoice review discloses the exact whole-credit quantity, total and current supplier VAT treatment. Fractional credits round down. The existing sequential, frozen platform invoice is used with `intent=credit_topup`. Supplier remains unregistered for VAT until explicitly configured. Purchased credits do not expire or change panel access, write limits, plan-change money credit or subscription recurrence.

Paystack checkout uses a one-off transaction without an ISP subaccount split or new subscription. Credits are delivered only after verified success, matching amount, currency and reference. The append-only credit ledger has a unique order grant; callback/webhook duplicates cannot deliver a second grant. Top-up verification skips plan provisioning and cancellation of existing recurrence. This follows [Paystack's digital-value verification guidance](https://paystack.com/docs/payments/verify-payments/).

Publishing the credit policy activates accounting for instrumented agent turns. Starts reserve available included plus purchased credits under a tenant row lock; insufficient balance returns 402 before work. Successful completion uses included allowance first and deducts purchased credits afterward, in the same transaction as the operation outcome. Failed/cancelled work releases its reservation. Completion is idempotent. A customer's final charge is capped by the operation reservation; this is a customer credit-charge cap, not a hard supplier-runtime or token limit. Reservations can temporarily limit concurrent work. Abandoned reservations are released by the existing two-hour cleanup. Historical shadow measurements remain visible; the selected allowance and current-period usage remain the allowance basis when publishing.

`PLATFORM_USAGE_ENABLED=true` is required on agent-orchestrator (already specified by `deploy/commercial/shadow.yml`). Unmetered third-party/provider paths are not automatically covered. Unknown completion outcomes, process interruptions, changes of plan while work is running and refund/dispute reversals still need reconciliation rather than an automatic replay or cash refund. Do not publish paid rates until the PostgreSQL integration tests and live metering checks pass.

## Voice and email choices

The view records tenant preferences for Call Centre/Deepgram and AgentMail email: prepaid capacity with stop at limit, or automatic card recharge, including recharge amount and monthly cap. Both options are visibly labelled **pending integration**. The API returns `prepaid_enforced=false` and `auto_recharge_active=false`. Saving preferences does not authorize card charges. Native minute/send metering, provider admission/cut-off, platform-owner reusable card authorization, consent, idempotent automatic recharge and provider capacity rates are not connected by this change. The other agent's saved cards serve tenant-customer ISP billing and must not be reused as a tenant owner's platform payment authorization.

## Current live status — later verification on 11 October

The billing UI and backend are now confirmed live: running source hashes match this checkout, the platform-billing page returns HTTP 200, and signed usage, logs, invoices and preferences APIs work for both Platform Admin and an existing tenant owner. Six PostgreSQL wallet tests passed. The credit price is still unpublished, so purchases remain disabled. See `docs/platform-billing-live-verification-2026-10-11.md` for evidence and the outstanding provider/visual checks. The watcher is active. The earlier blocked rollout notes below describe the previous attempt, not the current runtime state.

## Validation and earlier rollout

- Final source TypeScript check passed, including invoice history. The normal full check reported two stale generated `.next/dev` references to a removed `deck-harness` page; a temporary configuration excluded only that generated directory and was removed afterwards.
- Final production Next.js build passed and includes `/platform-billing`. The repository's build configuration skips type validation, so the separate TypeScript check above matters.
- 54 unit tests passed for credit quote/VAT rounding, amount boundaries, unpublished rates, invalid provider settlements, pricing, proration, shadow metering and agent telemetry, including fail-closed admission checks.
- Six PostgreSQL regressions cover tenant/role isolation, amount tampering, idempotent verified grants, preservation of the current plan, concurrent reservations, failed-work release, purchased-credit consumption, invoice documents and pending delivery controls. The module is skipped without a dedicated `TEST_DATABASE_URL`; it has not run successfully against PostgreSQL in this turn.
- WSL rejected the read-only RAG attempt with `Wsl/Service/CreateInstance/E_ABORT`; PostgreSQL localhost:5432 was unavailable. RAG was attempted but no retrieved context is claimed. WSL was not restarted because the user reports another agent working on the platform.
- Browser verification and live deployment remain pending. No real Paystack charge was made.

The narrow `deploy/commercial/finalize-review.sh` overlay now includes Admin commercial routes, Billing platform checkout, shared credits code and agent commercial telemetry, recreating Admin, Billing and agent-orchestrator. It still requires coordination with the other agent and a separate reviewed frontend sync/web rebuild. It has not been run successfully for this wallet change. The existing deployment watcher remains paused from the earlier runtime diagnosis; coordinate restoring it after deployment.

Main implementation: `services/common/platform_credits.py`, `services/admin/commercial.py`, `services/admin/pricing.py`, `services/common/platform_usage.py`, `services/billing/routes/platform_checkout.py`, `services/agent_orchestrator/commercial_usage.py`, and `apps/web/components/pricing/platform-billing.tsx`. The previous pricing-review handoff remains in `docs/pricing-review-rectification-2026-10-11.md`.
