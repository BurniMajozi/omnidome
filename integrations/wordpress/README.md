# OmniDome WordPress publishing

The Website Builder can connect to a WordPress site, export a Gutenberg draft,
open a WordPress preview, and publish the exact reviewed export. Native OmniDome
publication is a separate destination.

## Setup

1. Use WordPress 6.9+ with HTTPS and install/activate the official **MCP Adapter**
   plugin (tested protocol contract: adapter 0.7.0, MCP `2025-11-25`).
2. Zip the `omnidome-builder` directory in this folder. Upload the ZIP in
   **WordPress → Plugins → Add New → Upload Plugin**, then activate it.
3. Create a dedicated WordPress integration user with `edit_pages` and
   `publish_pages` (Editor is a practical starting role). Create an Application
   Password in that user's profile. Page ownership is tied to this user; keep the
   same username when rotating the password.
4. Configure `SECRETS_ENCRYPTION_KEY` on the `portal_builder` service using the
   existing shared secretbox key management. Keep the key stable across workers
   and restarts; losing it makes stored credentials unreadable.
5. Restart/deploy `portal_builder`. Its existing startup migration registers the
   three additive `portal_wordpress_*` tables. No existing page columns change.
6. In **Website Builder → WordPress**, enter the canonical site URL (including
   any WordPress subdirectory), username, and Application Password. Connect and
   test. The backend requires all four companion abilities.
7. Save the local page, send it as a WordPress draft, open the preview, review the
   theme and business copy, then select **Publish reviewed draft** as a manager.

Preview links require a WordPress login with permission to view that draft. The
browser does not receive the stored Application Password. WordPress may use a
different permalink from the local slug; the confirmed remote URL is displayed.

## Behavior and limits

- Draft export stages a separate WordPress draft page. Updating it leaves the
  live WordPress page unchanged; publication copies the reviewed content into
  the managed live page.
- The companion plugin exposes only site info, draft upsert, reviewed publish,
  and publication status. It uses per-user external page identities, WordPress
  capability/object checks, and a MySQL named lock per page.
- Gutenberg core blocks cover hero, text, gallery, features, pricing, FAQ, and
  CTA content. WordPress theme styles apply. Custom CSS, theme parity, SEO plugin
  fields, and the OmniDome enquiry form are not exported in this release.
- Images must have absolute URLs and remain hosted at their source. CTAs must
  use working absolute URLs (or mailto/tel). `#enquiry`, relative images, and
  unsupported blocks block export, preventing a silently broken landing page.
- Editing a staged or live managed page directly in WordPress causes an
  `external_changes` conflict. Restore the reviewed content/metadata in WordPress
  before retrying. Automatic overwrite and bidirectional import are not provided.
- A durable publication job is saved before the external write. An ambiguous
  response blocks further writes; **Refresh WordPress status** reconciles before
  retry. Active requests are protected for two minutes. Requests have bounded
  timeouts and response sizes; remote writes are never automatically retried.
- Connections and publication state are tenant-owned; exporting requires portal
  editor access, connecting and publishing require portal manager access.
- The backend requires public HTTPS URLs, rejects redirects, and does not use
  ambient proxy settings. Public-DNS validation shares the importer's documented
  DNS-rebinding limitation; use an outbound network policy to exclude private
  destinations in production.
- Disconnecting removes the encrypted credential locally. It does not delete or
  unpublish WordPress pages. Revoke unused Application Passwords in WordPress.

## Verification

Run `python -m pytest services/portal_builder/tests -q` from the repository root.
PHP tests in `tests/companion-test.php` use a lightweight WordPress API fixture;
run `php tests/companion-test.php` from this integration directory. These verify
the companion workflow and conflict/idempotency behavior; a real WordPress
staging smoke test is still required for theme rendering and adapter integration.

Staging smoke test: connect, export, log into WordPress to preview, publish, edit
locally and re-export, verify the live page is unchanged, publish the new version,
then modify the live page in WordPress and verify the next operation conflicts.

## Rollback

Disconnect sites in OmniDome and deactivate the companion plugin. Existing live
WordPress pages remain. Reverting the application change removes the connector
UI/routes. Leave the additive tables in place for recoverability; drop them only
after intentionally retiring their credentials, page mappings, and audit records.
