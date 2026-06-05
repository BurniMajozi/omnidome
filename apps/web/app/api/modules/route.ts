import { NextRequest, NextResponse } from 'next/server'
import { getSupabaseServer } from '../../../lib/supabase/server'

// GET /api/modules/[id] — fetch module data by ID
export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params
  const { client: sb, error: sbError } = getSupabaseServer()
  if (sbError || !sb) {
    return NextResponse.json({ error: sbError ?? "Supabase client not initialized" }, { status: 500 })
  }
  const { data, error } = await sb
    .from('module_data')
    .select('*')
    .eq('module_name', id)
    .single()

  if (error) {
    return NextResponse.json({ error: error.message }, { status: 404 })
  }
  return NextResponse.json(data)
}

// POST /api/modules/[id] — upsert module data by ID
export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params
  const body = await request.json()

  const { client: sb, error: sbError } = getSupabaseServer()
  if (sbError || !sb) {
    return NextResponse.json({ error: sbError ?? "Supabase client not initialized" }, { status: 500 })
  }
  const { data, error } = await sb
    .from('module_data')
    .upsert({ module_name: id, payload: body }, { onConflict: 'module_name' })
    .select()
    .single()

  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 })
  }
  return NextResponse.json(data)
}
