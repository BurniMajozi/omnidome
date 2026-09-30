/**
 * Pure helpers for the Marketing module (no React / browser imports, so they
 * can be unit tested with node: `node --test lib/marketing-state.test.mjs`).
 *
 * Owner rule: no fabricated figures or success messages. These helpers turn a
 * real HTTP outcome into honest copy, and decide how often a real batch status
 * may be polled.
 */

/** Minimum gap between polls of a background job (email batch etc.). */
export const MIN_POLL_MS = 5_000
/** Minimum gap for any passive refresh of a list (never tighter than this). */
export const MIN_REFRESH_MS = 30_000

/** Delay before the next poll: backs off 5s, 5s, 7.5s, 11s ... capped at 30s; never below 5s. */
export function nextPollDelay(attempt: number): number {
  const n = Math.max(0, Math.floor(attempt))
  const d = MIN_POLL_MS * Math.pow(1.5, Math.max(0, n - 1))
  return Math.min(MIN_REFRESH_MS, Math.max(MIN_POLL_MS, Math.round(d)))
}

/** Clamp a caller-requested refresh interval to the minimum. 0/undefined/negative = no polling. */
export function clampRefreshMs(ms: number | undefined | null): number {
  if (!ms || ms <= 0) return 0
  return Math.max(MIN_REFRESH_MS, ms)
}

export interface MutationOutcome {
  ok: boolean
  status: number
  error?: string | null
}

/**
 * Human message for a failed write. The server's own detail is always shown
 * verbatim where it gave one; we only add the reason class as a prefix.
 */
export function describeMutationError(status: number, detail?: string | null): string {
  const d = (detail ?? "").trim()
  switch (status) {
    case 0:
      return d ? `Service not running (${d})` : "Service not running. Nothing was saved."
    case 401:
      return d || "Your session has expired. Sign in again."
    case 403:
      return d ? `Not permitted: ${d}` : "Not permitted: your role cannot make this change."
    case 404:
      return d || "Not found. It may have been removed."
    case 409:
      return d ? `Not allowed in the current state: ${d}` : "Not allowed in the current state."
    case 422:
      return d ? `Invalid input: ${d}` : "Invalid input."
    case 501:
      return d ? `Not available yet: ${d}` : "Not available yet: the backend has not implemented this."
    case 502:
    case 503:
    case 504:
      return d ? `Provider or service unavailable: ${d}` : "Service unavailable. Nothing was sent."
    default:
      return d || `Request failed (${status})`
  }
}

export interface EmailBatchInfo {
  status: string
  queued: number | null
  sent: number | null
  failed: number | null
  suppressed: number | null
  done: boolean
}

const TERMINAL = new Set(["sent", "failed", "partial", "completed", "complete", "done", "cancelled", "canceled"])

function num(v: unknown): number | null {
  if (typeof v === "number" && Number.isFinite(v)) return v
  if (typeof v === "string" && v.trim() !== "" && Number.isFinite(Number(v))) return Number(v)
  return null
}

/**
 * Normalize the marketing service's GET /email/batches/{id} row. Counts the
 * API did not return stay `null` (shown as "not reported", never as 0).
 */
export function parseEmailBatch(row: unknown): EmailBatchInfo {
  const r = (row && typeof row === "object" ? row : {}) as Record<string, unknown>
  const status = typeof r.status === "string" ? r.status.toLowerCase() : "unknown"
  const failed = num(r.total_failed) ?? num(r.failed) ?? num(r.total_bounced)
  return {
    status,
    queued: num(r.total_queued) ?? num(r.queued),
    sent: num(r.total_sent) ?? num(r.sent),
    failed,
    suppressed: num(r.total_suppressed) ?? num(r.suppressed),
    done: TERMINAL.has(status),
  }
}

/** One line of real numbers for a batch; omits counts the API did not report. */
export function summarizeEmailBatch(b: EmailBatchInfo): string {
  const parts: string[] = []
  if (b.sent !== null) parts.push(`${b.sent} sent`)
  if (b.failed !== null) parts.push(`${b.failed} failed`)
  if (b.suppressed !== null) parts.push(`${b.suppressed} suppressed`)
  if (b.queued !== null) parts.push(`${b.queued} queued`)
  return parts.length ? parts.join(", ") : `status: ${b.status}`
}

// ── Tiny GET cache with in-flight de-duplication ─────────────────────────

export interface GetCache<T> {
  get(key: string, loader: () => Promise<T>, opts?: { force?: boolean }): Promise<T>
  clear(): void
  size(): number
}

/**
 * De-duplicates concurrent identical reads and serves a short-lived result to
 * later callers. Only call it with successful-or-not results you are happy to
 * reuse for `ttlMs`; failures are cached for `failTtlMs` (short) so a dead
 * backend is not hammered by every component mounting at once.
 */
export function createGetCache<T>(
  ttlMs: number,
  failTtlMs: number,
  isFailure: (v: T) => boolean,
  now: () => number = () => Date.now(),
): GetCache<T> {
  const store = new Map<string, { at: number; ttl: number; value?: T; promise?: Promise<T> }>()
  return {
    get(key, loader, opts) {
      const hit = store.get(key)
      if (hit && !opts?.force) {
        if (hit.promise) return hit.promise
        if (now() - hit.at < hit.ttl) return Promise.resolve(hit.value as T)
      }
      const promise = loader().then(
        (value) => {
          const cur = store.get(key)
          if (cur && cur.promise === promise) {
            store.set(key, { at: now(), ttl: isFailure(value) ? failTtlMs : ttlMs, value })
          }
          return value
        },
        (err) => {
          const cur = store.get(key)
          if (cur && cur.promise === promise) store.delete(key)
          throw err
        },
      )
      store.set(key, { at: now(), ttl: ttlMs, promise })
      return promise
    },
    clear() {
      store.clear()
    },
    size() {
      return store.size
    },
  }
}
