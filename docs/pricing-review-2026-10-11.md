# Review of the tenant pricing / bundle / metering work (11 Oct 2026)

Read-only review by Claude of the pricing work (commit `e88ef806` and later). Method: code reading plus running the real quote engine in Python. DB-backed tests, Paystack and the UI were not run.

## Verdict

- The tenant-chosen model is implemented end to end: a tenant picks a **bundle** (Starter, Growth, Professional, Enterprise) or **modular panels with tiers**, plus **seats**. The server computes the quote, freezes it in `platform_orders`, and Paystack charges the stored amount. Nothing is activated until the payment is verified server-side (reference, amount, currency, status).
- Metering is in shadow mode and never charges. Autumn is optional.
- Not ready for a public rollout until findings 1 to 7 are fixed.

## Findings (most severe first)

High
1. Failed or lapsed payment never suspends access. `billing_status` is written but no guard reads it; `platform_checkout.py:156-158` only sets `past_due`. Grace and suspension are documented, not implemented.
2. Module tier is cosmetic: it only changes the price and the AI credit allowance, and the allowance uses the highest tier chosen. One Enterprise panel at R1,499 gets the credits of the R9,500 Enterprise bundle.
3. The catalogue has 14 panels; the sidebar has 19 sections. Missing: BI Studio (`analytics`), Inventory, IoT, RICA. `overview` and `admin` are always on and free. Paying for a bundle disables the unlisted panels (`platform_commerce.py:83-87`).
4. Manual panel grants are lost when the Platform Owner re-saves pricing (`services/admin/pricing.py:66`, `manual_panels` not carried forward).
5. Module key mismatch: `portal-builder` is guarded in `services/portal_builder/main.py:56` but the catalogue key is `portal`, and no `portal-builder` row is seeded. A paying portal tenant would get a 403.
6. Price inversions: Growth (R999, 3 seats) costs more than the same modules bought modularly (R638). Professional (R3,500) is dominated by starter-tier modules at R1,494, because tiers gate nothing.
7. No proration; downgrades apply immediately and free; a pending recurring plan must be cancelled by hand.

Medium
8. Invoices are not VAT compliant: reference is `ODP-<uuid>`, no supplier or customer VAT number, and immutability of `quote` is by convention only.
9. UI and backend disagree on bundle plus add-on modules: `tenant-pricing.tsx` always sets `bundle: null` when a panel is added.
10. Inconsistent seat copy: R45 per extra seat in code, R45 or R75 on the pricing page, and 10 seats vs 6 included on Professional. The price is not strictly per user.
11. Idempotent replay can return 500 (`quote()` outside the try in `create_order`).
12. Cached checkout URL is reused forever, so an expired Paystack session is never re-initialised.
13. Usage operations can stay `running` forever after a crash; there is no sweeper.

Low
14. The public page uses floating-point for the discounted display price (fragile if prices ever have cents).
15. No seat cap: 100,000 seats yields a valid R5.18m online quote.

## Scenario table (real quote engine, VAT 15%)

| Scenario | Net | VAT | Total |
|---|---|---|---|
| Professional monthly, 10 seats | 3,680.00 | 552.00 | 4,232.00 |
| Professional annual, 6 seats | 33,600.00 | 5,040.00 | 38,640.00 |
| Professional annual, 10 seats | 35,328.00 | 5,299.20 | 40,627.20 |
| Growth monthly, 3 seats | 999.00 | 149.85 | 1,148.85 |
| Enterprise monthly, 8 seats | 9,500.00 | 1,425.00 | 10,925.00 |
| Enterprise annual | 91,200.00 | 13,680.00 | 104,880.00 |
| CRM + Sales starter, 3 seats (modular) | 638.00 | 95.70 | 733.70 |
| Professional's 6 panels at pro tier, modular | 4,719.00 | 707.85 | 5,426.85 |
| Professional bundle + Network (starter) via API | 3,999.00 | 599.85 | 4,598.85 |

The 20% annual discount is applied per line before x12, so VAT is on the discounted net. Rounding is half-up on Decimal. Zero or negative seats, unknown modules and tampered prices are rejected (`extra="forbid"`).

## What looks good

Server-side frozen quotes; verification of status, currency, amount and reference; stale revisions and seat-limit conflicts go to `payment_review`; signed admin-to-billing calls; webhook idempotency; shadow-mode metering that never breaks a request; Autumn is optional with no Stripe path; escaped invoice HTML with a strict CSP.
