"use client"

/**
 * Browser-side client for the communication service, always through the same-origin /api/chat/** proxy
 * (which signs the verified identity; the browser never talks to the service directly).
 *
 * Every call resolves to a CommResult (never throws): status null = network failure/timeout, `detail` is the
 * server's own text. A 401 is retried once after refreshing the Supabase session (the usual cause is a token
 * that expired or was not attached yet; a second 401 is a real "sign in again").
 */
import { supabase } from "@/lib/supabase/client"
import { detailText } from "@/lib/comm-messages"

export interface CommResult<T = unknown> {
  ok: boolean
  status: number | null
  data: T | null
  detail: string | null
  /** machine code from the proxy (unauthenticated | upstream_error | service_unreachable ...) */
  error: string | null
}

const REFRESH_TIMEOUT_MS = 4_000

async function refreshSession(): Promise<void> {
  let timer: ReturnType<typeof setTimeout> | undefined
  try {
    await Promise.race([
      supabase.auth.refreshSession(),
      new Promise((resolve) => { timer = setTimeout(resolve, REFRESH_TIMEOUT_MS) }),
    ])
  } catch {
    /* fall through: the retry will simply 401 again */
  } finally {
    if (timer) clearTimeout(timer)
  }
}

export async function commRequest<T = unknown>(
  method: "GET" | "POST" | "PATCH" | "PUT" | "DELETE",
  url: string,
  body?: unknown,
  opts: { signal?: AbortSignal; timeoutMs?: number; noRetry?: boolean } = {},
): Promise<CommResult<T>> {
  const attempt = async (): Promise<CommResult<T>> => {
    try {
      const res = await fetch(url, {
        method,
        headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
        body: body !== undefined ? JSON.stringify(body) : undefined,
        cache: "no-store",
        signal: opts.signal
          ? AbortSignal.any([opts.signal, AbortSignal.timeout(opts.timeoutMs ?? 20_000)])
          : AbortSignal.timeout(opts.timeoutMs ?? 20_000),
      })
      const payload = res.status === 204 ? null : await res.json().catch(() => null)
      const error = typeof payload?.error === "string" ? payload.error : null
      return { ok: res.ok, status: res.status, data: payload as T | null, detail: res.ok ? null : detailText(payload), error }
    } catch {
      return { ok: false, status: null, data: null, detail: null, error: null }
    }
  }
  let r = await attempt()
  if (r.status === 401 && !opts.noRetry && !opts.signal?.aborted) {
    await refreshSession()
    r = await attempt()
  }
  return r
}

export const HISTORY_PAGE_SIZE = 50

export function historyUrl(channelId: string, before?: string | null): string {
  const q = new URLSearchParams({ channel_id: channelId, limit: String(HISTORY_PAGE_SIZE) })
  if (before) q.set("before", before)
  return `/api/chat/messages?${q.toString()}`
}

export const commApi = {
  channels: (signal?: AbortSignal) => commRequest("GET", "/api/chat/channels", undefined, { signal }),
  history: (channelId: string, before?: string | null, signal?: AbortSignal) =>
    commRequest("GET", historyUrl(channelId, before), undefined, { signal }),
  send: (channelId: string, content: string, clientMsgId: string) =>
    commRequest("POST", "/api/chat/messages", { channel_id: channelId, content, client_msg_id: clientMsgId }),
  createChannel: (name: string, isPrivate: boolean) => commRequest("POST", "/api/chat/channels", { name, is_private: isPrivate }),
  addMembers: (channelId: string, userIds: string[]) =>
    commRequest("POST", `/api/chat/channels/${encodeURIComponent(channelId)}/members`, { user_ids: userIds }),
  removeMember: (channelId: string, userId: string) =>
    commRequest("DELETE", `/api/chat/channels/${encodeURIComponent(channelId)}/members/${encodeURIComponent(userId)}`),
  deleteChannel: (channelId: string) => commRequest("DELETE", `/api/chat/channels/${encodeURIComponent(channelId)}`),
  approvals: () => commRequest("GET", "/api/chat/approvals?page_size=100"),
  createApproval: (b: { channel_id: string; title: string; description?: string | null; message_id?: string | null }) =>
    commRequest("POST", "/api/chat/approvals", b),
  decideApproval: (id: string, status: "approved" | "rejected" | "cancelled") =>
    commRequest("POST", `/api/chat/approvals/${encodeURIComponent(id)}/decide`, { status }),
  escalations: () => commRequest("GET", "/api/chat/escalations?page_size=100"),
  createEscalation: (b: { channel_id: string; reason: string; ticket_id?: string | null }) =>
    commRequest("POST", "/api/chat/escalations", b),
  setEscalationStatus: (id: string, status: string) =>
    commRequest("PATCH", `/api/chat/escalations/${encodeURIComponent(id)}/status`, { status }),
}
