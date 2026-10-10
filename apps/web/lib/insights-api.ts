/**
 * Panel insights client (orchestrator /api/insights, docs/insights-and-jev.md).
 *
 * One engine feeds every panel's "AI recommendations" and executive overview. This file holds the wire types, the
 * calls, and a small shared store so several widgets on one panel (summary tab + recommendations column) share a
 * single request instead of each fetching.
 */
"use client"

import { useCallback, useEffect, useSyncExternalStore } from "react"
import { getSessionSafe } from "@/lib/supabase/client"

const BASE = "/api/orchestrator/insights"

export interface InsightEvidence {
  id: string
  ref?: string
  kind: "card" | "fact" | "personal" | "skill"
  title: string
  module?: string
  as_of?: string | null
  deep_link?: string | null
  stale?: boolean
  fact_kind?: string
  period?: string
}

export interface InsightAction {
  kind: "open" | "draft_task" | "ask_agent"
  label: string
  link?: string
  draft?: string
  executes: false
}

export interface InsightRecommendation {
  id: string
  title: string
  why: string
  priority: "high" | "medium" | "low"
  effort: "high" | "medium" | "low"
  impact: "high" | "medium" | "low"
  owner_hint: string
  suggested_action: InsightAction
  confidence: number
  evidence: InsightEvidence[]
}

export interface InsightKpi {
  id: string
  label: string
  value: string
  delta: string | null
  period: string
  kind: string
  scope: string | null
  as_of: string | null
  stale: boolean
  deep_link: string | null
}

export interface InsightVerification {
  status: "verified" | "weak" | "failed" | "unavailable" | "skipped"
  probability?: number
  reason?: string
}

export interface PanelInsights {
  id: string
  module: string
  label: string
  summary: string
  recommendations: InsightRecommendation[]
  kpis: InsightKpi[]
  risks: { text: string; evidence: InsightEvidence[] }[]
  evidence: InsightEvidence[]
  generated_at: string
  as_of: string | null
  stale: boolean
  degraded: string | null
  degraded_reasons: string[]
  model: string | null
  source: "llm" | "template" | "none"
  used_skills: string[]
  verified: boolean
  verification: InsightVerification
  empty: boolean
  empty_reason?: string
  cached: boolean
  refreshing?: boolean
  notice?: string
}

export type InsightVerdict = "helpful" | "not_helpful" | "dismissed" | "acted"

export class InsightsError extends Error {
  constructor(message: string, public status: number | null, public allowed?: string[]) {
    super(message)
  }
}

async function authFetch(url: string, init: RequestInit = {}): Promise<Response> {
  const { data } = await getSessionSafe()
  const headers = new Headers(init.headers)
  if (data.session?.access_token) headers.set("Authorization", `Bearer ${data.session.access_token}`)
  if (init.body) headers.set("Content-Type", "application/json")
  return fetch(url, { ...init, headers, signal: init.signal ?? AbortSignal.timeout(90_000) })
}

async function failure(res: Response): Promise<InsightsError> {
  let detail: any = null
  try {
    detail = (await res.json())?.detail
  } catch {
    /* body not JSON */
  }
  const message =
    typeof detail === "string" ? detail : (detail?.message as string | undefined) ?? `Insights request failed (${res.status})`
  return new InsightsError(message, res.status, Array.isArray(detail?.allowed) ? detail.allowed : undefined)
}

export async function fetchInsights(
  module: string,
  opts: { scope?: string; refresh?: boolean | "background" } = {},
): Promise<PanelInsights> {
  let res: Response
  try {
    res = await authFetch(`${BASE}/panel`, {
      method: "POST",
      body: JSON.stringify({ module, scope: opts.scope ?? "", refresh: opts.refresh ?? false }),
    })
  } catch {
    throw new InsightsError("The insights service is not reachable.", null)
  }
  if (!res.ok) throw await failure(res)
  return (await res.json()) as PanelInsights
}

