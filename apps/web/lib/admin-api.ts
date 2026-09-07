"use client"

/**
 * Admin API client - commission tiers, user management, audit log.
 * Proxies through the Next.js API routes to the admin service (port 8013).
 */

const ADMIN_API = "/api/admin"

async function fetchAdmin<T>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  }

  // Attempt to attach Supabase session token if available
  try {
    const { supabase } = await import("@/lib/supabase/client")
    if (supabase) {
      const { data } = await supabase.auth.getSession()
      if (data.session?.access_token) {
        headers["Authorization"] = `Bearer ${data.session.access_token}`
      }
    }
  } catch {
    // Supabase browser client optional in dev/fallback mode
  }

  const res = await fetch(`${ADMIN_API}${path}`, {
    cache: "no-store",
    headers: {
      ...headers,
      ...init?.headers,
    },
    ...init,
  })
  if (!res.ok) {
    const body = await res.text().catch(() => "")
    throw new Error(`Admin API error ${res.status}: ${body}`)
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
}

