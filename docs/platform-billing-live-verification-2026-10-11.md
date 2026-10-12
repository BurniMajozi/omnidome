# Platform billing: live verification, 11 October 2026

The recent tenant platform billing work is already running locally at `http://localhost:3000/platform-billing`, also available through **Admin → Platform Billing & Usage**. No further image activation was needed in this turn: the running backend and frontend files exactly match the reviewed Windows source.

## Why the earlier answer said it was not deployed

The previous attempt was blocked by WSL connection failures. The user reported another agent working on the shared platform, so WSL and shared services were not restarted. That handoff was accurate at the time it was written but stale by this request. Fresh live checks found the work present. The earlier answer should have checked runtime state before repeating the pending-deployment claim. It is not established which concurrent process deployed it.

## What is live

- Current plan, selected panels, subscription status and the existing plan-change checkout.
- Included allocation, measured usage, prepaid balance and available credits after reservations.
- Usage by panel, filtered/paginated activity logs and platform invoice history.
- Supplier/customer invoice details and Paystack top-up checkout for a user-selected amount from R50, conditional on publishing the credit price.
- Voice/Deepgram and AgentMail preferences for prepaid stopping or automatic recharge, visibly marked pending integration.

Autumn remains optional; Paystack remains the payment gateway. No Stripe payment setup is required by this wallet flow.

## Activation still needed

The live credit policy is `enabled=false`, `minimum_zar=50.00`, `price_per_credit_zar=null`. A Platform Owner must publish the selling price per credit in the billing view before tenants can buy credits. No selling rate was invented or published during deployment verification. Saving voice/email preferences neither authorizes nor charges a card: provider-specific metering, cut-off and platform card authorization/automatic recharge still need implementation.

## Evidence

At approximately 19:10–19:20 SAST, signed read-only checks succeeded for `/pricing/credits` and the tenant's `usage`, `usage/logs`, `pricing/orders` and `usage/delivery-controls` endpoints. The four tenant endpoints were checked both as Platform Admin and as an existing active tenant owner. `/platform-billing` returned HTTP 200.

SHA-256 hashes matched source for running Admin `commercial.py`, Billing `platform_checkout.py`, shared `platform_credits.py`, agent `commercial_usage.py`, and Web `platform-billing.tsx`, `admin-module.tsx`, `admin-api.ts`, `platform-pricing.ts` and the platform-billing route. This verifies the actual container filesystem rather than relying on an image name or prior handoff.

All 25 tests in the combined PostgreSQL wallet, pricing-review and tenant-pricing suite passed against the dedicated `omnidome_pricing_test` database in 92.62 seconds, with four existing FastAPI lifecycle deprecation warnings. These include all six wallet tests: tenant/role isolation, tampered amounts, duplicate verified grants, preservation of the current plan, concurrent reservations, failed-work release, purchased-credit consumption and explicitly pending delivery preferences. The first run found a test-fixture error: policy publication used a nonexistent tenant, which cannot receive an audit record. The fixture now uses a real test tenant; no production authorization or audit constraint was weakened.

Live hybrid memory/RAG recall succeeded and returned three knowledge hits after an initial timeout. The existing deployment watcher is active. No shared service restart, production credit-policy change, production balance adjustment or real Paystack charge was made in this turn.

Browser automation was rejected by the browser security policy, so visual verification of the authenticated owner screen remains outstanding. No workaround or alternate browser surface was attempted after that rejection. Prior source TypeScript and production build checks passed; those are not a substitute for visual confirmation.

## Deployment helpers

`deploy/commercial/deploy-platform-billing.sh` prepares staged images, protects against another image deployment during the build, keeps timestamped rollback images and activates only Admin, Billing, agent commercial telemetry and Web. It preserves the current orchestrator implementation; it does not deploy the new workflow engine. It restores an active watcher after activation or rollback. This helper was prepared but not executed because the reviewed code was already live.

`deploy/commercial/check-platform-billing.py` performs signed API and memory checks without printing credentials or initiating payments. The test image/helper target only the explicitly named `_test` database. The separate workflow changes remain uncommitted and not newly deployed by this verification.
