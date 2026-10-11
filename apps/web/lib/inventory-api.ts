"use client"

import { getSessionSafe } from "@/lib/supabase/client"
import { sendJson, type ActionResult } from "@/lib/api-result"
import { fetchLoadable } from "@/lib/service-fetch"
import type { Loadable } from "@/lib/service-state"

/**
 * Inventory API client — suppliers, purchase orders, goods receipts.
 * Proxies through the Next.js API routes to the inventory service.
 */

const API_BASE = "/svc/inventory"
const FALLBACK_TENANT_ID = "00000000-0000-0000-0000-000000000001"
const FALLBACK_USER_ID = "00000000-0000-0000-0000-000000000001"

async function getAuthHeaders(): Promise<Record<string, string>> {
  const { data } = await getSessionSafe()
  const tenantId =
    data.session?.user?.user_metadata?.tenant_id ??
    data.session?.user?.app_metadata?.tenant_id ??
    FALLBACK_TENANT_ID
  const userId = data.session?.user?.id ?? FALLBACK_USER_ID
  return { "x-tenant-id": tenantId, "x-user-id": userId }
}

async function fetchInventory<T>(path: string, init?: RequestInit): Promise<T | null> {
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      cache: "no-store",
      headers: { ...(await getAuthHeaders()), "Content-Type": "application/json" },
      ...init,
    })
    if (!res.ok) {
      console.warn(`Inventory API error ${res.status} for ${path}`)
      return null
    }
    if (res.status === 204) return null
    return res.json()
  } catch (error) {
    console.warn(`Inventory API unreachable for ${path}`, error)
    return null
  }
}

// ── Types ─────────────────────────────────────────────────────────────

export interface Supplier {
  id: string
  tenant_id: string
  code: string
  name: string
  contact_person: string | null
  email: string | null
  phone: string | null
  address: string | null
  tax_id: string | null
  payment_terms: string | null
  lead_time_days: number
  is_active: boolean
  notes: string | null
  created_at: string
}

export interface SupplierInput {
  code: string
  name: string
  contact_person?: string
  email?: string
  phone?: string
  address?: string
  tax_id?: string
  payment_terms?: string
  lead_time_days?: number
  notes?: string
}

export interface PurchaseOrderItem {
  id: string
  product_id: string
  quantity_ordered: number
  quantity_received: number
  unit_cost_zar: string
  total_cost_zar: string
}

export interface PurchaseOrder {
  id: string
  tenant_id: string
  supplier_id: string
  warehouse_id: string
  po_number: string
  status: "draft" | "submitted" | "approved" | "partially_received" | "received" | "cancelled"
  subtotal_zar: string
  tax_zar: string
  total_zar: string
  order_date: string
  expected_delivery: string | null
  received_at: string | null
  created_by: string | null
  approved_by: string | null
  notes: string | null
  created_at: string
  items: PurchaseOrderItem[]
}

export interface PurchaseOrderItemInput {
  product_id: string
  quantity_ordered: number
  unit_cost_zar: string
}

export interface PurchaseOrderInput {
  supplier_id: string
  warehouse_id: string
  expected_delivery?: string
  notes?: string
  items: PurchaseOrderItemInput[]
}

export interface GoodsReceiptItemInput {
  po_item_id: string
  quantity_received: number
  quantity_rejected?: number
  rejection_reason?: string
  serial_numbers?: string[]
}

export interface GoodsReceiptInput {
  supplier_delivery_note?: string
  supplier_invoice_number?: string
  notes?: string
  items: GoodsReceiptItemInput[]
}

export interface GoodsReceipt {
  id: string
  po_id: string | null
  warehouse_id: string
  gr_number: string
  status: string
  received_by: string | null
  received_at: string | null
  supplier_delivery_note: string | null
  supplier_invoice_number: string | null
  notes: string | null
  created_at: string
}

// ── Suppliers ───────────────────────────────────────────────────────────

export async function listSuppliers(): Promise<Supplier[]> {
  return (await fetchInventory<Supplier[]>("/suppliers")) ?? []
}

export async function createSupplier(input: SupplierInput): Promise<Supplier | null> {
  return fetchInventory<Supplier>("/suppliers", { method: "POST", body: JSON.stringify(input) })
}

// ── Purchase Orders ─────────────────────────────────────────────────────

export async function listPurchaseOrders(status?: string): Promise<PurchaseOrder[]> {
  const qs = status ? `?status=${encodeURIComponent(status)}` : ""
  return (await fetchInventory<PurchaseOrder[]>(`/purchase-orders${qs}`)) ?? []
}

export async function getPurchaseOrder(id: string): Promise<PurchaseOrder | null> {
  return fetchInventory<PurchaseOrder>(`/purchase-orders/${id}`)
}

