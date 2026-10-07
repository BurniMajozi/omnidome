"use client"

/**
 * Typed client for the Zernio-backed marketing contract (docs/zernio-marketing-integration.md):
 * in-app connect flow, posts/scheduling/media, ads, lead forms, WhatsApp senders.
 * Every call returns the real outcome (status + server message). Nothing here fabricates data.
 */

import { getSessionSafe } from "@/lib/supabase/client"
import { loadMarketing, writeMarketing, type MarketingResult } from "@/lib/marketing-api"

// ── Plain-language errors ────────────────────────────────────────────────────

function asText(v: unknown): string {
  if (v === null || v === undefined) return ""
  if (typeof v === "string") return v
  try {
    return JSON.stringify(v)
  } catch {
    return String(v)
  }
}

function prettyField(loc: unknown): string {
  const parts = Array.isArray(loc) ? loc.filter((p) => p !== "body" && p !== "query") : [loc]
  const last = parts[parts.length - 1]
  return typeof last === "string" ? last.replace(/_/g, " ") : ""
}

/**
 * Turn the (possibly JSON-stringified) server detail into one readable sentence.
 * Handles FastAPI validation lists, {message}, {errors:[{field,message}]} and plain strings.
 * Returns plain text only (React escapes it on render).
 */
export function friendlyServerMessage(raw: string | null | undefined, status?: number): string {
  const text = (raw ?? "").trim()
  if (!text) return status === 0 ? "The marketing service is not reachable." : `Request failed${status ? ` (HTTP ${status})` : ""}.`
  let parsed: unknown = null
  if (text.startsWith("{") || text.startsWith("[")) {
    try {
      parsed = JSON.parse(text)
    } catch {
      parsed = null
    }
  }
  if (parsed === null) return text
  if (Array.isArray(parsed)) {
    const msgs = parsed
      .map((e) => {
        if (e && typeof e === "object") {
          const o = e as Record<string, unknown>
          const f = prettyField(o.loc ?? o.field)
          const m = asText(o.msg ?? o.message)
          return f ? `${f}: ${m}` : m
        }
        return asText(e)
      })
      .filter(Boolean)
    return msgs.join("; ") || text
  }
  const o = parsed as Record<string, unknown>
  const lines: string[] = []
  if (typeof o.message === "string" && o.message) lines.push(o.message)
  else if (typeof o.error === "string" && o.error) lines.push(o.error.replace(/_/g, " "))
  if (Array.isArray(o.errors)) {
    for (const e of o.errors) {
      if (e && typeof e === "object") {
        const x = e as Record<string, unknown>
        const f = asText(x.field)
        const m = asText(x.message ?? x.msg)
        lines.push(f ? `${f.replace(/_/g, " ")}: ${m}` : m)
      } else lines.push(asText(e))
    }
  }
  const details = o.details && typeof o.details === "object" ? (o.details as Record<string, unknown>) : null
  if (details?.stage && typeof details.stage === "string") lines.push(`(stage: ${details.stage})`)
  if (typeof o.ref === "string") lines.push(`Ref ${o.ref}`)
  return lines.join(" ") || text
}

/** Machine code of a server error (e.g. "provider_not_configured", "validation_failed"), if any. */
export function serverErrorCode(raw: string | null | undefined): string | null {
  if (!raw || !raw.trim().startsWith("{")) return null
  try {
    const o = JSON.parse(raw) as Record<string, unknown>
    return typeof o.error === "string" ? o.error : null
  } catch {
    return null
  }
}

export function resultMessage(r: { status: number; error: string | null }): string {
  return friendlyServerMessage(r.error, r.status)
}

// ── Connect flow ─────────────────────────────────────────────────────────────

export type ConnectFlow = "oauth" | "oauth_select" | "credentials" | "telegram_code" | "embedded_signup"

export interface ConnectPlatform {
  id: string
  label: string
  flow: ConnectFlow
  category?: string
  coming_soon?: boolean
  connected?: boolean
  note?: string | null
  [k: string]: unknown
}

