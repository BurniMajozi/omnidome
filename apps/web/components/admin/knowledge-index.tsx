"use client"

/**
 * Knowledge index (docs/knowledge-layer.md): coverage of the vector index, embedding/store health, an admin
 * reindex action and a recall tester that shows the cards an agent would be given for a query.
 * Rendered inside the Agent Management memory panel.
 */
import { useCallback, useEffect, useMemo, useState } from "react"
import { AlertTriangle, BookOpen, CheckCircle2, Database, Loader2, RefreshCw, Search } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  getKnowledgeCoverage,
  getKnowledgeHealth,
  KnowledgeApiError,
  reindexKnowledge,
  searchKnowledge,
  type KnowledgeCoverage,
  type KnowledgeHealth,
  type KnowledgeHit,
} from "@/lib/orchestrator-api"

const when = (iso?: string | null) => (iso ? new Date(iso).toLocaleString("en-ZA", { dateStyle: "medium", timeStyle: "short" }) : "never")
const num = (v: number | null | undefined) => new Intl.NumberFormat("en-ZA").format(Number(v ?? 0))

type Health = { state: "loading" } | { state: "ok"; data: KnowledgeHealth } | { state: "error"; message: string }
type Cov = { state: "loading" } | { state: "ok"; data: KnowledgeCoverage } | { state: "forbidden" } | { state: "off" } | { state: "error"; message: string }

function isOff(e: unknown): boolean {
  return e instanceof KnowledgeApiError && e.status === 503
}

