// Pure logic for the agent chat "live activity" UI (docs/agui-events.md). No React, no DOM, no aliased imports,
// so it runs under `node --test lib/agent-activity.test.mjs`. All server text is treated as untrusted: it is
// only ever returned as plain strings (React escapes it) and clipped.

import type { ArtifactLinkItem } from "./artifact-links"
// .ts extension lets node --test load this file; the bundler resolves it as normal.
// @ts-ignore TS5097: extension imports are not enabled in tsconfig (noEmit, bundler resolution)
import { sanitizeArtifactItem } from "./artifact-links.ts"

export type StepStatus = "running" | "done" | "error"
export const STEP_KINDS = ["skill", "memory", "knowledge", "reasoning", "data", "tool", "verify", "approval"] as const
export type StepKind = (typeof STEP_KINDS)[number]

export interface ActivityStep {
  id: string
  title: string
  kind: StepKind | string
  status: StepStatus
  detail?: string
  started_at?: string | null
  ended_at?: string | null
  duration_ms?: number | null
  result_summary?: string | null
  meta?: Record<string, unknown>
}

export interface QuestionOption { label: string; description: string }
export interface QuestionItem { header: string; question: string; options: QuestionOption[]; multi_select: boolean }
export interface AgentQuestion {
  run_id: string
  question_id: string
  questions: QuestionItem[]
  expires_at: string
  ttl_seconds?: number
  /** answered | expired | cancelled once omnidome.question_resolved arrives */
  status?: string
}
export interface AgentApproval {
  approval_id: string
  reference?: string
  tool?: string
  summary: string
  requested_by_me: boolean
  status: string
  risk?: string
}

export interface Activity {
  steps: ActivityStep[]
  questions: AgentQuestion[]
  approvals: AgentApproval[]
  /** Latest omnidome.status text (replaced, never appended). */
  status: string
  /** ms. Live runs derive it from `started`; set when the run ends. */
  elapsed: number
  started: number
  /** True once any omnidome.* CUSTOM event arrived. False for Hermes/legacy runs. */
  hasCustom: boolean
  finished: boolean
  cancelled: boolean
}

const MAX_TEXT = 700

export function clip(value: unknown, max = MAX_TEXT): string {
  if (typeof value !== "string") return ""
  return value.length > max ? `${value.slice(0, max - 1)}…` : value
}

export function emptyActivity(now: number = Date.now()): Activity {
  return { steps: [], questions: [], approvals: [], status: "", elapsed: 0, started: now, hasCustom: false, finished: false, cancelled: false }
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v)
}

function parseStep(value: Record<string, unknown>): ActivityStep | null {
  if (typeof value.id !== "string" || !value.id || typeof value.title !== "string") return null
  const status = String(value.status)
  if (status !== "running" && status !== "done" && status !== "error") return null
  const dur = Number(value.duration_ms)
  return {
    id: value.id,
    title: clip(value.title, 200),
    kind: typeof value.kind === "string" ? value.kind : "tool",
    status,
    detail: clip(value.detail) || undefined,
    started_at: typeof value.started_at === "string" ? value.started_at : null,
    ended_at: typeof value.ended_at === "string" ? value.ended_at : null,
    duration_ms: value.duration_ms != null && Number.isFinite(dur) ? dur : null,
    result_summary: clip(value.result_summary, 300) || null,
    meta: isRecord(value.meta) ? value.meta : {},
  }
}

function parseQuestion(value: Record<string, unknown>): AgentQuestion | null {
  if (typeof value.question_id !== "string" || !Array.isArray(value.questions)) return null
  const questions: QuestionItem[] = []
  for (const raw of value.questions) {
    if (!isRecord(raw) || typeof raw.question !== "string" || !Array.isArray(raw.options)) continue
    const options: QuestionOption[] = []
    for (const o of raw.options) {
      if (isRecord(o) && typeof o.label === "string" && o.label) options.push({ label: clip(o.label, 200), description: clip(o.description, 400) })
    }
    questions.push({ header: clip(raw.header, 24), question: raw.question, options, multi_select: raw.multi_select === true })
  }
  if (!questions.length) return null
  return {
    run_id: typeof value.run_id === "string" ? value.run_id : "",
    question_id: value.question_id,
    questions,
    expires_at: typeof value.expires_at === "string" ? value.expires_at : "",
    ttl_seconds: Number.isFinite(Number(value.ttl_seconds)) ? Number(value.ttl_seconds) : undefined,
  }
}

function parseApproval(value: Record<string, unknown>): AgentApproval | null {
  if (typeof value.approval_id !== "string") return null
  return {
    approval_id: value.approval_id,
    reference: typeof value.reference === "string" ? value.reference : undefined,
    tool: typeof value.tool === "string" ? value.tool : undefined,
    summary: clip(value.summary, 400),
    requested_by_me: value.requested_by_me === true,
    status: typeof value.status === "string" ? value.status : "pending",
    risk: typeof value.risk === "string" ? value.risk : undefined,
  }
}

