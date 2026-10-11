"use client"

import { useEffect, useState, useCallback } from "react"
import { createTtlCache } from "@/lib/request-cache"
import { fetchLoadable } from "@/lib/service-fetch"
import { sendJson, type ActionResult } from "@/lib/api-result"
import type { Loadable } from "@/lib/service-state"
import { customerNameMap, billingTier, type BillingTier } from "@/lib/billing-derive"
import { useRoles } from "@/lib/use-roles"

/**
 * Billing API client. Everything goes through /svc/billing (the signed-identity
 * proxy; the Bearer token is attached by AuthFetchInit). Reads keep the HTTP
 * status (Loadable) so the UI can tell "not running" from "not permitted";
 * writes return an ActionResult carrying the server's 403/409/422 message.
 */

export const BILLING_BASE = "/svc/billing"
const ADMIN_LABEL = "finance admin"

export interface Paginated<T> {
  items: T[]
  total: number
  page?: number
  page_size?: number
  pages?: number
}

export interface InvoiceRow {
  id: string
  customer_id: string
  number: string
  status: string
  total_zar: string | number
  amount_paid_zar: string | number
  due_date: string
  created_at?: string
}

export interface PaymentRow {
  id?: string
  invoice_id?: string
  customer_id?: string
  method: string
  amount_zar: string | number
  status: string
  reference?: string | null
  created_at?: string
}

export interface CollectionsReportRow {
  period: string
  total_invoiced_zar: string | number
  total_collected_zar: string | number
  total_overdue_zar: string | number
  collection_rate: string | number | null
}

export interface DunningActionRow {
  id: string
  invoice_id: string
  customer_id: string
  action_type: string
  scheduled_at: string
  executed_at: string | null
  result: string | null
}

export interface PagedResult<T> {
  items: T[]
  total: number
  /** true when more rows exist than were fetched (cap reached). */
  truncated: boolean
}

/**
 * Fetch up to `maxPages` pages of a paginated list endpoint. A failure on the FIRST
 * page is returned as the non-ready state; a failure after that keeps what was
 * loaded and marks the result truncated so the UI says "Showing N of total".
 */
export async function fetchPages<T>(
  path: string,
  opts: { pageSize?: number; maxPages?: number } = {},
): Promise<Loadable<PagedResult<T>>> {
  const pageSize = Math.max(1, Math.min(100, Math.floor(opts.pageSize ?? 100)))
  const maxPages = Math.max(1, Math.min(50, Math.floor(opts.maxPages ?? 5)))
  const sep = path.includes("?") ? "&" : "?"
  const items: T[] = []
  let total = 0
  for (let page = 1; page <= maxPages; page++) {
    const l = await fetchLoadable<Paginated<T>>(`${BILLING_BASE}${path}${sep}page=${page}&page_size=${pageSize}`)
    if (l.state !== "ready") {
      if (page === 1) return l as Loadable<PagedResult<T>>
      return { state: "ready", data: { items, total: total, truncated: true } }
    }
    if (!l.data || !Array.isArray(l.data.items) || !Number.isSafeInteger(l.data.total) || l.data.total < 0) {
      if (page === 1) return { state: "error", status: 200, message: "Invalid billing list response" }
      return { state: "ready", data: { items, total, truncated: true } }
    }
    items.push(...l.data.items)
    total = Math.max(l.data.total, items.length)
    if (items.length >= total || (l.data.items ?? []).length < pageSize) break
  }
  return { state: "ready", data: { items, total, truncated: items.length < total } }
}

/** One page, used by "Load more" on the invoices table. */
export const fetchInvoicePage = (page: number, pageSize = 50) =>
  fetchLoadable<Paginated<InvoiceRow>>(`${BILLING_BASE}/invoices?page=${page}&page_size=${pageSize}`)

// Customer directory: bounded paginated batches, cached for one minute; no per-row calls.
const nameCache = createTtlCache(60_000)
export interface CustomerNames {
  names: Record<string, string>
  /** true when CRM has more customers than the batch returned. */
  partial: boolean
}
export function fetchCustomerNames(): Promise<CustomerNames | null> {
  return nameCache.get<CustomerNames | null>(
    "crm-names",
    async () => {
      const names: Record<string, string> = {}
      for (let page = 1; page <= 10; page++) {
        const l = await fetchLoadable<{ items: Array<{ id: string; first_name?: string; last_name?: string }>; total: number }>(
          `/svc/crm/customers?page=${page}&page_size=100`,
        )
        if (l.state !== "ready") return page === 1 ? null : { names, partial: true }
        Object.assign(names, customerNameMap(l.data.items ?? []))
        if (page * 100 >= l.data.total || l.data.items.length < 100) return { names, partial: false }
      }
      return { names, partial: true }
    },
    (r) => r !== null,
  )
}

