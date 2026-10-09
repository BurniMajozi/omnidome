"use client"

import { Fragment, useCallback, useEffect, useState } from "react"
import { Download, Loader2, Search, Trash2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import {
  AnalyticsApiError,
  deleteResearch,
  exportResearchMarkdown,
  getResearch,
  listResearch,
  safeHttpUrl,
  startResearch,
  type Depth,
  type ResearchRun,
} from "@/lib/analytics-ai-api"
import {
  ErrorNote,
  ExternalLink,
  NO_RUN_TIP,
  Pill,
  UsageIndicator,
  errText,
  fmtDateTime,
  inputCls,
  usePermission,
  usePoll,
} from "./shared"

const DEPTH_HELP: Record<Depth, string> = { quick: "3 sources", standard: "6 sources", deep: "10 sources" }

function statusTone(s: ResearchRun["status"]) {
  return s === "done" ? "good" : s === "failed" ? "bad" : "info"
}

/** Renders text with [S#] markers as citation chips; everything else stays escaped text. */
function Cited({ text, runId, known }: { text: string; runId: string; known: Set<string> }) {
  const parts = text.split(/\[(S\d+)\]/g)
  return (
    <>
      {parts.map((p, i) =>
        i % 2 === 1 ? (
          <CiteChip key={i} id={p} runId={runId} known={known.has(p)} />
        ) : (
          <Fragment key={i}>{p}</Fragment>
        ),
      )}
    </>
  )
}

function CiteChip({ id, runId, known }: { id: string; runId: string; known: boolean }) {
  const n = id.replace(/^S/, "")
  if (!known) return <span className="text-muted-foreground">[{n}]</span>
  return (
    <button
      type="button"
      className="mx-0.5 inline-flex h-5 min-w-5 items-center justify-center rounded-full border border-primary/40 bg-primary/10 px-1.5 align-baseline text-[11px] font-semibold text-primary hover:bg-primary/20"
      aria-label={`Source ${n}`}
      onClick={() => document.getElementById(`src-${runId}-${id}`)?.scrollIntoView({ behavior: "smooth", block: "center" })}
    >
      {n}
    </button>
  )
}

function Report({ run }: { run: ResearchRun }) {
  const report = run.report
  const sources = run.sources ?? []
  const known = new Set(sources.map((s) => s.id))
  if (!report) return null
  return (
    <div className="space-y-5">
      <section>
        <h4 className="mb-1 text-sm font-semibold text-foreground">Summary</h4>
        <p className="whitespace-pre-wrap text-sm leading-relaxed text-foreground/90">
          <Cited text={report.summary} runId={run.id} known={known} />
        </p>
      </section>

      <section>
        <h4 className="mb-2 text-sm font-semibold text-foreground">Key findings</h4>
        {report.key_findings.length === 0 ? (
          <p className="text-sm text-muted-foreground">No findings survived source verification.</p>
        ) : (
          <ol className="space-y-3">
            {report.key_findings.map((f, i) => (
              <li key={i} className="rounded-md border border-border bg-secondary/20 p-3 text-sm">
                <p className="text-foreground">
                  {f.claim}{" "}
                  {f.source_ids.map((sid) => (
                    <CiteChip key={sid} id={sid} runId={run.id} known={known.has(sid)} />
                  ))}
                </p>
                {f.quote?.text && (
                  <blockquote className="mt-2 border-l-2 border-border pl-3 text-xs italic text-muted-foreground">
                    “{f.quote.text}”
                  </blockquote>
                )}
              </li>
            ))}
          </ol>
        )}
      </section>

      <section>
        <h4 className="mb-2 text-sm font-semibold text-foreground">Sources</h4>
        <div className="overflow-x-auto rounded-md border border-border">
          <table className="w-full text-left text-xs">
            <thead className="bg-secondary/40 text-muted-foreground">
              <tr>
                <th className="px-3 py-2">#</th>
                <th className="px-3 py-2">Title</th>
                <th className="px-3 py-2">Domain</th>
                <th className="px-3 py-2">Link</th>
                <th className="px-3 py-2">Fetched</th>
              </tr>
            </thead>
            <tbody>
              {sources.map((s) => {
                const href = safeHttpUrl(s.url)
                return (
                  <tr key={s.id} id={`src-${run.id}-${s.id}`} className="border-t border-border align-top">
                    <td className="px-3 py-2 font-semibold">{s.id.replace(/^S/, "")}</td>
                    <td className="px-3 py-2">{s.title || s.domain}</td>
                    <td className="px-3 py-2 text-muted-foreground">{s.domain}</td>
                    <td className="px-3 py-2">{href ? <ExternalLink href={href}>Open</ExternalLink> : <span className="text-muted-foreground">Blocked</span>}</td>
                    <td className="whitespace-nowrap px-3 py-2 text-muted-foreground">{fmtDateTime(s.fetched_at)}</td>
                  </tr>
                )
              })}
              {sources.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-3 py-3 text-muted-foreground">
                    No sources were returned.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      {report.limitations.length > 0 && (
        <section className="rounded-md border border-amber-500/30 bg-amber-500/5 p-3">
          <h4 className="mb-1 text-sm font-semibold text-amber-300">Limitations</h4>
          <ul className="list-disc space-y-1 pl-5 text-xs text-foreground/80">
            {report.limitations.map((l, i) => (
              <li key={i}>{l}</li>
            ))}
          </ul>
        </section>
      )}
      {(report.stripped_claims ?? 0) > 0 && (
        <p className="text-xs text-muted-foreground">
          {report.stripped_claims} model statement{report.stripped_claims === 1 ? " was" : "s were"} removed because they could not be tied to a fetched source.
        </p>
      )}
    </div>
  )
}

export function ResearchView() {
  const { denied, markDenied } = usePermission()
  const [question, setQuestion] = useState("")
  const [depth, setDepth] = useState<Depth>("standard")
  const [country, setCountry] = useState("za")
  const [recency, setRecency] = useState("")
  const [maxSources, setMaxSources] = useState("")
  const [formErr, setFormErr] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [history, setHistory] = useState<ResearchRun[]>([])
  const [historyErr, setHistoryErr] = useState<string | null>(null)
  const [current, setCurrent] = useState<ResearchRun | null>(null)
  const [usageKey, setUsageKey] = useState(0)
  const [actionErr, setActionErr] = useState<string | null>(null)

  const loadHistory = useCallback(async () => {
    try {
      setHistory((await listResearch(25, 0)).items)
      setHistoryErr(null)
    } catch (e) {
      setHistoryErr(errText(e))
    }
  }, [])
  useEffect(() => {
    void loadHistory()
  }, [loadHistory])

  const running = current?.status === "queued" || current?.status === "running"
  usePoll(running, async () => {
    if (!current) return true
    const next = await getResearch(current.id)
    setCurrent(next)
    if (next.status === "done" || next.status === "failed") {
      void loadHistory()
      setUsageKey((k) => k + 1)
      return true
    }
    return false
  })

  async function submit() {
    setFormErr(null)
    const q = question.trim()
    if (q.length < 8 || q.length > 500) {
      setFormErr("Enter a question of 8 to 500 characters.")
      return
    }
    const cc = country.trim().toLowerCase()
    if (cc && !/^[a-z]{2}$/.test(cc)) {
      setFormErr("Country must be a 2-letter code, for example za.")
      return
    }
    const ms = maxSources.trim() === "" ? undefined : Number(maxSources)
    if (ms !== undefined && (!Number.isInteger(ms) || ms < 1 || ms > 15)) {
      setFormErr("Max sources must be a whole number from 1 to 15.")
      return
    }
    setSubmitting(true)
    try {
      const run = await startResearch({
        question: q,
        depth,
        ...(cc ? { country: cc } : {}),
        ...(recency ? { recency: recency as "day" | "week" | "month" | "year" } : {}),
        ...(ms ? { max_sources: ms } : {}),
      })
      setCurrent(run)
      void loadHistory()
      setUsageKey((k) => k + 1)
    } catch (e) {
      if (e instanceof AnalyticsApiError && e.forbidden) markDenied()
      setFormErr(errText(e))
    } finally {
      setSubmitting(false)
    }
  }

  async function open(id: string) {
    setActionErr(null)
    try {
      setCurrent(await getResearch(id))
    } catch (e) {
      setActionErr(errText(e))
    }
  }

  async function remove(id: string) {
    setActionErr(null)
    if (!window.confirm("Delete this research run?")) return
    try {
      await deleteResearch(id)
      if (current?.id === id) setCurrent(null)
      void loadHistory()
    } catch (e) {
      setActionErr(errText(e))
    }
  }

  async function exportMd(run: ResearchRun) {
    setActionErr(null)
    try {
      const md = await exportResearchMarkdown(run.id)
      const url = URL.createObjectURL(new Blob([md], { type: "text/markdown" }))
      const a = document.createElement("a")
      a.href = url
      a.download = `research-${run.id.slice(0, 8)}.md`
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(url)
    } catch (e) {
      setActionErr(errText(e))
    }
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-foreground">Research</h2>
          <p className="text-sm text-muted-foreground">Ask a question. Answers are built only from web pages fetched for this run, each claim cited.</p>
        </div>
        <UsageIndicator refreshKey={usageKey} />
      </div>

      <div className="surface-card space-y-3 p-4">
        <label className="block text-xs font-medium text-muted-foreground">
          Question
          <textarea
            className={cn(inputCls, "mt-1 h-24 py-2")}
            value={question}
            maxLength={500}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="How is Starlink affecting South African fibre uptake?"
          />
        </label>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <label className="text-xs font-medium text-muted-foreground">
            Depth
            <select className={cn(inputCls, "mt-1")} value={depth} onChange={(e) => setDepth(e.target.value as Depth)}>
              {(Object.keys(DEPTH_HELP) as Depth[]).map((d) => (
                <option key={d} value={d}>
                  {d} ({DEPTH_HELP[d]})
                </option>
              ))}
            </select>
          </label>
          <label className="text-xs font-medium text-muted-foreground">
            Country
            <input className={cn(inputCls, "mt-1")} value={country} maxLength={2} onChange={(e) => setCountry(e.target.value)} placeholder="za" />
          </label>
          <label className="text-xs font-medium text-muted-foreground">
            Recency
            <select className={cn(inputCls, "mt-1")} value={recency} onChange={(e) => setRecency(e.target.value)}>
              <option value="">Any time</option>
              <option value="day">Past day</option>
              <option value="week">Past week</option>
              <option value="month">Past month</option>
              <option value="year">Past year</option>
            </select>
          </label>
          <label className="text-xs font-medium text-muted-foreground">
            Max sources (1-15, optional)
            <input className={cn(inputCls, "mt-1")} inputMode="numeric" value={maxSources} onChange={(e) => setMaxSources(e.target.value)} />
          </label>
        </div>
        <ErrorNote message={formErr} />
        <div className="flex items-center gap-3">
          <Button onClick={submit} disabled={submitting || running || denied} title={denied ? NO_RUN_TIP : undefined}>
            {submitting || running ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
            {running ? "Researching…" : "Run research"}
          </Button>
          {denied && <span className="text-xs text-muted-foreground">{NO_RUN_TIP}</span>}
        </div>
      </div>

      {current && (
        <div className="surface-card space-y-4 p-4">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div className="min-w-0">
              <p className="break-words text-sm font-semibold text-foreground">{current.question}</p>
              <p className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                <Pill tone={statusTone(current.status)}>{current.status}</Pill>
                <span>{current.depth}</span>
                <span>{current.credits_used} credits</span>
                <span>{fmtDateTime(current.created_at)}</span>
              </p>
            </div>
            {current.status === "done" && (
              <Button variant="outline" size="sm" onClick={() => exportMd(current)}>
                <Download className="h-3.5 w-3.5" />
                Export markdown
              </Button>
            )}
          </div>
          {running && (
            <div className="flex items-center gap-2 text-sm text-muted-foreground" role="status">
              <Loader2 className="h-4 w-4 animate-spin" />
              {current.status === "queued" ? "Queued…" : "Searching and reading sources, then writing the report. This can take a minute or two."}
            </div>
          )}
          {current.status === "failed" && <ErrorNote message={current.error ?? "The run failed."} />}
          {current.status === "done" && <Report run={current} />}
        </div>
      )}

      <div className="surface-card p-4">
        <h3 className="mb-2 text-sm font-semibold text-foreground">History</h3>
        <ErrorNote message={historyErr ?? actionErr} className="mb-2" />
        {history.length === 0 && !historyErr ? (
          <p className="text-sm text-muted-foreground">No research runs yet.</p>
        ) : (
          <ul className="divide-y divide-border">
            {history.map((r) => (
              <li key={r.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                <button type="button" className="min-w-0 flex-1 text-left" onClick={() => open(r.id)}>
                  <span className="block truncate text-sm text-foreground hover:underline">{r.question}</span>
                  <span className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                    <Pill tone={statusTone(r.status)}>{r.status}</Pill>
                    {fmtDateTime(r.created_at)} · {r.source_count} sources
                  </span>
                </button>
                <Button variant="ghost" size="sm" aria-label="Delete run (admin)" title="Delete (admin only)" onClick={() => remove(r.id)}>
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}
