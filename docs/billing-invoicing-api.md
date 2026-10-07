# Billing: invoicing suite API (manual invoices, catalog, templates, quotes, delivery, share links, movements)

Service: `services/billing` (port 8003; web proxy path `/svc/billing/...`). All money is ZAR, `Decimal`, returned as **strings**.
Everything is tenant-scoped from the signed identity. Revenue still posts to finance **from invoices only, on issue**
(`POST /invoices/{id}/send`); drafts and quotes never touch the ledger.

Role tiers (billing `access.py`): **reader** views, **clerk** creates/edits/sends, **admin** voids, credits, big discounts,
templates, forced conversions, reconciling stuck sends. A discount above `BILLING_CLERK_MAX_DISCOUNT_PERCENT` (default 20) of
the gross needs **admin**. VAT default is `BILLING_VAT_RATE_PERCENT` (default 15), overridable per line (`tax_rate`).

## Money rules (server-side, never trust the client)
Per line: `gross = qty*unit_price`; `discount` is an amount (`discount_type:"amount"`, default) or a percent of gross;
`net = gross - discount`; `vat = net*tax_rate/100` (half-up per line); `total = net + vat`. Document: `subtotal = sum(net)`,
`vat = sum(vat)`, `total = subtotal + vat`. Client-sent totals are ignored. Stored line shape (`lines[]`):
`{line_id, description, quantity, unit_price_zar, gross_zar, discount_zar, tax_rate, total_zar (ex VAT), vat_zar, line_total_incl_zar, catalog_item_id}`.

## 1. Manual / one-off invoices (`routes/invoice_documents.py`)
| Endpoint | Tier | Notes |
|---|---|---|
| `POST /invoices/manual` | clerk | Creates a **draft**. Body: `customer_id`, `issue_date?`, `due_date?` (default issue + template `default_due_days`), `lines[{description, quantity, unit_price, discount?, discount_type?, tax_rate?, catalog_item_id?}]` (1..200), `notes?`, `terms?`, `po_number?`, `source_type` (`manual`\|`field_sales`\|`technician`\|`termination_fee`\|`web`\|`other`), `created_by?`, `template_id?`, `bill_to?{name,email,phone,address}` (else snapshotted from CRM, best effort). 201 -> invoice detail |
| `PUT /invoices/{id}` | clerk | Draft only (409 otherwise; subscription invoices and credit notes are not editable). Send only fields to change; `lines` replaces all lines |
| `POST /invoices/{id}/duplicate` | clerk | New draft copying lines/notes/terms/bill-to |
| `PUT /invoices/{id}/lines/order` | clerk | `{order:[line_id,...]}` must list every line exactly once |
| `GET /invoices/{id}/detail` | reader | Invoice + extras |
| `POST /invoices/{id}/send` | clerk | **Existing**: issues the draft (dunning schedule + revenue outbox entry) |

Invoice detail: `{id, number, status, customer_id, subscription_id, credit_note_of, issue_date, due_date, lines[], subtotal_zar, discount_total_zar, vat_zar, total_zar, amount_paid_zar, balance_zar, currency, notes, terms, po_number, source_type, created_by, template_id, bill_to, quote_id, created_at}`.
Numbering reuses `invoice_sequences` (`INV-<TENANT4>-000123`); drafts consume a number.

## 2. Item catalog and templates
- `GET /invoice-items?q&category&active&limit&offset` (reader), `POST` (clerk), `GET/PUT/PATCH /invoice-items/{id}` (reader/clerk), `DELETE` (admin).
  Item: `{id, name, description, unit_price_zar, tax_rate, category, active}`. Pass `catalog_item_id` on a line; the line stores its own price snapshot (deleting an item never changes invoices). Unknown ids -> 422.
- `GET /invoice-templates`, `GET /invoice-templates/default` (reader; built-in defaults if none, `builtin:true`), `POST/PUT/PATCH/DELETE` (admin).
  Template: `{name, is_default, company_name, company_address, vat_number, logo_url (http/https only), accent_colour (#rrggbb), footer, payment_details, default_terms, default_due_days, show_columns{description,quantity,unit_price,discount,tax,line_total}, show_payment_details, show_terms}`.
  The first template becomes default; setting another default clears the old one. An invoice/quote uses its `template_id`, else the default.

