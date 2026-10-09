"use client"

import { getSessionSafe } from "@/lib/supabase/client"

/**
 * Analytics & AI client (Research, Competitor analysis, Campaign analysis, credit usage).
 * Contract: docs/analytics-ai-api.md. Reaches services/fno_intelligence
 * /api/fno/analytics through the /svc/fno-intelligence rewrite.
 */

const API_BASE = "/svc/fno-intelligence/api/fno/analytics"
const FALLBACK_ID = "00000000-0000-0000-0000-000000000001"

async function getAuthHeaders(): Promise<Record<string, string>> {
  const { data } = await getSessionSafe()
  const tenantId =
    data.session?.user?.user_metadata?.tenant_id ?? data.session?.user?.app_metadata?.tenant_id ?? FALLBACK_ID
  const userId = data.session?.user?.id ?? FALLBACK_ID
  return { "x-tenant-id": tenantId, "x-user-id": userId }
}

export class AnalyticsApiError extends Error {
  constructor(public status: number, message: string) {
    super(message)
  }
  get forbidden() {
    return this.status === 403
  }
  get capped() {
    return this.status === 429
  }
  get unreachable() {
    return this.status === 0 || this.status === 502 || this.status === 503 || this.status === 504
  }
}

function detailMessage(body: unknown, status: number): string {
  const d = (body as { detail?: unknown } | null)?.detail
  if (typeof d === "string") return d
  if (Array.isArray(d)) {
    const parts = d.map((x) => (typeof x === "object" && x && "msg" in x ? String((x as { msg: unknown }).msg) : "")).filter(Boolean)
    if (parts.length) return parts.join("; ")
  }
  return `Request failed (${status})`
}

async function raw(path: string, init?: RequestInit, timeoutMs = 20000): Promise<Response> {
  let res: Response
  try {
    res = await fetch(`${API_BASE}${path}`, {
      cache: "no-store",
      ...init,
      signal: init?.signal ? AbortSignal.any([init.signal, AbortSignal.timeout(timeoutMs)]) : AbortSignal.timeout(timeoutMs),
      headers: { ...(await getAuthHeaders()), ...(init?.body ? { "Content-Type": "application/json" } : {}), ...init?.headers },
    })
  } catch {
    throw new AnalyticsApiError(0, "The analytics service is not reachable.")
  }
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    throw new AnalyticsApiError(res.status, detailMessage(body, res.status))
  }
  return res
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await raw(path, init)
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T)
}

const post = <T>(path: string, body?: unknown) =>
  call<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) })
const put = <T>(path: string, body: unknown) => call<T>(path, { method: "PUT", body: JSON.stringify(body) })
const del = (path: string) => call<void>(path, { method: "DELETE" })

function qs(params: Record<string, string | number | undefined | null>): string {
  const u = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== "") u.set(k, String(v))
  const s = u.toString()
  return s ? `?${s}` : ""
}

/** Only http(s) URLs are ever rendered as links. */
export function safeHttpUrl(u: unknown): string | null {
  if (typeof u !== "string") return null
  try {
    const p = new URL(u)
    return p.protocol === "https:" || p.protocol === "http:" ? p.toString() : null
  } catch {
    return null
  }
}

export interface Paged<T> {
  total: number
  limit: number
  offset: number
  items: T[]
}

// ── Usage ───────────────────────────────────────────────────────────
export interface Usage {
  period: string
  month: { used: number; cap: number; remaining: number }
  day: { used: number; cap: number; remaining: number }
  custom_limits: boolean
  by_feature?: Record<string, number>
  note?: string
}
export const getUsage = () => call<Usage>("/usage")
export const setUsageLimits = (b: { monthly_cap: number | null; daily_cap: number | null }) => put<Usage>("/usage/limits", b)

