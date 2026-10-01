/**
 * Pure helpers for the Talent (HR) module. No React / browser imports so they
 * can be unit-tested with `node --test`.
 *
 * Owner rule: no fabricated figures. Every number the Talent UI shows is
 * computed here from real rows, or the helper returns null/"—" so the UI can
 * show an honest "Not connected" / "Set company targets" state.
 */


// ── Roles ────────────────────────────────────────────────────────────────

/** Roles the HR backend treats as HR-admin (payroll, profiles, approvals, cascade). */
export const HR_ADMIN_ROLES = ["hr_manager", "hr", "hr_admin", "admin", "tenant_admin", "owner", "org_admin"] as const

export function hasHrAdminRole(roles: ReadonlyArray<string> | null | undefined): boolean {
  if (!roles || roles.length === 0) return false
  return roles.some((r) => (HR_ADMIN_ROLES as ReadonlyArray<string>).includes(String(r).trim().toLowerCase()))
}

// ── Errors from fetchHR ("HR API error 422: {...}") ───────────────────────

export interface HrErrorInfo {
  status: number | null
  /** Human-readable server text (never raw JSON when a `detail` is present). */
  message: string
}

/** Turn a response body into readable text: prefers FastAPI `detail` (string | list | object). */
export function readableErrorBody(body: string, status?: number | null): string {
  const text = (body ?? "").trim()
  if (!text) return status ? `HTTP ${status}` : "Request failed"
  try {
    const j = JSON.parse(text)
    const d = j?.detail ?? j?.message
    if (typeof d === "string") return d
    if (Array.isArray(d)) {
      const parts = d.map((x) => {
        if (typeof x === "string") return x
        const loc = Array.isArray(x?.loc) ? x.loc.filter((p: unknown) => p !== "body").join(".") : ""
        const msg = x?.msg ?? JSON.stringify(x)
        return loc ? `${loc}: ${msg}` : String(msg)
      })
      return parts.join("; ")
    }
    if (d && typeof d === "object") return d.message ?? JSON.stringify(d)
  } catch {
    /* not JSON */
  }
  return text.slice(0, 300)
}

/** Parse an Error message produced by fetchHR ("HR API error <status>: <body>"). */
export function parseHrError(err: unknown): HrErrorInfo {
  const anyErr = err as { status?: unknown; detail?: unknown; message?: unknown } | null
  if (anyErr && typeof anyErr === "object" && typeof anyErr.status === "number") {
    return {
      status: anyErr.status,
      message: typeof anyErr.detail === "string" && anyErr.detail ? anyErr.detail : String(anyErr.message ?? ""),
    }
  }
  const raw = err instanceof Error ? err.message : String(err)
  const m = raw.match(/^HR API error (\d+):\s*([\s\S]*)$/)
  if (!m) return { status: null, message: raw }
  const status = Number(m[1])
  return { status, message: readableErrorBody(m[2], status) }
}

export function hrErrorStatus(err: unknown): number | null {
  return parseHrError(err).status
}

export function isDeniedError(err: unknown): boolean {
  const s = hrErrorStatus(err)
  return s === 401 || s === 403
}

/** 503 from payroll run creation whose text says the PAYE tables are not verified. */
export function isUnverifiedTablesError(err: unknown): boolean {
  const { status, message } = parseHrError(err)
  return status === 503 && /not verified|unverified|paye tables/i.test(message)
}

/** Message for inline display next to a form; includes the server's own wording. */
export function formatHrError(err: unknown): string {
  const { status, message } = parseHrError(err)
  if (status === 403) return `Not permitted: ${message || "your role cannot do this"}`
  if (status === 422) return `Rejected by the server: ${message}`
  return message || (status ? `HTTP ${status}` : "Request failed")
}

// ── KPI sheet helpers ────────────────────────────────────────────────────

/** Achieved level selector is always an integer 1..5 (anything else becomes 3, the neutral level). */
export function clampLevel(n: unknown): number {
  const v = Math.round(Number(n))
  if (!Number.isFinite(v)) return 3
  return Math.min(5, Math.max(1, v))
}

export interface CompositeShape {
  total?: number | null
  shared_score?: number | null
  values_score?: number | null
  individual_score?: number | null
  values_rated?: boolean
  company_missing?: boolean
}

export interface HeadlineInput {
  /** Server composite (only trusted when the sheet has no unsaved edits). */
  composite?: CompositeShape | null
  sheetDirty: boolean
  /** Client-side fallback estimate, or null when it cannot be computed. */
  localEstimate: number | null
  /** The sheet is a not-persisted template: there is no score at all. */
  isTemplate?: boolean
}

