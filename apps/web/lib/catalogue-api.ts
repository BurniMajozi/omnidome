"use client"

import { getSessionSafe } from "@/lib/supabase/client"

/**
 * Product catalogue API client (inventory service, /catalogue). The server owns identity, numbering, the launch
 * gate and the readiness checks; this client only carries data. A failed call throws CatalogueError with the
 * server's message so the UI can show it, never a silent null.
 */

const API_BASE = "/svc/inventory/catalogue"
const FALLBACK_TENANT_ID = "00000000-0000-0000-0000-000000000001"
const FALLBACK_USER_ID = "00000000-0000-0000-0000-000000000001"

export class CatalogueError extends Error {
  status: number
  detail: unknown
  constructor(status: number, message: string, detail?: unknown) {
    super(message)
    this.status = status
    this.detail = detail
  }
}

async function authHeaders(): Promise<Record<string, string>> {
  const { data } = await getSessionSafe()
  const tenantId =
    data.session?.user?.user_metadata?.tenant_id ?? data.session?.user?.app_metadata?.tenant_id ?? FALLBACK_TENANT_ID
  return { "x-tenant-id": tenantId, "x-user-id": data.session?.user?.id ?? FALLBACK_USER_ID }
}

async function call<T>(path: string, init?: RequestInit & { json?: unknown }): Promise<T> {
  const { json, ...rest } = init ?? {}
  const res = await fetch(`${API_BASE}${path}`, {
    cache: "no-store",
    ...rest,
    headers: {
      ...(await authHeaders()),
      ...(json !== undefined ? { "Content-Type": "application/json" } : {}),
      ...(rest.headers ?? {}),
    },
    body: json !== undefined ? JSON.stringify(json) : rest.body,
  })
  if (!res.ok) {
    let detail: unknown
    try {
      detail = (await res.json())?.detail
    } catch {
      detail = undefined
    }
    const message =
      typeof detail === "string"
        ? detail
        : detail && typeof detail === "object" && "message" in detail
          ? String((detail as { message: unknown }).message)
          : Array.isArray(detail)
            ? detail.map((d: { msg?: string }) => d.msg).filter(Boolean).join("; ")
            : `Request failed (${res.status})`
    throw new CatalogueError(res.status, message, detail)
  }
  return res.json() as Promise<T>
}

// ── types (mirror services/inventory/routes/catalogue.py) ───────────────────

export type Status = "draft" | "in_review" | "active" | "archived"
export type Nature = "Digital service" | "Physical item" | "Professional service"
export type Usage = "Customer-facing" | "Internal consumable" | "Company-owned asset"

export interface Cost { name: string; supplier: string; amount: number | string; cadence: "Monthly" | "Once-off" }
export interface Component { product_id: string; qty: number }
export interface Fee {
  id: string
  name: string
  enabled: boolean
  amount: number | string
  cadence: "Once-off" | "Monthly" | "On event"
  mode: "Charge" | "Included" | "Waived"
  invoice_label: string
  policy_ref?: string | null
}
export interface Asset {
  id: string
  name: string
  kind: string
  extension: string
  size: number
  url: string
  alt: string
  visibility: "Internal only" | "Customer portal"
  primary: boolean
  category: string
  version: string
  effective: string
  acceptance: boolean
}
export interface Competitor { name: string; offer: string; price: number | string | null; spec: string; term: string; date: string; source: string }
export interface TestResult { name: string; result: "Pending" | "Pass" | "Fail" | "Waived"; tester: string; date: string; notes: string; evidence: string }
export interface IcasaItem {
  id: string
  kind: "Product" | "Promotion"
  objectives: string
  reasons: string
  effective: string
  promo_start: string
  promo_end: string
  lodged: string
  ref: string
  ack: boolean
}
export interface Definition {
  description: string
  customer_name: string
  down: number | null
  up: number | null
  stock: string
  unit: string
  supplier: string
  price: number | string
  recurring: boolean
  term: number
  launch_date: string | null
  costs: Cost[]
  components: Component[]
  fees: Fee[]
  media: Asset[]
  documents: Asset[]
  policy_refs: string[]
  research: { rows: Competitor[]; kpis: string[] }
  readiness: {
    tests_required: boolean
    tests_exempt_reason: string
    tests: TestResult[]
    icasa: { required: boolean | null; exempt_reason: string; notice: number; items: IcasaItem[] }
  }
}
export interface Check { key: string; label: string; ok: boolean; detail: string }
export interface Economics {
  complete: boolean
  monthly: string
  upfront: string
  horizon?: number
  revenue?: string
  cost?: string
  profit?: string
  margin_pct?: number | null
}
export interface Product {
  id: string
  product_number: string
  name: string
  category: string
  range: string
  family: string
  nature: Nature
  usage: Usage
  owner: string
  status: Status
  definition: Definition
  revision: number
  created_at: string
  updated_at: string
  launched_at: string | null
  checks: Check[]
  ready_to_launch: boolean
  cost_complete: boolean
  economics?: Economics
}
export interface ProductInput {
  name: string
  category: string
  range: string
  family: string
  nature: Nature
  usage: Usage
  owner: string
  product_number?: string | null
  definition: Definition
}
export interface Lists {
  categories: Record<string, string[]>
  families: string[]
  items: { id: string; kind: "category" | "range" | "family"; name: string; parent: string }[]
}
export interface HistoryEvent { id: string; kind: string; actor: string | null; detail: Record<string, unknown>; at: string }

