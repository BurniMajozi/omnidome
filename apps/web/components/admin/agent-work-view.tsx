"use client"
import { useCallback, useEffect, useMemo, useState } from "react"
import { Loader2, MessageSquare, Plus, RefreshCw } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog"
import type { AgentInfo } from "@/lib/orchestrator-api"
import type { TenantUsage } from "@/lib/platform-pricing"
import { workApi, workConversations, workLabel, running, needsReview, type WorkJob, type WorkThread, type WorkAgent, type WorkBudget } from "@/lib/agent-work-api"
import { AgentWorkConversation } from "./agent-work-conversation"
import { AgentWorkBudgets } from "./agent-work-budgets"

export function AgentWorkView({ agents }: { agents: AgentInfo[] }) {
  const [jobs, setJobs] = useState<WorkJob[]>([])
  const [registered, setRegistered] = useState<WorkAgent[]>([])
  const [budget, setBudget] = useState<WorkBudget>({ monthly_budget_usd: null, month_spend_usd: 0 })
  const [credits, setCredits] = useState<TenantUsage | null>(null)
  const [creditError, setCreditError] = useState("")
  const [selected, setSelected] = useState<string | null>(null)
  const [thread, setThread] = useState<WorkThread | null>(null)
  const [error, setError] = useState("")
  const [detailError, setDetailError] = useState("")
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState("")
  const [filter, setFilter] = useState("all")
  const [newTask, setNewTask] = useState(false)
  const [objective, setObjective] = useState("")
  const [goal, setGoal] = useState("")
  const [agentType, setAgentType] = useState("assistant")
  const [ceiling, setCeiling] = useState("5")
  const [busy, setBusy] = useState(false)
  const [formError, setFormError] = useState("")
  const groups = useMemo(() => workConversations(jobs), [jobs])
  const name = (type: string) => registered.find(a => a.agent_type === type)?.name || agents.find(a => a.agent_type === type)?.description.split(" — ")[0] || type
  const refresh = useCallback(async () => {
    try {
      const [list, roster, limits] = await Promise.all([workApi<WorkJob[]>("/jobs"), workApi<WorkAgent[]>("/registered"), workApi<WorkBudget>("/budgets/tenant")])
      setJobs(list); setRegistered(roster); setBudget(limits); setError("")
      void workApi<TenantUsage>("/budgets/credits").then(result => { setCredits(result); setCreditError("") }).catch(e => { setCredits(null); setCreditError(e.message) })
    } catch (e) { setError(e instanceof Error ? e.message : "Could not load work") }
    finally { setLoading(false) }
  }, [])
  useEffect(() => { void refresh(); const timer = setInterval(() => { if (document.visibilityState === "visible") void refresh() }, 5000); return () => clearInterval(timer) }, [refresh])
  useEffect(() => { if (!selected && groups.length) setSelected(groups[0].id) }, [groups, selected])
  useEffect(() => {
    if (!selected) return
    let disposed = false
    void workApi<WorkThread>(`/jobs/${selected}/thread`).then(value => {
      if (!disposed) { setThread(value); setDetailError("") }
    }).catch(e => { if (!disposed) setDetailError(e.message) })
    return () => { disposed = true }
  }, [selected, jobs])
  const choose = (id: string) => { if (id === selected) return; setSelected(id); setThread(null); setDetailError("") }
  async function create() {
    setBusy(true); setFormError("")
    try {
      const job = await workApi<WorkJob>("/jobs", { agent_type: agentType, objective, goal_label: goal || null, max_cost_usd: Number(ceiling) })
      choose(job.id); setObjective(""); setGoal(""); setNewTask(false); await refresh()
    } catch (e) { setFormError(e instanceof Error ? e.message : "Could not start task") }
    finally { setBusy(false) }
  }
  const visible = groups.filter(g => `${g.title} ${name(g.latest.agent_type)}`.toLowerCase().includes(search.toLowerCase()) && (filter === "all" || (filter === "running" ? running(g.latest.status) : needsReview(g.latest.status))))
  return <div className="space-y-5">
    <div className="flex flex-wrap items-center justify-between gap-3"><div><h2 className="text-lg font-semibold">Agent work</h2><p className="text-sm text-muted-foreground">Give direction, follow the work, and keep the conversation going.</p></div><Button onClick={() => setNewTask(true)}><Plus className="mr-2 h-4 w-4" />New task</Button></div>
    {error && <p role="alert" className="rounded-lg border border-destructive/40 p-3 text-sm text-destructive">{error} <Button variant="link" onClick={() => void refresh()}>Retry</Button></p>}
    <div className="grid gap-4 lg:grid-cols-[minmax(240px,0.8fr)_minmax(0,2fr)]">
      <aside className="rounded-xl border bg-card p-3 space-y-3" aria-label="Previous agent conversations">
        <div className="flex items-center justify-between"><h3 className="text-sm font-semibold">Conversations</h3><Button size="sm" variant="ghost" aria-label="Refresh agent conversations" onClick={() => void refresh()}><RefreshCw className="h-4 w-4" /></Button></div>
        <Input aria-label="Search task conversations" placeholder="Find a task or agent…" value={search} onChange={e => setSearch(e.target.value)} />
        <div className="flex flex-wrap gap-1">{[["all", "All"], ["running", "In progress"], ["review", "Needs attention"]].map(([id, label]) => <Button key={id} size="sm" variant={filter === id ? "secondary" : "ghost"} className="text-xs" onClick={() => setFilter(id)} aria-pressed={filter === id}>{label}</Button>)}</div>
        <div className="max-h-[65vh] overflow-y-auto space-y-2">
          {loading && <p role="status" className="flex gap-2 text-sm"><Loader2 className="h-4 w-4 animate-spin" />Loading…</p>}
          {!loading && !visible.length && <p className="p-4 text-sm text-muted-foreground">{groups.length ? "No conversations match this filter." : "Start a task to open a conversation with an agent."}</p>}
          {visible.map(group => <button key={group.id} onClick={() => choose(group.id)} className={`w-full rounded-lg border p-3 text-left hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${selected === group.id || thread?.id === group.id ? "border-primary bg-primary/5" : "border-border"}`}>
            <p className="line-clamp-2 text-sm font-medium">{group.title}</p><p className="mt-1 text-xs text-muted-foreground">{name(group.latest.agent_type)}</p><p className="mt-2 text-xs flex items-center gap-1">{running(group.latest.status) && <Loader2 className="h-3 w-3 animate-spin" />}{workLabel(group.latest.status)}</p><p className="mt-1 text-xs text-muted-foreground">{new Date(group.latest.created_at).toLocaleDateString("en-ZA")} · {group.count} turn{group.count === 1 ? "" : "s"}</p>
          </button>)}
        </div>
      </aside>
      <div className="min-w-0">
        {detailError ? <p role="alert" className="rounded-lg border p-4 text-sm">{detailError}<Button variant="link" onClick={() => void refresh()}>Retry</Button></p> : thread ? <AgentWorkConversation key={thread.id} thread={thread} agentName={name(thread.turns[0].agent_type)} refresh={refresh} /> : <div className="flex min-h-80 flex-col items-center justify-center rounded-xl border border-dashed p-6 text-center"><MessageSquare className="mb-3 h-8 w-8 text-muted-foreground" /><h3 className="font-medium">{selected ? "Loading conversation…" : "Your agents’ work, in one conversation"}</h3><p className="mt-2 max-w-sm text-sm text-muted-foreground">Open an earlier task to ask follow-up questions, or start a new one. Responses and run history stay together.</p></div>}
      </div>
    </div>
    <AgentWorkBudgets credits={credits} creditError={creditError} budget={budget} agents={registered} refresh={refresh} />
    <Dialog open={newTask} onOpenChange={setNewTask}><DialogContent className="max-h-[90vh] overflow-y-auto"><DialogTitle>Start a conversation with an agent</DialogTitle><DialogDescription>Describe the outcome. The agent will work within your run ceiling and keep a history you can return to.</DialogDescription>
      <form className="space-y-3" onSubmit={e => { e.preventDefault(); void create() }}><label className="block text-sm">Agent<select className="mt-1 w-full rounded-md border bg-background p-2" value={agentType} onChange={e => setAgentType(e.target.value)}>{agents.filter(a => a.agent_type !== "auto").map(a => <option key={a.agent_type} value={a.agent_type}>{name(a.agent_type)}</option>)}</select></label>
        <label className="block text-sm">What do you want done?<Textarea className="mt-1" value={objective} onChange={e => setObjective(e.target.value)} minLength={10} maxLength={4000} required placeholder="Explain the goal and what a good result looks like…" /></label>
        <label className="block text-sm">Conversation name (optional)<Input className="mt-1" value={goal} onChange={e => setGoal(e.target.value)} maxLength={200} placeholder="e.g. Improve lead follow-up" /></label>
        <label className="block text-sm">Run ceiling (USD)<Input className="mt-1" type="number" min="0.01" max="100" step="0.01" value={ceiling} onChange={e => setCeiling(e.target.value)} required /></label>
        <p className="text-xs text-muted-foreground">The ceiling is checked between turns; a turn can finish above it. Unattended agents inspect and draft; external actions still need approval.</p>
        {formError && <p role="alert" className="text-sm text-destructive">{formError}</p>}<Button type="submit" disabled={busy || objective.trim().length < 10}>{busy ? "Starting…" : "Start task"}</Button>
      </form>
    </DialogContent></Dialog>
  </div>
}
