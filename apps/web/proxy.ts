/**
 * Edge auth gate for every /svc/*, /api/* and /gateway/* request.
 *
 * Why: the backends used to run AUTH_MODE=header (now AUTH_MODE=signed, see lib/internal-identity.ts) and trust whatever X-User-Id /
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
 * Tenant + roles resolution (lib/api-auth.ts semantics): the admin service's
 * /internal/users/by-email (authoritative backend `users` + roles tables, incl. is_active)
 * when reachable, otherwise `app_metadata` (a cache the admin service writes server-side
 * only). `user_metadata` is user-editable and is NEVER trusted. No tenant -> 403;
 * a deactivated user -> 403 account_inactive (checked on every cache miss, TTL 5s).
 *
 * Page routes (/dashboard etc.) are not handled here: the Supabase session lives
 * in localStorage (no cookie), so the server cannot see it; the dashboard page
 * redirects to /auth client-side and every data request it makes is gated above.
 */
import { NextRequest, NextResponse } from "next/server"
import { createClient } from "@supabase/supabase-js"
import { backendPathForSvc, signHeaders } from "@/lib/internal-identity"
import { hasUnsafePath } from "@/lib/safe-path"

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
  "x-identity-ts",
  "x-identity-sig",
]

// Public by design. Each of these is protected by its own secret/signature (or
// carries no tenant data). Method-scoped where possible.
const PUBLIC_ROUTES: Array<{ methods: string[]; pattern: RegExp }> = [
  // Workflow webhook trigger (optional X-Webhook-Key checked in the handler)
  { methods: ["POST"], pattern: /^\/api\/workflows\/hook\/[A-Za-z0-9_-]+$/ },
  // Anonymous site analytics beacon (analytics-provider.tsx)
  { methods: ["POST"], pattern: /^\/api\/analytics\/track\/[A-Za-z0-9_-]+(?:\/[A-Za-z0-9_-]+)*$/ },
  // Supabase reachability probe (returns only {ok})
  { methods: ["GET"], pattern: /^\/api\/supabase\/health$/ },
  // Zernio / social / email provider webhooks: HMAC-verified by the marketing service
  { methods: ["POST"], pattern: /^\/svc\/marketing\/social\/webhooks\/[A-Za-z0-9_-]+(?:\/[A-Za-z0-9_-]+)?$/ },
  { methods: ["POST"], pattern: /^\/svc\/marketing\/email\/webhook$/ },
  // Recipient unsubscribe page / one-click POST: authorised by an HMAC-signed token in `?t=`
  { methods: ["GET", "POST"], pattern: /^\/svc\/marketing\/email\/unsubscribe$/ },
]

interface Identity {
  userId: string
  tenantId: string
  roles?: string
}

interface AdminLookup extends Identity {
  isActive: boolean
  // true when the admin DB holds at least one role for this user (else app_metadata roles are used)
  rolesAuthoritative: boolean
}

// Short TTL: a role change or deactivation in the admin DB is enforced within ~5s.
const CACHE_TTL_MS = 5_000
const CACHE_MAX = 500
const cache = new Map<string, { identity: Identity | "no-tenant" | "inactive"; expires: number }>()
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

async function lookupAdmin(email: string): Promise<AdminLookup | null> {
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
      const roles: string[] = Array.isArray(body.roles) ? body.roles.filter((r: unknown) => typeof r === "string" && /^[\w.:-]+$/.test(r as string)) : []
      return {
        userId: body.user_id,
        tenantId: body.tenant_id,
        roles: roles.join(","),
        isActive: body.is_active !== false,
        // Only a NON-EMPTY DB role set is authoritative. A user who is in the admin DB but has
        // zero DB roles (never provisioned/synced, e.g. test@omnidome.local) falls back to
        // app_metadata.roles below instead of being stripped to org_user.
        rolesAuthoritative: roles.length > 0,
      }
    }
    return null
  } catch {
    adminDownUntil = Date.now() + 30_000 // don't pay the timeout on every request
    return null
  }
}

