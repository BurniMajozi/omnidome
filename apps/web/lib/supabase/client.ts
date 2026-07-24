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