## 3. Quotes (`routes/quotes.py`, logic in `quotes.py`)
Statuses: `draft -> sent -> viewed -> accepted | declined | expired -> converted`. Expiry is lazy (a sent/viewed quote past `valid_until` reads as `expired`).
| Endpoint | Tier | Notes |
|---|---|---|
| `POST /quotes` | clerk | `customer_id` **or** `prospect_name` (+ `prospect_email`, `prospect_phone`, `prospect_address`) for field-sales leads; `source` (`field_sales`\|`technician`\|`web`\|`other`), `created_by`, `issue_date`, `valid_until` (default +30d, `BILLING_QUOTE_VALID_DAYS`), `lines`, `notes`, `terms`, `po_number`, `template_id` |
| `GET /quotes?status&customer_id&source&created_by&page&page_size`, `GET /quotes/{id}` | reader | `{items,total,page,page_size}` |
| `PUT /quotes/{id}` | clerk | Draft only |
| `POST /quotes/{id}/send` | clerk | Mark sent without emailing |
| `POST /quotes/{id}/accept` / `decline` | clerk | `{note?}` internal (staff records a decision); repeating the same decision is a no-op |
| `POST /quotes/{id}/convert` | clerk | `{customer_id?, due_date?, force?}` -> `{created, quote, invoice}`. Needs `accepted` (`force`=admin only; declined never). **Idempotent**: a repeat returns the same invoice with `created:false`. Links both ways: `quote.converted_invoice_id` and `invoice.quote_id`. Prospect quotes need `customer_id`. The result is a **draft**; issue it with `POST /invoices/{id}/send` |

Quote JSON: `{id, number (QUO-...), status, customer_id, prospect{name,email,phone,address}, issue_date, valid_until, lines[], subtotal_zar, discount_total_zar, vat_zar, total_zar, notes, terms, po_number, source, created_by, template_id, converted_invoice_id, sent_at, viewed_at, accepted_at, declined_at, converted_at, decision_note}`.

