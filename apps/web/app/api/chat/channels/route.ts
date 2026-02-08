import { NextResponse } from "next/server"
import { getSupabaseServer } from "@/lib/supabase/server"

export async function GET() {
  const { client: supabaseClient, error: supabaseError } = getSupabaseServer()
  if (supabaseError) {
    return NextResponse.json({ error: supabaseError }, { status: 500 })
  }
  const { data, error } = await supabaseClient.from("channels").select("*")
  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 })
  }
  return NextResponse.json({ data })
}

export async function POST(request: Request) {
  const { client: supabaseClient, error: supabaseError } = getSupabaseServer()
  if (supabaseError) {
    return NextResponse.json({ error: supabaseError }, { status: 500 })
  }
  const body = await request.json()
  const { data, error } = await supabaseClient.from("channels").insert(body).select("*")
  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 })
  }
  return NextResponse.json({ data })
}
