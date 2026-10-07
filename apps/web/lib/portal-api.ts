"use client"

import { getSessionSafe } from "@/lib/supabase/client"
import { fetchLoadable } from "@/lib/service-fetch"
import type { Loadable } from "@/lib/service-state"

/**
 * Portal Builder API client (services/portal_builder, contract in
 * docs/portal-builder-api.md). Goes through the Next proxy at /svc/portal_builder;
 * the edge gate (proxy.ts) derives tenant/user from the verified session and the
 * Bearer token is attached by AuthFetchInit, so no identity headers are sent here.
 *
 * Reads return a Loadable (unreachable / denied / error preserved). Writes return a
 * PortalResult carrying the server's `detail` message verbatim.
 */

const API_BASE = "/svc/portal_builder/api/v1/portal"
const TIMEOUT_MS = 20_000

export type PortalPageType = "landing" | "campaign" | "product" | "seo"
export type PortalPageStatus = "draft" | "published" | "archived"

export interface PortalBlock {
  type: string
  heading?: string
  subheading?: string
  image?: string
  body?: string
  images?: Array<{ src: string; alt?: string }>
  [key: string]: unknown
}

export interface PortalPageContent {
  blocks?: PortalBlock[]
  [key: string]: unknown
}

export interface PortalPageSummary {
  id: string
  slug: string
  title: string
  page_type: PortalPageType
  status: PortalPageStatus
  views: number
  conversions: number
  updated_at: string
}

export interface PortalPageList {
  items: PortalPageSummary[]
  total: number
  page: number
  page_size: number
  pages: number
}

export interface PortalPage {
  id: string
  tenant_id?: string
  slug: string
  title: string
  description: string | null
  page_type: PortalPageType
  status: PortalPageStatus
  content: PortalPageContent
  theme: Record<string, unknown> | null
  seo_meta: Record<string, unknown> | null
  custom_css: string | null
  views: number
  conversions: number
  sort_order?: number
  published_version: number | null
  published_at: string | null
  unpublished_at: string | null
  created_at: string
  updated_at: string
}

export interface PortalPageInput {
  slug: string
  title: string
  description?: string
  page_type?: PortalPageType
  content?: PortalPageContent
  theme?: Record<string, unknown>
  seo_meta?: Record<string, unknown>
}

export interface PortalPageUpdate {
  title?: string
  description?: string
  content?: PortalPageContent
  theme?: Record<string, unknown>
  seo_meta?: Record<string, unknown>
  custom_css?: string
  status?: "draft" | "archived"
}

export interface PortalVersion {
  id: string
  version_number: number
  reason: "edit" | "publish"
  created_at: string
}

export interface PortalPublishResult {
  status: "published"
  url: string
  public_path: string
  version: number
  published_at: string
}

export type ShareEmailStatus = "sent" | "suppressed" | "no_mailbox" | "failed"

export interface PortalShareCreated {
  id: string
  page_id: string
  recipient_email: string
  expires_at: string
  share_url: string
  email_status: ShareEmailStatus
  message_id: string | null
}

export interface PortalShare {
  id: string
  recipient_email: string
  expires_at: string
  revoked_at: string | null
  active: boolean
  email_status: ShareEmailStatus | null
  view_count: number
  last_viewed_at: string | null
  created_at: string
}

export interface PortalImportResult {
  source_url: string
  final_url: string
  fetch: { status_code: number; content_type: string; truncated: boolean; redirects: number; elapsed_ms: number }
  content: {
    title: string
    description: string
    lang: string | null
    og_image: string | null
    headings: Array<{ level: number; text: string }>
    paragraphs: string[]
    images: Array<{ src: string; alt?: string }>
    blocks: PortalBlock[]
    stats: { words: number; links: number; images: number }
  }
  suggested_page: { title: string; description: string; content: PortalPageContent }
}

export interface PortalSeoCheck {
  id: string
  label: string
  status: "pass" | "warn" | "fail"
  weight: number
  detail: string
}

export interface PortalSeoAudit {
  url: string
  score: number
  grade: string
  checks: PortalSeoCheck[]
  summary: { pass: number; warn: number; fail: number }
  stats: Record<string, unknown>
  keyword: {
    keyword: string
    in_title: boolean
    in_h1: boolean
    in_meta_description: boolean
    occurrences_in_text: number
    density_pct: number
  } | null
  fetch: Record<string, unknown>
}

