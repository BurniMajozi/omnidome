# Continuing Claude's workflow work — 11 October 2026

Implemented the first two items from Claude's handoff: agent workflow tools and approval resumption. These changes are now deployed with the billing workflow integration described in `docs/platform-billing-workflows-2026-10-11.md`; they remain uncommitted/unpushed in the shared checkout. Claude's existing commit `0a1a17fe` is preserved, including the fix for empty-message timeouts incorrectly succeeding. The earlier blocked-runtime notes below describe the prior attempt; the current runtime is healthy and its watcher is active.

## Agent journey

Internal agents can call `workflows.list` to discover active workflows belonging to their tenant. `workflows.run` requests the existing human approval gate; agents cannot edit workflows. Customer-facing agents do not receive these tools. A workflow agent step cannot recursively launch another workflow.

The approval stores the input, definition, step summary and a SHA-256 definition fingerprint. Execution checks that the workflow is still active and matches the approved fingerprint. A changed definition requires new approval. Listing and execution require tenant and user identities, and all database lookups are tenant scoped.

## Approval continuation

Each new workflow run saves a frozen definition, original requesting user, data produced by completed steps, next node, step count and associated approval IDs. Step claims commit before external calls; the engine does not hold a workflow database transaction while calling HTTP services or agents.

A parked run waits for every associated approval. Approval alone is insufficient: its actual execution result must have been recorded successfully. Rejection, expiry, a missing/cross-tenant association or failed action ends the run. After success, a read-only agent turn uses the actual approved results to finish the response, then the remaining workflow nodes run against the frozen definition. Previous writes and approved actions are not replayed. The existing Agent path still performs its memory/RAG preparation.

Approval execution triggers continuation after its result is recorded. The approval event consumer also triggers it, and a 15-second recovery scan catches decisions committed before a run was parked. A continuation error is logged for recovery without changing an already-recorded successful action into an apparent failure. Run row locks and committed step claims serialize concurrent continuations; PostgreSQL concurrency must still be checked in the live environment.

`POST /api/workflows/runs/{run_id}/resume` provides a tenant-scoped recovery action for the roles already allowed to decide approvals. It does not approve or execute pending actions by itself. Legacy parked runs without a checkpoint return a review-required message and are not replayed. An interrupted in-flight step remains running for manual reconciliation because its external effects may already have happened; automatic retries are deliberately outside this change.

## Schema and deployment

`workflow_runs.checkpoint` is a nullable JSONB column. The existing startup backfills add it idempotently, both in the auto-create path and normal event-bus schema setup. The recovery task starts only after schema setup, and is cancelled at shutdown.

Deploy the orchestrator changes together: `workflow_engine.py`, `workflow_tools.py`, `tools.py`, `agents.py`, `approvals.py`, `models.py`, `main.py` and `routes/workflows.py`. Preserve the other agent's concurrent source changes. The commercial deployment overlay does not include this workflow implementation. No WSL restart, service deployment, new live lead, email delivery or workflow run was performed in this turn.

WSL rejected the read-only memory/RAG attempt with `Wsl/Service/CreateInstance/E_ABORT`, and localhost PostgreSQL was unavailable. Session memory was consulted; no successful live RAG retrieval is claimed. The user reports another agent working on the platform, so shared runtime services were not restarted. The previously paused `omnidome-watch.service` still needs coordinated restoration after deployment.

## Verification

44 focused tests passed: 22 new workflow tests plus 22 existing tool/approval tests. SQLite state-transition tests exercise approval resumption without duplicate writes, frozen definitions, pending/rejected/expired/failed/cross-tenant outcomes, no replay of interrupted steps, the 50-step loop limit, tool approval policies and Claude's empty `ConnectTimeout` regression. They also verify that an approved action is recorded before continuation and stays successful when continuation recovery is needed. SQLite does not establish PostgreSQL row-lock correctness. One existing Pydantic namespace warning remains. Python compilation and `git diff --check` passed.

The final web production build passed, including `/platform-billing`. The normal full TypeScript check encountered stale `.next/dev` references to a removed `deck-harness` page; a source-only check excluding that generated directory passed, as recorded in the billing handoff. CI installs `aiosqlite` alongside pytest to run the new workflow state-transition tests without adding it to the production service dependencies.

Before calling this live-ready, use a dedicated PostgreSQL test database to verify duplicate/concurrent approval deliveries and schema backfill, then deploy and check one explicitly labelled draft-only manual workflow and one event workflow. No production contacts should receive messages during that verification.

## Remaining scope

Per-step retries/timeouts beyond the existing HTTP timeout, billing/payroll/VAT events and starter notification workflows remain subsequent work. The prior tenant platform billing, wallet and R50-minimum top-up changes remain in the checkout; their separate handoff is `docs/tenant-platform-billing-2026-10-11.md`. Voice/email auto-recharge preferences there remain visibly pending provider and platform-card integration.