/** Fold one CUSTOM event into the activity. Unknown names / malformed values return the same object. */
export function reduceActivity(activity: Activity, name: unknown, value: unknown): Activity {
  if (typeof name !== "string" || !name.startsWith("omnidome.") || !isRecord(value)) return activity
  switch (name) {
    case "omnidome.step": {
      const step = parseStep(value)
      if (!step) return activity
      const i = activity.steps.findIndex((s) => s.id === step.id)
      const steps = i < 0 ? [...activity.steps, step] : activity.steps.map((s, n) => (n === i ? step : s))
      return { ...activity, steps, hasCustom: true }
    }
    case "omnidome.status": {
      if (typeof value.text !== "string") return activity
      const ms = Number(value.elapsed_ms)
      return { ...activity, status: clip(value.text, 200), elapsed: Number.isFinite(ms) && ms >= 0 ? ms : activity.elapsed, hasCustom: true }
    }
    case "omnidome.question": {
      const q = parseQuestion(value)
      if (!q) return activity
      const i = activity.questions.findIndex((x) => x.question_id === q.question_id)
      const questions = i < 0 ? [...activity.questions, q] : activity.questions.map((x, n) => (n === i ? { ...q, status: x.status } : x))
      return { ...activity, questions, hasCustom: true }
    }
    case "omnidome.question_resolved": {
      if (typeof value.question_id !== "string") return activity
      const status = typeof value.status === "string" ? value.status : "answered"
      return { ...activity, questions: activity.questions.map((q) => (q.question_id === value.question_id ? { ...q, status } : q)), hasCustom: true }
    }
    case "omnidome.approval": {
      const a = parseApproval(value)
      if (!a) return activity
      const i = activity.approvals.findIndex((x) => x.approval_id === a.approval_id)
      const approvals = i < 0 ? [...activity.approvals, a] : activity.approvals.map((x, n) => (n === i ? a : x))
      return { ...activity, approvals, hasCustom: true }
    }
    default:
      return activity // omnidome.thinking and anything future: ignored
  }
}

/** Mark the run over. `cancelled` = user pressed Stop. Running steps are left as-is (UI renders them as stopped). */
export function finishActivity(activity: Activity, now: number = Date.now(), cancelled = false): Activity {
  if (activity.finished) return cancelled && !activity.cancelled ? { ...activity, cancelled: true } : activity
  return { ...activity, finished: true, cancelled, elapsed: Math.max(0, now - activity.started) }
}

export function formatDuration(ms: number): string {
  if (!Number.isFinite(ms) || ms < 0) return "0s"
  const s = Math.round(ms / 1000)
  if (s < 1) return ms < 100 ? "<1s" : "1s"
  if (s < 60) return `${s}s`
  const m = Math.floor(s / 60)
  return `${m}m ${s % 60}s`
}

export function elapsedMs(activity: Activity, now: number = Date.now()): number {
  return activity.finished ? activity.elapsed : Math.max(0, now - activity.started)
}

/** 'Worked for 14s · 6 steps' (or 'Stopped after 14s · 6 steps'). */
export function summaryText(activity: Activity): string {
  const dur = formatDuration(activity.elapsed)
  const n = activity.steps.length
  const head = activity.cancelled ? `Stopped after ${dur}` : `Worked for ${dur}`
  return n > 0 ? `${head} · ${n} ${n === 1 ? "step" : "steps"}` : head
}

/** Live one-liner: the server status text, or a plain fallback for runs without CUSTOM events. */
export function liveStatusText(activity: Activity, now: number = Date.now()): string {
  if (activity.status) return activity.status
  return activity.hasCustom ? "Working…" : `Working… ${formatDuration(elapsedMs(activity, now))}`
}

/** Duration for a step row: server value, else (for running steps) live from started_at. */
export function stepDurationLabel(step: ActivityStep, now: number = Date.now()): string {
  if (step.duration_ms != null) return formatDuration(step.duration_ms)
  if (step.status === "running" && step.started_at) {
    const t = Date.parse(step.started_at)
    if (Number.isFinite(t)) return formatDuration(now - t)
  }
  return ""
}

const TOOL_LABELS: Record<string, string> = {
  "data.query": "Queried data",
  "data.datasets": "Listed datasets",
  "knowledge.search": "Searched memory",
  "memory.search": "Searched memory",
  "memory.recall": "Recalled memory",
  "memory.write": "Saved to memory",
  "consult_specialist": "Consulted a specialist",
  "ask_user": "Asked you a question",
  "web.search": "Searched the web",
}

