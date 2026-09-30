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

export function fmtZar(n: number): string {
  return `R ${Math.round(n).toLocaleString("en-ZA")}`
}

/** Compact currency for chart cards: R 1.25M / R 340K / R 950. */
export function fmtZarCompact(n: number): string {
  if (Math.abs(n) >= 1_000_000) return `R ${(n / 1_000_000).toFixed(2)}M`
  if (Math.abs(n) >= 1_000) return `R ${(n / 1_000).toFixed(0)}K`
  return `R ${Math.round(n).toLocaleString("en-ZA")}`
}

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

function dealClosedAt(d: DealRow): number | null {
  const raw = d.closed_at || d.close_date
  if (!raw) return null
  const t = new Date(raw).getTime()
  return Number.isFinite(t) ? t : null
}

/**
 * Won revenue + won deal counts bucketed by close date. 7D/30D are daily,
 * 90D weekly, 1Y monthly. Buckets with no deals are real zeros. Deals without a
 * close date are not guessed into a bucket.
 */
export function bucketWonDeals(
  deals: DealRow[],
  range: TimeRange,
  now: Date = new Date(),
): Array<{ label: string; revenue: number; deals: number }> {
  const end = now.getTime()
  const spec =
    range === "7D"
      ? { n: 7, size: DAY }
      : range === "30D"
        ? { n: 30, size: DAY }
        : range === "90D"
          ? { n: 13, size: 7 * DAY }
          : { n: 12, size: 30 * DAY }
  const start = end - spec.n * spec.size
  const buckets = Array.from({ length: spec.n }, (_, i) => {
    const t = new Date(start + (i + 1) * spec.size)
    const label =
      range === "1Y"
        ? t.toLocaleDateString("en-ZA", { month: "short", year: "2-digit" })
        : t.toLocaleDateString("en-ZA", { day: "2-digit", month: "short" })
    return { label, revenue: 0, deals: 0 }
  })
  for (const d of deals) {
    if (up(d.status) !== "WON") continue
    const t = dealClosedAt(d)
    if (t === null || t <= start || t > end) continue
    const idx = Math.min(spec.n - 1, Math.floor((t - start) / spec.size))
    buckets[idx].revenue += num(d.value_zar)
    buckets[idx].deals += 1
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
    const t = new Date(d.close_date)
    return !Number.isNaN(t.getTime()) && t.getFullYear() === now.getFullYear() && t.getMonth() === now.getMonth()
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
