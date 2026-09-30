"use client"

import { getSessionSafe } from "@/lib/supabase/client"
import type { ApprovalFailure } from "@/lib/approvals-derive"

/**
 * Status-aware approve / reject for the Executive Approval Queue.
 * lib/orchestrator-api.ts throws only the detail text, which loses the HTTP
 * status the queue needs to tell 403 / 409 / 5xx apart, so the decision calls
 * live here. Identity: same Bearer the orchestrator proxy resolves server-side.
 */

export type DecideResult = { ok: true } | ({ ok: false } & ApprovalFailure)

export async function decideApproval(
  id: string,
  action: "approve" | "reject",
  body: { notes?: string; reason?: string },
): Promise<DecideResult> {
  let res: Response
  try {
    const { data } = await getSessionSafe()
    const headers: Record<string, string> = { "Content-Type": "application/json" }
    if (data.session?.access_token) headers.Authorization = `Bearer ${data.session.access_token}`
    res = await fetch(`/api/orchestrator/approvals/${encodeURIComponent(id)}/${action}`, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
      cache: "no-store",
      signal: AbortSignal.timeout(20_000),
    })
  } catch {
    return { ok: false, status: null, message: "" }
  }
  if (res.ok) return { ok: true }
  let message = ""
  try {
    const text = await res.text()
    try {
      const j = JSON.parse(text)
      message = typeof j?.detail === "string" ? j.detail : typeof j?.error === "string" ? j.error : ""
    } catch {
      message = ""
    }
  } catch {
    /* unreadable body */
  }
  return { ok: false, status: res.status, message }
}
