/**
 * OmniDome Customer Lifecycle API client.
 */

import { detailMessage } from "@/lib/crm-derive"

const LIFECYCLE_API = "/api/lifecycle"

/**
 * Identity: the lifecycle service takes the tenant ONLY from the signed
 * identity the edge gate injects. This client therefore sends no tenant_id
 * (a differing one is a 403 server-side). Errors carry the HTTP `status` so the
 * UI can tell "service not running" from "not permitted" from "empty".
 */
export class LifecycleApiError extends Error {
  status: number | null
  constructor(message: string, status: number | null) {
    super(message)
    this.name = "LifecycleApiError"
    this.status = status
  }
}

async function fetchLifecycle<T>(path: string, options?: RequestInit): Promise<T> {
  const url = `${LIFECYCLE_API}${path}`
  let res: Response
  try {
    res = await fetch(url, {
      ...options,
      headers: { "Content-Type": "application/json", ...options?.headers },
      cache: "no-store",
      signal: options?.signal ?? AbortSignal.timeout(15_000),
    })
  } catch {
    throw new LifecycleApiError("Lifecycle service did not respond", null)
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({}) as Record<string, unknown>)
    const detail = detailMessage(err)
    throw new LifecycleApiError(detail || `Lifecycle API error: ${res.status}`, res.status)
  }
  if (res.status === 204) return null as T
  try {
    return await res.json()
  } catch {
    throw new LifecycleApiError("Lifecycle service returned an invalid response", res.status)
  }
}

export interface LifecycleStage {
  id: string
  name: string
  category: string
  color: string
  sort_order: number
  is_default: boolean
}

export interface LifecycleEvent {
  id: string
  customer_id: string
  from_stage?: string
  to_stage: string
  trigger_source: string
  trigger_id?: string
  reason?: string
  metadata?: Record<string, any>
  created_at?: string
}

export interface CustomerLifecycle {
  id: string
  customer_id: string
  current_stage: string
  is_at_risk: boolean
  health_score: number
  churn_probability?: number | null
  risk_reason?: string
  monthly_recurring_revenue: number
  current_plan?: string
  originating_deal_id?: string
  originating_lead_id?: string
  assigned_sales_agent_id?: string
  converted_at?: string
  churned_at?: string
  updated_at?: string
}

export interface DashboardData {
  stages: Record<string, { count: number; mrr: number; avg_health: number }>
  risk: { at_risk_count: number; avg_churn_probability: number }
  revenue: { total_mrr: number; active_customers: number }
  recent_events: LifecycleEvent[]
}

export interface FunnelData {
  /** `customers` = distinct customers per stage (server-side); `entries` = transition events. */
  funnel: { stage: string; entries: number; customers?: number }[]
}

export const lifecycleApi = {
  // Stages. ensureStages creates defaults and is a WRITE: call it once, only
  // when listStages returns nothing and the caller is admin tier.
  ensureStages: () =>
    fetchLifecycle<{ stages: LifecycleStage[]; message: string }>(`/lifecycle/stages`, { method: "POST" }),
  listStages: () => fetchLifecycle<{ stages: LifecycleStage[] }>(`/lifecycle/stages`),

  // Transitions
  transition: (data: {
    customer_id: string
    to_stage: string
    reason?: string
    trigger_source?: string
    trigger_id?: string
  }) =>
    fetchLifecycle(`/lifecycle/transition`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  listEvents: (customerId?: string, limit?: number) => {
    const qs = new URLSearchParams()
    if (customerId) qs.set("customer_id", customerId)
    qs.set("limit", String(limit || 50))
    return fetchLifecycle<{ events: LifecycleEvent[] }>(`/lifecycle/events?${qs}`)
  },

  // Customer lifecycle
  getCustomerLifecycle: (customerId: string) =>
    fetchLifecycle<{ lifecycle: CustomerLifecycle | null }>(`/lifecycle/customer/${encodeURIComponent(customerId)}`),
  listLifecycles: (params?: {
    stage?: string
    is_at_risk?: boolean
    page?: number
    page_size?: number
  }) => {
    const qs = new URLSearchParams()
    if (params?.stage) qs.set("stage", params.stage)
    if (params?.is_at_risk !== undefined) qs.set("is_at_risk", String(params.is_at_risk))
    if (params?.page) qs.set("page", String(params.page))
    if (params?.page_size) qs.set("page_size", String(params.page_size))
    const q = qs.toString()
    return fetchLifecycle<{ lifecycles: CustomerLifecycle[]; total: number }>(`/lifecycle/customers${q ? `?${q}` : ""}`)
  },

  // Dashboard
  getDashboard: (days?: number) => fetchLifecycle<DashboardData>(`/lifecycle/dashboard?days=${days || 30}`),
  getFunnel: (days?: number) => fetchLifecycle<FunnelData>(`/lifecycle/funnel?days=${days || 30}`),

  // Bridges (called by other services; tenant comes from the signed identity)
  recordSale: (data: {
    customer_id: string; deal_id: string
    agent_id?: string; plan?: string; monthly_recurring_revenue?: number; lead_id?: string
  }) =>
    fetchLifecycle(`/lifecycle/from-sale`, { method: "POST", body: JSON.stringify(data) }),
  recordJourneyOutcome: (data: {
    customer_id: string; cancel_event_id: string
    outcome: string; journey_id?: string; offer_id?: string; reason?: string
  }) =>
    fetchLifecycle(`/lifecycle/from-journey`, { method: "POST", body: JSON.stringify(data) }),

  // Context
  getContext: (customerId: string) =>
    fetchLifecycle<{
      lifecycle: CustomerLifecycle | null
      recent_events: LifecycleEvent[]
      available_stages: LifecycleStage[]
    }>(`/lifecycle/context/${encodeURIComponent(customerId)}`),
}
