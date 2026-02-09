import { NextResponse } from "next/server"
import { createClient } from "@supabase/supabase-js"

export async function GET(_request: Request, { params }: { params: Promise<{ module: string }> }) {
  const { module: moduleId } = await params
  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL
  const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY

  if (!supabaseUrl || !supabaseAnonKey) {
    return NextResponse.json(
      { error: "Supabase env vars missing: NEXT_PUBLIC_SUPABASE_URL or NEXT_PUBLIC_SUPABASE_ANON_KEY" },
      { status: 500 },
    )
  }

  const client = createClient(supabaseUrl, supabaseAnonKey)
  const { data, error: dbError } = await client
    .from("module_data")
    .select("data, updated_at")
    .eq("module_id", moduleId)
    .maybeSingle()

  if (dbError) {
    return NextResponse.json({ error: dbError.message }, { status: 500 })
  }

  return NextResponse.json({ data: data?.data ?? null, updated_at: data?.updated_at ?? null })
}
