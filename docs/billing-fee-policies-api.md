# Billing: early-termination / claw-back fee engine API

Service: billing (port 8003), all paths below are relative to it (via the web proxy: `/svc/billing/...`).
Money is a **decimal string** in ZAR (`"2012.50"`), dates are ISO `YYYY-MM-DD`. Every call is tenant-scoped by the signed identity.

## Concepts

| Thing | What it is |
|---|---|
| **Fee policy** | Per-tenant, versioned rules: term, recoverable components, amortisation method, caps, grace, waivers, router credit, VAT. Editing creates version N+1; old calculations keep pointing at the version they used. |
| **Contract snapshot** | Immutable record of what a customer's contract cost to set up (router, activation, installation, term start/length, monthly rental). Written when the subscription is created (if a policy has fixed/catalog amounts) or via `POST /fee-policies/snapshots`. Later price changes never alter it. The snapshot always wins over policy amounts. |
| **Calculation** | Immutable engine run (inputs, `inputs_hash`, full breakdown). Only waiver/invoice/supersede bookkeeping changes. Idempotent on `(tenant, trigger, subject, effective_date, inputs_hash)`. |
| **Triggers** | `cancellation`, `downgrade`, `plan_change`, `relocation`, `suspension_abuse`, `device_buyout`, or any lowercase slug (custom). |

### Roles (billing tiers)
`reader` read/simulate - `clerk` (manager, billing_clerk...) calculate, snapshots, invoice, waive small - `admin` (billing_admin, finance, admin, owner...) policy CRUD, template, large/custom waivers.

### Worked example (the canonical one)
Router R1500 + activation R500 + installation R1000, 24-month term, cancel after 10 whole months, VAT 15% exclusive:

| Component | Total | /month | Remaining | Owed |
|---|---|---|---|---|
| Router | 1500.00 | 62.50 | 14 | 875.00 |
| Activation | 500.00 | 20.83 | 14 | 291.67 |
| Installation | 1000.00 | 41.67 | 14 | 583.33 |
| **Net** | | | | **1750.00** |
| VAT | | | | 262.50 |
| **Total** | | | | **2012.50** |

Router returned in good condition with `router_credit.mode = offset_router_component`: router line is credited, net 875.00, total 1006.25.

## Policy shape (`POST /fee-policies`, `PUT /fee-policies/{id}`)

```json
{
  "name": "Standard 24-month claw-back",
  "description": null,
  "trigger_types": ["cancellation", "downgrade"],
  "applies_to_plans": [],                 // plan ids or names; [] = every plan. Plan-specific beats generic, default beats non-default.
  "is_default": true, "is_active": true,
  "effective_from": "2026-10-01", "effective_to": null,
  "term_months": 24,
  "components": [
    {"code": "router", "label": "Router", "amount_source": "snapshot", "fixed_amount": null, "recoverable": true}
  ],                                      // amount_source = fallback when there is no snapshot: snapshot | fixed | catalog
  "method": "straight_line",              // straight_line | declining (sum-of-digits) | flat | percent_of_remaining_rental
  "flat_percent": "100", "rental_percent": "100",
  "month_rule": {"mode": "whole_months", "remaining_rounding": "up"},
                                          // whole_months: a started month counts as remaining (up) or elapsed (down)
                                          // prorated_days: fractional month by days
  "min_fee_zar": null, "max_fee_zar": null,
  "grace_period_days": 7,                 // cooling-off after term start: whole fee waived
  "waivers": [{"reason_code": "fno_fault", "label": "...", "waive_percent": "100", "required_tier": "none|clerk|admin", "evidence_required": false}],
  "auto_approve_waiver_limit_zar": "200.00", "allow_self_approval": false,
  "router_credit": {"enabled": true, "mode": "offset_router_component|credit_value_by_condition",
                    "router_component_code": "router",
                    "condition_pct": {"new":"100","good":"90","fair":"60","damaged":"25","missing_parts":"0"}},
  "vat": {"rate": "0.15", "treatment": "exclusive|inclusive"},
  "outstanding_balance": "include|exclude",   // include = shown in total_payable; never put on the fee invoice
  "auto_invoice": false, "auto_invoice_stage": "proceed|initiate", "invoice_due_days": 14,
  "catalog_amounts": {"router": {"Fibre 100": "800", "default": "600"}}
}
```
Response = the same fields plus `id`, `policy_key` (stable across versions), `version`, `superseded_by`, `created_at`.

