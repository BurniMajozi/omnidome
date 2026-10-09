import type { QueryColumn, QueryResult } from "@/lib/bi-studio-api"

/**
 * Client-side evaluation of {{alias.path|format}} tokens against query results, so the editor can show live values
 * for an unsaved draft. The server remains the authority (it re-resolves on save/export); this mirrors docs/bi-studio-api.md section 4.
 */

export type DataMap = Record<string, QueryResult | undefined>

export interface TokenOutcome {
  ok: boolean
  display: string
  raw: string
  /** Why it could not be resolved. */
  reason?: string
  /** Numeric value when available (for deltas / direction). */
  value?: number | null
}
export type Seg = { kind: "text"; text: string } | ({ kind: "token" } & TokenOutcome)

export const DASH = "—"
const TOKEN_RE = /\{\{\s*([^{}]*?)\s*\}\}/g

export const TOKEN_FORMATS = [
  "currency",
  "currency_compact",
  "number",
  "number_compact",
  "percent",
  "percent0",
  "duration",
  "text",
  "signed_currency",
  "signed_number",
  "signed_percent",
] as const

function group(n: number, decimals: number): string {
  const s = Math.abs(n).toFixed(decimals)
  const [i, f] = s.split(".")
  const g = i.replace(/\B(?=(\d{3})+(?!\d))/g, " ")
  return f ? `${g}.${f}` : g
}
function compact(n: number): string {
  const a = Math.abs(n)
  if (a >= 1e9) return `${(a / 1e9).toFixed(1).replace(/\.0$/, "")}bn`
  if (a >= 1e6) return `${(a / 1e6).toFixed(1).replace(/\.0$/, "")}m`
  if (a >= 1e3) return `${(a / 1e3).toFixed(1).replace(/\.0$/, "")}k`
  return a.toFixed(a % 1 === 0 ? 0 : 1)
}

export function formatNumber(n: number, fmt: string): string {
  const neg = n < 0
  const sign = neg ? "-" : ""
  const plus = neg ? "-" : "+"
  switch (fmt) {
    case "currency":
      return `${sign}R${group(n, 0)}`
    case "currency_compact":
      return `${sign}R${compact(n)}`
    case "number":
      return `${sign}${group(n, Number.isInteger(n) ? 0 : 1)}`
    case "number_compact":
      return `${sign}${compact(n)}`
    case "percent":
      return `${sign}${(Math.abs(n) * 100).toFixed(1)}%`
    case "percent0":
      return `${sign}${(Math.abs(n) * 100).toFixed(0)}%`
    case "duration": {
      const h = Math.abs(n)
      if (h < 1) return `${sign}${Math.round(h * 60)} min`
      if (h < 48) return `${sign}${h.toFixed(1).replace(/\.0$/, "")} h`
      return `${sign}${(h / 24).toFixed(1).replace(/\.0$/, "")} days`
    }
    case "signed_currency":
      return `${plus}R${group(n, 0)}`
    case "signed_number":
      return `${plus}${group(n, Number.isInteger(n) ? 0 : 1)}`
    case "signed_percent":
      return `${plus}${(Math.abs(n) * 100).toFixed(1)}%`
    default:
      return String(n)
  }
}

/** Map a measure column format to the token format that displays it. */
export function defaultTokenFormat(col: QueryColumn | undefined, stat?: string): string {
  if (stat === "delta_pct") return "signed_percent"
  switch (col?.format) {
    case "currency_zar":
      return stat === "delta" ? "signed_currency" : "currency"
    case "percent":
      return stat === "delta" ? "signed_percent" : "percent"
    case "duration":
      return "duration"
    default:
      return stat === "delta" ? "signed_number" : "number"
  }
}

function rowLabel(res: QueryResult, ri: number): string {
  const idx = res.columns.findIndex((c) => c.kind !== "measure")
  if (idx < 0) return `Row ${ri + 1}`
  const v = res.rows[ri]?.[idx]
  return v === null || v === undefined ? DASH : String(v)
}

function fail(raw: string, reason: string): TokenOutcome {
  return { ok: false, display: DASH, raw, reason }
}

