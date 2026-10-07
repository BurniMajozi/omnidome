"use client"

/**
 * Invoicing suite client: manual invoices, catalogue, templates, quotes, delivery,
 * share links, movements, fee policies. Contracts: docs/billing-invoicing-api.md and
 * docs/billing-fee-policies-api.md. Everything goes through the /svc/billing proxy
 * (Bearer attached by AuthFetchInit). Money is a decimal STRING end to end; the
 * server's numbers are authoritative, nothing here is invented.
 */

import { fetchLoadable } from "@/lib/service-fetch"
import { sendJson, newIdempotencyKey, type ActionResult } from "@/lib/api-result"
import type { Loadable } from "@/lib/service-state"
import { BILLING_BASE } from "@/lib/billing-api"

const enc = encodeURIComponent
const url = (p: string) => `${BILLING_BASE}${p}`
const ADMIN = "finance admin"

export { newIdempotencyKey }
export type { ActionResult, Loadable }

// ---------------------------------------------------------------- types

export type SourceType = "manual" | "field_sales" | "technician" | "termination_fee" | "web" | "other"
export type QuoteSource = "field_sales" | "technician" | "web" | "other"

export interface BillTo {
  name?: string | null
  email?: string | null
  phone?: string | null
  address?: string | null
}

export interface DocLine {
  line_id?: string
  description: string
  quantity: string | number
  unit_price_zar?: string | number
  gross_zar?: string
  discount_zar?: string
  tax_rate?: string | number
  total_zar?: string
  vat_zar?: string
  line_total_incl_zar?: string
  catalog_item_id?: string | null
}

export interface InvoiceDetail {
  id: string
  number: string
  status: string
  customer_id: string | null
  subscription_id?: string | null
  credit_note_of?: string | null
  issue_date?: string | null
  due_date?: string | null
  lines: DocLine[]
  subtotal_zar: string
  discount_total_zar?: string
  vat_zar: string
  total_zar: string
  amount_paid_zar: string
  balance_zar: string
  currency?: string
  notes?: string | null
  terms?: string | null
  po_number?: string | null
  source_type?: string | null
  created_by?: string | null
  template_id?: string | null
  bill_to?: BillTo | null
  quote_id?: string | null
  created_at?: string
}

export interface QuoteDoc {
  id: string
  number: string
  status: string
  customer_id: string | null
  prospect?: BillTo | null
  issue_date?: string | null
  valid_until?: string | null
  lines: DocLine[]
  subtotal_zar: string
  discount_total_zar?: string
  vat_zar: string
  total_zar: string
  notes?: string | null
  terms?: string | null
  po_number?: string | null
  source?: string | null
  created_by?: string | null
  template_id?: string | null
  converted_invoice_id?: string | null
  sent_at?: string | null
  viewed_at?: string | null
  accepted_at?: string | null
  declined_at?: string | null
  converted_at?: string | null
  decision_note?: string | null
}

export interface LineInput {
  description: string
  quantity: string
  unit_price: string
  discount?: string
  discount_type?: "amount" | "percent"
  tax_rate?: string
  catalog_item_id?: string | null
}

export interface InvoiceInput {
  customer_id?: string
  issue_date?: string
  due_date?: string
  lines?: LineInput[]
  notes?: string
  terms?: string
  po_number?: string
  source_type?: SourceType
  created_by?: string
  template_id?: string | null
  bill_to?: BillTo
}

export interface QuoteInput {
  customer_id?: string
  prospect_name?: string
  prospect_email?: string
  prospect_phone?: string
  prospect_address?: string
  source?: QuoteSource
  created_by?: string
  issue_date?: string
  valid_until?: string
  lines?: LineInput[]
  notes?: string
  terms?: string
  po_number?: string
  template_id?: string | null
}

export interface CatalogItem {
  id: string
  name: string
  description?: string | null
  unit_price_zar: string
  tax_rate: string | number | null
  category?: string | null
  active: boolean
}

export interface ShowColumns {
  description: boolean
  quantity: boolean
  unit_price: boolean
  discount: boolean
  tax: boolean
  line_total: boolean
}

export interface InvoiceTemplate {
  id?: string
  builtin?: boolean
  name: string
  is_default: boolean
  company_name?: string | null
  company_address?: string | null
  vat_number?: string | null
  logo_url?: string | null
  accent_colour?: string | null
  footer?: string | null
  payment_details?: string | null
  default_terms?: string | null
  default_due_days?: number | null
  show_columns: ShowColumns
  show_payment_details: boolean
  show_terms: boolean
}

