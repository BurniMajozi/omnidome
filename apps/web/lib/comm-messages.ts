// Pure helpers for chat history, send reconciliation and error text. Erasable TS only (runs under node --test).

export const MESSAGE_MAX_CHARS = 8000

export interface MsgLike {
  id: string
  client_msg_id?: string | null
  user_id?: string | null
  content?: string | null
  created_at?: string | null
  /** local-only: optimistic bubble not yet confirmed by the server */
  pending?: boolean
  /** local-only: send failed; can be retried with the same client_msg_id */
  failed?: boolean
}

export function newClientMsgId(): string {
  const c = (globalThis as { crypto?: { randomUUID?: () => string } }).crypto
  if (c?.randomUUID) return c.randomUUID()
  return `c-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`
}

function sameMessage(a: MsgLike, b: MsgLike): boolean {
  if (a.id && b.id && a.id === b.id) return true
  return !!a.client_msg_id && !!b.client_msg_id && a.client_msg_id === b.client_msg_id &&
    (!a.user_id || !b.user_id || a.user_id === b.user_id)
}

/**
 * Live reconcile: a POST response or a WebSocket echo (`incoming`, a real server row) is merged into
 * `list`. Same id or client_msg_id -> replaced in place (local-only fields kept), otherwise appended.
 * Content is never an identity: two identical sends can be separate messages.
 */
export function upsertMessage<T extends MsgLike>(list: T[], incoming: T): T[] {
  const idx = list.findIndex((m) => sameMessage(m, incoming))
  if (idx < 0) return [...list, incoming]
  const merged = { ...list[idx], ...incoming, client_msg_id: incoming.client_msg_id ?? list[idx].client_msg_id, pending: false, failed: false }
  return list.flatMap((m, i) => i === idx ? [merged] : sameMessage(m, incoming) ? [] : [m])
}

/** A send acknowledgement identifies an unkeyed WS echo without matching message text. */
export function reconcileSend<T extends MsgLike>(list: T[], created: T, clientMsgId: string, buffered: T[]): T[] {
  const confirmed = { ...created, client_msg_id: clientMsgId }
  return buffered.filter((row) => row.id !== created.id)
    .reduce((out, row) => upsertMessage(out, row), upsertMessage(list, confirmed))
}

/** Older history page (ascending) goes in front; anything already present (or repeated in the page) is dropped. */
export function prependOlder<T extends MsgLike>(list: T[], older: T[]): T[] {
  const fresh = older.filter(
    (o, i) => !list.some((m) => sameMessage(m, o)) && older.findIndex((x) => sameMessage(x, o)) === i,
  )
  return fresh.length ? [...fresh, ...list] : list
}

/**
 * The newest page just loaded replaces what we had, but anything that arrived over the socket while the
 * request was in flight (same channel, newer than the page start) and unconfirmed local sends are kept,
 * deduped, at the end.
 */
export function mergeNewestPage<T extends MsgLike>(local: T[], fetched: T[]): T[] {
  let out = fetched.slice()
  const oldest = fetched.length ? String(fetched[0].created_at ?? "") : ""
  for (const m of local) {
    const match = out.findIndex((f) => sameMessage(f, m))
    if (match >= 0) {
      out[match] = { ...m, ...out[match], pending: false, failed: false }
      continue
    }
    const newer = !!m.created_at && (!oldest || String(m.created_at) >= oldest)
    if (m.pending || m.failed || newer) out = upsertMessage(out, m)
  }
  return out.sort((a, b) => Date.parse(a.created_at ?? "") - Date.parse(b.created_at ?? "") || a.id.localeCompare(b.id))
}

export interface HistoryPage {
  items: unknown[]
  next_before: string | null
  has_more: boolean
}

/** Normalise the proxy's `{ data, next_before, has_more }` (tolerates the older bare `{ data }`). */
export function parseHistoryPage(payload: unknown): HistoryPage {
  const p = (payload ?? {}) as { data?: unknown; items?: unknown; next_before?: unknown; has_more?: unknown }
  const items = Array.isArray(p.data) ? p.data : Array.isArray(p.items) ? p.items : []
  const nb = typeof p.next_before === "string" && p.next_before ? p.next_before : null
  // Current service returns ascending pages. Sorting also accepts descending pages without
  // reversing the current contract, and preserves the backend's UUID timestamp tie-break.
  const ordered = items.slice().sort((a, b) => {
    const left = a as MsgLike, right = b as MsgLike
    return Date.parse(left.created_at ?? "") - Date.parse(right.created_at ?? "") || left.id.localeCompare(right.id)
  })
  return { items: ordered, next_before: nb, has_more: p.has_more === true && !!nb }
}

