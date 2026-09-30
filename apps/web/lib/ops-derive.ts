/**
 * Pure derivations for the Retention / Service / IoT / Network modules.
 *
 * Owner rule: no fabricated figures. Everything here is computed ONLY from rows
 * the backends actually returned (counts, sums, averages). No React / browser
 * imports so it can be unit-tested with node.
 */

// Type-only import (erased at runtime) so node --test can load this file without a resolver.
import type { Loadable } from "./service-state"

// ── HTTP outcome ─────────────────────────────────────────────────────────

/**
 * /svc/<iot|network|retention|support|communication> are next.config rewrites,
 * not route handlers. When the upstream container is down Next answers 500 with
 * a non-JSON body, while a real FastAPI failure is JSON `{"detail": ...}`
 * (services/common/middleware.py). So for rewrite-proxied services, a 500
 * without a JSON detail means "not running", not "error".
 */
export function loadableFromOps<T>(
  status: number | null,
  data: T | undefined,
  opts: { rewriteProxy?: boolean; hasJsonDetail?: boolean; message?: string } = {},
): Loadable<T> {
  // Same mapping as service-state.classifyHttpStatus (kept local: no runtime import).
  const unreachable = { state: "unreachable", status: null } as const
  if (opts.rewriteProxy && status === 500 && !opts.hasJsonDetail) return unreachable
  if (status === null || status === 0) return unreachable
  if (status >= 200 && status < 300) {
    return data !== undefined ? { state: "ready", data } : { state: "error", status, message: opts.message }
  }
  if (status === 502 || status === 503 || status === 504) return { state: "unreachable", status }
  if (status === 401 || status === 403) return { state: "denied", status }
  return { state: "error", status, message: opts.message }
}

/** All of these have finished loading (ready or failed). */
export function allSettled(...ls: Array<Loadable<unknown>>): boolean {
  return ls.every((l) => l.state !== "loading")
}

/** Data when ready, otherwise the fallback (used for secondary panels that degrade to empty). */
export function dataOr<T>(l: Loadable<T>, fallback: T): T {
  return l.state === "ready" ? l.data : fallback
}

/** Backends return either a bare array or a paginated `{items}` envelope. */
export function itemsOf<T>(payload: unknown): T[] {
  if (Array.isArray(payload)) return payload as T[]
  if (payload && typeof payload === "object" && Array.isArray((payload as { items?: unknown }).items)) {
    return (payload as { items: T[] }).items
  }
  return []
}

// ── small helpers ────────────────────────────────────────────────────────

export function relativeTime(iso: string | null | undefined, now: Date = new Date()): string {
  if (!iso) return "—"
  const t = new Date(iso).getTime()
  if (!Number.isFinite(t)) return "—"
  const s = Math.max(0, Math.round((now.getTime() - t) / 1000))
  if (s < 60) return "just now"
  const m = Math.round(s / 60)
  if (m < 60) return `${m} min ago`
  const h = Math.round(m / 60)
  if (h < 24) return `${h} hour${h === 1 ? "" : "s"} ago`
  const d = Math.round(h / 24)
  return `${d} day${d === 1 ? "" : "s"} ago`
}

export function countBy<T>(items: T[], key: (item: T) => string): Record<string, number> {
  const out: Record<string, number> = {}
  for (const it of items) {
    const k = key(it)
    out[k] = (out[k] ?? 0) + 1
  }
  return out
}

export function pct(part: number, whole: number, digits = 1): string {
  if (!whole) return "0%"
  return `${((part / whole) * 100).toFixed(digits)}%`
}

export function avg(nums: number[]): number | null {
  const v = nums.filter((n) => Number.isFinite(n))
  return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null
}

/** Tile text for a count that may be capped by page size. */
export function fmtInt(n: number): string {
  // Plain-space thousands ("1 234"), independent of the machine ICU (en-ZA uses NBSP).
  if (!Number.isFinite(n)) return "—"
  const r = Math.round(Math.abs(n))
  return `${n < 0 && r !== 0 ? "-" : ""}${String(r).replace(/\B(?=(\d{3})+(?!\d))/g, " ")}`
}