export interface DeliveryEvent {
  id: string
  event_type: string
  kind?: string | null
  recipient?: string | null
  subject?: string | null
  message_id?: string | null
  actor?: string | null
  detail?: Record<string, unknown> | null
  at: string
}

export interface ShareLinkRow {
  id: string
  expires_at: string | null
  revoked_at: string | null
  active: boolean
  view_count: number
  last_viewed_at: string | null
}

export interface ShareLinkCreated {
  id: string
  token: string
  url: string | null
  api_path: string
  expires_at: string
}

export interface SuggestedAction {
  id: string
  label: string
  endpoint: string | null
  payload?: Record<string, unknown> | null
  tier?: string
  reason?: string
}

export interface Movement {
  id: string
  type: string
  at: string
  amount: string | null
  status: string | null
  invoice_id: string | null
  quote_id: string | null
  customer_id: string | null
  actor: string | null
  next_actions: string[]
  detail?: Record<string, unknown> | null
}

export interface MovementsResponse {
  items: Movement[]
  count: number
  total_matching: number
}

export interface InvoiceTimeline {
  invoice_id: string
  number: string
  status: string
  events: Movement[]
  suggested_actions: SuggestedAction[]
}

export interface EmailInput {
  to?: string[]
  cc?: string[]
  subject?: string
  message?: string
  kind?: "document" | "reminder"
  link_expires_in_days?: number
}

export interface EmailResult {
  status: string
  message_id?: string
  event_id?: string
  recipients?: { to: string[]; cc: string[] }
  link_expires_at?: string | null
  replayed?: boolean
}

// ---- fee policies

export interface FeeComponent {
  code: string
  label: string
  amount_source: "snapshot" | "fixed" | "catalog"
  fixed_amount: string | null
  recoverable: boolean
}

export interface FeeWaiverRule {
  reason_code: string
  label: string
  waive_percent: string
  required_tier: "none" | "clerk" | "admin"
  evidence_required: boolean
}

export interface FeePolicyBody {
  name: string
  description?: string | null
  trigger_types: string[]
  applies_to_plans: string[]
  is_default: boolean
  is_active: boolean
  effective_from?: string | null
  effective_to?: string | null
  term_months: number
  components: FeeComponent[]
  method: "straight_line" | "declining" | "flat" | "percent_of_remaining_rental"
  flat_percent: string
  rental_percent: string
  month_rule: { mode: "whole_months" | "prorated_days"; remaining_rounding?: "up" | "down" }
  min_fee_zar: string | null
  max_fee_zar: string | null
  grace_period_days: number
  waivers: FeeWaiverRule[]
  auto_approve_waiver_limit_zar: string | null
  allow_self_approval: boolean
  router_credit: {
    enabled: boolean
    mode: "offset_router_component" | "credit_value_by_condition"
    router_component_code: string
    condition_pct: Record<string, string>
  }
  vat: { rate: string; treatment: "exclusive" | "inclusive" }
  outstanding_balance: "include" | "exclude"
  auto_invoice: boolean
  auto_invoice_stage: "proceed" | "initiate"
  invoice_due_days: number
  catalog_amounts?: Record<string, Record<string, string>>
}

export interface FeePolicy extends FeePolicyBody {
  id: string
  policy_key: string
  version: number
  superseded_by?: string | null
  created_at?: string
}

export interface FeeLine {
  code?: string
  label: string
  kind: string
  total_amount?: string
  monthly_amortisation?: string
  months_elapsed?: string
  months_remaining?: string
  unamortised_fraction?: string
  amount: string
  net?: string
  vat?: string
  gross?: string
  source?: string
  recoverable?: boolean
  formula?: string
  reason_code?: string
  applied_by?: string
}

export interface FeeBreakdown {
  term_months: number
  months_elapsed: string
  months_remaining: string
  method: string
  lines: FeeLine[]
  totals: {
    fee_net: string
    fee_vat: string
    fee_total: string
    waived_total: string
    total_before_waiver: string
    outstanding_balance: string
    total_payable: string
  }
  router_credit?: Record<string, unknown> | null
  waiver_eligibility?: Array<{ reason_code: string; required_tier: string; indicative_gross?: string; applied?: boolean }>
  formula?: string
}

