"use client"

/**
 * Admin API client - commission tiers, user management, audit log.
 * Proxies through the Next.js API routes to the admin service (port 8013).
 */

const ADMIN_API = "/api/admin"

export class BillingUnavailableError extends Error {
  constructor() {
    super("billing service not connected")
    this.name = "BillingUnavailableError"
  }
}

export class AdminApiError extends Error {
  status: number
  detail: unknown
  constructor(status: number, body: string) {
    super(`Admin API error ${status}: ${body}`)
    this.name = "AdminApiError"
    this.status = status
    let detail: unknown = body
    try {
      const parsed = JSON.parse(body)
      detail = parsed?.detail ?? parsed?.error ?? parsed
    } catch {
      /* non-JSON body */
    }
    this.detail = detail
  }
}

/** Human message for a backend error, verbatim where the server gave one. */
export function adminErrorMessage(err: unknown): string {
  if (err instanceof AdminApiError) {
    const d = err.detail
    if (typeof d === "string") return d || `Request failed (${err.status})`
    if (d && typeof d === "object") {
      const o = d as Record<string, unknown>
      if (o.error === "seat_limit_reached") {
        return `Seat limit reached (${o.seats_used} of ${o.seat_limit} seats used, including pending invites)`
      }
      if (typeof o.message === "string") return o.message
      if (typeof o.error === "string") return o.error
      return JSON.stringify(d)
    }
    return `Request failed (${err.status})`
  }
  if (err instanceof DOMException && err.name === "TimeoutError") return "The request timed out. Try again."
  return err instanceof Error ? err.message : String(err)
}

async function authHeader(): Promise<Record<string, string>> {
  // Attempt to attach Supabase session token if available
  try {
    const { getSessionSafe } = await import("@/lib/supabase/client")
    const { data } = await getSessionSafe()
    if (data.session?.access_token) return { Authorization: `Bearer ${data.session.access_token}` }
  } catch {
    // Supabase browser client optional in dev/fallback mode
  }
  return {}
}

async function fetchAdmin<T>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(await authHeader()),
  }

  const res = await fetch(`${ADMIN_API}${path}`, {
    cache: "no-store",
    signal: AbortSignal.timeout(20_000),
    headers: {
      ...headers,
      ...init?.headers,
    },
    ...init,
  })
  if (!res.ok) {
    const body = await res.text().catch(() => "")
    throw new AdminApiError(res.status, body)
  }
  return res.json()
}

// Types

export interface CommissionTier {
  id: string
  tenant_id: string
  tier_name: string
  min_deals: number
  max_deals: number | null
  rate_percent: string
  is_active: boolean
  sort_order: number
  created_at: string
  updated_at: string
}

export interface CommissionTierCreate {
  tier_name: string
  min_deals?: number
  max_deals?: number | null
  rate_percent?: string
  is_active?: boolean
  sort_order?: number
}

export interface CommissionTierUpdate {
  tier_name?: string
  min_deals?: number
  max_deals?: number | null
  rate_percent?: string
  is_active?: boolean
  sort_order?: number
}

export interface Tenant {
  id: string
  name: string
  domain?: string
  subdomain?: string
  org_code?: string
  tier?: string
  status?: string
  active?: boolean
  created_at?: string
  updated_at?: string
}

export interface ModuleCatalogItem {
  key?: string
  module_name?: string
  name: string
  description?: string
  enabled?: boolean
  is_core?: boolean
  license_required?: boolean
  config?: Record<string, unknown>
}

export interface AdminUser {
  id: string
  email: string
  name?: string
  full_name?: string
  is_active?: boolean
  created_at?: string
}

export interface AuditLogEntry {
  id: string
  tenant_id?: string
  user_id?: string
  action: string
  resource_type: string
  resource_id?: string
  metadata?: Record<string, unknown>
  created_at: string
}

// ── IAM: seats, invites, members ──

export interface SeatUsage {
  tenant_id: string
  seat_limit: number | null
  seat_price: string | null
  billing_status?: string
  active_users: number
  pending_invites: number
  seats_used: number
  seats_available: number | null
}

export interface PlatformSeatRow extends SeatUsage {
  name: string
  status?: string
}

export interface TenantInvite {
  id: string
  email: string
  roles: string[]
  status: string
  expires_at: string
  created_at?: string
}

export interface InviteDelivery {
  accept_link?: string
  email_requested?: boolean
  email_error?: string | null
  note?: string
}

export interface CreatedInvite extends InviteDelivery {
  invite_id: string
  email: string
  roles: string[]
  status: string
  expires_at: string
}

export interface TenantMember {
  id: string
  email: string
  name?: string | null
  is_active: boolean
  is_owner?: boolean
  roles: string[]
  created_at?: string
}

