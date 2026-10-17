# Product management: shared catalogue and profitability

Design proposal · 17 October 2026 · Companion: `product-management-preview.html`

## Outcome and scope

Product Management becomes the place to define, develop and maintain every item OmniDome sells, buys, includes in an offer, consumes internally or holds as an asset. Purchasing, inventory, promotions, quotations, billing, tickets and finance reference the same immutable product identity. The primary management question is: **what do we offer, where does it come from, and what does it earn after its costs?**

This deliverable is a proposed design, a working browser prototype with illustrative data, and an implementation contract. It does not migrate data, change the running application or connect the prototype to live services. Prototype edits last for the page session only. The production rollout described below remains implementation work.

## Findings in the current repository

- `apps/web/components/modules/products-module.tsx` reads plans and bundles through `apps/web/lib/products-api.ts`. Creation submits name, category and price to `/svc/billing/plans`; subscriber counts and MRR are derived from billing subscriptions. The generic form does not represent a full product definition.
- `services/inventory/database.py` already defines ServiceType → ProductCategory → ProductRange → Product, plus suppliers, stock relationships, packages and pricing rules. Products have a tenant-unique SKU, preferred supplier, scalar cost and retail price. This is a useful starting point, not a reason to create a third unrelated catalogue.
- `services/billing/models.py` contains a separate `billing_plans` catalogue, bundles, subscriptions and invoice lines. A compatibility mapping is necessary before those records can share the catalogue identity.
- Existing inventory category/range relationships include cascading deletion. Production changes must protect transaction history before exposing deletion across the combined catalogue.
- The design follows `DESIGN.md`: Obsidian Telecom surfaces, cyan actions, compact operational tables, semantic status colours and accessible labels.

## 1. Identity and classification

**Visible management hierarchy: Category → Range → SKU.**

Examples:

| Category | Range | SKU / product number | Description |
|---|---|---|---|
| Connectivity | Home Fibre | OD-000101 | Fibre 100/100, 24-month offer |
| Connectivity | Business Fibre | OD-000102 | Fibre 200/200, business SLA |
| Equipment | Wi-Fi Routers | OD-000201 | AX1800 router |
| Infrastructure | Installation Materials | OD-000301 | Fibre cable, per metre |

“Main products” is interpreted as the overall catalogue, not a fourth mandatory level. Existing service types remain a separate service-family attribute/filter, such as Fibre, LTE, VoIP, Hosting or Non-telco. Legacy categories and ranges are mapped explicitly; no automatic reclassification by similar names. If a fourth portfolio level is later needed, it can sit above categories without changing SKU identity.

- `product_id`: immutable UUID used for integration and relationships.
- `product_number`: immutable, server-assigned human-readable SKU code, unique within the tenant, never reused. Existing SKU strings become the canonical number where valid; retain aliases and source IDs during migration.
- Product title, customer-facing name, description, specifications and classification may evolve independently of the number.
- Supplier SKU, manufacturer part number, barcode and external system codes are aliases, not primary keys.
- A price/cost change creates a new commercial version of the same SKU. A change in what is delivered that requires separate stock, provisioning, entitlement or contract treatment creates a new SKU linked by “replaces/replaced by”.
- Category is derived from range membership, avoiding inconsistent category/range pairs. Reclassification is effective-dated so historical reports can use historical classification or explicitly restate to today's structure.

### Separate the questions that are currently conflated

| Attribute | Values / rule |
|---|---|
| Nature | Digital service, physical item, professional service. Composite offers link component SKUs rather than hiding physical items inside a digital label. |
| Usage | Sell to customers, purchase from suppliers, consume internally, include in another product, hold as a company asset. Multiple selections allowed. |
| Stock tracking | None, quantity, serial number, batch. Physical goods can be consumables, resale inventory or owned equipment. |
| Service family | Fibre, LTE/5G, VoIP, hosting, TV, installation, equipment, other; managed lookup values. |
| Lifecycle | Draft → In development → Ready for review → Active → Retired → Archived. Rejected review returns to development. |
| Charge basis | Recurring, one-off, usage-based, or a combination via charge lines. |

“Fixed stock” is ambiguous: the journey asks **resale stock, internal consumable, or company-owned asset?** A fixed asset is not automatically a saleable product. Transfers to technicians or warehouses do not constitute a sale or create profit.

## 2. Screen structure

The main screen has a short heading, an explicit **New product** action and six work areas:

1. **Catalogue:** expandable Category → Range → SKU rows; search by number/name/alias; nature, usage, supplier and lifecycle filters. Manage categories and ranges alongside the tree. Visible View, Edit and Archive/Delete actions.
2. **Profitability:** drill from category to range to SKU; projected unit economics versus realised financial results; date/period and currency controls; cost-completeness warnings; separate recurring, upfront and contract views.
3. **Pricing & changes:** price versions, supplier cost revisions and promotions in one timeline. Scheduled changes show before/after margin and affected contracts. Actions: Schedule price, Record supplier cost, Create promotion.
4. **Suppliers:** preferred and alternative sources, supplier references, costs, lead times, minimum order quantities, quote validity, contract dates and affected products. Link to the supplier's authoritative record rather than create a duplicate supplier master.
5. **Development:** draft products, owners, target launch, readiness checklist, cost completeness, commercial review, provisioning readiness and launch/retire workflow.
6. **Product detail:** reached from any view; sections for Definition, Costs & sourcing, Components, Selling prices, Profitability, History and Usage across modules. Preserve filters when returning to the list.

