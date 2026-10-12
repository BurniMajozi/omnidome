# Agent Manager: conversations, activity and budgets

The Work & Budget view now follows the task as a conversation. A searchable conversation list sits beside the selected chat on desktop and stacks above it on smaller screens. New-task setup is a dialog, leaving the main area for ongoing work. Existing runs remain visible; linked retries and new follow-ups share a transcript.

Users can reopen an old task, ask another question, give feedback or request a different approach without replacing the original objective or accepting an output first. Each message creates a bounded, auditable new run and retains prior user/assistant history. Messages sent during execution queue behind the preceding turn. They do not interrupt a model call or replay its tools. Pause is available between turns; Mark done remains optional human acknowledgement of an output.

Activity shows public steps such as memory retrieval, company RAG, tool execution and answer checks. The UI distinguishes tool counts from activity: a text-only response may legitimately use zero tools. It shows queued, running, paused, approval, review and failure states without inventing a success percentage. Raw prompts, tool arguments and hidden model reasoning are not in the activity feed.

Credits & budgets reads the existing tenant billing wallet: included allowance, used credits, prepaid remaining, reserved credits, remaining balance, reset date and panel usage. A link opens the established billing/top-up journey. USD operational ceilings remain separate from selling credits; no exchange rate or selling price is invented. Tenant ceiling editing remains Platform Owner-only. Registered-agent limits and context checks are retained. Bring-your-own-key/model is deferred as requested.

## Validation and release

Deployed locally on 12 October 2026. Rollback tags are `omnidome-chat-web:before-20261012152127` and `omnidome-chat-agent-orchestrator:before-20261012152127`. Only web and orchestrator were recreated. The deployment checked there were zero active/queued managed tasks before activation; no WSL restart or memory-service restart was used.

- Six PostgreSQL checks passed for persistent history, no copied spend/tool log, concurrent-request idempotence, tenant isolation, serial follow-ups, public activity, worker history continuation and waiting for the preceding turn. The worker check confirms an earlier answer reaches the new turn and that activity writes cannot overwrite its checkpoint.
- Seven existing long-horizon checks and 34 workflow/designer/continuation regressions passed: 47 checks across the relevant suites. No external model, email, payment or notification was invoked by the test suite.
- Web source type check passed with only the stale generated `.next/dev` harness imports excluded. The temporary configuration was removed. Production Next.js build passed. No new packages were added.
- Live signed HTTP checks passed for the job list, budgets, the existing billing wallet, an unknown conversation returning 404, reopening an old conversation, and Agent Manager page HTTP 200. The earlier workflow feature's live checks still passed. Final memory recall returned three team entries and three company-knowledge hits with no configuration/error note; the watchdog is active.
- Follow-ups while work is active are queued, not injected into a running model call. The claim query filters unresolved dependencies before its candidate limit, so a blocked conversation does not fill the queue's front with unclaimable turns.
- Activity is stored in the new `agent_job_activity` table, created through startup schema creation even when general automatic table creation is disabled. Existing objectives, results and cost history are unchanged. Follow-ups use existing `agent_jobs` rows/checkpoints and do not replace a saved output.
- Pending-action links open the Agent Manager approval tab. Tenant spend-ceiling editing is shown only to the Platform Owner; the API remains the authority.

Interactive browser testing remains unavailable under the earlier browser restriction; no rendered desktop/mobile or keyboard check is claimed. Changes are in the shared working tree and are not committed. No live verification task, customer/contact, invoice or charge was created.

## Use the new view

Refresh Agent Manager → Work & Budgets. Choose an earlier task in Conversations, read its transcript and type feedback in **Continue the conversation**. **Send follow-up** starts another bounded turn with the prior responses as context; accepting the output is not required. A direction sent during execution waits for that turn to finish or pause. Use **Pause/Resume** for execution control and **Mark done** when you are satisfied.

The activity section updates while the view is open. Credits & budgets shows the shared billing balance and a link to the existing billing/top-up flow; it does not create a second wallet. If billing cannot be reached, the view reports that rather than substituting an estimated balance.

## Limits

Old unrelated one-message tasks cannot be reconstructed as one prior conversation; they remain separate and can now receive follow-ups. Thread responses are bounded to 100 turns. The conversation list shows the latest 100 run records. A queued follow-up behind a task awaiting approval/interrupted execution waits until that task is resolved. Billing shadow metering and unpublished credit pricing are labelled accurately and left unchanged.
