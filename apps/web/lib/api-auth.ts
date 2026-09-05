/**
 * Shared server-side identity resolution for Next.js API route handlers.
 *
 * Backend services (communication, etc.) authorize on X-User-Id / X-Tenant-Id.
 * Those must be resolved server-side from a *verified* Supabase token — never
 * trusted from client-sent headers (tenant-spoofing). This mirrors the logic in
 * app/api/orchestrator/[...path]/route.ts so every proxy route authenticates the
 * same way instead of forwarding raw client headers (which 401s).
 *
 * Usage in a route handler:
 *   const headers = await identityHeaders(request)   // Authorization + x-user-id + x-tenant-id + content-type
 *   const res = await fetch(backendUrl, { method, headers, body })
 */
import { NextRequest } from "next/server"
import { getSupabaseServer } from "@/lib/supabase/server"

const ADMIN_SERVICE_URL = process.env.ADMIN_SERVICE_URL || "http://admin:8013"
const INTERNAL_SERVICE_KEY = process.env.INTERNAL_SERVICE_KEY || ""

export interface Identity {
  userId: string
  tenantId: string
}

/** Resolve a verified Supabase bearer token into {userId, tenantId}, or null. */
export async function resolveIdentity(bearerToken: string): Promise<Identity | null> {
  const { client } = getSupabaseServer()
  if (!client) return null

  const { data, error } = await client.auth.getUser(bearerToken)
  if (error || !data.user?.email) return null

  try {
    const res = await fetch(
      `${ADMIN_SERVICE_URL}/internal/users/by-email?email=${encodeURIComponent(data.user.email)}`,
      { headers: { "x-internal-key": INTERNAL_SERVICE_KEY }, cache: "no-store" },
    )
    if (!res.ok) return null
    const body = await res.json()
    if (!body.user_id || !body.tenant_id) return null
    return { userId: body.user_id, tenantId: body.tenant_id }
  } catch {
    return null
  }
}

/** Pull the bearer token from the request's Authorization header. */
export function bearerFrom(request: NextRequest): string | null {
  const auth = request.headers.get("authorization")
  return auth?.startsWith("Bearer ") ? auth.slice(7) : null
}

/**
 * Build outbound headers for a backend proxy call: forwards content-type +
 * Authorization, and injects server-resolved x-user-id / x-tenant-id.
 * Returns { headers, identity } — identity is null when the caller is
 * unauthenticated, so the route can 401 instead of calling the backend blind.
 */
export async function identityHeaders(
  request: NextRequest,
): Promise<{ headers: Headers; identity: Identity | null }> {
  const headers = new Headers()
  const ct = request.headers.get("content-type")
  if (ct) headers.set("content-type", ct)
  const auth = request.headers.get("authorization")
  if (auth) headers.set("authorization", auth)

  let identity: Identity | null = null
  const token = bearerFrom(request)
  if (token) {
    identity = await resolveIdentity(token)
    if (identity) {
      headers.set("x-user-id", identity.userId)
      headers.set("x-tenant-id", identity.tenantId)
    }
  }
  return { headers, identity }
}
