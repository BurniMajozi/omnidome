# Todo: Sales lead lifecycle, event bus, automations

- [x] T1 event-bus pure helpers + unit tests
- [x] T2 event-bus migration, publish/notify/EventConsumer, live verification — live: 11/11 (rollback, fan-out, back-off, dead+notify, idempotency, 2 workers × 60 events no dupes)
- [x] T3 notifications + deliveries API (orchestrator), header bell — API live (feed, unread, read, tenant isolation, proxy 200); bell verified in browser at Checkpoint B
- [x] Checkpoint A — bus live-tested, bell shows unread count in the browser
- [x] T4 lead_stages rules + unit tests — 23 tests; sales suite 39 passing (run with PYTHONPATH=../.. from services/sales)
- [x] T5 lead migration + models (ref_no, owner, priority, closed, activities, tasks) — applied at startup (advisory lock); 34 leads referenced, PROPOSAL→QUALIFIED
- [x] T6 sales API: pipeline on create, stage endpoint, detail, owners, board→lead sync, events — live 21/21 (board↔table, 409/400 rules, convert idempotent, close-won mirror, legacy PUT, 16 owners, 13 events)
- [x] T7 web: lead table, Lead sources → board, linked create modal, board card ref/owner — browser: lead table (ref/owner/dates), stage dialog → board card LD-000034 in Prospecting, board move → table shows Proposal
- [x] Checkpoint B — sales 43 tests, tsc clean, board ↔ table verified in browser
- [x] T8 sales action endpoints + sales consumer (email, campaign) — live 15/15 (email via AgentMail to own inbox, Marketing stopped → pending → delivered on retry, audience "Sales leads · <campaign>")
- [x] T9 web: action menu + record panel + forms — browser: ⋯ and right-click menu (8 actions), record panel (ref/stage/owner/dates/deal/tasks/timeline), note saved via form, campaign picker lists real campaigns
- [x] Checkpoint C — every action on the timeline; email delivered to own inbox; Marketing-down retry proven (T8)
- [x] T10 orchestrator event triggers, intake, consumer, engine templating, templates; sales automation endpoint — live 18/18 (3 cards end-to-end with real AI drafts, idempotency, orchestrator-down catch-up); fixed phone-match merging different people
- [ ] T11 web: real rule cards
- [ ] Checkpoint D (push, CI)
