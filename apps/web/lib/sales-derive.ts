/**
 * Pure Sales derivations (no React / browser imports, node-testable).
 *
 * Owner rule: no fabricated figures. Everything here is computed from real
 * rows the sales service returned; nothing has a built-in default.
 */

export interface DealRow {
  id?: string
  name?: string | null
  status?: string | null
  stage_name?: string | null
  value_zar?: number | string | null
  created_at?: string | null
  updated_at?: string | null
  closed_at?: string | null
  close_date?: string | null
  owner_name?: string | null
}

/** Shape of GET /svc/sales/deals/summary. */
export interface DealSummary {
  count: number
  total_value_zar: number
  won_count: number
  won_value_zar: number
  open_count: number
  open_value_zar: number
  lost_count: number
  lost_value_zar: number
}

const SAST_OFFSET_MS = 2 * 60 * 60 * 1000 // South Africa Standard Time, no DST

export function num(v: unknown): number {
  const n = typeof v === "string" ? Number(v) : (v as number)
  return typeof n === "number" && Number.isFinite(n) ? n : 0
}

/** Parse an API timestamp; text without an offset is UTC (the API stores UTC). */
export function parseTs(v: string | null | undefined): Date | null {
  if (!v) return null
  const s = /([zZ]|[+-]\d\d:?\d\d)$/.test(v) || !v.includes("T") ? v : `${v}Z`
  const d = new Date(s)
  return Number.isNaN(d.getTime()) ? null : d
}

/** YYYY-MM-DD of an instant as a SAST calendar date. */
export function sastDate(d: Date): string {
  return new Date(d.getTime() + SAST_OFFSET_MS).toISOString().slice(0, 10)
}

/** First of this SAST month to today (inclusive) as dates: the summary endpoint's closed_from/closed_to. */
export function sastMonthRange(now: Date): { closed_from: string; closed_to: string } {
  const today = sastDate(now)
  return { closed_from: `${today.slice(0, 8)}01`, closed_to: today }
}

export function isWon(d: DealRow): boolean {
  const s = (d.status ?? "").toUpperCase()
  return s === "WON" || s === "CLOSED_WON"
}
export function isLost(d: DealRow): boolean {
  const s = (d.status ?? "").toUpperCase()
  return s === "LOST" || s === "CLOSED_LOST"
}
export function isOpen(d: DealRow): boolean {
  return (d.status ?? "").toUpperCase() === "OPEN"
}

/**
 * Fallback for GET /deals/summary with identical semantics: totals by status
 * over all rows; `monthWon` = WON deals whose closed_at falls in the range
 * (SAST dates, inclusive).
 */
export function summarizeDeals(
  deals: DealRow[],
  range: { closed_from: string; closed_to: string },
): { all: DealSummary; monthWon: { count: number; value_zar: number } } {
  const all: DealSummary = {
    count: 0, total_value_zar: 0, won_count: 0, won_value_zar: 0,
    open_count: 0, open_value_zar: 0, lost_count: 0, lost_value_zar: 0,
  }
  const monthWon = { count: 0, value_zar: 0 }
  for (const d of deals) {
    const v = num(d.value_zar)
    all.count += 1
    all.total_value_zar += v
    if (isWon(d)) {
      all.won_count += 1
      all.won_value_zar += v
      const closed = parseTs(d.closed_at)
      if (closed) {
        const day = sastDate(closed)
        if (day >= range.closed_from && day <= range.closed_to) {
          monthWon.count += 1
          monthWon.value_zar += v
        }
      }
    } else if (isLost(d)) {
      all.lost_count += 1
      all.lost_value_zar += v
    } else if (isOpen(d)) {
      all.open_count += 1
      all.open_value_zar += v
    }
  }
  return { all, monthWon }
}

/** Accept a summary payload only if it has the contract's numeric fields. */
export function parseDealSummary(body: unknown): DealSummary | null {
  const b = body as Record<string, unknown> | null
  if (!b || typeof b !== "object") return null
  const keys = [
    "count", "total_value_zar", "won_count", "won_value_zar",
    "open_count", "open_value_zar", "lost_count", "lost_value_zar",
  ] as const
  for (const k of keys) if (typeof b[k] !== "number" && typeof b[k] !== "string") return null
  const out = {} as DealSummary
  for (const k of keys) out[k] = num(b[k])
  return out
}

