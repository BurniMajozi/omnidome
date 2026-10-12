"use client"

import { useEffect, useRef, useState } from "react"
import Link from "next/link"
import { Loader2, Play, Plus, Workflow } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog"

interface Attached {
  workflow_id: string; name: string; status: string; execution_status: string
  approval_id?: string; run_id?: string; error?: string; output?: unknown
}
interface Choice { id: string; name: string; description?: string; status: string; trigger_event?: string; schedule_enabled?: boolean }
async function api(path: string, init?: RequestInit) {
  const response = await fetch(`/api/orchestrator/${path}`, init)
  const data = await response.json()
  if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Workflow request failed")
  return data
}
const json = (body: unknown, method = "POST") => ({ method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })
const pending = (state: string) => ["running", "awaiting_approval", "approved"].includes(state)

export function ChatWorkflows({ conversationId, onConversation, open, onOpenChange, chatBusy }: {
  conversationId: string | null; onConversation: (id: string) => void
  open: boolean; onOpenChange: (open: boolean) => void; chatBusy: boolean
}) {
  const [attached, setAttached] = useState<Attached[]>([])
  const [choices, setChoices] = useState<Choice[]>([])
  const [selection, setSelection] = useState<string[]>([])
  const [search, setSearch] = useState("")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")
  const [review, setReview] = useState<any>(null)
  const [version, setVersion] = useState(0)
  const requestKeys = useRef<Record<string, string>>({})
  useEffect(() => { setAttached([]); setReview(null); setError(""); requestKeys.current = {} }, [conversationId])
  useEffect(() => {
    if (!conversationId) return
    let disposed = false
    let timer: ReturnType<typeof setTimeout>
    const load = async () => {
      try {
        const result = await api(`chat-workflows/${conversationId}`)
        if (disposed) return
        setAttached(result.data)
        if (result.data.some((w: Attached) => pending(w.execution_status))) timer = setTimeout(load, 8000)
      } catch (e) { if (!disposed) setError(e instanceof Error ? e.message : "Could not load attachments") }
    }
    void load()
    return () => { disposed = true; clearTimeout(timer) }
  }, [conversationId, version])
  useEffect(() => {
    if (!open) return
    let disposed = false
    setBusy(true); setError("")
    void api("workflows").then(result => {
      if (!disposed) { setChoices(result.data); setSelection(attached.map(w => w.workflow_id)) }
    }).catch(e => { if (!disposed) setError(e.message) }).finally(() => { if (!disposed) setBusy(false) })
    return () => { disposed = true }
  }, [open, conversationId]) // Attachment choices are staged when the picker opens.
  async function attach() {
    setBusy(true); setError("")
    try {
      const id = conversationId || (await api("chat-workflows/new", json({}))).id
      await api(`chat-workflows/${id}`, json({ workflow_ids: selection }, "PUT"))
      if (!conversationId) onConversation(id)
      setVersion(n => n + 1); onOpenChange(false)
    } catch (e) { setError(e instanceof Error ? e.message : "Could not attach workflows") }
    finally { setBusy(false) }
  }
  async function run(w: Attached) {
    setBusy(true); setError("")
    try {
      const key = requestKeys.current[w.workflow_id] ||= crypto.randomUUID()
      const result = await api(`chat-workflows/${conversationId}/${w.workflow_id}/run`, json({ request_key: key, input: {} }))
      delete requestKeys.current[w.workflow_id]
      setReview(await api(`approvals/${result.approval_id}`))
      setVersion(n => n + 1)
    } catch (e) { setError(e instanceof Error ? e.message : "Could not request execution") }
    finally { setBusy(false) }
  }
  async function approve() {
    setBusy(true); setError("")
    try {
      // Refresh status while the synchronous approval route executes the workflow.
      setVersion(n => n + 1)
      await api(`approvals/${review.id}/approve`, json({ resume_conversation: false }))
      setReview(null); setVersion(n => n + 1)
    } catch (e) { setError(e instanceof Error ? e.message : "A manager must approve this run") }
    finally { setBusy(false); setVersion(n => n + 1) }
  }
  return <>
    {attached.length > 0 && <section aria-label="Workflows attached to this chat" className="max-h-56 overflow-y-auto border-b border-border bg-muted/20 px-4 py-3 space-y-2">
      <div className="flex items-center justify-between"><h3 className="text-xs font-semibold">Workflows attached to this chat</h3><Button size="sm" variant="ghost" onClick={() => onOpenChange(true)} className="h-7 text-xs"><Plus className="mr-1 h-3 w-3" />Attach more</Button></div>
      {attached.map(w => <div key={w.workflow_id} className="rounded-lg border border-border bg-card p-2 space-y-1">
        <div className="flex gap-2 items-center"><Workflow className="h-4 w-4 shrink-0 text-primary" /><span className="min-w-0 flex-1 break-words text-xs font-medium">{w.name}</span>
          <Button size="sm" variant="outline" className="h-7 text-xs" disabled={busy || chatBusy || pending(w.execution_status) || w.status !== "active"} onClick={() => void run(w)}><Play className="mr-1 h-3 w-3" />Run</Button></div>
        <p className="text-xs text-muted-foreground" role="status">{w.execution_status.replaceAll("_", " ")}{w.status !== "active" ? " · activate in the workflow editor before running" : ""}</p>
        {w.approval_id && w.execution_status === "awaiting_approval" && <Button size="sm" variant="link" className="h-6 p-0 text-xs" onClick={() => { void api(`approvals/${w.approval_id}`).then(setReview).catch(e => setError(e.message)) }}>Review proposed run</Button>}
        {w.error && <p className="text-xs text-destructive">{w.error}</p>}
        {Boolean(w.output) && <details className="text-xs"><summary className="cursor-pointer">Step results</summary><pre className="max-h-36 overflow-auto whitespace-pre-wrap break-words mt-1">{JSON.stringify(w.output, null, 2)}</pre></details>}
        <Link className="text-xs text-primary" href={`/dashboard/admin/workflows?workflow=${w.workflow_id}`}>Open workflow</Link>
      </div>)}
    </section>}
    {!open && !review && error && <p role="alert" className="px-4 py-2 text-xs text-destructive">{error}</p>}
    <Dialog open={open} onOpenChange={onOpenChange}><DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-lg">
      <DialogTitle>Workflows</DialogTitle><DialogDescription>Attach reusable automations to this chat. They run only when you choose Run; background triggers stay unchanged.</DialogDescription>
      <Input aria-label="Search workflows" placeholder="Search workflows…" value={search} onChange={e => setSearch(e.target.value)} />
      <Link href="/dashboard/admin/workflows" className="text-sm text-primary">Describe an automation and design a new workflow →</Link>
      <div className="space-y-2 max-h-80 overflow-y-auto">
        {busy && <p role="status" className="flex gap-2 text-sm"><Loader2 className="h-4 w-4 animate-spin" />Loading…</p>}
        {!busy && choices.filter(w => `${w.name} ${w.description || ""}`.toLowerCase().includes(search.toLowerCase())).map(w => <label key={w.id} className="flex cursor-pointer gap-3 rounded-lg border border-border p-3">
          <input type="checkbox" checked={selection.includes(w.id)} onChange={e => setSelection(ids => e.target.checked ? [...ids, w.id] : ids.filter(id => id !== w.id))} className="mt-1" />
          <span className="min-w-0"><span className="block text-sm font-medium break-words">{w.name}</span><span className="block text-xs text-muted-foreground">{w.description}</span><span className="block text-xs text-muted-foreground mt-1">{w.status} · {w.trigger_event ? "event trigger" : w.schedule_enabled ? "scheduled" : "manual"}</span></span>
        </label>)}
        {!busy && !choices.length && <p className="text-sm text-muted-foreground">No workflows yet. Create a draft in the workflow editor.</p>}
      </div>
      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
      <div className="flex justify-end gap-2"><Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button><Button disabled={busy || chatBusy || selection.length > 20} onClick={() => void attach()}>Attach {selection.length ? `(${selection.length})` : "selection"}</Button></div>
    </DialogContent></Dialog>
    <Dialog open={Boolean(review)} onOpenChange={value => { if (!value && !busy) setReview(null) }}><DialogContent>
      <DialogTitle>Review workflow run</DialogTitle><DialogDescription>This run uses the saved workflow and conversation context. A manager or tenant admin must approve execution.</DialogDescription>
      <p className="text-sm font-medium">{review?.arguments?.workflow_name}</p>
      <ol className="list-decimal pl-5 space-y-1 text-sm">{review?.arguments?.step_summary?.map((step: any) => <li key={step.id}>{step.name || step.id} <span className="text-muted-foreground">({step.type})</span></li>)}</ol>
      <details className="text-xs"><summary className="cursor-pointer">Inspect frozen steps and inputs</summary><pre className="max-h-48 overflow-auto whitespace-pre-wrap break-words">{JSON.stringify(review?.arguments, null, 2)}</pre></details>
      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
      <Button onClick={() => void approve()} disabled={busy || review?.status !== "pending"}>{busy ? "Running…" : "Approve & run"}</Button>
    </DialogContent></Dialog>
  </>
}
