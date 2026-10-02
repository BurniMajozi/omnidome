"use client"

import { useEffect, useState, useCallback } from "react"
import { createTtlCache } from "@/lib/request-cache"
import { fetchLoadable } from "@/lib/service-fetch"
import { sendJson, type ActionResult } from "@/lib/api-result"
import type { Loadable } from "@/lib/service-state"
import { customerNameMap } from "@/lib/billing-derive"

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