## Endpoints

### Policies
| Method | Path | Tier | Notes |
|---|---|---|---|
| POST | `/fee-policies` | admin | 201 |
| GET | `/fee-policies?active_only=&trigger=&current_only=true` | reader | latest versions |
| GET | `/fee-policies/{id}` / `/{id}/versions` | reader | |
| PUT | `/fee-policies/{id}` | admin | creates a new version, closes the old one the day before |
| DELETE | `/fee-policies/{id}` | admin | soft: deactivates all versions |
| POST | `/fee-policies/templates/default-24m` | admin | creates the standard policy only when called (409 if already there). Components are `snapshot`-sourced: no amounts are invented. |
| GET | `/fee-policies/audit?entity_type=&entity_id=` | reader | append-only audit trail (policy, snapshot, calculation) |

### Snapshots
`POST /fee-policies/snapshots` (clerk/manager, audited)
```json
{"subscription_id": "...", "term_start": "2026-01-15", "term_months": 24,
 "components": [{"code":"router","amount":"1500","discount":"0"}, {"code":"activation","amount":"500"}, {"code":"installation","amount":"1000"}],
 "monthly_rental_zar": "699.00", "policy_id": null, "backfill": true, "supersede": false, "notes": "..."}
```
Defaults: `term_start` = subscription billing anchor, `term_months` = applicable policy term, rental = subscription base price. 409 if one exists unless `supersede: true` (adds version N+1; earlier versions kept, `is_current=false`).
`GET /fee-policies/snapshots?subscription_id=&all_versions=false`.
Automatic: creating a subscription (`POST /subscriptions`, `/subscriptions/prorated`) writes a snapshot from the policy's fixed/catalog amounts when an applicable policy has any (silent no-op otherwise). Without a snapshot the engine flags `snapshot_missing`.

### Simulate (persists nothing; works for downgrade/plan-change too)
`POST /fee-policies/simulate` (reader)
```json
{"subscription_id": "...", "trigger": "downgrade", "effective_date": "2026-11-15",
 "reason_code": "relocation_in_coverage", "router_returned": true, "router_condition": "good"}
```
or `{"snapshot": {"term_start","term_months","components":[...],"monthly_rental_zar","plan_name"}, ...}` for what-if inputs, or add `"policy": {...PolicyIn}` / `"policy_id"` to try an unsaved/specific policy. 404 when no policy applies.

Response:
```json
{"persisted": false, "policy": {"id","policy_key","version","name"}, "snapshot_id": "...|null", "snapshot_missing": false,
 "inputs_hash": "sha256", "inputs": {...}, "flags": ["..."],
 "breakdown": {
   "term_months": 24, "months_elapsed": "10", "months_remaining": "14", "method": "straight_line",
   "lines": [{"code":"router","label":"Router","kind":"component","total_amount":"1500.00","monthly_amortisation":"62.50",
              "months_elapsed":"10","months_remaining":"14","unamortised_fraction":"0.5833...","amount":"875.00",
              "net":"875.00","vat":"131.25","gross":"1006.25","source":"snapshot","recoverable":true,
              "formula":"1500.00 x 14/24 = 875.00"}],
   "totals": {"fee_net":"1750.00","fee_vat":"262.50","fee_total":"2012.50","waived_total":"0.00",
              "total_before_waiver":"2012.50","outstanding_balance":"0.00","total_payable":"2012.50"},
   "router_credit": {...}, "waiver_eligibility": [{"reason_code","required_tier","indicative_gross","applied"}],
   "formula": "Router: 1500.00 x 14/24 = 875.00; ...; Subtotal 1750.00 + VAT 262.50 = 2012.50"}}
```
`line.kind`: `component`, `router_credit` (negative), `cap_adjustment`/`min_adjustment`, `waiver` (negative, `reason_code`, `applied_by`).
Flags seen: `snapshot_missing`, `term_completed`, `max_fee_applied`, `min_fee_applied`, `grace_period_applied`, `waiver_applied_<code>`, `component_<code>_not_in_snapshot_used_fixed|catalog`, `component_<code>_amount_unresolved`, `router_condition_unknown_no_credit`, `effective_before_term_start`.