/** Human title for a raw tool name. Unknown names become readable Title Case; never raw JSON. */
export function humanizeTool(name: unknown): string {
  const raw = typeof name === "string" ? name.trim() : ""
  if (!raw) return "Ran a tool"
  const key = raw.toLowerCase()
  if (TOOL_LABELS[key]) return TOOL_LABELS[key]
  const words = key.replace(/[^a-z0-9]+/g, " ").trim().split(" ").filter(Boolean)
  if (!words.length) return "Ran a tool"
  return words.map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(" ")
}

/** Citation chips from a knowledge step's meta (cards|sources|citations), only items with a safe same-origin link. */
export function citationsFromSteps(steps: ActivityStep[]): ArtifactLinkItem[] {
  const out: ArtifactLinkItem[] = []
  const seen = new Set<string>()
  for (const s of steps) {
    if (s.kind !== "knowledge" || !s.meta) continue
    for (const k of ["cards", "sources", "citations"]) {
      const list = s.meta[k]
      if (!Array.isArray(list)) continue
      for (const raw of list) {
        const it = sanitizeArtifactItem(raw)
        if (it && !seen.has(it.href)) { seen.add(it.href); out.push(it) }
      }
    }
  }
  return out.slice(0, 8)
}

// ── Questions ─────────────────────────────────────────────────────────────

export interface AnswerDraft { selected: string[]; other: string }
export interface AnswerPayload { question_id: string; answers: Array<{ question: string; selected: string[]; other: string | null }> }
export const MAX_OTHER = 500

export function isAnswerComplete(q: QuestionItem, d: AnswerDraft | undefined): boolean {
  if (!d) return false
  return d.selected.length > 0 || d.other.trim().length > 0
}

export function allAnswered(question: AgentQuestion, drafts: AnswerDraft[]): boolean {
  return question.questions.every((q, i) => isAnswerComplete(q, drafts[i]))
}

/** Contract: one answer per question in order, exact question text, selected labels that exist (max 1 unless multi). */
export function buildAnswerPayload(question: AgentQuestion, drafts: AnswerDraft[]): AnswerPayload {
  return {
    question_id: question.question_id,
    answers: question.questions.map((q, i) => {
      const d = drafts[i] ?? { selected: [], other: "" }
      const valid = d.selected.filter((l, n) => q.options.some((o) => o.label === l) && d.selected.indexOf(l) === n)
      const selected = q.multi_select ? valid : valid.slice(0, 1)
      const other = d.other.trim().slice(0, MAX_OTHER)
      return { question: q.question, selected, other: other || null }
    }),
  }
}

export function answerSummary(question: AgentQuestion, drafts: AnswerDraft[]): string[] {
  return question.questions.map((q, i) => {
    const d = drafts[i]
    const parts = [...(d?.selected ?? [])]
    if (d?.other.trim()) parts.push(`Other: ${d.other.trim().slice(0, MAX_OTHER)}`)
    return `${q.header ? `${q.header}: ` : ""}${parts.join(", ") || "-"}`
  })
}

export function secondsUntil(expiresAt: string, now: number = Date.now()): number | null {
  const t = Date.parse(expiresAt)
  return Number.isFinite(t) ? Math.max(0, Math.floor((t - now) / 1000)) : null
}

export function formatCountdown(seconds: number): string {
  if (seconds <= 0) return "expired"
  if (seconds < 60) return `${seconds}s left`
  const m = Math.floor(seconds / 60), s = seconds % 60
  return s ? `${m}m ${s}s left` : `${m}m left`
}

export function answerErrorMessage(status: number | null): string {
  switch (status) {
    case 403: return "Only the person who started this run can answer its questions."
    case 404: return "This question has expired or the run was cancelled."
    case 409: return "This question was already answered."
    case 422: return "That answer was not accepted. Pick an option or write a shorter answer."
    case null: return "Could not reach the server. Try again."
    default: return `Could not send your answer (error ${status}). Try again.`
  }
}

export function decisionErrorMessage(status: number | null, serverMessage: string): string {
  const msg = clip(serverMessage, 300)
  if (status === 403) return msg || "You do not have permission to decide this approval."
  if (status === 409) return msg || "This approval was already decided."
  if (status === 404) return "This approval no longer exists."
  if (status === null) return "Could not reach the server. Try again."
  return msg || `Could not record the decision (error ${status}).`
}

/** Tone for the risk chip: 'high' | 'medium' | 'low' | 'review'. */
export function riskTone(risk: string | undefined, jevScore?: number | null): "high" | "medium" | "low" | "review" {
  const s = typeof jevScore === "number" && Number.isFinite(jevScore) ? jevScore : Number(risk)
  if (Number.isFinite(s)) return s >= 4 ? "high" : s >= 2.5 ? "medium" : "low"
  const r = (risk ?? "").toLowerCase()
  if (r === "high" || r === "critical") return "high"
  if (r === "medium") return "medium"
  if (r === "low") return "low"
  return "review"
}
