/** Sourcing: supplier discovery, RFI/RFQ rounds, quote scoring and KPI-driven reorder suggestions (inventory service, /sourcing). */
import { inventoryCall } from "@/lib/catalogue-api"

export interface Weights { price: number; lead_time: number; performance: number; completeness: number }
export interface Reorder { cover_days: number; lookback_days: number; min_margin_pct: number; max_requests_per_scan: number }
export interface ProcurementProtocol {
  allow_internal: boolean
  allow_external: boolean
  max_suppliers_per_request: number
  min_quotes_before_award: number
  outreach_requires_approval: boolean
  allow_self_approval: boolean
  share_target_price: boolean
  rfq_budget_limit_zar: number
  min_supplier_score: number
  reply_window_days: number
  mailbox_id: string | null
  weights: Weights
  reorder: Reorder
}
export interface ProtocolState { protocol: ProcurementProtocol; defaults: ProcurementProtocol; customised: boolean; updated_at: string | null }

export interface Prospect {
  id: string; product_id: string | null; name: string; domain: string; website: string; email: string | null; phone: string | null
  country: string | null; summary: string; fit: number | null; status: "new" | "invited" | "converted" | "dismissed"; supplier_id: string | null
}
export interface Discovery { id: string; status: "running" | "done" | "failed"; error?: string | null; summary?: string | null; prospects: number; items?: Prospect[]; note?: string }
export interface Candidate {
  supplier_id: string; name: string; email: string | null; kind: "internal" | "external"; current_source: boolean
  score: number | null; eligible: boolean; reason: string | null
}
export interface Candidates { suppliers: Candidate[]; prospects: Prospect[]; protocol: { max_suppliers: number } }

export type RequestStatus = "draft" | "pending_approval" | "approved" | "sent" | "awarded" | "closed" | "cancelled"
export interface SourcingRequest {
  id: string; number: string; kind: "RFI" | "RFQ"; product_id: string | null; product?: string | null; title: string; quantity: number | null
  target_price: number | null; needed_by: string | null; subject: string; body: string; drafted_by: "ai" | "template" | "user"
  status: RequestStatus; source: string; created_at: string | null; sent_at: string | null; approved_at: string | null
  awarded_invitee_id: string | null; award_note: string; created_by_agent: string | null; replies?: number; invited?: number
}
export interface Invitee { id: string; supplier_id: string | null; prospect_id: string | null; name: string; email: string | null; kind: "internal" | "external"; status: string; error: string | null; sent_at: string | null }
export interface QuoteResponse { id: string; invitee_id: string; unit_price: number | null; lead_time_days: number | null; moq: number | null; valid_until: string | null; notes: string; declined: boolean }
export interface RequestDetail extends SourcingRequest { invitees: Invitee[]; responses: QuoteResponse[] }
export interface CompareRow {
  invitee_id: string; name: string; kind: string; supplier_id: string | null; status: string; unit_price: number | null; lead_time_days: number | null
  moq: number | null; valid_until: string | null; notes: string; declined: boolean; score: number | null; flags: string[]; total?: number; margin_pct?: number | null
  breakdown?: { price_pts: number; lead_pts: number; performance_pts: number; completeness_pts: number; track_record: boolean }
}
export interface Comparison { request: SourcingRequest; rows: CompareRow[]; best: string | null; replies: number; needed: number; ready_to_award: boolean; weights: Weights }
export interface ReorderItem {
  product_id: string; product_number: string; name: string; offer_mode: string; available: number; on_order: number; sales_per_day: number
  days_of_cover: number | null; suggested_qty: number; preferred_supplier_id: string | null; unit_cost: number | null; estimated_spend: number | null
  margin_pct: number | null; supplier_score: number | null; needs_quotes: boolean; flags: string[]; open_request: boolean
}
export interface ParsedReply { unit_price: number | null; lead_time_days: number | null; moq: number | null; valid_until: string | null; declined: boolean; notes: string; method: "ai" | "patterns"; model: string | null }
export interface SourcingSupplier { id: string; name: string; email: string | null; contact_person: string | null; lead_time_days: number; kind: "internal" | "external"; score: number | null; deliveries: number }