/** Won revenue per SAST month for the last `months` months (by closed_at, not created_at). */
export function wonByMonth(
  deals: DealRow[],
  now: Date,
  months = 6,
): { month: string; revenue: number; deals: number }[] {
  const [y, m] = sastDate(now).split("-").map(Number)
  const buckets: { key: string; label: string; revenue: number; deals: number }[] = []
  for (let i = months - 1; i >= 0; i--) {
    const d = new Date(Date.UTC(y, m - 1 - i, 1))
    buckets.push({
      key: `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}`,
      label: d.toLocaleString("en-US", { month: "short", timeZone: "UTC" }),
      revenue: 0,
      deals: 0,
    })
  }
  for (const d of deals) {
    if (!isWon(d)) continue
    const closed = parseTs(d.closed_at)
    if (!closed) continue
    const b = buckets.find((x) => x.key === sastDate(closed).slice(0, 7))
    if (b) {
      b.revenue += num(d.value_zar)
      b.deals += 1
    }
  }
  return buckets.map((b) => ({ month: b.label, revenue: Math.round(b.revenue), deals: b.deals }))
}

// ── Panels generated only from real deals ─────────────────────────────

export function relativeTime(iso: string | null | undefined, now: Date): string {
  const t = parseTs(iso)
  if (!t) return ""
  const s = Math.max(0, Math.round((now.getTime() - t.getTime()) / 1000))
  if (s < 60) return "just now"
  const m = Math.floor(s / 60)
  if (m < 60) return `${m} minute${m === 1 ? "" : "s"} ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h} hour${h === 1 ? "" : "s"} ago`
  const d = Math.floor(h / 24)
  return `${d} day${d === 1 ? "" : "s"} ago`
}

export interface DerivedActivity {
  id: string
  user: string
  action: string
  target: string
  time: string
  type: "create" | "update"
}

/** Recent deal events from the real rows: won / lost / created. No invented people. */
export function deriveActivities(deals: DealRow[], now: Date, limit = 8): DerivedActivity[] {
  const events: { at: Date; a: DerivedActivity }[] = []
  for (const d of deals) {
    const id = String(d.id ?? "")
    const name = d.name || "Untitled deal"
    const owner = d.owner_name || "Pipeline"
    const closed = parseTs(d.closed_at)
    const created = parseTs(d.created_at)
    if (closed && (isWon(d) || isLost(d))) {
      events.push({
        at: closed,
        a: { id: `${id}:closed`, user: owner, action: isWon(d) ? "won the deal" : "lost the deal", target: name, time: relativeTime(d.closed_at, now), type: "update" },
      })
    } else if (created) {
      events.push({
        at: created,
        a: { id: `${id}:created`, user: owner, action: "created the deal", target: name, time: relativeTime(d.created_at, now), type: "create" },
      })
    }
  }
  return events.sort((x, y) => y.at.getTime() - x.at.getTime()).slice(0, limit).map((e) => e.a)
}

export interface DerivedRecommendation {
  id: string
  title: string
  description: string
  impact: "high" | "medium" | "low"
  category: string
}

const zar = (n: number) => `R ${Math.round(n).toLocaleString("en-ZA")}`

