"use client"

/**
 * Workflows admin — native workflow/DAG runner UI (Phase B/C).
 * List / create / edit / run workflows and view run results. Talks to the
 * orchestrator via the /api/orchestrator proxy (auth attached by AuthFetchInit).
 * A drag-drop React-Flow canvas is a later enhancement; this gives a functional
 * editor + a read-only visual flow of the nodes.
 */
import { useEffect, useState, useCallback } from "react"
import { Play, Plus, Save, Loader2, RefreshCw } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { FlowCanvas } from "@/components/workflows/flow-canvas"

interface WF {
  id: string
  name: string
  description?: string | null
  definition: { nodes?: any[]; edges?: any[] }
  status: string
}

const STARTER = {
  nodes: [
    { id: "start", type: "trigger", name: "Start", config: {} },
    { id: "ask", type: "agent_invoke", name: "Ask DomeBot", config: { agent_type: "customer_facing", message: "Summarize the input in one sentence: {{input.message}}" } },
    { id: "done", type: "end", name: "End", config: {} },
  ],
  edges: [{ from: "start", to: "ask" }, { from: "ask", to: "done" }],
}

export default function WorkflowsPage() {
  const [list, setList] = useState<WF[]>([])
  const [selected, setSelected] = useState<WF | null>(null)
  const [defText, setDefText] = useState("")
  const [runOut, setRunOut] = useState<any>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

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
  }

  const create = async () => {
    setBusy("create")
    try {
      const r = await fetch("/api/orchestrator/workflows", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: `Workflow ${list.length + 1}`, status: "active", definition: STARTER }),
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
        method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ definition }),
      })
      const w = await r.json()
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
    <div className="flex h-full gap-4 p-4">
      {/* List */}
      <div className="w-64 flex-shrink-0 space-y-2">
        <div className="flex items-center justify-between">
          <h2 className="font-semibold">Workflows</h2>
          <div className="flex gap-1">
            <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => void load()}><RefreshCw className="h-4 w-4" /></Button>
            <Button size="icon" className="h-7 w-7" onClick={() => void create()} disabled={busy === "create"}>
              {busy === "create" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
            </Button>
          </div>
        </div>
        {list.length === 0 && <p className="text-xs text-muted-foreground">No workflows yet. Click + to create one.</p>}
        {list.map((w) => (
          <button key={w.id} onClick={() => select(w)}
            className={`w-full rounded-md border px-3 py-2 text-left text-sm hover:bg-secondary/50 ${selected?.id === w.id ? "border-primary bg-secondary/50" : "border-border"}`}>
            <div className="font-medium">{w.name}</div>
            <div className="text-xs text-muted-foreground">{w.status} · {(w.definition?.nodes?.length ?? 0)} nodes</div>
          </button>
        ))}
      </div>

      {/* Editor / runner */}
      <div className="flex-1 min-w-0">
        {!selected && <div className="flex h-full items-center justify-center text-sm text-muted-foreground">Select or create a workflow.</div>}
        {selected && (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-semibold">{selected.name}</h3>
              <div className="flex gap-2">
                <Button size="sm" variant="outline" onClick={() => void save()} disabled={busy === "save"}>
                  {busy === "save" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4 mr-1" />} Save
                </Button>
                <Button size="sm" onClick={() => void run()} disabled={busy === "run"}>
                  {busy === "run" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4 mr-1" />} Run
                </Button>
              </div>
            </div>

            {/* Interactive drag-drop canvas */}
            <FlowCanvas
              key={selected.id}
              definition={selected.definition ?? { nodes: [], edges: [] }}
              onChange={(d) => setDefText(JSON.stringify(d, null, 2))}
            />

            {/* JSON editor */}
            <div>
              <label className="text-xs font-medium text-muted-foreground">Definition (JSON)</label>
              <textarea value={defText} onChange={(e) => setDefText(e.target.value)}
                className="mt-1 h-64 w-full rounded-md border border-border bg-background p-2 font-mono text-xs" spellCheck={false} />
            </div>

            {error && <div className="text-xs text-red-400">Error: {error}</div>}

            {runOut && (
              <div className="rounded-lg border border-border p-3">
                <div className="text-sm font-medium">Run: <span className={runOut.status === "succeeded" ? "text-green-400" : "text-red-400"}>{runOut.status}</span></div>
                {runOut.error && <div className="text-xs text-red-400">{runOut.error}</div>}
                <pre className="mt-2 max-h-64 overflow-auto rounded bg-secondary/40 p-2 text-xs">{JSON.stringify(runOut.steps ?? runOut, null, 2)}</pre>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