// ── Paged lists: truncation / partial-load signalling ────────────────────

/** What fetchAllPages actually managed to load, so headline counts stay honest. */
export interface PagedMeta {
  /** Rows actually loaded. */
  loaded: number
  /** Server total when it reported one (body `total` or X-Total-Count), else `loaded`. */
  total: number
  /** True when the server reported a total (or we could tell we reached the end). */
  totalKnown: boolean
  /** The page cap stopped the walk before the end of the list. */
  truncated: boolean
  /** 1-based page numbers that failed to load (never silently dropped). */
  failedPages: number[]
}

/** The loaded rows are a lower bound on the real list (cap hit, failed page, or short of the server total). */
export function isPartial(m: PagedMeta): boolean {
  return m.truncated || m.failedPages.length > 0 || m.loaded < m.total
}

/** A count computed from loaded rows: "N+" when the sample is partial (it is a lower bound). */
export function countText(n: number, m: PagedMeta): string {
  return `${fmtInt(n)}${isPartial(m) ? "+" : ""}`
}

/** The list size: the server total when known, else "N+" when we had to stop early. */
export function totalText(m: PagedMeta): string {
  return m.totalKnown ? fmtInt(m.total) : `${fmtInt(m.total)}${isPartial(m) ? "+" : ""}`
}

/** One line explaining a partial sample, or null when everything was loaded. */
export function partialNote(m: PagedMeta): string | null {
  if (m.failedPages.length > 0) {
    return `Partial: ${m.failedPages.length === 1 ? "a page" : `${m.failedPages.length} pages`} failed to load, so counts may be higher.`
  }
  if (m.truncated || m.loaded < m.total) {
    return m.totalKnown
      ? `Partial: counted in the first ${fmtInt(m.loaded)} of ${fmtInt(m.total)} rows.`
      : `Partial: counted in the first ${fmtInt(m.loaded)} rows; more exist.`
  }
  return null
}

/**
 * How many pages to walk. `total` null = unknown (caller walks until a short
 * page). Known total: pages needed, capped at maxPages, plus whether the cap
 * truncates.
 */
export function planPages(total: number | null, pageSize: number, maxPages: number): { pages: number; truncated: boolean } {
  if (total === null) return { pages: maxPages, truncated: false }
  const needed = Math.max(1, Math.ceil(total / pageSize))
  return { pages: Math.min(needed, maxPages), truncated: needed > maxPages }
}

/** Network tile figures that stay consistent when only the first page(s) loaded. */
export function networkTile(
  rows: NetworkDeviceRow[],
  m: PagedMeta,
): { active: string; registered: string; activeOfRegistered: string; note: string | null } {
  const s = networkDeviceStats(rows)
  return {
    active: countText(s.active, m),
    registered: totalText(m),
    activeOfRegistered: `${countText(s.active, m)} of ${totalText(m)}`,
    note: partialNote(m),
  }
}

// ── Retention (CRM) ──────────────────────────────────────────────────────

export interface CrmCustomerRow {
  id: string
  first_name?: string
  last_name?: string
  account_number?: string | null
  status?: string
  mrr?: number
  customer_type?: string
  health?: string
  created_at?: string
}

export const HEALTH_ORDER = ["Excellent", "Good", "At Risk", "Critical", "Unknown"] as const

export function healthBuckets(customers: CrmCustomerRow[]): Array<{ name: string; value: number }> {
  const c = countBy(customers, (x) => x.health || "Unknown")
  return HEALTH_ORDER.map((name) => ({ name, value: c[name] ?? 0 })).filter((b) => b.value > 0)
}

/** Customers CRM itself flags as at risk (health score < 60) — the watchlist. */
export function atRiskCustomers(customers: CrmCustomerRow[]): CrmCustomerRow[] {
  return customers.filter((c) => c.health === "At Risk" || c.health === "Critical")
}