export interface ConnectPlatformsResponse {
  social: ConnectPlatform[]
  ads: ConnectPlatform[]
  [k: string]: unknown
}

export interface ConnectedAccount {
  account_id: string
  platform: string
  username?: string | null
  display_name?: string | null
  profile_picture?: string | null
  is_active?: boolean
}

export interface SelectionOption {
  id: string
  name?: string
  username?: string
  category?: string
  instagram_username?: string
  urn?: string
  vanity_name?: string
  account_type?: string
  address?: string
  account_id?: string
  phone_number?: string
  waba_id?: string
  name_status?: string
  quality_rating?: string
  [k: string]: unknown
}

export interface ConnectStartResponse {
  status: "redirect" | "already_connected"
  platform: string
  auth_url?: string
  state?: string
  account_id?: string
  expires_in?: number
}

export type ConnectCompleteResponse =
  | { status: "connected"; accounts: ConnectedAccount[]; return_to?: string | null; failed?: Array<{ id: string; message: string }> }
  | {
      status: "selection_required"
      step: string
      selection_type: string
      multiple: boolean
      platform: string
      return_to?: string | null
      options: SelectionOption[]
    }
  | { status: "error"; error: string; reason?: string | null; message?: string | null; user_fixable?: boolean; platform?: string; return_to?: string | null }

export const getConnectPlatforms = () => loadMarketing<ConnectPlatformsResponse>("/social/connect/platforms")

export const startConnect = (body: {
  platform: string
  category: "social" | "ads"
  return_to?: string
  login_method?: string
  login_mode?: string
  reconnect_account_id?: string
}) => writeMarketing<ConnectStartResponse>("POST", "/social/connect/start", body)

export const completeConnect = (state: string, params: Record<string, string>) =>
  writeMarketing<ConnectCompleteResponse>("POST", "/social/connect/complete", { state, params })

export const selectConnect = (state: string, selection_ids: string[], account_type?: string | null) =>
  writeMarketing<ConnectCompleteResponse>("POST", "/social/connect/select", { state, selection_ids, account_type: account_type ?? null })

export const connectBluesky = (identifier: string, app_password: string) =>
  writeMarketing<{ status: string; accounts: ConnectedAccount[] }>("POST", "/social/connect/credentials/bluesky", { identifier, app_password })

export interface TelegramStart {
  status: string
  state: string
  code: string
  bot_username?: string
  expires_in?: number
  instructions?: string[]
}
export const startTelegram = () => writeMarketing<TelegramStart>("POST", "/social/connect/telegram/start", {})
export const telegramStatus = (state: string) =>
  loadMarketing<{ status: "pending" | "connected" | "expired"; accounts?: ConnectedAccount[] }>(
    `/social/connect/telegram/status?state=${encodeURIComponent(state)}`,
    { force: true },
  )

export interface WhatsAppSdkConfig {
  app_id: string
  config_id: string
  branding?: Record<string, unknown>
  state: string
  expires_in?: number
}
export const getWhatsAppSdkConfig = () => loadMarketing<WhatsAppSdkConfig>("/social/connect/whatsapp/sdk-config", { force: true })
export const completeWhatsAppSignup = (body: { state: string; code: string; waba_id?: string; phone_number_id?: string; is_coexistence?: boolean }) =>
  writeMarketing<{ status: string; accounts: ConnectedAccount[] }>("POST", "/social/connect/whatsapp/embedded-signup", body)
export const connectWhatsAppCredentials = (body: { access_token: string; waba_id: string; phone_number_id: string; pin?: string }) =>
  writeMarketing<{ status: string; accounts: ConnectedAccount[]; warning?: string }>("POST", "/social/connect/whatsapp/credentials", body)

export const disconnectAccount = (accountId: string) =>
  writeMarketing<unknown>("DELETE", `/social/connect/accounts/${encodeURIComponent(accountId)}`)

