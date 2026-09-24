# Spec: lead-lifecycle (one stage model, lead record, board sync)

Module of `CAPABILITY-MAP-sales-lifecycle.md`. Build order 2 of 4. Depends on `event-bus`.

## Objective

A lead is one record with one stage, whichever screen changes it. Sales people
see who owns it, its reference number and when it was created, last changed and
closed. Leads added from Lead sources (companies, tenders/RFQs) appear on the
Pipeline Board straight away.

## The stage model (answers "should Adjust Stage update the board?" — yes)

A lead lives in two phases:

```
Lead phase (lead table only)          Pipeline phase (lead has a deal on the board)
NEW → CONTACTED → QUALIFIED   ──►     Prospecting → Qualified → Proposal → Negotiation → Closed Won
        │                                                                              └► Closed Lost
        └► DISQUALIFIED (closed)
```

- **Before a deal exists** the lead's own status is the stage (NEW, CONTACTED,
  QUALIFIED, DISQUALIFIED).
- **Once a deal exists the deal's stage is the single source of truth.** The lead
  table's stage dropdown shows the board stages for it; changing it moves the
  deal (same call the board makes), and dragging the card on the board updates
  the lead. Lead status then mirrors the deal: `CONVERTED` while open (kept for
  the field app, shown as "In pipeline"), `WON`, `LOST`.
- Choosing a board stage for a lead with no deal creates the deal at that stage
  ("Convert to Deal" is the same thing at Prospecting).
- A lead in the pipeline cannot go back to NEW/CONTACTED/QUALIFIED (the deal
  would be orphaned); the UI disables those options and the API returns 409.
- Closed Won / Closed Lost go through the existing close-won (commission,
  finance, lifecycle bridges) and close-lost (reason required) paths.
- Old free-form lead statuses PROPOSAL/NEGOTIATION with no deal migrate to
  QUALIFIED; CONVERTED leads whose deal is won/lost become WON/LOST.

Pure module `services/sales/lead_stages.py` decides the transition
(`plan_stage_change`) so the rules are unit-tested without a database.

## Lead record

New `leads` columns (idempotent `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`):
`ref_no` (per-tenant sequence, shown as `LD-000042`, unique per tenant, backfilled
by created date), `owner_id` + `owner_name` (an HR employee; `agent_id` has a foreign key to
login `users` and stays the logged-in sales agent), `priority`
(low/normal/high/urgent, default normal), `closed_at`, `close_reason`,
`escalated_at`.

New tables: `lead_activities` (timeline: kind, summary, details jsonb, actor,
created_at) and `lead_tasks` (title, kind task/call, due_at, assignee, status
open/done, completed_at).

`LeadResponse` gains `reference, owner_name, priority, closed_at, close_reason,
escalated_at, deal_id, deal_stage, deal_value_zar, deal_status, open_tasks`.

Owners come from HR `employees` (the only populated directory locally), read
directly from the shared DB by `GET /owners`; an empty list if HR's table is
absent.

## API (sales; web path `/api/sales/...`)

| Method | Path | |
|---|---|---|
| POST | `/leads` | + `owner_*`, `priority`, `pipeline: {stage_name, value_zar}` → lead and deal created together |
| GET | `/leads/{id}` | record + activities + tasks |
| POST | `/leads/{id}/stage` | `{status}` or `{stage_name, value_zar?, reason?}`; one transaction |
| PUT | `/leads/{id}` | field edits; a `status` goes through the same rules |
| POST | `/leads/{id}/convert` | unchanged contract; now also uses the rules and records activity |
| GET | `/owners` | `[{id, name, department, job_title}]` |
| deals | `PUT /deals/{id}/stage`, `PUT /deals/{id}`, close-won, close-lost | now update the linked lead + timeline |

Every change writes a `lead_activities` row and publishes `sales.lead.created`,
`sales.lead.stage_changed` or `sales.deal.stage_changed` / `sales.deal.won` /
`sales.deal.lost` on the event bus (so automations can react).

## Web

- Lead table: Reference, Owner, Created / Modified / Closed columns; stage
  dropdown with two groups ("Lead" and "Pipeline board"); a lead in the pipeline
  shows its deal stage; value prompt only when a deal is created.
- "Add as lead" (companies) and "Add to pipeline" (tenders) create the lead with
  `pipeline: {stage_name: "Prospecting"}` → the card appears on the board.
- The "+ Create Deal / Lead" modal creates one linked lead+deal (it used to make
  two unrelated records).
- Board cards show the lead reference and owner.

## Testing

- Unit: `services/sales/tests/test_lead_stages.py` (transition rules, reference
  format, deal→lead status). Run: `cd services/sales && ../../.venv/Scripts/python.exe -m pytest tests -q`.
- Live: add a company as a lead → card on the board; move it on the board → lead
  table shows the new stage; change it in the table → board moves; close lost
  from the table requires a reason; timeline lists every step.

## Boundaries

- Always: tenant-scope every query; keep `/leads/{id}/convert` and the lead list
  shape backward compatible (field-sales app uses them).
- Never: delete a deal to move a lead backwards.

## Success criteria

- [ ] Company/tender "add" lands on the board in Prospecting.
- [ ] Table and board always agree on a lead's stage.
- [ ] Reference, owner, created/modified/closed shown for every lead.
- [ ] Unit tests green; existing sales tests still green.
