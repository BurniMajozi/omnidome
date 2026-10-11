# Commercial shadow rollout and profitable provider pricing

Reviewed 11 October 2026. Customer charging and enforcement remain disabled.

Later update: [pricing/runtime review and continued supplier reconciliation](pricing-review-and-next-work-2026-10-11.md). Autumn is now optional; Postgres is authoritative. Public bundle browser validation has also been completed since this original rollout record.

## Provider commercial proposal

Use HubSpot's structure: software access, explicitly selected marketing contacts, and separately purchased delivery capacity. CRM storage alone is not a marketing-contact charge. Keep tenant AI credits separate from audio, research, social accounts and email capacity.

| Capacity | Proposed price, excluding VAT |
|---|---:|
| Deepgram transcription | R0.59 per audio minute |
| Firecrawl | R0.49 per provider credit |
| Zernio | R499 per connected account per month |
| AgentMail inbox | R179 per inbox per month |
| AgentMail domain capacity | R179 per domain per month |
| AgentMail email capacity | R179 per 1,000 emails per month |

Draft rates use R20/USD as a scenario, a 15% currency buffer, allocated delivery costs and Paystack fees, targeting 65% contribution margin. This is not guaranteed net profit. Fixed subscriptions, real FX, support, storage and purchased capacity still need reconciliation. Voice calls also incur telephone, LLM and TTS costs. Domain registration, media ad spend, X API, WhatsApp and other metered services are excluded. Buy small metered units in packs to spread fixed payment fees.

Detailed replacement costs, formula, sources and billing journey: [Managed marketing and provider pricing](marketing-provider-pricing-2026-10-11.md). Primary sources: [HubSpot catalog](https://legal.hubspot.com/hubspot-product-and-services-catalog), [Deepgram](https://deepgram.com/pricing), [Firecrawl](https://www.firecrawl.dev/pricing), [Zernio](https://docs.zernio.com/pricing), [AgentMail](https://www.agentmail.to/pricing), [Paystack ZA](https://paystack.com/za/pricing).

Also proposed: a R1,599/month dedicated managed-email minimum covering the full AgentMail Developer base, R590/1,000 transcription minutes and R2,450/5,000 research credits. These proposals prevent relying on marginal add-on prices to recover fixed subscriptions or paying a card fee per tiny unit. They remain documentation proposals, excluded from checkout and the six-entry marginal-rate calculator.

## Implemented and deployed locally

- New quotes freeze a versioned AI policy: Free 50, Starter 500, Professional 5,000 and Enterprise 10,000 monthly credits. Modular selection takes the highest tier rather than adding pools. Existing quotes without a policy retain legacy zero allowance; no automatic migration.
- Verified Paystack payments and audited provisioning create a tenant entitlement snapshot and durable synchronization outbox in the local transaction. Duplicate payments cannot duplicate grants. Draft provider rates do not enter checkout totals.
- Append-only cost events distinguish actual, estimated, allocated and unknown amounts. Unknown remains null. Operations snapshot policy and finalize once. Failed and approval-paused operations consume zero customer credits.
- Agent turns record model tokens, reported model cost, tool time, retrieval and runtime in shadow mode. This does not debit Autumn or charge Paystack. Native provider receipts and streaming paths need fuller coverage.
- Tenant usage appears in expanded tenant pricing. Platform Owner sees costs and provider profit floors and can apply an audited, expiring override. Organisation members cannot inspect procurement costs or grant allowances. Overrides do not extend paid plans or rewrite invoices; expiry does not restore a prior override automatically.
- Public pricing uses the catalogue's credit allowances. Hosting capacities remain unset. Managed provider add-ons remain draft.

Local admin, billing, agent and web images were rebuilt and restored. The final overlay includes immutable policy versions and an expired-plan guard. Read-only probes returned 200 for usage/costs, six draft provider rates, and live RAG context with five citations. Deployed common/pricing hashes match source.

## Autumn runtime

Pinned source: `89b5b6dc2653a19b758815d09b109061c70ecc40`. Its runtime image and isolated PostgreSQL schema, organization, hashed server key, cache, queues and Kafka were prepared. No Stripe credentials or paid attach calls are configured.

Concurrent startup repeatedly made WSL unresponsive, including after memory bounds, one queue worker and the corrected one-partition catalog topic. The infrastructure/bootstrap command completed, but the API probe could not run reliably. Autumn is stopped with persistent data retained, and core services/Ollama are restored. Live grant/reservation/release verification and bridge activation remain pending. Preparation files do not prove a completed connector; this local machine has not demonstrated capacity to run the full stack reliably.

Run `deploy/autumn/bootstrap.py` inside WSL, then `deploy/autumn/probe.py`. The probe uses a synthetic customer, validates grant/dedup/reservation/release and deletes its balance. Keep reconciliation inactive until it passes. Server keys remain in managed container environments, never repository files.

## Verification and limits

Affected pricing/commercial database tests: 19 passed. Agent commercial/retrieval/usage tests: 30 passed. Provider floor/commercial policy tests: 7 passed. The final focused immutable-policy/expiry test also passed. A final independent provider/usage/agent check passed all 10 tests. TypeScript checks, production web build and CRLF-aware diff check passed. Resource-related interruptions were retried after recovery.

Browser visual testing remains uncompleted because of the existing browser protocol restriction; no alternate-browser bypass was used. Historical SQLite billing results do not verify this PostgreSQL rollout.

## Remaining work

1. Complete live Stripe-free Autumn validation and activate its server-only reconciliation worker.
2. Reconcile native provider receipts, fixed subscriptions, utilization, hosting and runtime before certifying margins.
3. Build managed-capacity/contact selection, provider meters, frozen invoices and Paystack top-ups; keep bring-your-own-key separate.
4. Add estimates, reservations, releases and spend caps before enforcement. Shadow operations currently record credits locally without remote debit.
5. Verify tenant journeys and permissions in a browser, including phone width.
6. Approve a versioned rate card and explicitly migrate existing contracts before enabling charges.

Implementation commit: `2d3f6c88`. Changes are local and unpushed; prior commits are retained. The working tree is clean apart from untracked `.codex/`. Separate website-builder, inventory, mail-event and cancellation backlogs remain outside this rollout.

After the final recovery, admin, billing, agent, tenant memory and gateway reported healthy. Other services were still warming up; `knowledge_indexer` reported unhealthy and needs a separate ingestion-health check. This is not a claim that every service passed health verification. Autumn containers are stopped and core/Ollama containers restored; no bridge process was activated.
