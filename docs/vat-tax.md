# VAT in OmniDome

General guidance, not tax advice. SARS figures verified against sars.gov.za on 2026-10-11; confirm with SARS or a tax adviser before relying on them for a formal decision.

## The two sides

| | OmniDome (charging tenants) | A tenant (charging its own customers) |
|---|---|---|
| VAT | **Charged**: OmniDome is treated as a VAT vendor by default (15%) | **The tenant's choice**: it says whether it is a VAT vendor |
| Prices | **VAT-exclusive**: the advertised price is before VAT; the invoice summation shows the 15% VAT added and the total | The tenant chooses: prices include VAT (default) or VAT is added on top |
| OmniDome fees (6% / 5.5% / 5% gateway commission, payout fees) | **VAT-exclusive**: 15% VAT is added on top (6.9% / 6.325% / 5.75% all-in); the VAT is recorded on each charge/payout | Shown on the tenant's statement as fee, VAT and total; a VAT-vendor tenant books the VAT as input tax (account 1210) |
| Config | Admin -> Platform Billing -> invoice settings (supplier name, address, **VAT number**) and `apps/web/lib/platform-pricing.json` (`tax_policy`, `supplier`) | Billing -> **VAT & tax** (`billing_tax_profiles`) |

**OmniDome's VAT number is a PLACEHOLDER (`4000000000`)** in `apps/web/lib/platform-pricing.json` (`supplier.vat_number`) until the real registration number is entered under Admin -> Platform Billing -> invoice settings. **Replace it before issuing real tax invoices**: a tax invoice with a wrong supplier VAT number is not a valid tax invoice and the tenant could lose its input claim.

## What SARS says (South Africa)

- **Who charges VAT**: registered VAT vendors. Registration is **compulsory** when taxable supplies exceed **R2.3 million** in any consecutive 12 months (or are contractually certain to), and **voluntary** above **R120,000**. These figures apply from **1 April 2026** (up from R1m / R50,000). SARS is administering them although the amending legislation had not been promulgated when checked, so they are overridable (`ZA_VAT_COMPULSORY_THRESHOLD_ZAR`, `ZA_VAT_VOLUNTARY_THRESHOLD_ZAR`).
- **Deadline**: apply within **21 business days** of exceeding the threshold.
- **Rate**: standard rate 15% (`ZA_VAT_RATE_PERCENT`).
- **Tax invoice** (section 20): the words "Tax Invoice", "VAT Invoice" or "Invoice"; supplier name, address and VAT number; recipient name and address and, if the recipient is a vendor, their VAT number; serial number and date; description; quantity; value, VAT and total. A full invoice is required above **R5,000**; an abridged one is allowed at R5,000 or less; none is required at R50 or less. Issue within 21 days of the supply.
- **Prices** (sections 64-65): a vendor's quoted prices are deemed VAT-inclusive unless the quote shows VAT separately, so every OmniDome price shown VAT-exclusive must say "excl. VAT" and the summation must show the VAT and the total.
- A business that is **not** registered does not charge VAT and issues a plain "Invoice".

Sources: SARS Budget 2026 FAQ, SARS "Tax Invoices", SARS "Register for VAT" pages.

## What the product does

- **Tenant tax profile** (`services/billing/tax.py`, `routes/tax.py`): country, registered or not, VAT number, rate, prices-include-VAT, registered name and address, registration date. Saving is validated: a vendor needs name, address and a 10-digit South African VAT number starting with 4; South Africa's rate is the statutory 15%; other countries enter their own rate (no unverified country rates are shipped). Every change is audited (`billing_tax_profile_events`).
- **Documents follow the profile**: every place that prices an invoice (subscription invoices, prorated first invoices, transfers, termination fees, the invoice and quote builders, fee policies) goes through the profile. A non-vendor **cannot** put VAT on a document whatever the client sends. Titles: "Tax invoice" / "Tax credit note" when VAT is charged, otherwise "Invoice" / "Credit note"; the VAT column and VAT line disappear when there is no VAT; a non-vendor never shows a VAT number. Credit notes carry the VAT treatment of the invoice they credit. Issued invoices are never rewritten when the profile changes.
- **Registration monitor** (`GET /tax/status`): last 12 months of invoiced ex-VAT value (credit notes net off, drafts and voids excluded) against the thresholds, plus a forward-looking run-rate check. States: registered, must_register, will_exceed, approaching (within 20%), may_register, below_threshold, not_applicable (non-South-African tenants).
- **Tenants that have not chosen yet** keep the legacy behaviour (15% added on top) so nothing changes under them; the Billing screens show a banner asking them to confirm their VAT status.

## OmniDome's monthly tax invoice to each tenant (fees)

`services/billing/fee_invoicing.py`, `routes/fee_invoices.py`. A VAT-registered tenant needs a tax invoice from OmniDome to claim the VAT on our
gateway and payout fees as input tax, so OmniDome issues one per tenant per month:

- **What it covers**: every fee not yet invoiced up to the end of the month: card-collection commission and payout fees, each already stored VAT-exclusive with the 15% VAT added on top when it was charged. A fee that arrives after its month was invoiced rolls into the next invoice. A payout that fails after its fee was invoiced gets its fee + VAT returned to the wallet, and the return is a negative adjustment line on the next invoice (a credit alone is not an invoice: it carries forward).
- **Document**: immutable, sequentially numbered `ODF-<year>-<serial>`, with OmniDome's and the tenant's details snapshotted at issue. "Tax invoice" when OmniDome is a VAT vendor with a VAT number; a plain "Invoice" (no VAT) if OmniDome is not a vendor; "Pro forma invoice" if OmniDome's own name/address/VAT number are missing. Above R5,000 the recipient's name and address are needed: if the tenant has not entered an address the invoice is flagged incomplete and tells them where to add it (Billing -> VAT & tax). The recipient's VAT number is shown when the tenant is a vendor.
- **Issuing**: `POST /fee-invoices/generate` (platform admin; last month by default), or the opt-in worker `FEE_INVOICE_WORKER_ENABLED=true` (from the 2nd of each month, every 6 hours, idempotent per tenant and month). Tenants see their invoices at `GET /fee-invoices` and the printable page at `GET /fee-invoices/{id}?format=html`; platform admins see all with `?all=true`.
- Delivery by email is not built; the tenant downloads the document from Billing -> Statement.

## Not built yet

- Abridged-invoice handling for amounts up to R5,000 (all documents are full invoices, which is always valid).
- Recipient VAT number / name / address checks on invoices above R5,000.
- Zero-rated and exempt supply categories per line (lines can carry 0% but there is no category).
- Per-country VAT rates other than South Africa: the tenant enters its own rate.
- Seat billing created by the legacy per-seat worker (`seat_runs`, off by default) still adds 15% on top; OmniDome's own pricing lives in the platform catalogue, which is VAT-inclusive.