// Writes
const post = <T>(path: string, body?: unknown, headers?: Record<string, string>) =>
  sendJson<T>(`${BILLING_BASE}${path}`, "POST", body ?? {}, { headers, adminLabel: ADMIN_LABEL })

export interface GeneratedInvoice extends InvoiceRow {
  created: boolean
}

/** Admin: bill the given customers' due subscriptions (idempotent: a second call creates nothing). */
export const generateInvoices = (customerIds: string[], billingDate?: string): Promise<ActionResult<GeneratedInvoice[]>> =>
  post<GeneratedInvoice[]>("/invoices/generate", {
    ...(billingDate ? { billing_date: billingDate } : {}),
    ...(customerIds.length ? { customer_ids: customerIds } : {}),
  })

export const sendInvoice = (id: string, channel: "email" | "sms" | "both" = "email") =>
  post<InvoiceRow>(`/invoices/${encodeURIComponent(id)}/send`, { channel })

export const voidInvoice = (id: string) => post<InvoiceRow>(`/invoices/${encodeURIComponent(id)}/void`)

export const createCreditNote = (id: string, reason: string) =>
  post<InvoiceRow>(`/invoices/${encodeURIComponent(id)}/credit-note`, { reason })

/** Manual payment. `idempotencyKey` is generated ONCE per dialog open so a double click records once. */
export const recordPayment = (
  input: { invoice_id: string; amount_zar: string; method: string; reference?: string },
  idempotencyKey: string,
) => post<PaymentRow>("/payments", { ...input, idempotency_key: idempotencyKey }, { "Idempotency-Key": idempotencyKey })

/** Admin: hosted Paystack checkout link. No callback_url is sent (the server allow-lists its own). */
export const initializePaystack = (invoiceId: string, amountZar?: string) =>
  post<{ authorization_url: string; access_code: string; reference: string }>("/payments/paystack/initialize", {
    invoice_id: invoiceId,
    ...(amountZar ? { amount_zar: amountZar } : {}),
  })

export const suspendCustomer = (customerId: string) => post<{ status: string }>(`/collections/${encodeURIComponent(customerId)}/suspend`)
export const reinstateCustomer = (customerId: string) => post<{ status: string }>(`/collections/${encodeURIComponent(customerId)}/reinstate`)

export const createArrangement = (
  customerId: string,
  input: { total_owed_zar: string; installment_zar: string; installments_count: number; first_due_date: string; notes?: string },
) => post<unknown>(`/collections/${encodeURIComponent(customerId)}/arrange`, input)

/** Admin: process this tenant's due dunning actions now. */
export const processDunningNow = () => post<{ processed: number; results: Record<string, number> }>("/dunning/process-tenant")

/** Admin: re-deliver pending/failed ledger postings. */
export const retryFinanceOutbox = () => post<unknown>("/billing/finance-outbox/retry")

export function useBillingPages<T>(path: string) {
  const [value, setValue] = useState<Loadable<PagedResult<T>>>({ state: "loading" })
  const [tick, setTick] = useState(0)
  useEffect(() => {
    let cancelled = false
    setValue({ state: "loading" })
    fetchPages<T>(path).then(result => { if (!cancelled) setValue(result) })
    return () => { cancelled = true }
  }, [path, tick])
  const reload = useCallback(() => setTick(t => t + 1), [])
  return { value, reload }
}

/**
 * The caller's billing tier (UI hint only; the server enforces). `loading` while the
 * role lookup is in flight; `none` when roles are unreadable, which hides every write control.
 */
export function useBillingTier(): { tier: BillingTier; loading: boolean; canWrite: boolean; isAdmin: boolean } {
  const { roles } = useRoles()
  const tier = billingTier(roles)
  return { tier, loading: roles === undefined, canWrite: tier === "clerk" || tier === "admin", isAdmin: tier === "admin" }
}

// ---------------------------------------------------------------- Payments gateway

const get = <T>(path: string) => fetchLoadable<T>(`${BILLING_BASE}${path}`)
const put = <T>(path: string, body: unknown) => sendJson<T>(`${BILLING_BASE}${path}`, "PUT", body, { adminLabel: ADMIN_LABEL })
const del = <T>(path: string) => sendJson<T>(`${BILLING_BASE}${path}`, "DELETE", undefined, { adminLabel: ADMIN_LABEL })

