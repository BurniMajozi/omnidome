"use client"

import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from "react"
import { AlertCircle, CheckCircle2, Clock3, Loader2, PauseCircle, PlayCircle, RefreshCw } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import type { AgentInfo } from "@/lib/orchestrator-api"

type JobStatus = "queued" | "running" | "pause_requested" | "paused" | "interrupted" |
  "awaiting_hitl" | "awaiting_review" | "completed" | "max_iterations" | "stopped_by_ceiling" | "failed"

interface AgentJob {
  id: string
  agent_type: string
  objective: string
  goal_label: string | null
  status: JobStatus
  max_cost_usd: number
  estimated_cost_usd: number
  actual_cost_usd: number | null
  cost_source: "provider" | "estimated"
  total_steps: number
  total_tokens: number
  iteration_history: Array<{ iteration: number; steps: number; tokens: number; content_preview: string; status?: string;
    verification?: { action: string; passed: boolean; reason: string; evaluated_by_jev: boolean } | null;
    jev_decisions?: Array<{ tool: string; decision: { action: string; reason: string; checks?: Record<string, number> } }> }>
  result: { final_output?: string; stopped_by?: string } | null
  error: string | null
  created_at: string | null
}

interface RegisteredAgent {
  id: string
  employee_id: string
  agent_type: string
  name: string
  role: string
  status: string
  monthly_budget_usd: number
  month_spend_usd: number
}

interface TenantBudget { monthly_budget_usd: number | null; month_spend_usd: number }

const attention = new Set<JobStatus>(["awaiting_hitl", "awaiting_review", "interrupted", "failed", "stopped_by_ceiling", "max_iterations"])
const active = new Set<JobStatus>(["queued", "running", "pause_requested"])