export function KnowledgeIndexSection() {
  const [health, setHealth] = useState<Health>({ state: "loading" })
  const [cov, setCov] = useState<Cov>({ state: "loading" })
  const [confirming, setConfirming] = useState<string | null>(null)
  const [reindexing, setReindexing] = useState<string | null>(null)
  const [msg, setMsg] = useState<{ tone: "ok" | "err"; text: string } | null>(null)

  const load = useCallback(async () => {
    setHealth({ state: "loading" })
    setCov({ state: "loading" })
    const h = getKnowledgeHealth()
      .then((data) => setHealth({ state: "ok", data }))
      .catch((e) => setHealth({ state: "error", message: e instanceof Error ? e.message : "Memory service unavailable" }))
    const c = getKnowledgeCoverage()
      .then((data) => setCov({ state: "ok", data }))
      .catch((e) => {
        if (e instanceof KnowledgeApiError && e.status === 403) setCov({ state: "forbidden" })
        else if (isOff(e)) setCov({ state: "off" })
        else setCov({ state: "error", message: e instanceof Error ? e.message : "Coverage unavailable" })
      })
    await Promise.all([h, c])
  }, [])
  useEffect(() => {
    void load()
  }, [load])

  const enabled = health.state === "ok" && health.data.enabled
  const notEnabled = (health.state === "ok" && !health.data.enabled) || cov.state === "off"
  const canAdmin = cov.state === "ok"

  async function doReindex(module: string) {
    setReindexing(module)
    setMsg(null)
    try {
      const r = await reindexKnowledge([module])
      setMsg({ tone: "ok", text: `Reindex of "${module}" queued (job ${r.job_id.slice(0, 8)}). The indexer picks it up within about 30 seconds; refresh to see progress.` })
    } catch (e) {
      setMsg({ tone: "err", text: e instanceof KnowledgeApiError && e.status === 403 ? "Only an admin can reindex." : e instanceof Error ? e.message : "Reindex failed" })
    } finally {
      setReindexing(null)
      setConfirming(null)
    }
  }

  const modules = useMemo(() => {
    if (cov.state !== "ok") return []
    return [...new Set(cov.data.sources.map((s) => s.module))].sort()
  }, [cov])

  return (
    <section className="space-y-3" aria-label="Knowledge index" data-testid="knowledge-index">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
          <BookOpen className="h-3.5 w-3.5 text-primary" />
          Knowledge index
        </h3>
        <Button size="sm" variant="outline" className="h-7 text-xs gap-1" onClick={() => void load()}>
          <RefreshCw className="h-3 w-3" /> Refresh
        </Button>
      </div>

      <HealthRow health={health} />

      {notEnabled && (
        <div role="status" className="rounded-lg border border-border bg-card p-4 text-xs text-muted-foreground">
          <p className="font-medium text-foreground">Knowledge layer is not enabled.</p>
          <p>
            Agents and Deck Studio are working without semantic memory. To switch it on, set up the knowledge database and the local embedding model, then start the indexer (see docs/knowledge-layer.md).
          </p>
        </div>
      )}

      {!notEnabled && cov.state === "loading" && (
        <p className="flex items-center gap-2 text-xs text-muted-foreground">
          <Loader2 className="h-3.5 w-3.5 animate-spin" /> Loading coverage…
        </p>
      )}
      {cov.state === "forbidden" && (
        <p role="status" className="rounded-lg border border-border bg-card p-3 text-xs text-muted-foreground">
          Coverage and reindexing are for admins. You can still test recall below; it shows only what your own role may see.
        </p>
      )}
      {cov.state === "error" && (
        <div role="alert" className="rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-xs text-amber-700 dark:text-amber-300 flex items-center justify-between gap-2">
          <span>Coverage unavailable: {cov.message}</span>
          <Button size="sm" variant="outline" onClick={() => void load()}>
            Retry
          </Button>
        </div>
      )}

      {cov.state === "ok" && (
        <div className="space-y-3">
          <div className="flex flex-wrap gap-2 text-[11px]">
            <span className="rounded-full border border-border px-2 py-0.5">Queue: {num(cov.data.queue.queued)} queued, {num(cov.data.queue.running)} running</span>
            <span className="rounded-full border border-border px-2 py-0.5">Failures logged: {num(cov.data.failures.length)}</span>
            {cov.data.not_yet_indexed && cov.data.not_yet_indexed.length > 0 && (
              <span className="rounded-full border border-border px-2 py-0.5 text-muted-foreground" title={cov.data.not_yet_indexed.join(", ")}>
                Not indexed yet: {cov.data.not_yet_indexed.length} type(s)
              </span>
            )}
          </div>

          {cov.data.sources.length === 0 ? (
            <p className="rounded-lg border border-border p-4 text-center text-xs text-muted-foreground">Nothing is indexed for this tenant yet. Run a reindex, or wait for the indexer’s next sweep.</p>
          ) : (
            <div className="overflow-x-auto rounded-lg border border-border">
              <table className="w-full text-xs">
                <thead className="bg-muted/40 text-left text-muted-foreground">
                  <tr>
                    <th className="px-3 py-2 font-medium">Source type</th>
                    <th className="px-3 py-2 font-medium">Module</th>
                    <th className="px-3 py-2 text-right font-medium">Chunks</th>
                    <th className="px-3 py-2 font-medium">Last indexed</th>
                  </tr>
                </thead>
                <tbody>
                  {cov.data.sources.map((r) => (
                    <tr key={`${r.source_type}:${r.module}`} className="border-t border-border">
                      <td className="px-3 py-1.5 font-mono">{r.source_type}</td>
                      <td className="px-3 py-1.5">{r.module}</td>
                      <td className="px-3 py-1.5 text-right">
                        {num(r.chunks)}
                        {r.tombstoned ? <span className="text-muted-foreground"> (+{num(r.tombstoned)} removed)</span> : null}
                      </td>
                      <td className="px-3 py-1.5 text-muted-foreground">{when(r.last_indexed)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {cov.data.watermarks.length > 0 && (
            <div className="overflow-x-auto rounded-lg border border-border">
              <table className="w-full text-xs">
                <caption className="sr-only">Indexing sources</caption>
                <thead className="bg-muted/40 text-left text-muted-foreground">
                  <tr>
                    <th className="px-3 py-2 font-medium">Indexing source</th>
                    <th className="px-3 py-2 font-medium">Caught up to</th>
                    <th className="px-3 py-2 font-medium">Last full reconcile</th>
                    <th className="px-3 py-2 text-right font-medium">Failures</th>
                  </tr>
                </thead>
                <tbody>
                  {cov.data.watermarks.map((w) => {
                    const f = cov.data.failures.filter((x) => x.source === w.source)
                    return (
                      <tr key={w.source} className="border-t border-border align-top">
                        <td className="px-3 py-1.5 font-mono">{w.source}</td>
                        <td className="px-3 py-1.5 text-muted-foreground">{when(w.last_ts)}</td>
                        <td className="px-3 py-1.5 text-muted-foreground">{when(w.last_full_at)}</td>
                        <td className="px-3 py-1.5 text-right" title={f[0]?.error}>
                          {f.length > 0 ? <span className="text-amber-400">{f.length}</span> : 0}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
          {cov.data.failures.length > 0 && (
            <details className="rounded-lg border border-border p-2 text-xs">
              <summary className="cursor-pointer text-muted-foreground">Latest indexing failures ({cov.data.failures.length})</summary>
              <ul className="mt-2 space-y-1">
                {cov.data.failures.slice(0, 10).map((f, i) => (
                  <li key={i} className="text-muted-foreground">
                    <span className="font-mono text-foreground">{f.source}</span> · {when(f.created_at)} · {f.error}
                  </li>
                ))}
              </ul>
            </details>
          )}

          {modules.length > 0 && (
            <div className="space-y-1.5">
              <p className="text-[11px] text-muted-foreground">Reindex a module (admin). This re-reads the source data and re-embeds only changed cards; it can take a while on a busy machine.</p>
              <div className="flex flex-wrap gap-2">
                {modules.map((m) =>
                  confirming === m ? (
                    <span key={m} className="inline-flex items-center gap-1 rounded-md border border-amber-500/40 bg-amber-500/10 px-2 py-1 text-xs">
                      Reindex “{m}”?
                      <Button size="sm" className="h-6 px-2 text-xs" disabled={reindexing !== null} onClick={() => void doReindex(m)}>
                        {reindexing === m ? <Loader2 className="h-3 w-3 animate-spin" /> : "Yes, reindex"}
                      </Button>
                      <Button size="sm" variant="outline" className="h-6 px-2 text-xs" disabled={reindexing !== null} onClick={() => setConfirming(null)}>
                        Cancel
                      </Button>
                    </span>
                  ) : (
                    <Button key={m} size="sm" variant="outline" className="h-7 text-xs gap-1" disabled={reindexing !== null} onClick={() => { setConfirming(m); setMsg(null) }}>
                      <Database className="h-3 w-3" /> Reindex {m}
                    </Button>
                  ),
                )}
              </div>
            </div>
          )}
        </div>
      )}

      {msg && (
        <div role={msg.tone === "err" ? "alert" : "status"} className={`rounded-lg border p-3 text-xs ${msg.tone === "err" ? "border-red-500/40 bg-red-500/10 text-red-600 dark:text-red-300" : "border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"}`}>
          {msg.text}
        </div>
      )}

      <RecallTester disabled={notEnabled || (!enabled && health.state === "ok")} canAdmin={canAdmin} />
    </section>
  )
}

function HealthRow({ health }: { health: Health }) {
  if (health.state === "loading") return null
  if (health.state === "error") {
    return (
      <p role="alert" className="rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-xs text-amber-700 dark:text-amber-300">
        Could not reach the memory service: {health.message}
      </p>
    )
  }
  const d = health.data
  if (!d.enabled) return null
  const emb = d.embedding
  return (
    <div className="grid gap-2 sm:grid-cols-2 text-xs">
      <div className="rounded-lg border border-border bg-card p-3 flex items-start gap-2">
        {d.store_ok ? <CheckCircle2 className="h-4 w-4 text-emerald-500 shrink-0" /> : <AlertTriangle className="h-4 w-4 text-amber-500 shrink-0" />}
        <div>
          <div className="font-medium text-foreground">Vector store</div>
          <div className="text-muted-foreground">{d.store_ok ? "Reachable" : "Not reachable: search falls back to nothing until the knowledge database is back."}</div>
        </div>
      </div>
      <div className="rounded-lg border border-border bg-card p-3 flex items-start gap-2">
        {emb?.ok ? <CheckCircle2 className="h-4 w-4 text-emerald-500 shrink-0" /> : <AlertTriangle className="h-4 w-4 text-amber-500 shrink-0" />}
        <div>
          <div className="font-medium text-foreground">Embedding model {emb?.model ? <span className="font-mono">{emb.model}</span> : null}</div>
          <div className="text-muted-foreground">
            {emb?.ok
              ? `Ready (${emb.dim ?? "?"} dimensions, runs locally)`
              : emb?.reachable === false
                ? `Embedding server unreachable${emb.error ? `: ${emb.error}` : ""}. Search uses keywords only.`
                : emb?.hint
                  ? `Model not installed. Run: ${emb.hint}`
                  : "Not ready"}
            {emb?.circuit_open ? " · temporarily paused after repeated errors" : ""}
          </div>
        </div>
      </div>
    </div>
  )
}

function RecallTester({ disabled, canAdmin }: { disabled: boolean; canAdmin: boolean }) {
  const [q, setQ] = useState("")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [res, setRes] = useState<{ query: string; degraded?: string | null; results: KnowledgeHit[] } | null>(null)

  async function run() {
    const query = q.trim()
    if (query.length < 2) return
    setBusy(true)
    setError(null)
    try {
      const r = await searchKnowledge(query)
      setRes({ query, degraded: r.degraded, results: r.results })
    } catch (e) {
      setRes(null)
      setError(isOff(e) ? "Knowledge layer is not enabled." : e instanceof Error ? e.message : "Search failed")
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-2 rounded-lg border border-border bg-card p-3">
      <div className="text-xs font-medium text-foreground">Recall tester</div>
      <p className="text-[11px] text-muted-foreground">
        Type what a user might ask. You see the cards the same hybrid search returns to an agent, with scores and citation ids.
        {canAdmin ? " As an admin you may see role-restricted cards that a regular agent session would not." : ""}
      </p>
      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault()
          void run()
        }}
      >
        <div className="relative flex-1">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input aria-label="Recall test query" value={q} onChange={(e) => setQ(e.target.value)} placeholder="e.g. what happened with the Acme renewal?" className="pl-8 text-xs h-9" disabled={disabled} />
        </div>
        <Button type="submit" size="sm" className="h-9" disabled={disabled || busy || q.trim().length < 2}>
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : "Test recall"}
        </Button>
      </form>
      {error && (
        <p role="alert" className="text-xs text-amber-700 dark:text-amber-300">
          {error}
        </p>
      )}
      {res?.degraded && <p className="text-[11px] text-amber-700 dark:text-amber-300">Partial result: {res.degraded}</p>}
      {res && res.results.length === 0 && !error && <p className="text-xs text-muted-foreground">No cards matched “{res.query}”. Agents would get no knowledge context for this question.</p>}
      {res && res.results.length > 0 && (
        <ol className="space-y-2">
          {res.results.map((h, i) => (
            <li key={`${h.source_type}:${h.source_id}:${h.chunk_no ?? 0}`} className="rounded-md border border-border p-2 text-xs">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="font-medium text-foreground">
                  {i + 1}. {h.title}
                </span>
                <span className="text-[10px] text-muted-foreground">score {h.score.toFixed(4)}</span>
              </div>
              <div className="text-[10px] text-muted-foreground">
                <span className="font-mono">card:{h.source_type}:{h.source_id}</span> · {h.module} · as of {h.as_of ? h.as_of.slice(0, 10) : "unknown"}
                {h.stale ? <span className="ml-1 font-semibold text-amber-400">may be out of date</span> : null}
              </div>
              <p className="mt-1 line-clamp-3 whitespace-pre-wrap text-muted-foreground">{h.markdown.replace(/^---[\s\S]*?---\s*/, "")}</p>
            </li>
          ))}
        </ol>
      )}
    </div>
  )
}
