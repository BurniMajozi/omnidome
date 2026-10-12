# Platform model console and routing

## Delivered

Agent Manager has a Platform Owner-only **Models & Routing** tab. It contains Models, Routing, Playground, Keys status and Analytics. Organisation Admins cannot read or change the global settings, test models or read cross-tenant analytics.

Three slots are configurable: Free / Basic, Balanced and Premium. Each has a primary model and up to two explicit fallbacks. Basic cloud models must have an OpenRouter `:free` identifier; local Ollama models are supported. A slot cannot mix local and cloud fallbacks. New configuration starts disabled; the existing deployment's routing remains in effect until the owner activates the new policy.

The owner enters model IDs, tests the slot in Playground, then saves and activates routing. Playground tests draft IDs without changing an existing active route. It checks every fallback, sends no company memory, executes no tools, records usage and can incur provider costs for paid slots. Verification expires after a day for subsequent configuration activation; a model or fallback change requires another test. Disabling routing is always possible without refreshing tests.

Routing uses the tenant's active provisioning quote. An unpaid new checkout cannot unlock paid models; a pending plan change retains the preceding active plan. Unknown plans and trials use Basic. Disabled paid slots also fall back to Basic. Tenant chat exposes only models from its resolved route. Existing credits, allowances, prices and Paystack checkout are unchanged.

Within a managed route, the Llama wrapper and common OpenRouter completion client use an explicit model chain. The OpenRouter environment's paid fallback cannot leak into it. Free routes strip provider server-side subagent tools and web plugins, which could otherwise charge independently of the free parent model. Paid JEV verification is skipped for these routes: approval-required actions retain human approval; final answers are flagged as unverified for review. Compaction uses the same reasoning wrapper. Managed legacy streaming yields a single completed answer through the existing stream API and records usage.

## Credentials and scope

Keys status uses the existing server OpenRouter environment key. The key is never returned to a browser. Tenant BYOK is absent. Adding or rotating a provider key still uses server deployment settings; this release does not implement a browser credential vault. Balanced and Premium are empty initially so no paid model is invented or activated.

This is native OmniDome functionality inspired by the FreeLLMAPI review; the external gateway was not installed and no source from it was copied. Ollama embeddings, RAG, workflow approvals and the usage ledger remain in place.

The guarded runtime deployment targets the orchestrator, web and Portal Builder's common client. Other services using direct or background provider clients require a separate audit before claiming a platform-wide zero-charge inference guarantee. Hosting, paid service tools, email, crawling and voice costs remain separate from reasoning-model routing. Model identifiers marked free are not a guarantee of capacity or uptime.

## Validation and deployment

Source TypeScript check passed. Routing and provider regression tests passed, including exhaustion without paid fallback, trial classification, owner-only permissions, hidden credentials, stale verification and provider server-tool removal. PostgreSQL configuration and existing job/workflow regression tests passed (42 tests). A separate common-provider regression run passed (35 tests). The live RAG retry returned three company-memory entries and three knowledge results with no error note.

Local deployment completed for web, orchestrator and Portal Builder. Rollback tags are `omnidome-chat-SERVICE:before-20261012182309` (the preceding deployment is also available at `before-20261012181153`). Signed live checks confirmed Platform Owner access, three disabled slots, the configured server key, all-tenant analytics and Agent Manager HTTP 200. Existing chat workflow attachments, old agent conversations, budgets and billing-wallet reads passed. Routing is disabled at shipment; the owner must configure and verify slots before activation. Browser visual verification is unavailable because browser automation was rejected earlier in this session.
