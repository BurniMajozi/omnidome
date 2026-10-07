# Portal Builder API (service port 8026)

Base path: `/api/v1/portal`. Authenticated routes need the signed identity (`x-user-id`, `x-tenant-id`, `x-roles`).
Errors are `{"detail": "..."}`.

## Roles

| Tier | Roles (or permission) | Allowed |
|---|---|---|
| read | any authenticated tenant member | list/get pages, versions, analytics, sitemap |
| write | marketing, content_editor, portal_editor, editor + manager tier (`portal.write`) | create/update pages, submissions list (PII), import, SEO audit/keywords, create campaign/SEO profile |
| manager | manager, marketing_manager, portal_manager, owner, admin, tenant_admin, org_admin, portal_admin (`portal.admin`/`portal.publish`/`portal.manage`) | publish, unpublish, delete, share/revoke, launch/complete campaign |

`PORTAL_ENFORCE_ROLES=false` disables gates (dev only). 403 body: `This action needs a portal <tier> role`.

## Pages

- `POST /pages` (write) `{slug, title, description?, page_type?: landing|campaign|product|seo, content?, theme?, seo_meta?}` -> 201 PageRead.
  Slug is lowercased; must match `^[a-z0-9](?:[a-z0-9-]{0,98}[a-z0-9])?$`, not reserved (admin, api, ...). 422 invalid, **409 duplicate in tenant**.
- `GET /pages?page&page_size&page_type&status&search` -> `{items:[{id,slug,title,page_type,status,views,conversions,updated_at}], total, page, page_size, pages}`
- `GET /pages/{id}` -> PageRead `{id, tenant_id, slug, title, description, page_type, status, content, theme, seo_meta, custom_css, views, conversions, sort_order, published_version, published_at, unpublished_at, created_at, updated_at}`
- `PUT /pages/{id}` (write) `{title?, description?, content?, theme?, seo_meta?, custom_css?, status?: draft|archived}`. Content/CSS are sanitised on save. `custom_js` is **rejected (422)**; `status:"published"` is rejected (use publish). Each save adds a version.
- `GET /pages/{id}/versions` -> `{published_version, items:[{id, version_number, reason: edit|publish, created_at}]}`
- `POST /pages/{id}/publish` (manager) -> `{status:"published", url:"/portal/<slug>", public_path, version, published_at}`. Snapshots a version. **409** if another published page (any tenant) has the slug.
- `POST /pages/{id}/unpublish` (manager) -> `{status:"draft", unpublished_at}` (409 if not published)
- `DELETE /pages/{id}` (manager) -> `{status:"deleted"}` (409 if campaigns reference it)

Page `content` convention (importer output): `{blocks:[{type:"hero",heading,subheading,image}|{type:"text",heading,body}|{type:"gallery",images:[{src,alt}]}]}`. String values may contain only a small tag allow-list (`a b strong i em u br p ul ol li span h1-h6 blockquote small sup sub`); URL fields (`src href url link image ...`) only http(s)/mailto/tel/#/relative.

## Public (no auth, rate limited)

- `GET /public/{slug}` -> `{id, slug, title, description, page_type, content, theme, seo_meta, custom_css, published_at, preview:false}`; published pages only (404 otherwise). **No `custom_js`.** Headers: strict `Content-Security-Policy` (no script), `nosniff`. Records a view (`utm_source|utm_medium|utm_campaign` query params and Referer host are stored). 429 when rate limited.
  Frontend must render `content` as data (React text/escaped), apply `custom_css` in a `<style>` only, never inject script.
- `POST /submissions` body `{page_id | slug, form_data:{k: string|number|bool|null}, consent: true, consent_text?, website?: "" (honeypot, keep empty and hidden), utm_source?, utm_medium?, utm_campaign?, referrer?}` -> `{status:"submitted", id}`.
  422 if `consent` is not true or `form_data` is nested/too large (max 40 fields, 2000 chars each); 413 over 16 KB; 404 unpublished page; 429 over 5/min per IP+page. A filled honeypot returns 200 without `id` and stores nothing.
- `GET /shared/{token}` -> same shape as public plus `preview:true, expires_at`. Works for drafts. 404 for unknown/expired/revoked. Headers include `X-Robots-Tag: noindex`.

## Sharing (manager)

- `POST /pages/{id}/share` `{recipient_email, expires_in_hours?: 1-720 (default 168), message?}` -> 201
  `{id, page_id, recipient_email, expires_at, share_url, email_status, message_id}`.
  `share_url` (with the token) is returned **only in this response**; only a hash is stored. `email_status`: `sent | suppressed | no_mailbox | failed`
  (suppressed recipients are never emailed; `no_mailbox` = Communication has no single active mailbox, or `PORTAL_SHARE_MAILBOX_ID` doesn't match; the link is still created, show it to the user).
- `GET /pages/{id}/shares` -> `{items:[{id, recipient_email, expires_at, revoked_at, active, email_status, view_count, last_viewed_at, created_at}]}`
- `POST /shares/{share_id}/revoke` -> `{status:"revoked", id, revoked_at}`

## Import and SEO (write)

- `POST /import/site` `{url}` -> `{source_url, final_url, fetch:{status_code, content_type, truncated, redirects, elapsed_ms}, content:{title, description, lang, og_image, headings:[{level,text}], paragraphs:[str], images:[{src,alt}], blocks:[...], stats:{words,links,images}}, suggested_page:{title, description, content:{blocks}}}`. Nothing is saved; create a page from `suggested_page`.
  https only, public hosts only (every redirect re-validated), 1.5 MB / 10 s / 4 redirect caps, HTML content types only. 422 URL not allowed, 415 not HTML, 502 fetch failed, 504 timeout. 20 per 10 min per user.
- `POST /seo/audit` `{url, keyword?}` -> `{url, score:0-100, grade:A-F, checks:[{id,label,status:pass|warn|fail,weight,detail}], summary:{pass,warn,fail}, stats:{...}, keyword:{keyword,in_title,in_h1,in_meta_description,occurrences_in_text,density_pct}|null, fetch:{...}}`
- `POST /seo/keywords` `{keywords:[...]}` -> without `SEO_PROVIDER_API_KEY`: `{provider_configured:false, keywords:[], message}`; with it: `{provider_configured:true, provider, keywords:[{keyword,search_volume,cpc,competition}]}` (or `error`). Show "not configured" in the UI, never placeholder numbers.
- `GET /seo/sitemap` -> `{base_url, urls:[{loc,lastmod,priority,changefreq}]}`

## Analytics

- `GET /analytics/summary?days=30` (1-365) -> `{period_days, since, pages:{total,published,draft,archived}, views, unique_visitors, submissions, conversion_rate (%), daily:[{date,views,submissions}] (zero-filled), top_pages:[{page_id,slug,title,views}], top_sources:[{source,views}], campaigns:{total,running}}`. All values come from the view/submission tables; zeros when empty.
- `GET /analytics` (legacy totals from page counters), `GET /pages/{id}/submissions?page_num&page_size` (write) -> `{items:[{id,form_data,utm,converted,consent_given,created_at}], total}`.

## Gateway / env

The web proxy must forward `GET /public/*`, `GET /shared/*` and `POST /submissions` without a session. Env: `PORTAL_BASE_URL` (share links, sitemap), `PORTAL_TRUST_PROXY` (use right-most `X-Forwarded-For` for rate limits/view hashes), `PORTAL_IP_SALT`, `PORTAL_SHARE_MAILBOX_ID`, `SEO_PROVIDER_API_KEY` (`login:password`, DataForSEO), `PORTAL_RUN_MIGRATIONS` (default true).
