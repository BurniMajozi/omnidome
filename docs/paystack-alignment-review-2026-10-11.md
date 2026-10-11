# Paystack alignment review (11 Oct 2026)

Method: Paystack's official OpenAPI spec (PaystackOSS/openapi, 160 endpoints, 35 resource groups) compared with what the code calls today. Read-only; nothing was run against Paystack. Whether Products, Storefronts, Orders and Payment Requests are enabled on a **South African** merchant account is not stated in the spec and must be confirmed in the dashboard (your screenshot shows them in the menu, which is a good sign).

## 1. What we call today (only 14 of 160 endpoints)

| Paystack endpoint | Where | Used for |
|---|---|---|
| POST /transaction/initialize | billing/routes/paystack.py, platform_checkout.py | Pay an invoice / platform order |
| GET /transaction/verify/{ref} | same | Verify |
| POST /plan, POST /subscription, GET /subscription/{code}, POST /subscription/disable | paystack_recurring.py, platform_checkout.py | Recurring |
| POST /transferrecipient, POST /transfer | hr/paystack.py | Payroll payouts |
| Webhook: charge.success, subscription.create/disable/not_renew, invoice.payment_failed, transfer.* (log only) | paystack.py, platform_checkout.py | Events |

Everything else in the spec is unused. Not a problem by itself, but the gaps below matter.

## 2. Structural gap (most important): one Paystack account for everyone

All services read a single global `PAYSTACK_SECRET_KEY`. That is correct for **platform pricing** (OmniDome bills tenants). It is wrong for the **tenant's own customer billing** (an ISP collecting from its subscribers): today those payments land in OmniDome's Paystack account, with no record of who is owed what and no payout path to the tenant.

Paystack has a purpose-built answer, which is what your arrows point at:

- **Subaccount** (`POST /subaccount`): one per tenant (business name, settlement bank, account number, percentage_charge). Created at tenant onboarding.
- **Transaction Split** (`POST /split`, types `percentage` / `flat`, `bearer_type`): the commission rules (e.g. OmniDome keeps 1.5%, tenant gets the rest).
- On each charge pass `subaccount` / `split_code` / `transaction_charge` / `bearer` to `/transaction/initialize`, `/transaction/charge_authorization`, `/paymentrequest`, `/product`, `/page`, and `/dedicated_account`. Paystack then settles to the tenant's bank directly.

Nothing in the code references subaccounts, splits or `split_code`. This is the biggest missing capability and defines the multi-tenant money model. Decision needed: **Subaccounts (OmniDome is merchant of record, takes commission) vs. each tenant bringing their own Paystack keys** (tenant is merchant of record, no commission mechanism). Subaccounts is the one that gives you commissions.

## 3. Area by area

### Billing and collection (ISP customer invoices)
- Initialize/verify/webhook are solid (HMAC check, idempotent events, amount and currency checks, overpayment to customer credit).
- **No card authorization is stored.** `charge.success` carries `authorization.authorization_code` and `reusable`, plus `customer.customer_code`. We discard them. Consequences: no one-click renewals, no `POST /transaction/charge_authorization` for monthly ISP debits or for the seat-billing hook (`seat_runs.py:115` is OFF for exactly this reason), and `paystack_recurring.create_subscription` requires the caller to already know the `authorization_code` and `customer_code`, which nothing supplies.
- **No Paystack Customer is created** (`POST /customer`); `customer_code` is expected but never obtained. Needed for subscriptions, risk actions, dedicated accounts and Direct Debit.
- **Failed payments**: `invoice.payment_failed` is only mapped to `past_due`; `charge.success` renewals on a subscription (no invoice metadata) are ignored (`"ignored"` path), so a Paystack-driven renewal does not become a payment on our invoice.
- **No dunning retries via the API**, no `partial_debit`, no `bulkcharge` (batch monthly debits for hundreds of subscribers, which is how an ISP would actually collect).
- **Direct Debit / mandates** (`/customer/{id}/initialize-direct-debit`, `/directdebit/*`) are ZA-relevant for ISP debit orders and are not used.
- **Dedicated Virtual Accounts** (`/dedicated_account`): bank-transfer collection with a per-customer account number and reconciliation by webhook; not used. Likely valuable for ISP EFT payers (needs ZA availability check).
- **Channels**: `channels` (card, bank, eft, ussd, qr, mobile_money, apple_pay) never set; Apple Pay domain registration unused.

### Invoicing
- We run our own invoice engine (numbering, VAT, PDF, share links, credit notes). Paystack has **Payment Requests** (`/paymentrequest`: line_items, tax, due_date, invoice_number, send_notification, draft, finalize, archive, split_code). Decision: keep our invoice as the legal document (recommended: VAT numbering, credit notes, ledger posting) and, when a customer needs a payable link, create a Payment Request or a transaction from it. Do not duplicate numbering. Not used today.
- Invoices must **not** be marked paid from the browser callback; they are not (verified server-side). Good.

### Refunds and credit notes
- Paystack: `POST /refund` (transaction, amount, customer_note, merchant_note), `GET /refund`, retry with customer details, events `refund.pending/processing/processed/failed`.
- Code: credit notes on paid invoices create a `refund_required` credit row, and the action list literally says "integration pending: refund payout has no billing endpoint". `movements.py` can show a `refunded` payment status but nothing ever sets it. No refund webhook handled. So **refunds are not wired to Paystack at all**; they are bookkeeping only. Needed: refund endpoint (checks amount <= captured, one refund per row, partial refunds), `refund.*` webhook handling that flips the credit to `refunded` and posts the finance entry, UI "Refund" button. Router-return refunds (`RRF-` reference) are also fake references.
- Refunds on split transactions need the bearer decision above.

