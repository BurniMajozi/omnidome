"use client"

import { useEffect, useState } from "react"
import { Bot, Loader2, Send } from "lucide-react"
import { Button } from "@/components/ui/button"

export interface WorkflowProposal {
  name: string
  description: string
  definition: { nodes: any[]; edges: any[] }
  trigger_event?: string | null
  schedule_cron?: string | null
}

export function WorkflowDesigner({ current, onProposal }: {
  current: unknown; onProposal: (draft: WorkflowProposal) => void
}) {
  const [prompt, setPrompt] = useState("")
  const [history, setHistory] = useState<{ role: string; content: string }[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")
  const [warnings, setWarnings] = useState<string[]>([])
  const [sessionId, setSessionId] = useState("")
  const [sessions, setSessions] = useState<{ id: string; title: string }[]>([])
  const loadSessions = () => fetch("/api/orchestrator/workflows/design/sessions", { cache: "no-store" }).then(r => r.ok ? r.json() : null).then(data => setSessions(data?.data || [])).catch(() => {})
  useEffect(() => { void loadSessions() }, [])
  async function reopen(id: string) {
    if (!id || busy) return
    setBusy(true); setError("")
    try { const response = await fetch(`/api/orchestrator/workflows/design/sessions/${id}`, { cache: "no-store" }); const saved = await response.json(); if (!response.ok) throw new Error(saved.detail || "Could not reopen the design chat"); setSessionId(id); setHistory(saved.history || []); setWarnings([]); if (saved.draft) onProposal(saved.draft) }
    catch (e) { setError(e instanceof Error ? e.message : "Could not reopen the design chat") }
    finally { setBusy(false) }
  }
  async function design() {
    if (prompt.trim().length < 3 || busy) return
    const request = prompt.trim()
    setBusy(true); setError("")
    try {
      const response = await fetch("/api/orchestrator/workflows/design", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt: request, current, history: history.slice(-10), ...(sessionId ? { session_id: sessionId } : {}) }),
      })
      const result = await response.json()
      if (!response.ok) throw new Error(typeof result.detail === "string" ? result.detail : Array.isArray(result.detail) ? result.detail.map((item: { msg?: string }) => item.msg || "Invalid request").join("; ") : "Could not design the workflow")
      onProposal(result.draft)
      setSessionId(result.session_id || "")
      setHistory(result.history || [...history, { role: "user", content: request }, { role: "assistant", content: result.message }].slice(-12))
      void loadSessions()
      setWarnings(result.warnings || [])
      setPrompt("")
    } catch (e) { setError(e instanceof Error ? e.message : "Designer unavailable") }
    finally { setBusy(false) }
  }
  return <section className="rounded-xl border border-border bg-card p-4 space-y-3" aria-label="Workflow design chat">
    <div className="flex items-center gap-2"><Bot className="h-4 w-4 text-primary" /><h3 className="text-sm font-semibold">Describe your automation</h3></div>
    <div className="flex flex-wrap gap-2 items-center"><label className="text-xs min-w-0 flex-1">Saved design chats<select aria-label="Reopen workflow design chat" value={sessionId} disabled={busy} onChange={e => void reopen(e.target.value)} className="block w-full rounded border bg-background p-2 mt-1"><option value="">Choose a saved conversation</option>{sessions.map(session => <option key={session.id} value={session.id}>{session.title}</option>)}</select></label><Button size="sm" variant="outline" disabled={busy} onClick={() => { setSessionId(""); setHistory([]); setWarnings([]); setError(""); setPrompt("") }}>New design chat</Button></div>
    <p className="text-xs text-muted-foreground">Tell the assistant what should trigger the workflow and what should happen next. Your proposal appears on the chart for review.</p>
    {history.length > 0 && <div className="max-h-48 overflow-y-auto space-y-2" aria-live="polite">
      {history.map((turn, i) => <p key={i} className={`rounded-lg p-2 text-sm whitespace-pre-wrap ${turn.role === "user" ? "bg-primary/10" : "bg-muted"}`}><span className="font-medium">{turn.role === "user" ? "You" : "Assistant"}: </span>{turn.content}</p>)}
    </div>}
    <form onSubmit={e => { e.preventDefault(); void design() }} className="space-y-2">
      <textarea aria-label="What do you want to automate?" value={prompt} onChange={e => setPrompt(e.target.value)} maxLength={4000} rows={3}
        placeholder="When platform credits run low, summarise usage and notify the owner."
        className="w-full rounded-lg border border-input bg-background p-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" />
      <div className="flex flex-wrap items-center justify-between gap-2"><span className="text-xs text-muted-foreground">Draft only · nothing saved or activated automatically</span>
        <Button size="sm" type="submit" disabled={busy || prompt.trim().length < 3}>{busy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Send className="mr-2 h-4 w-4" />}{busy ? "Designing…" : history.length ? "Refine proposal" : "Design workflow"}</Button>
      </div>
    </form>
    {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
    {warnings.map((warning, i) => <p key={i} className="text-xs text-muted-foreground">{warning}</p>)}
  </section>
}
