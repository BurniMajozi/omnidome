/**
 * Pure helpers for the Compliance Center's honest per-section states.
 * No React / browser / alias imports (type-only imports are erased) so
 * node --test can load it directly.
 *
 * Owner rules: no fabricated figures, never claim a SARS filing the app did
 * not make, and always tell the user WHY a section is empty (service down vs
 * no data vs forbidden vs error).
 */
import type { Loadable } from "./service-state"

// ── Status -> section state ─────────────────────────────────────────────────

/** HTTP status (or null/undefined/0 for network failure / timeout) of a failed call. */
export function statusOf(err: unknown): number | null {
  const s = (err as { status?: unknown } | null | undefined)?.status
  return typeof s === "number" && s > 0 ? s : null
}

/** Server-provided message of a failed call (already extracted), if any. */
export function messageOf(err: unknown): string | undefined {
  const d = (err as { detail?: unknown } | null | undefined)?.detail
  return typeof d === "string" && d ? d : undefined
}

/** One failed call -> the non-ready Loadable it represents. */
export function loadableFromError(err: unknown): Loadable<null> {
  const status = statusOf(err)
  if (status === null || status === 502 || status === 503 || status === 504) return { state: "unreachable", status }
  if (status === 401 || status === 403) return { state: "denied", status }
  return { state: "error", status, message: messageOf(err) }
}

const RANK: Record<string, number> = { unreachable: 3, denied: 2, error: 1 }

/**
 * Several calls feed one tab. Collapse their errors (undefined/null = that call
 * succeeded) into one state: any failure makes the tab non-ready, worst first
 * (service down > forbidden > server error). No failures -> ready.
 */
export function combineErrors(errors: Array<unknown | null | undefined>): Loadable<null> {
  let worst: Loadable<null> | null = null
  for (const e of errors) {
    if (e === null || e === undefined) continue
    const l = loadableFromError(e)
    if (!worst || (RANK[l.state] ?? 0) > (RANK[worst.state] ?? 0)) worst = l
  }
  return worst ?? { state: "ready", data: null }
}

export interface SectionCopy {
  title: string
  detail: string
}

/** Copy for a non-ready, non-loading section state. null for ready/loading. */
export function describeSection(l: Loadable<unknown>, serviceLabel = "Compliance service"): SectionCopy | null {
  switch (l.state) {
    case "unreachable":
      return {
        title: "Service not running",
        detail: `${serviceLabel} is not reachable${l.status ? ` (HTTP ${l.status})` : ""}. Nothing is shown until it is connected; this is not an empty register.`,
      }
    case "denied":
      return {
        title: "Not permitted",
        detail: "Not permitted: requires compliance or admin role.",
      }
    case "error":
      return {
        title: "Error loading",
        detail: `${serviceLabel} returned an error${l.status ? ` (HTTP ${l.status})` : ""}${l.message ? `: ${l.message}` : ""}.`,
      }
    default:
      return null
  }
}

// ── Server error bodies ─────────────────────────────────────────────────────

/**
 * Pull a human message out of a FastAPI-style error body. Handles
 * {"detail": "msg"}, {"detail": [{"msg": "..."}]}, {"error": "..."} and plain
 * text. Returned verbatim (server validation / SSRF rejections), only trimmed
 * and length-capped.
 */
export function extractErrorDetail(body: string, max = 400): string {
  const text = (body ?? "").trim()
  if (!text) return ""
  try {
    const j = JSON.parse(text) as unknown
    if (j && typeof j === "object") {
      const o = j as { detail?: unknown; error?: unknown; message?: unknown }
      if (typeof o.detail === "string") return o.detail.slice(0, max)
      if (Array.isArray(o.detail)) {
        const parts = o.detail
          .map((d) => (d && typeof d === "object" && typeof (d as { msg?: unknown }).msg === "string" ? (d as { msg: string }).msg : ""))
          .filter(Boolean)
        if (parts.length) return parts.join("; ").slice(0, max)
      }
      if (typeof o.error === "string") return o.error.slice(0, max)
      if (typeof o.message === "string") return o.message.slice(0, max)
    }
  } catch {
    /* not JSON: fall through to plain text */
  }
  return text.slice(0, max)
}