export async function createPurchaseOrder(input: PurchaseOrderInput): Promise<PurchaseOrder | null> {
  return fetchInventory<PurchaseOrder>("/purchase-orders", { method: "POST", body: JSON.stringify(input) })
}

export async function submitPurchaseOrder(id: string): Promise<PurchaseOrder | null> {
  return fetchInventory<PurchaseOrder>(`/purchase-orders/${id}/submit`, { method: "POST" })
}

export async function approvePurchaseOrder(id: string): Promise<PurchaseOrder | null> {
  return fetchInventory<PurchaseOrder>(`/purchase-orders/${id}/approve`, { method: "POST" })
}

export async function createGoodsReceipt(
  poId: string,
  input: GoodsReceiptInput,
): Promise<GoodsReceipt | null> {
  return fetchInventory<GoodsReceipt>(`/purchase-orders/${poId}/goods-receipts`, {
    method: "POST",
    body: JSON.stringify(input),
  })
}

// ── Supplier bank details + purchase order payments ────────────────────
// Status-preserving (unlike fetchInventory) so the UI can show 402/409/422/502 messages from `detail`.

export interface SupplierBankDetails {
  configured: boolean
  bank_code?: string
  account_name?: string
  account_last4?: string
}
export interface PoPayment {
  id: string
  po_id: string
  amount_zar: number
  fee_zar: number
  status: "pending" | "processing" | "paid" | "failed"
  supplier_invoice_ref: string | null
  message: string | null
  created_at: string
}
export interface PoPayments {
  po_total_zar: number
  paid_zar: number
  outstanding_zar: number
  payments: PoPayment[]
}
/** Body of the 402 returned when the payout wallet cannot cover a supplier payment. */
export interface PoWalletShortfall {
  message: string
  required_zar: number
  balance_zar: number
  shortfall_zar: number
  fee_zar: number
}

export const getSupplierBankDetails = (supplierId: string): Promise<Loadable<SupplierBankDetails>> =>
  fetchLoadable<SupplierBankDetails>(`${API_BASE}/suppliers/${encodeURIComponent(supplierId)}/bank-details`)
/** The account number is sent once; only the last 4 digits ever come back. */
export const saveSupplierBankDetails = (supplierId: string, input: { bank_code: string; account_name: string; account_number: string }) =>
  sendJson<SupplierBankDetails>(`${API_BASE}/suppliers/${encodeURIComponent(supplierId)}/bank-details`, "PUT", input)
export const getPoPayments = (poId: string): Promise<Loadable<PoPayments>> => fetchLoadable<PoPayments>(`${API_BASE}/purchase-orders/${encodeURIComponent(poId)}/payments`)
export interface PayPoResult {
  ok: boolean
  status: number
  payment: PoPayment | null
  /** The server's `detail` string (409/400/502...) or a generic message. */
  message: string | null
  /** Set on HTTP 402. */
  shortfall: PoWalletShortfall | null
}
/** Hand-rolled (not sendJson) because a 402 carries an object `detail` that callers need in full. */
export async function payPurchaseOrder(poId: string, input: { amount_zar?: number; supplier_invoice_ref?: string }): Promise<PayPoResult> {
  let res: Response
  try {
    res = await fetch(`${API_BASE}/purchase-orders/${encodeURIComponent(poId)}/payments`, {
      method: "POST",
      cache: "no-store",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
      signal: AbortSignal.timeout(30_000),
    })
  } catch {
    return { ok: false, status: 0, payment: null, message: "Could not confirm the result. Use Refresh status before paying again.", shortfall: null }
  }
  let body: unknown = null
  try {
    body = await res.json()
  } catch {
    body = null
  }
  if (res.ok) return { ok: true, status: res.status, payment: body as PoPayment, message: null, shortfall: null }
  const detail = (body as { detail?: unknown } | null)?.detail
  if (res.status === 402 && detail && typeof detail === "object") {
    const d = detail as Partial<PoWalletShortfall>
    return {
      ok: false,
      status: 402,
      payment: null,
      message: null,
      shortfall: {
        message: typeof d.message === "string" ? d.message : "The payout wallet does not have enough funds for this payment.",
        required_zar: Number(d.required_zar) || 0,
        balance_zar: Number(d.balance_zar) || 0,
        shortfall_zar: Number(d.shortfall_zar) || 0,
        fee_zar: Number(d.fee_zar) || 0,
      },
    }
  }
  const fallback = res.status === 403 ? "Not permitted: a purchasing manager is required." : `Payment request failed (HTTP ${res.status})`
  return { ok: false, status: res.status, payment: null, message: typeof detail === "string" && detail ? detail : fallback, shortfall: null }
}
export const syncPoPayments = (poId: string): Promise<ActionResult<{ paid_zar: number; payments: PoPayment[] }>> =>
  sendJson(`${API_BASE}/purchase-orders/${encodeURIComponent(poId)}/payments/sync`, "POST", {})