export interface CreatedTenant extends Tenant {
  seat_limit?: number | null
  seat_price?: string | null
  owner_invite?: InviteDelivery & { invite_id: string; email: string }
}

export interface Whoami {
  user_id: string
  tenant_id: string
  roles: string[]
}

export interface ReconcileReport {
  dry_run: boolean
  db_users: number
  supabase_users: number
  in_sync: number
  drift: Array<{ user_id: string; email: string; issue?: string; db?: unknown; supabase?: unknown; fixed?: boolean }>
  orphans_in_supabase_only: Array<{ supabase_id: string; email?: string; app_metadata_tenant?: string | null; app_metadata_roles?: string[] }>
  adopted?: unknown
}

export interface SeatBillingRun {
  id: string
  tenant_id: string
  period_start: string
  period_end: string
  peak_seats: number
  unit_price: string
  amount: string
  status: string
  invoice_id: string | null
}

/** Tenant roles with the server's ranks (mirrors services/admin/migrations.py ROLE_RANKS). */
export const TENANT_ROLE_RANKS: Record<string, number> = {
  owner: 90,
  org_admin: 80,
  manager: 50,
  hr_manager: 50,
  org_user: 10,
}
const ALIAS_RANKS: Record<string, number> = { admin: 80, tenant_admin: 80, super_admin: 80, line_manager: 50, hr_admin: 50, hr: 50 }

export const ROLE_LABELS: Record<string, string> = {
  owner: "Owner",
  org_admin: "Org admin",
  manager: "Manager",
  hr_manager: "HR manager",
  org_user: "User",
}

export function actorRank(actorRoles: string[]): number {
  if (actorRoles.includes("platform_admin")) return 100
  return Math.max(0, ...actorRoles.map((r) => TENANT_ROLE_RANKS[r] ?? ALIAS_RANKS[r] ?? 0))
}

/** Roles the actor may grant (the server re-checks; this keeps the UI honest). */
export function grantableRoles(actorRoles: string[]): string[] {
  const platform = actorRoles.includes("platform_admin")
  const owner = platform || actorRoles.includes("owner")
  const rank = actorRank(actorRoles)
  return Object.keys(TENANT_ROLE_RANKS).filter((r) => {
    if (r === "owner" && !owner) return false
    return platform || TENANT_ROLE_RANKS[r] <= rank
  })
}

// API methods

