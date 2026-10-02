"use client"

import { getSessionSafe } from "@/lib/supabase/client"
import { createTtlCache } from "@/lib/request-cache"
import { fetchLoadable } from "@/lib/service-fetch"
import { mapCrmError, type CrmError } from "@/lib/crm-derive"
import type { Loadable } from "@/lib/service-state"

/**
 * CRM API client — customers, leads, companies, 360 view, activities,
 * tasks, and rule-based insights. Proxies through the Next.js API route
 * (/svc/crm) to the CRM service.
 *
 * Identity: the edge gate (proxy.ts) derives tenant and user from the verified
 * session and strips any client-supplied x-tenant-id / x-user-id, so this
 * client sends NONE (no dev-tenant fallbacks). The Bearer token is attached by
 * AuthFetchInit.
 *
 * Reads return a Loadable (status preserved: unreachable / denied / error).
 * Writes return a CrmResult so the UI can show the server's message verbatim.
 */

const API_BASE = "/svc/crm"
const REQUEST_TIMEOUT_MS = 15_000

export type CrmResult<T> = { ok: true; data: T; status: number } | { ok: false; error: CrmError }

async function crmWrite<T>(path: string, init: { method: string; body?: unknown }): Promise<CrmResult<T>> {
  let res: Response
  try {
    // getSessionSafe warms/validates the session so a stale token fails fast.
    await getSessionSafe()
    res = await fetch(`${API_BASE}${path}`, {
      method: init.method,
      cache: "no-store",
      headers: { "Content-Type": "application/json" },
      body: init.body === undefined ? undefined : JSON.stringify(init.body),
      signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    })
  } catch {
    return { ok: false, error: mapCrmError(null, null) }
  }
  let body: unknown = null
  const text = await res.text().catch(() => "")
  if (text) {
    try {
      body = JSON.parse(text)
    } catch {
      body = text
    }
  }
  if (!res.ok) return { ok: false, error: mapCrmError(res.status, body) }
  if (res.status !== 204 && (!body || typeof body !== "object")) {
    return { ok: false, error: { kind: "error", status: res.status, message: "CRM returned an invalid response. Refresh the record before retrying." } }
  }
  invalidateCrmReads()
  return { ok: true, data: body as T, status: res.status }
}

/** Short-lived in-flight dedupe for the dashboard's initial reads. */
const readCache = createTtlCache(5_000)
function cachedRead<T>(path: string, force = false): Promise<Loadable<T>> {
  if (force) readCache.invalidate(path)
  return readCache.get(path, () => fetchLoadable<T>(`${API_BASE}${path}`, REQUEST_TIMEOUT_MS), (r) => r.state === "ready")
}
/** Drop cached reads after a successful write so lists refetch fresh data. */
export function invalidateCrmReads(): void {
  readCache.invalidate()
}

let rolesPromise: Promise<string[] | null> | null = null
/** Verified roles from the edge gate; null when unknown (the server still enforces). */
export function getMyRoles(): Promise<string[] | null> {
  if (!rolesPromise) {
    rolesPromise = fetch("/api/whoami", { cache: "no-store", signal: AbortSignal.timeout(8_000) })
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => (Array.isArray(j?.roles) ? (j.roles as string[]) : null))
      .catch(() => {
        rolesPromise = null
        return null
      })
  }
  return rolesPromise
}

// ── Types ─────────────────────────────────────────────────────────────

export interface DashboardSummary {
  totalCustomers: number
  activeLeads: number
  conversionRate: number
  avgRevenuePerCustomer: number
  /** Added by the CRM service: lead cohort counts (statuses upper-case; WON counts as converted). */
  won_from_leads?: number
  active_customers?: number
  convertedLeads?: number
  totalLeads?: number
  leadStatusCounts?: Record<string, number>
  customerData: { month: string; customers: number; churn: number }[]
  leadData: { week: string; leads: number; converted: number }[]
  flashcardKPIs: {
    id: string
    title: string
    value: string
    change: string
    changeType: "positive" | "negative" | "neutral"
    iconKey: string
    backTitle: string
    backDetails: { label: string; value: string }[]
    backInsight: string
  }[]
}

