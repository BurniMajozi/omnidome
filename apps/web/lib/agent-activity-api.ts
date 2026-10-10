"use client"

import { getSessionSafe } from "@/lib/supabase/client"
import { answerErrorMessage, clip, type AnswerPayload } from "@/lib/agent-activity"

// Status-aware calls for the inline question/approval cards. lib/orchestrator-api.ts throws only a generic
// message and loses the HTTP status the cards need (403 / 404 / 409 / 422). Same Bearer + proxy as the rest.
const BASE = "/api/orchestrator"

async function authed(url: string, init: RequestInit): Promise<Response> {
  const { data } = await getSessionSafe()
  const headers = new Headers(init.headers)
  headers.set("Content-Type", "application/json")
  if (data.session?.access_token) headers.set("Authorization", `Bearer ${data.session.access_token}`)
  return fetch(url, { ...init, headers, cache: "no-store", signal: AbortSignal.timeout(20_000) })
}

export type AnswerResult = { ok: true } | { ok: false; status: number | null; message: string }

export async function submitAgentAnswer(runId: string, payload: AnswerPayload): Promise<AnswerResult> {
  try {
    const res = await authed(`${BASE}/agents/runs/${encodeURIComponent(runId)}/answer`, { method: "POST", body: JSON.stringify(payload) })
    if (res.ok) return { ok: true }
    return { ok: false, status: res.status, message: answerErrorMessage(res.status) }
  } catch {
    return { ok: false, status: null, message: answerErrorMessage(null) }
  }
}

export interface ApprovalDetails {
  status: string
  title: string
  summary: string
  tool: string
  context: string
  args: string
  jevAction: string
  jevReason: string
  jevScore: number | null
  rejectionReason: string
}

const HIDDEN_ARG = /^_/

/** GET /approvals/{id}. Args are shown as escaped text for the approver; internal `_`-keys are dropped and the text is clipped. */
export async function fetchApprovalDetails(id: string): Promise<ApprovalDetails | null> {
  try {
    const res = await authed(`${BASE}/approvals/${encodeURIComponent(id)}`, { method: "GET" })
    if (!res.ok) return null
    const j = (await res.json()) as Record<string, unknown>
    const argsObj = j.arguments && typeof j.arguments === "object" ? (j.arguments as Record<string, unknown>) : {}
    const jev = (argsObj._jev_gate ?? j.jev_gate) as Record<string, unknown> | undefined
    const shown = Object.fromEntries(Object.entries(argsObj).filter(([k]) => !HIDDEN_ARG.test(k)))
    const score = jev ? Number(jev.risk_score) : NaN
    return {
      status: typeof j.status === "string" ? j.status : "pending",
      title: clip(j.title, 200),
      summary: clip(j.summary, 400),
      tool: typeof j.tool_name === "string" ? j.tool_name : "",
      context: clip(j.context, 400),
      args: Object.keys(shown).length ? clip(JSON.stringify(shown, null, 2), 1200) : "",
      jevAction: jev && typeof jev.action === "string" ? jev.action : "",
      jevReason: jev ? clip(jev.reason, 400) : "",
      jevScore: Number.isFinite(score) ? score : null,
      rejectionReason: clip(j.rejection_reason, 300),
    }
  } catch {
    return null
  }
}
