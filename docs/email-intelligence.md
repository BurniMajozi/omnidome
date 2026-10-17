# Email intelligence (AgentMail → events → vector index → agent tools)

Status 2026-10-16. Built on what already existed: the communication service stores AgentMail traffic (`agent_emails`,
`agent_mailboxes`, webhook + polling + approval-gated reply), and the knowledge layer already indexed a *digest* of mail
(`mail_thread` cards, no bodies). This adds the full path: thread state, clean events, a full-text email index with
mailbox-level access, agent tools, and a safety layer.

```
AgentMail ──webhook (Svix-signed) / poll ──► communication ──► agent_emails (idempotent on provider message id)
                                               │                 email_threads (state, owner, links)  email_audit_log
                                               └─► event bus: email.received · email.sent · email.send_failed ·
                                                   email.delivery_failed · email.thread_status_changed
knowledge_indexer ─ source `email_threads` ─► cards (redacted, chunked, embedded) ─► knowledge_db (pgvector)
orchestrator tools ─ email.search / list_threads / get_thread / draft_reply / send_reply(approval) ─► the two above
```

## 1. Ingestion (services/communication)

| Path | Stores | Notes |
|---|---|---|
| `POST /mail/webhook` `message.received` | inbound | owner tenant resolved from the inbox, signature checked against **only that tenant's** secret |
| `message.sent` (new) | outbound | mail sent outside our UI (AgentMail console, another service on the inbox); verified like `received`; 2 s grace so our own send wins the race |
| poll (`AGENTMAIL_POLL_MINUTES`, 24 h lookback) | inbound **and** sent | fallback when the webhook is dead |
| our own send (`/mail/send`, `/emails/{id}/reply`, `/threads/{id}/send`) | outbound | records the provider `thread_id` (new `send_message_ex`) |
| `POST /mail/backfill {provider_days}` (admin) | history | pages the provider oldest-first, **no events, no auto-reply**, then rebuilds thread state |

**Idempotency**: the application check (`tenant, direction, message_id`) plus a unique partial index
`uq_agent_emails_provider_msg` (created by `mail_state.ensure_schema`); a lost race is caught as `IntegrityError` and the
first row wins. Events use the idempotency key `email.<type>:<provider message id>`, and are published in the **same
transaction** as the email row, so an event exists iff the email committed. Thread/event bookkeeping runs in a savepoint:
a failure is logged and never loses the email.

### Event contract (for the ticketing session and any other consumer)

All have `source="communication"`, subject `("email_thread", <thread uuid>)`. Payloads carry a **redacted 500-char preview**
(`body_preview`), never the full body; fetch the thread through the API (access-checked) for the rest.

`email.received`: `email_id, thread_id (email_threads.id), thread_key, mailbox_id, mailbox_address, agent_type, message_id,
in_reply_to, is_reply, direction, subject, body_preview, has_attachments, thread_status, message_count, customer_id,
lead_id, ticket_id, from_address, from_name ("Thandi M."), from_domain, to_address, untrusted:true,
injection_suspected:[…], via (webhook|poll|api)`.
`email.sent` / `email.send_failed`: same shape with `to_addresses, status, error`. `email.delivery_failed`: bounce /
complaint / rejection of something we sent (`provider_event`). `email.thread_status_changed`:
`thread_id, from_status, status, owner_user_id, ticket_id, changed_by`.
A ticketing consumer links its ticket back with `PATCH /mail/threads/{id} {"ticket_id": …}`; the knowledge card and the
thread API then show it. Treat `body_preview`, `subject` and `from_name` as **untrusted text**.

### Conversation state (`email_threads`)

`needs_response` (customer wrote last) → `awaiting_customer` (our reply went out) → back on the next inbound; `closed`
by a person/agent (`PATCH`), reopened by any new inbound. A failed send changes nothing. Owner (`claim`/`owner_user_id`),
`customer_id`/`lead_id` (matched on the counterpart address at ingestion), `ticket_id`.
`GET /mail/threads?status=needs_response&owner=unassigned&older_than_hours=24` and `GET /mail/threads/summary` answer
"what emails need a response" for people, agents (`email.list_threads`) and the daily review.

## 2. Vector index (services/tenant_memory)

Source `email_threads` (`cards/sources_email.py`) → one card per thread, `source_type=email_thread`, `module=communication`.

* **Content**: header (subject, mailbox, status, linked records, participants as *display names + sender domains*), then every
  message (newest 30) as `### date - direction - name (domain)` + its **new text** (quoted history cut). The chunker splits
  long threads; every chunk repeats the frontmatter so a hit always carries its source. Embeddings: the existing local
  Ollama `nomic-embed-text` (768) via the same indexer, so content hashes make re-runs free.
* **Source refs** (returned with every hit, `source_ref`): `thread_id, thread_key, mailbox_id, subject, status,
  participants, from_domains, last_message_at, message_ids, customer_id, lead_id, ticket_id, deep_link`. Full addresses are
  deliberately not indexed.
* **Access** (same rule as `mail_state.can_read_mailbox`; enforced by the retrieval layer in SQL and Python):

  | Mailbox | Card | Who reads it |
  |---|---|---|
  | shared (default) | `team`, `required_permission = <area>.read` for the mailbox's `agent_type` (`communication.admin` if unmapped) | holders of that permission; tenant admins |
  | shared with `required_roles` | `team`, `required_roles` (replaces the permission) | those roles; admins |
  | **personal** (`PUT /mail/mailboxes/{id}/access {kind:"personal", owner_user_id}`) | `private`, `owner_id` | the owner only, **admins included**; the API hides it from `GET /mail/emails` and the thread routes (404) too |

  A mailbox access change re-cards the whole mailbox on the next sweep.