export async function sendInsightFeedback(
  insightId: string,
  verdict: InsightVerdict,
  opts: { recId?: string; note?: string } = {},
): Promise<void> {
  const res = await authFetch(`${BASE}/${encodeURIComponent(insightId)}/feedback`, {
    method: "POST",
    body: JSON.stringify({ verdict, rec_id: opts.recId ?? null, note: opts.note ?? null }),
  })
  if (!res.ok) throw await failure(res)
}

// ── shared store ─────────────────────────────────────────────────────────────

export interface InsightsState {
  status: "idle" | "loading" | "ready" | "error" | "denied"
  data: PanelInsights | null
  error: string | null
  allowed: string[]
  refreshing: boolean
  hidden: string[] // recommendation ids dismissed in this session (the server also remembers them)
}

interface Slot {
  state: InsightsState
  listeners: Set<() => void>
  inflight: Promise<void> | null
  loadedAt: number
}

const slots = new Map<string, Slot>()
const STALE_AFTER_MS = 10 * 60 * 1000
const INITIAL: InsightsState = { status: "idle", data: null, error: null, allowed: [], refreshing: false, hidden: [] }

function slotFor(key: string): Slot {
  let s = slots.get(key)
  if (!s) {
    s = { state: INITIAL, listeners: new Set(), inflight: null, loadedAt: 0 }
    slots.set(key, s)
  }
  return s
}

function set(key: string, patch: Partial<InsightsState>) {
  const s = slotFor(key)
  s.state = { ...s.state, ...patch }
  s.listeners.forEach((l) => l())
}

export function loadInsights(module: string, scope = "", refresh: boolean | "background" = false): Promise<void> {
  const key = `${module}|${scope}`
  const s = slotFor(key)
  if (s.inflight) return s.inflight
  set(key, s.state.data ? { refreshing: true } : { status: "loading", refreshing: false })
  s.inflight = fetchInsights(module, { scope, refresh })
    .then((data) => {
      s.loadedAt = Date.now()
      set(key, { status: "ready", data, error: null, refreshing: false })
    })
    .catch((e: unknown) => {
      const err = e instanceof InsightsError ? e : new InsightsError("Insights are unavailable right now.", null)
      // keep an earlier good briefing on screen if a refresh fails
      set(key, s.state.data
        ? { refreshing: false, error: err.message }
        : { status: err.status === 403 ? "denied" : "error", error: err.message, allowed: err.allowed ?? [], refreshing: false })
    })
    .finally(() => {
      s.inflight = null
    })
  return s.inflight
}

export interface UseInsights {
  state: InsightsState
  refresh: () => void
  feedback: (verdict: InsightVerdict, recId?: string, note?: string) => Promise<boolean>
}

export function useInsights(module: string, opts: { scope?: string; enabled?: boolean } = {}): UseInsights {
  const scope = opts.scope ?? ""
  const enabled = opts.enabled ?? true
  const key = `${module}|${scope}`
  const subscribe = useCallback(
    (cb: () => void) => {
      const s = slotFor(key)
      s.listeners.add(cb)
      return () => {
        s.listeners.delete(cb)
      }
    },
    [key],
  )
  const state = useSyncExternalStore(subscribe, () => slotFor(key).state, () => INITIAL)

  useEffect(() => {
    if (!enabled) return
    const s = slotFor(key)
    if (s.state.status === "idle" || (s.state.status === "error" && !s.inflight)) void loadInsights(module, scope)
    else if (s.state.status === "ready" && Date.now() - s.loadedAt > STALE_AFTER_MS) void loadInsights(module, scope, "background")
  }, [enabled, key, module, scope])

  const refresh = useCallback(() => void loadInsights(module, scope, true), [module, scope])

  const feedback = useCallback(
    async (verdict: InsightVerdict, recId?: string, note?: string) => {
      const doc = slotFor(key).state.data
      if (!doc) return false
      if (recId && (verdict === "dismissed" || verdict === "not_helpful")) {
        set(key, { hidden: [...slotFor(key).state.hidden, recId] })
      }
      try {
        await sendInsightFeedback(doc.id, verdict, { recId, note })
        return true
      } catch {
        return false
      }
    },
    [key],
  )

  return { state, refresh, feedback }
}
