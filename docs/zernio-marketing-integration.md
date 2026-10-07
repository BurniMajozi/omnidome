# Zernio marketing integration: connect flow, posts, campaigns, ads, WhatsApp, lead forms

Scope: `services/marketing/**`. Date: 2026-10-07. Provider: Zernio (`https://zernio.com/api/v1`, docs `docs.zernio.com`,
OpenAPI `zernio.com/openapi.json`, read 2026-10-07).

**Verification status, read this first.** Every provider interaction was built from the published OpenAPI + guides and
exercised only against fakes (`tests/test_zernio_integration.py`, 66 tests; the whole suite is 140 passing:
`python -m pytest services/marketing -q`). No call was made to Zernio with our key, so nothing here has been proven live.
Root causes below are diagnosed from the code and the provider docs, not reproduced against production.

Contents: [Conventions](#conventions) | [1 Connect](#1-connection-flow) | [2 Posts and media](#2-posts-scheduling-queue-and-media) |
[3 Campaigns and audiences](#3-campaigns-and-audiences) | [4 Ads](#4-ads) | [5 WhatsApp senders](#5-whatsapp-sender-status) |
[6 Lead forms and leads](#6-lead-forms-and-leads) | [Config, migrations](#configuration-and-migrations) | [Unresolved gaps](#unresolved-gaps)

---

## Conventions

* All paths are served by the marketing service and reached from the browser as `/svc/marketing/<path>`.
* Auth: signed identity, as everywhere. "write" = `marketing.write`/manager+, "admin" = `marketing.admin`/admin+. Reads are open to members.
* Provider rejection (Zernio 4xx: bad input, missing add-on, account not connected, validation) is **HTTP 422**:
  ```json
  {"detail": {"error": "provider_rejected", "message": "Meta rejected the ad: Page not connected",
              "provider_status": 400, "provider_code": "platform_rejected", "details": {"stage": "creative", "param": "pageId"}, "ref": "9f2c1a7e0b11"}}
  ```
  Provider outage / our key rejected / transport error is **502** `{"error": "provider_unavailable", "message": ..., "ref": ...}` (details only in server logs).
  Provider rate limit is **429** + `Retry-After`. Provider not configured is **503** `provider_not_configured`.
  Success is never reported unless the provider returned the object (an ad id, an account id, a post id).
* Tokens/keys are never returned, logged or placed in URLs. Provider `access_token` fields are stripped from lists.
* Tenant isolation: every account id that reaches the provider is first proven to belong to the tenant
  (`marketing_connected_accounts` for connections; `GET /v1/accounts?profileId=<tenant profile>` for fresh connections;
  the provider's `/ads/accounts` list for ad accounts; the tenant's own account rows for post targets).

---

## 1. Connection flow

### What was wrong

`GET /social/accounts/connect/{platform}` called Zernio `GET /v1/connect/{platform}?profileId=` with **no `redirect_url`**.
Per the provider docs, without our redirect Zernio runs its own hosted account-selection UI and finishes on its own dashboard, which
asks for a zernio.com login (the `zernio.com/signin` landing). Platforms needing a Page/organization/board/location pick were also
sent to Zernio's hosted picker. The frontend then opened that URL in a new tab.

### What changed

New module `zernio_connect.py` (+ legacy route delegating to it):

1. Every flow gets an OmniDome-owned `redirect_url` = `<OMNIDOME_PUBLIC_URL>/dashboard/marketing/connect/callback?st=<state>`.
   The callback host is **server-configured only**; a browser-supplied `redirect_url` is ignored (it would let an attacker receive the hand-off params).
2. Platforms that need a picker (Facebook, LinkedIn, Pinterest, Google Business, Snapchat, Instagram via Facebook Login, WhatsApp) start with
   `headless=true`, so OmniDome renders the picker and Zernio is only ever called server to server.
3. Ads accounts connect through `GET /v1/connect/{platform}/ads` (a dedicated `metaads`/`googleads`/`tiktokads`/`linkedinads`/`pinterestads`/`xads` account).
4. State `st = <nonce>.<mac>`: nonce row in `marketing_connect_sessions` (tenant, user, platform, the tenant's own Zernio profile id, expiry),
   MAC = HMAC-SHA256 over nonce|tenant|user|platform|profile|expiry. Validated on every call: MAC, row exists, TTL 30 min, **tenant and user equal the caller's**,
   one completion only (replay = 409). `st` is ~43 chars so the encoded redirect stays well under X's 258-char limit.
5. Account ids from the browser (`accountId` on the redirect, picker ids) are never trusted: picker ids must be among the options we returned, and the resulting
   account must appear in `GET /v1/accounts?profileId=<tenant profile>` before the tenant mapping is written.
6. Provider temp tokens for pick-lists are stored Fernet-encrypted in the session row (`SECRETS_ENCRYPTION_KEY`; without it pick-list platforms answer 503, fail closed) and cleared on completion.

### Frontend contract

**Callback page** (new, owned by the frontend): `/dashboard/marketing/connect/callback`. It reads **every** query param on its URL and sends them to `POST /social/connect/complete`
together with `st`. It then follows the `status` in the response.

| Endpoint | Role | Notes |
|---|---|---|
| `GET /social/connect/platforms` | catalog | grouped `social` / `ads`, each with `flow` (`oauth` / `oauth_select` / `credentials` / `telegram_code` / `embedded_signup`) |
| `POST /social/connect/start` | begin OAuth | admin |
| `GET /social/accounts/connect/{platform}?category=social\|ads` | legacy start | admin; still returns `{platform, auth_url}` plus `state` |
| `POST /social/connect/complete` | callback handler | admin |
| `POST /social/connect/select` | finish a picker | admin |
| `POST /social/connect/credentials/bluesky` | Bluesky app password | admin |
| `POST /social/connect/telegram/start`, `GET /social/connect/telegram/status?state=` | Telegram code flow | admin |
| `GET /social/connect/whatsapp/sdk-config`, `POST /social/connect/whatsapp/embedded-signup`, `POST /social/connect/whatsapp/credentials` | WhatsApp in-app | admin |
| `DELETE /social/connect/accounts/{account_id}` | disconnect | admin; only tenant accounts |
| `GET /social/zernio/connectors` | existing; now also lists the six ads connectors (`category: "Ads"`) with `connected` | |
| `GET /social/connected-accounts`, `GET /social/accounts-health` | existing | |

Social platform ids: `facebook instagram linkedin twitter tiktok youtube threads reddit pinterest googlebusiness snapchat bluesky telegram whatsapp`.
Ads ids (`category: "ads"`): `meta_ads google_ads tiktok_ads linkedin_ads pinterest_ads x_ads`.

#### `POST /social/connect/start`
```json
// request
{"platform": "linkedin", "category": "social", "return_to": "/dashboard/marketing",
 "login_method": null, "login_mode": null, "scopes": "posting,analytics",
 "reconnect_account_id": null, "ad_account_ids": null}
// 200
{"status": "redirect", "platform": "linkedin", "category": "social", "flow": "oauth_select",
 "auth_url": "https://www.linkedin.com/oauth/v2/authorization?...", "state": "q3J...Zw.Hk2...x9A",
 "expires_in": 1800, "callback_url": "https://app.example.com/dashboard/marketing/connect/callback"}
// 200 (Meta business login reconnect that is already valid)
{"status": "already_connected", "platform": "meta_ads", "account_id": "...", "state": "..."}
```
`window.location.assign(auth_url)` (same tab; no popup needed, the user returns to the callback page). `login_method` (`instagram_login|facebook_login`) is Instagram only;
`login_mode` (`classic|business`) is `meta_ads` only; `reconnect_account_id` must be one of the tenant's accounts.
Errors: 422 `unsupported_platform` / `wrong_flow` (bluesky, telegram and whatsapp use their own endpoints); 503 `provider_not_configured` / `callback_not_configured`.

#### `POST /social/connect/complete`
```json
// request: every query param the callback URL had
{"state": "<st>", "params": {"connected": "tiktok", "profileId": "...", "accountId": "...", "username": "acme", "request_id": "...", "stage": "..."}}
// 200 done
{"status": "connected", "accounts": [{"account_id": "...", "platform": "tiktok", "username": "acme", "display_name": "Acme", "profile_picture": null, "is_active": true}], "return_to": "/dashboard/marketing"}
// 200 pick needed (headless platforms)
{"status": "selection_required", "step": "select_page", "selection_type": "pages", "multiple": true, "platform": "facebook", "return_to": null,
 "options": [{"id": "123", "name": "Acme Fibre", "username": "acme", "category": "ISP"}]}
// 200 provider reported a failure (denied consent etc.)
{"status": "error", "error": "oauth_denied", "reason": null, "message": "You cancelled", "user_fixable": true, "platform": "tiktok", "return_to": null}
```
Option fields by `step`: `select_page` (id, name, username, category), `select_account` (id, name, instagram_username), `select_organization` (id, name, urn, vanity_name, account_type `personal|organization`;
first option is the personal profile), `select_board` (id, name), `select_location` (id, name, address, account_id), `select_public_profile` (id, name, username), `select_phone_number` (id, name, phone_number, waba_id, name_status, quality_rating).
Errors: 400 `invalid_state` / `state_expired`; 403 `state_mismatch` / `profile_mismatch` / `account_not_in_tenant`; 409 `already_completed`; 503 `secrets_unavailable`.
Meta Ads (`meta_ads`, classic login) skips the picker: the backend binds the first Page (the provider's documented ads-only path) and answers `connected`.

#### `POST /social/connect/select`
```json
{"state": "<st>", "selection_ids": ["123"], "account_type": null}   // multiple ids allowed only for page / account / location steps
// 200
{"status": "connected", "accounts": [...], "return_to": null, "failed": [{"id": "456", "message": "..."}]}   // `failed` only when some picks failed
```
422 `invalid_selection` if an id was not among the offered options.

#### Credentials / codes / WhatsApp
```json
POST /social/connect/credentials/bluesky   {"identifier": "acme.bsky.social", "app_password": "xxxx-xxxx-xxxx-xxxx"}   -> {"status":"connected","accounts":[...]}
POST /social/connect/telegram/start        -> {"status":"pending","state":"...","code":"ABC123","bot_username":"...","expires_in":900,"instructions":[...]}
GET  /social/connect/telegram/status?state=... (poll ~3 s) -> {"status":"pending"|"connected"|"expired", ...}   (connected adds "accounts")
GET  /social/connect/whatsapp/sdk-config   -> {"app_id":"...","config_id":"...","branding":{...},"state":"...","expires_in":1800}
POST /social/connect/whatsapp/embedded-signup {"state":"...","code":"<from the popup>","waba_id":"...","phone_number_id":"...","is_coexistence":false} -> {"status":"connected","accounts":[...]}
POST /social/connect/whatsapp/credentials  {"access_token":"<system user token>","waba_id":"...","phone_number_id":"...","pin":"123456"}  -> {"status":"connected","accounts":[...],"warning":"..."}
```
WhatsApp in-app signup: load Meta's JS SDK with `app_id`, call `FB.login(cb, {config_id, response_type: "code", override_default_response_type: true, extras: {setup: {}, sessionInfoVersion: 3}})`,
collect the `code` from the login response and `waba_id`/`phone_number_id` from the `WA_EMBEDDED_SIGNUP` postMessage, then POST them with `state`. (Zernio's alternative `signup=hosted` page lives on zernio.com, so it is deliberately not used.)
The credentials route re-points that WABA's webhook delivery to the provider (documented provider behaviour); the token is forwarded once and not stored.

### Not supported / not done
Discord, Slack, Shopify and WordPress connections (Shopify needs the merchant's shop domain; marked `coming_soon`). TikTok Ads brand identity (`PATCH /v1/connect/tiktok-ads`) is not exposed. Changing a Page/organization on an existing account without re-auth is not exposed.

---

## 2. Posts, scheduling, queue and media

### What was wrong (the "Nothing scheduled" screens)

1. `POST /social/posts` required `account_id`, and the composer sends `accounts[0]?.id` from `/social/accounts` (the legacy credentials table, empty for tenants connected through the provider). The field was absent, so FastAPI answered **422** and nothing was ever saved.
2. Statuses were mixed case (`scheduled` from create, `SCHEDULED` from the schedule endpoint, `DRAFT` default) and filtered by exact equality.
3. The provider call used field names the API does not read (`scheduleDate`, `mediaUrls`; real: `scheduledFor`, `mediaItems`), so even a "scheduled" post reached Zernio as a text-only **draft**.
4. `POST /social/queues/{id}/enqueue` and `POST /social/posts/{id}/schedule` only wrote a local row/flag and never called the provider.
5. Edits and deletes never reached the provider (a "deleted" scheduled post would still publish).

### What changed
* `account_id` is optional (legacy FK satisfied by a tenant stub row); targets come from `account_ids` (tenant provider accounts) or `platforms`. Any unconnected platform or foreign account id is refused (400 / 403) before any provider call.
* Statuses are stored lower case (`draft scheduled publishing published partial failed cancelled`); a startup migration lower-cases old rows; filters are case-insensitive, accept comma lists and `queued`.
* Provider calls use the documented fields, UTC `scheduledFor`, per-post `Idempotency-Key`, and copy the provider's real status/per-platform errors onto the row. A rejection leaves `status:"failed"` + `publish_error`; it never looks scheduled.
* `scheduled_for` in the past (< 30 s ahead) is refused (the provider would publish immediately).
* Enqueue computes the slot from the OmniDome queue and schedules at the provider for exactly that time. Update/schedule/publish/delete are propagated to the provider post (`PUT`/`DELETE /v1/posts/{id}`).
* Webhook `post.published|failed|partial|scheduled|cancelled` updates the row (needs the events subscribed, see Config). `POST /social/posts/sync` refreshes statuses on demand.

### Endpoints
| Endpoint | Notes |
|---|---|
| `GET /social/posts?status=&platform=&queued=&from=&to=&sort=&limit=&offset=` | list; `status` comma list, case-insensitive (`scheduled,draft`, `queued`); `sort` = `created_desc\|created_asc\|scheduled_asc\|scheduled_desc`; total in `X-Total-Count` |
| `GET /social/posts/scheduled?include_provider=false&platform=&queued=&from=&to=&limit=&offset=` | **what the Scheduled view should call**: scheduled + queued, soonest first |
| `GET /social/posts/provider?status=&platform=&page=&limit=` | live provider posts for the tenant profile (every entry re-checked against tenant accounts) |
| `POST /social/posts` | create (write) |
| `PUT /social/posts/{id}`, `DELETE /social/posts/{id}` | edit / delete (propagated) |
| `POST /social/posts/{id}/publish`, `POST /social/posts/{id}/schedule?scheduled_for=` | promote a stored post |
| `POST /social/queues/{queue_id}/enqueue` | body = create body; schedules at the next open slot |
| `POST /social/posts/sync` | refresh local statuses from the provider |

Existing `GET/POST /social/queues`, `PATCH/DELETE /social/queues/{id}` unchanged.

```json
// POST /social/posts
{"content": "Fibre promo", "platforms": ["facebook", "instagram"], "account_ids": null,
 "media_urls": ["https://cdn.../a.jpg"], "media_items": null,
 "status": "scheduled", "scheduled_for": "2026-10-12T08:00:00Z", "timezone": "Africa/Johannesburg",
 "queue_id": null, "provider_draft": false, "campaign_id": null}
```
`status`: `draft` (stored in OmniDome only; `provider_draft:true` also stores a provider draft), `scheduled` (needs `scheduled_for`), `published` (now). Blank strings for optional fields are treated as null.
```json
// 201
{"id": "uuid", "status": "scheduled", "scheduled_for": "2026-10-12T08:00:00Z", "platforms": ["facebook","instagram"],
 "media_urls": [...], "queue_id": null, "zernio_post_id": "66a...", "publish_error": null,
 "platform_post_ids": {"zernio_post_id": "66a...", "platforms": [{"platform":"facebook","accountId":"...","status":"scheduled"}]}, "...": "..."}
// provider rejected: still 201 (the row exists) but honest
{"id": "uuid", "status": "failed", "publish_error": "instagram: media required", "...": "..."}
// GET /social/posts/scheduled
{"posts": [{"...post fields", "source": "local"}], "total": 3, "limit": 100, "offset": 0, "provider_error": "only when include_provider=true failed"}
```
Validation errors: 422 (no platform, no content/media, missing/near-past `scheduled_for`), 400 `No connected account for: tiktok`, 403 foreign `account_ids`.

### Media upload
| Endpoint | Use |
|---|---|
| `POST /social/media/presign` `{"filename":"a.mp4","content_type":"video/mp4","size":123456}` -> `{"upload_url","public_url","key","expires_in":3600,"content_type"}` | **preferred**: browser `PUT`s the file to `upload_url` (header `Content-Type: <content_type>`, no auth), then uses `public_url` in `media_urls` / `creative.image_url` / `creative.video_url`. Up to the provider's 5 GB. |
| `POST /social/media/upload-base64` `{"filename","content_type","data_base64"}` -> `{"public_url","key","content_type","size","type"}` | works through the `/svc` proxy; keep to a few MB |
| `POST /social/media/upload` (multipart, field `file`) | server-side, up to `MARKETING_MEDIA_MAX_BYTES` (100 MB). **Not usable through the current `/svc/marketing` proxy**: it forwards bodies with `request.text()`, which corrupts binary. Fixing the proxy (`arrayBuffer()` for multipart) is a frontend change. |
| `POST /ads/media/presign` | alias of presign |

Allowed types: jpeg, png, webp, gif, mp4/mpeg/quicktime/avi/webm/x-m4v, pdf. We do **not** use the provider's `/media/upload-direct` (files auto-delete after 7 days, which would break posts scheduled further out).

### Not supported
Zernio-native queues are not used (OmniDome keeps its own queue definitions); client helpers `list_queues`/`next_queue_slot` exist. Recycling, first comment, per-platform custom content and platform-specific settings (TikTok privacy, YouTube title, Reddit subreddit, etc.) are not exposed by the composer API yet.

---

## 3. Campaigns and audiences

### What was wrong
* `POST /campaigns` 422: the form sends `start_date: ""`/`end_date: ""` (and sometimes `budget_zar: ""`); pydantic cannot parse `""` as a datetime.
* The audience column `marketing_campaigns.audience_segment_id` existed, but the Out model dropped it, nothing validated it, and `/email/send` only accepted a literal `recipients` list: selecting an audience did nothing.

### What changed
* `CampaignCreate`/`CampaignUpdate`: blank/whitespace dates, ids, description and budget become `null` (budget -> 0); negative budget and `end_date < start_date` are 422 with a clear message.
* `audience_id` is accepted as an alias of `audience_segment_id` on create and patch (patch with `null` clears it). The audience must belong to the tenant (422 otherwise). `GET /campaigns` and the create/patch responses now include `audience_segment_id`, `audience_id`, `audience_name`, `audience_size`; `GET /campaigns?audience_id=` filters.
* New migration columns (idempotent `ADD COLUMN IF NOT EXISTS`, run under the existing advisory lock): `audience_member_count`, `last_audience_send_at` + index on `audience_segment_id`.
* Sends use the audience: `POST /email/send` with `campaign_id` and **no** `recipients` resolves the campaign audience's members (`rules.businesses[].email`, `rules.contacts|members`, `rules.emails`), then goes through the normal path (validation, suppression list, caps, unsubscribe link). `recipients` still wins when given. Homes audiences hold areas only (no people) and answer 422 with the reason.
* `GET /campaigns/{id}/audience` -> `{"campaign_id","audience":{"id","name","type"},"emails":12,"phones":9,"skipped_without_contact":3,"note":null}` for a pre-send count.

```json
POST /campaigns  {"name":"Spring promo","channel":"email","description":"","budget_zar":"","start_date":"","end_date":"","audience_id":"<segment uuid>"}
201 {"id":"...","status":"draft","start_date":null,"end_date":null,"audience_segment_id":"...","audience_id":"...","audience_name":"Fibre businesses","audience_size":120,"...": "..."}
POST /email/send {"campaign_id":"<uuid>","subject":"Hi","body_html":"<p>...</p>"}   // recipients omitted -> audience members
202 {"batch_id":"...","campaign_id":"...","total_queued":118,"status":"sending","total_suppressed":2,"total_invalid":0}
```

### Not done
SMS and WhatsApp campaign sends do not yet take audience members (the audience endpoint returns the phone count; `/sms/send` and WhatsApp broadcasts still take explicit recipients). A `social`-channel campaign does not narrow who sees a post.

---

## 4. Ads

All endpoints are tenant scoped; an ads account / ad account is only usable after it is proven to belong to the tenant. New module `zernio_ads.py`.

| Endpoint | Purpose |
|---|---|
| `GET /ads/accounts` | connected ads accounts + platform ad accounts under each: `{connections:[{account_id,platform,account_platform,username,status}], ad_accounts:[{account_id,platform,ad_account_id,name,currency,account_status,minimum_daily_budget,timezone,balance,selectable,unusable_reason}], errors:[]}`; none connected -> `connections: []` + `message` |
| `GET /ads/goals?platform=` | objective enums per platform with the fields each goal requires |
| `GET /ads/options` | CTA enum, budget types, genders, age range, limits, default status |
| `GET /ads/targeting/search?account_id=&q=&dimension=geo\|interest\|behavior\|language\|...&geo_type=&country_code=` | resolve names to provider targeting ids (regions/cities/interests) |
| `POST /ads/targeting/reach` | `{account_id, ad_account_id, targeting}` -> audience size estimate (`available:false` on Google/TikTok) |
| `GET /ads/audiences?account_id=&ad_account_id=&type=` | custom / lookalike / saved audiences on the ad account |
| `POST /ads/audiences` | create `customer_list`, `website` (pixel), `lookalike`, `meta_engagement` |
| `POST /ads/audiences/from-segment` | push an OmniDome audience to the platform as a customer-match list (provider SHA-256 hashes; Meta also uses phone) |
| `POST /ads/validate?provider=true` | local rules + provider dry run (Meta `validateOnly`); creates nothing |
| `POST /ads/preview` | local preview data always; Meta rendered previews when `creative_spec`/`existing_creative_id` is sent |
| `POST /ads/create` | create the ad (PAUSED by default) |
| `GET /ads/provider/ads?account_id=&status=&page=&limit=` | live ads/metrics from the provider for the tenant profile |
| `PUT /ads/provider/ads/{ad_id}/status` `{"status":"active\|paused"}` | pause/resume (ad must be in the tenant's own list) |
| `POST /ads/media/presign`, `POST /social/media/*` | media -> `public_url` (see section 2) |

Goals (documented): meta 11 (`engagement traffic awareness video_views lead_generation lead_conversion conversions app_promotion catalog_sales page_likes page_visits`), google `engagement traffic awareness`,
tiktok `engagement traffic awareness video_views lead_generation conversions app_promotion`, linkedin `engagement traffic awareness video_views lead_generation job_applicants`, pinterest `engagement traffic awareness video_views`, x `engagement traffic awareness video_views app_promotion`.

```json
// POST /ads/create  (budget in WHOLE currency units, never cents)
{"account_id": "<ads connection id>", "ad_account_id": "act_123", "name": "Fibre launch", "goal": "traffic",
 "budget": {"amount": 100, "type": "daily", "currency": "ZAR"}, "start_date": "2026-10-20T08:00:00Z", "end_date": null,
 "status": "PAUSED",
 "creative": {"headline": "Get fibre", "body": "Uncapped from R399", "call_to_action": "LEARN_MORE",
              "link_url": "https://example.com/fibre", "image_url": "https://cdn.../a.jpg", "video_url": null, "video_id": null,
              "lead_gen_form_id": null, "page_id": null, "instagram_account_id": null},
 "targeting": {"countries": ["ZA"], "regions": [{"key": "...", "name": "Gauteng"}], "cities": [], "age_min": 25, "age_max": 55,
               "gender": "all", "interests": [{"id": "6003...", "name": "Internet"}], "audience_id": "<custom or lookalike id>", "saved_targeting_id": null},
 "promoted_object": {"pixel_id": null, "custom_event_type": null}, "provider_overrides": {}, "client_request_id": "uuid-per-submit"}
// 201
{"status": "created", "created_as": "paused", "ad": {"ad_id": "...", "name": "...", "platform": "facebook", "status": "paused", "platform_campaign_id": "...", "platform_ad_set_id": "...", "platform_ad_id": "...", "goal": "traffic", "budget": {...}},
 "ads": [...], "local_campaign_id": "uuid-or-null", "warnings": [{"field": "...", "code": "...", "message": "..."}]}
```
Errors: 409 `no_ads_account`; 403 `account_not_in_tenant` / `ad_account_not_available`; 422 `validation_failed` `{errors:[{field,code,message}],warnings}` (blocked before the provider is called) or `provider_rejected` (message verbatim, `details.stage`, `details.createdObjects` when the provider created partial objects); 502 `provider_no_ad` if the provider answered 2xx without an ad (nothing is shown as created).
Send the same `client_request_id` when retrying (it becomes the idempotency key). `POST /ads/validate` result: `{valid, errors, warnings, provider_validated, provider, platform}`.
Targeting limits of this API: one `audience_id` per ad (multi-audience / exclusions need Meta raw targeting, not exposed); locations by `countries`, `regions`, `cities` (keys from `/ads/targeting/search`).
A successful create also inserts a mirror row in the existing `ad_campaigns` table (provider ids in `creative.provider`) so the current Ads list shows it; it is not kept in sync afterwards, use `/ads/provider/ads` for live status and spend.

### Not supported / not done
Provider dry-run exists for Meta only (other platforms are validated by the provider at create). Multi-creative, carousel, dynamic creative, Google PMax/Demand Gen/Search keywords, TikTok Smart+ and brand identity, boost-a-post and catalogs are not exposed (`provider_overrides` allows a documented whitelist, e.g. `placements`, `optimizationGoal`, `bidStrategy`, `keywords`). Currency conversion for the legacy ZAR columns: budget is mirrored into `budget_zar`/`daily_budget_zar` only when the ad account bills in ZAR.

---

## 5. WhatsApp sender status

### Finding
**Hard-coded.** `POST /whatsapp/senders/connect` appended an in-memory sender with the literal strings `name_review: "Pending Meta Review"`, `business_verification: "Verified"`, `status: "LIVE"` and `number: "+27 11 000 0000"`; nothing was connected and nothing was read from Meta.

### What changed
* `GET /whatsapp/senders` is built from the tenant's connected WhatsApp accounts plus **live** `GET /v1/whatsapp/number-info?accountId=` (Meta: `phone.name_status` = `APPROVED | AVAILABLE_WITHOUT_REVIEW | PENDING_REVIEW | DECLINED | EXPIRED | NONE`, `waba.business_verification_status` = `verified | not_verified | pending | ...`, quality, messaging tier, connection status).
* If the provider call fails the status fields are `null` (UI shows a dash) with `live_data:false` and `status_error`; there is no placeholder value.
* `POST /whatsapp/senders/connect` now answers 422 `use_embedded_signup` with the replacement endpoints (section 1).

```json
GET /whatsapp/senders -> [{"id":"<account id>","account_id":"...","name":"Acme Fibre","number":"+27 82 000 0000","type":"Business (Cloud API)",
  "name_review":"Approved","name_status":"APPROVED","business_verification":"Not verified","business_verification_status":"not_verified",
  "quality_rating":"GREEN","messaging_limit_tier":"TIER_1K","official_business_account":false,"status":"LIVE","live_data":true,"status_error":null,"created_at":"..."}]
```
Webhooks `whatsapp.account.name_status_updated|quality_updated|status_updated` exist but are not consumed (the table reads live).

### Still fake (out of scope, flagged)
`/whatsapp/templates` (created as `APPROVED` instantly), `/whatsapp/flows`, `/whatsapp/groups` (fabricated invite links) and `/whatsapp/conversions` are still per-process in-memory stores. The provider has real template/flow/group APIs (`/v1/whatsapp/templates`, `/flows`, `/wa-groups`).

---

## 6. Lead forms and leads

### Provider support (checked in the OpenAPI)
Yes: `GET/POST /v1/ads/lead-forms`, `GET /v1/ads/lead-forms/{id}/leads`, `GET /v1/ads/leads` (cursor paged), webhook `lead.received` (Meta). Meta Lead Ads and LinkedIn Lead Gen only. **Not available**: lead forms for Google, TikTok, Pinterest or X ads, and no LinkedIn webhook (LinkedIn leads are pulled live, 90-day retention).

### What changed
New module `zernio_leads.py`, tables `marketing_lead_forms`, `marketing_ad_leads` (PK `(tenant_id, lead_id)`, so webhook + sync overlap is idempotent), `marketing_lead_sync_state`.
* Webhook: `lead.received` is routed by the payload's top-level `account` (previously such events had no routing and 400'd), stored with `source:"webhook"`. Post lifecycle events are handled the same way.
* Sync: `POST /ads/lead-forms/sync`, `POST /ads/leads/sync` page through the provider for the tenant's lead-capable accounts (`facebook`, `metaads`, `linkedinads`).
* `contact_id` is reserved for linking a CRM contact; no CRM records are created automatically.

| Endpoint | Notes |
|---|---|
| `GET /ads/lead-forms` | `{forms:[{form_id,account_id,platform,name,status,questions,lead_count,last_lead_at,synced_at}], sync:{last_synced_at,last_error,last_count}, supported_platforms}` |
| `POST /ads/lead-forms/sync` `{account_id?, ad_account_id?}` | -> `{forms_synced, accounts, errors}` |
| `POST /ads/lead-forms` | create a form: `{account_id, name, privacy_policy_url (https), questions:[{type:"EMAIL"\|"PHONE"\|"FULL_NAME"\|"CUSTOM",key?,label?,options?}], platform_specific_data?}` -> `{form_id,name,account_id}`. Not idempotent at the provider. |
| `GET /ads/leads?form_id=&campaign_id=&limit=&offset=` | `{leads:[{lead_id,leadgen_id,form_id,form_name,account_id,platform,ad_id,adset_id,campaign_id,is_organic,fields,created_time,source,contact_id}], total,...}` |
| `POST /ads/leads/sync` `{account_id?, ad_account_id?, form_id?}` | -> `{leads_seen, leads_inserted, accounts, errors}` (LinkedIn needs `ad_account_id`) |

Use a form's `form_id` as `creative.lead_gen_form_id` with goal `lead_generation` in `/ads/create`.

---

## Configuration and migrations

Env (names only):
* `ZERNIO_API_KEY` (existing). `ZERNIO_BASE_URL` is now honoured by the client.
* `OMNIDOME_PUBLIC_URL` (or `PUBLIC_URL` / `PUBLIC_BASE_URL`, or the explicit `MARKETING_CONNECT_CALLBACK_URL`): the public web origin the provider redirects back to. **Required outside dev**, otherwise `/social/connect/start` answers 503. Dev fallback `http://localhost:3000` only when `ENVIRONMENT`/`APP_ENV` is empty/dev/local/test.
* `SECRETS_ENCRYPTION_KEY` (existing): required for picker flows (Facebook/LinkedIn/Pinterest/Google Business/Snapchat/Instagram-FB/WhatsApp-select).
* `MARKETING_CONNECT_STATE_SECRET` (optional, >= 16 chars): signing key for `st`; defaults to a key derived from `ZERNIO_API_KEY`.
* `MARKETING_MEDIA_MAX_BYTES` (optional, default 100 MB).

Operator action in Zernio (not done here; no live calls were allowed): the existing webhook (`/social/webhooks/zernio/inbound`) must also subscribe to `lead.received` and `post.published`, `post.failed`, `post.partial`, `post.scheduled`, `post.cancelled` (`POST /v1/webhooks/settings`) for real-time leads and post status. Sync endpoints cover the gap meanwhile.

Idempotent startup migrations (`security.HARDENING_STATEMENTS`, run once per process under the existing Postgres advisory lock): tables `marketing_connect_sessions`, `marketing_lead_forms`, `marketing_ad_leads`, `marketing_lead_sync_state`; `social_posts` +`publish_error`, `queue_id`, `zernio_post_id`, `timezone` and a one-off lower-casing of `status`; `marketing_campaigns` +`audience_member_count`, `last_audience_send_at`; supporting indexes. The ORM `SocialPost` model carries the same four columns.

Tests: `services/marketing/tests/test_zernio_integration.py` (connect tenant/user/TTL/replay binding, token stripping, wire-format of posts, scheduling guards, blank-date campaigns, audience resolution, ads validation/create/rejection/ownership, WhatsApp status, lead ingest/sync).

---

## Unresolved gaps

1. **Nothing verified live.** All Zernio behaviour is from docs/OpenAPI; first real connect should be watched (especially the headless redirect params per platform and `GET /v1/accounts?profileId=` shape).
2. **Frontend work required**: the callback page, the picker UI, switching the Scheduled view to `/social/posts/scheduled`, the composer using `account_ids`/media presign, the Create Ad modal, lead form views, and a `/svc/marketing` proxy fix for multipart (it uses `request.text()`).
3. SMS/WhatsApp campaign sends do not use audiences yet; only email does.
4. WhatsApp templates, flows, groups, conversions remain in-memory fakes (section 5).
5. Ads: no multi-audience/exclusion targeting, no carousel/dynamic/PMax/Smart+, no post-create sync of mirrored `ad_campaigns` metrics; provider dry run is Meta only.
6. Lead forms: no Google/TikTok/Pinterest/X (provider has none); LinkedIn pull only; no automatic CRM contact creation (`contact_id` reserved).
7. Zernio-native queue endpoints are unused; OmniDome queues are authoritative. A queued post is scheduled at a fixed time, so editing a queue's slots does not reshuffle already scheduled posts.
8. `social_posts.account_id` still points at the legacy `social_media_accounts` table (stub rows per platform) because it is a NOT NULL FK; removing it needs a schema change outside this scope.
9. Provider webhook subscription for `lead.*`/`post.*` events must be enabled by an operator.
10. `GET /social/accounts` (legacy credentials table) is still what the composer uses to list "accounts"; provider-connected accounts are in `GET /social/connected-accounts`.
