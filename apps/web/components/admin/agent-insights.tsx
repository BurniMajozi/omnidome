"use client"

/**
 * Agent Manager + agent flow building blocks (SPEC-orchestrator-memory-hardening.md,
 * stage 1): tool policies (A6), LLM usage and loop-guard stops (A7), workflow run
 * history.
 */
import { useCallback, useEffect, useState } from "react"
import {
  AlertTriangle,
  Archive,
  ArrowRight,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clock,
  Cpu,
  Database,
  Eye,
  Loader2,
  Lock,
  PenLine,
  RefreshCw,
  Search,
  ShieldAlert,
  Sparkles,
  Zap,
  Check,
  X,
} from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { KnowledgeIndexSection } from "@/components/admin/knowledge-index"
import { DreamStateSection } from "@/components/admin/dream-state"
import {
  archiveMemoryEntry,
  approveApproval,
  createStrategyEntry,
  dryRunHousekeeping,
  getCompactionStats,
  getHousekeepingStatus,
  getLlmUsage,
  getWorkflowRun,
  listApprovals,
  listMemoryEntries,
  listWorkflowRuns,
  recallMemory,
  rejectApproval,
  runHousekeeping,
  type AgentUsage,
  type ApprovalItem,
  type CompactionStats,
  type HousekeepingReport,
  type LlmUsage,
  type MemoryEntry,
  type MemoryRecallResult,
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
  awaiting_approval: "border-amber-500/30 bg-amber-500/10 text-amber-400",
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
              {run.status.replace("_", " ")}
            </span>
            <Badge variant="outline" className="text-[10px] font-normal">{run.trigger}</Badge>
            <span className="text-muted-foreground">{formatWhen(run.started_at)}</span>
            <span className="ml-auto text-muted-foreground">{duration(run)}</span>
          </button>
          {run.status === "awaiting_approval" ? (
            <p className="px-9 pb-2 text-[11px] text-amber-400 font-medium flex items-center gap-1.5">
              <ShieldAlert className="h-3 w-3" />
              {run.error || "awaiting approval"}
            </p>
          ) : run.error ? (
            <p className="px-9 pb-2 text-[11px] text-red-400">{run.error}</p>
          ) : null}
          {open === run.id && (
            <div className="space-y-1 bg-muted/20 px-9 py-2">
              {!detail[run.id] ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />
              ) : (
                <>
                  <div className="flex items-center gap-2 pb-1 text-[10px] text-muted-foreground">
                    <span className="flex items-center gap-1 text-purple-400">
                      <Database className="h-3 w-3" />
                      Deterministic memory capture active (M3)
                    </span>
                  </div>
                  {detail[run.id].steps.map((st, i) => (
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
                </>
              )}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

// ── Memory Management (M1, M3, M4, M5) ──────────────────────────────────────

export function MemoryManagementView() {
  const [query, setQuery] = useState("")
  const [strategyTitle, setStrategyTitle] = useState("")
  const [strategyContent, setStrategyContent] = useState("")
  const [strategyAgent, setStrategyAgent] = useState("")
  const [strategyBusy, setStrategyBusy] = useState(false)
  const [selectedModule, setSelectedModule] = useState<string>("all")
  const [loading, setLoading] = useState(false)
  const [memoryError, setMemoryError] = useState<string | null>(null)
  const [recallData, setRecallData] = useState<MemoryRecallResult | null>(null)
  const [entries, setEntries] = useState<MemoryEntry[]>([])
  const [compactionStats, setCompactionStats] = useState<CompactionStats | null>(null)
  const [hkStatus, setHkStatus] = useState<any>(null)
  const [hkReport, setHkReport] = useState<HousekeepingReport | null>(null)
  const [hkBusy, setHkBusy] = useState(false)
  const [actionMsg, setActionMsg] = useState<string | null>(null)

  const loadData = useCallback(async () => {
    setLoading(true)
    setMemoryError(null)
    try {
      const [rec, ents, comp, hk] = await Promise.all([
        recallMemory(query.trim() || undefined, selectedModule === "all" ? undefined : selectedModule),
        listMemoryEntries(selectedModule === "all" ? undefined : selectedModule, false),
        getCompactionStats().catch(() => null),
        getHousekeepingStatus().catch(() => null),
      ])
      setRecallData(rec)
      setEntries(ents)
      setCompactionStats(comp)
      setHkStatus(hk)
    } catch (err) {
      setMemoryError(err instanceof Error ? err.message : "Memory service unavailable")
    } finally {
      setLoading(false)
    }
  }, [query, selectedModule])

  useEffect(() => {
    void loadData()
  }, [loadData])

  const handleArchive = async (id: string) => {
    try {
      await archiveMemoryEntry(id, true)
      setEntries((prev) => prev.filter((e) => e.id !== id))
      setActionMsg("Memory archived successfully")
      setTimeout(() => setActionMsg(null), 3000)
    } catch (err) {
      setActionMsg(err instanceof Error ? err.message : "Archive failed")
    }
  }

  const handleCreateStrategy = async () => {
    setStrategyBusy(true)
    try {
      await createStrategyEntry({
        title: strategyTitle.trim(),
        content: strategyContent.trim(),
        ...(strategyAgent.trim() ? { agent_type: strategyAgent.trim() } : {}),
      })
      setStrategyTitle("")
      setStrategyContent("")
      setStrategyAgent("")
      setActionMsg("Approved strategy saved for agent briefings")
      await loadData()
    } catch (err) {
      setActionMsg(err instanceof Error ? err.message : "Strategy save failed")
    } finally {
      setStrategyBusy(false)
    }
  }

  const handleHousekeeping = async (dryRun: boolean) => {
    setHkBusy(true)
    setHkReport(null)
    try {
      const rep = dryRun ? await dryRunHousekeeping() : await runHousekeeping()
      setHkReport(rep)
      if (!dryRun) {
        await loadData()
      }
    } catch (err) {
      setActionMsg(err instanceof Error ? err.message : "Housekeeping failed")
    } finally {
      setHkBusy(false)
    }
  }

  return (
    <div className="space-y-6">
      {actionMsg && (
        <div className="rounded-lg border border-primary/30 bg-primary/10 p-3 text-xs text-primary flex items-center justify-between">
          <span>{actionMsg}</span>
          <button type="button" onClick={() => setActionMsg(null)} className="text-muted-foreground hover:text-foreground">✕</button>
        </div>
      )}

      <div className="rounded-lg border border-border bg-card p-4 space-y-3">
        <div>
          <h3 className="text-sm font-semibold">Approved agent strategy</h3>
          <p className="text-xs text-muted-foreground">Record verified tenant goals and guardrails. Leave agent type blank to brief every agent.</p>
        </div>
        <div className="grid gap-2 sm:grid-cols-2">
          <Input aria-label="Strategy title" placeholder="Strategy title" value={strategyTitle} onChange={(event) => setStrategyTitle(event.target.value)} maxLength={240} />
          <Input aria-label="Agent type" placeholder="Agent type (optional)" value={strategyAgent} onChange={(event) => setStrategyAgent(event.target.value)} maxLength={80} />
        </div>
        <textarea aria-label="Verified strategy and guardrails" className="w-full min-h-28 rounded-md border border-input bg-background px-3 py-2 text-sm" placeholder="Verified strategy, success criteria, and boundaries" value={strategyContent} onChange={(event) => setStrategyContent(event.target.value)} maxLength={8000} />
        <Button size="sm" disabled={strategyBusy || strategyTitle.trim().length < 3 || strategyContent.trim().length < 10} onClick={() => void handleCreateStrategy()}>
          {strategyBusy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null} Save approved strategy
        </Button>
      </div>

      {/* Metrics Row: Compaction & Housekeeping */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="rounded-lg border border-border bg-card p-4 space-y-1">
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>Compacted Conversations (M4)</span>
            <Sparkles className="h-4 w-4 text-primary" />
          </div>
          <div className="text-2xl font-bold">{n(compactionStats?.compacted_conversations_count ?? 0)}</div>
          <p className="text-[11px] text-muted-foreground">
            Total compaction runs: {n(compactionStats?.total_compaction_runs ?? 0)}
          </p>
        </div>

        <div className="rounded-lg border border-border bg-card p-4 space-y-1">
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>Roll-up Retention</span>
            <Clock className="h-4 w-4 text-amber-500" />
          </div>
          <div className="text-2xl font-bold">{hkStatus?.config?.rollup_days ?? 30} days</div>
          <p className="text-[11px] text-muted-foreground">
            Low importance archive threshold: {hkStatus?.config?.low_importance_retention_days ?? 90} days
          </p>
        </div>

        <div className="rounded-lg border border-border bg-card p-4 space-y-2">
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>Memory Housekeeping (M5)</span>
            <Database className="h-4 w-4 text-emerald-500" />
          </div>
          <div className="flex gap-2">
            <Button
              size="sm"
              variant="outline"
              disabled={hkBusy}
              onClick={() => void handleHousekeeping(true)}
              className="text-xs h-8 flex-1"
            >
              {hkBusy ? <Loader2 className="h-3 w-3 animate-spin mr-1" /> : null}
              Dry Run
            </Button>
            <Button
              size="sm"
              disabled={hkBusy}
              onClick={() => void handleHousekeeping(false)}
              className="text-xs h-8 flex-1"
            >
              Execute
            </Button>
          </div>
        </div>
      </div>

      {/* Housekeeping Report Banner if run */}
      {hkReport && (
        <div className="rounded-lg border border-border bg-muted/30 p-4 space-y-2">
          <div className="flex items-center justify-between">
            <h4 className="text-sm font-semibold flex items-center gap-2">
              <CheckCircle2 className="h-4 w-4 text-emerald-400" />
              Housekeeping {hkReport.dry_run ? "Simulation (Dry Run)" : "Execution"} Result
            </h4>
            <span className="text-xs text-muted-foreground">{formatWhen(hkReport.executed_at)}</span>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
            <div className="rounded border bg-background/50 p-2">
              <div className="text-muted-foreground text-[10px]">Duplicates Merged</div>
              <div className="font-bold">{n(hkReport.duplicates_count)}</div>
            </div>
            <div className="rounded border bg-background/50 p-2">
              <div className="text-muted-foreground text-[10px]">Low-Importance Stale</div>
              <div className="font-bold">{n(hkReport.low_importance_count)}</div>
            </div>
            <div className="rounded border bg-background/50 p-2">
              <div className="text-muted-foreground text-[10px]">Groups Rolled Up</div>
              <div className="font-bold">{n(hkReport.groups_rolled_up)}</div>
            </div>
            <div className="rounded border bg-background/50 p-2">
              <div className="text-muted-foreground text-[10px]">Total Entries Archived</div>
              <div className="font-bold">{n(hkReport.total_archived)}</div>
            </div>
          </div>
        </div>
      )}

      {/* Search & Filters */}
      {memoryError && <div role="alert" className="rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-xs text-amber-700 dark:text-amber-300 flex items-center justify-between gap-2"><span>Memory service unavailable: {memoryError}</span><Button size="sm" variant="outline" onClick={() => void loadData()}>Retry</Button></div>}
      <div className="flex flex-col sm:flex-row gap-3 items-center justify-between">
        <div className="relative w-full sm:w-96">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search recalled memories & facts…"
            className="pl-8 text-xs h-9"
          />
        </div>
        <div className="flex items-center gap-1.5 w-full sm:w-auto overflow-x-auto">
          {["all", "strategy", "sales", "support", "retention", "billing", "general"].map((m) => (
            <Button
              key={m}
              size="sm"
              variant={selectedModule === m ? "default" : "outline"}
              onClick={() => setSelectedModule(m)}
              className="text-xs h-7 px-2.5 capitalize"
            >
              {m}
            </Button>
          ))}
          <Button size="sm" variant="ghost" onClick={() => void loadData()} className="h-7 w-7 p-0">
            <RefreshCw className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>

      {/* Recalled Summaries */}
      {recallData?.summaries && recallData.summaries.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
            <Sparkles className="h-3.5 w-3.5 text-primary" />
            Active Module Summaries ({recallData.summaries.length})
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {recallData.summaries.map((s) => (
              <div key={s.id} className="rounded-lg border border-primary/20 bg-primary/5 p-3 space-y-1">
                <div className="flex items-center justify-between">
                  <span className="font-medium text-xs text-foreground">{s.title || s.scope_key}</span>
                  <Badge variant="outline" className="text-[10px]">{s.module || "general"}</Badge>
                </div>
                <p className="text-xs text-muted-foreground whitespace-pre-wrap">{s.summary}</p>
                <div className="text-[10px] text-muted-foreground pt-1">
                  Updated: {formatWhen(s.updated_at)} · {s.source_entry_ids?.length ?? 0} source entries
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <KnowledgeIndexSection />

      <DreamStateSection />

      {/* Memory Entries List */}
      <div className="space-y-2">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
          <Database className="h-3.5 w-3.5 text-primary" />
          Tenant Memory Entries ({entries.length})
        </h3>
        {loading ? (
          <div className="flex items-center justify-center py-10">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        ) : memoryError ? null : entries.length === 0 ? (
          <p className="text-xs text-muted-foreground py-6 text-center border rounded-lg">No memory entries found.</p>
        ) : (
          <div className="divide-y divide-border rounded-lg border border-border">
            {entries.map((e) => (
              <div key={e.id} className="p-3 text-xs flex flex-col sm:flex-row sm:items-start justify-between gap-3 hover:bg-muted/20">
                <div className="space-y-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-foreground">{e.title}</span>
                    <Badge variant="outline" className="text-[10px] capitalize">{e.module || "general"}</Badge>
                    <span className="text-[10px] text-muted-foreground">{e.scope_key}</span>
                    <span className="text-[10px] font-mono text-muted-foreground">src: {e.source_type}</span>
                  </div>
                  <p className="text-muted-foreground whitespace-pre-wrap line-clamp-3">{e.content}</p>
                  <div className="text-[10px] text-muted-foreground">
                    Occurred: {formatWhen(e.occurred_at)}
                    {e.importance !== "normal" && <span className="ml-2 font-semibold text-amber-400">[{e.importance}]</span>}
                  </div>
                </div>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => void handleArchive(e.id)}
                  className="h-7 text-xs gap-1 text-muted-foreground hover:text-destructive shrink-0"
                >
                  <Archive className="h-3 w-3" />
                  Archive
                </Button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

// ── OKF Skills (docs/skills.md) ─────────────────────────────────────────────
// The panel moved to components/admin/okf-skills.tsx; re-exported so existing imports keep working.
export { OKFSkillsView } from "@/components/admin/okf-skills"

// ── Stage 3: Agent Approvals Queue View (Spec A8) ──────────────────────────

export function AgentApprovalsView({ initialAgent }: { initialAgent?: string }) {
  const [items, setItems] = useState<ApprovalItem[]>([])
  const [loading, setLoading] = useState(true)
  const [statusFilter, setStatusFilter] = useState<string>("pending")
  const [agentFilter, setAgentFilter] = useState<string>(initialAgent || "all")
  const [rejectingId, setRejectingId] = useState<string | null>(null)
  const [rejectReason, setRejectReason] = useState<string>("")
  const [feedback, setFeedback] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const statusParam = statusFilter === "all" ? undefined : statusFilter
      const agentParam = agentFilter === "all" ? undefined : agentFilter
      const res = await listApprovals(statusParam, agentParam)
      setItems(res?.items ?? [])
    } catch {
      setItems([])
    } finally {
      setLoading(false)
    }
  }, [statusFilter, agentFilter])

  useEffect(() => {
    void load()
  }, [load])

  const handleApprove = async (item: ApprovalItem) => {
    try {
      await approveApproval(item.id)
      setFeedback(`Approved #${item.reference}: ${item.tool_name} executed.`)
      void load()
    } catch (err) {
      setFeedback(`Failed to approve: ${String(err)}`)
    }
    setTimeout(() => setFeedback(null), 4000)
  }

  const handleReject = async (item: ApprovalItem) => {
    try {
      await rejectApproval(item.id, rejectReason || "Rejected by administrator")
      setFeedback(`Rejected #${item.reference}.`)
      setRejectingId(null)
      setRejectReason("")
      void load()
    } catch (err) {
      setFeedback(`Failed to reject: ${String(err)}`)
    }
    setTimeout(() => setFeedback(null), 4000)
  }

  const pendingCount = items.filter((i) => i.status === "pending").length

  return (
    <div className="space-y-4">
      {/* Header and Controls */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-border/70 pb-3">
        <div className="flex items-center gap-2.5">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-amber-500/15 text-amber-400">
            <ShieldAlert className="h-4 w-4" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-base font-semibold text-foreground">Action Approvals Queue</h3>
              {pendingCount > 0 && (
                <Badge variant="secondary" className="bg-amber-500/20 text-amber-300 font-mono text-[11px] px-1.5">
                  {pendingCount} Pending
                </Badge>
              )}
            </div>
            <p className="text-xs text-muted-foreground">
              Autonomous agent tool invocations requiring human authorization (spec A8)
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {/* Status filter tabs */}
          <div className="flex rounded-lg border border-border bg-muted/40 p-0.5 text-xs">
            {["pending", "approved", "rejected", "all"].map((st) => (
              <button
                key={st}
                onClick={() => setStatusFilter(st)}
                className={`px-2.5 py-1 rounded-md capitalize transition-colors ${
                  statusFilter === st
                    ? "bg-background text-foreground font-semibold shadow-xs"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                {st}
              </button>
            ))}
          </div>

          <Button size="sm" variant="outline" onClick={() => void load()} className="h-8 gap-1.5 text-xs">
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </Button>
        </div>
      </div>

      {feedback && (
        <div className="rounded-lg border border-primary/40 bg-primary/10 p-2.5 text-xs text-primary font-medium flex items-center justify-between">
          <span>{feedback}</span>
          <Button size="sm" variant="ghost" onClick={() => setFeedback(null)} className="h-5 px-1 text-xs">
            Dismiss
          </Button>
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      ) : items.length === 0 ? (
        <div className="rounded-xl border border-dashed border-border p-10 text-center">
          <CheckCircle2 className="mx-auto h-8 w-8 text-emerald-400 mb-2" />
          <p className="text-sm font-medium text-foreground">No {statusFilter !== "all" ? statusFilter : ""} approvals</p>
          <p className="text-xs text-muted-foreground mt-0.5">
            {statusFilter === "pending"
              ? "All autonomous agent proposals have been reviewed and decided."
              : "No approval items matched the selected filters."}
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {items.map((item) => {
            const isPending = item.status === "pending"
            const isApproved = item.status === "approved"
            const isRejected = item.status === "rejected"

            return (
              <div
                key={item.id}
                className={`rounded-xl border p-4 space-y-3 transition-colors ${
                  isPending
                    ? "border-amber-500/30 bg-amber-500/5 hover:border-amber-500/50"
                    : isApproved
                    ? "border-emerald-500/30 bg-emerald-500/5"
                    : "border-border bg-card/60"
                }`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="space-y-1 flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-mono text-xs font-semibold text-primary">
                        #{item.reference}
                      </span>
                      <span className="text-sm font-semibold text-foreground">
                        {item.title}
                      </span>
                      <Badge
                        variant="outline"
                        className={`text-[10px] font-mono capitalize ${
                          isPending
                            ? "border-amber-500/40 text-amber-400 bg-amber-500/10"
                            : isApproved
                            ? "border-emerald-500/40 text-emerald-400 bg-emerald-500/10"
                            : "border-border text-muted-foreground"
                        }`}
                      >
                        {item.status}
                      </Badge>
                      <Badge variant="outline" className="text-[10px] border-border text-muted-foreground">
                        {item.category}
                      </Badge>
                      {item.impact && (
                        <Badge
                          variant="outline"
                          className={`text-[10px] capitalize ${
                            item.impact === "critical"
                              ? "border-red-500/30 text-red-400"
                              : item.impact === "high"
                              ? "border-amber-500/30 text-amber-400"
                              : "border-blue-500/30 text-blue-400"
                          }`}
                        >
                          {item.impact}
                        </Badge>
                      )}
                    </div>

                    <div className="text-xs text-muted-foreground">
                      Requested by <strong className="text-foreground">{item.agentName}</strong> ({item.agent_type}) ·{" "}
                      Tool: <code className="font-mono text-[11px] text-primary">{item.tool_name}</code> ·{" "}
                      <span>{item.timestamp}</span>
                    </div>
                  </div>

                  {isPending && (
                    <div className="flex items-center gap-2 shrink-0">
                      <Button
                        size="sm"
                        onClick={() => void handleApprove(item)}
                        className="h-8 gap-1.5 bg-emerald-600 hover:bg-emerald-500 text-white text-xs shadow-xs"
                      >
                        <Check className="h-3.5 w-3.5" />
                        Approve &amp; Run
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => setRejectingId(rejectingId === item.id ? null : item.id)}
                        className="h-8 gap-1.5 text-xs text-destructive hover:bg-destructive/10 border-destructive/30"
                      >
                        <X className="h-3.5 w-3.5" />
                        Reject
                      </Button>
                    </div>
                  )}
                </div>

                {/* Reject reason input */}
                {rejectingId === item.id && (
                  <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-3 space-y-2">
                    <span className="text-xs font-medium text-foreground">Specify reason for rejection:</span>
                    <div className="flex items-center gap-2">
                      <Input
                        value={rejectReason}
                        onChange={(e) => setRejectReason(e.target.value)}
                        placeholder="e.g. Budget exceeded, needs revised terms..."
                        className="h-8 text-xs flex-1"
                      />
                      <Button
                        size="sm"
                        variant="destructive"
                        onClick={() => void handleReject(item)}
                        className="h-8 text-xs"
                      >
                        Confirm Rejection
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => setRejectingId(null)}
                        className="h-8 text-xs"
                      >
                        Cancel
                      </Button>
                    </div>
                  </div>
                )}

                {/* Arguments Preview */}
                <div className="rounded-lg bg-background/80 border border-border/60 p-2.5 text-xs space-y-1">
                  <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                    Tool Arguments:
                  </span>
                  <pre className="font-mono text-[11px] text-foreground/90 overflow-x-auto whitespace-pre-wrap">
                    {JSON.stringify(item.arguments, null, 2)}
                  </pre>
                </div>

                {/* Outcome or Rejection Details */}
                {isApproved && item.execution_result && (
                  <div className="rounded-lg bg-emerald-500/10 border border-emerald-500/20 p-2.5 text-xs space-y-1">
                    <span className="text-[10px] font-semibold uppercase tracking-wider text-emerald-400">
                      Execution Outcome:
                    </span>
                    <pre className="font-mono text-[11px] text-foreground/90 overflow-x-auto whitespace-pre-wrap">
                      {JSON.stringify(item.execution_result, null, 2)}
                    </pre>
                  </div>
                )}

                {isRejected && item.rejection_reason && (
                  <div className="rounded-lg bg-muted/40 border border-border p-2.5 text-xs text-muted-foreground">
                    <strong className="text-foreground">Rejection Reason:</strong> {item.rejection_reason}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