/** Recommendations that only state facts about real open deals. */
export function deriveRecommendations(
  deals: DealRow[],
  now: Date,
  stalledDays = 14,
): DerivedRecommendation[] {
  const open = deals.filter(isOpen)
  const out: DerivedRecommendation[] = []
  const today = sastDate(now)
  const cutoff = now.getTime() - stalledDays * 86_400_000

  const stalled = open.filter((d) => {
    const t = parseTs(d.updated_at) ?? parseTs(d.created_at)
    return t !== null && t.getTime() < cutoff
  })
  if (stalled.length > 0) {
    const names = stalled.slice(0, 3).map((d) => d.name || "Untitled deal").join(", ")
    out.push({
      id: "stalled",
      title: `${stalled.length} open deal${stalled.length === 1 ? "" : "s"} not updated in ${stalledDays}+ days`,
      description: `${names}${stalled.length > 3 ? ` and ${stalled.length - 3} more` : ""} (${zar(stalled.reduce((s, d) => s + num(d.value_zar), 0))} open value). Follow up or close them out.`,
      impact: stalled.length >= 3 ? "high" : "medium",
      category: "Risk",
    })
  }

  const overdue = open.filter((d) => d.close_date && d.close_date.slice(0, 10) < today)
  if (overdue.length > 0) {
    out.push({
      id: "overdue",
      title: `${overdue.length} open deal${overdue.length === 1 ? "" : "s"} past the expected close date`,
      description: `${overdue.slice(0, 3).map((d) => d.name || "Untitled deal").join(", ")}${overdue.length > 3 ? ` and ${overdue.length - 3} more` : ""}. Update the close date or close the deal.`,
      impact: "high",
      category: "Risk",
    })
  }

  const thisMonth = open.filter((d) => d.close_date && d.close_date.slice(0, 7) === today.slice(0, 7) && d.close_date.slice(0, 10) >= today)
  if (thisMonth.length > 0) {
    out.push({
      id: "closing-this-month",
      title: `${thisMonth.length} open deal${thisMonth.length === 1 ? "" : "s"} due to close this month`,
      description: `${zar(thisMonth.reduce((s, d) => s + num(d.value_zar), 0))} open value expected to close by the end of the month.`,
      impact: "medium",
      category: "Sales",
    })
  }
  return out
}

// ── Truncation ────────────────────────────────────────────────────────

/** "Showing N of TOTAL" only when the list is actually truncated. */
export function truncationNote(shown: number, total: number | null | undefined): string | null {
  if (typeof total !== "number" || !Number.isFinite(total) || total <= shown) return null
  return `Showing ${shown.toLocaleString("en-ZA")} of ${total.toLocaleString("en-ZA")}`
}

export function parseTotalCount(v: string | null | undefined): number | null {
  if (v === null || v === undefined || v.trim() === "") return null
  const n = Number(v)
  return Number.isInteger(n) && n >= 0 ? n : null
}

// ── Board ─────────────────────────────────────────────────────────────

/** Board header figures: open pipeline and won are separate, never one mixed total. */
export function boardTotals(deals: DealRow[]): { openValue: number; openCount: number; wonValue: number; wonCount: number; count: number } {
  let openValue = 0, openCount = 0, wonValue = 0, wonCount = 0
  for (const d of deals) {
    if (isOpen(d)) { openValue += num(d.value_zar); openCount += 1 }
    else if (isWon(d)) { wonValue += num(d.value_zar); wonCount += 1 }
  }
  return { openValue, openCount, wonValue, wonCount, count: deals.length }
}

export function isClosingStageName(name: string | null | undefined): "won" | "lost" | null {
  const k = (name ?? "").trim().toLowerCase().replace(/[\s_]+/g, " ")
  if (k === "closed won" || k === "won") return "won"
  if (k === "closed lost" || k === "lost") return "lost"
  return null
}

/** Moving into a closing stage posts commission/finance entries: it needs explicit confirmation. */
export function closingTarget(
  stages: { id: string; name: string }[],
  targetStageId: string,
): "won" | "lost" | null {
  return isClosingStageName(stages.find((s) => s.id === targetStageId)?.name)
}

// ── Funnel (case-insensitive, tolerant of old and new API shapes) ─────

export type FunnelTier = "top" | "mid" | "closing" | "won" | "lost" | "other"

export function funnelKey(stage: string | null | undefined): string {
  return (stage ?? "").trim().replace(/[\s_]+/g, " ").toUpperCase()
}

const TIER_BY_KEY: Record<string, FunnelTier> = {
  NEW: "top",
  CONTACTED: "top",
  QUALIFIED: "mid",
  PROSPECTING: "mid",
  CONVERTED: "mid",
  PROPOSAL: "closing",
  NEGOTIATION: "closing",
  "CLOSED WON": "won",
  WON: "won",
  "CLOSED LOST": "lost",
  LOST: "lost",
  DISQUALIFIED: "lost",
}

const TIER_ENTRY_KEY: Partial<Record<FunnelTier, string>> = {
  top: "NEW",
  mid: "QUALIFIED",
  closing: "PROPOSAL",
  won: "CLOSED WON",
}

/** Sum a stage->count map (keys of any case) over one tier. */
export function sumStageMap(map: Record<string, number | string> | null | undefined, tier: FunnelTier): number {
  let t = 0
  for (const [k, v] of Object.entries(map ?? {})) if (funnelTier(k) === tier) t += num(v)
  return t
}

