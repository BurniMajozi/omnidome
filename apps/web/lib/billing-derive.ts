/**
 * Pure helpers for the Billing screen: role tiers (UI hints only, the server
 * enforces), aging-bucket mapping, collection-rate display, dunning result copy,
 * invoice status copy and the payment-method mix. No imports (node --test).
 */

// Role tiers (mirror of services/billing/access.py; the server stays authoritative).
// Use default service roles; optional server role extensions are not assumed.
const BILLING_ADMIN = ["billing_admin", "finance", "finance_admin", "admin", "tenant_admin", "owner", "platform_admin"]
const BILLING_CLERK = ["manager", "billing", "billing_clerk", "finance_clerk", "finance_manager"]

export type BillingTier = "admin" | "clerk" | "reader" | "none"

/** Highest tier the roles grant. `roles === null` (whoami unreadable) hides every write control. */
export function billingTier(roles: string[] | null | undefined): BillingTier {
  if (!roles || roles.length === 0) return "none"
  const r = roles.map((x) => x.trim().toLowerCase())
  if (r.some((x) => BILLING_ADMIN.includes(x))) return "admin"
  if (r.some((x) => BILLING_CLERK.includes(x))) return "clerk"
  return "reader"
}

export const ADMIN_ONLY_TIP = "Finance admin only"
export const CLERK_ONLY_TIP = "Billing clerk or admin only"

export const isBillingAdmin = (roles: string[] | null | undefined) => billingTier(roles) === "admin"
export const isBillingClerk = (roles: string[] | null | undefined) => {
  const t = billingTier(roles)
  return t === "admin" || t === "clerk"
}

// Aging
export interface AgingApiRow {
  bucket: string
  count: number
  total_zar: string | number
  legacy?: boolean
}
export interface AgingView {
  key: string
  label: string
  count: number
  total: string | number
  overdue: boolean
}

const NEW_ORDER = ["current", "1_30", "31_60", "61_90", "90_plus"]
const NEW_LABELS: Record<string, string> = {
  current: "Current",
  "1_30": "1-30 days",
  "31_60": "31-60 days",
  "61_90": "61-90 days",
  "90_plus": "91+ days",
}
const LEGACY_ORDER = ["current", "30_days", "60_days", "90_days_plus"]
const LEGACY_LABELS: Record<string, string> = {
  current: "Current",
  "30_days": "1-30 days",
  "60_days": "31-60 days",
  "90_days_plus": "61+ days",
}

/**
 * The service returns the distinct buckets AND the legacy keys. Use the new keys
 * when present (never add legacy + new together: that double counts), else fall
 * back to the legacy keys of an older deployment.
 */
export function mapAgingBuckets(rows: AgingApiRow[] | null | undefined): AgingView[] {
  const list = Array.isArray(rows) ? rows : []
  const byKey = new Map(list.map((r) => [r.bucket, r]))
  const hasNew = NEW_ORDER.slice(1).some((k) => byKey.has(k))
  const order = hasNew ? NEW_ORDER : LEGACY_ORDER
  const labels = hasNew ? NEW_LABELS : LEGACY_LABELS
  return order
    .filter((k) => byKey.has(k))
    .map((k) => {
      const r = byKey.get(k) as AgingApiRow
      return { key: k, label: labels[k], count: r.count, total: r.total_zar, overdue: k !== "current" }
    })
}