export interface Headline {
  value: number | null
  /** server = backend composite; estimate = client formula (must be labelled); none = nothing to show */
  basis: "server" | "estimate" | "none"
}

/**
 * One headline number. Server `composite` wins whenever the sheet has no
 * unsaved edits; the client formula is only a labelled fallback. A template
 * sheet (nothing saved) has no score.
 */
export function pickHeadline(i: HeadlineInput): Headline {
  if (i.isTemplate) return { value: null, basis: "none" }
  const t = i.composite?.total
  if (!i.sheetDirty && typeof t === "number" && Number.isFinite(t)) return { value: t, basis: "server" }
  if (i.localEstimate !== null && Number.isFinite(i.localEstimate)) return { value: i.localEstimate, basis: "estimate" }
  return { value: null, basis: "none" }
}

export interface CompanyIndexInput {
  company_missing?: boolean
  corporate_attainment_index?: number | null
  company_shared_score_pct?: number | null
  sales_budget_zar?: number | null
  cost_budget_zar?: number | null
  profit_budget_zar?: number | null
}

export type IndexTile = { kind: "value"; value: number } | { kind: "set_targets" }

/**
 * Company index tile. `null` index from the backend, `company_missing: true`,
 * or any budget at 0 => "Set company targets" (never a 35% / 100% placeholder).
 */
export function companyIndexTile(c: CompanyIndexInput | null | undefined): IndexTile {
  if (!c) return { kind: "set_targets" }
  if (c.company_missing === true) return { kind: "set_targets" }
  const budgets = [c.sales_budget_zar, c.cost_budget_zar, c.profit_budget_zar].map((b) => Number(b))
  if (budgets.some((b) => !Number.isFinite(b) || b <= 0)) return { kind: "set_targets" }
  const idx = c.corporate_attainment_index
  if (idx === null) return { kind: "set_targets" }
  if (typeof idx === "number" && Number.isFinite(idx)) return { kind: "value", value: idx }
  const shared = c.company_shared_score_pct
  if (typeof shared === "number" && Number.isFinite(shared)) return { kind: "value", value: shared }
  return { kind: "set_targets" }
}

/** Level -> % of target (level 3 = 100%); same mapping the HR backend uses. */
export function levelScorePct(level: unknown): number {
  return (clampLevel(level) / 3) * 100
}

export interface CompositeInputs {
  /** Company attainment index (0-100) or null when targets are not set. */
  companyIndex: number | null
  /** The four 1-5 values ratings, or null until all four are rated. */
  valuesRatings: ReadonlyArray<number> | null
  kpis: ReadonlyArray<{ current_level?: number | null; weight_pct?: number | null }>
  /** Sheet weights: shared + values + individual (the individual weight is the sum of KPI weights, as saved). */
  weights: { shared: number; values: number; individual: number }
}

export interface CompositeBreakdown {
  total: number
  sharedPts: number | null
  valuesPts: number | null
  indivPts: number
  companyMissing: boolean
  valuesRated: boolean
  valuesScore: number | null
  individualScore: number
}

/**
 * Client-side ESTIMATE that mirrors the backend formula
 * (shared*w/100 + values*w/100 + weighted-average KPI score * individual weight/100).
 * Only used while the sheet has unsaved edits; always label it "estimate".
 */
export function estimateComposite(i: CompositeInputs): CompositeBreakdown {
  const companyMissing = i.companyIndex === null
  const valuesRated = !!i.valuesRatings && i.valuesRatings.length === 4
  const valuesScore = valuesRated ? ((i.valuesRatings as ReadonlyArray<number>).reduce((a, b) => a + b, 0) / 4 / 3) * 100 : null
  const wSum = i.kpis.reduce((a, k) => a + (Number(k.weight_pct) || 0), 0)
  const individualScore = wSum > 0 ? i.kpis.reduce((a, k) => a + levelScorePct(k.current_level ?? 3) * (Number(k.weight_pct) || 0), 0) / wSum : 0
  const sharedPts = companyMissing ? null : ((i.companyIndex as number) * i.weights.shared) / 100
  const valuesPts = valuesScore === null ? null : (valuesScore * i.weights.values) / 100
  const indivPts = (individualScore * i.weights.individual) / 100
  const total = Math.round(((sharedPts ?? 0) + (valuesPts ?? 0) + indivPts) * 10) / 10
  return { total, sharedPts, valuesPts, indivPts, companyMissing, valuesRated, valuesScore, individualScore }
}