export type SendFailure = { retryable: boolean; text: string }

/** Map a failed POST to user text and whether a manual retry is useful. */
export function sendFailure(status: number | null, detail?: string | null): SendFailure {
  if (status === 429) return { retryable: true, text: "Slow down: too many messages. Retry after a short wait" }
  if (status === 422) return { retryable: false, text: detail ?? "Invalid message" }
  if (status === 404) return { retryable: false, text: "Channel not available" }
  if (status === 401) return { retryable: false, text: "Session expired: sign in again" }
  if (status === 403) return { retryable: false, text: detail ? `Not permitted: ${detail}` : "Not permitted" }
  if (status === null || status === 0 || status >= 500) return { retryable: true, text: "Not sent: Retry" }
  return { retryable: false, text: detail ? `Not sent: ${detail}` : `Not sent (HTTP ${status})` }
}

/** Server `detail` (FastAPI string or validation list) as short text, never an object dump. */
export function detailText(payload: unknown): string | null {
  const d = payload as { detail?: unknown; message?: unknown } | null
  const v = d?.detail ?? d?.message
  if (typeof v === "string" && v.trim()) return v.trim().slice(0, 300)
  if (Array.isArray(v) && v.length) {
    const first = v[0] as { msg?: unknown }
    if (typeof first?.msg === "string") return first.msg.slice(0, 300)
  }
  return null
}

// ── Approvals / escalations / channel management ────────────────────────────

export const APPROVAL_STATES = ["pending", "approved", "rejected", "cancelled"] as const
export const ESCALATION_STATES = ["open", "in_progress", "resolved", "closed"] as const

const MANAGER_ROLE_NAMES = [
  "platform_admin", "owner", "org_admin", "admin", "tenant_admin", "super_admin", "manager", "line_manager", "team_lead",
]
const ADMIN_ROLE_NAMES = ["platform_admin", "owner", "org_admin", "admin", "tenant_admin", "super_admin"]

/** Mirrors services/communication/access.py tiers (UI hint only; the API stays the real guard). */
export function isManagerRole(roles?: string[] | null): boolean {
  return !!roles?.some((r) => MANAGER_ROLE_NAMES.includes(r.toLowerCase()))
}
export function isAdminRole(roles?: string[] | null): boolean {
  return !!roles?.some((r) => ADMIN_ROLE_NAMES.includes(r.toLowerCase()))
}

/** Owner/admin may manage a channel: its creator (created_by) or an admin-tier role. */
export function canManageChannel(
  ch: { created_by?: string | null } | null | undefined,
  userId?: string | null,
  roles?: string[] | null,
): boolean {
  if (!ch) return false
  if (userId && ch.created_by && ch.created_by === userId) return true
  return isAdminRole(roles)
}

/** Approval decision outcome text: 403 self-decision / role, 409 already decided, else server text. */
export function decisionError(status: number | null, detail?: string | null): string {
  if (status === 409) return "Already decided"
  if (status === 403) {
    if (detail && /own/i.test(detail)) return "You can't decide your own request"
    return detail ? `Not permitted: ${detail}` : "Not permitted"
  }
  if (status === 404) return "Not found (it may have been removed)"
  if (status === 401) return "Session expired: sign in again"
  if (status === null || status === 0) return "Could not reach the communication service"
  return detail ? `Error: ${detail}` : `Error (HTTP ${status})`
}

/** Short inline text for a failed channel/member action (create/update/delete/leave/invite). */
export function actionError(status: number | null, detail?: string | null, what = "Action"): string {
  if (status === 404) return "Channel not available"
  if (status === 403) return detail ? `Not permitted: ${detail}` : "Not permitted: only the channel owner or an admin can do this"
  if (status === 401) return "Session expired: sign in again"
  if (status === null || status === 0) return `${what} failed: could not reach the communication service`
  return detail ? `${what} failed: ${detail}` : `${what} failed (HTTP ${status})`
}
