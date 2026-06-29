"use client"

import { supabase } from "@/lib/supabase/client"

/**
 * CRM API client — customers, leads, dashboard summary, activities,
 * tasks, and rule-based insights. Proxies through the Next.js API routes
 * to the CRM service.
 */

const API_BASE = "/svc/crm"
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
  status: string
  account_number: string | null
  created_at: string
  mrr: number
  customer_type: string
  health: string
}

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

export async function listCustomers(pageSize = 5): Promise<CustomerListItem[]> {
  const result = await fetchCrm<{ items: CustomerListItem[] }>(`/customers?page=1&page_size=${pageSize}`)
  return result?.items ?? []
}