export interface Activity {
  id: string
  user: string
  action: string
  target: string
  time: string
  type: "create" | "update" | "assign" | "comment"
}

export interface CrmTask {
  id: string
  title: string
  priority: string
  status: string
  dueDate: string
  assignee: string
}

export interface AiRecommendation {
  id: string
  title: string
  description: string
  impact: "high" | "medium" | "low"
  category: string
}

export interface Issue {
  id: string
  title: string
  severity: "high" | "medium" | "low" | "critical"
  status: "open" | "in-progress" | "resolved"
  assignee: string
  time: string
}

export interface CustomerListItem {
  id: string
  first_name: string
  last_name: string
  email: string | null
  phone?: string | null
  address?: string | null
  province?: string | null
  status: string
  account_number: string | null
  rica_verified?: boolean
  company_id?: string | null
  company_role?: string | null
  created_at: string
  mrr: number | null
  customer_type: string | null
  health: string
}

export interface Customer360Data {
  id: string
  first_name: string
  last_name: string
  email: string | null
  phone?: string | null
  /** Masked (*********1234) for non-admins; show as is, never try to unmask. */
  id_number?: string | null
  address?: string | null
  province?: string | null
  account_number?: string | null
  status: string
  rica_verified: boolean
  company_id?: string | null
  created_at: string
  updated_at: string
  services?: any[]
  billing?: any[]
  support?: any[]
  network?: any[]
  tags?: string[]
  notes_count?: number
  lifecycle_data?: any
  /** True when one or more sections could not be built; see section_errors. */
  partial?: boolean
  section_errors?: Record<string, string> | string[]
}

export interface LeadItem {
  id: string
  tenant_id: string
  source: string | null
  first_name: string
  last_name: string
  email: string | null
  phone: string | null
  coverage_area: string | null
  interested_package: string | null
  status: string
  assigned_to: string | null
  notes: string | null
  converted_customer_id: string | null
  created_at: string
  updated_at: string
}

export interface CompanyItem {
  id: string
  tenant_id: string
  name: string
  registration_number: string | null
  tax_id: string | null
  industry: string | null
  contact_person: string | null
  email: string | null
  phone: string | null
  address: string | null
  billing_email: string | null
  payment_terms: string | null
  credit_limit_zar: number | null
  is_active: boolean
  notes: string | null
  members_count: number
  members?: CustomerListItem[]
  created_at: string
  updated_at: string
}

export interface CustomerNoteItem {
  id: string
  customer_id: string
  author_id: string
  content: string
  created_at: string
}

export interface PaginatedResult<T> {
  items: T[]
  total: number
  page: number
  page_size: number
  pages: number
}

// ── Dashboard & High-Level Endpoints (reads -> Loadable) ─────────────────────

export const loadDashboardSummary = (force = false) => cachedRead<DashboardSummary>("/customers/dashboard-summary", force)
export const loadActivities = (force = false) => cachedRead<Activity[]>("/customers/activities", force)
export const loadTasks = (force = false) => cachedRead<CrmTask[]>("/tasks", force)
export const loadInsights = (force = false) =>
  cachedRead<{ aiRecommendations: AiRecommendation[]; issues: Issue[] }>("/customers/insights", force)

// ── Customers ─────────────────────────────────────────────────────────────

export function loadCustomers(
  params?: { page?: number; pageSize?: number; search?: string; status?: string; province?: string },
  force = false,
): Promise<Loadable<PaginatedResult<CustomerListItem>>> {
  const query = new URLSearchParams()
  query.set("page", String(params?.page ?? 1))
  query.set("page_size", String(params?.pageSize ?? 20))
  if (params?.search) query.set("search", params.search)
  if (params?.status) query.set("status", params.status)
  if (params?.province) query.set("province", params.province)
  return cachedRead(`/customers?${query.toString()}`, force)
}

export const loadCustomer360 = (customerId: string) =>
  fetchLoadable<Customer360Data>(`${API_BASE}/customers/${encodeURIComponent(customerId)}`, REQUEST_TIMEOUT_MS)

