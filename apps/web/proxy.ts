/**
 * Edge auth gate for every /svc/*, /api/* and /gateway/* request.
 *
 * Why: the backends run AUTH_MODE=header and trust whatever X-User-Id /
 * X-Tenant-Id they receive. The /svc rewrites and several route handlers pass
 * client headers straight through, so without this gate anyone who can reach the
 * web port could read any tenant's data by sending those headers.
 *
 * What it does, in order:
 *   1. Public allow-list (webhooks / anonymous analytics / health) -> pass, but
 *      identity headers are still stripped so nothing client-supplied reaches a
 *      backend.
 *   2. Everything else needs a Supabase access token in `Authorization: Bearer`,
 *      verified server-side with supabase.auth.getUser(token) (not a JWT decode).
 *      Missing/invalid -> 401 JSON (no redirect).
 *   3. Strips every client-supplied identity header (x-user-id, x-tenant-id,
 *      x-roles, x-permissions, x-org-id, x-modules, x-internal-key, x-user-email)
 *      and re-injects x-user-id / x-tenant-id from the VERIFIED user.
 *
 * Tenant resolution (lib/api-auth.ts semantics): the admin service's
 * /internal/users/by-email (authoritative backend `users` table) when reachable,
 * otherwise `app_metadata.tenant_id` (set server-side only). `user_metadata` is
 * user-editable and is NEVER trusted. No tenant -> 403.
 *
 * Page routes (/dashboard etc.) are not handled here: the Supabase session lives
 * in localStorage (no cookie), so the server cannot see it; the dashboard page
 * redirects to /auth client-side and every data request it makes is gated above.
 */
import { NextRequest, NextResponse } from "next/server"
import { createClient } from "@supabase/supabase-js"

const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL || process.env.SUPABASE_URL
const SUPABASE_ANON_KEY = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || process.env.SUPABASE_ANON_KEY
const ADMIN_SERVICE_URL = process.env.ADMIN_SERVICE_URL || "http://admin:8013"
const INTERNAL_SERVICE_KEY = process.env.INTERNAL_SERVICE_KEY || ""

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

// Headers a client must never be able to set toward a backend.
const IDENTITY_HEADERS = [
  "x-user-id",
  "x-tenant-id",
  "x-roles",
  "x-permissions",
  "x-org-id",
  "x-modules",
  "x-user-email",
  "x-internal-key",
]

// Public by design. Each of these is protected by its own secret/signature (or
// carries no tenant data). Method-scoped where possible.
const PUBLIC_ROUTES: Array<{ methods: string[]; pattern: RegExp }> = [
  // Workflow webhook trigger (optional X-Webhook-Key checked in the handler)
  { methods: ["POST"], pattern: /^\/api\/workflows\/hook\/[^/]+$/ },
  // Anonymous site analytics beacon (analytics-provider.tsx)
  { methods: ["POST"], pattern: /^\/api\/analytics\/track\/.+$/ },
  // Supabase reachability probe (returns only {ok})
  { methods: ["GET"], pattern: /^\/api\/supabase\/health$/ },
  // Zernio / social / email provider webhooks: HMAC-verified by the marketing service
  { methods: ["POST"], pattern: /^\/svc\/marketing\/social\/webhooks\/.+$/ },
  { methods: ["POST"], pattern: /^\/svc\/marketing\/email\/webhook$/ },
]

interface Identity {
  userId: string
  tenantId: string
  roles?: string
}

const CACHE_TTL_MS = 30_000
const CACHE_MAX = 500
const cache = new Map<string, { identity: Identity | "no-tenant"; expires: number }>()
let adminDownUntil = 0

const supabase =
  SUPABASE_URL && SUPABASE_ANON_KEY
    ? createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
        auth: { persistSession: false, autoRefreshToken: false, detectSessionInUrl: false },
      })
    : null

function json(status: number, error: string) {
  return NextResponse.json({ error }, { status, headers: { "cache-control": "no-store" } })
}

async function lookupAdmin(email: string): Promise<{ userId: string; tenantId: string } | null> {
  if (!INTERNAL_SERVICE_KEY || Date.now() < adminDownUntil) return null
  try {
    const res = await fetch(`${ADMIN_SERVICE_URL}/internal/users/by-email?email=${encodeURIComponent(email)}`, {
      headers: { "x-internal-key": INTERNAL_SERVICE_KEY },
      cache: "no-store",
      signal: AbortSignal.timeout(1500),
    })
    if (!res.ok) return null
    const body = await res.json()
    if (UUID_RE.test(body?.user_id || "") && UUID_RE.test(body?.tenant_id || "")) {
      return { userId: body.user_id, tenantId: body.tenant_id }
    }
    return null
  } catch {
    adminDownUntil = Date.now() + 30_000 // don't pay the timeout on every request
    return null
  }
}

/** Verified identity, "no-tenant" for a valid user without a tenant, or null for an invalid token. */
async function verify(token: string): Promise<Identity | "no-tenant" | null> {
  const hit = cache.get(token)
  if (hit && hit.expires > Date.now()) return hit.identity
  if (!supabase) return null

  const { data, error } = await supabase.auth.getUser(token)
  if (error || !data.user) return null
  const user = data.user

  let result: Identity | "no-tenant"
  const admin = user.email ? await lookupAdmin(user.email) : null
  if (admin) {
    result = { userId: admin.userId, tenantId: admin.tenantId }
  } else {
    // app_metadata is writable only with the service role; user_metadata is not trusted.
    const appTenant = (user.app_metadata as Record<string, unknown> | undefined)?.tenant_id
    result = typeof appTenant === "string" && UUID_RE.test(appTenant) ? { userId: user.id, tenantId: appTenant } : "no-tenant"
  }
  if (result !== "no-tenant") {
    const roles = (user.app_metadata as Record<string, unknown> | undefined)?.roles
    if (Array.isArray(roles) && roles.every((r) => typeof r === "string" && /^[\w.:-]+$/.test(r))) {
      result.roles = roles.join(",")
    }
  }

  if (cache.size >= CACHE_MAX) cache.clear()
  cache.set(token, { identity: result, expires: Date.now() + CACHE_TTL_MS })
  return result
}

export async function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl
  const method = request.method.toUpperCase()

  const headers = new Headers(request.headers)
  for (const h of IDENTITY_HEADERS) headers.delete(h)

  const isPublic = PUBLIC_ROUTES.some((r) => r.methods.includes(method) && r.pattern.test(pathname))
  if (isPublic || method === "OPTIONS") {
    return NextResponse.next({ request: { headers } })
  }

  const auth = request.headers.get("authorization")
  let token = auth && /^bearer /i.test(auth) ? auth.slice(7).trim() : ""
  // Browsers cannot set headers on a WebSocket upgrade: accept the token from the
  // query string, for the communication WS endpoint only.
  if (
    !token &&
    method === "GET" &&
    request.headers.get("upgrade")?.toLowerCase() === "websocket" &&
    pathname === "/svc/communication/api/v1/ws"
  ) {
    token = request.nextUrl.searchParams.get("token")?.trim() || ""
  }
  if (!token) return json(401, "unauthorized")

  const identity = await verify(token)
  if (!identity) return json(401, "unauthorized")
  if (identity === "no-tenant") return json(403, "tenant_unresolved")

  headers.set("x-user-id", identity.userId)
  headers.set("x-tenant-id", identity.tenantId)
  if (identity.roles) headers.set("x-roles", identity.roles)
  return NextResponse.next({ request: { headers } })
}

export const config = {
  matcher: ["/svc/:path*", "/api/:path*", "/gateway/:path*"],
}