function statusLabel(status: JobStatus): string {
  const labels: Record<JobStatus, string> = {
    queued: "Queued", running: "Running", pause_requested: "Pausing", paused: "Paused",
    interrupted: "Interrupted", awaiting_hitl: "Needs approval", awaiting_review: "Review output", completed: "Completed",
    max_iterations: "Needs review", stopped_by_ceiling: "Budget or step limit", failed: "Failed",
  }
  return labels[status] ?? status
}

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/orchestrator/agents${path}`, {
    cache: "no-store", ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  })
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new Error(typeof body?.detail === "string" ? body.detail : `Request failed (HTTP ${response.status})`)
  }
  return response.json() as Promise<T>
}

function money(value: number): string {
  return new Intl.NumberFormat("en-ZA", { style: "currency", currency: "USD" }).format(value)
}

export function AgentWorkView({ agents }: { agents: AgentInfo[] }) {
  const [jobs, setJobs] = useState<AgentJob[]>([])
  const [registered, setRegistered] = useState<RegisteredAgent[]>([])
  const [tenantBudget, setTenantBudget] = useState<TenantBudget>({ monthly_budget_usd: null, month_spend_usd: 0 })
  const [tenantBudgetEdit, setTenantBudgetEdit] = useState("")
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [actionError, setActionError] = useState("")
  const [busy, setBusy] = useState("")
  const [selected, setSelected] = useState<string | null>(null)
  const [agentType, setAgentType] = useState("assistant")
  const [objective, setObjective] = useState("")
  const [goal, setGoal] = useState("")
  const [maxCost, setMaxCost] = useState("5")
  const [budgetEdits, setBudgetEdits] = useState<Record<string, string>>({})
  const tenantBudgetInitialized = useRef(false)

  const refresh = useCallback(async () => {
    try {
      const [nextJobs, nextRegistered, nextBudget] = await Promise.all([
        api<AgentJob[]>("/jobs"), api<RegisteredAgent[]>("/registered"), api<TenantBudget>("/budgets/tenant"),
      ])
      setJobs(nextJobs)
      setRegistered(nextRegistered)
      setTenantBudget(nextBudget)
      if (!tenantBudgetInitialized.current) {
        setTenantBudgetEdit(nextBudget.monthly_budget_usd === null ? "" : String(nextBudget.monthly_budget_usd))
        tenantBudgetInitialized.current = true
      }
      setError("")
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load agent work")
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible") void refresh()
    }, 15_000)
    return () => window.clearInterval(timer)
  }, [refresh])

  const chosen = useMemo(() => jobs.find((job) => job.id === selected), [jobs, selected])
  const needAttention = jobs.filter((job) => attention.has(job.status))
  const inProgress = jobs.filter((job) => active.has(job.status))
  const monthSpend = tenantBudget.month_spend_usd

  async function createWork(event: FormEvent) {
    event.preventDefault()
    setActionError("")
    setBusy("create")
    try {
      const job = await api<AgentJob>("/jobs", {
        method: "POST",
        body: JSON.stringify({ agent_type: agentType, objective, goal_label: goal || null, max_cost_usd: Number(maxCost) }),
      })
      setObjective("")
      setGoal("")
      setSelected(job.id)
      await refresh()
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Could not queue work")
    } finally {
      setBusy("")
    }
  }

  async function changeJob(id: string, action: "pause" | "resume" | "accept") {
    setBusy(id)
    setActionError("")
    try {
      await api(`/jobs/${id}/${action}`, { method: "POST" })
      await refresh()
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Could not update job")
    } finally {
      setBusy("")
    }
  }

  async function saveBudget(row: RegisteredAgent) {
    setBusy(row.id)
    setActionError("")
    try {
      await api(`/registered/${row.employee_id}/budget`, {
        method: "PUT", body: JSON.stringify({ monthly_budget_usd: Number(budgetEdits[row.id] ?? row.monthly_budget_usd) }),
      })
      await refresh()
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Could not save budget")
    } finally {
      setBusy("")
    }
  }

  async function saveTenantBudget() {
    setBusy("tenant-budget")
    setActionError("")
    try {
      await api("/budgets/tenant", { method: "PUT", body: JSON.stringify({ monthly_budget_usd: tenantBudgetEdit.trim() ? Number(tenantBudgetEdit) : null }) })
      await refresh()
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Could not save tenant budget")
    } finally {
      setBusy("")
    }
  }

  if (loading) return <div className="flex items-center gap-2 py-12 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" />Loading agent work…</div>
  if (error) return <div role="alert" className="rounded-lg border border-destructive/40 p-5 text-sm"><AlertCircle className="mb-2 h-5 w-5 text-destructive" />{error}<Button className="ml-3" size="sm" onClick={() => void refresh()}>Retry</Button></div>

  return <div className="space-y-6">
    <div className="grid gap-3 sm:grid-cols-3">
      <Card><CardContent className="flex items-center justify-between p-4"><div><p className="text-xs text-muted-foreground">Needs attention</p><p className="text-2xl font-semibold">{needAttention.length}</p></div><AlertCircle className="h-5 w-5 text-amber-500" /></CardContent></Card>
      <Card><CardContent className="flex items-center justify-between p-4"><div><p className="text-xs text-muted-foreground">Queued or running</p><p className="text-2xl font-semibold">{inProgress.length}</p></div><Clock3 className="h-5 w-5 text-primary" /></CardContent></Card>
      <Card><CardContent className="flex items-center justify-between p-4"><div><p className="text-xs text-muted-foreground">Managed runs · month to date</p><p className="text-2xl font-semibold">{money(monthSpend)}</p><p className="text-xs text-muted-foreground">{tenantBudget.monthly_budget_usd === null ? "No tenant cap set" : `of ${money(tenantBudget.monthly_budget_usd)} cap${monthSpend >= tenantBudget.monthly_budget_usd * 0.8 ? " · review spend" : ""}`}</p></div><CheckCircle2 className="h-5 w-5 text-emerald-500" /></CardContent></Card>
    </div>

    {actionError && <div role="alert" className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">{actionError}</div>}

    <div className="grid gap-5 xl:grid-cols-[minmax(0,1.4fr)_minmax(320px,1fr)]">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between"><CardTitle className="text-base">Work queue</CardTitle><Button variant="ghost" size="sm" onClick={() => void refresh()} aria-label="Refresh work queue"><RefreshCw className="h-4 w-4" /></Button></CardHeader>
        <CardContent className="space-y-2">
          {jobs.length === 0 && <p className="py-8 text-center text-sm text-muted-foreground">No work assigned yet. Queue a bounded task to start a run.</p>}
          {[...jobs].sort((a, b) => Number(attention.has(b.status)) - Number(attention.has(a.status))).map((job) => <button
            key={job.id} type="button" onClick={() => setSelected(job.id)}
            className={`w-full rounded-lg border p-3 text-left transition-colors hover:bg-muted/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary ${selected === job.id ? "border-primary" : "border-border"}`}
          >
            <div className="flex items-start justify-between gap-2"><span className="line-clamp-2 text-sm font-medium">{job.objective}</span><Badge variant="outline" className="shrink-0">{statusLabel(job.status)}</Badge></div>
            <div className="mt-2 flex flex-wrap gap-3 text-xs text-muted-foreground"><span>{job.agent_type}</span><span>{job.goal_label || "No goal label"}</span><span>{money(job.actual_cost_usd ?? job.estimated_cost_usd)} {job.cost_source === "provider" ? "provider" : "estimated"}</span></div>
          </button>)}
        </CardContent>
      </Card>

      <div className="space-y-5">
        <Card><CardHeader><CardTitle className="text-base">Assign work</CardTitle></CardHeader><CardContent>
          <form className="space-y-3" onSubmit={createWork}>
            <label className="block text-xs font-medium">Agent
              <select className="mt-1 w-full rounded-md border bg-background p-2 text-sm" value={agentType} onChange={(e) => setAgentType(e.target.value)}>
                {agents.filter((agent) => agent.agent_type !== "auto").map((agent) => <option key={agent.agent_type} value={agent.agent_type}>{agent.description.split(" — ")[0]}</option>)}
              </select>
            </label>
            <label className="block text-xs font-medium">Objective<Textarea className="mt-1" value={objective} onChange={(e) => setObjective(e.target.value)} minLength={10} maxLength={4000} required placeholder="Describe the result and how you will verify it" /></label>
            <label className="block text-xs font-medium">Goal label (optional)<Input className="mt-1" value={goal} onChange={(e) => setGoal(e.target.value)} maxLength={200} placeholder="e.g. Reduce support backlog" /></label>
            <label className="block text-xs font-medium">Maximum run cost (USD)<Input className="mt-1" type="number" min="0.01" max="100" step="0.01" value={maxCost} onChange={(e) => setMaxCost(e.target.value)} required /></label>
            <p className="text-xs text-muted-foreground">The cost ceiling is checked between turns; one turn may finish above it. Provider cost is shown only when every call reports it, otherwise spend is estimated.</p>
            <Button type="submit" disabled={busy === "create" || !objective.trim()}>{busy === "create" ? "Queueing…" : "Queue task"}</Button>
          </form>
        </CardContent></Card>
      </div>
    </div>

    {chosen && <Card><CardHeader className="flex flex-row items-center justify-between gap-3"><div><CardTitle className="text-base">Run detail</CardTitle><p className="mt-1 text-xs text-muted-foreground">{chosen.id}</p></div><div className="flex gap-2">
      {(["queued", "running"] as JobStatus[]).includes(chosen.status) && <Button size="sm" variant="outline" disabled={busy === chosen.id} onClick={() => void changeJob(chosen.id, "pause")}><PauseCircle className="mr-1 h-4 w-4" />Pause</Button>}
      {(["paused", "interrupted", "failed", "awaiting_hitl"] as JobStatus[]).includes(chosen.status) && <Button size="sm" variant="outline" disabled={busy === chosen.id} onClick={() => void changeJob(chosen.id, "resume")}><PlayCircle className="mr-1 h-4 w-4" />Resume</Button>}
      {(["awaiting_review", "max_iterations"] as JobStatus[]).includes(chosen.status) && <Button size="sm" disabled={busy === chosen.id} onClick={() => void changeJob(chosen.id, "accept")}><CheckCircle2 className="mr-1 h-4 w-4" />Accept output</Button>}
    </div></CardHeader><CardContent className="space-y-4 text-sm">
      <div className="flex flex-wrap gap-4 text-xs"><span>Status: <strong>{statusLabel(chosen.status)}</strong></span><span>Steps: {chosen.total_steps}</span><span>Tokens: {chosen.total_tokens}</span><span>Cost: {money(chosen.actual_cost_usd ?? chosen.estimated_cost_usd)} ({chosen.cost_source}) of {money(chosen.max_cost_usd)} max</span></div>
      {chosen.error && <p role="alert" className="rounded-md border border-amber-500/30 bg-amber-500/5 p-3 text-amber-700 dark:text-amber-300">{chosen.error}</p>}
      {chosen.iteration_history.length > 0 ? <ol className="space-y-2 border-l pl-4">{chosen.iteration_history.map((step, index) => <li key={`${step.iteration}-${index}`} className="text-xs"><strong>Iteration {step.iteration}</strong> · {step.steps} tool steps · {step.tokens} tokens<p className="mt-1 text-muted-foreground">{step.content_preview || "No response text"}</p>{step.verification && <p className="mt-1 rounded bg-muted p-2">{step.verification.evaluated_by_jev ? "JEV" : "Verification"} · {step.verification.action}: {step.verification.reason}</p>}{step.jev_decisions?.map((item, decisionIndex) => <p key={`${item.tool}-${decisionIndex}`} className="mt-1 rounded bg-muted p-2">JEV · {item.tool}: {item.decision.action} — {item.decision.reason}{item.decision.checks && <span className="block text-muted-foreground">{Object.entries(item.decision.checks).map(([name, value]) => `${name}: ${Math.round(value * 100)}%`).join(" · ")}</span>}</p>)}</li>)}</ol> : <p className="text-muted-foreground">No run steps recorded yet.</p>}
      {chosen.result?.final_output && <div><h3 className="mb-2 font-medium">Output</h3><pre className="max-h-72 overflow-auto whitespace-pre-wrap rounded-md bg-muted p-3 text-xs">{chosen.result.final_output}</pre></div>}
    </CardContent></Card>}

    <Card><CardHeader><CardTitle className="text-base">Budgets</CardTitle></CardHeader><CardContent className="space-y-4">
      <div className="flex flex-wrap items-end gap-3 rounded-md border p-3"><label className="block w-full text-xs sm:w-auto"><span className="block">Tenant monthly USD limit (blank = no tenant cap)</span><Input className="mt-1 w-full sm:w-40" type="number" min="0" max="100000" step="0.01" placeholder={tenantBudget.monthly_budget_usd === null ? "Not set" : String(tenantBudget.monthly_budget_usd)} value={tenantBudgetEdit} onChange={(e) => setTenantBudgetEdit(e.target.value)} /></label><Button size="sm" variant="outline" disabled={busy === "tenant-budget"} onClick={() => void saveTenantBudget()}>Save tenant cap</Button><span className="text-xs text-muted-foreground">Current: {tenantBudget.monthly_budget_usd === null ? "not set" : money(tenantBudget.monthly_budget_usd)}</span></div>
      {registered.length === 0 && <p className="text-sm text-muted-foreground">No HR-created agents are registered yet. Add one in Talent → Org Chart.</p>}
      {registered.map((row) => <div key={row.id} className="flex flex-wrap items-center justify-between gap-3 rounded-md border p-3">
        <div><p className="text-sm font-medium">{row.name} <Badge variant="outline" className="ml-2">{row.status}</Badge></p><p className="text-xs text-muted-foreground">{row.role} · {money(row.month_spend_usd)} spent this month{row.monthly_budget_usd > 0 && row.month_spend_usd >= row.monthly_budget_usd * 0.8 ? " · review spend" : ""}</p></div>
        <div className="flex items-center gap-2"><label className="text-xs">Monthly USD limit<Input className="mt-1 w-28" type="number" min="0" max="10000" step="0.01" value={budgetEdits[row.id] ?? String(row.monthly_budget_usd)} onChange={(e) => setBudgetEdits((prev) => ({ ...prev, [row.id]: e.target.value }))} /></label><Button size="sm" variant="outline" disabled={busy === row.id} onClick={() => void saveBudget(row)}>Save</Button></div>
      </div>)}
    </CardContent></Card>
  </div>
}
