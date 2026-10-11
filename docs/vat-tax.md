# VAT in OmniDome

General guidance, not tax advice. SARS figures verified against sars.gov.za on 2026-10-11; confirm with SARS or a tax adviser before relying on them for a formal decision.

## The two sides

| | OmniDome (charging tenants) | A tenant (charging its own customers) |
|---|---|---|
| VAT | **Charged**: OmniDome is treated as a VAT vendor by default (15%) | **The tenant's choice**: it says whether it is a VAT vendor |
| Prices | **VAT-inclusive**: the advertised price is what the tenant pays; the VAT is shown inside it | The tenant chooses: prices include VAT (default) or VAT is added on top |
| OmniDome fees (6% / 5.5% / 5% gateway commission, payout fees) | VAT-inclusive; the VAT inside each fee is recorded on the charge/payout | Shown on the tenant's statement as "includes VAT" |
| Config | Admin -> Platform Billing -> invoice settings (supplier name, address, **VAT number**) and `apps/web/lib/platform-pricing.json` (`tax_policy`, `supplier`) | Billing -> **VAT & tax** (`billing_tax_profiles`) |

**OmniDome still has to enter its VAT registration number** in the platform invoice settings. Until it does, Codex's platform invoicing marks documents "Pro forma invoice" rather than "Tax invoice" (a valid tax invoice needs the supplier's VAT number).

## What SARS says (South Africa)

- **Who charges VAT**: registered VAT vendors. Registration is **compulsory** when taxable supplies exceed **R2.3 million** in any consecutive 12 months (or are contractually certain to), and **voluntary** above **R120,000**. These figures apply from **1 April 2026** (up from R1m / R50,000). SARS is administering them although the amending legislation had not been promulgated when checked, so they are overridable (`ZA_VAT_COMPULSORY_THRESHOLD_ZAR`, `ZA_VAT_VOLUNTARY_THRESHOLD_ZAR`).
- **Deadline**: apply within **21 business days** of exceeding the threshold.
- **Rate**: standard rate 15% (`ZA_VAT_RATE_PERCENT`).
- **Tax invoice** (section 20): the words "Tax Invoice", "VAT Invoice" or "Invoice"; supplier name, address and VAT number; recipient name and address and, if the recipient is a vendor, their VAT number; serial number and date; description; quantity; value, VAT and total. A full invoice is required above **R5,000**; an abridged one is allowed at R5,000 or less; none is required at R50 or less. Issue within 21 days of the supply.
- **Prices** (sections 64-65): a vendor's prices are deemed VAT-inclusive, so VAT-inclusive pricing is the safe default.
- A business that is **not** registered does not charge VAT and issues a plain "Invoice".

Sources: SARS Budget 2026 FAQ, SARS "Tax Invoices", SARS "Register for VAT" pages.

## What the product does

- **Tenant tax profile** (`services/billing/tax.py`, `routes/tax.py`): country, registered or not, VAT number, rate, prices-include-VAT, registered name and address, registration date. Saving is validated: a vendor needs name, address and a 10-digit South African VAT number starting with 4; South Africa's rate is the statutory 15%; other countries enter their own rate (no unverified country rates are shipped). Every change is audited (`billing_tax_profile_events`).
- **Documents follow the profile**: every place that prices an invoice (subscription invoices, prorated first invoices, transfers, termination fees, the invoice and quote builders, fee policies) goes through the profile. A non-vendor **cannot** put VAT on a document whatever the client sends. Titles: "Tax invoice" / "Tax credit note" when VAT is charged, otherwise "Invoice" / "Credit note"; the VAT column and VAT line disappear when there is no VAT; a non-vendor never shows a VAT number. Credit notes carry the VAT treatment of the invoice they credit. Issued invoices are never rewritten when the profile changes.
- **Registration monitor** (`GET /tax/status`): last 12 months of invoiced ex-VAT value (credit notes net off, drafts and voids excluded) against the thresholds, plus a forward-looking run-rate check. States: registered, must_register, will_exceed, approaching (within 20%), may_register, below_threshold, not_applicable (non-South-African tenants).
- **Tenants that have not chosen yet** keep the legacy behaviour (15% added on top) so nothing changes under them; the Billing screens show a banner asking them to confirm their VAT status.

## Not built yet

- A monthly **tax invoice from OmniDome to each tenant for the gateway and payout fees** (VAT is recorded per charge and payout and shown on the statement, but no invoice document is generated). A VAT-registered tenant needs it to claim the VAT inside our fee as input tax.
- Abridged-invoice handling for amounts up to R5,000 (all documents are full invoices, which is always valid).
- Recipient VAT number / name / address checks on invoices above R5,000.
- Zero-rated and exempt supply categories per line (lines can carry 0% but there is no category).
- Per-country VAT rates other than South Africa: the tenant enters its own rate.
- Seat billing created by the legacy per-seat worker (`seat_runs`, off by default) still adds 15% on top; OmniDome's own pricing lives in the platform catalogue, which is VAT-inclusive.
