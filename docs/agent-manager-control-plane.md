# Agent Manager control plane

HR owns the organisation chart. Creating an employee with `is_agent=true` saves
the employee first, then registers a tenant-scoped agent with the orchestrator.
The HR response reports `registration_status`; a failed registration can be
retried from the employee card. Registration is idempotent and does not start a
process or grant autonomous write access. HR-created agents use the assistant
runtime with read-only tools and a mandate taken from the saved employee.

Agent Manager's Work & Budgets view is the operator surface. A task enters a
durable queue, and a worker claims at most one task per tenant at a time. It
saves a checkpoint after each model turn. A pause is applied after the current
turn; an expired worker lease marks the task interrupted for human review.
Resuming an interrupted task uses its saved conversation, so operators should
review its last step before resuming. Completed output waits for human acceptance.

The work states are `queued`, `running`, `pause_requested`, `paused`,
`interrupted`, `awaiting_hitl`, `awaiting_review`, `max_iterations`,
`stopped_by_ceiling`, `failed`, and `completed`. JEV tool decisions and response
verification appear in the run timeline. High-confidence suggestions to bypass
a static approval requirement remain in shadow mode unless
`JEV_AUTO_APPROVAL_ENABLED=true` is explicitly configured.

Managed runs have a per-run ceiling and a monthly tenant ceiling. The tenant
defaults to USD 100 per UTC month (`AGENT_TENANT_MONTHLY_BUDGET_USD`); an
explicit blank tenant cap removes it. HR-created agents additionally default
to USD 25 per month. Operators can change both budgets in Agent Manager.
Provider cost is labelled actual only when every model call reports a cost;
otherwise the token-based estimate is used. Ceilings are checked between model
turns, so one turn can exceed a monetary ceiling. The HR financial delegation
limit is a separate ZAR authority field and does not set the LLM budget.

The orchestrator creates the three control-plane tables on startup. Set
`AGENT_JOB_WORKER_ENABLED=false` to expose the API without starting the queue
worker during a staged rollout. Existing conversation and workflow routes are
separate from managed work and are not included in these budgets.
