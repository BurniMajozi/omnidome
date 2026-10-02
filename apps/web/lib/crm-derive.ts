/**
 * Pure CRM / lifecycle helpers (no React, no browser imports) so node --test
 * can load them. Owner rule: no fabricated figures; every number is read from
 * the API or derived transparently from API data.
 */

import { loadableFromStatus, type Loadable } from "./service-state"

// ─── Lead statuses ───────────────────────────────────────────────────────────

/** Canonical (upper-case) lead statuses. WON is the backend's alias of CONVERTED. */
export const OPEN_LEAD_STATUSES = ["NEW", "CONTACTED", "QUALIFIED"] as const
export const CLOSED_LEAD_STATUSES = ["LOST", "DISQUALIFIED"] as const

/**
 * Case-insensitive status normaliser. null/empty -> "NEW"; WON -> "CONVERTED";
 * anything else is upper-cased + trimmed (unknown statuses are preserved, never
 * silently remapped to NEW).
 */
export function normalizeLeadStatus(raw: unknown): string {
  if (typeof raw !== "string") return "NEW"
  const s = raw.trim().toUpperCase().replace(/[\s-]+/g, "_")
  if (!s) return "NEW"
  if (s === "WON" || s === "CONVERTED") return "CONVERTED"
  return s
}

export function isConvertedStatus(raw: unknown): boolean {
  return normalizeLeadStatus(raw) === "CONVERTED"
}
export function isClosedLostStatus(raw: unknown): boolean {
  const s = normalizeLeadStatus(raw)
  return (CLOSED_LEAD_STATUSES as readonly string[]).includes(s)
}

/** Sum counts per normalised status (so {new: 2, NEW: 1, won: 3} -> {NEW: 3, CONVERTED: 3}). */
export function normalizeStatusCounts(counts: Record<string, number> | null | undefined): Record<string, number> {
  const out: Record<string, number> = {}
  for (const [k, v] of Object.entries(counts ?? {})) {
    const n = Number(v)
    if (!Number.isFinite(n) || n < 0) continue
    const key = normalizeLeadStatus(k)
    out[key] = (out[key] ?? 0) + n
  }
  return out
}

export function countLeadStatuses(leads: { status?: string | null }[]): Record<string, number> {
  const out: Record<string, number> = {}
  for (const l of leads) {
    const k = normalizeLeadStatus(l.status)
    out[k] = (out[k] ?? 0) + 1
  }
  return out
}

/** Include zero-count canonical stages and every observed status in the same cohort. */
export function leadStageDistribution(raw: Record<string, number>) {
  const counts = normalizeStatusCounts(raw)
  const total = Object.values(counts).reduce((sum, count) => sum + count, 0)
  const stages = new Set(["NEW", "CONTACTED", "QUALIFIED", "PROPOSAL", "NEGOTIATION", "CONVERTED", "LOST", "DISQUALIFIED", ...Object.keys(counts)])
  return Array.from(stages, (stage) => ({ stage, count: counts[stage] ?? 0, pctOfTotal: pctOfCohort(counts[stage] ?? 0, total) }))
}

export interface LeadTilesInput {
  leadStatusCounts?: Record<string, number> | null
  convertedLeads?: number | null
  totalLeads?: number | null
}

export interface LeadTiles {
  total: number
  /** Active = NEW + CONTACTED + QUALIFIED (open, still being worked). */
  active: number
  converted: number
  lost: number
  /** converted / total as 0-100, or null when there are no leads (never a fake 0%). */
  conversionPct: number | null
  source: "api" | "list" | "none"
}

/**
 * Tiles from the API's leadStatusCounts / convertedLeads / totalLeads, falling
 * back to the status counts of the loaded lead list (case-insensitive).
 */
