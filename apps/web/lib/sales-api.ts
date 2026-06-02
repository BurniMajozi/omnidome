"use client"

/**
 * Sales API client — pipeline, deals, and deal stage management.
 * Proxies through the Next.js API routes to the sales service (port 8002).
 */

const SALES_API = "/api/sales"

async function fetchSales<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${SALES_API}${path}`, {
    cache: "no-store",
    headers: { "Content-Type": "application/json" },
    ...init,
  })
  if (!res.ok) {
    const body = await res.text().catch(() => "")
    throw new Error(`Sales API error ${res.status}: ${body}`)
  }
  return res.json()
}

// ── Types ─────────────────────────────────────────────────────────────

export interface PipelineStage {
  id: string
  name: string
  probability: number
  sort_order: number
}

export interface PipelineOverviewStage extends PipelineStage {
  deal_count: number
  total_value_zar: number
}

export interface Deal {
  id: string
  tenant_id: string
  customer_id: string
  lead_id?: string
  agent_id?: string
  stage_id: string
  stage_name: string
  package_id?: string
  value_zar: number
  status: string
  close_date?: string
  closed_at?: string
  close_reason?: string
  notes?: string
  created_at: string
  updated_at?: string
}

export interface DealCreate {
  name: string
  customer_id: string
  lead_id?: string
  agent_id?: string
  stage_id?: string
  stage_name?: string
  package_id?: string
  value_zar: number
  close_date?: string
  notes?: string
}

export interface DealStageUpdate {
  stage_id?: string
  stage_name?: string
  direction?: "next" | "previous"
}

// ── API methods ──────────────────────────────────────────────────────

export const salesApi = {
  // Pipeline
  getPipelineOverview: () =>
    fetchSales<PipelineOverviewStage[]>("/pipeline"),

  getPipelineStages: () =>
    fetchSales<PipelineStage[]>("/pipeline/stages"),

  createStage: (data: { name: string; probability?: number; sort_order?: number }) =>
    fetchSales<PipelineStage>("/pipeline/stages", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  // Deals
  listDeals: (params?: { stage_id?: string; stage?: string; agent_id?: string; status?: string }) => {
    const q = new URLSearchParams()
    if (params?.stage_id) q.set("stage_id", params.stage_id)
    if (params?.stage) q.set("stage", params.stage)
    if (params?.agent_id) q.set("agent_id", params.agent_id)
    if (params?.status) q.set("status", params.status)
    return fetchSales<Deal[]>(`/deals?${q}`)
  },

  createDeal: (data: DealCreate) =>
    fetchSales<Deal>("/deals", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  updateDeal: (dealId: string, data: Partial<DealCreate>) =>
    fetchSales<Deal>(`/deals/${dealId}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  moveDealStage: (dealId: string, data: DealStageUpdate) =>
    fetchSales<Deal>(`/deals/${dealId}/stage`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  closeDealWon: (dealId: string) =>
    fetchSales<Deal>(`/deals/${dealId}/close-won`, { method: "POST" }),

  closeDealLost: (dealId: string, reason: string) =>
    fetchSales<Deal>(`/deals/${dealId}/close-lost?reason=${encodeURIComponent(reason)}`, {
      method: "POST",
    }),
}