/** sessionStorage handoff so the callback page can return to where the user started. */
const CONNECT_RETURN_KEY = "omnidome.marketing.connect.return"
export function rememberConnectReturn(path: string) {
  try {
    sessionStorage.setItem(CONNECT_RETURN_KEY, path)
  } catch {
    /* storage unavailable: callback falls back to the marketing hub */
  }
}
export function takeConnectReturn(): string | null {
  try {
    const v = sessionStorage.getItem(CONNECT_RETURN_KEY)
    sessionStorage.removeItem(CONNECT_RETURN_KEY)
    return v
  } catch {
    return null
  }
}

/** Only same-origin relative paths are honoured for return_to. */
export function safeReturnPath(p: string | null | undefined, fallback = "/dashboard/marketing"): string {
  if (!p || !p.startsWith("/") || p.startsWith("//") || p.includes("\\")) return fallback
  return p
}

// ── Media upload ─────────────────────────────────────────────────────────────

export interface UploadedMedia {
  public_url: string
  key?: string
  content_type: string
  filename: string
  size: number
  type: "image" | "video" | "file"
}

export const MEDIA_ACCEPT = "image/jpeg,image/png,image/webp,image/gif,video/mp4,video/quicktime,video/webm,video/mpeg,video/x-m4v,video/avi,application/pdf"
const BASE64_FALLBACK_MAX = 6 * 1024 * 1024

async function toBase64(file: File): Promise<string> {
  const buf = new Uint8Array(await file.arrayBuffer())
  let bin = ""
  const chunk = 0x8000
  for (let i = 0; i < buf.length; i += chunk) bin += String.fromCharCode(...buf.subarray(i, i + chunk))
  return btoa(bin)
}

function mediaKind(ct: string): "image" | "video" | "file" {
  return ct.startsWith("image/") ? "image" : ct.startsWith("video/") ? "video" : "file"
}

/**
 * Preferred: presign + browser PUT to the signed URL. If presign or the PUT fails (e.g. CORS on the
 * bucket) and the file is small, fall back to upload-base64 through the proxy. Throws Error with a readable message.
 */
export async function uploadMedia(file: File, presignPath = "/social/media/presign"): Promise<UploadedMedia> {
  const contentType = file.type || "application/octet-stream"
  let presignFailure = ""
  const pre = await writeMarketing<{ upload_url: string; public_url: string; key?: string; content_type?: string }>("POST", presignPath, {
    filename: file.name,
    content_type: contentType,
    size: file.size,
  })
  if (pre.ok && pre.data?.upload_url && pre.data.public_url) {
    try {
      const put = await fetch(pre.data.upload_url, {
        method: "PUT",
        headers: { "Content-Type": pre.data.content_type || contentType },
        body: file,
      })
      if (put.ok) {
        return { public_url: pre.data.public_url, key: pre.data.key, content_type: contentType, filename: file.name, size: file.size, type: mediaKind(contentType) }
      }
      presignFailure = `Direct upload was refused (HTTP ${put.status}).`
    } catch {
      presignFailure = "Direct upload to storage was blocked by the browser."
    }
  } else {
    presignFailure = resultMessage(pre)
    // Validation problems (type/size/not configured) will not be fixed by the fallback.
    if (pre.status === 422 || pre.status === 403 || pre.status === 503) throw new Error(presignFailure)
  }
  if (file.size > BASE64_FALLBACK_MAX) {
    throw new Error(`${presignFailure} The file is too large (${(file.size / 1048576).toFixed(1)} MB) for the fallback upload, which is limited to ${BASE64_FALLBACK_MAX / 1048576} MB.`)
  }
  const b64 = await writeMarketing<{ public_url: string; key?: string; content_type?: string; size?: number; type?: string }>("POST", "/social/media/upload-base64", {
    filename: file.name,
    content_type: contentType,
    data_base64: await toBase64(file),
  })
  if (!b64.ok || !b64.data?.public_url) throw new Error(resultMessage(b64))
  return { public_url: b64.data.public_url, key: b64.data.key, content_type: contentType, filename: file.name, size: file.size, type: mediaKind(contentType) }
}