export function computeLeadTiles(
  summary: LeadTilesInput | null | undefined,
  leads: { status?: string | null }[] = [],
): LeadTiles {
  const apiCounts = summary?.leadStatusCounts ? normalizeStatusCounts(summary.leadStatusCounts) : null
  const hasApi = apiCounts !== null
  const counts = hasApi ? (apiCounts as Record<string, number>) : countLeadStatuses(leads)
  const sum = Object.values(counts).reduce((a, b) => a + b, 0)
  const source: LeadTiles["source"] = hasApi ? "api" : sum > 0 ? "list" : "none"

  const total = Number.isFinite(Number(summary?.totalLeads)) && summary?.totalLeads != null && hasApi
    ? Math.max(Number(summary.totalLeads), 0)
    : sum
  const converted = hasApi && summary?.convertedLeads != null && Number.isFinite(Number(summary.convertedLeads))
    ? Math.max(Number(summary.convertedLeads), 0)
    : counts.CONVERTED ?? 0
  const active = OPEN_LEAD_STATUSES.reduce((a, s) => a + (counts[s] ?? 0), 0)
  const lost = CLOSED_LEAD_STATUSES.reduce((a, s) => a + (counts[s] ?? 0), 0)
  return {
    total,
    active,
    converted,
    lost,
    conversionPct: total > 0 ? clampPct((converted / total) * 100) : null,
    source,
  }
}

// ─── Funnel maths ────────────────────────────────────────────────────────────

/** Round and clamp to 0-100; non-finite -> 0. */
export function clampPct(n: number): number {
  if (typeof n !== "number" || !Number.isFinite(n)) return 0
  return Math.min(100, Math.max(0, Math.round(n)))
}

/** count as a percentage of its OWN cohort (0 when the cohort is empty). */
export function pctOfCohort(count: number, cohort: number): number {
  return cohort > 0 ? clampPct((count / cohort) * 100) : 0
}

export interface TierMetric {
  pctOfTotal: number
  /** undefined for the first tier or when the previous tier is empty. */
  conversionFromPrev?: number
}

/**
 * Per-tier percentages for an ordered list of counts that all belong to the
 * SAME snapshot cohort (leads). pctOfTotal = count / sum(counts).
 * Current stage populations cannot establish a conversion rate between stages.
 */
export function funnelTierMetrics(counts: number[]): TierMetric[] {
  const cohort = counts.reduce((a, b) => a + (Number.isFinite(b) && b > 0 ? b : 0), 0)
  return counts.map((c, i) => {
    return {
      pctOfTotal: pctOfCohort(c, cohort),
    }
  })
}

// ─── Roles ───────────────────────────────────────────────────────────────────

export const CRM_ADMIN_ROLES = ["platform_admin", "owner", "org_admin", "admin", "tenant_admin", "super_admin"]
export const CRM_MANAGER_ROLES = [...CRM_ADMIN_ROLES, "manager", "sales_manager", "support_manager"]
export const CRM_AGENT_ROLES = [
  ...CRM_MANAGER_ROLES,
  "sales", "sales_agent", "sales_rep", "agent", "field_agent", "support_agent", "crm_agent", "account_manager",
]

/** Mirrors services/crm/access.py tiers. The server still enforces; this only hides dead buttons. */
export function roleTier(roles: string[] | null | undefined): "admin" | "agent" | "read" | "unknown" {
  if (!roles || roles.length === 0) return "unknown"
  const r = roles.map((x) => x.toLowerCase())
  if (r.some((x) => CRM_ADMIN_ROLES.includes(x))) return "admin"
  if (r.some((x) => CRM_AGENT_ROLES.includes(x))) return "agent"
  return "read"
}

// ─── Error mapping (409 duplicate, 403, 422...) ──────────────────────────────

export type CrmErrorKind = "duplicate" | "denied" | "validation" | "unreachable" | "not_found" | "bad_request" | "error"

export interface CrmError {
  kind: CrmErrorKind
  status: number | null
  message: string
  /** Existing record id on a 409 duplicate / already-converted. */
  existingCustomerId?: string
}

function str(v: unknown): string | undefined {
  return typeof v === "string" && v.trim() ? v.trim() : undefined
}

/** Flatten FastAPI `detail` (string | {message,...} | [{loc,msg}]) to verbatim text. */
export function detailMessage(body: unknown): string | undefined {
  if (!body || typeof body !== "object") return str(body)
  const b = body as Record<string, unknown>
  const d = b.detail ?? b.error ?? b.message
  if (typeof d === "string") return str(d)
  if (Array.isArray(d)) {
    const parts = d
      .map((e) => {
        if (typeof e === "string") return e
        const m = str((e as any)?.msg)
        const loc = Array.isArray((e as any)?.loc) ? (e as any).loc.filter((x: unknown) => x !== "body").join(".") : ""
        return m ? (loc ? `${loc}: ${m}` : m) : undefined
      })
      .filter(Boolean)
    return parts.length ? parts.join("; ") : undefined
  }
  if (d && typeof d === "object") return str((d as any).message) ?? str((d as any).detail)
  return undefined
}

