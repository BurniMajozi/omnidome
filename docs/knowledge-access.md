# Knowledge access, personal context and the Communication panel

Scope of this note: what backs Tasks / Escalations / Schedule / KPIs / Comms today (verified in code, 2026-10-10), how panel
access is represented, and how the knowledge layer now follows it. Companion to `docs/knowledge-layer.md`.

## 1. Findings: real tables vs mock

| Feature | Backing | Verdict |
|---|---|---|
| Tasks | `communication` service, table `comm_tasks` (`assignee_id`, `due_date`, `status todo/in-progress/done`). Web: `/api/tasks` -> `COMMUNICATION_SERVICE_URL /api/v1/tasks`. | REAL |
| Escalations | `communication` table `escalations` (`assigned_to`, `created_by`, `status open/in_progress/resolved/closed`). No SLA/priority column. Support `tickets` (`assigned_to`, `priority`) is a second real source. | REAL (SLA is a tenant default policy, see below) |
| Schedule | `communication` table `schedule_events` (`user_id`, `start_time`, `end_time`, `status`). Web `/api/schedule`. No shifts table anywhere. | REAL (meetings/calls/reminders only) |
| KPIs / objectives | `hr` service: `employee_kpi_sheets` (`kpis_json`, `status DRAFT/SUBMITTED/APPROVED`, `overall_score`, approval columns), `company_kpi_configs`; login <-> employee via `employees.user_id`, hierarchy via `employees.manager_id`. | REAL |
| Approvals | `communication` table `approvals` (pending/approved/rejected) + HR KPI sheet approvals (manager chain). | REAL |
| Communication panel (AgentMail) | `communication`: `agent_mailboxes` (one per `agent_type`, no owner column) and `agent_emails` (raw bodies, direction, status, `headers` JSON for read/starred/reply flags). No thread, assignment or label table. Chat (`channels`/`messages`) is separate. | REAL, but raw only |
| Dashboard `module_data` blob | `communication.module_data` generic JSON. | MOCK-style; **not used by any new card** |

Not built because no real source exists: user preferences (working hours, timezone, locale, notification settings, preferred tone).
No user-profile table carries them (`users`/`employees` have none). Timezone defaults to `KNOWLEDGE_PERSONAL_TZ`
(`Africa/Johannesburg`). Add a `user_preferences` table first, then a card; do not invent values.

## 2. How panel access is represented

* Signed identity: `x-user-id, x-tenant-id, x-roles, x-permissions, x-modules, x-org-id` HMAC-signed by `services/common/internal_auth.py`.
  The web tier (`apps/web/proxy.ts`) signs **user, tenant and roles** (roles from the admin DB). It does **not** currently set
  `x-modules` or `x-permissions`.
* Admin service: tenant **entitlements** (`modules`, `tenant_modules` ENABLED/TRIAL) and **role permissions** (`<module>.read|write|admin`
  in `permissions`/`role_permissions`; seeded for crm, sales, support, billing, finance, network, iot, retention, call_center, analytics,
  inventory, hr, rica, marketing, memory). **There is no per-user panel allow-list table.**
* Dashboard: `allowedSections` is derived from the **tenant's** enabled modules (`moduleBySection`), not per user.

So per-user panel access is, today, an approximation: tenant entitlement + the user's role permissions. The knowledge layer therefore
derives each caller's modules as follows (`knowledge/access.py`, single place; `PANELS` is the canonical MODULE -> PANEL map):

1. admin (platform admin or `admin/org_admin/tenant_admin/owner`) -> all modules, no module gate;
2. explicit `x-modules` / JWT `modules` -> exactly that list (authoritative the day the web tier starts signing it);
3. else roles (`x-roles`) and RBAC permissions (looked up from the admin RBAC tables, cached 60 s) -> `derive_modules`;
4. else only `general`, `memory`, `personal`.

`communication` is granted to every authenticated staff user (the product has no per-user gate for the chat panel); `portal` and
`products` need a matching role. A failed RBAC lookup never widens access.

## 3. Deny-by-default retrieval

A card is returned only if ALL hold (Python: `AccessScope.allows`; SQL: `store_pg.access_clause`; both enforced):
(a) card module in the caller's allowed modules, (b) role tag (`required_roles`) and permission tag (`required_permission`) match,
(c) `private` cards only for `owner_id == caller` - **admins included**. Admins see every module of their tenant, never other users'
private cards. Applies to search, context, graph (unreadable nodes are no longer listed at all), recall (hybrid) and metric facts.
Responses carry `meta.allowed_modules / allowed_panels / denied_panels` and `GET /api/v1/knowledge/access` returns the same, so a UI
or agent can say "you do not have access to the X panel".

