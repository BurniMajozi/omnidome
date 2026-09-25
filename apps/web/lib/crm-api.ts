"use client"

import { getSessionSafe } from "@/lib/supabase/client"

/**
 * CRM API client — customers, leads, companies, 360 view, activities,
 * tasks, and rule-based insights. Proxies through the Next.js API routes
 * to the CRM service.
 */

const API_BASE = "/svc/crm"
const FALLBACK_TENANT_ID = "00000000-0000-0000-0000-000000000001"
const FALLBACK_USER_ID = "00000000-0000-0000-0000-000000000002"

async function getAuthHeaders(): Promise<Record<string, string>> {
  const { data } = await getSessionSafe()
  const tenantId =
    data.session?.user?.user_metadata?.tenant_id ??
    data.session?.user?.app_metadata?.tenant_id ??
    FALLBACK_TENANT_ID
  const userId = data.session?.user?.id ?? FALLBACK_USER_ID
  return { "x-tenant-id": tenantId, "x-user-id": userId }
}

async function fetchCrm<T>(path: string, init?: RequestInit): Promise<T | null> {
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      cache: "no-store",
      headers: { ...(await getAuthHeaders()), "Content-Type": "application/json" },
      ...init,
    })
    if (!res.ok) {
      console.warn(`CRM API error ${res.status} for ${path}`)
      return null
    }
    return res.json()
  } catch (error) {
    console.warn(`CRM API unreachable for ${path}`, error)
    return null
  }
}

// ── Types ─────────────────────────────────────────────────────────────

export interface DashboardSummary {
  totalCustomers: number
  activeLeads: number
  conversionRate: number
  avgRevenuePerCustomer: number
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
  email: string
  phone?: string | null
  address?: string | null
  province?: string | null
  status: string
  account_number: string | null
  rica_verified?: boolean
  company_id?: string | null
  company_role?: string | null
  created_at: string
  mrr: number
  customer_type: string
  health: string
}

export interface Customer360Data {
  id: string
  first_name: string
  last_name: string
  email: string
  phone?: string | null
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

// ── Dashboard & High-Level Endpoints ──────────────────────────────────────────

export async function getDashboardSummary(): Promise<DashboardSummary | null> {
  return fetchCrm<DashboardSummary>("/customers/dashboard-summary")
}

export async function getActivities(): Promise<Activity[]> {
  return (await fetchCrm<Activity[]>("/customers/activities")) ?? []
}

export async function getTasks(): Promise<CrmTask[]> {
  return (await fetchCrm<CrmTask[]>("/tasks")) ?? []
}

export async function getInsights(): Promise<{ aiRecommendations: AiRecommendation[]; issues: Issue[] }> {
  const result = await fetchCrm<{ aiRecommendations: AiRecommendation[]; issues: Issue[] }>("/customers/insights")
  return result ?? { aiRecommendations: [], issues: [] }
}

// ── Customers ─────────────────────────────────────────────────────────────

export async function listCustomers(params?: {
  page?: number
  pageSize?: number
  search?: string
  status?: string
  province?: string
}): Promise<PaginatedResult<CustomerListItem>> {
  const query = new URLSearchParams()
  query.set("page", String(params?.page ?? 1))
  query.set("page_size", String(params?.pageSize ?? 20))
  if (params?.search) query.set("search", params.search)
  if (params?.status) query.set("status", params.status)
  if (params?.province) query.set("province", params.province)

  const result = await fetchCrm<PaginatedResult<CustomerListItem>>(`/customers?${query.toString()}`)
  return result ?? { items: [], total: 0, page: 1, page_size: 20, pages: 1 }
}

export async function getCustomer360(customerId: string): Promise<Customer360Data | null> {
  return fetchCrm<Customer360Data>(`/customers/${customerId}`)
}

export async function createCustomer(data: {
  first_name: string
  last_name: string
  email: string
  phone?: string
  id_number?: string
  address?: string
  province?: string
}): Promise<CustomerListItem | null> {
  return fetchCrm<CustomerListItem>("/customers", {
    method: "POST",
    body: JSON.stringify(data),
  })
}

export async function getCustomerNotes(customerId: string): Promise<CustomerNoteItem[]> {
  return (await fetchCrm<CustomerNoteItem[]>(`/customers/${customerId}/notes`)) ?? []
}

export async function addCustomerNote(customerId: string, content: string): Promise<CustomerNoteItem | null> {
  return fetchCrm<CustomerNoteItem>(`/customers/${customerId}/notes`, {
    method: "POST",
    body: JSON.stringify({ content }),
  })
}

export async function addCustomerTag(customerId: string, tag: string): Promise<any> {
  return fetchCrm(`/customers/${customerId}/tags`, {
    method: "POST",
    body: JSON.stringify({ tag }),
  })
}

// ── Leads & Opportunities Pipeline ──────────────────────────────────────────

export async function listLeads(params?: {
  page?: number
  pageSize?: number
  status?: string
  source?: string
}): Promise<PaginatedResult<LeadItem>> {
  const query = new URLSearchParams()
  query.set("page", String(params?.page ?? 1))
  query.set("page_size", String(params?.pageSize ?? 50))
  if (params?.status) query.set("status", params.status)
  if (params?.source) query.set("source", params.source)

  const result = await fetchCrm<PaginatedResult<LeadItem>>(`/leads?${query.toString()}`)
  return result ?? { items: [], total: 0, page: 1, page_size: 50, pages: 1 }
}

export async function createLead(data: {
  first_name: string
  last_name: string
  email?: string
  phone?: string
  source?: string
  coverage_area?: string
  interested_package?: string
}): Promise<LeadItem | null> {
  return fetchCrm<LeadItem>("/leads", {
    method: "POST",
    body: JSON.stringify(data),
  })
}

export async function updateLead(
  leadId: string,
  data: {
    status?: string
    notes?: string
    coverage_area?: string
    interested_package?: string
  }
): Promise<LeadItem | null> {
  return fetchCrm<LeadItem>(`/leads/${leadId}`, {
    method: "PUT",
    body: JSON.stringify(data),
  })
}

export async function convertLead(leadId: string): Promise<CustomerListItem | null> {
  return fetchCrm<CustomerListItem>(`/leads/${leadId}/convert`, {
    method: "POST",
  })
}

// ── Companies (B2B Accounts) ────────────────────────────────────────────────

export async function listCompanies(params?: {
  page?: number
  pageSize?: number
  search?: string
  is_active?: boolean
}): Promise<PaginatedResult<CompanyItem>> {
  const query = new URLSearchParams()
  query.set("page", String(params?.page ?? 1))
  query.set("page_size", String(params?.pageSize ?? 20))
  if (params?.search) query.set("search", params.search)
  if (params?.is_active !== undefined) query.set("is_active", String(params.is_active))

  const result = await fetchCrm<PaginatedResult<CompanyItem>>(`/companies?${query.toString()}`)
  return result ?? { items: [], total: 0, page: 1, page_size: 20, pages: 1 }
}

export async function createCompany(data: {
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
}): Promise<CompanyItem | null> {
  return fetchCrm<CompanyItem>("/companies", {
    method: "POST",
    body: JSON.stringify(data),
  })
}

export async function getCompany(companyId: string): Promise<CompanyItem | null> {
  return fetchCrm<CompanyItem>(`/companies/${companyId}`)
}
