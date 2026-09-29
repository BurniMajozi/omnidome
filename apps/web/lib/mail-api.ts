"use client"

import { getSessionSafe } from "@/lib/supabase/client"

/**
 * Agent Mail API client — mailboxes and agent emails.
 * Proxies through the /svc/communication rewrite to
 * services/communication/routes/mail.py (mounted at /api/v1/mail/*).
 */

const API_BASE = "/svc/communication/api/v1/mail"
const FALLBACK_TENANT_ID = "00000000-0000-0000-0000-000000000001"
const FALLBACK_USER_ID = "00000000-0000-0000-0000-000000000001"
const FETCH_TIMEOUT_MS = 15000

export interface MailboxRow {
  id: string
  tenant_id: string
  agent_type: string
  email_address: string
  display_name: string
  is_active: boolean
  inbound_channel_id?: string | null
  auto_reply_enabled: boolean
  created_at: string
  updated_at: string
}

export interface AgentEmailRow {
  id: string
  tenant_id: string
  mailbox_id: string
  direction: string
  sender: string
  recipient: string
  subject: string
  body_text: string
  body_html?: string | null
  status: string
  agent_response?: string | null
  headers: Record<string, unknown>
  message_id?: string | null
  created_at: string
}

export interface EmailFilters {
  mailbox_id?: string
  direction?: "inbound" | "outbound"
  status?: string
}

export interface MailResult<T> {
  ok: boolean
  status: number
  data: T | null
  error: string | null
}

async function getAuthHeaders(): Promise<Record<string, string>> {
  const { data } = await getSessionSafe()
  const tenantId =
    data.session?.user?.user_metadata?.tenant_id ??
    data.session?.user?.app_metadata?.tenant_id ??
    FALLBACK_TENANT_ID
  const userId = data.session?.user?.id ?? FALLBACK_USER_ID
  return { "x-tenant-id": tenantId, "x-user-id": userId }
}

async function fetchMail<T>(path: string, init?: RequestInit): Promise<MailResult<T>> {
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      cache: "no-store",
      signal: AbortSignal.timeout(FETCH_TIMEOUT_MS),
      headers: { ...(await getAuthHeaders()), "Content-Type": "application/json" },
      ...init,
    })
    if (!res.ok) {
      let detail = `HTTP ${res.status}`
      try {
        const body = await res.json()
        if (typeof body?.detail === "string") detail = body.detail
      } catch {
        /* ignore non-JSON error body */
      }
      return { ok: false, status: res.status, data: null, error: detail }
    }
    return { ok: true, status: res.status, data: (await res.json()) as T, error: null }
  } catch (error) {
    const msg = error instanceof Error ? error.message : "Mail service unreachable"
    return { ok: false, status: 0, data: null, error: msg }
  }
}

export function listMailboxes(): Promise<MailResult<MailboxRow[]>> {
  return fetchMail<MailboxRow[]>("/mailboxes")
}

export function listEmails(filters: EmailFilters = {}): Promise<MailResult<AgentEmailRow[]>> {
  const qs = new URLSearchParams()
  if (filters.mailbox_id) qs.set("mailbox_id", filters.mailbox_id)
  if (filters.direction) qs.set("direction", filters.direction)
  if (filters.status) qs.set("status", filters.status)
  const q = qs.toString()
  return fetchMail<AgentEmailRow[]>(`/emails${q ? `?${q}` : ""}`)
}

export function createMailbox(body: {
  agent_type: string
  email_address: string
  display_name: string
  auto_reply_enabled?: boolean
}): Promise<MailResult<MailboxRow>> {
  return fetchMail<MailboxRow>("/mailboxes", { method: "POST", body: JSON.stringify(body) })
}

export interface SendEmailBody {
  mailbox_id: string
  to: string[]
  cc?: string[]
  bcc?: string[]
  subject: string
  body_text: string
  body_html?: string
  in_reply_to_email_id?: string
}

export function sendEmail(body: SendEmailBody): Promise<MailResult<AgentEmailRow>> {
  return fetchMail<AgentEmailRow>("/send", {
    method: "POST",
    body: JSON.stringify({ cc: [], bcc: [], ...body }),
    signal: AbortSignal.timeout(45000),
  })
}

export function replyToEmail(emailId: string, body_text: string): Promise<MailResult<AgentEmailRow>> {
  return fetchMail<AgentEmailRow>(`/emails/${encodeURIComponent(emailId)}/reply`, {
    method: "POST",
    body: JSON.stringify({ body_text }),
    signal: AbortSignal.timeout(45000),
  })
}

export function approveAgentReply(emailId: string): Promise<MailResult<AgentEmailRow>> {
  return fetchMail<AgentEmailRow>(`/emails/${encodeURIComponent(emailId)}/approve-agent-reply`, {
    method: "POST",
    signal: AbortSignal.timeout(45000),
  })
}

export function updateEmail(
  emailId: string,
  patch: { is_read?: boolean; is_starred?: boolean },
): Promise<MailResult<AgentEmailRow>> {
  return fetchMail<AgentEmailRow>(`/emails/${encodeURIComponent(emailId)}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  })
}

export async function deleteEmail(emailId: string): Promise<MailResult<null>> {
  try {
    const res = await fetch(`${API_BASE}/emails/${encodeURIComponent(emailId)}`, {
      method: "DELETE",
      cache: "no-store",
      signal: AbortSignal.timeout(FETCH_TIMEOUT_MS),
      headers: await getAuthHeaders(),
    })
    if (!res.ok) {
      let detail = `HTTP ${res.status}`
      try {
        const b = await res.json()
        if (typeof b?.detail === "string") detail = b.detail
      } catch {
        /* ignore */
      }
      return { ok: false, status: res.status, data: null, error: detail }
    }
    return { ok: true, status: res.status, data: null, error: null }
  } catch (error) {
    return { ok: false, status: 0, data: null, error: error instanceof Error ? error.message : "Mail service unreachable" }
  }
}