/** Average monthly recurring revenue per customer segment, from customers with billing data. */
export function mrrBySegment(customers: CrmCustomerRow[]): Array<{ segment: string; avgMrr: number; customers: number }> {
  const by: Record<string, number[]> = {}
  for (const c of customers) {
    if (typeof c.mrr === "number" && c.mrr > 0) (by[c.customer_type || "Residential"] ??= []).push(c.mrr)
  }
  return Object.entries(by).map(([segment, v]) => ({
    segment,
    avgMrr: Math.round(v.reduce((a, b) => a + b, 0) / v.length),
    customers: v.length,
  }))
}

/** dashboard-summary's Total Customers tile carries Active/Suspended/Churned in backDetails. */
export function statusCountsFromSummary(
  kpis: Array<{ backDetails?: Array<{ label: string; value: string }> }> | undefined,
): { active: number; suspended: number; churned: number } | null {
  const details = kpis?.[0]?.backDetails
  if (!details) return null
  const get = (label: string) => {
    const n = Number(details.find((d) => d.label === label)?.value)
    return Number.isFinite(n) ? n : null
  }
  const active = get("Active")
  const suspended = get("Suspended")
  const churned = get("Churned")
  if (active === null || suspended === null || churned === null) return null
  return { active, suspended, churned }
}

// Task/issue vocabularies from different backends are normalised to what ModuleLayout renders.
export type LayoutTaskStatus = "todo" | "in-progress" | "done"
export type LayoutPriority = "urgent" | "high" | "normal" | "low"

export function normTaskStatus(s: string | null | undefined): LayoutTaskStatus {
  const v = (s ?? "").toLowerCase().replace(/[\s_]+/g, "-")
  if (v === "done" || v === "completed" || v === "complete" || v === "closed") return "done"
  if (v === "in-progress" || v === "doing" || v === "started") return "in-progress"
  return "todo"
}

export function normPriority(p: string | null | undefined): LayoutPriority {
  const v = (p ?? "").toLowerCase()
  if (v === "urgent" || v === "critical") return "urgent"
  if (v === "high") return "high"
  if (v === "low") return "low"
  return "normal"
}

export function normSeverity(s: string | null | undefined): "critical" | "high" | "medium" | "low" {
  const v = (s ?? "").toLowerCase()
  return v === "critical" || v === "high" || v === "medium" || v === "low" ? v : "medium"
}

export function normIssueStatus(s: string | null | undefined): "open" | "in-progress" | "resolved" {
  const v = (s ?? "").toLowerCase().replace(/[\s_]+/g, "-")
  if (v === "resolved" || v === "closed" || v === "done") return "resolved"
  if (v === "in-progress") return "in-progress"
  return "open"
}

// ── Service (communication escalations + tasks) ──────────────────────────

export interface EscalationRow {
  id: string
  ticket_id?: string | null
  reason?: string | null
  status: string
  assigned_to?: string | null
  created_at: string
  updated_at: string
}

export const isResolvedStatus = (s: string) => s === "resolved" || s === "closed"

export function escalationStats(items: EscalationRow[], now: Date = new Date()) {
  const byStatus = countBy(items, (e) => e.status)
  const open = byStatus["open"] ?? 0
  const inProgress = byStatus["in_progress"] ?? 0
  const resolved = (byStatus["resolved"] ?? 0) + (byStatus["closed"] ?? 0)
  const resolutionHours = items
    .filter((e) => isResolvedStatus(e.status))
    .map((e) => (new Date(e.updated_at).getTime() - new Date(e.created_at).getTime()) / 3_600_000)
    .filter((h) => Number.isFinite(h) && h >= 0)
  // Last 7 calendar days (UTC), oldest first: created that day vs resolved (last updated) that day.
  const days: Array<{ day: string; open: number; resolved: number }> = []
  for (let i = 6; i >= 0; i--) {
    const d = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate() - i))
    const key = d.toISOString().slice(0, 10)
    days.push({
      day: d.toLocaleDateString("en-ZA", { weekday: "short", timeZone: "UTC" }),
      open: items.filter((e) => e.created_at.slice(0, 10) === key).length,
      resolved: items.filter((e) => isResolvedStatus(e.status) && e.updated_at.slice(0, 10) === key).length,
    })
  }
  return {
    total: items.length,
    open,
    inProgress,
    resolved,
    avgResolutionHours: avg(resolutionHours),
    byStatus,
    days,
  }
}

