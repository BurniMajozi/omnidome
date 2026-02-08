import { NextResponse } from "next/server"
import { getSupabaseServer } from "@/lib/supabase/server"

export async function GET() {
  const { client: supabaseClient, error: supabaseError } = getSupabaseServer()
  if (supabaseError) {
    return NextResponse.json({ error: supabaseError }, { status: 500 })
  }
  const { error } = await supabaseClient.from("channels").select("id").limit(1)
  if (error) {
    return NextResponse.json({ ok: false, error: error.message }, { status: 503 })
  }
  return NextResponse.json({ ok: true })
}