// Collection rate
/** Report value (percent 0..100 or null) -> display text. null/NaN -> "N/A"; clamped to 0..100. */
export function collectionRateText(rate: unknown): string {
  const n = typeof rate === "string" && rate.trim() !== "" ? Number(rate) : rate
  if (typeof n !== "number" || !Number.isFinite(n)) return "N/A"
  const clamped = Math.min(100, Math.max(0, n))
  return `${(Math.round(clamped * 10) / 10).toFixed(1)}%`
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
/** "2026-09" -> "Sep 2026". Unknown shapes are returned as given. */
export function periodLabel(period: string | null | undefined): string {
  const m = /^(\d{4})-(\d{2})$/.exec(period ?? "")
  if (!m) return period ?? ""
  const idx = Number(m[2]) - 1
  return idx >= 0 && idx < 12 ? `${MONTHS[idx]} ${m[1]}` : (period as string)
}

// Dunning results
export type Tone = "success" | "warning" | "danger" | "muted"
export interface ResultView {
  label: string
  tone: Tone
  detail: string | null
}

/** Honest label for a dunning action result. Never reports "sent" for something skipped or failed. */
export function describeDunningResult(result: string | null | undefined): ResultView {
  const raw = (result ?? "").trim()
  if (!raw) return { label: "Pending", tone: "muted", detail: null }
  const lower = raw.toLowerCase()
  if (lower === "skipped_no_provider") return { label: "Not sent: no SMS provider configured", tone: "warning", detail: null }
  if (lower === "skipped_suppressed") return { label: "Not sent: recipient suppressed", tone: "warning", detail: null }
  if (lower.startsWith("skipped")) return { label: "Skipped", tone: "warning", detail: raw.replace(/^skipped[_:\s-]*/i, "") || null }
  if (lower.startsWith("failed")) {
    const detail = raw.replace(/^failed[:_\s-]*/i, "").trim()
    return { label: "Failed", tone: "danger", detail: detail || null }
  }
  if (lower === "sent") return { label: "Sent", tone: "success", detail: null }
  if (lower === "suspended") return { label: "Service suspended", tone: "danger", detail: null }
  return { label: raw.replace(/_/g, " "), tone: "muted", detail: null }
}

const ACTION_LABELS: Record<string, string> = {
  sms_reminder: "SMS reminder",
  email_warning: "Email warning",
  auto_suspend: "Auto suspend",
  collections_handover: "Collections handover",
}
export const dunningActionLabel = (t: string) => ACTION_LABELS[t] ?? t.replace(/_/g, " ")

/** POST /dunning/process-tenant -> { processed, results: { <result>: count } } as readable lines. */
export function summariseDunningRun(body: unknown): string[] {
  const b = body as { processed?: unknown; results?: Record<string, unknown> } | null
  const results = b?.results && typeof b.results === "object" ? b.results : {}
  const processed = typeof b?.processed === "number" ? b.processed : 0
  if (processed === 0) return ["Nothing was due."]
  return Object.entries(results).map(([k, v]) => `${describeDunningResult(k).label}: ${Number(v) || 0}`)
}

// Invoice status
export interface StatusView {
  label: string
  tone: Tone
}
/** credit_issued is NOT paid: the customer is owed a refund. */
export function invoiceStatusView(status: string): StatusView {
  switch (status) {
    case "paid":
      return { label: "Paid", tone: "success" }
    case "credit_issued":
      return { label: "Refund required", tone: "danger" }
    case "overdue":
      return { label: "Overdue", tone: "danger" }
    case "sent":
    case "pending":
    case "draft":
    case "partially_paid":
      return { label: status.replace(/_/g, " "), tone: "warning" }
    case "voided":
      return { label: "Voided", tone: "muted" }
    default:
      return { label: status.replace(/_/g, " "), tone: "muted" }
  }
}

/** Which row actions make sense for an invoice (the server re-checks all of it). */
export function invoiceActions(inv: { status: string; number?: string }) {
  const isCreditNote = (inv.number ?? "").startsWith("CN-")
  const open = ["sent", "partially_paid", "overdue"].includes(inv.status)
  return {
    send: !isCreditNote && (inv.status === "draft" || open),
    pay: !isCreditNote && open,
    paystack: !isCreditNote && open,
    credit: !isCreditNote && ["sent", "partially_paid", "overdue", "paid"].includes(inv.status),
    void: !isCreditNote && ["draft", "sent", "overdue"].includes(inv.status),
  }
}

// Customers
export const shortCustomer = (id: string) => `Customer ${String(id).slice(0, 8)}`

export function customerNameMap(items: Array<{ id: string; first_name?: string | null; last_name?: string | null }>): Record<string, string> {
  const out: Record<string, string> = {}
  for (const c of Array.isArray(items) ? items : []) {
    const name = `${c.first_name ?? ""} ${c.last_name ?? ""}`.trim()
    if (c.id && name) out[c.id] = name
  }
  return out
}

export const customerLabel = (names: Record<string, string>, id: string) => names[id] ?? shortCustomer(id)

// Payment method mix
export interface PaymentLike {
  method: string
  amount_zar: string | number
  status: string
}
const centsOf = (v: string | number): number => {
  const n = typeof v === "string" ? Number(v) : v
  return Number.isFinite(n) ? Math.round(n * 100) : 0
}

/** Share of completed payment value per method (integer cents internally), 1 dp percent out. */
export function paymentMix(items: PaymentLike[]): Array<{ name: string; value: number }> {
  const totals = new Map<string, number>()
  for (const p of items) {
    if (p.status !== "completed") continue
    const cents = centsOf(p.amount_zar)
    if (!Number.isSafeInteger(cents) || cents <= 0) continue
    const next = (totals.get(p.method) ?? 0) + cents
    if (!Number.isSafeInteger(next)) return []
    totals.set(p.method, next)
  }
  const sum = [...totals.values()].reduce((a, b) => a + b, 0)
  if (!Number.isSafeInteger(sum)) return []
  return [...totals.entries()].map(([name, c]) => ({ name, value: sum > 0 ? Math.round((c / sum) * 1000) / 10 : 0 }))
}

export function showingLabel(shown: number, total: number): string {
  return shown >= total ? `Showing all ${total}` : `Showing ${shown} of ${total}`
}

/** Quote every field and neutralize formula leads, including whitespace prefixes. */
export function billingCsv(headers: string[], rows: unknown[][]): string {
  const cell = (v: unknown) => {
    let text = v == null ? "" : typeof v === "number" ? (Number.isFinite(v) ? String(v) : "") : String(v)
    if (typeof v !== "number" && /^[\s]*[=+\-@]|^[\t\r\n]/.test(text)) text = "'" + text
    return '"' + text.replace(/"/g, '""') + '"'
  }
  return "\uFEFF" + [headers, ...rows].map(row => row.map(cell).join(",")).join("\r\n") + "\r\n"
}
