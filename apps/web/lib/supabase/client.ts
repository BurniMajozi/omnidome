import { createClient } from "@supabase/supabase-js"
import { AUTH_DISABLED } from "@/lib/flags"

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY

// Fail fast on misconfiguration. Previously these fell back to
// "https://placeholder-url.supabase.co" / "placeholder-anon-key", which let the
// app boot and then fail auth silently at runtime with confusing 401s. Missing
// Supabase env vars are always a deployment error, so surface them loudly at
// module load instead. Both are NEXT_PUBLIC_* (inlined at build time), so this
// throws during `next build` if they're absent — which is the point.
if (!supabaseUrl || !supabaseAnonKey) {
  throw new Error(
    "Missing Supabase configuration: set NEXT_PUBLIC_SUPABASE_URL and " +
      "NEXT_PUBLIC_SUPABASE_ANON_KEY (see apps/web/.env). Auth cannot work without them.",
  )
}

// In local auth-disabled mode the browser may still hold a session saved while
// the Supabase project was reachable. Reading it makes supabase-js retry the
// refresh-token call against the unreachable auth host in a loop, and every
// getSession() queues behind that loop. Don't persist or auto-refresh
// sessions at all in that mode; the proxy routes act as the dev tenant anyway.
export const supabase = createClient(
  supabaseUrl,
  supabaseAnonKey,
  AUTH_DISABLED
    ? { auth: { persistSession: false, autoRefreshToken: false, detectSessionInUrl: false } }
    : undefined,
)

type SessionResult = Awaited<ReturnType<typeof supabase.auth.getSession>>

const NO_SESSION = { data: { session: null }, error: null } as SessionResult
const SESSION_TIMEOUT_MS = 5000
// After a timeout, assume the auth host is unreachable for a while instead of
// making every request wait SESSION_TIMEOUT_MS again.
const UNREACHABLE_COOLDOWN_MS = 30_000

let inflight: Promise<SessionResult> | null = null
let unreachableUntil = 0

// supabase-js serializes getSession() calls behind an internal lock, and
// getSession() itself falls back to a network refresh call when the cached
// token is stale. If that network call hangs (unreachable/slow auth
// endpoint), EVERY api-client fetchX() helper across the app awaits this
// before it ever reaches its own AbortSignal.timeout()'d fetch -- so the
// whole page's data-loading spinner gets stuck forever with no timeout ever
// firing. Race it against a short local timeout and degrade to "no session"
// (same shape getSession() itself returns) instead of hanging. Concurrent
// callers share one lookup.
export function getSessionSafe(): Promise<SessionResult> {
  if (AUTH_DISABLED || Date.now() < unreachableUntil) return Promise.resolve(NO_SESSION)
  if (inflight) return inflight

  inflight = (async () => {
    let timer: ReturnType<typeof setTimeout> | undefined
    try {
      return await Promise.race([
        supabase.auth.getSession(),
        new Promise<SessionResult>((resolve) => {
          timer = setTimeout(() => {
            unreachableUntil = Date.now() + UNREACHABLE_COOLDOWN_MS
            resolve(NO_SESSION)
          }, SESSION_TIMEOUT_MS)
        }),
      ])
    } catch {
      return NO_SESSION
    } finally {
      clearTimeout(timer)
      inflight = null
    }
  })()
  return inflight
}
