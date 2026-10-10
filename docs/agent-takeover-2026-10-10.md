# Agent takeover checkpoint

Completed Claude's interrupted governed BI query and live-chat activity work. The native agent retrieves skills, recalled memory and company RAG before its model call; exact operational figures use governed dataset tools. Retrieval failure is reported honestly. Provider spellings such as data_query now resolve to registered tools before the agent allow-list check, and local embedding retrieval has a 30-second budget.

The web chat shows live steps, elapsed time, clarification choices with free text, approval waiting cards and Stop. Clarification uses owner- and tenant-scoped durable records, closes after 30 minutes or cancellation, and cannot approve gated actions. Existing manager-role/no-self-approval rules remain enforced. Public step summaries contain no raw arguments or model reasoning.

Dataset discovery and queries respect signed panel permissions. Row lists use allowlisted columns, tenant filters, a 200-row cap and an exact matching-row count. Capability source cards describe datasets and tool policies. Existing SQL endpoints remain for compatibility but are removed from normal internal agent tool lists.

Validation: 432 tests passed and one skipped in the combined orchestrator/BI run. After the final provider-name and timeout fixes, 49 affected tests passed. The changed chat files type-check. The full web build passed. The unfiltered type check encountered stale generated .next references to deleted routes; the targeted source check passed.

Deployed locally to WSL Docker: agent-orchestrator, tenant_memory, fno_intelligence and web. Original running services and watchdog were restored. Backup image tags: pre-live-agent; an additional agent backup is pre-rag-fix.

Live checks: RAG context returned 200 with three citations; the native turn reported ready with two source cards before the first model step. PostgreSQL list queries returned 200 for sales_pipeline (22 matching rows), billing_invoices (two) and support_tickets (zero). The native AGUI run completed, with custom progress before answer text and successful data.datasets/data.query calls. The model made two invalid query attempts before correcting them; the backend rejected them with 422.

Capability reindex was queued. Browser security policy rejected the existing test tab because its current page uses a blocked protocol. Visual desktop/phone verification and browser interaction with question/approval cards remain unverified; API, cancellation and durable-answer tests passed. Hermes does not yet emit native per-step activity.

Continued user request: align pricing bundles and individual modules with admin tenant creation/editing, inherited panel entitlements, Organisation Admin versus Platform Owner, and invoice/subscription checkout. That work follows this checkpoint.