/** Breakdown points taken from the SERVER composite fields so they always add up to the server headline. */
export function pointsFromComposite(
  c: CompositeShape,
  weights: { shared: number; values: number; individual: number },
): CompositeBreakdown | null {
  if (typeof c.total !== "number" || !Number.isFinite(c.total)) return null
  const companyMissing = c.company_missing === true
  const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null)
  const shared = num(c.shared_score)
  const values = num(c.values_score)
  const indiv = num(c.individual_score) ?? 0
  return {
    total: c.total,
    sharedPts: companyMissing || shared === null ? null : (shared * weights.shared) / 100,
    valuesPts: values === null ? null : (values * weights.values) / 100,
    indivPts: (indiv * weights.individual) / 100,
    companyMissing,
    valuesRated: c.values_rated === true || values !== null,
    valuesScore: values,
    individualScore: indiv,
  }
}

// ── Concurrency ─────────────────────────────────────────────────────────

/** Map with at most `limit` in flight; result order matches input; a failing item yields `fallback(err)`. */
export async function mapLimit<T, R>(
  items: ReadonlyArray<T>,
  limit: number,
  fn: (item: T, index: number) => Promise<R>,
  onError: (err: unknown, item: T, index: number) => R,
): Promise<R[]> {
  const out = new Array<R>(items.length)
  let next = 0
  const worker = async () => {
    for (;;) {
      const i = next++
      if (i >= items.length) return
      try {
        out[i] = await fn(items[i], i)
      } catch (e) {
        out[i] = onError(e, items[i], i)
      }
    }
  }
  const n = Math.max(1, Math.min(limit, items.length))
  await Promise.all(Array.from({ length: n }, worker))
  return out
}

export type FanOutResult<R> = { ok: true; rows: R } | { ok: false; err: unknown }

/**
 * Combine per-employee fan-out results: rows from the ones that worked. Only when
 * EVERY call failed is the first error rethrown (so a 403 shows "Not permitted"
 * instead of an empty list that looks like zero rows).
 */
export function collectOrThrow<R>(results: ReadonlyArray<FanOutResult<ReadonlyArray<R>>>): R[] {
  const fails = results.filter((r): r is { ok: false; err: unknown } => !r.ok)
  if (results.length > 0 && fails.length === results.length) throw fails[0].err
  const out: R[] = []
  for (const r of results) if (r.ok) out.push(...r.rows)
  return out
}

/** Exits whose last working day (else notice date) falls in the 12 months up to `now` (future-dated exits are not yet turnover). */
export function exitsInLast12Months(
  exits: ReadonlyArray<{ last_working_date?: string | null; notice_date?: string | null }>,
  now: Date,
): number {
  const since = new Date(now.getFullYear() - 1, now.getMonth(), now.getDate()).getTime()
  let n = 0
  for (const x of exits) {
    const d = new Date(x.last_working_date || x.notice_date || "")
    if (!Number.isNaN(d.getTime()) && d.getTime() >= since && d.getTime() <= now.getTime()) n += 1
  }
  return n
}

/** Mean of the real scores only (null scores are skipped). null when nothing is scored. */
export function averageScore(rows: ReadonlyArray<{ overall_score: number | null }>): { avg: number; scored: number } | null {
  const vals = rows.map((r) => r.overall_score).filter((v): v is number => typeof v === "number" && Number.isFinite(v))
  if (vals.length === 0) return null
  return { avg: Math.round((vals.reduce((a, b) => a + b, 0) / vals.length) * 10) / 10, scored: vals.length }
}

// ── Workforce analytics from real rows ─────────────────────────────────

export interface MonthBucket {
  key: string // YYYY-MM
  label: string // "Oct 25"
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

/** The last `count` calendar months ending with `now`'s month, oldest first. */
export function lastMonths(now: Date, count = 12): MonthBucket[] {
  const out: MonthBucket[] = []
  for (let i = count - 1; i >= 0; i--) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1)
    out.push({
      key: `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`,
      label: `${MONTHS[d.getMonth()]} ${String(d.getFullYear()).slice(2)}`,
    })
  }
  return out
}

function monthKey(dateStr: string | null | undefined): string | null {
  if (!dateStr) return null
  const m = String(dateStr).match(/^(\d{4})-(\d{2})/)
  return m ? `${m[1]}-${m[2]}` : null
}

export interface PipelinePoint {
  month: string
  hires: number
  exits: number
  net: number
}

/**
 * Hires from real employee hire_date, exits from real exit records
 * (last_working_date, else notice_date). Only the buckets in the window count.
 */
