/**
 * OmniDome Customer Lifecycle API client.
 */

const LIFECYCLE_API = "/api/lifecycle"

async function fetchLifecycle<T>(path: string, options?: RequestInit): Promise<T> {
  const url = `${LIFECYCLE_API}${path}`
  const res = await fetch(url, {
    ...options,
    headers: { "Content-Type": "application/json", ...options?.headers },
    cache: "no-store",
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: res.statusText }))
    throw new Error(err.error || `Lifecycle API error: ${res.status}`)
  }
  return res.json()
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
  churn_probability?: number
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
  funnel: { stage: string; entries: number }[]
}

export const lifecycleApi = {
  // Stages
  ensureStages: (tenantId: string) =>
    fetchLifecycle<{ stages: LifecycleStage[]; message: string }>(
      `/lifecycle/stages?tenant_id=${tenantId}`,
      { method: "POST" }
    ),
  listStages: (tenantId: string) =>
    fetchLifecycle<{ stages: LifecycleStage[] }>(
      `/lifecycle/stages?tenant_id=${tenantId}`
    ),

  // Transitions
  transition: (tenantId: string, data: {
    customer_id: string
    to_stage: string
    reason?: string
    trigger_source?: string
    trigger_id?: string
  }) =>
    fetchLifecycle(`/lifecycle/transition?tenant_id=${tenantId}`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  listEvents: (tenantId: string, customerId?: string, limit?: number) =>
    fetchLifecycle<{ events: LifecycleEvent[] }>(
      `/lifecycle/events?tenant_id=${tenantId}${customerId ? `&customer_id=${customerId}` : ""}&limit=${limit || 50}`
    ),

  // Customer lifecycle
  getCustomerLifecycle: (customerId: string, tenantId: string) =>
    fetchLifecycle<{ lifecycle: CustomerLifecycle | null }>(
      `/lifecycle/customer/${customerId}?tenant_id=${tenantId}`
    ),
  listLifecycles: (tenantId: string, params?: {
    stage?: string
    is_at_risk?: boolean
    page?: number
    page_size?: number
  }) => {
    const qs = new URLSearchParams({ tenant_id: tenantId })
    if (params?.stage) qs.set("stage", params.stage)
    if (params?.is_at_risk !== undefined) qs.set("is_at_risk", String(params.is_at_risk))
    if (params?.page) qs.set("page", String(params.page))
    if (params?.page_size) qs.set("page_size", String(params.page_size))
    return fetchLifecycle<{ lifecycles: CustomerLifecycle[]; total: number }>(
      `/lifecycle/customers?${qs}`
    )
  },

  // Dashboard
  getDashboard: (tenantId: string, days?: number) =>
    fetchLifecycle<DashboardData>(`/lifecycle/dashboard?tenant_id=${tenantId}&days=${days || 30}`),
  getFunnel: (tenantId: string, days?: number) =>
    fetchLifecycle<FunnelData>(`/lifecycle/funnel?tenant_id=${tenantId}&days=${days || 30}`),

  // Bridges (called by other services)
  recordSale: (data: {
    tenant_id: string; customer_id: string; deal_id: string
    agent_id?: string; plan?: string; monthly_recurring_revenue?: number; lead_id?: string
  }) =>
    fetchLifecycle(`/lifecycle/from-sale`, { method: "POST", body: JSON.stringify(data) }),
  recordJourneyOutcome: (data: {
    tenant_id: string; customer_id: string; cancel_event_id: string
    outcome: string; journey_id?: string; offer_id?: string; reason?: string
  }) =>
    fetchLifecycle(`/lifecycle/from-journey`, { method: "POST", body: JSON.stringify(data) }),

  // Context
  getContext: (customerId: string, tenantId: string) =>
    fetchLifecycle<{
      lifecycle: CustomerLifecycle | null
      recent_events: LifecycleEvent[]
      available_stages: LifecycleStage[]
    }>(`/lifecycle/context/${customerId}?tenant_id=${tenantId}`),
}