Behaviour change to know about: callers with no recognised role or module now see only `general`/`memory`/`personal` cards (before,
anything with an empty role tag was visible tenant-wide). Trusted in-process callers can still build `AccessScope(..., modules=None)`.

## 4. Communication panel

No thread table exists, so threads are **derived deterministically** (no LLM, no new table, no hook into ingestion): the
`mail_threads` source groups `agent_emails` per mailbox by normalised subject (Re:/Fwd: stripped) over the last 90 days, and emits one
`mail_thread` card per thread: subject, counts, unread, needs-reply, last activity, status, participants as **display names only**
("Thandi M."; bare addresses become "External sender"), and a <=300 character excerpt of the **last inbound** message with quoted
history cut, every link removed, and the standard scrubber applied. No attachments, no full bodies, no addresses, no tokens.

* Visibility: team inbox. Mailboxes have no owner column, so there are no "private mailboxes" to model; the card needs the
  `communication` module plus `<area>.read` for the mailbox's `agent_type` (support->support, billing/collections->billing, ...);
  unmapped agent types need `communication.admin`.
* Suppression: threads whose external address is in `marketing_suppressions`, or whose messages carry `unsubscribed / suppressed /
  do_not_contact` flags, produce no card (tombstoned).
* Legal hold: `headers.legal_hold` marks the card `legal_hold` and blocks forgetting.
* Forget: `POST /api/v1/knowledge/admin/mail/forget {mailbox_id, thread_key}` (admin) sets `headers.knowledge_forget=true` on the
  thread's rows (same JSON-flag mechanism the mail UI uses for read/starred; this is the only write into another service's table) and
  erases the card; the flag stops re-indexing. Refused (409) under legal hold.
* Assignment/labels do not exist in the schema, so the card says "not tracked" instead of guessing.

## 5. Personal context (private cards)

Source `personal_context` (`personal.py` reads the real tables; `cards/builders_personal.py` renders). Per user, up to five cards,
all `module=personal`, `visibility=private`, `owner_id=user`: `my_tasks`, `my_escalations`, `my_schedule`, `my_kpis`, `my_approvals`.
KPIs: own sheet (objectives, level vs target, status, next step); managers (manager role AND people under them in `employees.manager_id`)
also get an **aggregate** (counts, averages) and the SUBMITTED sheets awaiting them (names reduced to "Sipho N."). Free text is scrubbed.

Freshness: the worker sweep runs about every 2 minutes; cards expire after `KNOWLEDGE_PERSONAL_TTL_MIN` (20) minutes unless the sweep
re-confirms them (`Indexer` extends `valid_to` of unchanged cards via `store.refresh_valid_to`); a user with nothing open stops being
refreshed and disappears from retrieval within the TTL, and the daily reconcile tombstones the rows. Bodies avoid relative wording so
unchanged data is never re-embedded.

Escalation SLA: the table has no SLA field. The clock is `now - created_at` against `KNOWLEDGE_ESCALATION_SLA_HOURS` (default 24) and
every item states `sla_basis`. Timezone for "today": `KNOWLEDGE_PERSONAL_TZ`.

## 6. Agent tools (read-only)

`my.day`, `my.tasks`, `my.escalations`, `my.schedule`, `my.kpis`, `my.approvals` in `services/agent_orchestrator/personal_tools.py`,
hooked into `tools.py` (policy, execute branch, registry, per-agent lists). Each is a signed call to
`POST /api/v1/knowledge/personal/{kind}` which reads the **live** tables for the signed caller only; there is no user/employee id
parameter, a run without a user is refused, strings are neutralised as untrusted data. Granted to assistant, executive, support,
retention, crm, call_center, talent, billing, analytics, products; never customer_facing or provisioning. `my.day` can take a `focus`
and adds up to three related non-private knowledge cards under the same access rules. Note: the agent type `sales` has no entry in
`AGENT_TOOL_PERMISSIONS` and falls back to the customer_facing list, so it gets none of these (pre-existing quirk, not changed).

Skipped: write/draft tools. There is no draft-then-confirm path for `comm_tasks` or `schedule_events` (the UI posts straight to
`/api/tasks` and `/api/schedule`), and inventing one was out of scope.

## 7. Tests and unverified items

`python -m pytest services/tenant_memory -q` (includes `knowledge/tests/test_access_personal.py`: module x role x private matrix,
SQL/Python parity, thread digest scrubbing and suppression, personal builders, expiry/refresh/tombstone, caller-only gather, route and
tool scoping). Not verified live: SQL against real Postgres for `personal.py` and `sources_personal.py` (fakes only), the RBAC lookup in a
running stack, the first full sweep and its embedding load, and whether the web tier should start signing `x-modules`/`x-permissions`.