export interface GatewayBank {
  code: string
  name: string
}
export interface GatewaySettings {
  configured: boolean
  business_name?: string | null
  bank?: string | null
  settlement_bank_code?: string | null
  account_last4?: string | null
  status?: string | null
  /** Set when a change to the settlement account awaits platform approval. */
  pending_change?: { bank: string; last4: string; requested_at: string } | null
}
export interface GatewayTier {
  from_zar: number
  to_zar: number | null
  rate_percent: number
}
export interface GatewaySummary {
  period: string
  volume_zar: number
  charges: number
  commission_zar: number
  current_rate_percent: number
  next_threshold_zar: number | null
  remaining_in_band_zar: number | null
  tiers: GatewayTier[]
}
export interface CommissionPreview {
  commission_zar: number
  tenant_receives_zar: number
  effective_rate_percent: number
}
export interface PendingGatewayChange {
  tenant_id: string
  business_name: string
  current: { bank: string; last4: string }
  requested: { bank: string; last4: string; business_name: string }
  requested_by: string
  requested_at: string
}

export const getGatewaySettings = () => get<GatewaySettings>("/gateway/settings")
export const listGatewayBanks = () => get<{ banks: GatewayBank[] }>("/gateway/banks")
/** Admin. The account number is sent once here; the API only ever returns the last 4 digits. */
export const saveGatewaySettings = (input: { business_name: string; settlement_bank_code: string; account_number: string }) =>
  put<GatewaySettings>("/gateway/settings", input)
export const getGatewaySummary = () => get<GatewaySummary>("/gateway/summary")
export const previewCommission = (amountZar: number) => get<CommissionPreview>(`/gateway/commission/preview?amount_zar=${encodeURIComponent(String(amountZar))}`)
/** Platform admin only: a 403 (state "denied") means the caller is not one. */
export const listPendingGatewayChanges = () => get<{ changes: PendingGatewayChange[] }>("/gateway/changes/pending")
export const approveGatewayChange = (tenantId: string) => post<unknown>(`/gateway/changes/${encodeURIComponent(tenantId)}/approve`)
export const rejectGatewayChange = (tenantId: string) => post<unknown>(`/gateway/changes/${encodeURIComponent(tenantId)}/reject`)

// ---------------------------------------------------------------- Disputes

export interface DisputeRow {
  id: string
  dispute_id: string
  reference: string | null
  invoice_id: string | null
  amount_zar: number
  status: string
  category: string | null
  resolution: string | null
  due_at: string | null
  open: boolean
  outcome?: "lost" | "won" | null
  updated_at: string | null
}
export interface DisputeList {
  disputes: DisputeRow[]
  open: number
  next_due_at: string | null
}
export interface EvidencePack {
  customer_name?: string | null
  customer_email?: string | null
  customer_phone?: string | null
  service_details?: string | null
  delivery_address?: string | null
  delivery_date?: string | null
  invoice_numbers?: string[]
  payments?: Array<{ reference: string; amount_zar: number; paid_at: string }>
  activity?: Array<{ at: string; text: string }>
}
export interface DisputeDetail extends DisputeRow {
  evidence_pack?: EvidencePack | null
}
export interface EvidenceInput {
  customer_email: string
  customer_name: string
  customer_phone: string
  service_details: string
  delivery_address: string
  delivery_date: string | null
}

export const listDisputes = () => get<DisputeList>("/disputes")
export const getDispute = (id: string) => get<DisputeDetail>(`/disputes/${encodeURIComponent(id)}`)
export const submitDisputeEvidence = (id: string, input: EvidenceInput) => post<unknown>(`/disputes/${encodeURIComponent(id)}/evidence`, input)
export const resolveDispute = (id: string, input: { resolution: "merchant-accepted" | "declined"; message: string; refund_amount_zar?: number }) =>
  post<unknown>(`/disputes/${encodeURIComponent(id)}/resolve`, input)

// ---------------------------------------------------------------- Cards on file

export interface PaymentMethod {
  id: string
  customer_id: string
  brand: string | null
  card_type: string | null
  bank: string | null
  last4: string
  exp_month: number | string | null
  exp_year: number | string | null
  is_default: boolean
  /** "active" | "expired" | ... */
  status: string
}
export const listPaymentMethods = (customerId: string) =>
  get<{ methods: PaymentMethod[] }>(`/payment-methods?customer_id=${encodeURIComponent(customerId)}`)