// ── Posts ────────────────────────────────────────────────────────────────────

export interface PostRow {
  id: string
  content: string
  platforms?: string[]
  status: string
  scheduled_for?: string | null
  published_at?: string | null
  created_at?: string
  media_urls?: string[]
  queue_id?: string | null
  publish_error?: string | null
  zernio_post_id?: string | null
  source?: string
  [k: string]: unknown
}

export interface ScheduledResponse {
  posts: PostRow[]
  total: number
  limit?: number
  offset?: number
  provider_error?: string | null
}

export interface CreatePostBody {
  content: string
  platforms?: string[]
  account_ids?: string[]
  media_urls?: string[]
  status: "draft" | "scheduled" | "published"
  scheduled_for?: string
  timezone?: string
  queue_id?: string | null
  provider_draft?: boolean
  campaign_id?: string | null
}

export const scheduledPostsPath = (params?: { platform?: string; limit?: number; offset?: number; includeProvider?: boolean }) => {
  const q = new URLSearchParams()
  if (params?.platform) q.set("platform", params.platform)
  q.set("limit", String(params?.limit ?? 200))
  if (params?.offset) q.set("offset", String(params.offset))
  if (params?.includeProvider) q.set("include_provider", "true")
  return `/social/posts/scheduled?${q.toString()}`
}

export const createPost = (body: CreatePostBody) => writeMarketing<PostRow>("POST", "/social/posts", body)
export const enqueueNewPost = (queueId: string, body: CreatePostBody) =>
  writeMarketing<PostRow>("POST", `/social/queues/${encodeURIComponent(queueId)}/enqueue`, body)

// ── Campaigns ────────────────────────────────────────────────────────────────

export interface CampaignBody {
  name: string
  channel: string
  description?: string | null
  budget_zar?: number | null
  start_date?: string | null
  end_date?: string | null
  audience_id?: string | null
}
export const createCampaignBody = (body: CampaignBody) => writeMarketing<Record<string, unknown>>("POST", "/campaigns", body)

// ── Ads ──────────────────────────────────────────────────────────────────────

export interface AdsConnection {
  account_id: string
  platform: string
  account_platform?: string
  username?: string | null
  status?: string
}
export interface AdAccount {
  account_id: string
  platform: string
  ad_account_id: string
  name?: string
  currency?: string
  account_status?: string
  minimum_daily_budget?: number | null
  timezone?: string
  balance?: unknown
  selectable?: boolean
  unusable_reason?: string | null
}
export interface AdsAccountsResponse {
  connections: AdsConnection[]
  ad_accounts: AdAccount[]
  errors?: Array<{ message?: string } | string>
  message?: string | null
}
export interface AdGoalInfo {
  id?: string
  label?: string
  requires?: string[]
  [k: string]: unknown
}
export interface AdsGoalsResponse {
  platform?: string
  goals: Array<string | AdGoalInfo>
  [k: string]: unknown
}
export interface AdsOptions {
  cta?: string[]
  call_to_actions?: string[]
  budget_types?: string[]
  genders?: string[]
  age_range?: { min?: number; max?: number }
  limits?: Record<string, number>
  default_status?: string
  [k: string]: unknown
}
export interface TargetingResult {
  id?: string
  key?: string
  name: string
  type?: string
  dimension?: string
  country_code?: string
  [k: string]: unknown
}
export interface AdsAudience {
  id: string
  name: string
  type?: string
  size?: number | null
  [k: string]: unknown
}
export interface LeadFormQuestion {
  type: string
  key?: string
  label?: string
  options?: string[]
}
export interface LeadForm {
  form_id: string
  account_id?: string
  platform?: string
  name?: string
  status?: string
  questions?: unknown
  lead_count?: number
  last_lead_at?: string | null
  synced_at?: string | null
}
export interface LeadFormsResponse {
  forms: LeadForm[]
  sync?: { last_synced_at?: string | null; last_error?: string | null; last_count?: number | null }
  supported_platforms?: string[]
  note?: string | null
  webhook_subscribed?: boolean | null
  [k: string]: unknown
}
export interface AdLead {
  lead_id: string
  form_id?: string
  form_name?: string
  platform?: string
  campaign_id?: string
  is_organic?: boolean
  fields?: unknown
  created_time?: string
  source?: string
  [k: string]: unknown
}
export interface AdLeadsResponse {
  leads: AdLead[]
  total: number
  note?: string | null
  webhook_subscribed?: boolean | null
  [k: string]: unknown
}

