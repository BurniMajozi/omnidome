"use client"

/**
 * Sales API client — pipeline, deals, and deal stage management.
 * Proxies through the Next.js API routes to the sales service (port 8002).
 */

const SALES_API = "/api/sales"

async function fetchSales<T>(path: string, init?: RequestInit): Promise<T> {
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
    // Supabase browser client optional
  }

  const res = await fetch(`${SALES_API}${path}`, {
    cache: "no-store",
    headers: {
      ...headers,
      ...init?.headers,
    },
    ...init,
  })
  if (!res.ok) {
    const body = await res.text().catch(() => "")
    throw new Error(`Sales API error ${res.status}: ${body}`)
  }
  return res.json()
}

// ── Types ─────────────────────────────────────────────────────────────

export type SalesChannel =
  | "INBOUND_EMAIL"
  | "CALL_CENTER_INBOUND"
  | "CALL_CENTER_OUTBOUND"
  | "PORTAL_WEBSITE"
  | "FIELD_SALES"
  | "WALK_IN"
  | "REFERRAL"
  | "OTHER"

export const SALES_CHANNELS: { id: SalesChannel; label: string; description: string; icon: string; color: string }[] = [
  { id: "INBOUND_EMAIL", label: "Inbound Email", description: "Email inquiries & quote requests", icon: "Mail", color: "#60a5fa" },
  { id: "CALL_CENTER_INBOUND", label: "Call Center Inbound", description: "Toll-free customer hotline calls", icon: "PhoneCall", color: "#34d399" },
  { id: "CALL_CENTER_OUTBOUND", label: "Call Center Outbound", description: "Telesales campaigns & cold calls", icon: "PhoneOutgoing", color: "#fbbf24" },
  { id: "PORTAL_WEBSITE", label: "Portal & Website", description: "Online customer self-service applications", icon: "Globe", color: "#a78bfa" },
  { id: "FIELD_SALES", label: "Field Sales Team", description: "On-site visits & regional agents", icon: "MapPin", color: "#f87171" },
  { id: "WALK_IN", label: "Walk-in Customers", description: "Branch & retail customer work-ins", icon: "Store", color: "#38bdf8" },
  { id: "REFERRAL", label: "Partner Referral", description: "Affiliate & partner networks", icon: "Users", color: "#ec4899" },
]

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
  name: string
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

export interface SalesLead {
  id: string
  tenant_id: string
  contact_id?: string | null
  agent_id?: string | null
  first_name: string
  last_name: string
  email?: string | null
  phone?: string | null
  address?: string | null
  source: string // Maps to channel e.g. INBOUND_EMAIL, WALK_IN, PORTAL_WEBSITE
  interest_level: number
  status: string // "NEW" | "CONTACTED" | "QUALIFIED" | "PROPOSAL" | "NEGOTIATION" | "CONVERTED" | "LOST"
  notes?: string | null
  converted_at?: string | null
  created_at: string
  updated_at?: string | null
}

export interface SalesLeadCreate {
  first_name: string
  last_name: string
  email?: string
  phone?: string
  address?: string
  source: string
  interest_level?: number
  notes?: string
  agent_id?: string
}

export interface SalesLeadUpdate {
  first_name?: string
  last_name?: string
  email?: string
  phone?: string
  address?: string
  source?: string
  interest_level?: number
  status?: string
  notes?: string
  agent_id?: string
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

  // Leads
  listLeads: (params?: { status?: string; source?: string; limit?: number }) => {
    const q = new URLSearchParams()
    if (params?.status) q.set("status", params.status)
    if (params?.source) q.set("source", params.source)
    if (params?.limit) q.set("limit", String(params.limit))
    return fetchSales<SalesLead[]>(`/leads?${q}`)
  },

  createLead: (data: SalesLeadCreate) =>
    fetchSales<SalesLead>("/leads", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  updateLead: (leadId: string, data: SalesLeadUpdate) =>
    fetchSales<SalesLead>(`/leads/${leadId}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  convertLead: (leadId: string, data: { name?: string; value_zar: number; agent_id?: string }) =>
    fetchSales<{ id: string; message: string; deal_id?: string }>(`/leads/${leadId}/convert`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
}