### Catalogue columns

Product number; product name; category/range; nature/usage; preferred supplier; charge basis; current net selling price; recurring direct cost; upfront direct cost; projected margin with explicit basis; lifecycle; actions. Add optional columns for stock, active subscriptions, realised period revenue and forecast completeness. Do not imply that one-off prices and monthly prices are directly comparable.

Top indicators are scoped to the selected filters: active SKUs, products missing cost data, planned changes, and realised gross profit for a selected period **only once actual financial data is connected**. Never display fabricated zero profit when data is unavailable.

### Design contract

The screen's job is to expose product identity, sources and economics, with New product as the primary action. Use the existing dark design tokens, restrained borders and dense readable tables. Large screens use a hierarchy rail, data table and contextual detail; smaller screens stack the rail above results and allow labelled horizontal table scrolling. The product form uses a full-width workspace or large dialog, not the current small generic modal. Keep cost context visible while editing pricing. Every field has a persistent label; keyboard focus is visible; dialogs trap focus and restore it when closed. Loading, empty, failed load, failed save, permission-limited and incomplete-cost states must have explicit copy.

## 3. Create and edit journey

Save draft is available before all launch requirements are met. Publishing validates the complete product. Editing an active product opens a draft revision; it never silently overwrites the published commercial terms.

### Step 1 — Define the product

- Product number (assigned on first save, read-only afterwards), internal title, customer-facing title, short and full descriptions.
- Category and dependent range, with inline create where authorised; service family and tags.
- Nature; usage checkboxes; stock/asset treatment; owner; proposed launch date.
- Digital/telco: access technology, download/upload speed and units, data allowance or unlimited flag, FUP policy, provisioning profile, coverage/provider constraints, SLA, contract duration, cancellation/return policy references.
- Physical: manufacturer, model, supplier aliases, barcode, unit of measure, purchase/sale unit conversion, serial/batch tracking, warranty, weight and dimensions as applicable.
- Internal/asset: intended department, tracking requirements and finance classification reference. Avoid making a GL code the primary product definition.
- Professional service: service unit (hour, visit, job), delivery method and fulfilment requirements.

### Step 2 — Source and cost

One product can have several suppliers, and one cost sheet can contain several cost components. Each line contains:

`cost component | supplier/internal source | source reference | quantity | unit | unit cost | currency | cadence | tax treatment | effective from/to | evidence | confirmed/estimated`

Cost types include access/wholesale, bandwidth, licence, installation, equipment, freight, labour and other attributable delivery costs. Cadence is one-off, recurring with frequency, or usage-based with a driver. Recurring frequency and quantity conversion must be explicit. Non-recoverable costs belong in the cost basis; tax treatment is configured by finance, not inferred from product nature.

Preferred/alternative suppliers have supplier product references, purchase units, lead time, minimum order, warranty and availability. Alternative quotes are mutually exclusive sourcing scenarios: **do not add all suppliers' quotes together**. All active cost components in the selected sourcing scenario do contribute.

Allow “cost unknown” with a reason and owner. A missing cost is not zero. Display incomplete profitability and prevent ordinary publication unless an authorised exception is recorded. Zero-cost lines require an explicit reason.

### Step 3 — Include other products

Search the same catalogue for components. Fields: child SKU, quantity/UOM, required/optional, charge to customer or included, once/per period/per usage, supplier/stock sourcing policy, ownership (gift/loan/rental), return requirement and effective dates.

Example: fibre SKU includes one router SKU at customer charge R0. The router's cost and fulfilment requirement still apply. It reserves stock on order, consumes stock on confirmed delivery, and retains the serial-to-customer link where required. A loaned router retains an asset/return relationship.

Reject self-reference and indirect cycles; validate quantity and unit compatibility. A router's cost is included once through the component relationship, not also as an independent manual router cost line. Cost sheets must show the provenance of inherited component costs. Component cost changes trigger an impact review for parent offers, with an explicit decision to adopt a new effective version; they do not rewrite old offers.

### Step 4 — Price and promotion

- Currency; selling price with explicit tax-inclusive/exclusive entry mode; configured tax code; recurring charge interval; once-off setup fee; usage rates and units where relevant.
- Price list/channel/customer segment; minimum term; launch and expiry; target/minimum margin; contract price-change policy.
- Promotions are separate overlays: code/name, fixed price or discount, eligible SKU/range/category, audience/channel, enrolment window, benefit duration, quantity limits, funding source, stacking rule, priority and approval.
- “Three months discounted” is distinct from “offer available for enrolment until December”. Show both dates/rules.
- Fixed-value and percentage promotions have an explicit precedence policy; default no stacking. Resolve ties deterministically, reject ambiguous overlaps and show the winning rule in a quote preview.
- Existing subscribers may retain a contracted rate. “Change list price” must ask whether it affects new sales only or creates a separately approved migration proposal for existing contracts. Never silently reprice all subscriptions.

