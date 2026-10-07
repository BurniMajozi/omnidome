"use client"

/**
 * Data helpers shared by the Field Sales and Technician document screens.
 *
 * - useWhoami(): the verified user id from /api/whoami (same id the billing service stores as
 *   `created_by` when the client does not send one). null = unreadable, so "mine" filtering is
 *   skipped and the UI says so.
 * - listFieldQuotes(): GET /quotes with source + created_by (the typed client in
 *   lib/invoicing-api.ts does not expose created_by yet).
 * - Tracked invoices: GET /invoices has no source/created_by filter and its rows carry neither
 *   field, so the app remembers the ids of invoices it created/converted on THIS device and loads
 *   each one for real from the server. The list is a convenience index only (never document data).
 */

import { useEffect, useState } from "react"
import { fetchLoadable } from "@/lib/service-fetch"
import { BILLING_BASE } from "@/lib/billing-api"
import type { Loadable } from "@/lib/service-state"
import type { QuoteDoc } from "@/lib/invoicing-api"

export function useWhoami(): { userId: string | null; loading: boolean } {
  const [state, setState] = useState<{ userId: string | null; loading: boolean }>({ userId: null, loading: true })
  useEffect(() => {
    let off = false
    fetch("/api/whoami", { cache: "no-store", signal: AbortSignal.timeout(10_000) })
      .then((r) => (r.ok ? r.json() : null))
      .then((j: { user_id?: string } | null) => {
        if (!off) setState({ userId: j?.user_id ? j.user_id : null, loading: false })
      })
      .catch(() => !off && setState({ userId: null, loading: false }))
    return () => {
      off = true
    }
  }, [])
  return state
}

export function listFieldQuotes(p: { source: string; createdBy?: string | null; customerId?: string }): Promise<Loadable<{ items: QuoteDoc[]; total: number }>> {
  const q = new URLSearchParams({ source: p.source, page_size: "100" })
  if (p.createdBy) q.set("created_by", p.createdBy)
  if (p.customerId) q.set("customer_id", p.customerId)
  return fetchLoadable<{ items: QuoteDoc[]; total: number }>(`${BILLING_BASE}/quotes?${q.toString()}`)
}

export interface CustomerInvoiceRow {
  id: string
  number: string
  status: string
  total_zar: string | number
  amount_paid_zar: string | number
  due_date: string
  customer_id: string
}

export function listCustomerInvoices(customerId: string): Promise<Loadable<{ items: CustomerInvoiceRow[]; total: number }>> {
  return fetchLoadable<{ items: CustomerInvoiceRow[]; total: number }>(`${BILLING_BASE}/invoices?customer_id=${encodeURIComponent(customerId)}&page_size=50`)
}

const key = (source: string, userId: string | null) => `omnidome.field-docs.invoices.${source}.${userId ?? "anon"}`

export function readTrackedInvoiceIds(source: string, userId: string | null): string[] {
  try {
    const raw = window.localStorage.getItem(key(source, userId))
    const arr = raw ? JSON.parse(raw) : []
    return Array.isArray(arr) ? arr.filter((x): x is string => typeof x === "string") : []
  } catch {
    return []
  }
}

export function trackInvoiceId(source: string, userId: string | null, id: string) {
  try {
    const cur = readTrackedInvoiceIds(source, userId).filter((x) => x !== id)
    window.localStorage.setItem(key(source, userId), JSON.stringify([id, ...cur].slice(0, 60)))
  } catch {
    /* storage unavailable: the list simply will not remember */
  }
}
