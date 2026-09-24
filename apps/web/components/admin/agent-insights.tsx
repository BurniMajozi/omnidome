"use client"

/**
 * Agent Manager + agent flow building blocks (SPEC-orchestrator-memory-hardening.md,
 * stage 1): tool policies (A6), LLM usage and loop-guard stops (A7), workflow run
 * history.
 */
import { useCallback, useEffect, useState } from "react"
import { AlertTriangle, ChevronDown, ChevronRight, Eye, Loader2, Lock, PenLine } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import {
  getLlmUsage,
  getWorkflowRun,
  listWorkflowRuns,
  type AgentUsage,
  type LlmUsage,
  type ModelUsage,
  type ToolPolicyInfo,
  type WorkflowRunDetail,
  type WorkflowRunSummary,
} from "@/lib/orchestrator-api"

const n = (v: number | null | undefined) => new Intl.NumberFormat("en-ZA").format(Number(v ?? 0))
const secs = (ms: number | null | undefined) => (ms == null ? "—" : `${(Number(ms) / 1000).toFixed(1)} s`)

export function formatWhen(iso?: string | null): string {
  if (!iso) return "—"
  return new Date(iso).toLocaleString("en-ZA", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })
}

// ── Tool policies (A6) ──────────────────────────────────────────────────────