export const loadCustomer360Section = (customerId: string, section: "details" | "cx" | "crm" | "cvm") =>
  fetchLoadable<unknown>(`${API_BASE}/customers/${encodeURIComponent(customerId)}/360/${section}`, REQUEST_TIMEOUT_MS)

export const loadCustomerNotes = (customerId: string) =>
  fetchLoadable<CustomerNoteItem[]>(`${API_BASE}/customers/${encodeURIComponent(customerId)}/notes`, REQUEST_TIMEOUT_MS)

export type CreateCustomerInput = {
  first_name: string
  last_name: string
  email?: string | null
  phone?: string
  id_number?: string
  address?: string
  province?: string
}

/** 409 => error.kind === "duplicate" with existingCustomerId; pass merge:true to merge into it. */
export function createCustomer(data: CreateCustomerInput, opts?: { merge?: boolean }): Promise<CrmResult<CustomerListItem>> {
  return crmWrite<CustomerListItem>(`/customers${opts?.merge ? "?merge=true" : ""}`, { method: "POST", body: data })
}

export const addCustomerNote = (customerId: string, content: string) =>
  crmWrite<CustomerNoteItem>(`/customers/${encodeURIComponent(customerId)}/notes`, { method: "POST", body: { content } })

export const addCustomerTag = (customerId: string, tag: string) =>
  crmWrite<unknown>(`/customers/${encodeURIComponent(customerId)}/tags`, { method: "POST", body: { tag } })

// ── Leads & Opportunities Pipeline ──────────────────────────────────────────

export function loadLeads(
  params?: { page?: number; pageSize?: number; status?: string; source?: string },
  force = false,
): Promise<Loadable<PaginatedResult<LeadItem>>> {
  const query = new URLSearchParams()
  query.set("page", String(params?.page ?? 1))
  query.set("page_size", String(params?.pageSize ?? 50))
  if (params?.status) query.set("status", params.status)
  if (params?.source) query.set("source", params.source)
  return cachedRead(`/leads?${query.toString()}`, force)
}

export const createLead = (data: {
  first_name: string
  last_name: string
  email?: string
  phone?: string
  source?: string
  coverage_area?: string
  interested_package?: string
}) => crmWrite<LeadItem>("/leads", { method: "POST", body: data })

export const updateLead = (
  leadId: string,
  data: { status?: string; notes?: string; coverage_area?: string; interested_package?: string },
) => {
  if (data.status && ["CONVERTED", "WON"].includes(data.status.trim().toUpperCase())) {
    return Promise.resolve<CrmResult<LeadItem>>({ ok: false, error: { kind: "bad_request", status: 400, message: "Use Convert to create or link a customer." } })
  }
  return crmWrite<LeadItem>(`/leads/${encodeURIComponent(leadId)}`, { method: "PUT", body: data })
}

/**
 * The only way a lead becomes CONVERTED (never PUT status=CONVERTED).
 * 409 {customer_id}: already converted. 400: LOST / DISQUALIFIED.
 */
export const convertLead = (leadId: string, opts?: { merge?: boolean }) =>
  crmWrite<CustomerListItem>(`/leads/${encodeURIComponent(leadId)}/convert${opts?.merge ? "?merge=true" : ""}`, { method: "POST" })

// ── Companies (B2B Accounts) ────────────────────────────────────────────────

export function loadCompanies(
  params?: { page?: number; pageSize?: number; search?: string; is_active?: boolean },
  force = false,
): Promise<Loadable<PaginatedResult<CompanyItem>>> {
  const query = new URLSearchParams()
  query.set("page", String(params?.page ?? 1))
  query.set("page_size", String(params?.pageSize ?? 20))
  if (params?.search) query.set("search", params.search)
  if (params?.is_active !== undefined) query.set("is_active", String(params.is_active))
  return cachedRead(`/companies?${query.toString()}`, force)
}

export const createCompany = (data: {
  name: string
  registration_number?: string
  tax_id?: string
  industry?: string
  contact_person?: string
  email?: string
  phone?: string
  address?: string
  billing_email?: string
  payment_terms?: string
  credit_limit_zar?: number
  notes?: string
}) => crmWrite<CompanyItem>("/companies", { method: "POST", body: data })
