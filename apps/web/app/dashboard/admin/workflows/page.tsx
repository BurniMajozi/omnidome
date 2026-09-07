"use client"

/**
 * Workflows admin — native workflow/DAG runner UI (Phase B/C).
 * List / create / edit / run workflows and view run results. Talks to the
 * orchestrator via the /api/orchestrator proxy (auth attached by AuthFetchInit).
 * A drag-drop React-Flow canvas is a later enhancement; this gives a functional
 * editor + a read-only visual flow of the nodes.
 */
import { useEffect, useState, useCallback } from "react"
import { Play, Plus, Save, Loader2, RefreshCw, Clock } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { FlowCanvas } from "@/components/workflows/flow-canvas"

interface WF {
  id: string
  name: string
  description?: string | null
  definition: { nodes?: any[]; edges?: any[] }
  status: string
  schedule_cron?: string | null
  schedule_enabled?: boolean
  last_run_at?: string | null
  next_run_at?: string | null
}

const STARTER = {
  nodes: [
    { id: "start", type: "trigger", name: "Start", config: {} },
    { id: "ask", type: "agent_invoke", name: "Ask DomeBot", config: { agent_type: "customer_facing", message: "Summarize the input in one sentence: {{input.message}}" } },
    { id: "done", type: "end", name: "End", config: {} },
  ],
  edges: [{ from: "start", to: "ask" }, { from: "ask", to: "done" }],
}

// ─── Preset Schedules & Templates ──────────────────────────────────────────
const SCHEDULE_PRESETS = [
  { label: "Disabled", cron: "", desc: "Manual execution only" },
  { label: "Every 5 minutes", cron: "*/5 * * * *", desc: "Frequent polling or sync" },
  { label: "Every 15 minutes", cron: "*/15 * * * *", desc: "Quarter-hourly health check" },
  { label: "Hourly", cron: "0 * * * *", desc: "At minute 0 every hour" },
  { label: "Daily at 09:00 UTC", cron: "0 9 * * *", desc: "Start of business daily digest" },
  { label: "Daily at Midnight UTC", cron: "0 0 * * *", desc: "Daily batch reconciliation" },
  { label: "Weekly on Monday", cron: "0 9 * * 1", desc: "Weekly review pipeline" },
  { label: "Custom Cron", cron: "custom", desc: "Provide standard 5-part cron syntax" },
]

const WORKFLOW_TEMPLATES = [
  {
    name: "Customer Churn Escalation",
    desc: "Inspect high-risk accounts and notify retention team",
    definition: {
      nodes: [
        { id: "start", type: "trigger", name: "Scheduled Trigger", config: { source: "cron" } },
        { id: "check_churn", type: "agent_invoke", name: "Consult ChurnGuard", config: { agent_type: "retention", message: "Fetch all accounts with churn risk score above 75% and summarize key indicators." } },
        { id: "notify", type: "agent_invoke", name: "Draft Escalation Brief", config: { agent_type: "executive", message: "Draft an executive retention briefing with proposed concessions: {{steps.check_churn.output}}" } },
        { id: "done", type: "end", name: "Save Brief to Artifacts", config: {} },
      ],
      edges: [
        { from: "start", to: "check_churn" },
        { from: "check_churn", to: "notify" },
        { from: "notify", to: "done" },
      ],
    },
  },
  {
    name: "Support Auto-Triage & Routing",
    desc: "Categorize incoming issues and assign specialists",
    definition: {
      nodes: [
        { id: "start", type: "trigger", name: "Inbound Support Event", config: {} },
        { id: "triage", type: "agent_invoke", name: "Triage with SupportBot", config: { agent_type: "support", message: "Categorize ticket priority, sentiment, and required subsystem: {{input.ticket}}" } },
        { id: "provision", type: "agent_invoke", name: "Inspect Provisioning State", config: { agent_type: "provisioning", message: "Check service health and active node quotas: {{steps.triage.output}}" } },
        { id: "done", type: "end", name: "Dispatch & Respond", config: {} },
      ],
      edges: [
        { from: "start", to: "triage" },
        { from: "triage", to: "provision" },
        { from: "provision", to: "done" },
      ],
    },
  },
  {
    name: "Executive Briefing Digest",
    desc: "Generate morning summary of ARR, MRR, churn, and open tickets",
    definition: {
      nodes: [
        { id: "start", type: "trigger", name: "Morning Schedule", config: { time: "09:00 UTC" } },
        { id: "brief", type: "agent_invoke", name: "Executive InsightBot", config: { agent_type: "executive", message: "Compile executive operational briefing covering pipeline status, support SLAs, and retention alerts." } },
        { id: "done", type: "end", name: "Publish Digest", config: {} },
      ],
      edges: [
        { from: "start", to: "brief" },
        { from: "brief", to: "done" },
      ],
    },
  },
]

