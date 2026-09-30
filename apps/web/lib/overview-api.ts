"use client"

import { useCallback, useMemo } from "react"
import { fetchOps, fetchOpsMeta, useOps } from "@/lib/ops-api"
import { getSessionSafe } from "@/lib/supabase/client"
import { createTtlCache } from "@/lib/request-cache"
import type { Loadable } from "@/lib/service-state"
import { listOf, readDealSummary, stageNamesInOrder, type DealRow, type DealSummary } from "@/lib/overview-derive"

/**
 * Status-aware loaders for the Overview page. Every loader returns a
 * Loadable so the UI can tell loading / ready (real zeros OK) / service not
 * running / error apart.
 * Identity is attached to /api/* and /svc/* by AuthFetchInit.
 *
 * Each request is made once per page: use `useSharedOps(key, loader)` (not
 * `useOps`) so two components asking for the same URL share one in-flight
 * request, and a fresh result is reused for 30s (see lib/request-cache.ts).
 */

// ── Shared request cache (per identity + URL, 30s TTL, in-flight dedupe) ──

const sharedCache = createTtlCache(30_000)
let lastIdentity = "anon"

async function identityKey(): Promise<string> {
  try {
    const { data } = await getSessionSafe()
    lastIdentity = data.session?.user?.id ?? "anon"
  } catch {
    /* keep the last known identity */
  }
  return lastIdentity
}

/** Runs `loader` once per identity+key within the TTL; only `ready` results are kept. */
export async function cachedLoad<T>(key: string, loader: () => Promise<Loadable<T>>): Promise<Loadable<T>> {
  const id = await identityKey()
  return sharedCache.get(`${id}|${key}`, loader, (r) => r.state === "ready")
}

export function invalidateShared(key?: string): void {
  sharedCache.invalidate(key === undefined ? undefined : `${lastIdentity}|${key}`)
}

/** `useOps` through the shared cache. `key` is the request URL; `loader` must be module-level/stable. */
export function useSharedOps<T>(
  key: string,
  loader: () => Promise<Loadable<T>>,
): { value: Loadable<T>; reload: () => void } {
  const wrapped = useMemo(() => () => cachedLoad(key, loader), [key, loader])
  const { value, reload } = useOps(wrapped)
  const reloadFresh = useCallback(() => {
    invalidateShared(key)
    reload()
  }, [key, reload])
  return { value, reload: reloadFresh }
}

// ── Endpoints (keys are the URLs) ─────────────────────────────────────────

/** Deals: bounded request (server max 1000) + X-Total-Count so truncation is visible. */
export const DEALS_LIMIT = 1000
export const DEALS_URL = `/api/sales/deals?limit=${DEALS_LIMIT}`

export interface DealsPage {
  rows: DealRow[]
  /** X-Total-Count; null when the proxy did not pass it. */
  total: number | null
}

export const loadOverviewDeals = async (): Promise<Loadable<DealsPage>> => {
  const { result, totalCount } = await fetchOpsMeta<unknown>(DEALS_URL, { timeoutMs: 12_000 })
  if (result.state !== "ready") return result
  const rows = listOf<DealRow>(result.data)
  if (rows === null) return { state: "error", status: 200, message: "Unexpected response" }
  return { state: "ready", data: { rows, total: totalCount } }
}

/** Exact headline figures without pulling rows. A non-200 just means "fall back to rows". */
export const DEAL_SUMMARY_URL = "/svc/sales/deals/summary"
export const loadOverviewDealSummary = async (): Promise<Loadable<DealSummary>> => {
  const r = await fetchOps<unknown>(DEAL_SUMMARY_URL, { rewriteProxy: true, timeoutMs: 12_000 })
  if (r.state !== "ready") return r
  const s = readDealSummary(r.data)
  return s ? { state: "ready", data: s } : { state: "error", status: 200, message: "Unexpected response" }
}

/** Real pipeline stage order (by sort_order). */
export const STAGES_URL = "/svc/sales/pipeline/stages"
export const loadOverviewStageOrder = async (): Promise<Loadable<string[]>> => {
  const r = await fetchOps<unknown>(STAGES_URL, { rewriteProxy: true })
  return r.state === "ready" ? { state: "ready", data: stageNamesInOrder(r.data) } : r
}

/** page_size=1: only `total` is needed. */
export const CRM_TOTAL_URL = "/svc/crm/customers?page=1&page_size=1"
export const loadCrmCustomerTotal = () =>
  fetchOps<{ total?: number; items?: unknown[] } | unknown[]>(CRM_TOTAL_URL)

export const CAMPAIGNS_URL = "/svc/marketing/campaigns?limit=200"
export const loadOverviewCampaigns = () => fetchOps<Array<{ status?: string }>>(CAMPAIGNS_URL)

export const EMPLOYEES_URL = "/svc/hr/employees"
export const loadOverviewEmployees = () => fetchOps<Array<{ status?: string }>>(EMPLOYEES_URL)

export const CC_SESSIONS_URL = "/svc/call-center/sessions"
export const loadCcSessions = () => fetchOps<unknown>(CC_SESSIONS_URL, { rewriteProxy: true })

export const CC_QUEUES_URL = "/svc/call-center/queues"
export const loadCcQueues = () => fetchOps<unknown>(CC_QUEUES_URL, { rewriteProxy: true })

/** Keys for the ops-api loaders the Overview shares (same URLs those loaders request). */
export const ESCALATIONS_KEY = "/svc/communication/api/v1/escalations"
export const NETWORK_DEVICES_KEY = "/svc/network/devices"
export const CRM_SUMMARY_KEY = "/svc/crm/customers/dashboard-summary"
export const CRM_INSIGHTS_KEY = "/svc/crm/customers/insights"
export const CRM_ACTIVITIES_KEY = "/svc/crm/customers/activities?limit=15"