export const getAdsAccounts = () => loadMarketing<AdsAccountsResponse>("/ads/accounts")
export const getAdsGoals = (platform: string) => loadMarketing<AdsGoalsResponse>(`/ads/goals?platform=${encodeURIComponent(platform)}`)
export const getAdsOptions = () => loadMarketing<AdsOptions>("/ads/options")

export async function searchTargeting(p: {
  account_id: string
  q: string
  dimension: string
  geo_type?: string
  country_code?: string
}): Promise<MarketingResult<{ results?: TargetingResult[]; items?: TargetingResult[] } | TargetingResult[]>> {
  const q = new URLSearchParams({ account_id: p.account_id, q: p.q, dimension: p.dimension })
  if (p.geo_type) q.set("geo_type", p.geo_type)
  if (p.country_code) q.set("country_code", p.country_code)
  const r = await loadMarketing<{ results?: TargetingResult[]; items?: TargetingResult[] } | TargetingResult[]>(`/ads/targeting/search?${q.toString()}`)
  if (r.state === "ready") return { ok: true, status: 200, data: r.data, error: null }
  return { ok: false, status: "status" in r && r.status ? r.status : 0, data: null, error: "message" in r ? (r.message ?? null) : "Search unavailable" }
}

export const getAdsAudiences = (account_id: string, ad_account_id: string) =>
  loadMarketing<{ audiences?: AdsAudience[] } | AdsAudience[]>(`/ads/audiences?account_id=${encodeURIComponent(account_id)}&ad_account_id=${encodeURIComponent(ad_account_id)}`)

export const adsReach = (body: { account_id: string; ad_account_id: string; targeting: Record<string, unknown> }) =>
  writeMarketing<Record<string, unknown>>("POST", "/ads/targeting/reach", body)
export const adsValidate = (body: Record<string, unknown>) =>
  writeMarketing<{ valid: boolean; errors?: Array<{ field?: string; message?: string }>; warnings?: Array<{ field?: string; message?: string }>; provider_validated?: boolean; provider?: unknown; platform?: string }>(
    "POST",
    "/ads/validate?provider=true",
    body,
  )
export const adsPreview = (body: Record<string, unknown>) => writeMarketing<Record<string, unknown>>("POST", "/ads/preview", body)
export const adsCreate = (body: Record<string, unknown>, idempotencyKey: string) =>
  writeMarketing<{
    status: string
    created_as?: string
    ad?: Record<string, unknown>
    warnings?: Array<{ field?: string; message?: string }>
    local_campaign_id?: string | null
  }>("POST", "/ads/create", { ...body, client_request_id: idempotencyKey })

export const leadFormsPath = "/ads/lead-forms"
export const adLeadsPath = (formId?: string) => `/ads/leads?limit=100${formId ? `&form_id=${encodeURIComponent(formId)}` : ""}`
export const syncLeadForms = (body: { account_id?: string; ad_account_id?: string } = {}) =>
  writeMarketing<{ forms_synced?: number; accounts?: unknown; errors?: unknown[] }>("POST", "/ads/lead-forms/sync", body)
export const syncLeads = (body: { account_id?: string; ad_account_id?: string; form_id?: string } = {}) =>
  writeMarketing<{ leads_seen?: number; leads_inserted?: number; accounts?: unknown; errors?: unknown[] }>("POST", "/ads/leads/sync", body)

// ── Session helper for callback page (state only; no secrets) ────────────────

export async function hasSession(): Promise<boolean> {
  const { data } = await getSessionSafe()
  return Boolean(data.session)
}