* **Opt-in retrieval**: `email_thread` chunks are excluded from every query that does not name `source_types:["email_thread"]`
  (`kdata.OPT_IN_SOURCE_TYPES`), so inbound mail never rides along in auto-grounding, generic search or graph expansion.
* **Retention / deletion**: a thread leaves the index when all messages are older than `KNOWLEDGE_EMAIL_RETENTION_DAYS`
  (365), when every message is deleted (`status='deleted'`, the mail UI's delete), when its counterpart is in
  `marketing_suppressions` or a message is flagged `unsubscribed / suppressed / do_not_contact`, or when
  `knowledge_forget` is set (existing admin *forget* endpoint). Cards also expire (`valid_to`). Daily full reconcile
  tombstones anything the queries stop returning. `legal_hold` blocks forgetting and is shown on the card.
* **Backfill & incremental**: the first run has no watermark = the whole retention window; afterwards a `(created_at, id)`
  keyset plus a 6 h rescan (read/status flags carry no timestamp) and a rescan of threads whose state/access changed.
  Attachments: filenames only (redacted); no extracted text — PDFs/Office files are neither cheap nor reliably safe to embed.

## 3. Agent tools (services/agent_orchestrator)

| Tool | Class | Backed by |
|---|---|---|
| `email.search` | read | knowledge search forced to `email_thread` / `communication` (the model cannot widen it); refused for `customer_facing` |
| `email.list_threads` | read | `GET /mail/threads` |
| `email.get_thread` | read | `GET /mail/threads/{id}` — messages fenced as `<untrusted_email>`, redacted, flagged |
| `email.draft_reply` | mutates, no approval | `POST /mail/threads/{id}/draft` — stores text on the latest inbound; never sends |
| `email.send_reply` | mutates, **approval required** | `POST /mail/threads/{id}/send` — see §4 |

Given to `support, crm, billing, assistant` (all five) and `retention, call_center, executive` (read tools). Never to
`customer_facing` or `provisioning`. Listed in `KNOWN_TOOLS` (so the skills catalogue and the capability cards
describe them under the Communication panel) and in the workflow editor's event list. Identity is the signed caller's, so
mailbox access applies to agents exactly as to the person behind them.

## 4. Safety

* **Redaction** (`services/common/email_safety.redact`) before anything is embedded, put in an event or shown to a model:
  private keys, JWTs, AWS/API tokens, `password/secret/token/api key … = value`, bearer tokens, OTPs, Luhn-valid card numbers,
  SA ID numbers, IBAN/account numbers, long hex tokens, e-mail addresses, SA phone numbers; links reduced to their domain
  (reset tokens live in paths/queries).
* **Untrusted data**: every path that hands email text to a model wraps it in `<untrusted_email …>` with a fence the text
  cannot forge or close, adds a standing notice, and attaches `injection_suspected` pattern names (override-instructions,
  role hijack, fake system blocks, tool commands, exfiltration, approval claims, zero-width evasion). The system prompt
  tells agents never to follow, call tools for, or accept approval from email content. The flag is a *signal*; the boundary is
  structural: reading tools cannot act, drafting only stores text, and the only way out is `send_reply`, behind the approval
  gate, which also refuses credential-shaped text (422), refuses a second reply to the same message (atomic claim, 409),
  and is audited. Cards show a "Safety" line when a thread contains instruction-like text.
* **Audit** (`email_audit_log`, `GET /mail/audit`, admin): `ingested`, `recorded_outbound`, `injection_flagged`,
  `read_thread`, `draft_saved`, `sent`, `send_refused_secret`, `thread_updated`, `mailbox_access_set`, `backfill`.
* **Tenant isolation**: every query filters `tenant_id`; webhook secrets are per owning tenant; chunks are tenant-keyed.

## 5. Operations

* Deploy: `deploy/commercial/deploy-email-intelligence.sh` (overlay images for communication, tenant_memory,
  knowledge_indexer, agent-orchestrator; explicit file list; backup tags; health-gated rollback).
* Verify live: `docker exec -i omnidome-communication-1 python < deploy/commercial/check-email-intelligence.py`.
* One-off backfill for a tenant: `POST /api/v1/mail/backfill {"provider_days": 365}` (admin); the knowledge worker then embeds
  everything within its next sweeps (≈2 min cadence, gentle batches).
* Env: `KNOWLEDGE_EMAIL_RETENTION_DAYS` (365), `KNOWLEDGE_EMAIL_RESCAN_HOURS` (6); existing `AGENTMAIL_*` unchanged;
  disable the source with `KNOWLEDGE_SOURCES=all,-email_threads`.
* Tests: `services/communication/tests/test_email_intelligence.py`, `services/tenant_memory/knowledge/tests/test_email_cards.py`,
  `services/agent_orchestrator/tests/test_email_tools.py`.

## 6. Known limits / follow-ups

* No migrations tooling: tables are created idempotently at communication startup; the old `mail_thread` digest source is
  kept (Communication panel) alongside the new full-text source.
* The agent auto-reply on inbound (`auto_reply_enabled`) still invokes the orchestrator directly, as before; its drafts land in
  `agent_response` and show up as `pending_draft` on the thread. Moving that to an `email.received` workflow is possible
  now (event label exists) but was left alone to avoid changing live behaviour.
* Provider-side attachments (inbound) are not fetched; only filenames present in headers appear.
* `ticket_id` is set by whoever links it (the ticketing consumer via `PATCH`); there is no automatic subject parsing.
* Provider send needs AgentMail credentials (tenant config or `AGENTMAIL_API_KEY`); the dev stack has none, so the live check
  stubs the provider call and exercises everything else against real Postgres.