// ── Research ────────────────────────────────────────────────────────
export type RunStatus = "queued" | "running" | "done" | "failed"
export type Depth = "quick" | "standard" | "deep"
export interface ResearchSource {
  id: string
  title: string
  url: string
  domain: string
  fetched_at: string
  snippet?: string
}
export interface ResearchFinding {
  claim: string
  source_ids: string[]
  quote?: { text: string; source_id: string } | null
}
export interface ResearchReport {
  summary: string
  key_findings: ResearchFinding[]
  limitations: string[]
  stripped_claims?: number
  cited_source_ids?: string[]
}
export interface ResearchRun {
  id: string
  question: string
  depth: Depth
  params?: { max_sources?: number; country?: string; recency?: string }
  status: RunStatus
  error: string | null
  credits_used: number
  model_used?: string | null
  source_count: number
  summary: string | null
  created_at: string
  started_at?: string | null
  finished_at: string | null
  report?: ResearchReport | null
  sources?: ResearchSource[] | null
}
export interface ResearchInput {
  question: string
  depth: Depth
  max_sources?: number
  country?: string
  recency?: "day" | "week" | "month" | "year"
}
export const startResearch = (b: ResearchInput) => post<ResearchRun>("/research", b)
export const getResearch = (id: string) => call<ResearchRun>(`/research/${id}`)
export const listResearch = (limit = 25, offset = 0) => call<Paged<ResearchRun>>(`/research${qs({ limit, offset })}`)
export const deleteResearch = (id: string) => del(`/research/${id}`)
export async function exportResearchMarkdown(id: string): Promise<string> {
  const res = await raw(`/research/${id}/export`)
  return res.text()
}

// ── Competitors ─────────────────────────────────────────────────────
export type ScanStatus = "never" | "scanning" | "ok" | "no_data" | "failed"
export interface Competitor {
  id: string
  name: string
  website: string
  pricing_page_url: string | null
  promo_page_url: string | null
  social_urls: string[]
  active: boolean
  scan_status: ScanStatus
  last_error: string | null
  last_scanned_at: string | null
  created_at: string
}
export interface CompetitorInput {
  name: string
  website: string
  pricing_page_url?: string | null
  promo_page_url?: string | null
  active?: boolean
}
export interface PlanChange {
  id: string
  competitor_id: string
  competitor_name?: string
  snapshot_id: string
  change_type:
    | "price_up"
    | "price_down"
    | "new_plan"
    | "removed_plan"
    | "new_promotion"
    | "ended_promotion"
    | "promotion_changed"
    | "plan_attribute_change"
  subject: string
  old_value: string | null
  new_value: string | null
  abs_change?: number | null
  pct_change?: number | null
  currency?: string | null
  verified?: boolean
  source_url?: string | null
  detected_at: string
}
export interface CompetitorOverviewItem extends Competitor {
  plans_count: number
  promotions_count: number
  latest_snapshot_at: string | null
  latest_changes: PlanChange[]
}
export interface Plan {
  plan_key: string
  plan_name: string
  price_amount: number | null
  price_text: string | null
  currency: string | null
  billing_period: string | null
  speed_text: string | null
  speed_down_mbps: number | null
  data_text: string | null
  contract_term: string | null
  setup_fee_text: string | null
  promo_text: string | null
  valid_until: string | null
  price_verified: boolean
  source_url: string | null
}
export interface Promotion {
  promo_key: string
  title: string
  description: string | null
  discount_text: string | null
  valid_until: string | null
  source_url: string | null
}
export interface Snapshot {
  id: string
  scanned_at: string
  extraction_method: string
  plans_count: number
  promotions_count: number
  pages: { url: string; kind: string; fetched_at: string; status: string; error: string | null }[]
  plans: Plan[]
  promotions: Promotion[]
}
export interface PricingHistory {
  snapshots_considered: number
  plans: {
    plan_key: string
    plan_name: string
    currency: string | null
    points: { scanned_at: string; price_amount: number | null; price_verified: boolean; source_url?: string | null }[]
  }[]
}
export interface PromotionsView {
  as_of: string
  active: Promotion[]
  plan_promos: { plan_name: string; promo_text: string | null; valid_until: string | null; source_url: string | null }[]
  ended: { title: string; ended_detected_at: string; last_seen_value: string | null }[]
}
export type ActivityItem =
  | ({ kind: "change"; at: string } & PlanChange)
  | { kind: "scan"; at: string; competitor_id: string; competitor_name: string; snapshot_id: string; plans_count: number; promotions_count: number }

