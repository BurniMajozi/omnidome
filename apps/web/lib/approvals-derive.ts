/**
 * Pure helpers for the Executive Approval Queue. No React / browser imports so
 * they can be unit-tested with node.
 *
 * Owner rule: never claim an action happened before the server says so, and
 * never hide a failure. Copy here is what the UI shows on success/failure.
 */

export interface ApprovalFailure {
  /** HTTP status, or null when the request never got an answer. */
  status: number | null
  /** Server-provided detail text (may be empty). */
  message: string
}

export type ApprovalAction = "approve" | "dismiss"

/** One inline-alert sentence for a failed approve/dismiss; 403 / 409 / 5xx / offline are distinct. */
export function describeApprovalFailure(action: ApprovalAction, f: ApprovalFailure): string {
  const verb = action === "approve" ? "approve" : "dismiss"
  const detail = f.message.trim()
  const s = f.status
  if (s === null || s === 0) return `Could not reach the orchestrator, so nothing was changed. Try again.`
  if (s === 403 || s === 401) {
    return `Not permitted (HTTP ${s}): ${detail || `you do not have permission to ${verb} this proposal`}.`
  }
  if (s === 409) {
    return `Already decided or expired (HTTP 409): ${detail || "this proposal is no longer pending"}. The queue was refreshed.`
  }
  if (s === 404) return `Proposal not found (HTTP 404)${detail ? `: ${detail}` : ""}. The queue was refreshed.`
  if (s >= 500) return `Orchestrator error (HTTP ${s})${detail ? `: ${detail}` : ""}. Nothing was changed.`
  return `Could not ${verb} (HTTP ${s})${detail ? `: ${detail}` : ""}.`
}

/** The queue should be re-read from the server after these outcomes (the item is gone or stale). */
export function shouldRefreshAfter(f: ApprovalFailure): boolean {
  return f.status === 404 || f.status === 409
}

/** GET /approvals must answer `{ items: [...] }`; anything else is an error state, never 'Queue Clear'. */
export function readApprovalItems<T>(res: unknown): T[] | null {
  const items = (res as { items?: unknown } | null)?.items
  return Array.isArray(items) ? (items as T[]) : null
}

export interface BatchOutcome {
  id: string
  title: string
  ok: boolean
  failure?: ApprovalFailure
}

export interface BatchSummary {
  approved: number
  failed: number
  /** ids that failed (they stay in the queue). */
  failedIds: string[]
  /** e.g. "3 approved, 1 failed: Not permitted (HTTP 403): ..." */
  text: string
  allOk: boolean
}

/** Per-item report for a batch approve. Failed items are listed so they can stay in the queue. */
export function summarizeBatch(outcomes: BatchOutcome[]): BatchSummary {
  const okCount = outcomes.filter((o) => o.ok).length
  const bad = outcomes.filter((o) => !o.ok)
  if (bad.length === 0) {
    return { approved: okCount, failed: 0, failedIds: [], text: `${okCount} approved`, allOk: true }
  }
  const reasons = bad.map((o) => describeApprovalFailure("approve", o.failure ?? { status: null, message: "" }))
  const distinct = [...new Set(reasons)]
  const reason = distinct.length === 1 ? distinct[0] : `${distinct[0]} (+${distinct.length - 1} other reason${distinct.length === 2 ? "" : "s"})`
  return {
    approved: okCount,
    failed: bad.length,
    failedIds: bad.map((o) => o.id),
    text: `${okCount} approved, ${bad.length} failed: ${reason}`,
    allOk: false,
  }
}
