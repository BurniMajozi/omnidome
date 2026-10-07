# Builder review fixes — 7 October 2026

All five findings from the Claude review have been addressed and deployed locally.

- **Full agent objectives:** Edit prompt and Revise & retry wait for successfully loaded full detail. The submission handler also refuses summary-only objectives. Failed detail requests show an error and retry control.
- **Live agent detail:** Each successful list poll refreshes the selected run, even when its status stays unchanged. Fresh summary counters take precedence over cached detail. Cancelled requests cannot overwrite a newer selection.
- **Conversation continuity:** Suggestions receive the original brief and the last 20 conversation turns. Saving retains that context in a separate, tenant-scoped `portal_design_contexts` table; reopening restores it. Page content, publication snapshots and public responses contain none of this private context. Failed conversation saves remain marked unsaved and stop publication until retried.
- **Business promises:** Common unsupported numerical, security/privacy, experience and guarantee claims are replaced with neutral copy and listed for confirmation. Explicitly supplied user copy can be retained. The model's self-certification is discarded; editor and publication review display a factual-review reminder. This is a conservative guard, not a general fact checker: other AI-written business copy still requires review.
- **Paragraph formatting:** Text sanitization preserves newlines, the renderer preserves whitespace, and direct editing reads rendered line breaks so keyboard-created paragraphs also survive blur.

## Validation

- Portal backend suite: **56 passed**, six existing deprecation warnings. Added coverage for private context round trips, tenant/role isolation, exclusion from published output, conversation bounds, provider context, invented promises and explicit supplied facts.
- Scoped TypeScript check: **passed**.
- Frontend state-transition checks: **passed**. Covered pending full-detail gating, preservation of a long objective, same-status polling, detail errors/retry, chat save/reopen, partial-save handling and paragraph rendering. Run with `node tests/builder-review-regressions.cjs` from `apps/web`.
- Production web build: **passed**. Updated web and portal-builder images deployed to the local WSL runtime. PostgreSQL startup created the private context table successfully.
- Browser check on the deployed builder: multiline hero copy preserved its blank paragraph after direct editing and blur. The browser draft was unsaved; no page was published, emailed or submitted. Chat persistence and agent request transitions were exercised by automated checks rather than by modifying real agent jobs.

The existing chat-first journey remains: describe → generate → refine in chat or preview → save → review publication. No unrelated marketing changes were included in this fix.