### Step 4b — Customer fees

Fees are a configurable list on the product, separate from its base price and from internal costs. A customer charge is revenue; the cost of delivering it belongs in the cost sheet. Each fee has: enabled toggle, **treatment** (Charge / Included / Waived; the latter two bill R0 but are still disclosed), amount, **trigger/cadence** (once-off, monthly, on event), tax code and the invoice line description.

Default fee types: delivery, setup, callout, maintenance, installation, activation, administration, equipment rental, reconnection, relocation, support visit, other (custom). Rules:

- Delivery is a toggle. Enabling it proposes a once-per-order fee; postcode/zone pricing and collection options are production work.
- Once-off and monthly fees feed the customer total and the contract-contribution calculation. Event-triggered fees (callout, reconnection, relocation, support visit) are disclosed to the customer but excluded from forecast revenue until an event occurs.
- Each fee may link to a fee policy (below), so the amount, waiver rules and the invoice wording come from one source.
- The existing single "setup fee" field migrates into this list as the Setup fee.

### Step 4c — Media, policies and documents

**Media (physical products only).** Gallery of photos, GIFs, meme-style images and 3D models. Images: PNG, JPEG, WebP, AVIF, GIF (size-limited); 3D: GLB, glTF, USDZ. Each asset has alt text, a primary-image flag, ordering and a visibility setting. The gallery appears only when Nature is *Physical item*; digital and professional services can still attach documents. Files are scanned and size/type-validated server-side, stored in object storage under the tenant, and referenced by ID, never inlined into the product record. Animated GIFs play on request (reduced-motion safe); 3D assets show a fallback image where the portal cannot render them.

**AI description assistance.** The description field has a *Suggest description* action with a style choice (customer-friendly, technical summary, short portal description). It drafts only from the product's recorded facts (nature, speeds, inclusions, fees, specifications); it must not invent specifications, prices or legal commitments. Output is a suggestion: existing text is never overwritten until the author selects *Use suggestion*. Requests run through the orchestrator under the tenant's model quota and are audited like any agent proposal. The prototype demonstrates the interaction only; no model is connected.

**Fee policy and T&C links.** The policy library already used by invoices is the single source for fee policies and terms. A product links to an approved policy **version**, not a copy. Linked policies appear on the quote, invoice and portal, and a required T&C version is presented for acceptance at order. Acceptance records the version, time and actor. Publishing a new policy version never alters accepted agreements; the product shows which version applies from which effective date.

**Documents.** T&C documents, fee schedules, instructions, manuals, warranties, installation guides (PDF/DOCX/TXT, size-limited). Each has category, version, effective date, an *acceptance required* flag and visibility: **Internal only** (default for new uploads) or **Customer portal**. Replacing a document creates a new version; old versions remain for history and for agreements already accepted.

### Step 1a — Editable definition (CRUD)

Every definition field is directly editable and nothing is preloaded: a new product starts with category, range and service family unselected, so the user chooses them deliberately. Category, range and service family are **managed lists** with visible controls: pen (rename), plus (add) and bin (delete). Renaming updates every product that uses the value; deleting is blocked, with the blocking products named, while any product uses it, and deleting a category also removes its empty ranges. Changing the category clears the range. The **product number** has a pen to set a custom number (3–24 letters, digits or hyphens, unique, never reused), an undo icon to return to auto-assignment, and a lock once the product is launched or in use. Product nature and usage are fixed enumerations because validation, stock and billing rules depend on them. Existing products show a bin to archive or delete from the same screen. A customer-facing name is separate from the internal name.

**AI description assistance** sits directly under the description box: choose a style, press *Draft with AI*, and a suggestion panel appears with an editable draft and the actions *Replace description*, *Append to description*, *Regenerate* and *Dismiss*. The current text is never changed until the user applies the draft.

### Step 3a — Included products come from the catalogue

Included items are chosen from a dropdown of products that are already developed and launched, never typed. Each row shows the item's picture, number, nature, once-off cost, customer fees and document count, read live from that product, plus quantity, a view-details icon and a remove bin. Pictures, fees and documents are edited on the included product itself, so there is one source. Self-inclusion and cycles are excluded from the list, and the same product cannot be added twice. A product that must be included but is not yet launched is developed through the same journey first (for example equipment that needs no ICASA lodgment can take the direct route below).

### Step 4d — Research and KPIs

