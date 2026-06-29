"use client"

import { supabase } from "@/lib/supabase/client"

/**
 * Finance API client — GL journal entries. Proxies through the Next.js
 * API routes to the finance service.
 */

const API_BASE = "/svc/finance"
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

async function fetchFinance<T>(path: string, init?: RequestInit): Promise<T | null> {
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      cache: "no-store",
      headers: { ...(await getAuthHeaders()), "Content-Type": "application/json" },
      ...init,
    })
    if (!res.ok) {
      console.warn(`Finance API error ${res.status} for ${path}`)
      return null
    }
    if (res.status === 204) return null
    return res.json()
  } catch (error) {
    console.warn(`Finance API unreachable for ${path}`, error)
    return null
  }
}

// ── Types ─────────────────────────────────────────────────────────────

export interface JournalEntryLine {
  account_code: string
  account_name: string
  description: string | null
  debit: number
  credit: number
}

export interface JournalEntry {
  id: string
  tenant_id: string
  entry_date: string
  reference: string | null
  description: string | null
  source: string | null
  source_id: string | null
  is_posted: boolean
  total_debit: number
  total_credit: number
  lines: JournalEntryLine[]
  created_at: string
}

export interface JournalEntryLineInput {
  account_code: string
  account_name: string
  description?: string
  debit?: number
  credit?: number
}

export interface JournalEntryInput {
  entry_date?: string
  reference?: string
  description?: string
  source?: string
  source_id?: string
  lines: JournalEntryLineInput[]
}

export async function listJournalEntries(params?: { source?: string; isPosted?: boolean }): Promise<JournalEntry[]> {
  const qs = new URLSearchParams()
  if (params?.source) qs.set("source", params.source)
  if (params?.isPosted !== undefined) qs.set("is_posted", String(params.isPosted))
  const suffix = qs.toString() ? `?${qs}` : ""
  return (await fetchFinance<JournalEntry[]>(`/journal-entries${suffix}`)) ?? []
}

export async function createJournalEntry(input: JournalEntryInput): Promise<JournalEntry | null> {
  return fetchFinance<JournalEntry>("/journal-entries", { method: "POST", body: JSON.stringify(input) })
}

export async function postJournalEntry(id: string): Promise<{ status: string; id: string } | null> {
  return fetchFinance(`/journal-entries/${id}/post`, { method: "POST" })
}

export async function deleteJournalEntry(id: string): Promise<void> {
  await fetchFinance(`/journal-entries/${id}`, { method: "DELETE" })
}

// ── Overview / Statements / Cash Flow ───────────────────────────────────

export interface FinanceOverview {
  tenant_id: string
  currency: string
  kpis: { revenue: number; expenses: number; ebit: number; cash_position: number }
  period: string
  generated_at: string
}

export interface StatementLineRaw {
  line: string
  amount: number | string
  section?: boolean
  total?: boolean
  subtotal?: boolean
}

export interface Statements {
  income_statement: StatementLineRaw[]
  balance_sheet: StatementLineRaw[]
  currency: string
  generated_at: string
}

export interface CashFlowActivity {
  items: { label: string; amount: number }[]
  total: number
}

export interface CashFlowStatement {
  operating_activities: CashFlowActivity
  investing_activities: CashFlowActivity
  financing_activities: CashFlowActivity
  net_change_in_cash: number
}

export async function getOverview(): Promise<FinanceOverview | null> {
  return fetchFinance<FinanceOverview>("/overview")
}

export async function getStatements(): Promise<Statements | null> {
  return fetchFinance<Statements>("/statements")
}

export async function getCashFlow(): Promise<CashFlowStatement | null> {
  return fetchFinance<CashFlowStatement>("/cash-flow")
}

// ── Revenue Recognition ──────────────────────────────────────────────────

export interface RevenueContract {
  id: string
  contract: string
  customer: string
  method: string
  start: string
  end: string
  recognized: number
  deferred: number
}

export const listRevenueContracts = () => fetchFinance<RevenueContract[]>("/revenue-contracts").then((r) => r ?? [])

// ── Expense Governance ───────────────────────────────────────────────────

export interface ExpenseReceipt {
  id: string; vendor: string; amount: number; category: string
  status: "queued" | "processed" | "flagged"; ocrConfidence: number; submittedBy: string; date: string
}
export interface ApprovalRequest {
  id: string; request: string; amount: number; owner: string; status: "pending" | "approved" | "rejected"; policy: string
}
export interface PurchaseOrder {
  id: string; vendor: string; amount: number; status: "draft" | "review" | "approved" | "sent"; approver: string; dueDate: string
}
export interface FixedAsset {
  id: string; asset: string; location: string; status: "active" | "maintenance" | "retired"
  cost: number; depreciation: number; remainingLife: string
}
export interface RecurringPayment {
  id: string; vendor: string; amount: number; frequency: string; nextRun: string; status: "active" | "paused"
}
export interface BankStatementItem {
  id: string; date: string; description: string; amount: number; status: "matched" | "unmatched" | "review"; source: string
}

interface RawExpenseReceipt extends Omit<ExpenseReceipt, "category" | "ocrConfidence" | "submittedBy"> {
  category: string | null; ocrConfidence: number | null; submittedBy: string | null
}
export const listExpenseReceipts = () =>
  fetchFinance<RawExpenseReceipt[]>("/expense-receipts").then((r) =>
    (r ?? []).map((x) => ({ ...x, category: x.category ?? "General", ocrConfidence: x.ocrConfidence ?? 100, submittedBy: x.submittedBy ?? "—" }))
  )

interface RawApprovalRequest extends Omit<ApprovalRequest, "owner" | "policy"> {
  owner: string | null; policy: string | null
}
export const listApprovalRequests = () =>
  fetchFinance<RawApprovalRequest[]>("/approval-requests").then((r) =>
    (r ?? []).map((x) => ({ ...x, owner: x.owner ?? "—", policy: x.policy ?? "—" }))
  )

interface RawPurchaseOrder extends Omit<PurchaseOrder, "approver" | "dueDate"> {
  approver: string | null; dueDate: string | null
}
export const listPurchaseOrders = () =>
  fetchFinance<RawPurchaseOrder[]>("/purchase-orders").then((r) =>
    (r ?? []).map((x) => ({ ...x, approver: x.approver ?? "—", dueDate: x.dueDate ?? "—" }))
  )

interface RawFixedAsset extends Omit<FixedAsset, "location" | "remainingLife"> {
  location: string | null; remainingLife: string | null
}
export const listFixedAssets = () =>
  fetchFinance<RawFixedAsset[]>("/fixed-assets").then((r) =>
    (r ?? []).map((x) => ({ ...x, location: x.location ?? "—", remainingLife: x.remainingLife ?? "—" }))
  )

interface RawRecurringPayment extends Omit<RecurringPayment, "nextRun"> {
  nextRun: string | null
}
export const listRecurringPayments = () =>
  fetchFinance<RawRecurringPayment[]>("/recurring-payments").then((r) =>
    (r ?? []).map((x) => ({ ...x, nextRun: x.nextRun ?? "—" }))
  )

// ── Bank Reconciliation ───────────────────────────────────────────────────

interface RawBankStatementItem extends Omit<BankStatementItem, "source"> {
  source: string | null
}
export const listBankItems = () =>
  fetchFinance<RawBankStatementItem[]>("/bank-items").then((r) =>
    (r ?? []).map((x) => ({ ...x, source: x.source ?? "—" }))
  )
