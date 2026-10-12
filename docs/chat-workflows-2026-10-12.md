# Chat workflows and automation designer

## Journey and design contract

The supplied references show a named workflow picker, clear attachment controls and workflow cards within a conversation. OmniDome uses those interaction patterns with its existing Button, Dialog, Input and semantic colour tokens. The picker supports search, selection, loading, empty and error states, a keyboard-accessible dialog and a bounded scrolling list. Attached cards show text status and explicit Run controls; nothing runs on a new message. On narrow screens the workflow editor stacks its sidebar and editor.

Chat attachments belong to the saved conversation. They never toggle a workflow's event or schedule activation. Detaching removes the association, not an already requested/running execution. The editor keeps an explicit Draft/Active selector. Saving an active workflow with an event or enabled schedule affects its background execution, independently of chat.

## Implementation

- Chat header: Workflows button beside History/New; searchable picker with checkboxes and an Attach action.
- Attached workflow cards: Run, review frozen steps/inputs, Approve & run (existing manager/admin approval gate), execution status, step results and a link to the editor.
- An empty chat can be created and owned before its first message. Attachments persist server-side and reappear when loading chat history.
- Run uses stored recent user/assistant messages as input, `input.message` and `input.chat.messages`. User-supplied identity/transcript fields cannot replace verified identity or stored conversation context.
- Approval freezes the saved workflow graph; changing that graph requires a new approval. The gate executes a claimed approval at most once. Duplicate request keys return the original approval; a conversation row lock prevents double-clicks/concurrent requests from creating two pending executions of the same attached workflow.
- The approval/run result is read from the database. Pending/running state is polled while this chat is open. Awaiting step approvals resume through the existing workflow continuation path.
- Workflow editor: describe an automation, get a proposed graph, refine it using chat, review and save. Proposals—including revisions of an existing active workflow—are new unsaved drafts. The original active workflow is unaffected. Explicit activation remains a separate visible selection/save.
- Designer uses the existing Agent/Llama-wrapper turn, including tenant memory/RAG and commercial usage accounting, with no executable tools exposed. Generated agent nodes remain read-only/draft-only. Notifications are private tenant-owner notifications. Direct HTTP actions are intentionally rejected in generated proposals and must be configured by a tenant admin.
- Graph validation bounds node/edge counts and identifiers, requires one trigger and an end, rejects disconnected/cyclic graphs and unsupported parallel execution, and checks both condition branches. Unknown events are removed with a publisher warning. Suggested cron schedules use UTC and remain disabled.
- Workflow editing/designing requires a tenant admin; ordinary conversation owners can attach existing tenant workflows and request an approved execution.

## How to use it

1. Refresh the local web app. Open Agent Chat and choose **Workflows** beside History/New.
2. Search and tick existing workflows, then **Attach**. Choose **Run** on an attached active workflow, inspect its frozen steps/inputs, and use **Approve & run** if you have a manager/admin role. Ordinary staff can request execution; an approver can review it in the existing approval inbox.
3. For a new automation, open **Admin → Workflows**, type a brief in **Describe your automation**, and choose **Design workflow**. The chart shows the proposal. Continue typing to refine it, including a request to change only a named step.
4. Review the chart, proposed event and UTC schedule, then **Save draft**. To enable background triggers, explicitly select **Active**, enable a schedule if needed, and save. The chat picker then lists that saved workflow.
5. If a running agent step requires a further approval, review it in **Admin → Agents**. The existing continuation resumes after the approved action; do not start a second run to continue the first.

## Validation and deployment

Deployed locally on 12 October 2026. Web rollback tag: `omnidome-chat-web:before-20261012143509`; final orchestrator rollback tag: `omnidome-chat-agent-orchestrator:before-20261012144137`. Only web and orchestrator were recreated. The memory service and other platform services were left running. No WSL restart was used.

- 56 checks passed across the designer, PostgreSQL conversation ownership/concurrent requests, existing workflow continuation, provider fallback and JSON-repair suites. PostgreSQL tests also exercise detach/reattach and the approved-before-execution interval.
- A designer regression confirms both team-memory and company-RAG recall before a model call, with an empty executable-tool list. Provider tests confirm structured JSON format reaches both Ollama and OpenRouter. The brief leads the retrieval query so the schema does not crowd it out.
- Web source type check passed using a temporary configuration excluding only stale `.next/dev` harness imports; the temporary file was removed. The normal check still has two pre-existing missing deck-harness module errors. Production Next.js build passed.
- Live HTTP checks passed: attachment tables ready, workflow list, private conversation lookup, design input validation, staff denied design access, anonymous denied access and workflow page HTTP 200.
- Final hybrid company-memory recall returned three knowledge hits with no configuration/error note. Tenant-owner billing usage, logs, invoices and delivery-controls endpoints still passed; credit pricing was unchanged. The local watchdog is active.
- A real live model turn returned HTTP 200 and a valid four-node draft: trigger → agent draft → private owner notification → end, with `platform.billing.credits.low`. It remained unsaved/inactive. No workflow, approval, notification, email or payment was created by that check; normal agent memory/usage telemetry was recorded.
- The first deployment rolled back because the script assumed web had a Docker health check. It now verifies web through HTTP. The first real model attempt produced malformed JSON; designer turns now request structured JSON through the existing Llama wrapper and retain graph validation.

Interactive browser verification remains unavailable under the existing browser automation restriction. No rendered desktop/phone, keyboard or screen-reader check is claimed. Changes remain uncommitted in the shared working tree.

## API additions

| Method and path | Purpose |
| --- | --- |
| POST `/api/workflows/design` | Admin-only unsaved graph proposal |
| POST `/api/chat-workflows/new` | Create an owned empty chat |
| GET `/api/chat-workflows/{conversation}` | Attached workflows and latest execution state |
| PUT `/api/chat-workflows/{conversation}` | Replace the attachment selection; maximum 20 |
| POST `/api/chat-workflows/{conversation}/{workflow}/run` | Idempotent approval request with stored chat context |

The web uses the existing authenticated `/api/orchestrator` proxy. New tables are created by the existing orchestrator startup schema creation. Existing workflow IDs, event subscriptions and conversation ownership are preserved.

## Limits

Attaching does not add a workflow to every future message. No automatic message trigger, workflow cancellation, parallel nodes, delays or retries were added. A lost connection must not be interpreted as a failed action; inspect the persisted approval/run status before retrying. Generated agents can inspect and draft, but direct customer sends, billing mutations and arbitrary service actions require explicit configuration and approval. New designer requests are bounded and rate limited.
