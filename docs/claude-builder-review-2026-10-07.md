# Review of Claude's latest changes

Reviewed on 7 October 2026: `b924c207..9e43cadd`, covering the chat-first builder (`bb27d6fb`), its verification notes (`f885c17a`), and the Agent Manager detail fix (`9e43cadd`). The builder commit includes work that was already underway in this shared checkout.

The builder now has the journey you requested: describe a landing page, generate a draft, edit the preview, save, then review before publishing. Import is optional. I independently exercised generation, direct editing, saving and reopening in the browser. The direction is right, but I would fix the following issues before signing off. This review did not change application source.

## Findings

### 1. [P1] Editing a run before its full detail loads can truncate the actual task

Location: `apps/web/components/admin/agent-work-view.tsx:148–154,302–308`; `services/agent_orchestrator/control_plane.py:75`.

The list endpoint truncates objectives to 200 characters. While the full-detail request is pending, `chosen` falls back to that summary, but Edit prompt and Revise & retry remain available. Clicking either copies the truncated objective into `draftObjective`. A later successful detail response does not update that editing buffer. Saving can therefore replace a longer task with its first 200 characters. A failed detail request is silently swallowed and leaves the same risk indefinitely.

Require successfully loaded full detail before enabling objective editing or retry. Show loading/error state and a retry action; never submit the summary objective as an editable full prompt. This finding follows the request/state flow in source; I did not alter any real agent jobs.

### 2. [P2] The assistant cannot remember the conversation shown beside the preview

Location: `apps/web/components/modules/portal/use-design-studio.ts:42,49–56`; `services/portal_builder/design.py:62,121–122`.

Messages are retained only for display in local component state. Each suggestion sends the latest prompt and current page, without previous conversation turns or the original brief. A request such as “use the first headline you suggested” has no corresponding history available to the model. Reopening a saved draft replaces the conversation with a generic greeting; I confirmed this in the browser.

Send bounded conversation context and retain the original brief and relevant decisions. Persist it privately for the page so reopening can resume the conversation. Conversation data must stay outside the published page payload.

### 3. [P2] Generated copy invents business promises while claiming no claims were added

Location: `services/portal_builder/design.py:92,102–114` and its accepted assistant response.

In a live generation test I provided a fictional service name and requested a hero, benefits, FAQ and enquiry section, explicitly excluding business claims and prices. The resulting draft promised feedback within 24 hours, experienced reviewers, secure/private document handling and support for documents up to 20 pages. None of those facts had been supplied. The assistant then stated: “No prices, claims, or images were added.”

The system prompt prohibits invented facts, but response validation checks structure rather than grounding. Publishing remains a separate action, which limits the immediate impact. Still, the reassurance is inaccurate and makes unsupported copy easier to trust. Treat unsupported operational promises as items requiring confirmation, and derive any factual validation message from checks rather than accepting the model's self-assessment. A factual instruction alone was insufficient in the exercised provider response.

### 4. [P2] Direct editing removes paragraph breaks

Location: `apps/web/components/modules/portal/portal-blocks.tsx:4–7,36`.

`plainText` replaces every whitespace sequence with a space, including newlines. In the browser I entered `First paragraph.\n\nSecond paragraph.` into the hero subheading. On blur it became `First paragraph. Second paragraph.`, and saving/reopening retained the flattened version. This prevents users from formatting multiline copy through the visual editor.

Separate markup stripping from whitespace normalization. Preserve newlines for body/subheading fields and render them consistently in both the editor and the public page.

### 5. [P2] Selected Agent Manager details stop updating while a run keeps the same status

Location: `apps/web/components/admin/agent-work-view.tsx:144–154`.

The detail effect depends only on the selected ID and status. The list polls every 15 seconds, but a running job can gain steps, tokens, costs and iteration history without changing status. Its full detail is never refreshed in that interval. The merge `{ ...summary, ...detail }` also overwrites fresh list values with the older detail values, so the selected panel can remain behind the list until a status transition or reselection.

Refresh selected detail alongside polling, with cancellation/ordering protection. Avoid allowing stale detail to override newer summary counters. This was verified from the polling dependencies and merge order, not by modifying a live run.

## Verification and limits

- Portal backend suite: **50 passed**, six warnings.
- Scoped TypeScript check covering changed portal screens, public routes/proxy and Agent Manager: **passed**.
- Published-snapshot regression: an in-memory mutation that incorrectly served the current draft caused the targeted regression test to fail as expected. Production source was unchanged by this check.
- Browser: a real AI request succeeded; direct edits, save and reopen worked. The conversation reset, unsupported claims and paragraph loss were observed directly.
- At viewport widths 320, 768, 1024 and 1440 pixels, measured document and builder widths showed no horizontal overflow.
- The disposable review draft and its saved version were removed. Existing pages were preserved. I did not publish, send email, submit an enquiry or change real agent objectives.

These checks add browser and live-provider evidence beyond the earlier commit's documentation, which correctly said those checks had not yet been performed. They do not establish that every provider response is reliable, nor do they cover the entire earlier invoicing/inventory backlog. The Agent Manager findings concern the additional latest commit; they are separate from the landing-page journey.
