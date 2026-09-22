import { NextResponse } from "next/server"
import { createClient } from "@supabase/supabase-js"

// This backs useModuleData() for modules not yet migrated to a real backend
// (see lib/module-data.ts). It's decorative/supplementary data, not the
// module's core functionality -- so a Supabase outage here must NEVER 500 the
// page. Every failure path below returns 200 with data:null; the client hook
// already treats that as "use my fallback defaults" (see module-data.ts).
// Found 2026-09-22: this used to 500 whenever the Supabase project was
// paused/unreachable, which is a real, expected state (e.g. free-tier project
// swaps), not an application error.
export async function GET(_request: Request, { params }: { params: Promise<{ module: string }> }) {
  const { module: moduleId } = await params
  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL
  const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY

  if (!supabaseUrl || !supabaseAnonKey) {
    return NextResponse.json({ data: null, updated_at: null, unavailable: "config" })
  }

  try {
    const client = createClient(supabaseUrl, supabaseAnonKey)
    const { data, error: dbError } = await client
      .from("module_data")
      .select("data, updated_at")
      .eq("module_id", moduleId)
      .maybeSingle()

    if (dbError) {
      console.warn(`module_data fetch failed for "${moduleId}": ${dbError.message}`)
      return NextResponse.json({ data: null, updated_at: null, unavailable: "supabase_error" })
    }

    return NextResponse.json({ data: data?.data ?? null, updated_at: data?.updated_at ?? null })
  } catch (err) {
    // Network-level failure (paused project, DNS, timeout) throws rather than
    // returning `error` -- catch it too so it degrades the same way.
    console.warn(`module_data unreachable for "${moduleId}":`, err instanceof Error ? err.message : err)
    return NextResponse.json({ data: null, updated_at: null, unavailable: "unreachable" })
  }
}