// ── calls ────────────────────────────────────────────────────────────────────

export const listProducts = (q?: { status?: Status; q?: string }) => {
  const p = new URLSearchParams()
  if (q?.status) p.set("status", q.status)
  if (q?.q) p.set("q", q.q)
  return call<Product[]>(`/products${p.toString() ? `?${p}` : ""}`)
}
export const getProduct = (id: string) => call<Product>(`/products/${id}`)
export const createProduct = (body: ProductInput) => call<Product>("/products", { method: "POST", json: body })
export const updateProduct = (id: string, body: Partial<ProductInput> & { expected_revision: number; submit_for_review?: boolean }) =>
  call<Product>(`/products/${id}`, { method: "PATCH", json: body })
export const deleteProduct = (id: string) => call<{ deleted: boolean }>(`/products/${id}`, { method: "DELETE" })
export const launchProduct = (id: string, expected_revision: number) =>
  call<Product>(`/products/${id}/launch`, { method: "POST", json: { expected_revision } })
export const archiveProduct = (id: string, expected_revision: number) =>
  call<{ status: string }>(`/products/${id}/archive`, { method: "POST", json: { expected_revision } })
export const productHistory = (id: string) => call<HistoryEvent[]>(`/products/${id}/history`)
export const previewProduct = (body: ProductInput, productId?: string) =>
  call<{ checks: Check[]; ready_to_launch: boolean; economics?: Economics }>(`/preview${productId ? `?product_id=${productId}` : ""}`, { method: "POST", json: body })

export const getLists = () => call<Lists>("/lists")
export const addListValue = (kind: "category" | "range" | "family", name: string, parent = "") =>
  call<{ id: string }>("/lists", { method: "POST", json: { kind, name, parent } })
export const renameListValue = (id: string, name: string) => call<{ updated_products: number }>(`/lists/${id}`, { method: "PATCH", json: { name } })
export const deleteListValue = (id: string) => call<{ deleted: boolean }>(`/lists/${id}`, { method: "DELETE" })

/** Upload raw bytes (the server validates type, magic bytes and size). Returns the asset metadata. */
export async function uploadAsset(productId: string, file: File): Promise<Pick<Asset, "id" | "name" | "kind" | "extension" | "size" | "url">> {
  return call(`/products/${productId}/assets?filename=${encodeURIComponent(file.name)}`, {
    method: "POST",
    body: file,
    headers: { "Content-Type": "application/octet-stream" },
  })
}
export const deleteAsset = (assetId: string) => call<{ deleted: boolean }>(`/assets/${assetId}`, { method: "DELETE" })

/** Images need the tenant headers, which <img src> cannot send: fetch as a blob and return an object URL. */
const blobCache = new Map<string, Promise<string>>()
export function assetObjectUrl(url: string): Promise<string> {
  if (!url.startsWith("/svc/inventory/catalogue/assets/")) return Promise.resolve(url)
  let hit = blobCache.get(url)
  if (!hit) {
    hit = (async () => {
      const res = await fetch(url, { headers: await authHeaders(), cache: "force-cache" })
      if (!res.ok) throw new CatalogueError(res.status, "Could not load file")
      return URL.createObjectURL(await res.blob())
    })()
    hit.catch(() => blobCache.delete(url))
    blobCache.set(url, hit)
  }
  return hit
}
export async function downloadAsset(a: Pick<Asset, "url" | "name">) {
  const href = await assetObjectUrl(a.url)
  const el = document.createElement("a")
  el.href = href
  el.download = a.name
  el.click()
}

export function blankDefinition(): Definition {
  return {
    description: "", customer_name: "", down: null, up: null, stock: "None", unit: "Each", supplier: "", price: 0, recurring: true,
    term: 24, launch_date: null, costs: [], components: [], fees: [], media: [], documents: [], policy_refs: [],
    research: { rows: [], kpis: [] },
    readiness: { tests_required: true, tests_exempt_reason: "", tests: [], icasa: { required: null, exempt_reason: "", notice: 7, items: [] } },
  }
}
