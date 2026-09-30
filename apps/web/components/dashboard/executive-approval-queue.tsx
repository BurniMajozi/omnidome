"use client"

import { useState, useEffect } from "react"
import {
  ShieldAlert,
  CheckCircle,
  XCircle,
  MessageSquare,
  Sparkles,
  ArrowRight,
  TrendingDown,
  Mail,
  Zap,
  Check,
  AlertTriangle,
  Clock,
  ExternalLink,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"
import { listApprovals, type ApprovalItem } from "@/lib/orchestrator-api"
import { decideApproval } from "@/lib/approvals-api"
import {
  describeApprovalFailure,
  readApprovalItems,
  shouldRefreshAfter,
  summarizeBatch,
  type ApprovalFailure,
  type BatchOutcome,
} from "@/lib/approvals-derive"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"

export interface ExecutiveApprovalItem {
  id: string
  title: string
  agent: "executive" | "retention" | "support" | "provisioning" | "customer_facing" | string
  agentName: string
  agentIcon: string
  impact: "critical" | "high" | "medium"
  category: "Retention Save" | "Pricing Strategy" | "Outage Compensation" | "Network Provisioning" | "Compliance Alert" | string
  summary: string
  context: string
  estimatedRoi?: string
  targetCount?: number
  timestamp: string
  status: "pending" | "approved" | "dismissed" | "rejected" | "expired"
}

export function ExecutiveApprovalQueue() {
  const [items, setItems] = useState<ExecutiveApprovalItem[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [actionFeedback, setActionFeedback] = useState<string | null>(null)
  /** Inline alert for a failed approve / dismiss / batch (persists until dismissed). */
  const [actionError, setActionError] = useState<string | null>(null)
  /** Ids with a request in flight: their buttons are disabled. */
  const [busyIds, setBusyIds] = useState<Set<string>>(new Set())
  const [confirmBatch, setConfirmBatch] = useState(false)
  const [batchRunning, setBatchRunning] = useState(false)

  const setBusy = (ids: string[], on: boolean) =>
    setBusyIds((prev) => {
      const next = new Set(prev)
      for (const id of ids) {
        if (on) next.add(id)
        else next.delete(id)
      }
      return next
    })

  const flash = (msg: string, ms = 5000) => {
    setActionFeedback(msg)
    setTimeout(() => setActionFeedback((cur) => (cur === msg ? null : cur)), ms)
  }

  const loadApprovals = async () => {
    try {
      const res = await listApprovals("pending")
      const rows = readApprovalItems<ApprovalItem>(res)
      if (rows === null) {
        // 200 with an unexpected body is an error state, never "Queue Clear".
        setItems([])
        setLoadError("The orchestrator answered with an unexpected response, so the queue cannot be shown.")
      } else {
        setItems(
          rows.map((i) => ({
            id: i.id,
            title: i.title || `${i.agent_type}: ${i.tool_name}`,
            agent: i.agent || i.agent_type,
            agentName: i.agentName || i.agent_type,
            agentIcon: i.agentIcon || "🤖",
            impact: i.impact || "medium",
            category: i.category || "General",
            summary: i.summary || `${i.agent_type} requested to run ${i.tool_name}`,
            context: i.context || "Action submitted for executive authorization",
            timestamp: i.timestamp || "recent",
            status: "pending" as const,
          })),
        )
        setLoadError(null)
      }
    } catch {
      // Orchestrator unavailable: show an honest state, never sample proposals.
      setItems([])
      setLoadError("Service not running. The agent orchestrator is not reachable, so no proposals can be shown.")
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadApprovals()
  }, [])

  const pendingItems = items.filter((i) => i.status === "pending")

  /** Server first: nothing is marked approved, and no success is shown, until the API says so. */
  const handleApprove = async (item: ExecutiveApprovalItem) => {
    if (busyIds.has(item.id)) return
    setActionError(null)
    setBusy([item.id], true)
    const r = await decideApproval(item.id, "approve", {})
    setBusy([item.id], false)
    if (r.ok) {
      setItems((prev) => prev.filter((i) => i.id !== item.id))
      flash(`Approved: "${item.title}". The orchestrator accepted the approval and dispatched it via ${item.agentName}.`)
    } else {
      setActionError(`"${item.title}": ${describeApprovalFailure("approve", r)}`)
      if (shouldRefreshAfter(r)) loadApprovals()
    }
  }

  const handleDismiss = async (item: ExecutiveApprovalItem) => {
    if (busyIds.has(item.id)) return
    setActionError(null)
    setBusy([item.id], true)
    const r = await decideApproval(item.id, "reject", { reason: "Dismissed by executive" })
    setBusy([item.id], false)
    if (r.ok) {
      setItems((prev) => prev.filter((i) => i.id !== item.id))
      flash(`Dismissed: "${item.title}".`, 4000)
    } else {
      setActionError(`"${item.title}": ${describeApprovalFailure("dismiss", r)}`)
      if (shouldRefreshAfter(r)) loadApprovals()
    }
  }

  /** Runs after the confirmation dialog: every pending item is decided independently. */
  const runBatchApprove = async () => {
    const targets = pendingItems.filter((i) => !busyIds.has(i.id))
    setConfirmBatch(false)
    if (targets.length === 0) return
    setActionError(null)
    setBatchRunning(true)
    setBusy(targets.map((t) => t.id), true)
    const settled = await Promise.allSettled(targets.map((t) => decideApproval(t.id, "approve", {})))
    const outcomes: BatchOutcome[] = settled.map((s, i) => {
      const t = targets[i]
      if (s.status === "fulfilled" && s.value.ok) return { id: t.id, title: t.title, ok: true }
      const failure: ApprovalFailure =
        s.status === "fulfilled" && !s.value.ok
          ? { status: s.value.status, message: s.value.message }
          : { status: null, message: "" }
      return { id: t.id, title: t.title, ok: false, failure }
    })
    setBusy(targets.map((t) => t.id), false)
    setBatchRunning(false)
    const okIds = new Set(outcomes.filter((o) => o.ok).map((o) => o.id))
    setItems((prev) => prev.filter((i) => !okIds.has(i.id))) // failed items stay in the queue
    const summary = summarizeBatch(outcomes)
    if (summary.allOk) flash(`Batch approve: ${summary.text}.`)
    else {
      setActionError(`Batch approve: ${summary.text}. The failed items are still in the queue.`)
      if (outcomes.some((o) => !o.ok && o.failure && shouldRefreshAfter(o.failure))) loadApprovals()
    }
  }

  const handleDiscussInChat = (item: ExecutiveApprovalItem) => {
    const prompt = `Executive Deliberation on Action Proposal:
Title: ${item.title}
Originating Agent: ${item.agentName} (${item.agent})
Category: ${item.category} | Priority: ${item.impact}
Summary: ${item.summary}
Financial / Operational Context: ${item.context}
${item.estimatedRoi ? `Projected Impact: ${item.estimatedRoi}` : ""}

Please break down:
1. What are the key risks and immediate benefits if approved?
2. What are the specific implementation steps?
3. Draft the required customer communication / executive order as an artifact for review.`

    window.dispatchEvent(
      new CustomEvent("open-agent-chat", {
        detail: {
          agent: item.agent,
          prompt,
          draft: prompt,
        },
      }),
    )

    setActionFeedback(`Opened deliberation with ${item.agentName} in Agent Chat.`)
    setTimeout(() => setActionFeedback(null), 4000)
  }

  if (loading) {
    return <div className="h-20 animate-pulse rounded-xl border border-border bg-muted/40" aria-label="Loading approvals" />
  }

  if (loadError !== null && pendingItems.length === 0) {
    return (
      <div role="status" className="flex items-center justify-between gap-3 rounded-xl border border-dashed border-border bg-card p-5 shadow-xs">
        <div>
          <h3 className="text-base font-semibold text-foreground">Executive Approval Queue</h3>
          <p className="text-xs text-muted-foreground">{loadError}</p>
        </div>
        <Button variant="outline" size="sm" onClick={() => { setLoading(true); setLoadError(null); loadApprovals() }}>
          Retry
        </Button>
      </div>
    )
  }

  if (pendingItems.length === 0) {
    return (
      <div className="rounded-xl border border-border bg-card p-5 shadow-xs">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-emerald-500/10 text-emerald-400">
              <CheckCircle className="h-4 w-4" />
            </div>
            <div>
              <h3 className="text-base font-semibold text-foreground">Executive Action Queue</h3>
              <p className="text-xs text-muted-foreground">No agent proposals are waiting for review</p>
            </div>
          </div>
          <Badge variant="outline" className="border-emerald-500/30 text-emerald-400 text-xs">
            Queue Clear
          </Badge>
        </div>
      </div>
    )
  }

  return (
    <div className="rounded-xl border border-border bg-card p-5 shadow-xs space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/60 pb-3">
        <div className="flex items-center gap-2.5">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-amber-500/15 text-amber-400">
            <ShieldAlert className="h-4 w-4" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-base font-semibold text-foreground">Executive Approval Queue</h3>
              <Badge variant="secondary" className="bg-amber-500/20 text-amber-300 font-mono text-[11px] px-1.5">
                {pendingItems.length} Needs Review
              </Badge>
            </div>
            <p className="text-xs text-muted-foreground">
              High-stakes autonomous actions staged by specialist agents requiring executive authorization
            </p>
          </div>
        </div>

        <Button
          variant="outline"
          size="sm"
          className="text-xs h-8 border-primary/40 text-primary hover:bg-primary/10 gap-1.5"
          disabled={batchRunning || pendingItems.every((i) => busyIds.has(i.id))}
          onClick={() => setConfirmBatch(true)}
        >
          <Check className="h-3.5 w-3.5" />
          <span>{batchRunning ? "Approving..." : `Batch Approve All (${pendingItems.length})`}</span>
        </Button>
      </div>

      {actionFeedback && (
        <div className="rounded-md bg-primary/10 border border-primary/20 px-3 py-1.5 text-xs font-medium text-primary animate-in fade-in flex items-center justify-between">
          <span>{actionFeedback}</span>
          <button type="button" aria-label="Close message" onClick={() => setActionFeedback(null)} className="text-primary hover:text-primary/80">×</button>
        </div>
      )}

      {actionError && (
        <div
          role="alert"
          className="flex items-start justify-between gap-3 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs font-medium text-destructive"
        >
          <span>{actionError}</span>
          <button
            type="button"
            aria-label="Dismiss error"
            onClick={() => setActionError(null)}
            className="shrink-0 hover:opacity-80"
          >
            ×
          </button>
        </div>
      )}

      <Dialog open={confirmBatch} onOpenChange={setConfirmBatch}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Approve {pendingItems.length} proposal{pendingItems.length === 1 ? "" : "s"}?</DialogTitle>
            <DialogDescription>
              These are autonomous actions staged by specialist agents. Approving them authorises the agents to execute
              them now, and most cannot be undone. Each item is approved independently; any that fail stay in the queue
              and are reported.
            </DialogDescription>
          </DialogHeader>
          <ul className="max-h-48 space-y-1 overflow-y-auto text-xs text-muted-foreground">
            {pendingItems.map((i) => (
              <li key={i.id} className="truncate">
                <span className="font-medium text-foreground">{i.agentName}</span>: {i.title}
              </li>
            ))}
          </ul>
          <DialogFooter>
            <Button variant="outline" size="sm" onClick={() => setConfirmBatch(false)}>
              Cancel
            </Button>
            <Button size="sm" onClick={runBatchApprove}>
              Approve {pendingItems.length} action{pendingItems.length === 1 ? "" : "s"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <div className="grid gap-3">
        {pendingItems.map((item) => (
          <div
            key={item.id}
            className="group relative flex flex-col justify-between rounded-lg border border-border/80 bg-secondary/15 p-4 transition-all hover:border-primary/40 hover:bg-secondary/25"
          >
            <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3">
              <div className="space-y-1.5 flex-1 min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="flex items-center gap-1.5 text-xs font-semibold px-2 py-0.5 rounded-md bg-secondary text-foreground border border-border/60">
                    <span>{item.agentIcon}</span>
                    <span>{item.agentName}</span>
                  </span>

                  <span
                    className={cn(
                      "text-[10px] uppercase font-bold tracking-wider px-1.5 py-0.5 rounded border",
                      item.impact === "critical" && "bg-red-500/15 text-red-400 border-red-500/30",
                      item.impact === "high" && "bg-amber-500/15 text-amber-400 border-amber-500/30",
                      item.impact === "medium" && "bg-blue-500/15 text-blue-400 border-blue-500/30",
                    )}
                  >
                    {item.impact}
                  </span>

                  <Badge variant="outline" className="text-[10px] text-muted-foreground">
                    {item.category}
                  </Badge>

                  <span className="text-[11px] text-muted-foreground ml-auto sm:ml-0 flex items-center gap-1">
                    <Clock className="h-3 w-3" />
                    {item.timestamp}
                  </span>
                </div>

                <h4 className="text-sm font-semibold text-foreground pt-0.5">{item.title}</h4>
                <p className="text-xs text-muted-foreground leading-relaxed">{item.summary}</p>
                <div className="rounded-md bg-background/60 border border-border/40 p-2 text-[11px] text-muted-foreground/90 font-mono">
                  {item.context}
                </div>
              </div>

              {item.estimatedRoi && (
                <div className="shrink-0 sm:text-right pt-1 sm:pt-0">
                  <span className="text-[10px] uppercase text-muted-foreground font-semibold block">Projected Value</span>
                  <span className="text-xs font-bold text-emerald-400 font-mono">{item.estimatedRoi}</span>
                </div>
              )}
            </div>

            <div className="mt-3.5 flex flex-wrap items-center justify-between gap-2 pt-3 border-t border-border/50 text-xs">
              <span className="text-[11px] text-muted-foreground">
                {item.targetCount ? `Affects ${item.targetCount} accounts/lines` : "Strategic executive policy"}
              </span>

              <div className="flex items-center gap-2">
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7 text-xs text-muted-foreground hover:text-foreground gap-1"
                  disabled={busyIds.has(item.id)}
                  onClick={() => handleDismiss(item)}
                >
                  <XCircle className="h-3.5 w-3.5" />
                  <span>Dismiss</span>
                </Button>

                <Button
                  variant="outline"
                  size="sm"
                  className="h-7 text-xs border-primary/40 text-primary hover:bg-primary/10 gap-1"
                  disabled={busyIds.has(item.id)}
                  onClick={() => handleDiscussInChat(item)}
                >
                  <MessageSquare className="h-3.5 w-3.5" />
                  <span>Discuss in Chat</span>
                </Button>

                <Button
                  size="sm"
                  className="h-7 text-xs bg-primary hover:bg-primary/90 text-primary-foreground gap-1 font-semibold"
                  disabled={busyIds.has(item.id)}
                  onClick={() => handleApprove(item)}
                >
                  <Check className="h-3.5 w-3.5" />
                  <span>{busyIds.has(item.id) ? "Working..." : "Approve & Execute"}</span>
                </Button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
