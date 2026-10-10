# Agent stream: live activity, questions, approvals (AG-UI CUSTOM events)

Endpoints that stream: `POST /api/agents/invoke/stream` and `POST /api/protocols/ag-ui/run` (web chat). SSE frames:
`data: {"type", "run_id", "tenant_id", "conversation_id", "timestamp", "data"}`.

Unchanged events: `RUN_STARTED`, `TOOL_CALL_START|RESULT|END` (sent after the agent finishes, one triple per tool call),
`TEXT_MESSAGE_CONTENT`, `RUN_FINISHED`, `RUN_ERROR`. New: `type:"CUSTOM"` with `data = {"name": "<event>", "value": {...}}`.
Clients must ignore unknown CUSTOM names. CUSTOM events arrive live, before the first `TEXT_MESSAGE_CONTENT`.
All strings are redacted (emails, bearer/token patterns, long digit runs) and clipped to 700 chars; render as text, never HTML.
Hermes chat (`chat_backend=hermes`) does not emit these events: the UI must work with none.

## `omnidome.step`
Same `id` is sent twice (`running`, then `done|error`): upsert by id, keep arrival order.
```json
{"id":"s_1a2b3c4d5e","kind":"skill|memory|knowledge|reasoning|data|tool|verify|approval","title":"Querying governed data",
 "detail":"","status":"running|done|error","started_at":"ISO","ended_at":null,"duration_ms":null,
 "result_summary":null,"meta":{}}
```
`detail` and `meta` are currently always empty (reserved). Titles emitted today: `Choosing skills`, `Recalling team memory`,
`Searching company memory (RAG)` (summary e.g. `ready: 2 source cards`), `Preparing the next step` (each model call),
`Listing available datasets`, `Querying governed data` (summary `N rows`), `Searching company knowledge`,
`Running an approved tool`, `Waiting for your answer` (kind `approval`, stays running until the question closes),
`Checking the answer` (verifier). A failed tool ends with `status:"error"`, summary `Could not complete this step`.

## `omnidome.status`
`{"text":"Still working: querying governed data (6s)","elapsed_ms":6120}`. Sent on each step start and every 3 s while
the run works. Replace the previous status line, do not append.

## `omnidome.thinking`
Not emitted (no safe reasoning summary is available). Reserved name; ignore.

## `omnidome.question` (agent asks the user, via the `ask_user` tool)
```json
{"run_id":"uuid","question_id":"uuid","questions":[{"header":"<=12 chars","question":"...",
  "options":[{"label":"..","description":".."}],"multi_select":false}],"expires_at":"ISO","ttl_seconds":1800}
```
1-3 questions, 2-4 options each (unique labels). Free text ("Other") is always allowed via `other`. The run is paused
(worker polls the durable record) for up to 30 min. Keep the stream open. Answer with:

`POST /api/agents/runs/{run_id}/answer`
```json
{"question_id":"uuid","answers":[{"question":"<exact question text, one per question, same order>","selected":["Label"],"other":null}]}
```
Each answer needs at least one `selected` label (must exist; max 1 unless `multi_select`) or non-empty `other` (<=500 chars).
Responses: `200 {"ok":true}`; `403` caller is not the run's owner; `404` unknown run/question, other tenant, expired or
cancelled; `409` already answered; `422` invalid answers. Answers reach the model as the tool result (user input).
A clarification answer is never an approval.

Then: `omnidome.question_resolved` `{"run_id","question_id","status":"answered|expired|cancelled"}`. On `expired` the
agent is told not to assume an answer. Closing the stream cancels the run and the question.

## `omnidome.approval`
Emitted when a mutating tool is held by the existing approval gate (the turn then ends `awaiting_hitl`; the run is NOT
paused).
```json
{"approval_id":"uuid","reference":"APR-..","tool":"support_create_ticket","summary":"This action requires a manager's approval",
 "requested_by_me":true,"status":"pending","risk":"review|<jev risk level>"}
```
Show an inline "waiting for a manager" card. Decisions use the existing endpoints unchanged (`/api/approvals/{id}/approve`
`{notes}` and `/reject` `{reason}`; manager/admin/executive/owner or `agents.approve`; requesters cannot approve their own
request). `GET /api/approvals/{id}` for status. Args preview and JEV probabilities are NOT in the event: fetch the approval.

## Governed data (what the agent can now answer)
Tools: `data.datasets` (datasets and allowed columns for the caller's panels; restricted ones listed with the panel name)
and `data.query` (maps to `GET /api/fno/bi/datasets`, `POST /api/fno/bi/query`, signed with tenant/user/roles). No raw SQL
tool exists in the registry. A dataset in a panel the user lacks returns 403 `Access to the <Panel> panel is required for this dataset`.
List mode (`mode:"list"`): registered columns only (no email/phone/ID/address/names/free text), tenant-scoped, text filters
case-insensitive, hard cap 200 rows, `totals.matching_rows` = exact match count. Datasets with list mode: `sales_pipeline`,
`sales_leads`, `billing_invoices`, `support_tickets`.

"Open deals older than 14 days":
```json
{"dataset":"sales_pipeline","mode":"list",
 "columns":["name","stage","value_zar","created_at","age_days"],
 "filters":[{"field":"status","op":"eq","value":"OPEN"},{"field":"age_days","op":"gt","value":14}],
 "order_by":[{"field":"age_days","dir":"desc"}],"limit":50}
```
Capability cards (knowledge source `capabilities`, snapshot) describe datasets (measures, dimensions, list columns) and
tool policies, without customer rows; reindex that source after registry changes.