export interface PortalKeywordResult {
  provider_configured: boolean
  provider?: string
  message?: string
  error?: string
  keywords: Array<{ keyword: string; search_volume: number | null; cpc: number | null; competition: number | string | null }>
}

export interface PortalAnalyticsSummary {
  period_days: number
  since: string
  pages: { total: number; published: number; draft: number; archived: number }
  views: number
  unique_visitors: number
  submissions: number
  conversion_rate: number
  daily: Array<{ date: string; views: number; submissions: number }>
  top_pages: Array<{ page_id: string; slug: string; title: string; views: number }>
  top_sources: Array<{ source: string; views: number }>
  campaigns: { total: number; running: number }
}

export interface PortalSubmission {
  id: string
  form_data: Record<string, string | number | boolean | null>
  utm: Record<string, unknown> | null
  converted: boolean
  consent_given: boolean
  created_at: string
}

export type PortalResult<T> =
  | { ok: true; data: T; status: number }
  | { ok: false; status: number | null; message: string }

function errorMessage(status: number | null, body: unknown): string {
  if (status === null) return "Portal service is not reachable. Try again shortly."
  const detail = body && typeof body === "object" ? (body as { detail?: unknown }).detail : undefined
  if (typeof detail === "string" && detail) return detail
  if (Array.isArray(detail) && detail.length) {
    const first = detail[0] as { msg?: unknown }
    if (typeof first?.msg === "string") return first.msg
  }
  if (status === 401) return "Your session could not be verified. Sign in again."
  if (status === 403) return "You do not have the portal role needed for this action."
  if (status === 429) return "Too many requests. Wait a moment and retry."
  if (status === 502 || status === 503 || status === 504) return "Portal service is not reachable. Try again shortly."
  return `Portal request failed (HTTP ${status}).`
}

async function portalWrite<T>(path: string, method: string, body?: unknown, timeout = TIMEOUT_MS): Promise<PortalResult<T>> {
  let res: Response
  try {
    await getSessionSafe()
    res = await fetch(`${API_BASE}${path}`, {
      method,
      cache: "no-store",
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: AbortSignal.timeout(timeout),
    })
  } catch {
    return { ok: false, status: null, message: errorMessage(null, null) }
  }
  let parsed: unknown = null
  const text = await res.text().catch(() => "")
  if (text) {
    try {
      parsed = JSON.parse(text)
    } catch {
      parsed = null
    }
  }
  if (!res.ok) return { ok: false, status: res.status, message: errorMessage(res.status, parsed) }
  return { ok: true, data: parsed as T, status: res.status }
}

const read = <T>(path: string): Promise<Loadable<T>> => fetchLoadable<T>(`${API_BASE}${path}`, TIMEOUT_MS)

// ---- Pages ----
export interface PortalDesignDraft {
  title: string
  description: string
  blocks: PortalBlock[]
  theme: Record<string, unknown>
}
export interface PortalDesignContext {
  brief: string
  messages: Array<{ role: "user" | "assistant"; text: string }>
  generated: boolean
}
export const loadPortalDesignContext = (id: string) => read<PortalDesignContext>(`/design/context/${encodeURIComponent(id)}`)
export const savePortalDesignContext = (id: string, context: PortalDesignContext) => portalWrite<PortalDesignContext>(`/design/context/${encodeURIComponent(id)}`, "PUT", context)
export const suggestPortalDesign = (prompt: string, current?: PortalDesignDraft, selected_section?: number, context?: PortalDesignContext) =>
  portalWrite<{ message: string; warnings: string[]; draft: PortalDesignDraft }>("/design/suggest", "POST", { prompt, current, selected_section, context }, 75_000)

export function loadPortalPages(opts: { page?: number; pageSize?: number; pageType?: PortalPageType; status?: PortalPageStatus; search?: string } = {}) {
  const q = new URLSearchParams()
  if (opts.page) q.set("page", String(opts.page))
  if (opts.pageSize) q.set("page_size", String(opts.pageSize))
  if (opts.pageType) q.set("page_type", opts.pageType)
  if (opts.status) q.set("status", opts.status)
  if (opts.search) q.set("search", opts.search)
  const qs = q.toString()
  return read<PortalPageList>(`/pages${qs ? `?${qs}` : ""}`)
}
export const loadPortalPage = (id: string) => read<PortalPage>(`/pages/${encodeURIComponent(id)}`)
export const createPortalPage = (input: PortalPageInput) => portalWrite<PortalPage>("/pages", "POST", input)
export const updatePortalPage = (id: string, updates: PortalPageUpdate) =>
  portalWrite<PortalPage>(`/pages/${encodeURIComponent(id)}`, "PUT", updates)
