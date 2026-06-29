"use client"

import { supabase } from "@/lib/supabase/client"

/**
 * Products API client — billing plan catalog (Fibre/LTE/VoIP/TV) and
 * multi-plan bundles. Proxies through the Next.js API routes to the
 * billing service, which owns billing_plans/bundles and aggregates
 * subscriber counts + MRR from live subscriptions.
 */

const API_BASE = "/svc/billing"
const FALLBACK_TENANT_ID = "00000000-0000-0000-0000-000000000001"
const FALLBACK_USER_ID = "00000000-0000-0000-0000-000000000001"

async function getAuthHeaders(): Promise<Record<string, string>> {
  const { data } = await supabase.auth.getSession()
  const tenantId =
    data.session?.user?.user_metadata?.tenant_id ??
    data.session?.user?.app_metadata?.tenant_id ??
    FALLBACK_TENANT_ID
  const userId = data.session?.user?.id ?? FALLBACK_USER_ID
  return { "x-tenant-id": tenantId, "x-user-id": userId }
}

async function fetchBilling<T>(path: string, init?: RequestInit): Promise<T | null> {
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      cache: "no-store",
      headers: { ...(await getAuthHeaders()), "Content-Type": "application/json" },
      ...init,
    })
    if (!res.ok) {
      console.warn(`Billing API error ${res.status} for ${path}`)
      return null
    }
    return res.json()
  } catch (error) {
    console.warn(`Billing API unreachable for ${path}`, error)
    return null
  }
}

export interface Plan {
  id: string
  name: string
  category: string | null
  price: number
  currency: string
  billing_cycle: string
  fno_provider: string | null
  is_active: boolean
  subscribers: number
  mrr: number
}

export interface PlanCreate {
  name: string
  category?: string
  price: number
  fno_provider?: string
}

export interface Bundle {
  id: string
  name: string
  discount_pct: number
  products: string[]
  price: number
  subscribers: number
}

export interface BundleCreate {
  name: string
  discount_pct: number
  plan_ids: string[]
}

export const listPlans = () => fetchBilling<Plan[]>("/plans").then((r) => r ?? [])
export const createPlan = (data: PlanCreate) => fetchBilling<Plan>("/plans", { method: "POST", body: JSON.stringify(data) })

export const listBundles = () => fetchBilling<Bundle[]>("/bundles").then((r) => r ?? [])
export const createBundle = (data: BundleCreate) => fetchBilling<Bundle>("/bundles", { method: "POST", body: JSON.stringify(data) })
