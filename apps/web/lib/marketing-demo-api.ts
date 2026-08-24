"use client"

/**
 * Marketing demo API client — campaigns, prospect (WhatsApp contact) import +
 * segments, lead scores, and WhatsApp broadcasts. Proxies through /svc/marketing.
 * Self-contained (does not import marketing-api.ts, which has a wrong bulk path)
 * so the demo page is correct and independent.
 */

import { supabase } from "@/lib/supabase/client"

const API_BASE = "/svc/marketing"
const FALLBACK_TENANT = "00000000-0000-0000-0000-000000000001"
const FALLBACK_USER = "00000000-0000-0000-0000-000000000001"

async function headers(): Promise<Record<string, string>> {
  const { data } = await supabase.auth.getSession()
  const tenant =
    data.session?.user?.user_metadata?.tenant_id ??
    data.session?.user?.app_metadata?.tenant_id ??
    FALLBACK_TENANT
  const user = data.session?.user?.id ?? FALLBACK_USER
  return { "x-tenant-id": tenant, "x-user-id": user, "Content-Type": "application/json" }
}

async function mk<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { cache: "no-store", ...init, headers: { ...(await headers()), ...(init?.headers ?? {}) } })
  if (!res.ok) {
    const body = await res.text().catch(() => "")
    throw new Error(`${res.status}: ${body || res.statusText}`)
  }
  if (res.status === 204) return undefined as T
  return res.json()
}

// ── Types ──────────────────────────────────────────────────────────────
export interface Campaign {
  id: string
  name: string
  channel: string
  status: string
  description?: string | null
  budget_zar?: number | null
  created_at?: string
}
export interface Contact {
  id: string
  name: string
  phone_number: string
  email?: string | null
  tags?: string[] | null
  opt_in_status?: boolean
}
export interface Broadcast {
  id: string
  name: string
  template_name: string
  content: string
  status: string
  recipient_count?: number
}
export interface BroadcastStats {
  broadcast_id: string
  name?: string
  recipient_count: number
  sent_count: number
  delivered_count: number
  read_count: number
  failed_count: number
  delivery_rate?: number
  read_rate?: number
}
export interface LeadScore {
  id?: string
  name?: string
  email?: string
  score?: number
  grade?: string
  [k: string]: unknown
}

// ── Campaigns ──────────────────────────────────────────────────────────
export const listCampaigns = () => mk<Campaign[]>(`/campaigns`)
export const createCampaign = (data: { name: string; channel: string; description?: string; budget_zar?: number }) =>
  mk<Campaign>(`/campaigns`, { method: "POST", body: JSON.stringify(data) })
export const deleteCampaign = (id: string) => mk<void>(`/campaigns/${id}`, { method: "DELETE" })

// ── Prospects (WhatsApp contacts) + segments ───────────────────────────
export interface ContactInput { name: string; phone_number: string; email?: string; tags?: string[] }
export const bulkImportContacts = (contacts: ContactInput[]) =>
  mk<{ imported: number; errors: { index: number; error: string }[] }>(`/whatsapp/contacts/bulk-import`, {
    method: "POST",
    body: JSON.stringify({ contacts }),
  })
export const listContacts = () => mk<Contact[]>(`/whatsapp/contacts`)

// ── WhatsApp broadcasts ────────────────────────────────────────────────
export const listBroadcasts = () => mk<Broadcast[]>(`/whatsapp/broadcasts`)
export const createBroadcast = (data: { name: string; template_name: string; content: string; recipient_ids?: string[] }) =>
  mk<Broadcast>(`/whatsapp/broadcasts`, { method: "POST", body: JSON.stringify(data) })
export const sendBroadcast = (id: string) => mk<{ status: string }>(`/whatsapp/broadcasts/${id}/send`, { method: "POST" })
export const getBroadcastStats = (id: string) => mk<BroadcastStats>(`/whatsapp/broadcasts/${id}/stats`)

// ── Lead scores ────────────────────────────────────────────────────────
export const listLeadScores = () => mk<LeadScore[]>(`/leads/scores`)

/** Parse a simple CSV of prospects into contact inputs. Header row required.
 *  Recognised columns (case-insensitive, aliased): name, phone/phone_number/cell,
 *  email, segment/tag/type. */
export function parseProspectCsv(text: string): ContactInput[] {
  const lines = text.replace(/\r/g, "").split("\n").filter((l) => l.trim())
  if (lines.length < 2) return []
  const headers = lines[0].split(",").map((h) => h.trim().toLowerCase())
  const idx = (names: string[]) => headers.findIndex((h) => names.includes(h))
  const iName = idx(["name", "prospect", "company", "contact"])
  const iPhone = idx(["phone_number", "phone", "cell", "mobile", "number"])
  const iEmail = idx(["email", "e-mail"])
  const iSeg = idx(["segment", "tag", "type", "category"])
  const out: ContactInput[] = []
  for (let i = 1; i < lines.length; i++) {
    const c = lines[i].split(",").map((v) => v.trim())
    const name = iName >= 0 ? c[iName] : ""
    const phone = iPhone >= 0 ? c[iPhone] : ""
    if (!name || !phone) continue
    out.push({
      name,
      phone_number: phone,
      email: iEmail >= 0 ? c[iEmail] || undefined : undefined,
      tags: iSeg >= 0 && c[iSeg] ? [c[iSeg]] : undefined,
    })
  }
  return out
}
