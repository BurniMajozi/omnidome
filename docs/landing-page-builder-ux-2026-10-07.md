# DomeDesign: restore the chat-based landing-page journey

The previous backend integration replaced the discovery/chat/canvas layout with a page list and a long block form. That made the main task—building and refining a page—hard to discover. This change reconnects a chat-first experience to the real Portal Builder APIs.

## Design contract

- Start with “What would you like to build?” and a brief. Optional starting prompts fill the brief for the user to review; they do not run automatically.
- “Build my page” asks the configured design provider for editable structured sections. It opens a chat beside the resulting preview, rather than creating or publishing a page behind the scenes.
- Select a section to scope chat refinements, or click the selected section's text to edit it directly. Reorder/remove sections, add cards and sections, adjust links/images, or change appearance/accent. Undo is available for local content edits.
- “My pages” is a secondary place to resume saved work. Website import is an optional way to reuse text and images, not a required journey and not a promise to reproduce an existing website's design.
- Save draft persists the actual page. Publish is a separate review step; on a published page, saved edits remain private until explicitly published. Share uses the existing preview-link workflow after saving.
- Keep the product's current dark shell, cyan action colour and familiar controls. The page canvas represents the landing page's own light/dark style. Chat and canvas stack on narrower screens. The portal navigation wraps instead of showing a horizontal scrollbar; overview metrics are hidden while building.
- Keep drafts when switching portal tabs. Warn before discarding unsaved content or closing the browser. Do not fabricate generation success or business claims when the provider is unavailable.

## Backend contract

`POST /api/v1/portal/design/suggest` requires a portal editor role and a verified tenant/user. Body: `{prompt, current?, selected_section?}`; result: `{message, draft:{title, description, theme, blocks}}`.

The endpoint uses the existing common OpenRouter provider and configured model fallback chain (`PORTAL_DESIGN_MODEL` is an optional primary). There are no tools or publishing capabilities in the generation call. The server validates its response, bounds inputs and sections, sanitises text/URLs and limits each caller to twelve requests per ten minutes per process. Provider failures return explicit errors and leave the existing editor content unchanged. No provider credentials reach the browser.

Supported generation sections: hero, text, features, pricing, FAQ, CTA and gallery. Images must come from the supplied brief/current page; there is no image-generation workflow. Copy must be reviewed before publishing. Prices, coverage, SLAs and testimonials must come from real supplied facts. The public page uses the same section renderer and saved theme; enquiry buttons link to the actual consent-based form.

## Verification

Portal backend suite: 48 passed. Scoped TypeScript check: passed. Production build and browser results will be recorded after deployment.
