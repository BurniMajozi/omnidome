import { NextResponse } from "next/server"
import { getSupabaseServer } from "@/lib/supabase/server"

export async function GET(request: Request) {
  const { client: supabaseClient, error: supabaseError } = getSupabaseServer()
  if (supabaseError) {
    return NextResponse.json({ error: supabaseError }, { status: 500 })
  }
  const { searchParams } = new URL(request.url)
  const status = searchParams.get("status")

  let query = supabaseClient.from("escalations").select("*")
  if (status) query = query.eq("status", status)

  const { data, error } = await query.order("created_at", { ascending: false })
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
  const { data, error } = await supabaseClient.from("escalations").insert(body).select("*")
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
    return NextResponse.json({ error: "Missing escalation id" }, { status: 400 })
  }
  const { data, error } = await supabaseClient.from("escalations").update(updates).eq("id", id).select("*")
  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 })
  }
  return NextResponse.json({ data })
}