// ── IoT (Home Assistant devices, alert rules, events) ────────────────────

export interface IotDeviceRow {
  id: string
  friendly_name: string
  device_type: string
  ha_domain?: string
  status: string
  battery_level?: number | null
  signal_strength?: number | null
  last_seen?: string | null
}

export interface IotEventRow {
  id: string
  event_type: string
  source?: string
  message?: string | null
  created_at: string
}

export function deviceStats(devices: IotDeviceRow[]) {
  const byStatus = countBy(devices, (d) => d.status)
  const online = byStatus["online"] ?? 0
  const byType = Object.entries(countBy(devices, (d) => d.device_type)).map(([type, count]) => ({
    type,
    count,
    online: devices.filter((d) => d.device_type === type && d.status === "online").length,
    offline: devices.filter((d) => d.device_type === type && d.status !== "online").length,
  }))
  const withBattery = devices.filter((d) => typeof d.battery_level === "number")
  return {
    total: devices.length,
    online,
    byStatus,
    byType,
    lowBattery: withBattery.filter((d) => (d.battery_level as number) < 20).length,
    withBattery: withBattery.length,
  }
}

/** Events per hour for the trailing 24 hours (oldest first). */
export function eventsPerHour(events: IotEventRow[], now: Date = new Date()): Array<{ hour: string; events: number }> {
  const start = now.getTime() - 24 * 3_600_000
  const buckets = Array.from({ length: 24 }, (_, i) => ({
    hour: new Date(start + (i + 1) * 3_600_000).getHours().toString().padStart(2, "0") + ":00",
    events: 0,
  }))
  for (const e of events) {
    const t = new Date(e.created_at).getTime()
    if (!Number.isFinite(t) || t <= start || t > now.getTime()) continue
    const idx = Math.min(23, Math.floor((t - start) / 3_600_000))
    buckets[idx].events += 1
  }
  return buckets
}

// ── Network ──────────────────────────────────────────────────────────────

export interface NetworkDeviceRow {
  id: string
  device_type: string
  status: string
  serial_number?: string | null
  management_ip?: string | null
  last_seen?: string | null
}

export interface NetworkMetricRow {
  metric_type: string
  metric_value: number
  collected_at: string
}

export function networkDeviceStats(devices: NetworkDeviceRow[]) {
  const byStatus = countBy(devices, (d) => d.status)
  const byType = Object.entries(countBy(devices, (d) => d.device_type)).map(([type, count]) => ({
    type,
    active: devices.filter((d) => d.device_type === type && d.status === "active").length,
    count,
  }))
  return { total: devices.length, active: byStatus["active"] ?? 0, byStatus, byType }
}

/** Average of one metric per hour for the trailing 24h; hours with no samples are null (a gap, not zero). */
export function metricByHour(
  rows: NetworkMetricRow[],
  metricType: string,
  now: Date = new Date(),
): Array<{ hour: string; value: number | null }> {
  const start = now.getTime() - 24 * 3_600_000
  const sums = Array.from({ length: 24 }, () => ({ s: 0, n: 0 }))
  for (const r of rows) {
    if (r.metric_type !== metricType) continue
    const t = new Date(r.collected_at).getTime()
    if (!Number.isFinite(t) || t <= start || t > now.getTime()) continue
    const b = sums[Math.min(23, Math.floor((t - start) / 3_600_000))]
    b.s += Number(r.metric_value)
    b.n += 1
  }
  return sums.map((b, i) => ({
    hour: new Date(start + (i + 1) * 3_600_000).getHours().toString().padStart(2, "0") + ":00",
    value: b.n ? Math.round((b.s / b.n) * 100) / 100 : null,
  }))
}

export function latestAverage(rows: NetworkMetricRow[], metricType: string): number | null {
  return avg(rows.filter((r) => r.metric_type === metricType).map((r) => Number(r.metric_value)))
}