/** Verified identity, "no-tenant" (valid user, no tenant), "inactive" (deactivated in the admin DB), or null (invalid token). */
async function verify(token: string): Promise<Identity | "no-tenant" | "inactive" | null> {
  const hit = cache.get(token)
  if (hit && hit.expires > Date.now()) return hit.identity
  if (!supabase) return null

  const { data, error } = await supabase.auth.getUser(token)
  if (error || !data.user) return null
  const user = data.user
  // Identity is keyed on the email: an unconfirmed sign-up must not inherit a provisioned user's tenant.
  if (!user.email_confirmed_at && !user.confirmed_at) return null

  let result: Identity | "no-tenant" | "inactive"
  const admin = user.email ? await lookupAdmin(user.email) : null
  if (admin && !admin.isActive) {
    result = "inactive"
  } else if (admin) {
    result = { userId: admin.userId, tenantId: admin.tenantId }
    // roles come from the admin DB; app_metadata only for users the DB has no roles for yet
    if (admin.rolesAuthoritative) {
      result.roles = admin.roles
      // platform_admin is granted out of band (app_metadata, service role only), never through the
      // tenant role tables, so keep it when the DB is authoritative for the tenant roles.
      const meta = (user.app_metadata as Record<string, unknown> | undefined)?.roles
      if (Array.isArray(meta) && meta.includes("platform_admin") && !(admin.roles || "").split(",").includes("platform_admin")) {
        result.roles = admin.roles ? `${admin.roles},platform_admin` : "platform_admin"
      }
    }
  } else {
    // app_metadata is writable only with the service role; user_metadata is not trusted.
    const appTenant = (user.app_metadata as Record<string, unknown> | undefined)?.tenant_id
    result = typeof appTenant === "string" && UUID_RE.test(appTenant) ? { userId: user.id, tenantId: appTenant } : "no-tenant"
  }
  if (result !== "no-tenant" && result !== "inactive" && result.roles === undefined) {
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

  // Reject traversal / encoded-separator paths before any allow-list check: handlers decode the
  // path and fetch() normalizes "..", so a public-looking path must not be able to escape its prefix.
  if (hasUnsafePath(request.nextUrl.pathname) || hasUnsafePath(new URL(request.url).pathname)) {
    return json(400, "invalid_path")
  }

  const headers = new Headers(request.headers)
  for (const h of IDENTITY_HEADERS) headers.delete(h)

  const isPublic = PUBLIC_ROUTES.some((r) => r.methods.includes(method) && r.pattern.test(pathname))
  if (isPublic || method === "OPTIONS") {
    return NextResponse.next({ request: { headers } })
  }

  const auth = request.headers.get("authorization")
  let token = auth && /^bearer /i.test(auth) ? auth.slice(7).trim() : ""
  // Set when the credential came in the query string (WS upgrade): it must be stripped from the
  // URL forwarded to the backend so it never reaches uvicorn's access log.
  let stripQueryToken = false
  // Browsers cannot set headers on a WebSocket upgrade: accept the token from the
  // query string, for the communication WS endpoint only.
  if (
    !token &&
    method === "GET" &&
    request.headers.get("upgrade")?.toLowerCase() === "websocket" &&
    pathname === "/svc/communication/api/v1/ws"
  ) {
    token = request.nextUrl.searchParams.get("token")?.trim() || ""
    stripQueryToken = true
  }
  if (!token) return json(401, "unauthorized")

  const identity = await verify(token)
  if (!identity) return json(401, "unauthorized")
  if (identity === "inactive") return json(403, "account_inactive")
  if (identity === "no-tenant") {
    // A freshly signed-in invitee has no tenant yet: let them (and only them) redeem an invite.
    // The admin service verifies the bearer token itself and matches it to the invite's email.
    if (method === "POST" && pathname === "/svc/admin/invites/accept") {
      return NextResponse.next({ request: { headers } })
    }
    return json(403, "tenant_unresolved")
  }

  headers.set("x-user-id", identity.userId)
  headers.set("x-tenant-id", identity.tenantId)
  if (identity.roles) headers.set("x-roles", identity.roles)
  // Sign the verified identity for the backend (AUTH_MODE=signed). Bound to method + the path the
  // backend will see: for /svc/<service>/* rewrites that is the path with the prefix stripped.
  // /api/*, /gateway/* and the /svc/<crm|billing|...> route handlers rebuild their own identity
  // headers and re-sign the final values with signedFetch() (lib/internal-identity.ts).
  await signHeaders(headers, method, backendPathForSvc(pathname))
  if (stripQueryToken) {
    // The backend authenticates via the signed headers; drop the credential from the forwarded URL.
    const clean = request.nextUrl.clone()
    clean.searchParams.delete("token")
    return NextResponse.rewrite(clean, { request: { headers } })
  }
  return NextResponse.next({ request: { headers } })
}

export const config = {
  matcher: ["/svc/:path*", "/api/:path*", "/gateway/:path*"],
}
