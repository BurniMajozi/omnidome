import { NextResponse } from "next/server"
import { getSupabaseServer } from "@/lib/supabase/server"

export async function GET(request: Request) {
  const { client: supabaseClient, error: supabaseError } = getSupabaseServer()
  if (supabaseError) {
    return NextResponse.json({ error: supabaseError }, { status: 500 })
  }
  const { searchParams } = new URL(request.url)
  const channelId = searchParams.get("channel_id")
  let query = supabaseClient.from("messages").select("*")
  if (channelId) {
    query = query.eq("channel_id", channelId)
  }
  const { data, error } = await query.order("created_at", { ascending: true })
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
  const { data, error } = await supabaseClient.from("messages").insert(body).select("*")
  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 })
  }
  return NextResponse.json({ data })
}
