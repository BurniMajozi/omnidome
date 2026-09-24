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
    const { getSessionSafe } = await import("@/lib/supabase/client")
    const { data } = await getSessionSafe()
    if (data.session?.access_token) {
      headers["Authorization"] = `Bearer ${data.session.access_token}`
    }
  } catch {
    // Supabase browser client optional
  }

  const res = await fetch(`${SALES_API}${path}`, {
    cache: "no-store",
    // Without a timeout, a stuck/unreachable sales service leaves this
    // pending forever -- the pipeline board's individual .catch(() => [])
    // calls never fire, so loading never clears ("Loading pipeline..."
    // stuck permanently instead of degrading to an empty/error state).
    signal: AbortSignal.timeout(15000),
    headers: {
      ...headers,
      ...init?.headers,
    },
    ...init,
  })
  if (!res.ok) {
    const body = await res.text().catch(() => "")
    throw new SalesApiError(res.status, body)
  }
  return res.json()
}

/** Error carrying the service's own message (FastAPI `detail`), for the UI. */
export class SalesApiError extends Error {
  status: number
  constructor(status: number, body: string) {
    let detail = body
    try {
      const parsed = JSON.parse(body)
      if (typeof parsed?.detail === "string") detail = parsed.detail
    } catch {
      /* not JSON */
    }
    super(detail || `Sales API error ${status}`)
    this.status = status
  }
}

