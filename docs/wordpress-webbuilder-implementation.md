# WordPress Webbuilder implementation

Implemented locally on 8 October 2026. The first release connects a WordPress
site, exports a saved builder page as a separate draft, opens its preview, and
publishes the exact reviewed content. Existing OmniDome publication remains a
separate destination. The running application has not been redeployed, and no
external WordPress site has been connected or changed.

## What is available

- **Website Builder → WordPress** opens connection and publication controls.
  Users can add/reconnect a site, test it, save the local draft, export, preview,
  explicitly acknowledge review, publish, refresh status, and disconnect.
- The backend stores encrypted Application Passwords using the shared
  `SECRETS_ENCRYPTION_KEY` helper. Secrets are never returned in connection APIs.
- All connection/page/job records belong to a tenant. Connecting and publishing
  require a portal manager; exporting and reconciliation require editor access.
- The outbound MCP client implements the adapter's session-based `2025-11-25`
  profile, with JSON/SSE response handling, a narrow ability allowlist, bounded
  requests, public HTTPS validation, and redirect refusal.
- Export generates deterministic Gutenberg core blocks for hero, text, gallery,
  features, pricing, FAQ, and CTA content. An export hash identifies the reviewed
  version; publication refuses stale hashes and local edits.
- Publication attempts are persisted before the remote write. Ambiguous writes
  block repeats until reconciliation. The remote plugin enforces idempotency and
  per-page locking and recovers failed publication-record saves.
- WordPress draft export never overwrites the managed live page. Publication
  copies staged content to a separate live page. Changes made directly in
  WordPress produce a conflict rather than an automatic overwrite.
- Pending WordPress writes also block local page deletion and connection
  replacement/disconnection until status is reconciled.

## Install and activate

1. Deploy/restart the updated web app and `portal_builder` service. Keep the
   existing `SECRETS_ENCRYPTION_KEY` available to all backend workers. The existing
   startup migration creates the three additive WordPress tables.
2. Install the official **MCP Adapter** on a WordPress 6.9+ staging site with
   HTTPS. The tested adapter contract is 0.7.0 with MCP `2025-11-25`.
3. Upload [omnidome-builder.zip](../integrations/wordpress/omnidome-builder.zip)
   using WordPress's plugin upload screen, then activate it.
4. Create an Application Password for a dedicated integration user with
   `edit_pages` and `publish_pages`. Keep the same integration username when
   rotating credentials.
5. Open **Website Builder → WordPress**, enter the canonical site URL, username,
   and Application Password, and select **Connect and verify**.
6. Save a fibre landing-page draft, set its enquiry buttons to working absolute
   URLs, send it to WordPress, review the WordPress preview, and publish as a
   portal manager. The preview requires a WordPress login that can view drafts.

The plugin ZIP contains the `omnidome-builder` directory and its PHP entry point;
the official adapter remains a separate dependency. Full operational instructions
and rollback guidance are in [the integration README](../integrations/wordpress/README.md).

## Validation

| Check | Result |
| --- | --- |
| Full portal_builder suite | 75 passed |
| Frontend publication behavior tests | Passed: explicit review, dirty-state invalidation, publish, ambiguous-write guard, reconciliation, stale-site responses |
| Existing builder regression checks | Passed |
| TypeScript `tsc --noEmit` | Passed |
| Targeted ESLint on affected TypeScript files | Zero errors; three existing warnings in the builder/proxy |
| PHP 8.4 syntax check | Passed |
| Companion workflow fixture | Passed: separate draft/live pages, stale hashes, object permissions, external conflicts, idempotency, initial orphan-draft recovery, lost-write recovery, user isolation, lock refusal |
| Next.js production build | Passed, including the final WordPress proxy timeout adjustment |
| Git whitespace check | Passed |

Next's existing configuration skips build-time type validation, so TypeScript was
checked separately. Existing FastAPI/Pydantic deprecation warnings and Next
workspace/browser-baseline warnings were left unchanged.

## Practical limits

WordPress theme styles apply; exact visual parity and custom CSS are not exported.
Images retain absolute source URLs; media upload is a later capability. The
OmniDome enquiry form and SEO-plugin fields are not exported. Relative media,
`#enquiry` buttons, and unsupported section types block export with an actionable
message. Use an existing contact/coverage page or another working enquiry URL.

This release covers the interactive builder-to-WordPress publishing path. Generic
agent tool registration, arbitrary WordPress imports, bidirectional editing,
media-library upload, SEO-plugin adapters, and automatic unpublication are later
increments, not features implied by installing MCP Adapter.

Real WordPress adapter/theme validation remains outstanding: no staging URL or
credentials were supplied. The local browser session was signed out, so the
authenticated publishing panel was verified through behavioral tests rather than
a live browser interaction. No deployment, plugin installation, external
publication, or secret-key change was performed.

The PHP checks used an official portable PHP runtime downloaded to
`C:\Users\Benedict\AppData\Local\Temp\omnidome-php-8.4.26` (plus its ZIP in
the same Temp directory). Automatic approval review rejected both the validated
cleanup command and an explicit-path cleanup command as blocked by policy, so
these temporary validation files remain. No system PHP installation or PATH
change was made.

## Code locations

- `apps/web/components/modules/portal/wordpress-publisher.tsx`: publishing panel.
- `apps/web/lib/portal-api.ts`: typed connection/publication API client.
- `apps/web/app/svc/portal_builder/[...path]/route.ts`: WordPress request timeout.
- `services/portal_builder/wordpress.py`: tenant-owned storage, authorization,
  durable publication attempts, and reconciliation.
- `services/portal_builder/wordpress_client.py`: outbound MCP transport.
- `services/portal_builder/wordpress_export.py`: Gutenberg export and validation.
- `integrations/wordpress/omnidome-builder/omnidome-builder.php`: companion abilities.
- `services/portal_builder/tests/test_wordpress*.py`,
  `apps/web/tests/wordpress-publisher.cjs`, and
  `integrations/wordpress/tests/companion-test.php`: focused verification.