**Competitor analysis** per SKU: competitor, offer, price (ex tax), spec, term, date checked and source URL or note, with add and remove. OmniDome computes the positioning (your price against the competitor median and range, and how many competitors are cheaper). Automated research via a web-research connector is a production option; the prototype takes manual entries only and invents none. **KPI links**: the user chooses which KPIs the product is tracked on, from a list by nature. Digital: active subscribers, MRR, new sales (30 days), churn, realised gross profit, open tickets. Physical: stock on hand, reserved stock, units sold, customers holding the item, returns, realised gross profit. After launch the product detail and review show these from sales, billing, inventory, finance and support, with a clear "not connected" state where a feed is absent.

### Step 5 — Launch route, internal testing and ICASA lodgment (launch requirements)

Three launch routes are offered. **Full**: internal testing and ICASA lodgment. **No ICASA**: internal testing only, for items that need no lodgment such as equipment or non-telecoms products. **Direct to market**: neither. Any skipped part needs a recorded reason and is audited. Whatever is kept becomes a gate on the **Launch product** action, not an advisory field.

**Internal testing.** A standard test plan is proposed from the product's nature and can be extended:

| Nature | Standard tests |
|---|---|
| Digital service | Provisioning & activation; speed/throughput; billing & invoice line; customer-portal order journey; cancellation & termination |
| Physical item | Fulfilment & stock reservation; serial & warranty record; billing & invoice line |
| Professional service | Scheduling & job completion; billing & invoice line |

Each test records result (Pending, Pass, Fail, Waived), tester, date, notes and evidence (file reference). A Waived test needs a written reason. Launch requires every standard test Passed (or Waived with reason) and no test Failed or Pending. Test results belong to the product revision being launched; a material change to the definition, cost or fulfilment invalidates earlier results and requires re-test or a recorded waiver.

**ICASA lodgment.** Licensees must notify ICASA of new products, product amendments/terminations and promotions before implementation. Research findings (October 2026, secondary sources; the primary regulation text could not be read):

- The notification is an **email to `tariffs@icasa.org.za`**. No fillable ICASA web form or standard template was found. Per the compliance consultancy Ellipsis, ICASA has advised that each notification include the **objectives**, the **reason(s)**, the **effective date** and, for a promotion, the **period** it will run.
- Notice period differs by source: five working days for product tariffs (Standard Terms regulation 9), seven for promotions (End-User Regulations 5(1)), seven business days in Ellipsis' guidance, and a published amendment that shortens promotion notice to five days, with sources disagreeing on when it takes effect. **The notice period is therefore a tenant-level setting (default 7 business days) to confirm against the regulation in force.**
- Separately, licensees report tariffs periodically (Form 5 "Tariff Reporting" under the Compliance Procedure Manual). That recurring report is out of scope here but can read the same product and promotion records.

Design: each launch has a **Product tariff notification**; each promotion has its own **Promotion notification** (with the promotion period). Fields: objectives, reasons, effective date, promotion start/end, date lodged, reference/proof (message ID or sent-mail copy), and ICASA acknowledgement received (optional flag). OmniDome generates the email text from the product record for the user to review and send from the licensee's own mailbox; sending is a separate approval-gated action and the prototype sends nothing. Validation: lodged date + minimum business days ≤ effective date (weekends excluded; public holidays need a calendar in production); promotion end after start; reference present. A product that does not need lodgment (for example a non-telecoms item or internal consumable) records a reason and approver instead. The notification snapshot is retained with the product revision, and an amendment or termination of an active product uses the same flow.

**Promotions** follow the same rule from Pricing & changes: choosing "Introductory promotion" requires objectives, reasons, date lodged, reference and a compliant notice gap before the proposal can be scheduled; the lodgment then appears on the product.

**Launch.** *Launch product* is enabled only when definition, cost completeness, price, internal testing and ICASA lodgment all pass; otherwise it lists exactly what is missing. Launching records actor, time and the evidence set (test results, lodgment reference), sets the effective date to the lodged effective date, and emits `product.published` so the catalogue, portal, billing and inventory sync at that date. It never skips the commercial review role.

### Step 6 — Review and publish

Show product identity, sourcing, all direct costs, linked items, customer charges and projected margin side by side. Highlight unknown costs, negative margins, expired supplier quotes, missing fulfilment configuration, duplicate aliases and required review. Preview an invoice/quote description including the stable product number. Show affected modules and effective date. Actions: Save draft, Submit for review, Publish/Schedule (role-dependent).

Published revisions are immutable. Display author, approver, reason, recorded time and effective time. Editing returns a new revision linked to the old one.

## 4. Profitability definitions

Use decimal currency arithmetic server-side. Compare the same currency, tax basis, quantity and time period. The prototype uses illustrative ZAR amounts **excluding tax**, not verified existing prices or tax assumptions.

| Measure | Definition |
|---|---|
| Recurring unit contribution | Net recurring selling revenue − recurring direct delivery costs, for the same interval |
| Upfront unit contribution | Net once-off customer charges − once-off direct costs, including included hardware |
| Contract contribution | Sum of net revenue across the chosen horizon − sum of direct costs across that horizon, including discounts and one-off items |
| Contract contribution % | Contract contribution / contract net revenue × 100 |
| Equivalent monthly contribution | Contract contribution / horizon in months; explicitly an analytical allocation, not accounting profit recognition |
| Realised gross profit | Net recognised revenue − matched actual COGS for the selected period, including returns/credits and relevant adjustments |
| Margin % | Profit / revenue × 100; N/A when revenue is zero |
| Markup % | Profit / cost × 100; separate from margin; N/A when cost is zero |

