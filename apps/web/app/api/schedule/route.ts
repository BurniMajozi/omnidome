import { NextResponse } from "next/server"
import { getSupabaseServer } from "@/lib/supabase/server"

export async function GET(request: Request) {
  const { client: supabaseClient, error: supabaseError } = getSupabaseServer()
  if (supabaseError) {
    return NextResponse.json({ error: supabaseError }, { status: 500 })
  }
  const { searchParams } = new URL(request.url)
  const ownerId = searchParams.get("owner_id")

  let query = supabaseClient.from("schedule_events").select("*")
  if (ownerId) query = query.eq("owner_id", ownerId)

  const { data, error } = await query.order("start_at", { ascending: true })
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
  const { data, error } = await supabaseClient.from("schedule_events").insert(body).select("*")
  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 })
  }
  return NextResponse.json({ data })
}

export async function PATCH(request: Request) {
  const { client: supabaseClient, error: supabaseError } = getSupabaseServer()
  if (supabaseError) {
    return NextResponse.json({ error: supabaseError }, { status: 500 })
  }
  const body = await request.json()
  const { id, ...updates } = body
  if (!id) {
    return NextResponse.json({ error: "Missing schedule event id" }, { status: 400 })
  }
  const { data, error } = await supabaseClient
    .from("schedule_events")
    .update(updates)
    .eq("id", id)
    .select("*")
  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 })
  }
  return NextResponse.json({ data })
}
