/**
 * Dream state (nightly memory self-maintenance) client. docs/dream-state.md.
 * Same transport as the knowledge index panel: the /svc/memory proxy with the Supabase bearer attached.
 */
import { getSessionSafe } from "@/lib/supabase/client"

const BASE = "/svc/memory/api/v1/knowledge/dream"

export class DreamApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const { data } = await getSessionSafe()
  const headers = new Headers({ "Content-Type": "application/json", ...(init?.headers as Record<string, string> | undefined) })
  if (data.session?.access_token) headers.set("Authorization", `Bearer ${data.session.access_token}`)
  let res: Response
  try {
    res = await fetch(`${BASE}${path}`, { cache: "no-store", signal: AbortSignal.timeout(20000), ...init, headers })
  } catch (e) {
    throw new DreamApiError(e instanceof Error ? e.message : "Memory service unreachable", 0)
  }
  if (!res.ok) {
    const text = await res.text().catch(() => "")
    let detail: unknown = text
    try {
      const j = JSON.parse(text)
      detail = j?.detail ?? j?.error ?? text
    } catch {
      /* not JSON */
    }
    throw new DreamApiError(typeof detail === "string" && detail ? detail : `Memory service error ${res.status}`, res.status)
  }
  return res.json()
}

export type DreamSeverity = "info" | "low" | "medium" | "high" | "critical"
export type DreamFindingStatus = "open" | "proposed" | "auto_applied" | "applied" | "accepted" | "dismissed"

export interface DreamSettings {
  enabled: boolean
  window_start: string
  window_hours: number
  timezone: string
  max_cards_per_night: number
  rotation_days: number
  semantic_drift: number
  canary_n: number
  canary_recall_floor: number
  canary_alert_drop: number
  metric_tolerance: number
  decay_after_days: number
  jev_enabled: boolean
  jev_max_calls: number
  jev_max_cost_usd: number
  jev_approve: number
  jev_reject: number
  stale_days: Record<string, number>
}

export interface DreamReport {
  run_date?: string
  health_score?: number
  health_label?: string
  cards?: { live_chunks: number; live_sources: number; stale: number; tombstoned: number }
  drift?: Record<string, number>
  embeddings?: Record<string, number>
  canary?: { n: number; hits?: number; recall_at_3: number | null; misses?: { title: string }[]; previous?: number | null }
  metrics?: { checked: number; drifted: number; refreshed: boolean }
  forecast?: { series_scored: number; degraded: number; mean_smape: number | null }
  relevance?: { importance_up: number; importance_down: number; cold: number; conflicts: number; telemetry?: boolean | null }
  consolidation?: Record<string, number | boolean>
  jev?: { enabled: boolean; calls: number; cost_usd: number; cached: number; decided: number; queued_for_review: number }
  findings?: { open_by_severity: Record<string, number>; total_open: number }
  errors?: string[]
}

export interface DreamRunSummary {
  id: string
  run_date: string
  trigger: string
  dry_run: boolean
  status: string
  started_at?: string | null
  finished_at?: string | null
  health_score?: number | null
  jev_calls?: number
  jev_cost_usd?: number
  phases_done?: string[]
  report?: DreamReport
}

export interface DreamStatus {
  ready: boolean
  note?: string
  kill_switch: boolean
  phases: string[]
  settings: DreamSettings
  overrides: Partial<DreamSettings>
  last_run: DreamRunSummary | null
  last_dry_run?: DreamRunSummary | null
  running: DreamRunSummary | null
  trend: { run_date: string; health_score: number | null; canary_recall: number | null; stale: number | null; status: string }[]
  findings: { open: Record<string, number>; total_open: number }
  cards?: { live_chunks: number; live_sources: number; stale_tagged: number; tombstoned: number }
  next_window?: string | null
  jev?: { enabled: boolean; credentials: boolean; external: boolean }
}

export interface DreamFinding {
  id: string
  phase?: string | null
  type: string
  severity: DreamSeverity
  status: DreamFindingStatus
  source_type?: string | null
  source_id?: string | null
  title: string
  detail: Record<string, unknown>
  action?: { kind?: string } | null
  jev?: { question: string; p: number; decision: string; cost_usd?: number } | null
  occurrences: number
  auto_applied: boolean
  first_seen: string
  last_seen: string
}

export const getDreamStatus = () => call<DreamStatus>("/status")
export const getDreamRuns = (limit = 20) => call<{ runs: DreamRunSummary[] }>(`/runs?limit=${limit}`)
export const getDreamFindings = (params: { status?: string; severity?: string; limit?: number } = {}) => {
  const q = new URLSearchParams()
  if (params.status) q.set("status", params.status)
  if (params.severity) q.set("severity", params.severity)
  q.set("limit", String(params.limit ?? 50))
  return call<{ findings: DreamFinding[] }>(`/findings?${q.toString()}`)
}
/** Queued for the knowledge worker; a dry run changes nothing except the dream log. */
export const runDream = (dryRun = true, phases?: string[]) =>
  call<{ job_id: string; status: string; dry_run: boolean; note?: string }>("/run", {
    method: "POST",
    body: JSON.stringify({ dry_run: dryRun, ...(phases?.length ? { phases } : {}) }),
  })
export const resolveDreamFinding = (id: string, action: "accept" | "dismiss" | "apply", note?: string) =>
  call<DreamFinding>(`/findings/${id}/resolve`, { method: "POST", body: JSON.stringify({ action, ...(note ? { note } : {}) }) })
export const getDreamSettings = () => call<{ settings: DreamSettings; overrides: Partial<DreamSettings>; tunable: string[] }>("/settings")
export const putDreamSettings = (patch: Partial<DreamSettings>) =>
  call<{ settings: DreamSettings; overrides: Partial<DreamSettings> }>("/settings", { method: "PUT", body: JSON.stringify(patch) })
