"use client"

/**
 * Payroll API client — bulk spreadsheet import, roster (search), CRUD, and
 * payroll runs. Proxies through /svc/hr to the HR service (port 8009).
 * Self-contained (does not import hr-api.ts) to stay clear of the Talent module.
 */

import { supabase } from "@/lib/supabase/client"

const API_BASE = "/svc/hr"
const FALLBACK_TENANT_ID = "00000000-0000-0000-0000-000000000001"

async function tenantId(): Promise<string> {
  const { data } = await supabase.auth.getSession()
  return (
    data.session?.user?.user_metadata?.tenant_id ??
    data.session?.user?.app_metadata?.tenant_id ??
    FALLBACK_TENANT_ID
  )
}

async function hr<T>(path: string, init?: RequestInit): Promise<T> {
  const tid = await tenantId()
  const isForm = init?.body instanceof FormData
  const headers: Record<string, string> = {
    "x-tenant-id": tid,
    ...((init?.headers as Record<string, string>) ?? {}),
  }
  if (!isForm) headers["Content-Type"] = "application/json"
  const res = await fetch(`${API_BASE}${path}`, { cache: "no-store", ...init, headers })
  if (!res.ok) {
    const body = await res.text().catch(() => "")
    throw new Error(`${res.status}: ${body || res.statusText}`)
  }
  if (res.status === 204) return undefined as T
  return res.json()
}

// ── Types ──────────────────────────────────────────────────────────────
export interface RosterRow {
  id: string
  employee_id: string
  full_name: string
  job_title: string
  department: string
  status: string
  email?: string | null
  phone?: string | null
  base_salary: number | null
  currency: string
  bank_code?: string | null
  account_number_masked?: string | null
  has_recipient: boolean
}

export interface ImportResult {
  total_rows: number
  created: number
  updated: number
  profiles_set: number
  recipients_created: number
  errors: { row: number; message: string }[]
}

export interface Payslip {
  id: string
  employee_id: string
  gross: number
  tax: number
  uif: number
  net: number
  payout_status: string
  payout_message?: string | null
}

export interface PayRun {
  id: string
  period: string
  status: string
  employee_count: number
  total_gross: number
  total_deductions: number
  total_net: number
  payslips?: Payslip[]
}

// ── Calls ──────────────────────────────────────────────────────────────
export const getRoster = (q?: string) =>
  hr<{ items: RosterRow[]; total: number }>(`/payroll/roster${q ? `?q=${encodeURIComponent(q)}` : ""}`)

export const importSpreadsheet = (file: File, createRecipients = false) => {
  const fd = new FormData()
  fd.append("file", file)
  return hr<ImportResult>(`/payroll/import?create_recipients=${createRecipients}`, { method: "POST", body: fd })
}

export interface NewEmployee {
  employee_id: string
  full_name: string
  job_title: string
  department: string
  hire_date: string
  email?: string
  phone?: string
}

export const createEmployee = (data: NewEmployee) =>
  hr<{ id: string }>(`/employees`, { method: "POST", body: JSON.stringify(data) })

export const deleteEmployee = (id: string) => hr<void>(`/employees/${id}`, { method: "DELETE" })

export const setPayroll = (
  id: string,
  base_salary: number,
  bank?: { bank_code?: string; account_number?: string; account_name?: string },
) => hr(`/employees/${id}/payroll-profile`, { method: "PUT", body: JSON.stringify({ base_salary, ...bank }) })

export const createRun = (period: string) =>
  hr<PayRun & { skipped_employees_without_profile?: string[] }>(`/payroll/runs`, {
    method: "POST",
    body: JSON.stringify({ period }),
  })

export const payRun = (id: string) =>
  hr<PayRun & { initiated: number; failed: number }>(`/payroll/runs/${id}/pay`, { method: "POST" })
