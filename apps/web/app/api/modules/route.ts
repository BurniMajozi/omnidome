import { NextRequest, NextResponse } from 'next/server'
import { getSupabaseServer } from '../../../lib/supabase/server'

// GET /api/modules — list all module_data rows
export async function GET() {
  const { client: sb, error: sbError } = getSupabaseServer()
  if (sbError || !sb) {
    return NextResponse.json({ error: sbError ?? "Supabase client not initialized" }, { status: 500 })
  }
  const { data, error } = await sb
    .from('module_data')
    .select('module_id, data, updated_at')

  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 })
  }
  return NextResponse.json(data)
}

// POST /api/modules — upsert module data; body must include module_id
export async function POST(request: NextRequest) {
  const body = await request.json()
  const { module_id, data: moduleData } = body ?? {}

  if (!module_id || moduleData === undefined) {
    return NextResponse.json({ error: "Request body must include module_id and data" }, { status: 400 })
  }

  const { client: sb, error: sbError } = getSupabaseServer()
  if (sbError || !sb) {
    return NextResponse.json({ error: sbError ?? "Supabase client not initialized" }, { status: 500 })
  }
  const { data, error } = await sb
    .from('module_data')
    .upsert({ module_id, data: moduleData }, { onConflict: 'module_id' })
    .select()
    .single()

  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 })
  }
  return NextResponse.json(data)
}