export function funnelTier(stage: string | null | undefined): FunnelTier {
  return TIER_BY_KEY[funnelKey(stage)] ?? "other"
}

export function clampPct(n: number | null | undefined): number {
  const v = typeof n === "number" && Number.isFinite(n) ? n : 0
  return Math.round(Math.max(0, Math.min(100, v)) * 10) / 10
}

export interface FunnelStageIn {
  stage: string
  count: number
  value_zar?: number | string | null
  cohort_count?: number | null
  conversion_from_previous_pct?: number | null
}

export interface TierAgg {
  count: number
  value: number
  cohort: number | null
  stages: string[]
}

/**
 * Group the API's stage rows into funnel tiers. Duplicate stages that differ
 * only by case are merged; unknown stage names go to "other"; if the stages do
 * not add up to `totalLeads`, the remainder is reported as `unaccounted`.
 */
export function aggregateFunnel(
  stages: FunnelStageIn[],
  totalLeads: number,
): { tiers: Record<FunnelTier, TierAgg>; merged: FunnelStageIn[]; unaccounted: number } {
  const mergedMap = new Map<string, FunnelStageIn>()
  for (const s of stages) {
    const key = funnelKey(s.stage)
    const cur = mergedMap.get(key)
    if (cur) {
      cur.count += num(s.count)
      cur.value_zar = num(cur.value_zar) + num(s.value_zar)
      if (s.cohort_count != null) cur.cohort_count = num(cur.cohort_count) + num(s.cohort_count)
    } else {
      mergedMap.set(key, { ...s, count: num(s.count), value_zar: num(s.value_zar) })
    }
  }
  const merged = [...mergedMap.values()]
  const empty = (): TierAgg => ({ count: 0, value: 0, cohort: null, stages: [] })
  const tiers: Record<FunnelTier, TierAgg> = {
    top: empty(), mid: empty(), closing: empty(), won: empty(), lost: empty(), other: empty(),
  }
  let sum = 0
  for (const s of merged) {
    const t = tiers[funnelTier(s.stage)]
    t.count += num(s.count)
    t.value += num(s.value_zar)
    t.stages.push(s.stage)
    sum += num(s.count)
  }
  // A cohort is cumulative (reached this stage or beyond), so a tier's cohort is its ENTRY stage's, never a sum.
  for (const tier of Object.keys(TIER_ENTRY_KEY) as FunnelTier[]) {
    const entry = merged.find((m) => funnelKey(m.stage) === TIER_ENTRY_KEY[tier])
    tiers[tier].cohort = entry && entry.cohort_count != null ? num(entry.cohort_count) : null
  }
  const unaccounted = Math.max(0, num(totalLeads) - sum)
  return { tiers, merged, unaccounted }
}

/**
 * Conversion from the previous tier, clamped 0-100. Uses cohort counts when
 * both sides have them (reached-or-beyond), otherwise snapshot counts; returns
 * null when the previous side is empty (nothing to convert from).
 */
export function tierConversion(
  cur: { count: number; cohort: number | null },
  prev: { count: number; cohort: number | null },
): number | null {
  const useCohort = cur.cohort !== null && prev.cohort !== null
  const c = useCohort ? (cur.cohort as number) : cur.count
  const p = useCohort ? (prev.cohort as number) : prev.count
  if (!(p > 0)) return null
  return clampPct((c / p) * 100)
}

/** The open-pipeline figure and its honest label. */
export function pipelineValueFigure(totals: Record<string, unknown> | null | undefined): { value: number; label: string } {
  const t = totals ?? {}
  if (t.open_value_zar !== undefined && t.open_value_zar !== null) {
    return { value: num(t.open_value_zar), label: "Open pipeline (excludes won and lost)" }
  }
  return { value: num(t.total_pipeline_value_zar), label: "Pipeline value (older API: may include won)" }
}

/** Channels to render: all of them, or the first `max` until expanded. */
export function visibleChannels<T>(items: T[], max: number, expanded: boolean): { shown: T[]; hidden: number } {
  if (expanded || items.length <= max) return { shown: items, hidden: 0 }
  return { shown: items.slice(0, max), hidden: items.length - max }
}
