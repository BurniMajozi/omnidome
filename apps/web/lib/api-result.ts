/**
 * Status-preserving result for mutations against /svc/<service>/... so the UI
 * can show the server's 403/409/422 message inline. No imports (node --test).
 */

export interface ActionResult<T = unknown> {
  ok: boolean
  /** HTTP status, or 0 for a network failure / timeout. */
  status: number
  data: T | null
  /** Human message for the UI when !ok. */
  message: string | null
}

/** Pull a readable message out of a FastAPI/Next error body. */
export function readErrorMessage(body: unknown, status: number, adminLabel = "finance admin"): string {
  const b = body as { detail?: unknown; message?: unknown; error?: unknown } | null
  let msg: string | null = null
  const d = b?.detail
  if (typeof d === "string") msg = d
  else if (Array.isArray(d)) {
    const parts = d
      .map((x) => {
        const e = x as { msg?: unknown; loc?: unknown }
        const loc = Array.isArray(e.loc) ? e.loc.filter((p) => p !== "body").join(".") : ""
        return typeof e.msg === "string" ? (loc ? `${loc}: ${e.msg}` : e.msg) : null
      })
      .filter(Boolean)
    if (parts.length) msg = parts.join("; ")
  } else if (typeof b?.message === "string") msg = b.message
  else if (typeof b?.error === "string") msg = b.error

  if (status === 403) return msg ? `Not permitted: ${msg}` : `Not permitted: requires ${adminLabel}`
  if (status === 401) return "Your session has expired. Sign in again."
  if (status === 0) return "Could not reach the service. Try again."
  if (status === 502 || status === 503 || status === 504) return msg ? `Service unavailable: ${msg}` : "Service not running"
  return msg ?? `Request failed (HTTP ${status})`
}

export async function sendJson<T = unknown>(
  url: string,
  method: "POST" | "PUT" | "PATCH" | "DELETE",
  body?: unknown,
  opts: { headers?: Record<string, string>; timeoutMs?: number; adminLabel?: string } = {},
): Promise<ActionResult<T>> {
  let res: Response
  try {
    res = await fetch(url, {
      method,
      cache: "no-store",
      headers: { ...(body === undefined ? {} : { "Content-Type": "application/json" }), ...(opts.headers ?? {}) },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: AbortSignal.timeout(opts.timeoutMs ?? 15_000),
    })
  } catch {
    return { ok: false, status: 0, data: null, message: readErrorMessage(null, 0) }
  }
  let payload: unknown = null
  if (res.status !== 204) {
    try {
      payload = await res.json()
    } catch {
      payload = null
    }
  }
  if (!res.ok) return { ok: false, status: res.status, data: null, message: readErrorMessage(payload, res.status, opts.adminLabel) }
  return { ok: true, status: res.status, data: payload as T, message: null }
}

/** Client-generated idempotency key (double-click safe). */
export function newIdempotencyKey(): string {
  const c = (globalThis as { crypto?: { randomUUID?: () => string } }).crypto
  if (c?.randomUUID) return c.randomUUID()
  return `k-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`
}