Example, using sample data: R799/month, recurring costs R480 access + R35 platform = R515/month; included router R600 + installation R300 = R900 upfront; no setup charge; 24-month horizon.

- Recurring contribution: R284/month, 35.54%.
- Upfront contribution: −R900.
- Contract revenue: R19,176; cost: R13,260; contribution: R5,916, 30.85%.
- Equivalent monthly contribution: R246.50. R37.50/month is the analytical allocation of R900 across 24 months, not an extra cost to charge again.
- A R699 introductory rate for three months reduces contract contribution by R300 to R5,616 (29.75% of R18,876).
- Increasing the recurring cost from R515 to R555 reduces recurring contribution by R40/month. Its effect on an existing cohort depends on the effective date and remaining service months.

Payback may be shown from the cash contribution schedule (including promotional periods); if contribution never becomes positive, display “not recovered within horizon”. Month-to-month products require a user-selected forecast horizon and label it as an assumption, not a guaranteed term.

### Rollups and double counting

- For **realised** category/range totals, sum transaction revenue and matched costs, then compute `(sum revenue − sum cost) / sum revenue`. Never average SKU percentages.
- For **forecast** totals, require a demand scenario: quantities, activation dates, churn/term assumptions, usage drivers and selected commercial versions. Do not sum unit margins from unrelated monthly services and once-off stock and call it portfolio profit.
- Included components can be cost-attributed to the parent offer or analysed separately in a component-consumption view. They must not contribute duplicate revenue or duplicate COGS in consolidated totals. Internal transfer value is not external revenue.
- Internal consumables and company-owned assets show spend, consumption and utilisation. They do not show a misleading sales margin unless there is an actual attributable revenue stream.
- A new supplier quote changes prospective standard cost; historical stock keeps its receipt valuation. Stock valuation, COGS recognition and asset accounting follow the finance-configured policy, with variance reporting against product standard costs.
- Keep projected unit economics, actual gross profit and optional overhead allocation separately labelled. Gross contribution is not net company profit.

## 5. Historical changes and scheduled changes

Every revision needs **effective time** (when it applies commercially) and **recorded time** (when OmniDome learned about it). Use non-overlapping `[valid_from, valid_to)` intervals within a product/price-list/source/component scope. Display local dates and store unambiguous timestamps where time-of-day matters.

Price change flow: choose SKU → new amount → effective date → affected audience/contracts → reason/reference → compare current vs proposed margin → review → schedule/publish. Cost change follows the same flow and additionally selects source/cost component. Promotion creation shows both enrolment and benefit periods. Bulk supplier increases support dry-run results per SKU and parent offer.

Timeline entries show old/new values, delta, status, affected scope, source document, actor/approver, effective date and recorded date. A date picker answers “what was the price, cost and margin on this date?” with the applicable component and promo versions. A separate audit view answers “what did we know at that time?” Backdated corrections are auditable adjustments, not destructive rewrites of issued documents.

Quotes, orders, subscription agreements and invoices retain the selected product ID/number, description, UOM, quantity, price/tax/discount/cost version references and relevant snapshots. Quotes have validity/repricing rules. A historical invoice must render the amounts actually issued, not join today's price. Returns and credits reference the original sale and reverse its matched cost according to policy.

## 6. Proposed data contract

Use the inventory product identity as the initial canonical anchor, exposed through a catalogue API facade; this is a recommendation based on current code, not a completed migration. Billing remains owner of subscriptions, invoices and recognised billing events; inventory remains owner of stock and sourcing; finance remains owner of ledger policy and postings. Product Management owns the definition and commercial revision workflow.

