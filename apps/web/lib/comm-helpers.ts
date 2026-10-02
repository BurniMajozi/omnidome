// Pure helpers for the Communication module (author labels, polling/reconnect backoff).

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i

export function looksLikeUuid(v?: string | null): boolean {
  return !!v && UUID_RE.test(v)
}

/** Display name from a Supabase-like user: full_name / name, else email local-part, else null. */
export function displayNameFromUser(
  user?: { email?: string | null; user_metadata?: Record<string, unknown> | null } | null,
): string | null {
  if (!user) return null
  const md = user.user_metadata ?? {}
  for (const k of ["full_name", "name"]) {
    const v = md[k]
    if (typeof v === "string" && v.trim()) return v.trim()
  }
  const email = user.email?.trim()
  if (email) return email.split("@")[0] || email
  return null
}

/**
 * Label for a message author. Never returns a raw UUID and never invents a name:
 * own messages -> the current user's real name; known directory users -> their name;
 * anything else -> the neutral "Team member".
 */
export function resolveAuthorLabel(opts: {
  userId?: string | null
  authorName?: string | null
  currentUserId?: string | null
  currentUserName?: string | null
  directory?: Record<string, string>
}): string {
  const { userId, authorName, currentUserId, currentUserName, directory } = opts
  if (userId && currentUserId && userId === currentUserId && currentUserName) return currentUserName
  if (userId && directory?.[userId]) return directory[userId]
  const n = authorName?.trim()
  if (n && !looksLikeUuid(n) && n.toLowerCase() !== "unknown") return n
  return "Team member"
}

/** Next polling interval: reset to base on success, double up to max on failure. */
export function nextPollDelay(current: number, ok: boolean, base = 30_000, max = 300_000): number {
  if (ok) return base
  return Math.min(Math.max(current, base) * 2, max)
}

/** Reconnect delay: exponential 1s -> 30s cap with +/-20% jitter (rand in [0,1)). */
export function reconnectDelay(attempt: number, rand: number = Math.random(), base = 1_000, cap = 30_000): number {
  const raw = Math.min(base * 2 ** Math.max(0, attempt), cap)
  const jitter = 1 + (rand * 2 - 1) * 0.2
  return Math.min(Math.round(raw * jitter), cap)
}

// Closes after which reconnecting cannot succeed (or must not resend what caused the close):
// 1008/4401/4403 auth style, 4001 bad identity, 4003 channel/origin denied, 1009 frame too large.
// 4408 (idle) and 4429 (rate/connection cap) have their own policy in wsClosePolicy().
export const WS_AUTH_CLOSE_CODES = [1008, 1009, 4001, 4003, 4401, 4403]
export const WS_IDLE_CLOSE_CODE = 4408
export const WS_RATE_CLOSE_CODE = 4429
export const WS_RATE_BACKOFF_MS = 30_000
export const WS_MAX_FAILURES = 5

/** Stop reconnecting after an auth-style close or too many consecutive failures. */
export function shouldStopReconnect(code: number, consecutiveFailures: number): boolean {
  return WS_AUTH_CLOSE_CODES.includes(code) || consecutiveFailures > WS_MAX_FAILURES
}

export type WsCloseDecision = { action: "stop"; reason: string } | { action: "retry"; delayMs: number; immediate?: boolean }

/**
 * What to do when the socket closes.
 *  - 1009/4001/4003/4401/4403/1008: stop (never resend the oversized frame, never hammer a denied channel)
 *  - 4429: back off at least 30s (+ jitter)
 *  - 4408: server dropped an idle socket: reconnect once immediately, then normal back-off
 *  - anything else: exponential back-off, stop after WS_MAX_FAILURES consecutive failed attempts
 * attempt = consecutive failures so far; wasOpen = this socket had opened; immediateUsed = the one free
 * 4408 reconnect was already spent since the last successful open.
 */
export function wsClosePolicy(
  code: number,
  ctx: { attempt: number; wasOpen: boolean; immediateUsed: boolean; rand?: number },
): WsCloseDecision {
  const rand = ctx.rand ?? Math.random()
  if (WS_AUTH_CLOSE_CODES.includes(code)) return { action: "stop", reason: code === 1009 ? "frame too large" : "not allowed" }
  if (code === WS_RATE_CLOSE_CODE) return { action: "retry", delayMs: WS_RATE_BACKOFF_MS + Math.round(rand * 5_000) }
  if (code === WS_IDLE_CLOSE_CODE && !ctx.immediateUsed) return { action: "retry", delayMs: 0, immediate: true }
  const failures = ctx.wasOpen ? 0 : ctx.attempt + 1
  if (failures > WS_MAX_FAILURES) return { action: "stop", reason: "too many failed attempts" }
  return { action: "retry", delayMs: reconnectDelay(ctx.wasOpen ? 0 : ctx.attempt, rand) }
}

/** Target text for the corporate sales tile: only when a real target AND real actual exist. */
export function corpTargetText(
  snap: { budget: number | null; actual: number | null } | null | undefined,
  fmt: (v: number) => string,
): string | null {
  if (!snap || snap.budget === null || snap.budget <= 0 || snap.actual === null) return null
  return fmt(snap.budget)
}
