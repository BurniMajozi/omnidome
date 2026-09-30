"use client"

import { useCallback, useEffect, useState } from "react"
import { getSessionSafe } from "@/lib/supabase/client"
import type { Loadable } from "@/lib/service-state"
import { itemsOf, loadableFromOps, planPages, type PagedMeta } from "@/lib/ops-derive"

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
  return (await fetchOpsMeta<T>(url, opts)).result
}

/** fetchOps plus the X-Total-Count response header (null when absent/unreadable). */
export async function fetchOpsMeta<T>(
  url: string,
  opts: OpsOptions = {},
): Promise<{ result: Loadable<T>; totalCount: number | null }> {
  let res: Response
  try {
    await getSessionSafe()
    res = await fetch(url, { cache: "no-store", signal: AbortSignal.timeout(opts.timeoutMs ?? 12_000) })
  } catch {
    return { result: loadableFromOps<T>(null, undefined), totalCount: null }
  }
  const header = res.headers.get("X-Total-Count")
  const parsed = header === null || header.trim() === "" ? NaN : Number(header)
  const totalCount = Number.isFinite(parsed) && parsed >= 0 ? parsed : null
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
    return { result: loadableFromOps<T>(res.status, undefined, { rewriteProxy: opts.rewriteProxy, hasJsonDetail, message }), totalCount }
  }
  try {
    return { result: loadableFromOps<T>(res.status, (res.status === 204 ? null : await res.json()) as T), totalCount }
  } catch {
    return { result: { state: "error", status: res.status, message: "Invalid response" }, totalCount }
  }
}

export type PagedResult<T> = PagedMeta & {
  rows: T[]
  /** Same array as `rows` (alias). */
  items: T[]
}

/**
 * Fetches every page of a `{items,total}` list endpoint (page + page_size query
 * params), capped at `maxPages`. Never silently lossy:
 * - `total` is the server's (body `total`, else X-Total-Count), not the loaded count;
 * - `truncated` says the page cap stopped the walk;
 * - `failedPages` lists pages 2+ that failed (a failed FIRST page fails the whole load).
 * Without a server total it walks sequentially until a short page or the cap.
 */
export async function fetchAllPages<T>(
  base: string,
  opts: OpsOptions & { pageSize?: number; maxPages?: number } = {},
): Promise<Loadable<PagedResult<T>>> {
  const pageSize = opts.pageSize ?? 100
  const maxPages = opts.maxPages ?? 10
  const sep = base.includes("?") ? "&" : "?"
  const pageUrl = (n: number) => `${base}${sep}page=${n}&page_size=${pageSize}`
  const { result: first, totalCount } = await fetchOpsMeta<{ items?: T[]; total?: number }>(pageUrl(1), opts)
  if (first.state !== "ready") return first
  const rows = [...itemsOf<T>(first.data)]
  const bodyTotal = (first.data as { total?: unknown } | null)?.total
  const serverTotal = typeof bodyTotal === "number" ? bodyTotal : totalCount
  const failedPages: number[] = []
  let truncated = false
  if (serverTotal !== null) {
    const plan = planPages(serverTotal, pageSize, maxPages)
    truncated = plan.truncated
    if (plan.pages > 1) {
      const rest = await Promise.all(
        Array.from({ length: plan.pages - 1 }, (_, i) => fetchOps<{ items?: T[] }>(pageUrl(i + 2), opts)),
      )
      rest.forEach((r, i) => {
        if (r.state === "ready") rows.push(...itemsOf<T>(r.data))
        else failedPages.push(i + 2)
      })
    }
  } else {
    let page = 1
    let lastLen = rows.length
    while (lastLen >= pageSize) {
      if (page >= maxPages) {
        truncated = true
        break
      }
      page += 1
      const r = await fetchOps<{ items?: T[] }>(pageUrl(page), opts)
      if (r.state !== "ready") {
        failedPages.push(page)
        break
      }
      const got = itemsOf<T>(r.data)
      rows.push(...got)
      lastLen = got.length
    }
  }
  return {
    state: "ready",
    data: {
      rows,
      items: rows,
      loaded: rows.length,
      total: serverTotal ?? rows.length,
      totalKnown: serverTotal !== null,
      truncated,
      failedPages,
    },
  }
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