| Record | Important fields / relationships |
|---|---|
| Category, Range | Tenant, stable ID/code, name, effective membership, lifecycle; range belongs to category |
| Product | Tenant, immutable ID/number, range, nature, usage flags, lifecycle, owner; preserve existing `inventory_products.id` |
| ProductDefinitionVersion | Product, descriptions/specifications, service family, UOM/stock/asset settings, effective interval, recorded time, actor and approval |
| ProductAlias | Product, source system, external ID/code; unique per tenant/source |
| ProductSupplier | Product, supplier, supplier code, units/conversion, preferred flag, lead time, MOQ, sourcing scope |
| CostSheetVersion | Product, scenario, currency, completeness, effective interval, approval and source |
| CostLine | Cost sheet, component type, supplier/internal source, quantity/UOM, cadence/driver, amount, tax basis, estimate flag |
| ProductComponentVersion | Parent, child, quantity/UOM, cadence, inclusion charge, ownership/return/fulfilment policy, chosen costing version policy |
| SellingPriceVersion | Product, price list/segment/currency, charge lines and cadence, effective interval, contractual applicability, status |
| PromotionVersion | Target scope, eligibility/enrolment window, benefit duration, price/discount, precedence/stacking, source funding, approval |
| ProductFee | Product, fee type, treatment (charge/included/waived), amount, cadence/trigger, tax code, invoice description, optional policy version; versioned with the selling price |
| ProductAsset | Product, kind (image/gif/3D/document), storage reference, checksum, alt text, order, primary flag, category, version, effective interval, acceptance-required flag, visibility (internal/portal) |
| PolicyLink | Product or fee, policy ID and **version** from the invoice policy library, effective interval; acceptance records live with the order/agreement |
| ProductTestResult | Product revision, test name, result, tester, date, notes/waiver reason, evidence asset reference |
| RegulatoryNotification | Product revision or promotion, regulator (ICASA), kind (product/promotion/amendment/termination), objectives, reasons, effective date, promotion period, lodged date, reference/proof asset, acknowledgement, generated email text, actor; notice-period setting captured at lodgment |
| CompetitorObservation | Product, competitor, offer, price, currency/tax basis, spec, term, source URL/evidence, date checked, actor |
| ProductKpiLink | Product, KPI key, owning module; drives the performance panel and alerts |
| ManagedListValue | Tenant, list (category/range/service family), value, parent, usage count; delete blocked while referenced |
| ProductChange | Product, change type, prior/new version IDs, reason, source document, actor/approver, recorded/effective timestamps |
| LegacyCatalogueMapping | Canonical product ID ↔ billing plan, inventory product, bundle/package, storefront references; never merge based on name alone |
| Transaction product reference | Document line/subscription/stock movement/ticket carries canonical product ID plus necessary immutable commercial snapshots |
| Profitability facts/read models | Product, historical range/category, period, quantity, net revenue, actual costs/variance, source event, currency and calculation basis |

All foreign keys and queries enforce tenant scope; use composite tenant relationships where needed. Product numbers cannot be changed through ordinary PATCH. Database constraints enforce unique identities, valid intervals and valid pricing-rule shapes. Use optimistic concurrency (`revision`/ETag) so two editors cannot silently overwrite a proposal. Reference documents remain under existing access control. Restrict cost and margin visibility separately from ordinary catalogue read access.

Suggested facade endpoints (proposed, not existing):

```
GET/POST /catalogue/products
GET/PATCH /catalogue/products/{id}           # draft definition, expected revision required
GET/POST /catalogue/categories
GET/POST /catalogue/ranges
POST     /catalogue/products/{id}/revisions
POST     /catalogue/products/{id}/cost-revisions
POST     /catalogue/products/{id}/price-revisions
POST     /catalogue/products/{id}/promotions
GET/POST /catalogue/products/{id}/fees
POST     /catalogue/products/{id}/assets             # upload intent → validated, scanned asset
PATCH    /catalogue/products/{id}/assets/{asset_id}  # alt text, order, visibility, version
POST     /catalogue/products/{id}/policy-links
POST     /catalogue/products/{id}/description-suggestions   # AI draft; never auto-applied
GET      /portal/catalogue/products/{id}             # published customer projection
POST     /catalogue/products/{id}/preview    # resolved terms + economics + warnings
GET/POST /catalogue/products/{id}/test-results
GET/POST /catalogue/products/{id}/regulatory-notifications   # ICASA product and promotion lodgments
GET      /catalogue/products/{id}/launch-readiness           # checks + blocking reasons
POST     /catalogue/products/{id}/launch                     # rejected unless all checks pass
POST     /catalogue/products/{id}/publish
POST     /catalogue/products/{id}/archive
DELETE   /catalogue/products/{id}           # unused drafts only; dependency check
GET      /catalogue/products/{id}/history?effective_at=...
GET      /catalogue/products/{id}/usage
GET      /catalogue/profitability?basis=actual&period=...&group_by=range
POST     /catalogue/profitability/scenarios
```

Consumers receive validated price resolutions, not permission to assemble invoice pricing from unrelated tables. Writes and events use an outbox and idempotency keys. Events include tenant, product, immutable revision ID, effective time and event ID. Suggested events: `product.published`, `product.archived`, `product.price_scheduled`, `product.cost_changed`, `product.component_changed`, `promotion.published`. Consumers reject duplicates and apply versions by effective time, not message arrival order. Surface synchronisation errors and retry status.

## 7. Connections to the rest of OmniDome

