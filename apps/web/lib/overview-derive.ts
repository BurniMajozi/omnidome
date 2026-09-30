/**
 * Pure derivations for the Overview page.
 *
 * Owner rule: no fabricated figures. Everything here is computed ONLY from rows
 * the backends actually returned. When there is nothing to compute the helpers
 * return null / [] so the UI can show an honest state. No React / browser
 * imports so it can be unit-tested with node.
 */

// Type-only import (erased at runtime) so node --test can load this file without a resolver.
import type { Loadable } from "./service-state"

export interface DealRow {
  id?: string
  name?: string | null
  value_zar?: number | string | null
  status?: string | null
  stage_name?: string | null
  close_date?: string | null
  closed_at?: string | null
  created_at?: string | null
  updated_at?: string | null
  lead_reference?: string | null
  owner_name?: string | null
}

export type TimeRange = "7D" | "30D" | "90D" | "1Y"

const num = (v: unknown): number => {
  const n = typeof v === "string" ? Number.parseFloat(v) : (v as number)
  return typeof n === "number" && Number.isFinite(n) ? n : 0
}

const up = (s: string | null | undefined) => (s ?? "").toUpperCase()

// One ZAR formatter for every Overview tile/tooltip/axis (lib/format.ts). The explicit
// .ts extension lets node --test load this file; the bundler resolves it as normal.
// @ts-ignore TS5097: extension imports are not enabled in tsconfig (noEmit, bundler resolution)
import { fmtZar, fmtZarCompact } from "./format.ts"
export { fmtZar, fmtZarCompact }

export interface DealTotals {
  count: number
  won: number
  open: number
  lost: number
  wonValue: number
  openValue: number
  totalValue: number
  /** won / (won + lost); null until at least one deal is closed. */
  winRate: number | null
}

export function dealTotals(deals: DealRow[]): DealTotals {
  let won = 0
  let open = 0
  let lost = 0
  let wonValue = 0
  let openValue = 0
  let totalValue = 0
  for (const d of deals) {
    const v = num(d.value_zar)
    totalValue += v
    const s = up(d.status)
    if (s === "WON") {
      won++
      wonValue += v
    } else if (s === "LOST") {
      lost++
    } else {
      open++
      openValue += v
    }
  }
  const closed = won + lost
  return { count: deals.length, won, open, lost, wonValue, openValue, totalValue, winRate: closed ? won / closed : null }
}

const DAY = 86_400_000

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

/**
 * Parses a deal date. Date-only strings ("2026-09-30", how `close_date` arrives)
 * are LOCAL calendar dates, not UTC midnight (which would slip a day in SAST
 * comparisons); anything with a time/offset (`closed_at`) goes through Date.
 */
export function parseDealDate(raw: string | null | undefined): Date | null {
  if (!raw) return null
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(raw.trim())
  const d = m ? new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3])) : new Date(raw)
  return Number.isNaN(d.getTime()) ? null : d
}

function dealClosedAt(d: DealRow): Date | null {
  return parseDealDate(d.closed_at || d.close_date)
}

/** Whole local calendar days from a to b, immune to DST (works on Y/M/D components only). */
function daysBetween(a: Date, b: Date): number {
  return Math.round((Date.UTC(b.getFullYear(), b.getMonth(), b.getDate()) - Date.UTC(a.getFullYear(), a.getMonth(), a.getDate())) / DAY)
}

const pad2 = (n: number) => String(n).padStart(2, "0")
const dayLabel = (d: Date) => `${pad2(d.getDate())} ${MONTHS[d.getMonth()]}`
const dayKey = (d: Date) => `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`

/** Monday on/before `d` (ISO week start), as a local date. */
function isoWeekStart(d: Date): Date {
  const back = (d.getDay() + 6) % 7
  return new Date(d.getFullYear(), d.getMonth(), d.getDate() - back)
}

export interface WonBucket {
  /** Sortable key: YYYY-MM-DD (day, or Monday for weeks) or YYYY-MM (months). */
  key: string
  label: string
  revenue: number
  deals: number
}