export const makePaymentMethodDefault = (id: string) => post<unknown>(`/payment-methods/${encodeURIComponent(id)}/default`)
export const removePaymentMethod = (id: string) => del<unknown>(`/payment-methods/${encodeURIComponent(id)}`)
export const chargeSavedCard = (input: { invoice_id: string; payment_method_id?: string; amount_zar?: number }) =>
  post<{ status: "succeeded" | "failed" | "pending"; reason?: string | null }>("/payments/charge-saved", input)

export interface AutopayResult {
  charged: number
  failed: number
  pending: number
  skipped: number
  details: Array<{ invoice_id: string; status: string; attempt?: number | null; reason?: string | null; error?: string | null }>
}
/** Admin: charge every due invoice that has a saved card. */
export const runAutopayNow = () => post<AutopayResult>("/payments/autopay/run")

// ---------------------------------------------------------------- Refunds + amounts owed to the platform

export type RefundCreditKind = "refund_required" | "overpayment" | "unallocated_payment"
export interface RefundCredit {
  id: string
  customer_id: string
  invoice_id: string | null
  kind: RefundCreditKind
  reason: string | null
  amount_zar: number
  remaining_zar: number
  /** How much of the credit can still go back to the customer's card; 0 when the original payment was not by card. */
  paystack_refundable_zar: number
  created_at: string
}
export interface RefundRow {
  id: string
  credit_id: string
  invoice_id: string | null
  method: "paystack" | "manual"
  amount_zar: number
  status: string
  reason: string | null
  failure_reason: string | null
  created_at: string
  updated_at: string | null
}
export const listRefundCredits = () => get<{ credits: RefundCredit[] }>("/refunds/credits")
export const listRefunds = () => get<{ refunds: RefundRow[] }>("/refunds")
/** Admin. Money movement: callers confirm first. 400/422/502 bodies carry a useful `detail`. */
export const createRefund = (input: { credit_id: string; amount_zar: number; reason: string; method: "paystack" | "manual"; manual_reference?: string }) =>
  post<RefundRow>("/refunds", input)

export interface GatewayLiability {
  id: string
  kind: "refund" | "chargeback"
  amount_zar: number
  status: "open" | "recovered" | "written_off"
  note: string | null
  created_at: string
}
export const getGatewayLiabilities = () => get<{ owed_zar: number; items: GatewayLiability[] }>("/gateway/liabilities")

// ---------------------------------------------------------------- Payout wallet

export type WalletEntryKind = "funding" | "manual_funding" | "payout" | "payout_fee" | "reversal" | "fee_reversal" | "liability_recovery"
export interface WalletEntry {
  kind: WalletEntryKind | string
  amount_zar: number
  note: string | null
  created_at: string
}
export interface PayoutWallet {
  balance_zar: number
  open_liabilities_zar: number
  entries: WalletEntry[]
}
export interface PayoutQuote {
  amount_zar: number
  fee_zar: number
  required_zar: number
  effective_rate_percent: number
  balance_zar: number
  shortfall_zar: number
  period?: string
}
export interface PayoutBatchItem {
  item_ref: string
  reference: string | null
  status: string
  amount_zar: number
  fee_zar: number
  transfer_code: string | null
  message: string | null
}
export interface PayoutBatch {
  id: string
  kind: string
  source_id: string | null
  attempt: number
  status: string
  total_zar: number
  fee_zar: number
  counts: { pending: number; processing: number; success: number; failed: number }
  created_at: string
  items: PayoutBatchItem[]
}

export const getPayoutWallet = () => get<PayoutWallet>("/payouts/wallet")
export const listPayoutBatches = () => get<{ batches: PayoutBatch[] }>("/payouts/batches")
/** Admin: Paystack checkout to top up the wallet. */
export const initializeWalletFunding = (input: { amount_zar: number; email: string }) =>
  post<{ authorization_url: string; reference: string }>("/payouts/funding/initialize", input)
export const quotePayout = (amountZar: number) => post<PayoutQuote>("/payouts/quote", { amount_zar: amountZar })
/** Admin: re-check a batch that has not finished; returns the updated batch. */
export const reconcilePayoutBatch = (id: string) => post<PayoutBatch>(`/payouts/batches/${encodeURIComponent(id)}/reconcile`)
/** Platform admin only: record an EFT received for a tenant. credited=false means the reference was already recorded. */
export const recordManualFunding = (input: { tenant_id: string; amount_zar: number; bank_reference: string }) =>
  post<{ credited: boolean }>("/payouts/funding/manual", input)