export const deletePortalPage = (id: string) => portalWrite<{ status: "deleted" }>(`/pages/${encodeURIComponent(id)}`, "DELETE")
export const publishPortalPage = (id: string) =>
  portalWrite<PortalPublishResult>(`/pages/${encodeURIComponent(id)}/publish`, "POST")
export const unpublishPortalPage = (id: string) =>
  portalWrite<{ status: "draft"; unpublished_at: string }>(`/pages/${encodeURIComponent(id)}/unpublish`, "POST")
export const loadPortalVersions = (id: string) =>
  read<{ published_version: number | null; items: PortalVersion[] }>(`/pages/${encodeURIComponent(id)}/versions`)
export const loadPortalSubmissions = (id: string, page = 1, pageSize = 50) =>
  read<{ items: PortalSubmission[]; total: number }>(
    `/pages/${encodeURIComponent(id)}/submissions?page_num=${page}&page_size=${pageSize}`,
  )

// ---- Sharing ----
export const sharePortalPage = (id: string, input: { recipient_email: string; expires_in_hours?: number; message?: string }) =>
  portalWrite<PortalShareCreated>(`/pages/${encodeURIComponent(id)}/share`, "POST", input)
export const loadPortalShares = (id: string) => read<{ items: PortalShare[] }>(`/pages/${encodeURIComponent(id)}/shares`)
export const revokePortalShare = (shareId: string) =>
  portalWrite<{ status: "revoked"; id: string; revoked_at: string }>(`/shares/${encodeURIComponent(shareId)}/revoke`, "POST")

// ---- Import / SEO / analytics ----
export const importPortalSite = (url: string) => portalWrite<PortalImportResult>("/import/site", "POST", { url })
export const auditPortalSeo = (url: string, keyword?: string) =>
  portalWrite<PortalSeoAudit>("/seo/audit", "POST", keyword ? { url, keyword } : { url })
export const lookupPortalKeywords = (keywords: string[]) =>
  portalWrite<PortalKeywordResult>("/seo/keywords", "POST", { keywords })
export const loadPortalAnalytics = (days = 30) => read<PortalAnalyticsSummary>(`/analytics/summary?days=${days}`)

export interface PortalCampaign {
  id: string; name: string; page_id: string | null; campaign_type: string; status: string
  budget_zar: number; spent_zar: number; created_at: string; stats: Record<string, unknown> | null
}
export interface PortalSeoProfile {
  id: string; name: string; target_keywords: string[]; sitemap_enabled: boolean
  robots_txt: string | null; structured_data: Record<string, unknown> | null; analytics_id: string | null
  updated_at: string
}
export const loadPortalCampaigns = (page = 1) => read<{items: PortalCampaign[]; total: number; pages: number}>(`/campaigns?page=${page}&page_size=20`)
export const createPortalCampaign = (input: {name: string; page_id?: string; campaign_type: string; budget_zar: number; content: Record<string, unknown>}) => portalWrite<PortalCampaign>("/campaigns", "POST", input)
export const transitionPortalCampaign = (id: string, action: "launch" | "complete") => portalWrite<unknown>(`/campaigns/${encodeURIComponent(id)}/${action}`, "POST")
export const loadPortalSeoProfiles = () => read<PortalSeoProfile[]>("/seo-profiles")
export const createPortalSeoProfile = (input: Omit<PortalSeoProfile, "id" | "updated_at">) => portalWrite<PortalSeoProfile>("/seo-profiles", "POST", input)

/** URL path (relative to the web origin) where a published page is served. */
export function portalPublicPath(slug: string): string {
  return `/portal/${encodeURIComponent(slug)}`
}

/** Lowercase slug that satisfies the backend regex; returns "" when nothing usable remains. */
export function slugify(input: string): string {
  return input
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 100)
    .replace(/-+$/g, "")
}
