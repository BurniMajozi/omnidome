"use client"

/**
 * Mobile Field Sales API client.
 * Aggregates data from CRM, Sales, Billing, Inventory, Communication services.
 */

const API = "/api"

async function fetchJSON<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    cache: "no-store",
    headers: { "Content-Type": "application/json" },
    ...init,
  })
  if (!res.ok) {
    const body = await res.text().catch(() => "")
    throw new Error(`API error ${res.status}: ${body}`)
  }
  return res.json()
}

// ── Types ─────────────────────────────────────────────────────────────

export interface MobileContact {
  id: string
  first_name: string
  last_name: string
  email: string
  phone: string
  physical_address: string
  rica_verified: boolean
  status?: string
}

export interface MobileDeal {
  id: string
  name: string
  customer_id: string
  stage_name: string
  value_zar: number
  status: string
  close_date?: string
  created_at: string
}

export interface MobileLead {
  id: string
  first_name: string
  last_name: string
  email: string
  phone: string
  source: string
  status: string
  interest_level: number
  address: string
}

export interface MobileQuote {
  id: string
  deal_id?: string
  customer_id: string
  total_monthly: number
  total_once_off: number
  status: string
  valid_until?: string
  created_at: string
}

export interface MobileInvoice {
  id: string
  invoice_number: string
  amount: number
  total_amount: number
  status: string
  due_date: string
}

export interface MobileCommission {
  id: string
  deal_id: string
  amount_zar: number
  rate_percent: number
  status: string
  created_at: string
}

export interface Customer360 {
  contact: MobileContact
  deals: MobileDeal[]
  quotes: MobileQuote[]
  invoices: MobileInvoice[]
  total_revenue: number
  open_deals_value: number
}

// ── API methods ──────────────────────────────────────────────────────

export const fieldSalesApi = {
  // Leads
  listLeads: (params?: { status?: string; limit?: number }) => {
    const q = new URLSearchParams()
    if (params?.status) q.set("status", params.status)
    if (params?.limit) q.set("limit", String(params.limit))
    return fetchJSON<MobileLead[]>(`/sales/leads?${q}`)
  },

  createLead: (data: Partial<MobileLead>) =>
    fetchJSON<MobileLead>("/sales/leads", { method: "POST", body: JSON.stringify(data) }),

  updateLead: (id: string, data: Partial<MobileLead>) =>
    fetchJSON<MobileLead>(`/sales/leads/${id}`, { method: "PUT", body: JSON.stringify(data) }),

  convertLead: (leadId: string, data: { name: string; value_zar: number; agent_id?: string }) =>
    fetchJSON<{ deal_id: string }>(`/sales/leads/${leadId}/convert`, { method: "POST", body: JSON.stringify(data) }),

  // Contacts / Customers
  listContacts: (params?: { search?: string; limit?: number }) => {
    const q = new URLSearchParams()
    if (params?.search) q.set("search", params.search)
    if (params?.limit) q.set("limit", String(params.limit))
    return fetchJSON<MobileContact[]>(`/sales/contacts?${q}`)
  },

  getContact: (id: string) =>
    fetchJSON<MobileContact>(`/sales/contacts/${id}`),

  getCustomer360: (contactId: string) =>
    fetchJSON<Customer360>(`/sales/contacts/${contactId}/360`),

  // Deals
  listDeals: (params?: { status?: string; agent_id?: string; limit?: number }) => {
    const q = new URLSearchParams()
    if (params?.status) q.set("status", params.status)
    if (params?.agent_id) q.set("agent_id", params.agent_id)
    if (params?.limit) q.set("limit", String(params.limit))
    return fetchJSON<MobileDeal[]>(`/sales/deals?${q}`)
  },

  createDeal: (data: { name: string; customer_id: string; value_zar: number; stage_id?: string }) =>
    fetchJSON<MobileDeal>("/sales/deals", { method: "POST", body: JSON.stringify(data) }),

  // Quotes
  listQuotes: (params?: { status?: string; customer_id?: string }) => {
    const q = new URLSearchParams()
    if (params?.status) q.set("status", params.status)
    if (params?.customer_id) q.set("customer_id", params.customer_id)
    return fetchJSON<MobileQuote[]>(`/sales/quotes?${q}`)
  },

  createQuote: (data: { customer_id: string; deal_id?: string; items: Array<{ product_id: string; name: string; monthly_price: number; qty: number }>; term_months?: number }) =>
    fetchJSON<MobileQuote>("/sales/quotes", { method: "POST", body: JSON.stringify(data) }),

  // Commissions
  getMyCommissions: () =>
    fetchJSON<MobileCommission[]>(`/sales/commissions`),

  // Products (for quote builder)
  listProducts: () =>
    fetchJSON<Array<{ id: string; name: string; monthly_price: number; setup_fee: number; fno_type: string }>>(`/inventory/products`),

  // Invoices (customer billing summary)
  getCustomerInvoices: (contactId: string) =>
    fetchJSON<MobileInvoice[]>(`/billing/invoices?customer_id=${contactId}`),
}