/**
 * Won revenue + won deal counts bucketed by LOCAL calendar close date:
 * 7D / 30D = that many local days ending today (today included), 90D = 13 ISO
 * weeks (Mon-start) ending with the current week, 1Y = 12 calendar months
 * ending with the current month. Boundary days are included; deals closing
 * after today, or with no close date, are not placed. Buckets with no deals
 * are real zeros.
 */
export function bucketWonDeals(deals: DealRow[], range: TimeRange, now: Date = new Date()): WonBucket[] {
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  let starts: Date[]
  let index: (t: Date) => number
  let labelOf: (d: Date) => string
  let keyOf: (d: Date) => string
  if (range === "1Y") {
    const first = new Date(today.getFullYear(), today.getMonth() - 11, 1)
    starts = Array.from({ length: 12 }, (_, i) => new Date(first.getFullYear(), first.getMonth() + i, 1))
    index = (t) => (t.getFullYear() - first.getFullYear()) * 12 + (t.getMonth() - first.getMonth())
    labelOf = (d) => `${MONTHS[d.getMonth()]} ${d.getFullYear()}`
    keyOf = (d) => `${d.getFullYear()}-${pad2(d.getMonth() + 1)}`
  } else if (range === "90D") {
    const first = isoWeekStart(new Date(today.getFullYear(), today.getMonth(), today.getDate() - 12 * 7))
    starts = Array.from({ length: 13 }, (_, i) => new Date(first.getFullYear(), first.getMonth(), first.getDate() + i * 7))
    index = (t) => Math.floor(daysBetween(first, t) / 7)
    labelOf = dayLabel
    keyOf = dayKey
  } else {
    const n = range === "7D" ? 7 : 30
    const first = new Date(today.getFullYear(), today.getMonth(), today.getDate() - (n - 1))
    starts = Array.from({ length: n }, (_, i) => new Date(first.getFullYear(), first.getMonth(), first.getDate() + i))
    index = (t) => daysBetween(first, t)
    labelOf = dayLabel
    keyOf = dayKey
  }
  const buckets: WonBucket[] = starts.map((d) => ({ key: keyOf(d), label: labelOf(d), revenue: 0, deals: 0 }))
  for (const d of deals) {
    if (up(d.status) !== "WON") continue
    const t = dealClosedAt(d)
    if (!t) continue
    if (daysBetween(today, t) > 0) continue // closes after today
    const i = index(t)
    if (i < 0 || i >= buckets.length) continue
    buckets[i].revenue += num(d.value_zar)
    buckets[i].deals += 1
  }
  return buckets
}

/** Sum of the bucketed series (for the period KPI cards). */
export function sumBuckets(b: Array<{ revenue: number; deals: number }>): { revenue: number; deals: number } {
  return b.reduce((a, x) => ({ revenue: a.revenue + x.revenue, deals: a.deals + x.deals }), { revenue: 0, deals: 0 })
}

/** Open deals whose expected close date falls in the same calendar month as `now`. */
export function dealsClosingThisMonth(deals: DealRow[], now: Date = new Date()): DealRow[] {
  return deals.filter((d) => {
    if (up(d.status) === "WON" || up(d.status) === "LOST" || !d.close_date) return false
    const t = parseDealDate(d.close_date)
    return t !== null && t.getFullYear() === now.getFullYear() && t.getMonth() === now.getMonth()
  })
}

/** Open deals whose last update is older than `days` days. */
export function stalledOpenDeals(deals: DealRow[], days = 14, now: Date = new Date()): DealRow[] {
  return deals.filter((d) => {
    const s = up(d.status)
    if (s === "WON" || s === "LOST") return false
    const t = new Date(d.updated_at || d.created_at || "").getTime()
    return Number.isFinite(t) && now.getTime() - t > days * DAY
  })
}

export interface TopDeal {
  client: string
  type: string
  amount: string
  stage: string
  won: boolean
  rep: string | null
}