export interface SimulateResult {
  persisted: boolean
  policy: { id: string; policy_key: string; version: number; name: string }
  snapshot_id: string | null
  snapshot_missing: boolean
  inputs_hash: string
  inputs: Record<string, unknown>
  flags: string[]
  breakdown: FeeBreakdown
}

export interface FeeCalculation {
  id: string
  status: "calculated" | "waived" | "invoiced" | "superseded" | string
  subscription_id?: string | null
  customer_id?: string | null
  trigger?: string
  effective_date?: string
  fee_net_zar: string
  fee_vat_zar: string
  fee_total_zar: string
  amount_due_zar: string
  waived_total_zar: string
  waivers?: Array<Record<string, unknown>>
  invoice_id?: string | null
  invoice_number?: string | null
  breakdown: FeeBreakdown
  flags: string[]
  inputs?: Record<string, unknown>
  inputs_hash?: string
  policy_id?: string
  policy_version?: number
  auto_calculated?: boolean
  created_at?: string
}

export interface SimulateInput {
  subscription_id?: string
  trigger: string
  effective_date?: string
  reason_code?: string
  router_returned?: boolean
  router_condition?: string
  policy_id?: string
  snapshot?: {
    term_start: string
    term_months: number
    components: Array<{ code: string; amount: string; discount?: string }>
    monthly_rental_zar?: string
    plan_name?: string
  }
}

export interface SnapshotInput {
  subscription_id: string
  term_start?: string
  term_months?: number
  components: Array<{ code: string; amount: string; discount?: string }>
  monthly_rental_zar?: string
  policy_id?: string | null
  backfill?: boolean
  supersede?: boolean
  notes?: string
}

export interface ContractSnapshot {
  id: string
  subscription_id: string
  term_start?: string
  term_months?: number
  components?: Array<{ code: string; amount: string; discount?: string }>
  monthly_rental_zar?: string
  version?: number
  is_current?: boolean
  created_at?: string
}

// ---------------------------------------------------------------- helpers

const clean = (o: object) => {
  const out: Record<string, unknown> = {}
  for (const [k, v] of Object.entries(o)) if (v !== undefined && v !== "") out[k] = v
  return out
}
const qs = (o: Record<string, string | number | boolean | undefined | null>) => {
  const p = new URLSearchParams()
  for (const [k, v] of Object.entries(o)) if (v !== undefined && v !== null && v !== "") p.set(k, String(v))
  const s = p.toString()
  return s ? `?${s}` : ""
}
const get = <T>(path: string) => fetchLoadable<T>(url(path))
const send = <T>(method: "POST" | "PUT" | "PATCH" | "DELETE", path: string, body?: unknown, headers?: Record<string, string>) =>
  sendJson<T>(url(path), method, body, { headers, adminLabel: ADMIN })

// ---------------------------------------------------------------- invoices

export const getInvoiceDetail = (id: string) => get<InvoiceDetail>(`/invoices/${enc(id)}/detail`)
export const getInvoiceTimeline = (id: string) => get<InvoiceTimeline>(`/invoices/${enc(id)}/timeline`)
export const listInvoicePayments = (id: string) =>
  get<{ items: Array<{ id: string; method: string; amount_zar: string; status: string; reference?: string | null; created_at?: string }> }>(
    `/payments${qs({ invoice_id: id, page_size: 100 })}`,
  )
export const createManualInvoice = (b: InvoiceInput) => send<InvoiceDetail>("POST", "/invoices/manual", clean(b))
export const updateInvoice = (id: string, b: InvoiceInput) => send<InvoiceDetail>("PUT", `/invoices/${enc(id)}`, clean(b))
export const duplicateInvoice = (id: string) => send<InvoiceDetail>("POST", `/invoices/${enc(id)}/duplicate`)
export const reorderInvoiceLines = (id: string, order: string[]) => send<InvoiceDetail>("PUT", `/invoices/${enc(id)}/lines/order`, { order })
/** Issues the draft (dunning schedule + ledger outbox). */
export const issueInvoice = (id: string) => send<InvoiceDetail>("POST", `/invoices/${enc(id)}/send`, { channel: "email" })

// ---------------------------------------------------------------- catalogue / templates

