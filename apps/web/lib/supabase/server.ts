import { createClient } from "@supabase/supabase-js"

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL
const serviceRoleKey = process.env.SUPABASE_SERVICE_ROLE_KEY

export const getSupabaseServer = () => {
  if (!supabaseUrl || !serviceRoleKey) {
    return {
      client: null,
      error: "Supabase env vars missing: NEXT_PUBLIC_SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY",
    }
  }
  return { client: createClient(supabaseUrl, serviceRoleKey), error: null }
}