export const getCompetitorOverview = () => call<{ count: number; competitors: CompetitorOverviewItem[] }>("/competitors/overview")
export const getCompetitorActivity = (limit = 50) => call<{ items: ActivityItem[] }>(`/competitors/activity${qs({ limit })}`)
export const createCompetitor = (b: CompetitorInput) => post<Competitor>("/competitors", b)
export const updateCompetitor = (id: string, b: Partial<CompetitorInput>) => put<Competitor>(`/competitors/${id}`, b)
export const getCompetitor = (id: string) => call<Competitor>(`/competitors/${id}`)
export const deleteCompetitor = (id: string) => del(`/competitors/${id}`)
export const scanCompetitor = (id: string) =>
  post<{ competitor_id: string; scan_status: ScanStatus; estimated_credits: number; message: string }>(`/competitors/${id}/scan`)
export const getSnapshots = (id: string, limit = 20, offset = 0) => call<Paged<Snapshot>>(`/competitors/${id}/snapshots${qs({ limit, offset })}`)
export const getChanges = (id: string, limit = 50, offset = 0) => call<Paged<PlanChange>>(`/competitors/${id}/changes${qs({ limit, offset })}`)
export const getPricingHistory = (id: string) => call<PricingHistory>(`/competitors/${id}/pricing-history`)
export const getPromotions = (id: string) => call<PromotionsView>(`/competitors/${id}/promotions`)

// ── Campaign analysis ───────────────────────────────────────────────
export type Sentiment = "positive" | "neutral" | "negative"
export interface ThemeExample {
  excerpt: string
  url: string
  domain: string
  sentiment: Sentiment
  date: string | null
}
export interface Theme {
  theme: string
  count: number
  avg_score: number
  positive: number
  negative: number
  polarity: "praised" | "complained" | "mixed"
  examples: ThemeExample[]
}
export interface CampaignAggregate {
  total_items: number
  overall: {
    label: string
    avg_score: number
    split: Record<Sentiment, { count: number; pct: number }>
  }
  top_praised_themes: Theme[]
  top_complained_themes: Theme[]
  all_themes?: Theme[]
  trend: { period: string; count: number; avg_score: number; positive: number; neutral: number; negative: number }[]
  undated_items: number
  volume_by_source: { domain: string; count: number }[]
  volume_by_type?: Record<string, number>
  ratings?: { count: number; avg: number | null }
  coverage?: Record<string, number>
}
export interface CampaignAnalysis {
  id: string
  name: string
  subject: string
  own_campaign_id: string | null
  competitor_id: string | null
  keywords: string[]
  sources: "auto" | string[]
  status: RunStatus
  error: string | null
  item_count: number
  credits_used: number
  run_count: number
  last_run_at: string | null
  created_at: string
  aggregate?: CampaignAggregate | null
  overall?: { label?: string } | string | null
  limitations?: string[]
}
export interface CampaignInput {
  name: string
  subject?: string
  own_campaign_id?: string | null
  keywords?: string[]
  sources?: "auto" | string[]
  competitor_id?: string | null
  country?: string
}
export interface CampaignItem {
  id: string
  url: string
  domain: string
  source_type: string
  excerpt: string
  rating: number | null
  date: string | null
  sentiment: Sentiment
  sentiment_score: number
  themes: string[]
  fetched_at: string
}
export const createCampaignAnalysis = (b: CampaignInput) => post<CampaignAnalysis>("/campaign-analyses", b)
export const listCampaignAnalyses = (limit = 50, offset = 0) => call<Paged<CampaignAnalysis>>(`/campaign-analyses${qs({ limit, offset })}`)
export const getCampaignAnalysis = (id: string) => call<CampaignAnalysis>(`/campaign-analyses/${id}`)
export const getCampaignItems = (id: string, limit = 25, offset = 0) => call<Paged<CampaignItem>>(`/campaign-analyses/${id}/items${qs({ limit, offset })}`)
export const refreshCampaignAnalysis = (id: string) => post<CampaignAnalysis>(`/campaign-analyses/${id}/refresh`)
export const deleteCampaignAnalysis = (id: string) => del(`/campaign-analyses/${id}`)