const j = (json: unknown) => ({ method: "POST", json })
export const getProtocol = () => inventoryCall<ProtocolState>("/sourcing/protocol")
export const saveProtocol = (p: ProcurementProtocol) => inventoryCall<{ protocol: ProcurementProtocol }>("/sourcing/protocol", { method: "PUT", json: p })
export const resetProtocol = () => inventoryCall<{ protocol: ProcurementProtocol }>("/sourcing/protocol", { method: "DELETE" })
export const listSourcingSuppliers = () => inventoryCall<SourcingSupplier[]>("/sourcing/suppliers")
export const setSupplierKind = (id: string, kind: "internal" | "external") => inventoryCall(`/sourcing/suppliers/${id}/kind`, { method: "PUT", json: { kind } })
export const startDiscovery = (product_id: string, note = "") => inventoryCall<{ id: string; status: string }>("/sourcing/discoveries", j({ product_id, note }))
export const getDiscovery = (id: string) => inventoryCall<Discovery>(`/sourcing/discoveries/${id}`)
export const listProspects = (product_id?: string) => inventoryCall<Prospect[]>(`/sourcing/prospects${product_id ? `?product_id=${product_id}` : ""}`)
export const patchProspect = (id: string, body: Partial<Pick<Prospect, "name" | "email" | "phone">> & { status?: "new" | "dismissed" }) => inventoryCall<Prospect>(`/sourcing/prospects/${id}`, { method: "PATCH", json: body })
export const convertProspect = (id: string) => inventoryCall<{ supplier_id: string; name: string }>(`/sourcing/prospects/${id}/convert`, { method: "POST" })
export const getCandidates = (product_id: string) => inventoryCall<Candidates>(`/sourcing/candidates?product_id=${product_id}`)
export const createRequest = (b: { kind: "RFI" | "RFQ"; product_id: string; quantity?: number | null; target_price?: number | null; needed_by?: string | null; invitees: { supplier_id?: string; prospect_id?: string; email?: string }[]; ai?: boolean }) =>
  inventoryCall<RequestDetail>("/sourcing/requests", j(b))
export const listRequests = () => inventoryCall<SourcingRequest[]>("/sourcing/requests")
export const getRequest = (id: string) => inventoryCall<RequestDetail>(`/sourcing/requests/${id}`)
export const editRequest = (id: string, b: { subject?: string; body?: string; regenerate?: boolean }) => inventoryCall<SourcingRequest>(`/sourcing/requests/${id}`, { method: "PATCH", json: b })
export const requestAction = (id: string, action: "submit" | "approve" | "reject" | "close") => inventoryCall<SourcingRequest>(`/sourcing/requests/${id}/${action}`, { method: "POST" })
export const sendRequest = (id: string) => inventoryCall<{ sent: number; failed: number; status: string; error?: string | null; invitees: Invitee[] }>(`/sourcing/requests/${id}/send`, { method: "POST" })
export const recordResponse = (id: string, b: { invitee_id: string; unit_price?: number | null; lead_time_days?: number | null; moq?: number | null; valid_until?: string | null; notes?: string; declined?: boolean; source?: "manual" | "parsed" }) =>
  inventoryCall<QuoteResponse>(`/sourcing/requests/${id}/responses`, j(b))
export const parseReply = (id: string, text: string) => inventoryCall<ParsedReply>(`/sourcing/requests/${id}/parse-reply`, j({ text }))
export const compareRequest = (id: string) => inventoryCall<Comparison>(`/sourcing/requests/${id}/compare`)
export interface AwardOptions { reason?: string; add_source?: boolean; make_preferred?: boolean; create_po?: boolean; warehouse_id?: string | null }
export interface AwardResult {
  supplier_id: string; name: string; unit_price: number; lead_time_days: number | null; quantity: number | null; flags: string[]; product_id: string | null
  source: { status: "added" | "updated" | "unchanged" | "skipped"; preferred?: boolean; note: string } | null
  purchase_order: { status: "drafted" | "skipped"; id?: string; po_number?: string; quantity?: number; note: string } | null
}
export const awardRequest = (id: string, invitee_id: string, o: AwardOptions = {}) =>
  inventoryCall<AwardResult>(`/sourcing/requests/${id}/award`, j({ invitee_id, reason: "", ...o }))
export const getReorder = () => inventoryCall<{ items: ReorderItem[]; cover_days: number; lookback_days: number; note: string }>("/sourcing/reorder-suggestions")
export const runScan = () => inventoryCall<{ created: { request_id: string; number: string; product: string; quantity: number; invited: number }[]; skipped: { product: string; why: string }[]; note: string }>("/sourcing/automation/run", { method: "POST" })