/** Evaluate the inside of a token: `alias.path | format`. */
export function resolveToken(body: string, data: DataMap): TokenOutcome {
  const raw = body
  const t = body.trim()
  if (t === "?") return { ok: false, display: "[add figure]", raw, reason: "Placeholder: add a figure" }
  const [pathPart, fmtPart] = t.split("|").map((s) => s.trim())
  const seg = (pathPart ?? "").split(".").filter(Boolean)
  if (seg.length === 0) return fail(raw, "Empty token")
  const alias = seg[0]
  const res = data[alias]
  if (!res) return fail(raw, `No data for “${alias}” (not loaded, failed, or unknown alias)`)
  const measures = res.columns.filter((c) => c.kind === "measure")
  let rest = seg.slice(1)
  let mi = measures.findIndex((m) => m.id === rest[0])
  if (mi >= 0) rest = rest.slice(1)
  else mi = 0
  if (!measures[mi] && rest[0] !== "rows") return fail(raw, "Query has no measures")
  const col = measures[mi]
  const colIdx = col ? res.columns.findIndex((c) => c.id === col.id) : -1
  const rows = res.rows
  const val = (ri: number): number | null => {
    const v = rows[ri]?.[colIdx]
    return typeof v === "number" ? v : v === null || v === undefined ? null : Number(v)
  }
  const stat = rest.join(".")
  const out = (v: number | null | undefined, statName?: string): TokenOutcome => {
    if (v === null || v === undefined || Number.isNaN(v)) return fail(raw, "No value for this row")
    const fmt = fmtPart && fmtPart !== "" ? fmtPart : defaultTokenFormat(col, statName)
    return { ok: true, display: fmt === "text" ? String(v) : formatNumber(v, fmt), raw, value: v }
  }
  if (stat === "rows") return { ok: true, display: String(rows.length), raw, value: rows.length }
  if (rows.length === 0 && stat !== "total" && stat !== "") return fail(raw, "No data yet")
  if (stat === "" || stat === "total") {
    const tv = res.totals?.[col.id]
    return out(typeof tv === "number" ? tv : rows.length ? rows.reduce((a, _r, i) => a + (val(i) ?? 0), 0) : null)
  }
  const labelOf = (i: number): TokenOutcome => (i >= 0 && i < rows.length ? { ok: true, display: rowLabel(res, i), raw } : fail(raw, "No such row"))
  switch (stat) {
    case "first":
      return out(val(0))
    case "last":
      return out(val(rows.length - 1))
    case "prev":
      return rows.length < 2 ? fail(raw, "Needs at least two rows") : out(val(rows.length - 2))
    case "first.label":
      return labelOf(0)
    case "last.label":
      return labelOf(rows.length - 1)
    case "prev.label":
      return labelOf(rows.length - 2)
    case "delta":
    case "delta_pct": {
      if (rows.length < 2) return fail(raw, "Needs at least two rows")
      const l = val(rows.length - 1)
      const p = val(rows.length - 2)
      if (l === null || p === null) return fail(raw, "Missing value")
      if (stat === "delta") return out(l - p, "delta")
      if (p === 0) return fail(raw, "Previous value is 0")
      return out((l - p) / Math.abs(p), "delta_pct")
    }
    case "max":
    case "min":
    case "avg": {
      const vs = rows.map((_r, i) => val(i)).filter((v): v is number => v !== null)
      if (!vs.length) return fail(raw, "No values")
      const r = stat === "max" ? Math.max(...vs) : stat === "min" ? Math.min(...vs) : vs.reduce((a, b) => a + b, 0) / vs.length
      return out(r)
    }
  }
  const m = /^(top|bottom|row)(\d+)\.(value|label|share)$/.exec(stat)
  if (m) {
    const n = Number(m[2])
    if (n < 1 || n > rows.length) return fail(raw, "No such row")
    let ri = n - 1
    if (m[1] !== "row") {
      const order = rows.map((_r, i) => i).sort((a, b) => (val(b) ?? -Infinity) - (val(a) ?? -Infinity))
      ri = m[1] === "top" ? order[n - 1] : order[order.length - n]
    }
    if (m[3] === "label") return labelOf(ri)
    if (m[3] === "share") {
      if (!col.additive) return fail(raw, "Share only applies to additive measures")
      const tot = res.totals?.[col.id]
      const v = val(ri)
      if (!tot || v === null) return fail(raw, "No total")
      return { ok: true, display: formatNumber(v / tot, fmtPart || "percent"), raw, value: v / tot }
    }
    return out(val(ri))
  }
  return fail(raw, `Unknown statistic “${stat}”`)
}

export function splitTokens(text: string, data: DataMap): Seg[] {
  const segs: Seg[] = []
  let last = 0
  for (const m of text.matchAll(TOKEN_RE)) {
    const i = m.index ?? 0
    if (i > last) segs.push({ kind: "text", text: text.slice(last, i) })
    segs.push({ kind: "token", ...resolveToken(m[1], data) })
    last = i + m[0].length
  }
  if (last < text.length) segs.push({ kind: "text", text: text.slice(last) })
  return segs
}

export function resolveText(text: string, data: DataMap): string {
  return splitTokens(text, data)
    .map((s) => (s.kind === "text" ? s.text : s.display))
    .join("")
}

/** Resolve a kpi value_ref (a token body without braces). */
export const resolveRef = (ref: string | null | undefined, fmt: string | null | undefined, data: DataMap): TokenOutcome =>
  resolveToken(fmt ? `${ref}|${fmt}` : (ref ?? ""), data)

export function tokenBody(alias: string, measure: string | null, stat: string, format?: string): string {
  const path = [alias, measure, stat === "total" && !measure ? "" : stat].filter(Boolean).join(".")
  return `{{${path}${format ? `|${format}` : ""}}}`
}

/** Plain value formatter for chart axes / tables by measure format. */
export function formatByMeasure(v: unknown, format?: string | null): string {
  if (v === null || v === undefined || v === "") return DASH
  if (typeof v !== "number") return String(v)
  switch (format) {
    case "currency_zar":
    case "currency":
      return formatNumber(v, "currency")
    case "percent":
      return formatNumber(v, "percent")
    case "duration":
      return formatNumber(v, "duration")
    default:
      return formatNumber(v, "number")
  }
}
export function compactByMeasure(v: number, format?: string | null): string {
  if (format === "currency_zar" || format === "currency") return formatNumber(v, "currency_compact")
  if (format === "percent") return formatNumber(v, "percent0")
  return formatNumber(v, "number_compact")
}
