import { createClient } from "@supabase/supabase-js"

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

export const supabase = createClient(supabaseUrl, supabaseAnonKey)

// supabase-js serializes getSession() calls behind an internal lock, and
// getSession() itself falls back to a network refresh call when the cached
// token is stale. If that network call hangs (unreachable/slow auth
// endpoint), EVERY api-client fetchX() helper across the app awaits this
// before it ever reaches its own AbortSignal.timeout()'d fetch -- so the
// whole page's data-loading spinner gets stuck forever with no timeout ever
// firing. Race it against a short local timeout and degrade to "no session"
// (same shape getSession() itself returns) instead of hanging.
export async function getSessionSafe(): Promise<
  Awaited<ReturnType<typeof supabase.auth.getSession>>
> {
  const NO_SESSION = { data: { session: null }, error: null } as Awaited<
    ReturnType<typeof supabase.auth.getSession>
  >
  try {
    return await Promise.race([
      supabase.auth.getSession(),
      new Promise<typeof NO_SESSION>((resolve) =>
        setTimeout(() => resolve(NO_SESSION), 5000),
      ),
    ])
  } catch {
    return NO_SESSION
  }
}
