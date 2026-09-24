# Spec: lead-actions (action menu + lead record panel)

Module of `CAPABILITY-MAP-sales-lifecycle.md`. Build order 3 of 4.

## Objective

From any lead row, a ⋯ menu (and right-click) offers the next steps a sales
person takes, like the message menu in Communication. Every action is recorded
on the lead's timeline; anything that talks to another service goes through the
event bus so it cannot block or be lost.

## Actions

| Action | Effect | Cross-service |
|---|---|---|
| Open record | Slide-over: details, owner, dates, deal, tasks, timeline | — |
| Assign owner | Pick an HR employee; `agent_id` + `owner_name` | notification |
| Add note / log call | Timeline entry | — |
| Send email | Compose to the lead's email | `sales.lead.email_requested` → sales consumer sends via AgentMail; timeline shows queued → sent / failed |
| Create task | Title, due date, assignee; listed on the record | notification to assignee |
| Escalate | Reason; priority → urgent, `escalated_at` | critical notification; `sales.lead.escalated` |
| Send to outbound agent | Creates a call task in the "Outbound queue" | `sales.lead.outbound_requested` (orchestrator workflows can pick it up, e.g. an AI voice agent later) |
| Send to marketing campaign | Pick a real marketing campaign | `sales.lead.campaign_requested` → sales consumer upserts the campaign's "Sales leads" audience in Marketing (one audience per campaign, full member list, so retries are idempotent) |
| Move stage / Mark lost | Same rules as `lead-lifecycle` | — |

## API (sales)

`POST /leads/{id}/assign {owner_id, owner_name}` · `POST /leads/{id}/notes {body, kind?}` ·
`POST /leads/{id}/email {subject, body}` (400 when the lead has no email) ·
`POST /leads/{id}/tasks {title, due_at?, assignee_*?, kind?}` · `GET /leads/{id}/tasks` ·
`PATCH /lead-tasks/{id} {status}` · `POST /leads/{id}/escalate {reason}` ·
`POST /leads/{id}/outbound {notes?}` · `POST /leads/{id}/campaign {campaign_id, campaign_name}` ·
`GET /leads/{id}/activities`.

Sales runs an `EventConsumer("sales")` for `sales.lead.email_requested` and
`sales.lead.campaign_requested`. Email is guarded by the event id so a retry
never sends twice once the provider accepted it.

## Safety

Email goes to real people. Tests send only to the tenant's own AgentMail inbox.
Automations never send customer messages on their own; they draft them for a
person to send (see `SPEC-lead-automations.md`).

## Success criteria

- [x] Every action appears on the timeline with who/when.
- [x] With Marketing stopped, "Send to campaign" still returns at once; the
      delivery retries and completes when Marketing is back.
- [x] Email to the own inbox arrives; a provider failure shows on the timeline
      and in the bell.
- [x] Menu + panel match the Communication pattern (dropdown + right slide-over).
