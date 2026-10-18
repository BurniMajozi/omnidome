"use client"

import { inventoryCall } from "@/lib/catalogue-api"

/**
 * Suppliers, supplier performance, returns and the product-mix profitability. One supplier master serves both the
 * Product panel (where the buyer maintains suppliers and the products they supply) and the Stock panel (where
 * purchase orders are raised and deliveries are received and rated).
 */

export interface SupplierRecord {
  id: string
  code: string
  name: string
  contact_person: string | null
  email: string | null
  phone: string | null
  address: string | null
  tax_id: string | null
  account_number: string | null
  payment_terms: string | null
  lead_time_days: number
  spend_limit: number | string | null
  is_active: boolean
  notes: string | null
  created_at: string
}
export interface SupplierInput {
  code: string
  name: string
  contact_person?: string | null
  email?: string | null
  phone?: string | null
  address?: string | null
  tax_id?: string | null
  account_number?: string | null
  payment_terms?: string | null
  lead_time_days?: number
  spend_limit?: number | string | null
  notes?: string | null
  is_active?: boolean
}

const clean = <T extends object>(o: T) => Object.fromEntries(Object.entries(o).map(([k, v]) => [k, v === "" ? null : v])) as T

export const listSuppliers = (activeOnly = false) => inventoryCall<SupplierRecord[]>(`/suppliers?active_only=${activeOnly}`)
export const createSupplier = (b: SupplierInput) => inventoryCall<SupplierRecord>("/suppliers", { method: "POST", json: clean(b) })
export const updateSupplier = (id: string, b: Partial<SupplierInput>) => inventoryCall<SupplierRecord>(`/suppliers/${id}`, { method: "PATCH", json: clean(b) })
export const deleteSupplier = (id: string) => inventoryCall<void>(`/suppliers/${id}`, { method: "DELETE" })

// ── performance ──────────────────────────────────────────────────────────────

export interface Metrics {
  deliveries: number
  receipts: number
  orders_open: number
  on_time_rate: number | null
  on_time_known: number
  avg_days_late: number | null
  avg_lead_days: number | null
  units_ordered: number
  units_received: number
  units_accepted: number
  units_rejected: number
  units_returned: number
  fill_rate: number | null
  rejection_rate: number | null
  return_rate: number | null
  avg_rating: number | null
  ratings: number
  avg_unit_cost: number | null
  top_rejection_reasons: { reason: string; units: number }[]
  score: number | null
  grade: string
}
export interface ScorecardRow {
  id: string
  name: string
  code: string
  is_active: boolean
  lead_time_days: number
  payment_terms: string | null
  metrics: Metrics
}
export interface Scorecards { months: number; min_deliveries: number; weights: Record<string, number>; suppliers: ScorecardRow[] }
export interface SupplierDetail {
  supplier: { id: string; name: string; code: string; is_active: boolean; lead_time_days: number; payment_terms: string | null }
  months: number
  metrics: Metrics
  by_product: { product_id: string; catalogue_product_id: string | null; product_number: string; name: string; metrics: Metrics }[]
  deliveries: { po_number: string; order_date: string; expected_delivery: string | null; first_received: string | null; days_late: number | null; status: string }[]
  returns: { id: string; product_id: string; quantity: number; reason: string; status: string; credit_note_ref: string | null; returned_at: string }[]
}
export interface ProductSupplierPerformance {
  product_id: string
  product_number: string
  stock_linked: boolean
  months: number
  suppliers: { supplier_id: string; name: string; preferred: boolean; supplier_sku: string; unit_cost: number; cadence: string; quoted_lead_days: number | null; moq: number | null; metrics: Metrics }[]
  best_supplier_id: string | null
  best_reason: string | null
}

export const getScorecards = (months = 12) => inventoryCall<Scorecards>(`/supplier-performance?months=${months}`)
export const getSupplierDetail = (id: string, months = 12) => inventoryCall<SupplierDetail>(`/supplier-performance/${id}?months=${months}`)
export const getProductSupplierPerformance = (productId: string, months = 12) =>
  inventoryCall<ProductSupplierPerformance>(`/catalogue/products/${productId}/supplier-performance?months=${months}`)

// ── receiving: ratings and returns ──────────────────────────────────────────

export const evaluateDelivery = (grId: string, b: { rating: number; late_reason?: string; comment?: string }) =>
  inventoryCall<{ rating: number }>(`/goods-receipts/${grId}/evaluation`, { method: "POST", json: b })
export interface ReturnInput {
  supplier_id: string
  product_id: string
  quantity: number
  reason: string
  warehouse_id?: string | null
  credit_note_ref?: string | null
  adjust_stock: boolean
}
export const returnToSupplier = (b: ReturnInput) => inventoryCall<{ id: string; stock_adjusted: boolean }>("/supplier-returns", { method: "POST", json: clean(b) })

// ── purchasing from the catalogue ───────────────────────────────────────────

export interface PurchasableProduct {
  catalogue_product_id: string
  inventory_product_id: string
  product_number: string
  name: string
  unit: string
  stock: string | null
  sources: { supplier_id: string; supplier_name: string; unit_cost: number | string; lead_time_days: number | null; moq: number | null; preferred: boolean; supplier_sku: string }[]
  offer: { supplier_id: string; unit_cost: number | string; lead_time_days: number | null; moq: number | null; supplier_sku: string } | null
  preferred: { supplier_id: string; supplier_name: string; unit_cost: number | string } | null
}
export const getPurchasable = (supplierId?: string) => inventoryCall<PurchasableProduct[]>(`/catalogue/purchasable-products${supplierId ? `?supplier_id=${supplierId}` : ""}`)

// ── profitability of the product mix ────────────────────────────────────────

export interface ProfitRow {
  id: string
  product_number: string
  name: string
  category: string
  range: string
  nature: string
  price: number
  recurring: boolean
  horizon_months: number | null
  revenue: number
  cost: number
  profit: number
  margin_pct: number | null
  cost_complete: boolean
  recurring_cost: number
  upfront_cost: number
  volume_90d: number | null
  preferred_supplier: string | null
  best_supplier: { supplier_id: string; name: string; unit_cost: number; score: number | null } | null
  suppliers: number
}
export interface Profitability {
  months: number
  products: ProfitRow[]
  mix: { products: number; costed: number; unweighted_margin_pct: number | null; weighted_margin_pct: number | null; weighted_products: number; note: string }
}
export const getProfitability = (months = 12) => inventoryCall<Profitability>(`/catalogue/profitability?months=${months}`)

export const pct = (v: number | null | undefined) => (v === null || v === undefined ? "—" : `${(v * 100).toFixed(v >= 0.995 || v === 0 ? 0 : 1)}%`)