export function ToolPolicyBadge({ policy }: { policy?: ToolPolicyInfo }) {
  if (!policy) return null
  if (policy.requires_approval) {
    return (
      <span className="inline-flex items-center gap-1 rounded border border-red-500/40 bg-red-500/10 px-1.5 py-px text-[10px] font-medium text-red-400" title="Waits for a person's approval before it runs">
        <Lock className="h-2.5 w-2.5" /> approval
      </span>
    )
  }
  if (policy.mutates) {
    return (
      <span className="inline-flex items-center gap-1 rounded border border-amber-500/40 bg-amber-500/10 px-1.5 py-px text-[10px] font-medium text-amber-400" title="Changes data; runs on its own, never in parallel">
        <PenLine className="h-2.5 w-2.5" /> changes data
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1 rounded border border-emerald-500/30 bg-emerald-500/10 px-1.5 py-px text-[10px] font-medium text-emerald-400" title="Read-only; may run in parallel with other reads">
      <Eye className="h-2.5 w-2.5" /> reads
    </span>
  )
}

export function ToolPolicyTable({ policies }: { policies: ToolPolicyInfo[] }) {
  if (!policies.length) return <p className="text-sm text-muted-foreground">No tools attached.</p>
  const sorted = [...policies].sort((a, b) =>
    Number(b.requires_approval) - Number(a.requires_approval) || Number(b.mutates) - Number(a.mutates) || a.name.localeCompare(b.name))
  return (
    <div className="overflow-x-auto rounded-lg border border-border">
      <table className="w-full text-left text-xs">
        <thead className="bg-muted/40 text-muted-foreground">
          <tr>
            <th className="px-3 py-2 font-medium">Tool</th>
            <th className="px-3 py-2 font-medium">Policy</th>
            <th className="px-3 py-2 font-medium">Timeout</th>
            <th className="px-3 py-2 font-medium">Output cap</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border/60">
          {sorted.map((p) => (
            <tr key={p.name}>
              <td className="px-3 py-1.5 font-mono text-[11px]">{p.name}</td>
              <td className="px-3 py-1.5"><ToolPolicyBadge policy={p} /></td>
              <td className="px-3 py-1.5">{p.timeout_s} s</td>
              <td className="px-3 py-1.5">{n(p.max_output_chars)} chars</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ── Usage (A7) ──────────────────────────────────────────────────────────────

export function useLlmUsage(days = 7) {
  const [usage, setUsage] = useState<LlmUsage | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    let cancelled = false
    getLlmUsage(days)
      .then((u) => { if (!cancelled) setUsage(u) })
      .catch((err) => { if (!cancelled) setError(err instanceof Error ? err.message : "Could not load usage") })
    return () => { cancelled = true }
  }, [days])
  return { usage, error }
}

export function AgentUsageStats({ usage, compact = false }: { usage?: AgentUsage; compact?: boolean }) {
  if (!usage || usage.turns === 0) {
    return <p className="text-[11px] text-muted-foreground">No runs in the last 7 days.</p>
  }
  const stops = usage.stopped_step_limit + usage.stopped_empty + usage.stopped_truncated
  const items: [string, string][] = [
    ["Turns", n(usage.turns)],
    ["Tool calls", n(usage.tool_calls)],
    ["Tokens", n(usage.tokens)],
    ["Avg time", secs(usage.avg_duration_ms)],
  ]
  return (
    <div className="space-y-1.5">
      <div className={`grid ${compact ? "grid-cols-4" : "grid-cols-2 sm:grid-cols-4"} gap-1.5`}>
        {items.map(([label, value]) => (
          <div key={label} className="rounded-md border border-border/60 bg-background/60 px-2 py-1">
            <div className="text-[10px] text-muted-foreground">{label}</div>
            <div className="text-xs font-semibold text-foreground">{value}</div>
          </div>
        ))}
      </div>
      {(stops > 0 || usage.ai_unavailable > 0) && (
        <p className="flex items-start gap-1 text-[11px] text-amber-400">
          <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" />
          <span>
            {stops > 0 && `${stops} turn${stops === 1 ? "" : "s"} ended by a safety guard `}
            {stops > 0 && `(step limit ${usage.stopped_step_limit}, empty ${usage.stopped_empty}, cut off ${usage.stopped_truncated})`}
            {stops > 0 && usage.ai_unavailable > 0 && " · "}
            {usage.ai_unavailable > 0 && `${usage.ai_unavailable} with every AI model unavailable`}
          </span>
        </p>
      )}
    </div>
  )
}

export function ModelUsageTable({ models }: { models: ModelUsage[] }) {
  if (!models.length) return <p className="text-xs text-muted-foreground">No AI calls in this period.</p>
  return (
    <div className="overflow-x-auto rounded-lg border border-border">
      <table className="w-full text-left text-xs">
        <thead className="bg-muted/40 text-muted-foreground">
          <tr>
            <th className="px-3 py-2 font-medium">Model that answered</th>
            <th className="px-3 py-2 font-medium">Calls</th>
            <th className="px-3 py-2 font-medium">Failed</th>
            <th className="px-3 py-2 font-medium">Tokens</th>
            <th className="px-3 py-2 font-medium">Avg latency</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border/60">
          {models.map((m) => (
            <tr key={m.model}>
              <td className="px-3 py-1.5 font-mono text-[11px]">{m.model}</td>
              <td className="px-3 py-1.5">{n(m.calls)}</td>
              <td className={`px-3 py-1.5 ${m.failures ? "text-red-400" : ""}`}>{n(m.failures)}</td>
              <td className="px-3 py-1.5">{n(m.tokens)}</td>
              <td className="px-3 py-1.5">{secs(m.avg_latency_ms)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ── Workflow run history (agent flow) ───────────────────────────────────────

const RUN_TONE: Record<string, string> = {
  succeeded: "border-emerald-500/30 bg-emerald-500/10 text-emerald-400",
  failed: "border-red-500/30 bg-red-500/10 text-red-400",
  running: "border-sky-500/30 bg-sky-500/10 text-sky-400",
}

function duration(run: WorkflowRunSummary) {
  if (!run.started_at || !run.finished_at) return "—"
  return secs(new Date(run.finished_at).getTime() - new Date(run.started_at).getTime())
}

function preview(value: unknown): string {
  if (value == null) return ""
  const text = typeof value === "string" ? value : JSON.stringify(value)
  return text.length > 400 ? `${text.slice(0, 400)}…` : text
}

export function WorkflowRunHistory({ workflowId, refreshKey = 0 }: { workflowId: string; refreshKey?: number }) {
  const [runs, setRuns] = useState<WorkflowRunSummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [open, setOpen] = useState<string | null>(null)
  const [detail, setDetail] = useState<Record<string, WorkflowRunDetail>>({})

  useEffect(() => {
    let cancelled = false
    listWorkflowRuns(workflowId)
      .then((r) => { if (!cancelled) { setRuns(r); setError(null) } })
      .catch((err) => { if (!cancelled) setError(err instanceof Error ? err.message : "Could not load runs") })
    return () => { cancelled = true }
  }, [workflowId, refreshKey])

  const toggle = useCallback(async (runId: string) => {
    setOpen((cur) => (cur === runId ? null : runId))
    if (!detail[runId]) {
      try {
        const d = await getWorkflowRun(runId)
        setDetail((prev) => ({ ...prev, [runId]: d }))
      } catch { /* the row stays collapsed-looking without steps */ }
    }
  }, [detail])

  if (error) return <p className="text-xs text-red-400">{error}</p>
  if (!runs) return <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
  if (!runs.length) return <p className="text-xs text-muted-foreground">No runs yet.</p>

  return (
    <div className="divide-y divide-border/60 rounded-lg border border-border">
      {runs.map((run) => (
        <div key={run.id}>
          <button type="button" onClick={() => void toggle(run.id)}
            className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs hover:bg-muted/40">
            {open === run.id ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
            <span className={`rounded border px-1.5 py-px text-[10px] font-semibold ${RUN_TONE[run.status] ?? "border-border"}`}>
              {run.status}
            </span>
            <Badge variant="outline" className="text-[10px] font-normal">{run.trigger}</Badge>
            <span className="text-muted-foreground">{formatWhen(run.started_at)}</span>
            <span className="ml-auto text-muted-foreground">{duration(run)}</span>
          </button>
          {run.error && <p className="px-9 pb-2 text-[11px] text-red-400">{run.error}</p>}
          {open === run.id && (
            <div className="space-y-1 bg-muted/20 px-9 py-2">
              {!detail[run.id] ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />
              ) : detail[run.id].steps.map((st, i) => (
                <div key={`${st.node_id}-${i}`} className="text-[11px]">
                  <span className={`mr-1.5 rounded border px-1 py-px text-[10px] ${RUN_TONE[st.status] ?? "border-border"}`}>{st.status}</span>
                  <span className="font-mono text-foreground">{st.node_id}</span>
                  <span className="text-muted-foreground"> · {st.node_type}</span>
                  {(st.error || st.output != null) && (
                    <pre className="mt-0.5 max-h-28 overflow-auto whitespace-pre-wrap rounded bg-background/60 p-1.5 text-[10px] text-muted-foreground">
                      {st.error ?? preview(st.output)}
                    </pre>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}
