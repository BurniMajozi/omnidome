"use client"

import { getSessionSafe } from "@/lib/supabase/client"

/**
 * Market Watch API client (competitor pricing monitor). Reaches
 * services/fno_intelligence /api/fno/market through the /svc/fno-intelligence
 * rewrite in next.config.mjs.
 */

const API_BASE = "/svc/fno-intelligence/api/fno/market"
const FALLBACK_TENANT_ID = "00000000-0000-0000-0000-000000000001"
const FALLBACK_USER_ID = "00000000-0000-0000-0000-000000000001"

async function getAuthHeaders(): Promise<Record<string, string>> {
  const { data } = await getSessionSafe()
  const tenantId =
    data.session?.user?.user_metadata?.tenant_id ??
    data.session?.user?.app_metadata?.tenant_id ??
    FALLBACK_TENANT_ID
  const userId = data.session?.user?.id ?? FALLBACK_USER_ID
  return { "x-tenant-id": tenantId, "x-user-id": userId }
}

export class MarketApiError extends Error {
  constructor(public status: number, message: string) {
    super(message)
  }
}

async function fetchMarket<T>(path: string, init?: RequestInit, timeoutMs = 15000): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    cache: "no-store",
    ...init,
    signal: init?.signal
      ? AbortSignal.any([init.signal, AbortSignal.timeout(timeoutMs)])
      : AbortSignal.timeout(timeoutMs),
    headers: { ...(await getAuthHeaders()), "Content-Type": "application/json", ...init?.headers },
  })
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    const detail = typeof body?.detail === "string" ? body.detail : `Request failed (${res.status})`
    throw new MarketApiError(res.status, detail)
  }
  return res.status === 204 ? (undefined as T) : res.json()
}

export type WatchCategory = "fibre" | "lte" | "wireless" | "other"
export type SignalType = "price_change" | "new_plan" | "removed_plan" | "speed_change"

export interface MarketWatch {
  id: string
  competitor_name: string
  url: string
  category: WatchCategory
  active: boolean
  last_scraped_at: string | null
  last_status: "never" | "scanning" | "ok" | "no_plans_found" | "failed"
  last_error: string | null
  created_at: string | null
}

export interface WatchInput {
  competitor_name: string
  url: string
  category: WatchCategory
  active?: boolean
}

export interface MarketSignal {
  id: string
  watch_id: string
  competitor_name: string | null
  type: SignalType
  plan_name: string | null
  before: Record<string, unknown> | null
  after: Record<string, unknown> | null
  detected_at: string | null
  acknowledged: boolean
}

export interface CompareRow {
  watch_id: string
  competitor_name: string
  category: WatchCategory
  scraped_at: string | null
  plan_name: string
  speed_down_mbps: number | null
  speed_up_mbps: number | null
  price_zar: number | null
  contention: string | null
  notes: string | null
}

export interface ScanResult {
  watch: MarketWatch
  plans: unknown[]
  signals: MarketSignal[]
}

// A scan can take Firecrawl up to ~3 minutes.
const SCAN_TIMEOUT_MS = 200_000

export const listWatches = () => fetchMarket<MarketWatch[]>("/watches")
export const createWatch = (data: WatchInput) =>
  fetchMarket<MarketWatch>("/watches", { method: "POST", body: JSON.stringify(data) })
export const updateWatch = (id: string, data: Partial<WatchInput>) =>
  fetchMarket<MarketWatch>(`/watches/${id}`, { method: "PATCH", body: JSON.stringify(data) })
export const deleteWatch = (id: string) => fetchMarket<void>(`/watches/${id}`, { method: "DELETE" })
export const scanWatch = (id: string) =>
  fetchMarket<ScanResult>(`/watches/${id}/scan`, { method: "POST" }, SCAN_TIMEOUT_MS)
export const scanAll = () =>
  fetchMarket<{ scanned: number; results: unknown[] }>("/scan-all", { method: "POST" }, SCAN_TIMEOUT_MS * 3)
export const listSignals = (unacknowledgedOnly = false) =>
  fetchMarket<MarketSignal[]>(`/signals${unacknowledgedOnly ? "?unacknowledged=true" : ""}`)
export const acknowledgeSignal = (id: string) =>
  fetchMarket<MarketSignal>(`/signals/${id}/acknowledge`, { method: "POST" })
export const getCompare = () => fetchMarket<{ rows: CompareRow[] }>("/compare").then((r) => r.rows)