// ── Scores ──────────────────────────────────────────────────────────────────

export interface ScoreView {
  assessed: boolean
  /** 0-100 rounded, only when assessed. */
  value: number | null
  label: string
}

/** null/undefined/NaN/non-number -> "Not assessed" (never 0 or 100). */
export function scoreView(score: unknown): ScoreView {
  if (typeof score === "number" && Number.isFinite(score)) {
    const v = Math.max(0, Math.min(100, Math.round(score)))
    return { assessed: true, value: v, label: `${v}%` }
  }
  return { assessed: false, value: null, label: "Not assessed" }
}

/** Mean of the assessed scores only; null when none were assessed. */
export function meanAssessed(scores: Array<unknown>): number | null {
  const nums = scores.filter((s): s is number => typeof s === "number" && Number.isFinite(s))
  if (!nums.length) return null
  return nums.reduce((a, b) => a + b, 0) / nums.length
}

// ── EMP201 manual filing ────────────────────────────────────────────────────

/** SARS Payment Reference Number as pasted from eFiling: 16-19 alphanumerics. */
export const PRN_RE = /^[A-Za-z0-9]{16,19}$/

export type PrnCheck = { ok: true; prn: string } | { ok: false; error: string }

export function validatePrn(input: string): PrnCheck {
  const prn = (input ?? "").replace(/\s+/g, "").toUpperCase()
  if (!prn) return { ok: false, error: "Enter the PRN / receipt reference from SARS eFiling." }
  if (!PRN_RE.test(prn)) return { ok: false, error: "PRN must be 16 to 19 letters or digits (no spaces or symbols)." }
  return { ok: true, prn }
}

export type DateCheck = { ok: true; date: string } | { ok: false; error: string }

/** Filed date: real YYYY-MM-DD calendar date, not in the future (+1 day tolerance for timezones). */
export function validateFiledDate(input: string, now: Date = new Date()): DateCheck {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec((input ?? "").trim())
  if (!m) return { ok: false, error: "Enter the date you filed (YYYY-MM-DD)." }
  const [y, mo, d] = [Number(m[1]), Number(m[2]), Number(m[3])]
  const dt = new Date(Date.UTC(y, mo - 1, d))
  if (dt.getUTCFullYear() !== y || dt.getUTCMonth() !== mo - 1 || dt.getUTCDate() !== d) {
    return { ok: false, error: "That is not a real calendar date." }
  }
  if (dt.getTime() > now.getTime() + 24 * 3600 * 1000) return { ok: false, error: "Filed date cannot be in the future." }
  return { ok: true, date: `${m[1]}-${m[2]}-${m[3]}` }
}

/** Tax period YYYY-MM. */
export function validatePeriod(input: string): boolean {
  return /^\d{4}-(0[1-9]|1[0-2])$/.test((input ?? "").trim())
}

/** Statuses that mean the filing really happened (only after the user recorded the receipt). */
export function isFiledStatus(status: string | null | undefined): boolean {
  const s = (status ?? "").toUpperCase()
  return s === "FILED" || s === "MARKED_FILED" || s === "PAID"
}

/** Numbers only when the API gave a real finite number; otherwise "Not available". */
export function zarOrNA(v: unknown): string {
  if (typeof v !== "number" || !Number.isFinite(v)) return "Not available"
  const neg = v < 0
  const [i, f] = Math.abs(v).toFixed(2).split(".")
  return `${neg ? "-" : ""}R ${i.replace(/\B(?=(\d{3})+(?!\d))/g, " ")},${f}`
}

export const SARS_EFILING_URL = "https://www.sarsefiling.co.za/"