export function salesErrorMessage(err: unknown, fallback = "Something went wrong"): string {
  return err instanceof Error && err.message ? err.message : fallback
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
  | "MARKETING"
  | "COMPANY_SEARCH"
  | "TENDER"
  | "OTHER"

export const SALES_CHANNELS: { id: SalesChannel; label: string; description: string; icon: string; color: string }[] = [
  { id: "MARKETING", label: "Marketing Campaigns", description: "Campaign lead forms, social ads & marketing funnels", icon: "Megaphone", color: "#e03131" },
  { id: "INBOUND_EMAIL", label: "Inbound Email", description: "Email inquiries & quote requests", icon: "Mail", color: "#60a5fa" },
  { id: "CALL_CENTER_INBOUND", label: "Call Center Inbound", description: "Toll-free customer hotline calls", icon: "PhoneCall", color: "#34d399" },
  { id: "CALL_CENTER_OUTBOUND", label: "Call Center Outbound", description: "Telesales campaigns & cold calls", icon: "PhoneOutgoing", color: "#fbbf24" },
  { id: "PORTAL_WEBSITE", label: "Portal & Website", description: "Online customer self-service applications", icon: "Globe", color: "#a78bfa" },
  { id: "FIELD_SALES", label: "Field Sales Team", description: "On-site visits & regional agents", icon: "MapPin", color: "#f87171" },
  { id: "WALK_IN", label: "Walk-in Customers", description: "Branch & retail customer work-ins", icon: "Store", color: "#38bdf8" },
  { id: "REFERRAL", label: "Partner Referral", description: "Affiliate & partner networks", icon: "Users", color: "#ec4899" },
  { id: "COMPANY_SEARCH", label: "Company Search", description: "Businesses found by area in Lead sources", icon: "Building2", color: "#14b8a6" },
  { id: "TENDER", label: "Tenders & RFQs", description: "Public tenders and RFQs tracked in Lead sources", icon: "FileText", color: "#f59e0b" },
]

export interface ProductPackage {
  id: string
  name: string
  category: "Fiber" | "Broadband" | "Voice" | "Cloud" | "Enterprise"
  speed?: string
  price_monthly: number
  description: string
}

export const PRODUCT_CATALOG: ProductPackage[] = [
  { id: "BF-200", name: "Business Fiber 200Mbps", category: "Fiber", speed: "200/200 Mbps", price_monthly: 1899, description: "Symmetric business uncapped fiber with 99.5% uptime SLA" },
  { id: "BF-500", name: "Business Fiber 500Mbps", category: "Fiber", speed: "500/500 Mbps", price_monthly: 2999, description: "High-capacity symmetric fiber with static IP & prioritized routing" },
  { id: "ENT-1G", name: "Enterprise Dedicated 1Gbps", category: "Enterprise", speed: "1 Gbps Dedicated", price_monthly: 7500, description: "1:1 Dedicated leased line, 99.9% SLA, BGP peering, 4-hour MTTR" },
  { id: "HB-100", name: "Home Broadband 100Mbps", category: "Broadband", speed: "100/100 Mbps", price_monthly: 899, description: "Uncapped, unshaped residential fiber with premium Wi-Fi 6 router" },
  { id: "HB-200", name: "Home Broadband 200Mbps", category: "Broadband", speed: "200/200 Mbps", price_monthly: 1199, description: "High-speed family streaming & gaming fiber with zero throttling" },
  { id: "PBX-10", name: "Hosted PBX & VoIP Trunk (10-Seat)", category: "Voice", speed: "Voice", price_monthly: 1450, description: "Cloud telephone switchboard, 10 geographic SIP trunks, call recording" },
  { id: "VDC-STD", name: "Cloud Virtual Data Center & Backup", category: "Cloud", speed: "Cloud", price_monthly: 3200, description: "Automated off-site backup, disaster recovery, Veeam integration" },
  { id: "SDWAN-5", name: "SD-WAN Multi-Branch Secure Network", category: "Enterprise", speed: "SD-WAN", price_monthly: 5800, description: "Automated multi-branch WAN path selection with Fortinet firewall" },
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
  lead_reference?: string | null
  owner_name?: string | null
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
  /** Lead phase: NEW | CONTACTED | QUALIFIED | DISQUALIFIED. With a deal it mirrors
   *  the deal: CONVERTED (open, "In pipeline") | WON | LOST. SPEC-lead-lifecycle.md */
  status: string
  notes?: string | null
  converted_at?: string | null
  created_at: string
  updated_at?: string | null
  reference?: string | null
  owner_id?: string | null
  owner_name?: string | null
  priority?: LeadPriority
  closed_at?: string | null
  close_reason?: string | null
  escalated_at?: string | null
  deal_id?: string | null
  deal_stage?: string | null
  deal_status?: string | null
  deal_value_zar?: number | null
  open_tasks?: number
}

export type LeadPriority = "low" | "normal" | "high" | "urgent"

export const LEAD_PHASE_STAGES = [
  { id: "NEW", label: "New" },
  { id: "CONTACTED", label: "Contacted" },
  { id: "QUALIFIED", label: "Qualified" },
  { id: "DISQUALIFIED", label: "Disqualified" },
] as const

export const LEAD_STATUS_LABELS: Record<string, string> = {
  NEW: "New",
  CONTACTED: "Contacted",
  QUALIFIED: "Qualified",
  DISQUALIFIED: "Disqualified",
  CONVERTED: "In pipeline",
  WON: "Won",
  LOST: "Lost",
}

export interface PipelinePlacement {
  stage_name?: string
  value_zar?: number
  deal_name?: string
}

export interface LeadStageChange {
  status?: string
  stage_name?: string
  value_zar?: number
  deal_name?: string
  reason?: string
}

export interface LeadActivity {
  id: string
  kind: string
  summary: string
  details: Record<string, unknown>
  actor_id?: string | null
  actor_name?: string | null
  created_at: string
}

export interface LeadTask {
  id: string
  lead_id: string
  title: string
  kind: string
  due_at?: string | null
  assignee_id?: string | null
  assignee_name?: string | null
  status: "open" | "done" | string
  created_at: string
  completed_at?: string | null
}

export interface SalesLeadDetail extends SalesLead {
  activities: LeadActivity[]
  tasks: LeadTask[]
}

export interface LeadOwner {
  id: string
  name: string
  department?: string | null
  job_title?: string | null
  email?: string | null
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
  owner_id?: string
  owner_name?: string
  priority?: LeadPriority
  /** Put the lead straight onto the pipeline board. */
  pipeline?: PipelinePlacement
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

  getLead: (leadId: string) => fetchSales<SalesLeadDetail>(`/leads/${leadId}`),

  /** One stage model with the board: a lead-phase `status` or a board `stage_name`. */
  changeLeadStage: (leadId: string, data: LeadStageChange) =>
    fetchSales<SalesLead>(`/leads/${leadId}/stage`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  listOwners: () => fetchSales<LeadOwner[]>("/owners"),
}