| Module | Reads from catalogue | Owns / writes back |
|---|---|---|
| Purchasing | Purchasable SKUs, sources, supplier codes, units, expected costs | PO lines, commitments, receipts and supplier invoice/price variances |
| Inventory | Physical definition, UOM, serial/batch/asset rules, components | Quantity, location, reservations, receipt valuation, movements, serials |
| Sales / quotations | Sellable SKUs, resolved price/promo and customer description | Quote snapshots, chosen options and commercial acceptance |
| Billing | Contracted product/version, recurring/usage/once-off charge definitions | Subscriptions, invoice/credit lines, actual billed revenue and status |
| Finance | Product classification and posting references | Ledger, actual COGS, tax/accounting policy, allocations and reconciliation |
| Promotions | Same SKU/range/category identities, margin floor and cost versions | Approved rules, redemption/funding records and realised campaign results |
| Ticketing | Product ID plus installed asset/subscription, entitlement and SLA | Fault/service history and attributable support costs if configured |
| Product development | Existing components, sources, costs, version history | Drafts, evaluations, evidence, owner, review and launch decisions |
| Provisioning | Service specification and provisioning profile/version | Activation outcomes and service/asset identifiers |
| Storefront / customer portal | Published sellable projection: name, description, customer-visible media and documents, enabled fees, linked policy versions, price and availability | Orders/selections and T&C acceptances; never maintains an independently editable product identity |
| Invoices / quotes | Fee lines and their descriptions, linked policy versions, product number | Issued documents with fee and policy snapshots; the policy library stays owned by invoicing |

### Portal synchronisation

The portal reads a **published projection** produced from the product's published revision, not the draft. The projection contains only customer-visible fields: internal costs, margins, supplier data, internal-only documents and unpublished drafts are excluded by construction. Publishing, archiving, fee changes, asset visibility changes and policy-version changes emit events (`product.published`, `product.fee_changed`, `product.asset_changed`, `product.policy_linked`); the portal applies them by effective time, idempotently, and surfaces sync status and retry errors in the product's history. Draft edits and the preview never change what customers see. A portal preview in Product Management renders the same projection function the portal uses, so the author sees what the customer will see.

## 8. Add, edit, delete and retirement

- **New product** is always visible to authorised creators; use the full journey.
- **Edit** opens the definition/commercial draft revision with current values and usage impact.
- **Delete draft** is visible on unused drafts. Confirm the exact product number, check dependencies server-side in the same transaction, and retain the number reservation/audit tombstone so it is never recycled.
- **Archive** is visible for used products. First retire from new sales/purchasing as appropriate; require component/contract dependency review. Existing subscriptions, invoices, returns, stock and tickets keep their references. Outstanding fulfilment and support remain accessible.
- Historical versions cannot be deleted through normal UI. Categories/ranges with products cannot be cascade-deleted. Show what blocks removal and where to resolve it.
- Audit author, reason and affected version for every operation. Permissions distinguish create/edit drafts, view costs, approve commercials, publish, migrate contracts and archive.

## 9. Delivery sequence and acceptance checks

1. **Reconcile identity:** inventory existing plan/product/package records, produce a mapping report, resolve ambiguous duplicates, assign canonical references and retain aliases. Back up and validate counts/references. Do not infer equivalence from display names.
2. **Establish versioned catalogue:** additive migrations, tenant constraints, cost sheets, components, price revisions, audit and published projections. Backfill existing price/cost values with an explicitly known/imported start date; do not invent earlier history. Mark unverifiable costs unknown.
3. **Replace the generic form and table:** deliver the catalogue hierarchy, journey, visible edit/archive/delete, cost completeness, unit economics and timeline. Existing billing endpoints continue through compatibility adapters until cutover.
4. **Connect commercial flows:** quote and invoice snapshots, subscription price policy, purchases and stock component consumption. Reconcile sample orders end to end before enabling live pricing changes.
5. **Enable actual profitability:** reconcile billed/recognised revenue, matched stock/service costs, returns and supplier variances to finance; add weighted category/range rollups with drill-through to source documents.
6. **Enable development and monitoring:** readiness workflow, bulk changes, margin floor alerts and pending sync/change visibility. Agent proposals must pass the same validation, audit and approval roles as human proposals.

Acceptance examples:

- Create a digital fibre SKU including an existing physical router. The router is costed once and appears on the fulfilment requirement; it may show a zero-charge invoice inclusion without losing its cost.
- Change price and supplier cost on different dates. Product number stays unchanged; date-specific preview resolves the correct pair; old invoices retain their original amounts.
- Introduce a three-month promotion with a separate signup window. Quotes explain eligibility, benefit end and subsequent price; overlapping conflicting rules are rejected.
- Compare a contracted existing subscriber and a new signup after a list increase: only the authorised cohort changes.
- Sum SKU financial facts to range/category; overall profit matches the source totals and weighted margin, including credits and returns. Internal component consumption is not counted twice.
- Try to launch with a failed or pending test, a missing lodgment, or a lodgment dated inside the notice period: the Launch button stays disabled and names the gap; the API returns the same reasons. With all gates met, launch succeeds and records the evidence.
- A promotion cannot be scheduled without objectives, reasons, lodged date, reference and compliant notice; its lodgment appears on the product.
- Enable delivery and callout fees on a product: once-off and monthly fees appear on the quote, invoice and portal with their policy version; event fees are disclosed but not forecast. A fee set to Included or Waived bills R0 and keeps its cost.
- Attach a manual and a T&C document marked *Customer portal*: both appear in the portal projection; an *Internal only* document does not. Replacing the T&C creates a new version and leaves accepted agreements on the old one.
- Upload an oversized, wrong-type or malware-flagged file: rejected with a clear message, nothing stored. A digital product cannot be given a gallery; a physical one can have image, GIF and 3D assets with alt text.
- AI description suggestion never overwrites existing text, never states unrecorded specifications, and is auditable.
- Missing costs suppress complete-margin claims; an explicit zero is distinguishable from missing information. Zero revenue produces N/A margin, not infinity.
- A supplier cost increase leaves historical stock receipt value intact and exposes purchase variance; a stock transfer does not create revenue.
- Attempt to delete a used SKU, parent category or included component: preserve history and show dependencies. An unused draft can be deleted without recycling its number.
- Reject cross-tenant references, component cycles, overlapping commercial intervals, invalid unit conversion and stale concurrent edits.
- Loading/saving failures are visible and recoverable. Keyboard-only users can create, inspect and close the form; layouts work at 320, 768, 1024 and 1440px.