function describeCron(cron: string): string {
  if (!cron || !cron.trim()) return "Manual trigger only (no schedule)"
  const trimmed = cron.trim()
  const matched = SCHEDULE_PRESETS.find((p) => p.cron === trimmed)
  if (matched) return matched.label
  if (trimmed === "*/5 * * * *") return "Every 5 minutes"
  if (trimmed === "*/15 * * * *") return "Every 15 minutes"
  if (trimmed === "0 * * * *") return "Every hour at minute 0"
  if (trimmed === "0 0 * * *") return "Every day at 00:00 UTC"
  return `Custom: "${trimmed}" (UTC)`
}

export default function WorkflowsPage() {
  const [list, setList] = useState<WF[]>([])
  const [selected, setSelected] = useState<WF | null>(null)
  const [defText, setDefText] = useState("")
  const [schedCron, setSchedCron] = useState("")
  const [schedEnabled, setSchedEnabled] = useState(false)
  const [activePreset, setActivePreset] = useState<string>("Disabled")
  const [runOut, setRunOut] = useState<any>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [showJson, setShowJson] = useState(false)

  const load = useCallback(async () => {
    setError(null)
    try {
      const r = await fetch("/api/orchestrator/workflows")
      const b = await r.json()
      setList(Array.isArray(b.data) ? b.data : [])
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }, [])

  useEffect(() => { void load() }, [load])

  const select = (w: WF) => {
    setSelected(w)
    setRunOut(null)
    setDefText(JSON.stringify(w.definition ?? { nodes: [], edges: [] }, null, 2))
    const cron = w.schedule_cron ?? ""
    setSchedCron(cron)
    setSchedEnabled(Boolean(w.schedule_enabled))
    const matched = SCHEDULE_PRESETS.find((p) => p.cron === cron)
    setActivePreset(matched ? matched.label : cron ? "Custom Cron" : "Disabled")
  }

  const handlePresetSelect = (presetLabel: string) => {
    setActivePreset(presetLabel)
    const preset = SCHEDULE_PRESETS.find((p) => p.label === presetLabel)
    if (!preset) return
    if (preset.cron === "") {
      setSchedCron("")
      setSchedEnabled(false)
    } else if (preset.cron !== "custom") {
      setSchedCron(preset.cron)
      setSchedEnabled(true)
    } else {
      setSchedEnabled(true)
      if (!schedCron) setSchedCron("0 12 * * *")
    }
  }

  const applyTemplate = (tpl: typeof WORKFLOW_TEMPLATES[0]) => {
    setDefText(JSON.stringify(tpl.definition, null, 2))
    if (selected) {
      setSelected({
        ...selected,
        name: tpl.name,
        description: tpl.desc,
        definition: tpl.definition,
      })
    }
  }

  const create = async (template?: typeof WORKFLOW_TEMPLATES[0]) => {
    setBusy("create")
    try {
      const payload = template
        ? { name: template.name, description: template.desc, status: "active", definition: template.definition }
        : { name: `Workflow ${list.length + 1}`, status: "active", definition: STARTER }
      const r = await fetch("/api/orchestrator/workflows", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      })
      const w = await r.json()
      await load()
      select(w)
    } catch (e) { setError(String(e)) } finally { setBusy(null) }
  }

  const save = async () => {
    if (!selected) return
    setBusy("save"); setError(null)
    try {
      const definition = JSON.parse(defText)
      const r = await fetch(`/api/orchestrator/workflows/${selected.id}`, {
        method: "PUT", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: selected.name,
          definition,
          schedule_cron: schedCron.trim() || null,
          schedule_enabled: schedEnabled,
        }),
      })
      const w = await r.json()
      if (!r.ok) throw new Error(w?.detail || `save failed (${r.status})`)
      select(w); await load()
    } catch (e) { setError(e instanceof Error ? e.message : String(e)) } finally { setBusy(null) }
  }

  const run = async () => {
    if (!selected) return
    setBusy("run"); setRunOut(null); setError(null)
    try {
      const r = await fetch(`/api/orchestrator/workflows/${selected.id}/run`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ input: { message: "Hello from the workflow runner." } }),
      })
      setRunOut(await r.json())
    } catch (e) { setError(String(e)) } finally { setBusy(null) }
  }

  return (
    <div className="flex h-full min-h-[85vh] gap-6 p-4 sm:p-6">
      {/* Sidebar List & Templates */}
      <div className="w-80 flex-shrink-0 space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-base font-semibold text-foreground">Workflows</h2>
            <p className="text-xs text-muted-foreground">Automated DAG multi-agent pipelines</p>
          </div>
          <div className="flex gap-1.5">
            <Button size="icon" variant="outline" className="h-8 w-8" onClick={() => void load()} title="Refresh list">
              <RefreshCw className="h-3.5 w-3.5" />
            </Button>
            <Button size="sm" className="h-8 gap-1 text-xs" onClick={() => void create()} disabled={busy === "create"}>
              {busy === "create" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />}
              New
            </Button>
          </div>
        </div>

        {list.length === 0 && (
          <div className="rounded-lg border border-dashed border-border p-4 text-center">
            <p className="text-xs text-muted-foreground">No custom workflows created yet.</p>
          </div>
        )}

        <div className="space-y-2 max-h-[40vh] overflow-y-auto pr-1">
          {list.map((w) => (
            <button
              key={w.id}
              onClick={() => select(w)}
              className={`w-full rounded-lg border p-3 text-left transition-all ${
                selected?.id === w.id
                  ? "border-primary bg-primary/5 shadow-sm ring-1 ring-primary/20"
                  : "border-border bg-card hover:bg-muted/50"
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="font-medium text-sm text-foreground">{w.name}</span>
                <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium ${
                  w.status === "active" ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20" : "bg-muted text-muted-foreground"
                }`}>
                  {w.status}
                </span>
              </div>
              <div className="mt-1 flex items-center justify-between text-xs text-muted-foreground">
                <span>{(w.definition?.nodes?.length ?? 0)} step{((w.definition?.nodes?.length ?? 0) === 1) ? "" : "s"}</span>
                {w.schedule_enabled && w.schedule_cron ? (
                  <span className="flex items-center gap-1 font-mono text-[10px] text-primary">
                    <Clock className="h-3 w-3" />
                    {describeCron(w.schedule_cron)}
                  </span>
                ) : (
                  <span className="text-[11px]">Manual trigger</span>
                )}
              </div>
            </button>
          ))}
        </div>

        {/* Quick Workflow Templates */}
        <div className="rounded-xl border border-border bg-card/60 p-3.5">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2.5">
            Prebuilt Templates
          </h3>
          <div className="space-y-2">
            {WORKFLOW_TEMPLATES.map((tpl) => (
              <div
                key={tpl.name}
                className="group flex flex-col justify-between rounded-lg border border-border/80 bg-background/50 p-2.5 hover:border-primary/50 transition-colors"
              >
                <div>
                  <div className="text-xs font-medium text-foreground">{tpl.name}</div>
                  <div className="text-[11px] text-muted-foreground leading-snug mt-0.5">{tpl.desc}</div>
                </div>
                <div className="mt-2 flex gap-1.5">
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-6 text-[10px] px-2"
                    onClick={() => void create(tpl)}
                    disabled={busy === "create"}
                  >
                    + Create as New
                  </Button>
                  {selected && (
                    <Button
                      size="sm"
                      variant="ghost"
                      className="h-6 text-[10px] px-2 text-muted-foreground hover:text-foreground"
                      onClick={() => applyTemplate(tpl)}
                    >
                      Load into current
                    </Button>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Editor & Execution Pane */}
      <div className="flex-1 min-w-0">
        {!selected ? (
          <div className="flex h-full flex-col items-center justify-center rounded-2xl border border-dashed border-border p-12 text-center">
            <Clock className="h-10 w-10 text-muted-foreground/40 mb-3" />
            <h3 className="text-base font-semibold text-foreground">Select or create a workflow</h3>
            <p className="mt-1 max-w-sm text-xs text-muted-foreground">
              Choose a workflow from the left sidebar or select a prebuilt template to visually configure triggers, agents, and schedules.
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            {/* Header / Title / Action Controls */}
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-card p-4">
              <div className="space-y-0.5">
                <input
                  type="text"
                  value={selected.name}
                  onChange={(e) => setSelected({ ...selected, name: e.target.value })}
                  className="bg-transparent text-lg font-semibold text-foreground focus:outline-none focus:ring-1 focus:ring-primary rounded px-1 -ml-1"
                />
                <p className="text-xs text-muted-foreground">
                  {selected.description || "Multi-step agent DAG workflow pipeline"}
                </p>
              </div>
              <div className="flex items-center gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  className="h-9 gap-1.5"
                  onClick={() => setShowJson(!showJson)}
                >
                  {showJson ? "Hide Raw JSON" : "Inspect Raw JSON"}
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  className="h-9 gap-1.5"
                  onClick={() => void save()}
                  disabled={busy === "save"}
                >
                  {busy === "save" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4 text-muted-foreground" />}
                  Save Changes
                </Button>
                <Button
                  size="sm"
                  className="h-9 gap-1.5 bg-primary text-primary-foreground shadow-sm"
                  onClick={() => void run()}
                  disabled={busy === "run"}
                >
                  {busy === "run" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                  Run Pipeline
                </Button>
              </div>
            </div>

            {/* Visual Schedule Builder */}
            <div className="rounded-xl border border-border bg-card p-4 space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="p-1.5 rounded-md bg-primary/10 text-primary">
                    <Clock className="h-4 w-4" />
                  </div>
                  <div>
                    <h4 className="text-sm font-semibold text-foreground">Automated Run Schedule</h4>
                    <p className="text-xs text-muted-foreground">Configure periodic background execution for this workflow</p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <label className="relative inline-flex items-center cursor-pointer">
                    <input
                      type="checkbox"
                      checked={schedEnabled}
                      onChange={(e) => setSchedEnabled(e.target.checked)}
                      className="sr-only peer"
                    />
                    <div className="w-9 h-5 bg-muted peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-primary"></div>
                    <span className="ml-2 text-xs font-medium text-foreground">
                      {schedEnabled ? "Schedule Enabled" : "Schedule Paused"}
                    </span>
                  </label>
                </div>
              </div>

              {/* Schedule Presets */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-1">
                {SCHEDULE_PRESETS.map((preset) => (
                  <button
                    key={preset.label}
                    type="button"
                    onClick={() => handlePresetSelect(preset.label)}
                    className={`rounded-lg border p-2.5 text-left transition-all ${
                      activePreset === preset.label
                        ? "border-primary bg-primary/10 text-foreground ring-1 ring-primary"
                        : "border-border bg-background/50 text-muted-foreground hover:bg-muted/50 hover:text-foreground"
                    }`}
                  >
                    <div className="text-xs font-semibold">{preset.label}</div>
                    <div className="text-[10px] opacity-75 mt-0.5">{preset.desc}</div>
                  </button>
                ))}
              </div>

              {/* Custom Cron Editor & Timing Summary */}
              <div className="flex flex-wrap items-center justify-between gap-3 pt-2 border-t border-border/60">
                <div className="flex items-center gap-2.5">
                  <span className="text-xs font-medium text-muted-foreground">Cron Syntax (UTC):</span>
                  <Input
                    value={schedCron}
                    onChange={(e) => {
                      setSchedCron(e.target.value)
                      setActivePreset("Custom Cron")
                    }}
                    placeholder="e.g. */15 * * * * or 0 9 * * 1-5"
                    className="h-8 w-52 font-mono text-xs"
                    disabled={!schedEnabled && activePreset === "Disabled"}
                  />
                  <span className="text-xs font-medium text-primary">
                    {describeCron(schedCron)}
                  </span>
                </div>
                <div className="text-xs text-muted-foreground flex items-center gap-3">
                  <span>
                    <strong>Next Run:</strong>{" "}
                    {schedEnabled && schedCron
                      ? selected.next_run_at
                        ? new Date(selected.next_run_at).toUTCString()
                        : "Calculated upon save"
                      : "Not scheduled"}
                  </span>
                  {selected.last_run_at && (
                    <span>
                      <strong>Last Executed:</strong>{" "}
                      {new Date(selected.last_run_at).toLocaleString()}
                    </span>
                  )}
                </div>
              </div>
            </div>

            {/* Interactive Flow Canvas */}
            <div className="rounded-xl border border-border overflow-hidden bg-card">
              <div className="border-b border-border/80 px-4 py-2.5 bg-muted/30 flex items-center justify-between">
                <span className="text-xs font-semibold text-foreground">Interactive Visual DAG Canvas</span>
                <span className="text-[11px] text-muted-foreground">Drag to arrange · Connect ports to chain execution</span>
              </div>
              <div className="p-2">
                <FlowCanvas
                  key={selected.id}
                  definition={selected.definition ?? { nodes: [], edges: [] }}
                  onChange={(d) => setDefText(JSON.stringify(d, null, 2))}
                />
              </div>
            </div>

            {/* Optional Raw JSON Editor */}
            {showJson && (
              <div className="rounded-xl border border-border bg-card p-4 space-y-2">
                <div className="flex items-center justify-between">
                  <label className="text-xs font-semibold text-foreground">DAG Definition (JSON)</label>
                  <span className="text-[11px] text-muted-foreground">Advanced manual configuration</span>
                </div>
                <textarea
                  value={defText}
                  onChange={(e) => setDefText(e.target.value)}
                  className="h-56 w-full rounded-lg border border-border bg-background/80 p-3 font-mono text-xs leading-relaxed focus:outline-none focus:ring-1 focus:ring-primary"
                  spellCheck={false}
                />
              </div>
            )}

            {error && (
              <div className="rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-xs text-destructive">
                <strong>Error:</strong> {error}
              </div>
            )}

            {/* Run Output Inspector */}
            {runOut && (
              <div className="rounded-xl border border-border bg-card p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold text-foreground">Latest Execution Result</span>
                    <span
                      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold ${
                        runOut.status === "succeeded"
                          ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/30"
                          : "bg-red-500/10 text-red-400 border border-red-500/30"
                      }`}
                    >
                      {runOut.status ?? "Completed"}
                    </span>
                  </div>
                  {runOut.duration_ms && (
                    <span className="text-xs text-muted-foreground font-mono">
                      {runOut.duration_ms}ms
                    </span>
                  )}
                </div>

                {runOut.error && (
                  <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-400 font-mono">
                    {runOut.error}
                  </div>
                )}

                {/* Step-by-Step Execution Cards if steps exist */}
                {Array.isArray(runOut.steps) && runOut.steps.length > 0 ? (
                  <div className="space-y-2 pt-1">
                    {runOut.steps.map((st: any, idx: number) => (
                      <div
                        key={idx}
                        className="rounded-lg border border-border/80 bg-background/60 p-3 text-xs"
                      >
                        <div className="flex items-center justify-between mb-1.5">
                          <span className="font-semibold text-foreground">
                            Step {idx + 1}: {st.node_id ?? st.name ?? "Execution Node"}
                          </span>
                          <span
                            className={`font-mono text-[10px] px-1.5 py-0.5 rounded ${
                              st.success !== false ? "bg-emerald-500/10 text-emerald-400" : "bg-red-500/10 text-red-400"
                            }`}
                          >
                            {st.success !== false ? "SUCCESS" : "FAILED"}
                          </span>
                        </div>
                        {st.output && (
                          <div className="rounded bg-muted/40 p-2 font-mono text-[11px] overflow-x-auto text-muted-foreground">
                            {typeof st.output === "string" ? st.output : JSON.stringify(st.output, null, 2)}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                ) : (
                  <pre className="max-h-64 overflow-auto rounded-lg bg-background/80 p-3 text-xs font-mono text-muted-foreground border border-border/60">
                    {JSON.stringify(runOut, null, 2)}
                  </pre>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