/** Top deals by value. Only real fields: no invented rep names or clients. */
export function topDeals(deals: DealRow[], limit = 4): TopDeal[] {
  return [...deals]
    .sort((a, b) => num(b.value_zar) - num(a.value_zar))
    .slice(0, limit)
    .map((d) => {
      const won = up(d.status) === "WON"
      return {
        client: d.name || "Unnamed deal",
        type: d.lead_reference ? `Lead ${d.lead_reference}` : won ? "Closed won" : "Open deal",
        amount: fmtZar(num(d.value_zar)),
        stage: d.stage_name || (won ? "Closed Won" : up(d.status) === "LOST" ? "Closed Lost" : "In pipeline"),
        won,
        rep: d.owner_name || null,
      }
    })
}

export interface Insight {
  id: string
  title: string
  description: string
  category: string
  impact: "high" | "medium"
  actionPrompt: string
  agentType: string
}

const plural = (n: number, w: string) => `${n} ${w}${n === 1 ? "" : "s"}`

/**
 * Suggestions generated ONLY from real rows: deals from the sales service and
 * rule-based recommendations the CRM service already computed. Empty when there
 * is nothing to say (the UI then shows an honest empty state).
 */
export function buildInsights(
  deals: DealRow[] | null,
  crmRecommendations: Array<{ id?: string; title?: string; description?: string; impact?: string; category?: string }> | null,
  now: Date = new Date(),
  limit = 4,
): Insight[] {
  const out: Insight[] = []
  if (deals) {
    const t = dealTotals(deals)
    const closing = dealsClosingThisMonth(deals, now)
    if (closing.length > 0) {
      const v = closing.reduce((s, d) => s + num(d.value_zar), 0)
      out.push({
        id: "deals-closing",
        title: `${plural(closing.length, "deal")} closing this month`,
        description: `${fmtZar(v)} in open deals has an expected close date this month.`,
        category: "Sales Pipeline",
        impact: "high",
        actionPrompt: "Review the open deals with an expected close date this month and draft follow-ups to secure them.",
        agentType: "executive",
      })
    }
    const stalled = stalledOpenDeals(deals, 14, now)
    if (stalled.length > 0) {
      out.push({
        id: "deals-stalled",
        title: `${plural(stalled.length, "open deal")} untouched for 14+ days`,
        description: "These open deals have not been updated in over two weeks.",
        category: "Sales Pipeline",
        impact: "medium",
        actionPrompt: "List the open deals that have not been updated in 14 days and suggest next steps for each.",
        agentType: "executive",
      })
    }
    if (t.open > 0) {
      out.push({
        id: "deals-open",
        title: `${plural(t.open, "open deal")} in the pipeline`,
        description: `${fmtZar(t.openValue)} in open deals awaits closure.`,
        category: "Sales Pipeline",
        impact: "medium",
        actionPrompt: "Analyze our open sales deals in the pipeline and draft tailored follow-ups to accelerate closure.",
        agentType: "executive",
      })
    }
  }
  for (const r of crmRecommendations ?? []) {
    if (!r?.title) continue
    const cat = r.category || "CRM"
    out.push({
      id: `crm-${r.id ?? out.length}`,
      title: r.title,
      description: r.description ?? "",
      category: cat,
      impact: r.impact === "high" ? "high" : "medium",
      actionPrompt: `${r.title}. ${r.description ?? ""}`.trim(),
      agentType: cat === "Retention" ? "retention" : "executive",
    })
  }
  // High impact first, stable otherwise.
  return out
    .map((x, i) => ({ x, i }))
    .sort((a, b) => (a.x.impact === b.x.impact ? a.i - b.i : a.x.impact === "high" ? -1 : 1))
    .map((p) => p.x)
    .slice(0, limit)
}

/**
 * One-paragraph briefing assembled from real counts. Returns null when neither
 * source produced data (the UI shows a not-connected state instead).
 */
