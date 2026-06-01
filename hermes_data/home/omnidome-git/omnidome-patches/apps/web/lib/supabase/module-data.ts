import { supabase } from './client'
import { createServerSupabase } from './server'

export interface ModuleData {
  module_name: string
  payload: Record<string, any>
  updated_at: string
}

// Client-side: get module data by name
export async function getModuleData(moduleName: string): Promise<ModuleData | null> {
  const { data, error } = await supabase
    .from('module_data')
    .select('*')
    .eq('module_name', moduleName)
    .single()
  if (error) {
    console.error(`getModuleData(${moduleName}):`, error)
    return null
  }
  return data
}

// Server-side: get all module data
export async function getAllModuleData(): Promise<ModuleData[]> {
  const sb = createServerSupabase()
  const { data, error } = await sb.from('module_data').select('*')
  if (error) {
    console.error('getAllModuleData:', error)
    return []
  }
  return data || []
}

// Upsert module data (admin only)
export async function upsertModuleData(
  moduleName: string,
  payload: Record<string, any>
): Promise<ModuleData | null> {
  const sb = createServerSupabase()
  const { data, error } = await sb
    .from('module_data')
    .upsert({ module_name: moduleName, payload }, { onConflict: 'module_name' })
    .select()
    .single()
  if (error) {
    console.error(`upsertModuleData(${moduleName}):`, error)
    return null
  }
  return data
}
