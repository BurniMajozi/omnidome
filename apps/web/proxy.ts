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
 * when reachable. `app_metadata` (a cache the admin service writes server-side only) is used ONLY for
 * users the admin DB has never known (definitive 404) or when no INTERNAL_SERVICE_KEY is configured; if the admin
 * service is failing (5xx/429/timeout) the proxy FAILS CLOSED: a same-token identity <= 30s old is reused,
 * otherwise 503 identity_unavailable (Retry-After). `user_metadata` is user-editable and is NEVER trusted. No tenant -> 403;
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
import { singleFlight } from "@/lib/single-flight"
import {
  POSITIVE_TTL_MS,
  STALE_ON_ERROR_MS,
  RETRY_AFTER_SECONDS,
  classifyAdminResponse,
  resolveIdentityDecision,
  type AdminLookupResult,
  type Identity,
} from "@/lib/identity-resolve"

const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL || process.env.SUPABASE_URL
const SUPABASE_ANON_KEY = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || process.env.SUPABASE_ANON_KEY
const ADMIN_SERVICE_URL = process.env.ADMIN_SERVICE_URL || "http://admin:8013"
const INTERNAL_SERVICE_KEY = process.env.INTERNAL_SERVICE_KEY || ""


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
  // Paystack authenticates the exact raw body with its provider signature.
  { methods: ["POST"], pattern: /^\/svc\/billing\/payments\/paystack\/webhook$/ },
  // Invite activation requires a code delivered to the invitee by AgentMail.
  { methods: ["POST"], pattern: /^\/svc\/admin\/invites\/claim$/ },
  // Recipient unsubscribe page / one-click POST: authorised by an HMAC-signed token in `?t=`
  { methods: ["GET", "POST"], pattern: /^\/svc\/marketing\/email\/unsubscribe$/ },
  // Portal Builder: published page by slug (anonymous visitors; backend rate-limits, returns published pages only)
  { methods: ["GET"], pattern: /^\/svc\/portal_builder\/api\/v1\/portal\/public\/[A-Za-z0-9-]{1,100}$/ },
  // Portal Builder: private review link, authorised by the unguessable share token in the path
  { methods: ["GET"], pattern: /^\/svc\/portal_builder\/api\/v1\/portal\/shared\/[A-Za-z0-9_-]{16,200}$/ },
  // Portal Builder: public form submission (consent required, honeypot + 5/min per IP and page enforced by the backend)
  { methods: ["POST"], pattern: /^\/svc\/portal_builder\/api\/v1\/portal\/submissions$/ },
]

type Verified = Identity | "no-tenant" | "inactive"

// Short TTL: a role change or deactivation in the admin DB is enforced within ~5s.
const CACHE_MAX = 500
// `at` is when the entry was resolved; entries outlive POSITIVE_TTL_MS so they can serve as the
// (<= STALE_ON_ERROR_MS) stale-while-error fallback for the SAME token only.
const cache = new Map<string, { value: Verified; at: number }>()
let adminDownUntil = 0
const ADMIN_COOLDOWN_MS = 5_000

const supabase =
  SUPABASE_URL && SUPABASE_ANON_KEY
    ? createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
        auth: { persistSession: false, autoRefreshToken: false, detectSessionInUrl: false },
      })
    : null

function json(status: number, error: string, extra?: Record<string, string>) {
  return NextResponse.json({ error }, { status, headers: { "cache-control": "no-store", ...(extra || {}) } })
}

async function lookupAdmin(email: string): Promise<AdminLookupResult> {
  if (!INTERNAL_SERVICE_KEY) return { kind: "not_configured" }
  if (Date.now() < adminDownUntil) return { kind: "unavailable" } // don't pay the timeout on every request
  try {
    const res = await fetch(`${ADMIN_SERVICE_URL}/internal/users/by-email?email=${encodeURIComponent(email)}`, {
      headers: { "x-internal-key": INTERNAL_SERVICE_KEY },
      cache: "no-store",
      signal: AbortSignal.timeout(3500),
    })
    let body: unknown
    try {
      body = await res.json()
    } catch {
      body = undefined
    }
    const result = classifyAdminResponse(res.status, body)
    if (result.kind === "unavailable") adminDownUntil = Date.now() + ADMIN_COOLDOWN_MS
    return result
  } catch {
    adminDownUntil = Date.now() + ADMIN_COOLDOWN_MS
    return { kind: "unavailable" }
  }
}

/** Verified identity, "no-tenant" (valid user, no tenant), "inactive" (deactivated in the admin DB),
 * "unavailable" (admin service failing and no fresh cached identity: fail closed), or null (invalid token). */
const verifyInFlight = singleFlight<string, Verified | "unavailable" | null>()
function verify(token: string): Promise<Verified | "unavailable" | null> {
  return verifyInFlight(token, () => verifyIdentity(token))
}

async function verifyIdentity(token: string): Promise<Verified | "unavailable" | null> {
  const now = Date.now()
  const hit = cache.get(token)
  if (hit && now - hit.at <= POSITIVE_TTL_MS) return hit.value
  if (!supabase) return null

  let data: { user: any } | null = null
  try {
    const res = await supabase.auth.getUser(token)
    if (res.error || !res.data.user) {
      cache.delete(token)
      return null
    }
    data = res.data
  } catch (err) {
    // If Supabase network/DNS is transiently failing, reuse a recent stale identity if within window
    if (hit && typeof hit.value === "object" && now - hit.at <= STALE_ON_ERROR_MS) {
      return hit.value
    }
    return "unavailable"
  }

  const user = data.user
  // Identity is keyed on the email: an unconfirmed sign-up must not inherit a provisioned user's tenant.
  if (!user.email_confirmed_at && !user.confirmed_at) return null

  const lookup: AdminLookupResult = user.email ? await lookupAdmin(user.email) : { kind: "not_found" }
  const stale = hit && typeof hit.value === "object" ? { identity: hit.value, at: hit.at } : null
  const decision = resolveIdentityDecision({
    lookup,
    supabaseUserId: user.id,
    appMetadata: user.app_metadata as Record<string, unknown> | undefined,
    stale,
    now,
  })
  if (decision.kind === "unavailable") return "unavailable"
  const value: Verified = decision.kind === "identity" ? decision.identity : decision.kind
  if (decision.kind === "identity" && !decision.fresh) return value // stale reuse: keep the original timestamp
  if (cache.size >= CACHE_MAX) {
    for (const [k, v] of cache) if (now - v.at > STALE_ON_ERROR_MS) cache.delete(k)
    if (cache.size >= CACHE_MAX) cache.clear()
  }
  // inactive overwrites (evicts) any cached identity for this token
  cache.set(token, { value, at: now })
  return value
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
  if (identity === "unavailable") {
    return json(503, "identity_unavailable", { "retry-after": String(RETRY_AFTER_SECONDS) })
  }
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