## 4. Documents and exports
`GET /invoices/{id}/document`, `GET /quotes/{id}/document` (reader) -> print-ready, self-contained HTML (all user text escaped, no scripts, strict CSP, `@media print` styled; use the browser's Print -> PDF; **no server-side PDF yet**).
`GET .../export?format=csv|json|html` (reader). CSV neutralises formula cells (`=`, `+`, `-`, `@`).

## 5. Email delivery (AgentMail via the Communication service) (`delivery.py`)
`POST /invoices/{id}/email`, `POST /quotes/{id}/email` (clerk), header `Idempotency-Key` (optional), body `{to?[], cc?[], subject?, message?, kind?: "document"|"reminder", link_expires_in_days?}`.
- Invoice must be **issued** (draft -> 409 "issue first"). `kind:"reminder"` (invoices payable only) is the "send_reminder" action. Quote success marks a draft quote `sent`.
- `to` defaults to the customer's/billing account's email (invoice) or the prospect email (quote).
- The email carries a text part, an HTML part with the document **embedded** (Communication only accepts PDF attachments, so there is no HTML attachment) and a freshly minted signed public link. Mailbox: `BILLING_MAILBOX_ID`, else the tenant's single active Communication mailbox (409 otherwise).
- Suppression list honoured (suppressed addresses are dropped and recorded as `suppressed`; none left -> 409). Throttle: `BILLING_EMAIL_MAX_PER_RECIPIENT_HOUR` (default 3) per document per recipient -> 429.
- Failure handling (same as the purchase-order send): a `queued` claim row is committed **before** I/O. Definite refusal (HTTP 4xx except 408, or status failed/rejected/error) -> row `failed`, key cleared, retry allowed (502 "nothing was sent"). Anything ambiguous (timeout, 5xx, unconfirmed body) -> row stays `queued` with `detail.ambiguous=true`, 502, and **further sends return 409** until `POST /delivery/events/{event_id}/reconcile {outcome:"sent"|"not_sent", message_id?}` (admin).
- Replay with the same `Idempotency-Key` returns the original result (`replayed:true`) without sending.
- Success: `{status:"sent", message_id, event_id, recipients{to,cc}, link_expires_at, replayed}`.
- `GET /invoices/{id}/delivery-events`, `GET /quotes/{id}/delivery-events` (reader): `[{id,event_type,kind,recipient,subject,message_id,actor,detail,at}]`. Event types: `queued, sent, delivered, bounced, complained, failed, suppressed, viewed, opened, replied`.

### `POST /delivery/webhook-event` (Communication -> billing, internal)
Auth: `x-internal-key: $INTERNAL_SERVICE_KEY` (constant-time; closed if unset). Body `{tenant_id, message_id, event_type: delivered|bounced|complained|rejected|replied|opened, occurred_at?, detail?}`. Matches rows with that `message_id` (tenant-scoped), appends one event per document, idempotent per (message, type). `bounced`/`complained` add the address(es) the provider names in `detail.recipient|recipients` (or the single recipient) to the suppression list.
AgentMail mapping: `message.delivered -> delivered`, `message.bounced -> bounced`, `message.complained -> complained`, `message.rejected -> rejected` (stored as `failed`), `message.received` (reply on our thread) `-> replied`. **Gap:** Communication's `_apply_delivery_event` does not yet forward these to billing; it must call this endpoint with the tenant and `message_id`.

## 6. Share / pay links and PUBLIC routes (`routes/public_invoices.py`)
- `POST /invoices/{id}/share-link`, `POST /quotes/{id}/share-link` (clerk) body `{expires_in_days?}` (default `BILLING_SHARE_LINK_TTL_DAYS`=30, max 365) -> `{id, token, url, api_path, expires_at}`. **The raw token is returned once**; only its SHA-256 is stored. Invoices must be issued and not void; max 20 active links per document.
- `GET /invoices/{id}/share-links`, `GET /quotes/{id}/share-links` (reader) -> `[{id, expires_at, revoked_at, active, view_count, last_viewed_at}]` (no tokens). `POST /share-links/{id}/revoke` (clerk).
- `url` = `BILLING_PUBLIC_BASE_URL` (else `APP_PUBLIC_URL`) + `/public/invoices/{token}` or `/public/quotes/{token}` (null if neither is set). **The web app must route `/public/invoices/*` and `/public/quotes/*` to billing** (or render its own pages over `api_path`).
- **No auth** (path prefix `/public/` is public to the entitlement middleware):
  - `GET /public/invoices/{token}?format=json|html` -> sanitised document (`number,status,issue_date,due_date,po_number,bill_to{name,address},lines[],subtotal,discount_total,vat,total,paid,balance,notes,terms,branding,currency` + `payable`, `pay_path`). Records `view_count` and a `viewed` event (deduped to one per 10 min).
  - `POST /public/invoices/{token}/pay` `{amount_zar?}` -> `{authorization_url, reference}`: calls the same `initialize_paystack` logic (balance cap, customer email from record, unique reference, `PaystackInitialization` row; callback from `BILLING_PUBLIC_PAY_CALLBACK_URL` if allowed). Only `sent|partially_paid|overdue` invoices (else 409); gateway problems map to generic 409/502/503. Payment is applied by the existing Paystack webhook.
  - `GET /public/quotes/{token}`, `POST /public/quotes/{token}/accept|decline` `{note?}` (a first view moves `sent -> viewed`; drafts/expired are not actionable).
- Hardening: per-IP limits (view 60/min, actions 10/min, `trusted_client_ip`), 20 unknown-token lookups per 10 min per IP -> 429 (even for good tokens from that IP), identical `404 {"detail":"Not found"}` for unknown/wrong-type/revoked/expired tokens, no internal ids, customer email or phone in responses, `Cache-Control: no-store`.

## 7. Customer-app endpoints (`routes/customer_app.py`)
`GET /customer-app/invoices?customer_id=&status=&include_links=&limit=` (reader): issued invoices (never drafts) `{id, number, status, is_credit_note, due_date, total_zar, amount_paid_zar, balance_zar, overdue, payable, pay_link, links}` + `outstanding_zar`, `overdue_zar`. `include_links=true` mints a new expiring pay link per payable invoice (max 25, token returned once). `GET /customer-app/quotes?customer_id=` (non-draft). `GET /customer-app/statement?customer_id=&from=&to=` (opening/closing balance, invoice/credit-note/payment lines, open credits).
**Auth gap:** billing has no end-customer identity (`access.py`: "no customer<->user linkage"; portal issues no customer token). These endpoints require a billing **reader** identity (a signed service identity from the customer-app backend) and a **mandatory** `customer_id` that the calling backend must bind to the logged-in customer. Customers themselves can open one document via the share-token flow. Replace the dependency when an end-customer token exists.

## 8. Movements and suggested actions (`routes/movements.py`)
- `GET /invoices/{id}/timeline` (reader) -> `{invoice_id, number, status, events[] (oldest first), suggested_actions[]}`.
- `GET /billing/movements?from=&to=&customer_id=&type=&limit=` (reader; `type` = one, comma list, or `prefix*`; limit <= 500) -> `{items[], count, total_matching}` newest first.
- Movement: `{id, type, at, amount, status, invoice_id, quote_id, customer_id, actor, next_actions[ids], detail}`. Derived from existing tables (nothing duplicated). Types: `invoice_issued` (finance outbox time), `invoice_voided`, `credit_note`, `payment`, `partial_payment`, `payment_failed`, `refund` (refunded payment rows), `credit`, `refund_due` (billing_customer_credits), `dunning_<action>` (executed only), `payment_arrangement` (customer level, no invoice), `termination_fee`, `invoice_emailed`, `invoice_reminder_sent`, `invoice_delivered|bounced|complained|failed|viewed|opened|replied|suppressed|email_unconfirmed|email_pending`, same for `quote_*`, and `quote_created|sent|viewed|accepted|declined|converted`.
- `suggested_actions[]` item: `{id, label, endpoint ("METHOD /path" or null), payload, tier, reason?}`. Real endpoints: `issue_invoice`, `edit_draft`, `share_pay_link`, `record_payment` (`POST /payments`), `send_invoice_email`, `send_reminder` (`POST /invoices/{id}/email {kind:"reminder"}`), `offer_arrangement` (`POST /collections/{customer_id}/arrange`, admin; payload is a 3-instalment suggestion), `suspend_service` (`POST /collections/{customer_id}/suspend`, admin, 14+ days overdue), `issue_credit` (`POST /invoices/{id}/credit-note`, admin), `void_invoice` (admin, no payments). **`endpoint:null, reason:"integration pending..."`**: `queue_call` (no call-centre queue endpoint in billing), `mailer_builder`, `review_upgrade_request` (no upgrade/downgrade request endpoint), `issue_refund` (no refund payout endpoint; a credit note on a paid invoice records a `refund_required` row in `billing_customer_credits`).

## Tables added (all new; `Base.metadata.create_all` in `init_tables`, no ALTERs)
`invoice_items`, `invoice_templates`, `invoice_meta` (per-invoice extras keyed by invoice id; the `invoices` table is untouched), `quotes`, `quote_lines`, `quote_sequences`, `document_share_links`, `document_delivery_events`.

## Known gaps
- No server-side PDF (browser print only); Communication accepts PDF attachments only, so the document is embedded in the email body.
- Communication does not yet call `/delivery/webhook-event`; web app must expose the `/public/...` routes.
- No end-customer authentication (see section 7). Request/access logs include the share token in the URL path (shared `RequestLoggingMiddleware` and uvicorn access log): redact `/public/` paths or disable access logs for billing before relying on link secrecy.
- Rate limiters and the bad-token throttle are in-process (per worker), like `services.common.rate_limiter`.
- Invoice `issued_at` is taken from the finance-outbox row; invoices issued before the outbox existed fall back to `created_at`.