export function hiresVsExits(
  employees: ReadonlyArray<{ hire_date?: string | null }>,
  exits: ReadonlyArray<{ last_working_date?: string | null; notice_date?: string | null }>,
  now: Date,
  months = 12,
): PipelinePoint[] {
  const buckets = lastMonths(now, months)
  const hires = new Map<string, number>()
  const out = new Map<string, number>()
  for (const e of employees) {
    const k = monthKey(e.hire_date)
    if (k) hires.set(k, (hires.get(k) ?? 0) + 1)
  }
  for (const x of exits) {
    const k = monthKey(x.last_working_date) ?? monthKey(x.notice_date)
    if (k) out.set(k, (out.get(k) ?? 0) + 1)
  }
  return buckets.map((b) => {
    const h = hires.get(b.key) ?? 0
    const x = out.get(b.key) ?? 0
    return { month: b.label, hires: h, exits: x, net: h - x }
  })
}

export function departmentCounts(
  employees: ReadonlyArray<{ department?: string | null }>,
): Array<{ department: string; count: number }> {
  const counts = new Map<string, number>()
  for (const e of employees) {
    const d = (e.department ?? "").trim() || "Unassigned"
    counts.set(d, (counts.get(d) ?? 0) + 1)
  }
  return [...counts.entries()].map(([department, count]) => ({ department, count })).sort((a, b) => b.count - a.count)
}

/** Turnover % = exits in the trailing 12 months / current headcount. null when headcount is 0. */
export function turnoverPct(exitsLast12m: number, headcount: number): number | null {
  if (!Number.isFinite(headcount) || headcount <= 0) return null
  return Math.round((exitsLast12m / headcount) * 1000) / 10
}

/** Whole years between a hire date and `now` (floor); null for an unparseable date. */
export function yearsOfService(hireDate: string | null | undefined, now: Date): number | null {
  if (!hireDate) return null
  const d = new Date(hireDate)
  if (Number.isNaN(d.getTime())) return null
  let y = now.getFullYear() - d.getFullYear()
  const beforeAnniv = now.getMonth() < d.getMonth() || (now.getMonth() === d.getMonth() && now.getDate() < d.getDate())
  if (beforeAnniv) y -= 1
  return Math.max(0, y)
}

/** Same output as lib/format.ts fmtZar (kept in step by talent-derive.test.mjs): "R 135 382". */
function zar(n: number): string {
  const r = Math.round(Math.abs(n))
  const sign = n < 0 && r !== 0 ? "-" : ""
  return `${sign}R ${String(r).replace(/\B(?=(\d{3})+(?!\d))/g, " ")}`
}

// ── Display ───────────────────────────────────────────────────────────

/** Money that may be omitted by the backend's privacy redaction: missing/blank/non-finite => "—" (never "R 0"). */
export function fmtMoneyOrDash(v: unknown): string {
  if (v === null || v === undefined || v === "") return "—"
  const n = typeof v === "string" ? Number(v) : v
  if (typeof n !== "number" || !Number.isFinite(n)) return "—"
  return zar(n)
}

/** Money with cents for payslip lines; same dash rule. */
export function fmtMoneyCents(v: unknown): string {
  if (v === null || v === undefined || v === "") return "—"
  const n = typeof v === "string" ? Number(v) : v
  if (typeof n !== "number" || !Number.isFinite(n)) return "—"
  const abs = Math.abs(n).toFixed(2)
  const [i, f] = abs.split(".")
  return `${n < 0 ? "-" : ""}R ${i.replace(/\B(?=(\d{3})+(?!\d))/g, " ")},${f}`
}

// ── Performance summary (bulk endpoint) ────────────────────────────────

export interface PerformanceSummaryRow {
  employee_id: string
  overall_score: number | null
  status: string | null
  fiscal_year: string | null
  composite?: { total?: number | null } | null
}

/** Normalise the bulk endpoint payload (bare array or `{items}`) into rows; anything else => null. */
export function readPerformanceSummary(payload: unknown): PerformanceSummaryRow[] | null {
  const arr = Array.isArray(payload)
    ? payload
    : Array.isArray((payload as { items?: unknown })?.items)
      ? (payload as { items: unknown[] }).items
      : null
  if (!arr) return null
  const rows: PerformanceSummaryRow[] = []
  for (const r of arr) {
    const id = (r as { employee_id?: unknown })?.employee_id
    if (typeof id !== "string") continue
    const o = (r as { overall_score?: unknown }).overall_score
    rows.push({
      employee_id: id,
      overall_score: typeof o === "number" && Number.isFinite(o) ? o : null,
      status: typeof (r as { status?: unknown }).status === "string" ? (r as { status: string }).status : null,
      fiscal_year: typeof (r as { fiscal_year?: unknown }).fiscal_year === "string" ? (r as { fiscal_year: string }).fiscal_year : null,
      composite: ((r as { composite?: unknown }).composite as PerformanceSummaryRow["composite"]) ?? null,
    })
  }
  return rows
}
