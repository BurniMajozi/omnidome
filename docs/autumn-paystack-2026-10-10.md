# Autumn with Paystack in OminiDome

Yes, they can work together through a custom integration. Autumn does not document a native Paystack payment connector. Its paid checkout and subscription lifecycle use Stripe. Self-hosting Autumn does not change that limitation.

Your selected direction is to **keep Paystack**, use Autumn for **usage limits, credits and entitlements**, and **self-host Autumn locally**. This is a viable architecture; it is not a ready-made payment integration and is not running yet.

## Responsibilities

| Responsibility | System |
|---|---|
| Bundle/module prices, admin overrides, tenant membership and roles | OminiDome |
| Checkout, charges and recurring payment collection | Paystack |
| Frozen invoices, verified payment records and subscription history | OminiDome Billing |
| Consumable credits, feature balances and usage checks | Autumn |
| Tenant panel permission ceiling and Platform Owner permissions | OminiDome |

An Autumn allowance must never grant a panel that the tenant does not have, or promote someone to Platform Owner. Organisation Owner/Admin and ordinary users remain scoped to their organisation. Usage is pooled under the tenant's Autumn customer ID unless a particular feature explicitly requires per-user balances.

## How it would work

1. A customer selects a bundle or individual modules. The platform calculates and freezes an invoice using its canonical catalogue.
2. Paystack collects the payment. OminiDome verifies the signed webhook and/or server-side transaction result, including reference, amount, currency and commercial revision.
3. In the same local transaction that accepts the payment, Billing records a durable entitlement-sync job. A worker subsequently creates the corresponding Autumn customer and grants the purchased allowances.
4. The app checks tenant permissions first, then Autumn's balance before performing metered work. It records actual consumption with a stable event ID to avoid double deductions on retries.
5. Verified renewals grant the next paid allowance. Cancellation, expiry, failed renewal, refunds and admin adjustments explicitly reconcile grants according to the platform's policy.

Autumn supports [plans without a price](https://docs.useautumn.com/documentation/modelling-pricing/free-plans) and [standalone balance grants](https://docs.useautumn.com/api-reference/balances/createBalance). We can use those as externally funded allowances after a Paystack payment. “No price” in Autumn describes the entitlement configuration; it does not mean the OminiDome plan is free to the customer.

For this arrangement, grants should have an explicit paid-period expiry. An indefinitely resetting free Autumn plan could continue granting credits after Paystack payments stop. The synchronization worker must also distinguish a deliberate Platform Owner override from an unpaid tenant purchase.

## What we cannot reuse unchanged

Autumn's paid `billing.attach`, Stripe checkout, Stripe billing portal, automatic Stripe proration and Stripe overage collection cannot simply be pointed at Paystack. The official [attach API](https://docs.useautumn.com/api-reference/billing/attach) exposes Stripe checkout behavior, and the project's [README](https://github.com/useautumn/autumn/blob/dev/README.md) describes Autumn as a layer between the app and Stripe.

For Paystack, OminiDome must own renewal synchronization, payment failures, proration, cancellation and refund policy. Credit exhaustion can block further usage or offer a Paystack top-up. It must not silently invoke Autumn's Stripe auto-charge flow.

## Reliability requirements for the bridge

- A provider timeout must not undo a recorded successful payment. Durable jobs retry synchronization and surface unresolved failures to Platform Owner.
- Duplicate payment events must not grant credits twice. Use a deterministic grant identity derived from the verified order/payment and feature, and reconcile the existing grant after ambiguous timeouts.
- Old invoices and cancelled subscription renewals marked `payment_review` must not grant allowances automatically.
- Autumn cannot bypass OminiDome's tenant access checks. An unavailable quota service must not grant new permissions; metered operations need an explicit availability policy.
- Credit quantities, reset periods, expiry and rollover must be defined in the catalogue. The existing panel prices do not specify these quantities, so they must not be invented during integration.
- Tests must exercise payment-to-grant retries, duplicate deliveries, stale commercial revisions, cancellation/expiry and tenant isolation against an actual local Autumn instance before activation.

## Self-hosting assessment

Reviewed upstream revision: `89b5b6dc2653a19b758815d09b109061c70ecc40` on 2026-10-10. Autumn currently ships a [runtime Dockerfile](https://github.com/useautumn/autumn/blob/89b5b6dc2653a19b758815d09b109061c70ecc40/docker/Dockerfile) using Bun 1.4.2 and a [development services compose file](https://github.com/useautumn/autumn/blob/89b5b6dc2653a19b758815d09b109061c70ecc40/docker/dev-services.compose.yml). Its local infrastructure includes PostgreSQL, Dragonfly caches, Kafka, DynamoDB and SQS emulators. Server, workers and scheduled processes have separate commands. This is a substantial service stack, rather than a single extra billing container.

It should use isolated databases, volumes, ports and secrets alongside OminiDome. The upstream development defaults must not replace the platform's existing database or credentials. Pin the source revision and validate migrations, workers and balance operations before wiring production grants. No Stripe connection is needed for the proposed *payment collection* path; the complete Stripe-free Autumn runtime still needs validation.

## Current status

The tenant pricing, role labels, panel inheritance and Paystack provisioning changes are implemented, tested, committed locally as `e88ef806`, and deployed locally. The final read-only checks returned 200 for pricing, checkout, tenant modules and RAG; the annual Professional quote was R38,640 including configured VAT. See [tenant pricing handoff](tenant-pricing-2026-10-10.md) for all tests and limitations.

This Autumn assessment establishes the integration boundary. **The Autumn service, payment-to-entitlement bridge and usage enforcement are not implemented or activated yet.** No new payment was initiated and no Stripe or Autumn billing account was connected. The existing Paystack journey remains the working payment path.