export const listItems = (p: { q?: string; category?: string; active?: boolean; limit?: number; offset?: number } = {}) =>
  get<CatalogItem[] | { items: CatalogItem[] }>(`/invoice-items${qs({ limit: 200, ...p })}`)
export const createItem = (b: Partial<CatalogItem>) => send<CatalogItem>("POST", "/invoice-items", clean(b))
export const updateItem = (id: string, b: Partial<CatalogItem>) => send<CatalogItem>("PUT", `/invoice-items/${enc(id)}`, clean(b))
export const deleteItem = (id: string) => send<unknown>("DELETE", `/invoice-items/${enc(id)}`)

export const listTemplates = () => get<InvoiceTemplate[] | { items: InvoiceTemplate[] }>("/invoice-templates")
export const getDefaultTemplate = () => get<InvoiceTemplate>("/invoice-templates/default")
export const createTemplate = (b: InvoiceTemplate) => send<InvoiceTemplate>("POST", "/invoice-templates", b)
export const updateTemplate = (id: string, b: InvoiceTemplate) => send<InvoiceTemplate>("PUT", `/invoice-templates/${enc(id)}`, b)
export const deleteTemplate = (id: string) => send<unknown>("DELETE", `/invoice-templates/${enc(id)}`)

/** Endpoints may return a bare array or `{items}`; normalise. */
export function asList<T>(d: T[] | { items: T[] } | null | undefined): T[] {
  if (Array.isArray(d)) return d
  if (d && Array.isArray((d as { items?: T[] }).items)) return (d as { items: T[] }).items
  return []
}

// ---------------------------------------------------------------- quotes

export const listQuotes = (p: { status?: string; customer_id?: string; source?: string; page?: number; page_size?: number } = {}) =>
  get<{ items: QuoteDoc[]; total: number; page: number; page_size: number }>(`/quotes${qs({ page_size: 100, ...p })}`)
export const getQuote = (id: string) => get<QuoteDoc>(`/quotes/${enc(id)}`)
export const createQuote = (b: QuoteInput) => send<QuoteDoc>("POST", "/quotes", clean(b))
export const updateQuote = (id: string, b: QuoteInput) => send<QuoteDoc>("PUT", `/quotes/${enc(id)}`, clean(b))
export const markQuoteSent = (id: string) => send<QuoteDoc>("POST", `/quotes/${enc(id)}/send`)
export const acceptQuote = (id: string, note?: string) => send<QuoteDoc>("POST", `/quotes/${enc(id)}/accept`, note ? { note } : {})
export const declineQuote = (id: string, note?: string) => send<QuoteDoc>("POST", `/quotes/${enc(id)}/decline`, note ? { note } : {})
export const convertQuote = (id: string, b: { customer_id?: string; due_date?: string; force?: boolean } = {}) =>
  send<{ created: boolean; quote: QuoteDoc; invoice: InvoiceDetail }>("POST", `/quotes/${enc(id)}/convert`, clean(b))

// ---------------------------------------------------------------- documents, delivery, share links

export type DocKind = "invoices" | "quotes"

/** Same-origin path of the print-ready HTML (fetched with the Bearer token, shown via srcDoc). */
export const documentPath = (kind: DocKind, id: string) => url(`/${kind}/${enc(id)}/document`)

/** Fetch text (HTML/CSV/JSON) of a document or export with auth. */
export async function fetchDocText(
  kind: DocKind,
  id: string,
  format?: "csv" | "json" | "html",
): Promise<ActionResult<string>> {
  const path = format ? `/${kind}/${enc(id)}/export?format=${format}` : `/${kind}/${enc(id)}/document`
  try {
    const res = await fetch(url(path), { cache: "no-store", signal: AbortSignal.timeout(20_000) })
    const text = await res.text()
    if (!res.ok) {
      let msg = `Request failed (HTTP ${res.status})`
      try {
        const j = JSON.parse(text)
        if (typeof j?.detail === "string") msg = j.detail
      } catch {
        /* keep default */
      }
      return { ok: false, status: res.status, data: null, message: msg }
    }
    return { ok: true, status: res.status, data: text, message: null }
  } catch {
    return { ok: false, status: 0, data: null, message: "Could not reach the service. Try again." }
  }
}

export const listDeliveryEvents = (kind: DocKind, id: string) => get<DeliveryEvent[]>(`/${kind}/${enc(id)}/delivery-events`)
export const emailDocument = (kind: DocKind, id: string, b: EmailInput, idempotencyKey: string) =>
  send<EmailResult>("POST", `/${kind}/${enc(id)}/email`, clean(b), { "Idempotency-Key": idempotencyKey })