export function buildBriefing(deals: DealRow[] | null, customerTotal: number | null): string | null {
  if (!deals && customerTotal === null) return null
  const parts: string[] = []
  if (deals) {
    const t = dealTotals(deals)
    parts.push(
      t.count === 0
        ? "The sales pipeline has no deals yet."
        : `The sales pipeline tracks ${fmtZar(t.totalValue)} across ${plural(t.count, "deal")} (${t.won} won, ${t.open} open, ${t.lost} lost).`,
    )
  }
  if (customerTotal !== null) parts.push(`CRM records ${plural(customerTotal, "customer")}.`)
  return parts.join(" ")
}

export interface ActivityItem {
  id: string
  user: string
  action: string
  target: string
  time: string
}

/** Normalises CRM activity rows; drops rows without any descriptive text. */
export function toActivityItems(rows: unknown): ActivityItem[] {
  if (!Array.isArray(rows)) return []
  const out: ActivityItem[] = []
  for (const r of rows) {
    if (!r || typeof r !== "object") continue
    const a = r as Record<string, unknown>
    const user = String(a.user ?? "").trim()
    const action = String(a.action ?? "").trim()
    const target = String(a.target ?? "").trim()
    if (!action && !target) continue
    out.push({ id: String(a.id ?? `${out.length}`), user, action, target, time: String(a.time ?? "") })
  }
  return out
}

export function initials(name: string): string {
  const p = name.split(/\s+/).filter(Boolean)
  if (p.length === 0) return "?"
  return ((p[0][0] ?? "") + (p.length > 1 ? (p[p.length - 1][0] ?? "") : "")).toUpperCase()
}

/** Transform a ready Loadable; every other state passes through unchanged. */
export function mapLoadable<T, U>(l: Loadable<T>, fn: (data: T) => U): Loadable<U> {
  return l.state === "ready" ? { state: "ready", data: fn(l.data) } : l
}

/** CRM /customers is a `{items,total}` envelope (or a bare array). null when unreadable. */
export function customerTotalOf(payload: unknown): number | null {
  if (Array.isArray(payload)) return payload.length
  if (payload && typeof payload === "object") {
    const p = payload as { total?: unknown; items?: unknown }
    if (typeof p.total === "number") return p.total
    if (Array.isArray(p.items)) return p.items.length
  }
  return null
}

/** Case-insensitive count of rows whose `status` equals `status`. */
export function countStatus(rows: Array<{ status?: string | null }>, status: string): number {
  const s = status.toLowerCase()
  return rows.filter((r) => (r.status ?? "").toLowerCase() === s).length
}

/** Loadable list payloads: bare array or `{items}` envelope; anything else is treated as unreadable. */
export function listOf<T>(payload: unknown): T[] | null {
  if (Array.isArray(payload)) return payload as T[]
  const items = (payload as { items?: unknown } | null)?.items
  return Array.isArray(items) ? (items as T[]) : null
}

// ── Escalations: one definition everywhere ───────────────────────────────

/** The one label for the escalation headline count (module card AND KPI strip). */
export const OPEN_ESCALATIONS_LABEL = "Open + in progress"

/** Escalations that still need work: open AND in progress. Used by every Overview surface. */
export function openEscalationCount(stats: { open: number; inProgress: number }): number {
  return stats.open + stats.inProgress
}

// ── Deal headline totals: server summary first, real rows as fallback ────

/** Contract of GET /svc/sales/deals/summary. Decimals may arrive as strings. */
export interface DealSummary {
  count: number | string
  total_value_zar: number | string
  won_count: number | string
  won_value_zar: number | string
  open_count: number | string
  open_value_zar: number | string
  lost_count: number | string
  lost_value_zar: number | string
}

export interface ResolvedTotals extends DealTotals {
  source: "summary" | "rows"
  /** Rows-derived and the list was cut off (X-Total-Count > rows loaded): figures are lower bounds. */
  partial: boolean
}

const hasNum = (v: unknown) => (typeof v === "number" && Number.isFinite(v)) || (typeof v === "string" && v.trim() !== "" && Number.isFinite(Number(v)))

/** A usable summary payload, or null (missing field => ignore it and fall back to rows). */
export function readDealSummary(payload: unknown): DealSummary | null {
  if (!payload || typeof payload !== "object") return null
  const p = payload as Record<string, unknown>
  const keys = ["count", "total_value_zar", "won_count", "won_value_zar", "open_count", "open_value_zar", "lost_count", "lost_value_zar"]
  return keys.every((k) => hasNum(p[k])) ? (payload as DealSummary) : null
}

