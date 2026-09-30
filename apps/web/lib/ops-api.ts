"use client"

import { useCallback, useEffect, useState } from "react"
import { getSessionSafe } from "@/lib/supabase/client"
import type { Loadable } from "@/lib/service-state"
import { itemsOf, loadableFromOps } from "@/lib/ops-derive"

/**
 * Status-aware GETs for the Retention / Service / IoT / Network modules.
 * Requests go to /svc/<service>/... (identity is attached by AuthFetchInit and
 * signed at the edge); the session read only keeps the same "no hung
 * getSession" guard the other lib/*-api.ts clients have.
 */

export interface OpsOptions {
  /** /svc/<service> is a next.config rewrite (iot, network, retention, communication ...). */
  rewriteProxy?: boolean
  timeoutMs?: number
}

export async function fetchOps<T>(url: string, opts: OpsOptions = {}): Promise<Loadable<T>> {
  let res: Response
  try {
    await getSessionSafe()
    res = await fetch(url, { cache: "no-store", signal: AbortSignal.timeout(opts.timeoutMs ?? 12_000) })
  } catch {
    return loadableFromOps<T>(null, undefined)
  }
  if (!res.ok) {
    let message: string | undefined
    let hasJsonDetail = false
    try {
      const body = await res.json()
      if (typeof body?.detail === "string") {
        message = body.detail
        hasJsonDetail = true
      } else if (typeof body?.error === "string") {
        message = body.error
        hasJsonDetail = true
      }
    } catch {
      /* non-JSON body */
    }
    return loadableFromOps<T>(res.status, undefined, { rewriteProxy: opts.rewriteProxy, hasJsonDetail, message })
  }
  try {
    return loadableFromOps<T>(res.status, (res.status === 204 ? null : await res.json()) as T)
  } catch {
    return { state: "error", status: res.status, message: "Invalid response" }
  }
}

/**
 * Fetches every page of a `{items,total}` list endpoint (page + page_size query
 * params), capped at `maxPages`. Returns rows plus the real total so callers can
 * say when the sample is truncated.
 */
export async function fetchAllPages<T>(
  base: string,
  opts: OpsOptions & { pageSize?: number; maxPages?: number } = {},
): Promise<Loadable<{ rows: T[]; total: number }>> {
  const pageSize = opts.pageSize ?? 100
  const maxPages = opts.maxPages ?? 10
  const sep = base.includes("?") ? "&" : "?"
  const first = await fetchOps<{ items?: T[]; total?: number }>(`${base}${sep}page=1&page_size=${pageSize}`, opts)
  if (first.state !== "ready") return first
  const total = typeof first.data?.total === "number" ? first.data.total : itemsOf<T>(first.data).length
  const rows = itemsOf<T>(first.data)
  const pages = Math.min(maxPages, Math.ceil(total / pageSize))
  if (pages > 1) {
    const rest = await Promise.all(
      Array.from({ length: pages - 1 }, (_, i) =>
        fetchOps<{ items?: T[] }>(`${base}${sep}page=${i + 2}&page_size=${pageSize}`, opts),
      ),
    )
    for (const r of rest) if (r.state === "ready") rows.push(...itemsOf<T>(r.data))
  }
  return { state: "ready", data: { rows, total } }
}

/**
 * Runs `loader` on mount and on `reload()`. Hooks are unconditional and stable;
 * `loader` must be a module-level function (or memoised) so it does not refire.
 */
export function useOps<T>(loader: () => Promise<Loadable<T>>): { value: Loadable<T>; reload: () => void } {
  const [value, setValue] = useState<Loadable<T>>({ state: "loading" })
  const [tick, setTick] = useState(0)

  useEffect(() => {
    let cancelled = false
    loader().then((v) => {
      if (!cancelled) setValue(v)
    })
    return () => {
      cancelled = true
    }
  }, [loader, tick])

  const reload = useCallback(() => {
    setValue({ state: "loading" })
    setTick((t) => t + 1)
  }, [])

  return { value, reload }
}

// ── Endpoints ────────────────────────────────────────────────────────────

const CRM = "/svc/crm"
const COMM = "/svc/communication/api/v1"
const IOT = "/svc/iot/api/iot"
const NET = "/svc/network"

export const loadCrmSummary = () => fetchOps<any>(`${CRM}/customers/dashboard-summary`)
export const loadCrmInsights = () => fetchOps<{ aiRecommendations: any[]; issues: any[] }>(`${CRM}/customers/insights`)
export const loadCrmActivities = () => fetchOps<any[]>(`${CRM}/customers/activities?limit=15`)
export const loadCrmTasks = () => fetchOps<any[]>(`${CRM}/tasks?limit=20`)
export const loadCrmCustomers = () => fetchAllPages<any>(`${CRM}/customers`, { maxPages: 10 })

export const loadEscalations = () => fetchAllPages<any>(`${COMM}/escalations`, { rewriteProxy: true, maxPages: 5 })
export const loadCommTasks = () => fetchAllPages<any>(`${COMM}/tasks`, { rewriteProxy: true, maxPages: 3 })

export const loadIotDevices = () => fetchAllPages<any>(`${IOT}/devices`, { rewriteProxy: true, maxPages: 10 })
export const loadIotAlerts = () => fetchAllPages<any>(`${IOT}/alerts`, { rewriteProxy: true, maxPages: 3 })
export const loadIotEvents = () =>
  fetchOps<{ items: any[]; total: number }>(`${IOT}/events?limit=500`, { rewriteProxy: true })

export const loadNetworkDevices = () => fetchAllPages<any>(`${NET}/devices`, { rewriteProxy: true, maxPages: 10 })
export const loadNetworkMetrics = () =>
  fetchOps<any[]>(`${NET}/performance/metrics?limit=2000`, { rewriteProxy: true })
export const loadNetworkBreaches = () =>
  fetchOps<any[]>(`${NET}/performance/sla-breaches?open_only=true&limit=500`, { rewriteProxy: true })
