/**
 * Signed internal identity (the web half of AUTH_MODE=signed).
 *
 * Backends no longer trust raw x-user-id / x-tenant-id headers: this module signs the
 * identity the web tier verified (HMAC-SHA256 with INTERNAL_AUTH_SECRET), and the
 * backend verifies it (services/common/internal_auth.py). The two implementations
 * MUST produce identical bytes; lib/internal-identity.test.mjs and
 * services/common/tests/test_internal_auth.py pin the same test vector.
 *
 * Canonical string (UTF-8, "\n"-joined):
 *   v1, METHOD, decoded-path, ts(seconds), user_id, tenant_id, roles, permissions,
 *   modules, org_id
 * with ids lower-cased and role/permission/module lists trimmed, de-duplicated, sorted
 * and comma-joined. Signature = lower-case hex. Sent as x-identity-ts / x-identity-sig.
 *
 * Self-contained on purpose (no "@/..." imports, erasable TS only, Web Crypto only) so it
 * runs in the proxy, in route handlers and directly under `node --test`.
 */

export const TS_HEADER = "x-identity-ts"
export const SIG_HEADER = "x-identity-sig"
const VERSION = "v1"

export interface SignFields {
  method: string
  path: string
  ts: number
  userId?: string | null
  tenantId?: string | null
  roles?: string | null
  permissions?: string | null
  modules?: string | null
  orgId?: string | null
}

function normList(value?: string | null): string {
  if (!value) return ""
  const items = value
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean)
  return Array.from(new Set(items)).sort().join(",")
}

const normId = (v?: string | null) => (v || "").trim().toLowerCase()

export function canonicalString(f: SignFields): string {
  return [
    VERSION,
    f.method.trim().toUpperCase(),
    f.path,
    String(Math.trunc(f.ts)),
    normId(f.userId),
    normId(f.tenantId),
    normList(f.roles),
    normList(f.permissions),
    normList(f.modules),
    normId(f.orgId),
  ].join("\n")
}

export async function hmacHex(secret: string, message: string): Promise<string> {
  const enc = new TextEncoder()
  const key = await crypto.subtle.importKey("raw", enc.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"])
  const sig = new Uint8Array(await crypto.subtle.sign("HMAC", key, enc.encode(message)))
  return Array.from(sig, (b) => b.toString(16).padStart(2, "0")).join("")
}

export function signIdentity(secret: string, fields: SignFields): Promise<string> {
  return hmacHex(secret, canonicalString(fields))
}

/** Path exactly as the backend will see it: percent-decoded, no query string. */
export function decodedPath(pathname: string): string {
  const p = pathname.split("?")[0].split("#")[0]
  try {
    return decodeURIComponent(p)
  } catch {
    return p
  }
}

/**
 * Path the backend receives for a /svc/<service>/<rest> request served by a next.config.mjs
 * rewrite (prefix stripped). Route-handler services re-sign with their own outbound path.
 */
export function backendPathForSvc(pathname: string): string {
  const m = /^\/svc\/[^/]+(\/.*)?$/.exec(pathname)
  return decodedPath(m ? m[1] || "/" : pathname)
}

const MIN_SECRET_LENGTH = 32
let warned = false

export function internalAuthSecret(): string {
  const secret = (process.env.INTERNAL_AUTH_SECRET || "").trim()
  if (secret.length < MIN_SECRET_LENGTH) {
    if (!warned) {
      warned = true
      console.error(
        "[internal-identity] INTERNAL_AUTH_SECRET is missing or shorter than 32 chars: identity headers are NOT signed. " +
          "Backends running AUTH_MODE=signed will answer 401/503.",
      )
    }
    return ""
  }
  return secret
}

/**
 * Set x-identity-ts / x-identity-sig on `headers` for the identity headers it currently holds.
 * Always clears any stale signature first (a signature from an earlier hop covers a different
 * path). No identity headers or no secret -> no signature.
 */
export async function signHeaders(headers: Headers, method: string, path: string, now?: number): Promise<Headers> {
  headers.delete(TS_HEADER)
  headers.delete(SIG_HEADER)
  const userId = headers.get("x-user-id")
  const tenantId = headers.get("x-tenant-id")
  if (!userId && !tenantId) return headers
  const secret = internalAuthSecret()
  if (!secret) return headers
  const ts = now ?? Math.floor(Date.now() / 1000)
  const sig = await signIdentity(secret, {
    method,
    path,
    ts,
    userId,
    tenantId,
    roles: headers.get("x-roles"),
    permissions: headers.get("x-permissions"),
    modules: headers.get("x-modules"),
    orgId: headers.get("x-org-id"),
  })
  headers.set(TS_HEADER, String(ts))
  headers.set(SIG_HEADER, sig)
  return headers
}

/**
 * fetch() for calls to a backend service: signs the FINAL identity headers in `init.headers`
 * over the request method and the target URL's path. Use instead of fetch() in every route
 * handler that builds backend identity headers itself.
 */
export async function signedFetch(input: string | URL, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers)
  const url = typeof input === "string" ? new URL(input) : input
  await signHeaders(headers, init.method || "GET", decodedPath(url.pathname))
  return fetch(input, { ...init, headers })
}