/**
 * Headline deal figures. Uses the server summary when it answered (exact, no row
 * cap); otherwise sums the loaded rows and flags `partial` if the list was truncated.
 * null when neither source is available.
 */
export function resolveDealTotals(
  rows: DealRow[] | null,
  summary: DealSummary | null,
  rowsTotal: number | null = null,
): ResolvedTotals | null {
  if (summary) {
    const won = num(summary.won_count)
    const lost = num(summary.lost_count)
    return {
      count: num(summary.count),
      won,
      open: num(summary.open_count),
      lost,
      wonValue: num(summary.won_value_zar),
      openValue: num(summary.open_value_zar),
      totalValue: num(summary.total_value_zar),
      winRate: won + lost ? won / (won + lost) : null,
      source: "summary",
      partial: false,
    }
  }
  if (!rows) return null
  return { ...dealTotals(rows), source: "rows", partial: rowsTotal !== null && rowsTotal > rows.length }
}

/** Append "+" to a rendered figure that is only a lower bound. */
export const lowerBound = (text: string, partial: boolean) => (partial ? `${text}+` : text)

// ── Pipeline by stage, in the real stage order ───────────────────────────

/** Stage names ordered by `sort_order` from /pipeline/stages; [] when unreadable. */
export function stageNamesInOrder(payload: unknown): string[] {
  const rows = listOf<{ name?: string; sort_order?: number }>(payload) ?? (payload as { data?: unknown })?.data
  const list = Array.isArray(rows) ? (rows as Array<{ name?: string; sort_order?: number }>) : []
  return list
    .filter((r) => r && typeof r.name === "string" && r.name)
    .map((r, i) => ({ name: r.name as string, o: typeof r.sort_order === "number" ? r.sort_order : i, i }))
    .sort((a, b) => a.o - b.o || a.i - b.i)
    .map((r) => r.name)
}

/**
 * Open deals grouped by stage. Stages follow `stageOrder` (real pipeline order);
 * stages not in it come after, alphabetically (stable, not first-seen);
 * "Unstaged" is always last.
 */
export function pipelineByStage(
  deals: DealRow[],
  stageOrder: string[] = [],
): Array<{ month: string; revenue: number; deals: number }> {
  const m = new Map<string, { month: string; revenue: number; deals: number }>()
  for (const d of deals) {
    const st = up(d.status)
    if (st === "WON" || st === "LOST") continue
    const key = d.stage_name || "Unstaged"
    const cur = m.get(key) ?? { month: key, revenue: 0, deals: 0 }
    cur.revenue += num(d.value_zar)
    cur.deals += 1
    m.set(key, cur)
  }
  const rank = (name: string) => {
    if (name === "Unstaged") return Number.MAX_SAFE_INTEGER
    const i = stageOrder.indexOf(name)
    return i === -1 ? stageOrder.length : i
  }
  return [...m.values()].sort((a, b) => rank(a.month) - rank(b.month) || a.month.localeCompare(b.month))
}

// ── Corporate KPI banner ─────────────────────────────────────────────────

export interface CorpKpiView {
  targetText: string
  actualText: string
  /** Achievement badge; only when BOTH sides are known. null otherwise (never a blanket 'Not connected'). */
  badge: string | null
}

/** Target and actual are shown separately and truthfully; each side has its own state. */
export function corpKpiView(
  snap: { budget: number | null; actual: number | null; achievementPct: number | null } | null | undefined,
): CorpKpiView {
  const budget = snap?.budget ?? null
  const actual = snap?.actual ?? null
  return {
    targetText: budget !== null && budget > 0 ? fmtZar(budget) : "No target set",
    actualText: actual !== null ? fmtZar(actual) : "Not connected",
    badge: snap?.achievementPct != null ? `${snap.achievementPct.toFixed(1)}% of target` : null,
  }
}
