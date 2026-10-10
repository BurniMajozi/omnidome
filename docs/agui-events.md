# Live agent activity

Both `POST /api/protocols/ag-ui/run` (the web chat) and `POST /api/agents/invoke/stream` emit SSE frames with the existing AGUI envelope. Live activity uses `type: CUSTOM` and `data: {name, value}`.

| Event name | Value |
|---|---|
| `omnidome.step` | `id`, `kind`, `title`, `status` (`running`, `done`, `error`), timestamps, `duration_ms`, `result_summary`; reserved `detail` and `meta` are currently empty |
| `omnidome.status` | Current phase text and `elapsed_ms`; sent on step start and every three seconds |
| `omnidome.question` | `run_id`, `question_id`, one to three questions (header, question, two to four labelled options, optional multi_select), expires_at, ttl_seconds=1800 |
| `omnidome.question_resolved` | run_id, question_id, status (`answered`, `expired`, `cancelled`) |
| `omnidome.approval` | approval_id, reference, tool, generic summary, requested_by_me=true, status=pending, risk |

Replace a step by id and preserve arrival order. Ignore unknown custom events. React text rendering is required. Public summaries redact emails, token patterns and long number sequences; they never include model reasoning, system prompts or tool arguments.

Preparation emits skill selection, memory recall and company RAG retrieval before the first model call. Further steps show model activity, governed data queries, tools and verification. RAG status is reported honestly; retrieval failure does not become invented evidence. The grounding timeout defaults to 30 seconds to accommodate local Ollama embeddings.

Clarification answers use `POST /api/agents/runs/{run_id}/answer`:

```json
{"question_id":"uuid","answers":[{"question":"Which period?","selected":["Month"],"other":null}]}
```

Answers are validated against the displayed questions, saved in `agent_pending_questions` and polled by the waiting worker. Only the signed user who owns the run, in the same tenant, can answer. Expired, cancelled and already answered questions are rejected. Disconnecting cancels the native agent task and closes its pending question.

Clarification is never approval. Existing approval endpoints retain their approver-role and no-self-approval gates. A gated action ends the turn awaiting human review; it does not keep a live task paused for approval. The requester sees an inline waiting card. Existing approval management remains the decision surface for managers.

The web chat shows collapsible activity, elapsed time, clarification choices with free text and a Stop action. Live activity is transient; conversation messages remain persisted. Hermes chat does not currently emit the native per-step events.

`data.datasets` discovers panel-authorised datasets. `data.query` accepts governed specs only: aggregate mode for exact counts/totals, or list mode for registered columns with a hard 200-row cap and matching_rows total. No raw SQL is accepted. Provider tool names such as data_query are resolved to registered names before checking the agent allow-list.

The knowledge `capabilities` snapshot source indexes dataset columns and tool policy metadata. Its cards contain no customer rows. Run an administrator reindex of that source after deploying registry changes.
