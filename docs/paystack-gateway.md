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

## Funded payouts (payroll and supplier payments)

Paystack transfers are paid from OmniDome's own balance, so a tenant can only pay out money it has already given us.
`services/billing/routes/payouts.py` owns a per-tenant **payout wallet** (`billing_payout_wallets`, append-only entries):

- **Funding**: a card checkout (`POST /payouts/funding/initialize`, no subaccount, credited by the `charge.success` webhook for
  exactly the initialised amount) or an EFT recorded by a platform admin (`POST /payouts/funding/manual`, idempotent per bank
  reference). Card funding costs OmniDome about 3% in processing, so large payrolls should be funded by EFT.
- **Fee**: the same marginal tiers as card collections, on the tenant's month-to-date volume (card charges + payouts).
- **Pay**: HR (`POST /payroll/runs/{id}/pay`) and inventory (`POST /purchase-orders/{id}/payments`) call billing's internal
  endpoints with the service key. Billing reserves amount + fee from the wallet (402 with the shortfall if it cannot) and sends
  Paystack `POST /transfer/bulk` (100 per request). An item that fails, or a transfer that is reversed, credits its amount and fee
  back exactly once. An outcome that cannot be known (gateway error) stays *pending* and is resolved by reconcile
  (`GET /transfer/verify/{reference}`); a transfer Paystack never created is failed and returned to the wallet.
- **Safety**: an item already paid or in flight is never sent again; a failed one can be retried as a new attempt
  (`...-r2` reference); billing refuses when OmniDome's own Paystack balance is below the batch; open refund/chargeback
  liabilities are netted against the wallet as money arrives.
- **Supplier payments**: a purchase order must be approved, the supplier needs bank details (the account number goes to Paystack
  once; only the recipient code and last 4 digits are kept; changing details is blocked while a payment is in flight), and the
  total paid across non-failed payments cannot exceed the order total. Manager access only.
- **Payroll mode**: `PAYROLL_PAYOUT_MODE=funded` (default) pays from the wallet; `direct` keeps the legacy per-payslip transfer from
  the platform balance (development only, no funding check, no fee).
- Transfer OTP must be disabled for API transfers in the Paystack dashboard, otherwise transfers stall in `otp` status.
- HR and inventory need `INTERNAL_SERVICE_KEY` and `BILLING_SERVICE_URL` in their environment.

## Reconciliation (platform admin) and the tenant statement

`routes/recon.py`, run on demand (`POST /recon/run`) or by an opt-in worker (`RECON_WORKER_ENABLED=true`, hourly,
`RECON_INTERVAL_SECONDS`), under a Postgres advisory lock. Read-only against Paystack; nothing here moves money.

1. **Solvency snapshot**: OmniDome's Paystack ZAR balance (`GET /balance`) vs the sum of the tenants' payout wallets.
   EFT-funded wallet credits never touch Paystack, so someone must top the Paystack balance up; negative headroom means
   OmniDome could not pay every wallet out today. Ops is emailed (`GATEWAY_ALERT_EMAIL`) when the state flips to `short`.
2. **Ledger copy**: Paystack's `GET /balance/ledger` is stored (idempotent on its id), categorised (payout, payout_reversal,
   charge, refund, dispute, settlement, fee, topup, other) and checked for continuity (`balance == previous + difference`);
   a missing or altered row shows as a gap. Categories are inferred from Paystack's free-text `reason`; unknown ones are `other`.
3. **Charge integrity**: every succeeded subaccount charge is verified (`GET /transaction/verify`) and the split Paystack
   applied is compared with what we asked for: the tenant must have received gross - commission on the right subaccount,
   and OmniDome's share must be about commission - Paystack fee (2 cent tolerance). A charge Paystack cannot find, or a short-changed
   tenant, is a *mismatch* and alerts ops. If Paystack does not return `fees_split` the charge is `no_split_data`
   (not called ok). **Verify this against one real test-mode charge: the `fees_split` field name comes from Paystack's API
   behaviour, not its OpenAPI file.**
4. **In-flight payouts and settlements**: payout items still processing after `RECON_PAYOUT_STALE_MINUTES` (120) are reconciled
   against Paystack; settlements paid to OmniDome's own bank account (`GET /settlement`) are copied for the audit trail.

Tenant view: `GET /gateway/statement?period=YYYY-MM` (collected, gateway fee, what the tenant receives, refunds, chargebacks,
payouts and fees, wallet balance, open liabilities, and how many charges were verified).

## Tenant liability

Refunds and lost disputes are paid from OmniDome's Paystack balance for money the tenant was already settled.
They are recorded in `billing_gateway_liabilities` (open until recovered). They are netted against the payout wallet
automatically as funding arrives (oldest first, whole liabilities only).

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
| `RECON_WORKER_ENABLED` | false | Run the reconciliation worker in the billing service |
| `RECON_INTERVAL_SECONDS` | 3600 | Worker interval |
| `RECON_LEDGER_PAGES` | 10 | Pages of Paystack's balance ledger copied per run |
| `RECON_PAYOUT_STALE_MINUTES` | 120 | A payout still processing after this long is reconciled |
| `PAYSTACK_NATIVE_SUBSCRIPTIONS_ENABLED` | false | Re-enable the retired `/payments/paystack/plans/.../sync` and `/subscriptions` creators |

## Not built yet

Dispute evidence file upload, VAT on the gateway fee, a Paystack
dedicated virtual account for EFT funding (today an admin records the EFT), tenant-books posting of payout fees, and the
platform prepaid credits + top-ups (Codex, platform side).
