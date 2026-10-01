/**
 * Pure decision logic for proxy.ts identity resolution (no I/O, unit-tested in identity-resolve.test.mjs).
 *
 * The admin DB (`/internal/users/by-email`) is authoritative for tenant / roles / is_active. The
 * Supabase `app_metadata` copy is a cache that ignores is_active, so it may only be used for users the
 * admin DB has NEVER known (a definitive 404). When the admin service is merely unavailable
 * (5xx / 429 / timeout / network / garbage) we FAIL CLOSED: a recent identity for the same token is
 * reused for a short stale window, otherwise the caller gets 503 identity_unavailable.
 */

export const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
export const POSITIVE_TTL_MS = 5_000
/** How long a previously-resolved identity may be reused while the admin service is failing. */
export const STALE_ON_ERROR_MS = 30_000
export const RETRY_AFTER_SECONDS = 5

export interface Identity {
  userId: string
  tenantId: string
  roles?: string
}

export type AdminLookupResult =
  | { kind: "ok"; userId: string; tenantId: string; roles: string[]; isActive: boolean }
  /** Definitive 404: the admin DB has never known this email. */
  | { kind: "not_found" }
  /** No internal key configured (local dev): the admin DB cannot be consulted at all. */
  | { kind: "not_configured" }
  /** 5xx / 429 / timeout / network error / malformed body / unexpected status. */
  | { kind: "unavailable" }

export interface StaleEntry {
  identity: Identity
  /** Epoch ms at which the identity was resolved from the admin DB (not the app_metadata fallback). */
  at: number
}

export type Resolution =
  | { kind: "identity"; identity: Identity; fresh: boolean }
  | { kind: "inactive" }
  | { kind: "no-tenant" }
  | { kind: "unavailable"; retryAfter: number }

const ROLE_RE = /^[\w.:-]+$/

/** Classify an admin-service HTTP answer. `body` is the parsed JSON (or undefined). */
export function classifyAdminResponse(status: number, body: unknown): AdminLookupResult {
  if (status === 404) {
    const detail = (body as { detail?: unknown } | undefined)?.detail
    // Only the service's own "User not found" is definitive; a 404 from a proxy/other route is an outage.
    return typeof detail === "string" && /^user not found$/i.test(detail) ? { kind: "not_found" } : { kind: "unavailable" }
  }
  if (status < 200 || status >= 300) return { kind: "unavailable" }
  const b = body as Record<string, unknown> | undefined
  if (!b || typeof b.user_id !== "string" || typeof b.tenant_id !== "string" || !UUID_RE.test(b.user_id) || !UUID_RE.test(b.tenant_id)) {
    return { kind: "unavailable" }
  }
  const roles = Array.isArray(b.roles) ? (b.roles as unknown[]).filter((r): r is string => typeof r === "string" && ROLE_RE.test(r)) : []
  return { kind: "ok", userId: b.user_id, tenantId: b.tenant_id, roles, isActive: b.is_active !== false }
}

function metaRoles(appMetadata: Record<string, unknown> | undefined): string[] | undefined {
  const roles = appMetadata?.roles
  if (Array.isArray(roles) && roles.every((r) => typeof r === "string" && ROLE_RE.test(r))) return roles as string[]
  return undefined
}

export interface ResolveInput {
  lookup: AdminLookupResult
  /** Verified Supabase user id and app_metadata (service-role writable only). */
  supabaseUserId: string
  appMetadata?: Record<string, unknown>
  stale?: StaleEntry | null
  now: number
}

export function resolveIdentityDecision(input: ResolveInput): Resolution {
  const { lookup, appMetadata, stale, now } = input

  if (lookup.kind === "unavailable") {
    if (stale && now - stale.at <= STALE_ON_ERROR_MS) return { kind: "identity", identity: stale.identity, fresh: false }
    return { kind: "unavailable", retryAfter: RETRY_AFTER_SECONDS }
  }

  if (lookup.kind === "ok") {
    if (!lookup.isActive) return { kind: "inactive" }
    const identity: Identity = { userId: lookup.userId, tenantId: lookup.tenantId }
    if (lookup.roles.length > 0) {
      // The DB is authoritative for tenant roles. platform_admin is granted out of band (app_metadata,
      // service role only) and never lives in the tenant role tables: keep it.
      const roles = [...lookup.roles]
      const meta = metaRoles(appMetadata)
      if (meta?.includes("platform_admin") && !roles.includes("platform_admin")) roles.push("platform_admin")
      identity.roles = roles.join(",")
    } else {
      // In the admin DB but with zero DB roles (never provisioned/synced): app_metadata roles apply.
      const meta = metaRoles(appMetadata)
      if (meta) identity.roles = meta.join(",")
    }
    return { kind: "identity", identity, fresh: true }
  }

  // not_found / not_configured: the admin DB has no opinion. app_metadata is the only source
  // (platform owner / test accounts). user_metadata is never trusted.
  const appTenant = appMetadata?.tenant_id
  if (typeof appTenant === "string" && UUID_RE.test(appTenant)) {
    // Do not honour a metadata copy the sync explicitly marked inactive.
    if (appMetadata?.is_active === false) return { kind: "inactive" }
    const identity: Identity = { userId: input.supabaseUserId, tenantId: appTenant }
    const meta = metaRoles(appMetadata)
    if (meta) identity.roles = meta.join(",")
    return { kind: "identity", identity, fresh: true }
  }
  return { kind: "no-tenant" }
}
