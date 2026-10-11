# Paystack payment gateway (OmniDome as merchant of record)

Tenants collect from their own customers through Paystack **subaccounts** under the OmniDome account. OmniDome
keeps a commission, and the rest settles straight to the tenant's bank. Code: `services/billing/gateway.py`
(tier maths), `routes/gateway.py`, `routes/payment_methods.py`, `routes/refunds.py`, `routes/disputes.py`.

## Commission

Marginal bands on the tenant's processed volume in the calendar month (SAST): 6.0% on the first R250,000,
5.5% on the next R750,000 (to R1,000,000), 5.0% above. All-in: Paystack's fee is paid out of the commission
(`bearer: "account"`). Sent per charge as `transaction_charge` (cents that stay with OmniDome) with `subaccount`.
A per-tenant negotiated tier override can be stored in `billing_gateway_settings.commission_tiers`.
Only *succeeded* charges count toward the month's volume. The commission is kept on refunds and on lost disputes.

## Flows

| Flow | What happens |
|---|---|
| Customer pays an invoice | `POST /payments/paystack/initialize` (or the public pay link) with the tenant subaccount + commission; `charge.success` applies the payment, marks the ledger row succeeded with Paystack's real fee, posts `billing.payment` and `billing.gateway_fee` (Dr 6950 / Cr 1010). |
| Card on file | Saved only if the customer ticked "save this card" (`save_payment_method`) and Paystack says the card is reusable. Token never returned by the API. |
| Recurring billing | Our invoices are charged against the saved card with `POST /transaction/charge_authorization` + the split (`/payments/charge-saved`, `/payments/autopay/run`, optional worker). Paystack Plans/Subscriptions are **not** used: they cannot carry a subaccount or commission. |
| Refund | From an open customer credit (credit note on a paid invoice, overpayment, unallocated payment). Paystack `POST /refund` against the original charge, or a manual (EFT) record. `refund.*` webhooks finish it; posts `billing.refund` (Dr 1100 / Cr 1010). |
| Dispute | `charge.dispute.*` recorded, matched to tenant + invoice, ops alerted, dunning + autopay frozen. Evidence pack assembled from our records; accept / decline from the Disputes tab. Lost -> `billing.chargeback` (Dr 6960 / Cr 1010) + liability. |

## Tenant liability

Refunds and lost disputes are paid from OmniDome's Paystack balance for money the tenant was already settled.
They are recorded in `billing_gateway_liabilities` (open until recovered). Recovery by netting against future
pre-funding / top-ups is built with the payroll + top-up work, not yet automatic.

## Safety controls

- `GATEWAY_REQUIRE_SUBACCOUNT` (default **on**): a tenant-customer charge is refused (409) until the tenant has an active gateway.
- Settlement-account changes after first setup create a second subaccount and stay *pending*; a **different** platform admin approves or rejects (`/gateway/changes/...`). Every setup / request / approval is audited in `billing_gateway_change_events`. Optional ops email: `GATEWAY_ALERT_EMAIL`.
- Only the last 4 digits of the bank account are stored; the full number goes to Paystack once.
- Webhooks are signature-verified and deduplicated; the public pay path never trusts client amounts or email.

## Environment

| Variable | Default | Purpose |
|---|---|---|
| `GATEWAY_REQUIRE_SUBACCOUNT` | true | Refuse customer charges without a tenant gateway |
| `GATEWAY_ALERT_EMAIL` | unset | Ops email for settlement-change requests and disputes |
| `AUTOPAY_WORKER_ENABLED` | false | Run the autopay scheduler in the billing service |
| `AUTOPAY_INTERVAL_SECONDS` | 3600 | Scheduler pass interval |
| `AUTOPAY_MAX_ATTEMPTS` | 3 | Failed attempts per invoice before dunning takes over |
| `AUTOPAY_RETRY_HOURS` | 48 | Gap between retries |
| `PAYSTACK_NATIVE_SUBSCRIPTIONS_ENABLED` | false | Re-enable the retired `/payments/paystack/plans/.../sync` and `/subscriptions` creators |

## Not built yet

Settlement reconciliation + balance ledger, dispute evidence file upload, VAT on the gateway fee, automatic
liability recovery, payroll / supplier pre-funding with bulk transfers, prepaid credits + top-ups (Autumn).