### Platform pricing and metering (OmniDome billing tenants)
- Plans: we create **one Paystack Plan per order** (`"OminiDome " + reference`). Paystack plans are meant to be reusable (e.g. one plan per bundle/interval, 20 or so, not one per order); thousands of plans will clutter the dashboard and the `invoice_limit` / `send_invoices` plan options are unused. Better model: since the amount is per tenant, keep a plan per distinct (amount, interval) or charge via `charge_authorization` on our own schedule.
- Plan changes: Paystack has **no proration**. Upgrading means update/create plan + disable old subscription (or `PUT /plan` which does not retroactively change existing subscriptions) or charge a prorated amount via `charge_authorization`. Our proration engine must therefore compute the difference itself and charge it, then swap the plan. Matches the Codex approach; just confirm it uses `charge_authorization`, not a new checkout.
- **Usage-based metering is not a Paystack feature.** Paystack has no metered billing. So "metering should follow Paystack" can only mean: usage overage is computed by us and billed as an add-on charge on the next invoice via `charge_authorization` or a Payment Request. Autumn (metering) is a separate system; it does not integrate with Paystack.
- Subscription management links (`GET /subscription/{code}/manage/link`, `POST .../manage/email`) let tenants update their card without us handling it; not used, and the code does not handle `subscription.expiring_cards`.
- `subscription.enable` is never called (only disable), so a paused tenant can't be re-enabled.

### Products, Storefronts, Orders and stock
- Paystack Commerce: `/product` (name, description, price, currency, unlimited, quantity, split_code), `/storefront` (+ publish, duplicate, products), `/order` (email, names, phone, items, shipping), `/page` (Payment Pages, incl. subscription type pages).
- We have our own catalogue (`inventory_products`, `store_products` in customer_journey with `stock_quantity`, `track_inventory`) and our own cart/checkout, orders and stock reservation. **None of it is synced to Paystack.** Options:
  1. **Our store is the source of truth; Paystack is payment only** (recommended): keep our product, order and stock tables, use `/transaction/initialize` with the order reference. No Paystack Products needed.
  2. Mirror products to Paystack Products/Storefronts so tenants who want a no-code Paystack store get one. Paystack's quantity field is a count; ours is per-warehouse levels, so a sync would flatten stock and race with reservations. Only worth it as an optional "publish to Paystack storefront" feature.
- Paystack `Order` webhooks are not in the event list; Paystack orders have no stock-reservation semantics we can rely on. Do not make Paystack the stock system.
- Checkout in `store_routes.py` takes a `payment_method_id` and sets `payment_status` but does **not** call Paystack at all (no initialize, no verification of `payment_reference`). Orders can be created without any verified payment. That is a gap to check against the intended flow.

### Payroll (HR)
- Transfer recipients + transfers work (ZAR `basa`). Missing: `finalize_transfer`/OTP handling (a live account with OTP on will stall transfers in `otp` state), `POST /transfer/bulk` for pay runs (one request instead of N), `GET /transfer/verify/{ref}` reconciliation, `transfer.*` events only logged (never update payslip status), `GET /balance` pre-check, and the test account is "starter" so payouts fail by design.

### Reconciliation, settlements, disputes
- Not present: `/settlement` + `/settlement/{id}/transactions` (match payouts to bank), `/transaction/totals`, `/balance/ledger`, `/dispute*` (chargebacks have a response deadline; `charge.dispute.create/remind/resolve` events are ignored), `/transaction/export`. For a billing product these three (settlements, disputes, ledger) are the usual first gaps. Finance has no Paystack awareness.

### Webhooks
Handled: charge.success, subscription.create/disable/not_renew, invoice.payment_failed, transfer.* (log only). Missing: `refund.*`, `charge.dispute.*`, `paymentrequest.*`, `invoice.create/update`, `subscription.enable`, `subscription.expiring_cards`, `customeridentification.*`, `dedicatedaccount.assign.*`. One shared `/payments/paystack/webhook` URL is used for the platform, tenant billing and payroll, which is fine since Paystack has a single webhook URL per account, but it means tenant-scoped events must carry tenant metadata (they do for invoices).

## 4. Recommended order of work

1. **Money model decision (blocking)**: Subaccounts + a platform split (commission), or tenant-owned keys. Then add Tenant Payment Settings (settlement bank, subaccount code, KYC status) and pass `subaccount`/`split_code` on every tenant-customer charge.
2. **Store the authorization + customer**: persist `customer_code`, `authorization_code` (reusable only), card brand/last4/exp, on `charge.success`; create Paystack Customers. Unlocks renewals, `charge_authorization`, seat billing, proration.
3. **Refunds end to end** (endpoint, webhook, UI, ledger).
4. **Handle renewal `charge.success` and failed renewals** properly (match by subscription/plan/customer; dunning ladder).
5. **Reconciliation**: settlements + balance ledger + disputes screens and webhooks.
6. Payroll: bulk transfer, OTP finalize, transfer status webhooks, balance check.
7. ISP collection extras: Direct Debit mandates, Dedicated Virtual Accounts, bulk charge for monthly runs.
8. Commerce: keep our store as source of truth; add the missing Paystack initialize/verify to store checkout; optional Paystack Storefront publish later.
9. Plan hygiene: reusable plans instead of plan-per-order.

## 5. What is already aligned
HMAC-SHA512 webhook verification, event idempotency, amounts in cents with half-up rounding, ZAR-only enforcement, server-side verify before marking paid, callback host allow-list, unique references, overpayment handling, subscription disable with email token, payroll recipient/transfer with graceful failure.