/** The existing customer id the backend returns with a 409. */
export function existingIdFromBody(body: unknown): string | undefined {
  if (!body || typeof body !== "object") return undefined
  const b = body as Record<string, any>
  const cands = [b.customer_id, b.existing_customer_id, b.detail?.customer_id, b.detail?.existing_customer_id, b.detail?.id, b.id]
  for (const c of cands) if (typeof c === "string" && c) return c
  return undefined
}

/** Map an HTTP failure to the message the UI shows. */
export function mapCrmError(status: number | null, body: unknown): CrmError {
  const msg = detailMessage(body)
  if (status === null || status === 0 || status === 502 || status === 503 || status === 504) {
    return { kind: "unreachable", status, message: "CRM service is not running or not reachable." }
  }
  if (status === 409) {
    const id = existingIdFromBody(body)
    return {
      kind: "duplicate",
      status,
      message: msg ?? "Customer already exists",
      existingCustomerId: id,
    }
  }
  if (status === 401 || status === 403) return { kind: "denied", status, message: msg ?? "Not permitted" }
  if (status === 404) return { kind: "not_found", status, message: msg ?? "Not found" }
  if (status === 422) return { kind: "validation", status, message: msg ?? "The server rejected the submitted values." }
  if (status === 400) return { kind: "bad_request", status, message: msg ?? "Request rejected." }
  return { kind: "error", status, message: msg ?? `Request failed (HTTP ${status})` }
}

// ─── Customer 360 payload ────────────────────────────────────────────────────

export interface Payload360Info {
  partial: boolean
  /** section name -> error text, for sections the server could not build. */
  sectionErrors: Record<string, string>
}

/** Read `partial` / `section_errors` off a 360 payload (or its `.data` wrapper). */
export function read360Meta(json: unknown): Payload360Info {
  const root = (json && typeof json === "object" ? (json as any) : {}) as Record<string, any>
  const src = root.section_errors !== undefined || root.partial !== undefined ? root : (root.data ?? {})
  const errs: Record<string, string> = {}
  const raw = src?.section_errors
  if (raw && typeof raw === "object" && !Array.isArray(raw)) {
    for (const [k, v] of Object.entries(raw)) errs[k] = typeof v === "string" ? v : "Unavailable"
  } else if (Array.isArray(raw)) {
    for (const k of raw) if (typeof k === "string") errs[k] = "Unavailable"
  }
  return { partial: src?.partial === true || Object.keys(errs).length > 0, sectionErrors: errs }
}

const NOT_ASSESSED = "Not assessed"

/** Tier text: missing / NOT_ASSESSED -> "Not assessed" (never a default BRONZE). */
export function formatTier(tier: unknown): string {
  if (typeof tier !== "string" || !tier.trim()) return NOT_ASSESSED
  const t = tier.trim().toUpperCase()
  return t === "NOT_ASSESSED" || t === "UNKNOWN" ? NOT_ASSESSED : t
}

/** Reliability 0-100 or null -> "Not assessed" (never 100%). */
export function formatReliability(v: unknown): string {
  if (v === null || v === undefined || typeof v !== "number" || !Number.isFinite(v)) return NOT_ASSESSED
  return `${Math.round(v)}%`
}

export function formatRecommendation(v: unknown): string {
  if (typeof v !== "string" || !v.trim()) return NOT_ASSESSED
  return v.trim().toUpperCase() === "NOT_ASSESSED" ? NOT_ASSESSED : v.trim()
}

// ─── Lifecycle loadable from a thrown API error ──────────────────────────────

/** Settle a promise into a Loadable, preserving the HTTP status (`err.status`). */
export async function settleLoadable<T>(p: Promise<T>): Promise<Loadable<T>> {
  try {
    const data = await p
    return { state: "ready", data }
  } catch (e) {
    const status = typeof (e as any)?.status === "number" ? ((e as any).status as number) : null
    return loadableFromStatus<T>(status, undefined, status ? (e as Error)?.message : undefined) as Loadable<T>
  }
}
