"use client"

/**
 * Admin API client — commission tiers, user management, audit log.
 * Proxies through the Next.js API routes to the admin service (port 8013).
 */

const ADMIN_API = "/api/admin"

async function fetchAdmin<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${ADMIN_API}${path}`, {
    cache: "no-store",
    headers: { "Content-Type": "application/json" },
    ...init,
  })
  if (!res.ok) {
    const body = await res.text().catch(() => "")
    throw new Error(`Admin API error ${res.status}: ${body}`)
  }
  return res.json()
}

// ── Types ─────────────────────────────────────────────────────────────

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

// ── API methods ──────────────────────────────────────────────────────

export const adminApi = {
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
}
