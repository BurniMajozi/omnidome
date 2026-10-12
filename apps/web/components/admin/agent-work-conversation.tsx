"use client"
import { useEffect, useRef, useState } from "react"
import Link from "next/link"
import { CheckCircle2, Loader2, Pause, Play, Send } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { Input } from "@/components/ui/input"
import { FormattedMarkdown } from "@/components/chat/ag-ui-chat"
import { workApi, workLabel, usd, type WorkThread } from "@/lib/agent-work-api"

export function AgentWorkConversation({ thread, agentName, refresh }: { thread: WorkThread; agentName: string; refresh: () => Promise<void> }) {
  const [message, setMessage] = useState("")
  const [ceiling, setCeiling] = useState("2")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")
  const key = useRef<{ message: string; id: string } | null>(null)
  const end = useRef<HTMLDivElement>(null)
  const latest = thread.turns[thread.turns.length - 1]
  const working = [...thread.turns].reverse().find(t => ["running", "pause_requested"].includes(t.status)) || latest
  const total = thread.turns.reduce((sum, turn) => sum + (turn.actual_cost_usd ?? turn.estimated_cost_usd), 0)
  useEffect(() => { end.current?.scrollIntoView({ block: "nearest" }) }, [thread.turns.length])
  async function act(action: string) {
    setBusy(true); setError("")
    try { await workApi(`/jobs/${working.id}/${action}`, {}); await refresh() }
    catch (e) { setError(e instanceof Error ? e.message : "Could not update this run") }
    finally { setBusy(false) }
  }
  async function send() {
    if (!message.trim() || busy) return
    setBusy(true); setError("")
    try {
      if (key.current?.message !== message.trim()) key.current = { message: message.trim(), id: crypto.randomUUID() }
      await workApi(`/jobs/${thread.id}/messages`, { message: message.trim(), request_key: key.current.id, max_cost_usd: Number(ceiling) })
      setMessage(""); key.current = null; await refresh()
    } catch (e) { setError(e instanceof Error ? e.message : "Could not send follow-up") }
    finally { setBusy(false) }
  }
  return <section className="rounded-xl border bg-card flex flex-col min-w-0" aria-label="Agent task conversation">
    <header className="border-b p-4 space-y-2">
      <div className="flex flex-wrap items-start justify-between gap-3"><div className="min-w-0"><h3 className="text-base font-semibold break-words">{thread.title}</h3><p className="text-xs text-muted-foreground">{agentName} · persistent conversation · {thread.turns.length} turn{thread.turns.length === 1 ? "" : "s"}</p></div>
        <div className="flex flex-wrap gap-2">
          {["queued", "running"].includes(working.status) && <Button size="sm" variant="outline" disabled={busy} onClick={() => void act("pause")}><Pause className="mr-1 h-3 w-3" />Pause</Button>}
          {["paused", "interrupted", "failed", "awaiting_hitl"].includes(working.status) && <Button size="sm" variant="outline" disabled={busy} onClick={() => void act("resume")}><Play className="mr-1 h-3 w-3" />Resume</Button>}
          {["awaiting_review", "max_iterations"].includes(working.status) && <Button size="sm" variant="outline" disabled={busy} onClick={() => void act("accept")}><CheckCircle2 className="mr-1 h-3 w-3" />Mark done</Button>}
        </div>
      </div>
      <p role="status" className="text-sm font-medium">{workLabel(working.status)}{working.status === "running" && working.activity?.text ? ` · ${working.activity.text}` : ""}</p>
      <p className="text-xs text-muted-foreground">Conversation spend {usd(total)} · {working.total_steps} completed tool calls · {working.total_tokens.toLocaleString()} tokens. Progress below shows public actions, not hidden model reasoning.</p>
    </header>
    <div className="max-h-[65vh] min-h-64 overflow-y-auto p-4 space-y-5">
      {thread.turns.map(turn => <article key={turn.id} className="space-y-3">
        <div className="ml-auto max-w-[90%] rounded-lg bg-primary/10 p-3 text-sm whitespace-pre-wrap break-words"><p className="mb-1 text-xs font-medium text-muted-foreground">You · {new Date(turn.created_at).toLocaleString("en-ZA")}</p>{turn.objective}</div>
        <div className="rounded-lg border p-3 space-y-3">
          <div className="flex flex-wrap gap-2 items-center text-xs text-muted-foreground"><span className="font-medium text-foreground">{agentName}</span><span>{workLabel(turn.status)}</span><span>{usd(turn.actual_cost_usd ?? turn.estimated_cost_usd)} {turn.cost_source === "provider" ? "reported" : "estimated"} · ceiling {usd(turn.max_cost_usd)}</span></div>
          {turn.activity && <details open={turn.status === "running" || turn.status === "pause_requested"}>
            <summary className="cursor-pointer text-xs font-medium">Activity · {turn.activity.items.length} recorded steps</summary>
            <ol className="mt-2 space-y-2 border-l pl-3">{turn.activity.items.map(step => <li key={step.id} className="flex gap-2 text-xs">{step.status === "running" && turn.status === "running" ? <Loader2 className="h-3 w-3 animate-spin shrink-0" /> : <span className="text-muted-foreground">•</span>}<span>{step.title} <span className="text-muted-foreground">· {step.status === "done" ? "completed" : step.status === "error" ? "could not complete" : turn.status === "running" ? "in progress" : "not completed"}{step.result_summary ? ` · ${step.result_summary}` : ""}</span></span></li>)}</ol>
          </details>}
          {turn.result?.final_output ? <div className="text-sm break-words"><FormattedMarkdown content={turn.result.final_output} /></div> : <p className="text-sm text-muted-foreground">{turn.status === "queued" ? "Queued. A follow-up waits for the preceding turn to finish or pause." : turn.status === "running" ? "The agent is working. You can send your next direction below." : "No response was saved for this turn."}</p>}
          {turn.error && <p className="text-xs text-destructive">{turn.error}</p>}
          {turn.status === "awaiting_hitl" && <Link href="/dashboard/admin/agents#approvals" className="text-xs text-primary">Review the pending action in the approval inbox</Link>}
          <details className="text-xs text-muted-foreground"><summary className="cursor-pointer">Run evidence and context</summary><p className="mt-1">Run {turn.id} · memory {turn.context_used?.memory_status || "not reported"} · skills {turn.context_used?.skills?.join(", ") || "not reported"}</p><p>Models: {turn.model_calls?.map(call => `${call.provider} · ${call.model}`).join(", ") || "not reported"}</p></details>
        </div>
      </article>)}
      <div ref={end} />
    </div>
    <form onSubmit={e => { e.preventDefault(); void send() }} className="border-t p-4 space-y-2">
      <label className="block text-sm font-medium" htmlFor="agent-follow-up">Continue the conversation</label>
      <Textarea id="agent-follow-up" value={message} onChange={e => setMessage(e.target.value)} maxLength={4000} rows={3} placeholder="Tell the agent what to change, ask a question, or explain what to try next…" />
      <div className="flex flex-wrap items-end justify-between gap-3"><label className="text-xs text-muted-foreground">Follow-up run ceiling (USD)<Input className="mt-1 w-28" aria-label="Follow-up run ceiling in USD" type="number" min="0.01" max="100" step="0.01" value={ceiling} onChange={e => setCeiling(e.target.value)} required /></label><Button type="submit" disabled={busy || !message.trim()}>{busy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Send className="mr-2 h-4 w-4" />}Send follow-up</Button></div>
      <p className="text-xs text-muted-foreground">Previous responses stay in context. Each follow-up is a new bounded run; earlier tool calls are not replayed. Pause takes effect between turns.</p>
      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
    </form>
  </section>
}