export const reconcileDelivery = (eventId: string, outcome: "sent" | "not_sent", messageId?: string) =>
  send<unknown>("POST", `/delivery/events/${enc(eventId)}/reconcile`, clean({ outcome, message_id: messageId }))

export const listShareLinks = (kind: DocKind, id: string) => get<ShareLinkRow[]>(`/${kind}/${enc(id)}/share-links`)
export const createShareLink = (kind: DocKind, id: string, expiresInDays?: number) =>
  send<ShareLinkCreated>("POST", `/${kind}/${enc(id)}/share-link`, expiresInDays ? { expires_in_days: expiresInDays } : {})
export const revokeShareLink = (linkId: string) => send<unknown>("POST", `/share-links/${enc(linkId)}/revoke`)

// ---------------------------------------------------------------- movements

export const listMovements = (p: { from?: string; to?: string; customer_id?: string; type?: string; limit?: number } = {}) =>
  get<MovementsResponse>(`/billing/movements${qs({ limit: 200, ...p })}`)

/** Execute a suggested action whose endpoint is "METHOD /path". Returns null when it is not executable. */
export function runSuggestedAction(a: SuggestedAction, extraBody?: Record<string, unknown>): Promise<ActionResult<unknown>> | null {
  if (!a.endpoint) return null
  const m = /^(GET|POST|PUT|PATCH|DELETE)\s+(\/\S*)$/.exec(a.endpoint.trim())
  if (!m) return null
  const method = m[1] as "POST" | "PUT" | "PATCH" | "DELETE" | "GET"
  if (method === "GET") return null
  const body = { ...(a.payload ?? {}), ...(extraBody ?? {}) }
  const headers = /\/email$/.test(m[2]) ? { "Idempotency-Key": newIdempotencyKey() } : undefined
  return send<unknown>(method, m[2], body, headers)
}

// ---------------------------------------------------------------- fee policies

export const listFeePolicies = (p: { active_only?: boolean; trigger?: string; current_only?: boolean } = {}) =>
  get<FeePolicy[] | { items: FeePolicy[] }>(`/fee-policies${qs({ current_only: true, ...p })}`)
export const createFeePolicy = (b: FeePolicyBody) => send<FeePolicy>("POST", "/fee-policies", b)
export const updateFeePolicy = (id: string, b: FeePolicyBody) => send<FeePolicy>("PUT", `/fee-policies/${enc(id)}`, b)
export const deactivateFeePolicy = (id: string) => send<unknown>("DELETE", `/fee-policies/${enc(id)}`)
export const createDefaultFeeTemplate = () => send<FeePolicy>("POST", "/fee-policies/templates/default-24m")
export const simulateFee = (b: SimulateInput) => send<SimulateResult>("POST", "/fee-policies/simulate", clean(b))
export const calculateFee = (b: SimulateInput & { cancellation_id?: string }) =>
  send<FeeCalculation & { created: boolean }>("POST", "/fee-policies/calculate", clean(b))
export const listFeeCalculations = (p: { subscription_id?: string; customer_id?: string; cancellation_id?: string; include_superseded?: boolean }) =>
  get<FeeCalculation[] | { items: FeeCalculation[] }>(`/fee-policies/calculations${qs(p)}`)
export const waiveFeeCalculation = (id: string, b: { reason_code: string; reason: string; percent?: string; amount_zar?: string }) =>
  send<{ waiver: unknown; calculation: FeeCalculation }>("POST", `/fee-policies/calculations/${enc(id)}/waive`, clean(b))
export const invoiceFeeCalculation = (id: string, issue?: boolean) =>
  send<{ created: boolean; invoice_id: string; invoice_number: string; status: string; total_zar: string }>(
    "POST",
    `/fee-policies/calculations/${enc(id)}/invoice`,
    issue === undefined ? {} : { issue },
  )
export const createSnapshot = (b: SnapshotInput) => send<ContractSnapshot>("POST", "/fee-policies/snapshots", clean(b))
export const listSnapshots = (subscriptionId: string) =>
  get<ContractSnapshot[] | { items: ContractSnapshot[] }>(`/fee-policies/snapshots${qs({ subscription_id: subscriptionId, all_versions: true })}`)
