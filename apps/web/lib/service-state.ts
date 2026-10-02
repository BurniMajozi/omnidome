/**
 * Pure state-mapping for "is this number real?" UI.
 *
 * Owner rule: no fabricated figures. A value is either read from the real
 * backend or the tile shows an honest state. This maps an HTTP outcome to that
 * state. No React / browser imports so it can be unit-tested with node.
 */

export type ServiceState = "ok" | "unreachable" | "denied" | "error"

/** status: HTTP status, or null/0 for network failure / timeout. */
export function classifyHttpStatus(status: number | null | undefined): ServiceState {
  if (status === null || status === undefined || status === 0) return "unreachable"
  if (status >= 200 && status < 300) return "ok"
  if (status === 502 || status === 503 || status === 504) return "unreachable"
  if (status === 401 || status === 403) return "denied"
  return "error"
}

export type Loadable<T> =
  | { state: "loading" }
  | { state: "ready"; data: T }
  | { state: "unreachable"; status: number | null }
  | { state: "denied"; status: number }
  | { state: "error"; status: number | null; message?: string }

export function loadableFromStatus<T>(
  status: number | null,
  data: T | undefined,
  message?: string,
): Loadable<T> {
  const s = classifyHttpStatus(status)
  if (s === "ok" && data !== undefined) return { state: "ready", data }
  if (s === "unreachable") return { state: "unreachable", status }
  if (s === "denied") return { state: "denied", status: status as number }
  return { state: "error", status, message }
}

export interface StateCopy {
  title: string
  detail: string
}

/** Human copy for a non-ready state. Returns null for loading/ready. */
export function describeLoadable(l: Loadable<unknown>, serviceLabel = "Service"): StateCopy | null {
  switch (l.state) {
    case "unreachable":
      return {
        title: "Service not running",
        detail: `${serviceLabel} is not reachable${l.status ? ` (HTTP ${l.status})` : ""}. No figures are shown until it is connected.`,
      }
    case "denied":
      if (l.status === 401) return {
        title: "Session not verified",
        detail: "Retry to verify your session. If this continues, sign in again.",
      }
      return {
        title: "Not permitted",
        detail: `You do not have access to ${serviceLabel} data (HTTP ${l.status}).`,
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

/** Short label for a KPI tile value slot. */
export function tileLabel(l: Loadable<unknown>): string | null {
  switch (l.state) {
    case "loading":
      return "…"
    case "unreachable":
      return "Service not running"
    case "denied":
      return l.status === 401 ? "Session not verified" : "Not permitted"
    case "error":
      return "Error loading"
    default:
      return null
  }
}

/** Sum decimal-ish values (API returns Decimal as string or number). Non-finite parts are ignored. */
export function sumMoney(values: Array<number | string | null | undefined>): number {
  let t = 0
  for (const v of values) {
    const n = typeof v === "string" ? Number(v) : v
    if (typeof n === "number" && Number.isFinite(n)) t += n
  }
  return t
}

/** /api/chat/channels (or any `{ data: T[] }` proxy) outcome -> Loadable. 200 + [] is ready-and-empty. */
export function listLoadable<T>(status: number | null, payload: unknown): Loadable<T[]> {
  const data = (payload as { data?: unknown } | null)?.data
  return loadableFromStatus<T[]>(status, Array.isArray(data) ? (data as T[]) : undefined)
}