### Calculations
- `POST /fee-policies/calculate` (clerk): body = simulate's subscription fields + optional `cancellation_id`, `policy_id`. Returns the stored calculation plus `created` (false on an idempotent repeat). A different input set for the same subject supersedes the older un-invoiced row (status `superseded`).
- `GET /fee-policies/calculations?subscription_id=|customer_id=|cancellation_id=&include_superseded=false`
- `GET /fee-policies/calculations/{id}`
  Fields: `status` (`calculated|waived|invoiced|superseded`), `fee_net_zar`, `fee_vat_zar`, `fee_total_zar` and `amount_due_zar` (gross after waivers), `waived_total_zar`, `waivers[]`, `invoice_id`, `invoice_number`, `breakdown`, `flags`, `inputs`, `inputs_hash`, `policy_id`, `policy_version`, `auto_calculated`.
- `POST /fee-policies/calculations/{id}/waive` (clerk; admin where required)
  ```json
  {"reason_code": "relocation_in_coverage", "reason": "free text, required", "percent": "50"}   // or "amount_zar": "150.00" (gross)
  ```
  Approval rules: a clerk may waive up to `auto_approve_waiver_limit_zar` for reason codes whose rule tier is `none|clerk`; anything above the limit, a rule tier of `admin`, or an unlisted/custom reason needs an admin (403 otherwise). Above the limit you cannot waive a fee you calculated yourself (403) unless the policy sets `allow_self_approval`. 400 invalid amount, 409 already invoiced/superseded. Returns `{waiver, calculation}`.
- `POST /fee-policies/calculations/{id}/invoice` (clerk), optional body `{"issue": true|false}` (default: the policy's `auto_invoice`; true = issued `sent` + ledger entry queued through the finance outbox + dunning, false = `draft`).
  Creates one invoice with one `invoice_lines` row per component/adjustment/waiver (`line_type: "termination_fee"`; invoice `line_items[].type = "termination_fee"` and notes carry the calculation and policy version). Idempotent: repeat returns `created:false`. 409 when nothing is due or the subject was already invoiced via another calculation.
  Response: `{created, invoice_id, invoice_number, status, subtotal_zar, vat_zar, total_zar, invoice_type:"termination_fee", calculation_id, cancellation_request_id}`.

## Cancellation flow changes (`/cancellations/...`)

- `POST /cancellations/initiate` now auto-runs the engine (no human step) and returns `fee_calculation_id`, `fee_total_zar`, `fee_amount_due_zar` (null when the tenant has no policy). The reason code is `cancel_reason` if it is a slug (e.g. `fno_fault`), else `cancel_type`. If the policy has `auto_invoice` and `auto_invoice_stage: "initiate"` (and no retention offer is pending) it is invoiced and issued immediately.
- `POST /cancellations/{id}/calculate-etf` (optional body `{"reason_code"}`) uses the engine. Response keeps the legacy fields (`contract_etf_zar`, `router_charge_zar`, `total_etf_zar`, all ex-VAT) and adds `engine` (`"policy"` or `"legacy"`), `calculation_id`, `policy_id`, `policy_version`, `fee_net_zar`, `fee_vat_zar`, `fee_total_zar`, `amount_due_zar`, `flags`, `breakdown`. `engine: "legacy"` + `flags: ["legacy_no_policy"]` means the tenant has no applicable policy and the old hardcoded tiers were used: create a policy.
- `POST /cancellations/router-returns/{id}/inspect` recalculates with the inspected condition (router credit per policy). Response adds `fee_update`: `{mode:"recalculated", amount_due_zar}` or, if the fee is already invoiced (never mutated), `{mode:"invoiced_no_change", credit_note_required_zar}`.
- `POST /cancellations/{id}/proceed` invoices the engine fee (issued if `auto_invoice`, else draft; idempotent); response adds `fee_invoice`.
- `GET /cancellations/{id}/status` adds `fee_calculation` (full calculation + breakdown) and `fee_engine` (`policy|legacy|null`). The legacy `termination_fee` block is kept in sync (amounts ex-VAT).

## Tables
`fee_policies`, `contract_fee_snapshots`, `fee_calculations`, `fee_audit_events` (created by billing `init_tables` / `AUTO_CREATE_TABLES`; no changes to existing tables).

## Not covered
The downgrade/plan-change flows themselves (only `simulate`/`calculate` with that trigger); credit notes for fees already invoiced when a router is later returned (the amount is reported, not issued); `percent_of_remaining_rental` ignores components.
