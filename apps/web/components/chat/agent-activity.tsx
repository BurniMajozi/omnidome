"use client"
import { useState } from "react"
import { Button } from "@/components/ui/button"
import { answerAgentQuestion, decideAgentApproval } from "@/lib/orchestrator-api"

export interface ActivityStep { id: string; title: string; kind: string; status: "running" | "done" | "error"; result_summary?: string; duration_ms?: number }
export interface AgentQuestion { run_id: string; question_id: string; expires_at: string; questions: Array<{ header: string; question: string; options: Array<{label: string; description: string}>; multi_select?: boolean }>; status?: string }
export interface AgentApproval { approval_id: string; summary: string; requested_by_me: boolean; status: string }
export interface Activity { steps: ActivityStep[]; questions: AgentQuestion[]; approvals: AgentApproval[]; status: string; elapsed: number; started: number }
export const emptyActivity = (): Activity => ({ steps: [], questions: [], approvals: [], status: "Starting…", elapsed: 0, started: Date.now() })

export function activityEvent(activity: Activity, name: string, value: Record<string, unknown>): Activity {
  if (name === "omnidome.step" && typeof value.id === "string" && typeof value.title === "string" && ["running", "done", "error"].includes(String(value.status))) {
    const step = value as unknown as ActivityStep
    return { ...activity, steps: activity.steps.some(s => s.id === step.id) ? activity.steps.map(s => s.id === step.id ? step : s) : [...activity.steps, step] }
  }
  if (name === "omnidome.status" && typeof value.text === "string") return { ...activity, status: value.text, elapsed: Number(value.elapsed_ms) || 0 }
  if (name === "omnidome.question" && typeof value.question_id === "string" && Array.isArray(value.questions)) return { ...activity, questions: [...activity.questions.filter(q => q.question_id !== value.question_id), value as unknown as AgentQuestion] }
  if (name === "omnidome.question_resolved") return { ...activity, questions: activity.questions.map(q => q.question_id === value.question_id ? { ...q, status: String(value.status) } : q) }
  if (name === "omnidome.approval" && typeof value.approval_id === "string") return { ...activity, approvals: [...activity.approvals.filter(a => a.approval_id !== value.approval_id), value as unknown as AgentApproval] }
  return activity
}

function QuestionCard({ question, streaming }: { question: AgentQuestion; streaming: boolean }) {
  const [selected, setSelected] = useState<string[][]>(() => question.questions.map(() => []))
  const [other, setOther] = useState<string[]>(() => question.questions.map(() => ""))
  const [busy, setBusy] = useState(false), [error, setError] = useState(""), [sent, setSent] = useState(false)
  const closed = sent || !!question.status || !streaming || Date.now() >= Date.parse(question.expires_at)
  const valid = question.questions.every((_, i) => selected[i].length || other[i].trim())
  async function answer() {
    setBusy(true); setError("")
    try { await answerAgentQuestion(question.run_id, question.question_id, question.questions.map((q, i) => ({ question: q.question, selected: selected[i], other: other[i].trim() || null }))); setSent(true) }
    catch (err) { setError(err instanceof Error ? err.message : "Could not send your answer. Retry.") }
    finally { setBusy(false) }
  }
  return <section aria-label="Agent question" className="space-y-3 rounded-md border border-primary/30 bg-background p-3">
    {question.questions.map((q, i) => <fieldset key={i} disabled={closed || busy} className="space-y-2"><legend className="text-sm font-medium">{q.question}</legend>
      <div className="space-y-2">{q.options.map(o => <label key={o.label} className="flex cursor-pointer items-start gap-2 rounded border p-2 text-xs">
        <input type={q.multi_select ? "checkbox" : "radio"} name={`${question.question_id}-${i}`} checked={selected[i].includes(o.label)} onChange={e => setSelected(prev => prev.map((v, n) => n !== i ? v : q.multi_select ? e.target.checked ? [...v, o.label] : v.filter(x => x !== o.label) : [o.label]))} className="mt-0.5" />
        <span><strong>{o.label}</strong><span className="block text-muted-foreground">{o.description}</span></span>
      </label>)}</div>
      <label className="block text-xs">Other answer<input className="mt-1 w-full rounded border bg-background p-2" maxLength={500} value={other[i]} onChange={e => setOther(prev => prev.map((v, n) => n === i ? e.target.value : v))} /></label>
    </fieldset>)}
    {error && <p role="alert" className="text-xs text-destructive">{error}</p>}
    {closed ? <p className="text-xs text-muted-foreground">{sent || question.status === "answered" ? "Answer submitted" : "Question closed"}</p> : <Button size="sm" disabled={!valid || busy} onClick={() => void answer()}>{busy ? "Sending…" : "Send answers"}</Button>}
  </section>
}

function ApprovalCard({ approval }: { approval: AgentApproval }) {
  const [status, setStatus] = useState(approval.status), [busy, setBusy] = useState(false), [error, setError] = useState("")
  async function decide(action: "approve" | "reject") {
    setBusy(true); setError("")
    try { await decideAgentApproval(approval.approval_id, action); setStatus(action === "approve" ? "approved" : "rejected") }
    catch (err) { setError(err instanceof Error ? err.message : "Could not record decision") } finally { setBusy(false) }
  }
  return <section className="space-y-2 rounded border p-3 text-xs" aria-label="Action approval"><p className="font-medium">{approval.summary}</p>
    {status !== "pending" ? <p>{status}</p> : approval.requested_by_me ? <p>Waiting for a manager to approve. You cannot approve your own request.</p> : <div className="flex gap-2"><Button size="sm" disabled={busy} onClick={() => void decide("approve")}>Approve</Button><Button size="sm" variant="outline" disabled={busy} onClick={() => void decide("reject")}>Reject</Button></div>}
    {error && <p role="alert" className="text-destructive">{error}</p>}
  </section>
}

export function AgentActivity({ activity, streaming }: { activity: Activity; streaming: boolean }) {
  return <div className="mb-3 space-y-3">
    <details open={streaming} className="rounded-md border bg-background/50 p-2">
      <summary className="cursor-pointer text-xs font-medium"><span role={streaming ? "status" : undefined}>{streaming ? activity.status : `Worked for ${Math.max(1, Math.round(activity.elapsed / 1000))}s`}</span></summary>
      <ol className="mt-2 space-y-2 border-l pl-3">{activity.steps.map(step => <li key={step.id} className="text-xs"><span aria-label={step.status}>{step.status === "done" ? "✓" : step.status === "error" ? "!" : "•"}</span> {step.title}<span className="ml-2 text-muted-foreground">{step.duration_ms != null ? `${Math.round(step.duration_ms / 1000)}s` : "working"}</span>{step.result_summary && <p className="mt-0.5 text-muted-foreground">{step.result_summary}</p>}</li>)}</ol>
    </details>
    {activity.questions.map(q => <QuestionCard key={q.question_id} question={q} streaming={streaming} />)}
    {activity.approvals.map(a => <ApprovalCard key={a.approval_id} approval={a} />)}
  </div>
}