export const adminApi = {
  listTenants: () =>
    fetchAdmin<Tenant[]>("/tenants"),

  listModules: () =>
    fetchAdmin<ModuleCatalogItem[]>("/modules"),

  listTenantModules: (tenantId: string) =>
    fetchAdmin<ModuleCatalogItem[]>(`/tenants/${tenantId}/modules`),

  updateTenantModules: (tenantId: string, modules: { name: string; enabled: boolean; config?: Record<string, unknown> }[]) =>
    fetchAdmin<{ tenant_id: string; updated: number }>(`/tenants/${tenantId}/modules`, {
      method: "PUT",
      body: JSON.stringify({ modules }),
    }),

  listUsers: () =>
    fetchAdmin<AdminUser[]>("/users"),

  listAuditLog: (params?: { limit?: number; action?: string; resource_type?: string }) => {
    const query = new URLSearchParams()
    if (params?.limit) query.set("limit", String(params.limit))
    if (params?.action) query.set("action", params.action)
    if (params?.resource_type) query.set("resource_type", params.resource_type)
    const suffix = query.toString() ? `?${query}` : ""
    return fetchAdmin<AuditLogEntry[]>(`/audit-log${suffix}`)
  },

  listCommissionTiers: () =>
    fetchAdmin<CommissionTier[]>("/commission-tiers"),

  createCommissionTier: (data: CommissionTierCreate) =>
    fetchAdmin<{ id: string; tier_name: string; rate_percent: string }>("/commission-tiers", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  updateCommissionTier: (tierId: string, data: CommissionTierUpdate) =>
    fetchAdmin<{ status: string }>(`/commission-tiers/${tierId}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  deleteCommissionTier: (tierId: string) =>
    fetchAdmin<{ status: string }>(`/commission-tiers/${tierId}`, {
      method: "DELETE",
    }),

  listRoles: () =>
    fetchAdmin<{ id: string; name: string; description?: string; permissions?: string[] }[]>("/roles"),

  inviteUser: (data: { email: string; name?: string; role_id?: string; password?: string; is_active?: boolean }) =>
    fetchAdmin<AdminUser>("/users", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  assignUserRole: (userId: string, roleId: string) =>
    fetchAdmin<{ status?: string; user_id: string; role_id: string }>(`/users/${userId}/roles`, {
      method: "POST",
      body: JSON.stringify({ role_id: roleId }),
    }),

  removeUserRole: (userId: string, roleId: string) =>
    fetchAdmin<{ status?: string }>(`/users/${userId}/roles/${roleId}`, {
      method: "DELETE",
    }),

  // ── IAM: seats, invites, members ──
  whoami: async (): Promise<Whoami> => {
    const res = await fetch("/api/whoami", { cache: "no-store", signal: AbortSignal.timeout(10_000), headers: await authHeader() })
    if (!res.ok) throw new AdminApiError(res.status, await res.text().catch(() => ""))
    return res.json()
  },

  createTenant: (data: {
    name: string
    domain: string
    seat_limit?: number
    seat_price?: number
    owner_email?: string
    tier?: string
    send_owner_invite_email?: boolean
  }) => fetchAdmin<CreatedTenant>("/tenants", { method: "POST", body: JSON.stringify(data) }),

  updateTenant: (tenantId: string, data: { tier?: string; status?: string; active?: boolean; name?: string }) =>
    fetchAdmin<Tenant>(`/tenants/${tenantId}`, { method: "PUT", body: JSON.stringify(data) }),

  closeTenant: (tenantId: string) => fetchAdmin<Tenant>(`/tenants/${tenantId}`, { method: "DELETE" }),

  getSeats: (tenantId: string) => fetchAdmin<SeatUsage>(`/tenants/${tenantId}/seats?since_days=1`),

  setSeats: (tenantId: string, data: { seat_limit?: number; seat_price?: number }) =>
    fetchAdmin<SeatUsage>(`/tenants/${tenantId}/seats`, { method: "PUT", body: JSON.stringify(data) }),

  platformSeatUsage: () => fetchAdmin<{ tenants: PlatformSeatRow[]; total_seats_used: number }>("/platform/seat-usage"),

  listInvites: (tenantId: string) => fetchAdmin<TenantInvite[]>(`/tenants/${tenantId}/invites`),

  createInvite: (tenantId: string, data: { email: string; roles: string[]; send_email?: boolean }) =>
    fetchAdmin<CreatedInvite>(`/tenants/${tenantId}/invites`, { method: "POST", body: JSON.stringify(data) }),

  resendInvite: (inviteId: string, sendEmail = true) =>
    fetchAdmin<CreatedInvite>(`/invites/${inviteId}/resend?send_email=${sendEmail}`, { method: "POST" }),

  revokeInvite: (inviteId: string) => fetchAdmin<{ status: string }>(`/invites/${inviteId}`, { method: "DELETE" }),

  listMembers: (tenantId: string) => fetchAdmin<TenantMember[]>(`/tenants/${tenantId}/members`),

  setMemberRoles: (tenantId: string, userId: string, roles: string[]) =>
    fetchAdmin<{ added: string[]; removed: string[] }>(`/tenants/${tenantId}/members/${userId}/roles`, {
      method: "PUT",
      body: JSON.stringify({ roles }),
    }),

  deactivateMember: (tenantId: string, userId: string) =>
    fetchAdmin<{ changed: boolean }>(`/tenants/${tenantId}/members/${userId}/deactivate`, { method: "POST" }),

  reactivateMember: (tenantId: string, userId: string) =>
    fetchAdmin<{ changed: boolean }>(`/tenants/${tenantId}/members/${userId}/reactivate`, { method: "POST" }),

  transferOwnership: (tenantId: string, newOwnerUserId: string) =>
    fetchAdmin<{ owner_user_id: string }>(`/tenants/${tenantId}/transfer-ownership`, {
      method: "POST",
      body: JSON.stringify({ new_owner_user_id: newOwnerUserId }),
    }),

  reconcileSupabase: (apply = false) =>
    fetchAdmin<ReconcileReport>(`/admin/sync/reconcile?apply=${apply}`, { method: "POST" }),

  /** Billing service (may be down): resolves to runs, or throws BillingUnavailableError. */
  listSeatRuns: async (tenantId?: string): Promise<SeatBillingRun[]> => {
    let res: Response
    try {
      res = await fetch(`/svc/billing/billing/seats/runs${tenantId ? `?tenant_id=${tenantId}` : ""}`, {
        cache: "no-store",
        signal: AbortSignal.timeout(10_000),
        headers: await authHeader(),
      })
    } catch {
      throw new BillingUnavailableError()
    }
    if (res.status === 502 || res.status === 503 || res.status === 504) throw new BillingUnavailableError()
    if (!res.ok) throw new AdminApiError(res.status, await res.text().catch(() => ""))
    return res.json()
  },
}