## Design assumptions to validate during implementation

Three visible hierarchy levels; service family is a filter. Product number is stable per tenant. Multiple suppliers and sources are supported. Cost amounts are maintained separately from selling prices and taxes. Existing finance rules determine actual valuation and recognition. Contract pricing changes use a separate controlled process. The preview illustrates the design using invented data; all displayed numbers must be replaced with verified records when connected.

## Preview validation and boundaries

The editor now has eight steps (Definition, Sourcing & costs, Included products, Selling price & fees, Media & documents, Research & KPIs, Testing & ICASA, Review). The definition step has the pen/plus/bin controls, the custom product number and the inline AI draft panel; included products are a catalogue dropdown with live thumbnails; the review step and product detail show the performance tiles (illustrative sample values for launched products, "available after launch" otherwise) and the competitor summary. Checked in a browser: adding, renaming and deleting a range, blocked deletion of a used category, custom and duplicate product numbers, AI draft then replace, adding an included product, a competitor row feeding the positioning line, and switching to the direct route.

Launch readiness is in the preview: editor step 6 "Testing & ICASA" (standard test plan, results with tester/date/evidence name, ICASA product and promotion lodgment with notice-period check and an email draft), a launch-requirements card with the **Launch product** button on the Review step, launch-check counts in Development, and ICASA fields in the promotion proposal dialog. Checked in a browser: the button stayed disabled while costs were incomplete or the lodgment was inside the notice period, and launching succeeded once all gates passed. The ICASA text is a draft only; no official form was available to reproduce and nothing is sent. Business days exclude weekends only.

The preview is now a single self-contained HTML file. It includes the media gallery (images, GIFs, 3D attachment placeholders), a demo-only *Suggest description* assistant (no model connected), the fee list with enable toggles, illustrative fee-policy/T&C references (invented placeholders, not legal terms), document attachments with internal/portal visibility, and a *Portal preview* tab showing the customer projection. Attachments stay in the browser session and nothing is uploaded. It was checked in a browser over a local server: no console errors, all six editor steps render, and the portal tab renders for published sample products.

JavaScript syntax and all five work-area rendering functions, all five editor steps and product-detail rendering passed local checks with a minimal document stub. Calculation checks covered R515 recurring cost, R900 upfront cost, R5,916 contract contribution, unknown costs, zero-revenue margin, included-component quantities, introductory promotion impact, supplier-cost impact, date-specific published prices and dependency protection for an included router.

These are logic checks, not browser or accessibility tests. Browser security policy rejected automatic navigation to the local HTML file, so visual rendering, responsive layouts, focus handling and keyboard operation have not been verified in a browser. Open the companion HTML manually to explore the design. No live service or database was modified.

The prototype deliberately illustrates a subset of the full specification: primary usage rather than multiple usage flags; monthly or once-off charges rather than usage tariffs; a simple single-currency cost sheet; one-time included items; a fixed published sample timeline for the first fibre SKU; and session-only draft/change proposals. Category/range administration, full supplier records, actual finance facts, publish approvals, revision editing and module synchronisation remain specified production work. It must not be used to issue commercial documents.

## Implementation status (17 October 2026)

Built and verified: the Products portal module now has Overview, Pricing and Catalogue tabs (Products and Bundles removed). The Catalogue tab holds the Product Directory (grid and table, with pictures), Development lanes, the eight-step journey and the product detail view. The backend is part of the inventory service (`/catalogue`): products with optimistic concurrency, managed category/range/family lists, server-assigned or custom product numbers (never reused), asset upload with content sniffing, a history log, a preview endpoint that returns the same launch checks as launch itself, and a launch endpoint that refuses unless every gate passes. Launch publishes `product.published` on the event bus. Product knowledge cards (no costs, suppliers or margins) are indexed for RAG and were verified end to end against the local embedding model and pgvector.

Not built yet: revisions of launched products (price and cost changes, promotions as overlays), legacy billing-plan and inventory-product mapping, portal sync consumer, live KPI feeds, finance actuals, object storage for files, per-tenant ICASA notice setting and public-holiday calendar, and an LLM-backed description assistant and competitor research.
