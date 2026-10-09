"use client"

import { useCallback, useEffect, useState } from "react"
import { ArrowLeft, Loader2, Plus, RefreshCcw, Trash2 } from "lucide-react"
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import { listCampaigns, type Campaign } from "@/lib/marketing-api"
import {
  AnalyticsApiError,
  createCampaignAnalysis,
  deleteCampaignAnalysis,
  getCampaignAnalysis,
  getCampaignItems,
  getCompetitorOverview,
  listCampaignAnalyses,
  refreshCampaignAnalysis,
  safeHttpUrl,
  type CampaignAnalysis,
  type CampaignItem,
  type Sentiment,
  type Theme,
} from "@/lib/analytics-ai-api"
import { ErrorNote, ExternalLink, NO_RUN_TIP, Pill, UsageIndicator, errText, fmtDate, fmtDateTime, inputCls, usePermission, usePoll } from "./shared"

const SENT_TONE: Record<Sentiment, "good" | "muted" | "bad"> = { positive: "good", neutral: "muted", negative: "bad" }
const SENT_COLOR: Record<Sentiment, string> = { positive: "#4ade80", neutral: "#94a3b8", negative: "#f87171" }
const PAGE = 25

function runTone(s: CampaignAnalysis["status"]) {
  return s === "done" ? "good" : s === "failed" ? "bad" : "info"
}

function ThemeList({ title, themes, tone }: { title: string; themes: Theme[]; tone: "good" | "bad" }) {
  return (
    <div className="surface-card p-4">
      <h4 className="mb-2 text-sm font-semibold text-foreground">{title}</h4>
      {themes.length === 0 ? (
        <p className="text-sm text-muted-foreground">None identified.</p>
      ) : (
        <ul className="space-y-3">
          {themes.map((t) => (
            <li key={t.theme} className="text-sm">
              <p className="flex items-center gap-2 font-medium text-foreground">
                {t.theme} <Pill tone={tone}>{t.count} mention{t.count === 1 ? "" : "s"}</Pill>
              </p>
              {t.examples.slice(0, 2).map((ex, i) => (
                <blockquote key={i} className="mt-1 border-l-2 border-border pl-3 text-xs text-muted-foreground">
                  “{ex.excerpt}”{" "}
                  <ExternalLink href={safeHttpUrl(ex.url)}>{ex.domain}</ExternalLink>
                  {ex.date ? ` · ${fmtDate(ex.date)}` : ""}
                </blockquote>
              ))}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function Detail({ id, onBack, onChanged }: { id: string; onBack: () => void; onChanged: () => void }) {
  const { denied, markDenied } = usePermission()
  const [a, setA] = useState<CampaignAnalysis | null>(null)
  const [items, setItems] = useState<{ total: number; rows: CampaignItem[] } | null>(null)
  const [offset, setOffset] = useState(0)
  const [err, setErr] = useState<string | null>(null)
  const [usageKey, setUsageKey] = useState(0)

  const loadItems = useCallback(
    async (off: number) => {
      try {
        const r = await getCampaignItems(id, PAGE, off)
        setItems({ total: r.total, rows: r.items })
      } catch (e) {
        setErr(errText(e))
      }
    },
    [id],
  )
  const load = useCallback(async () => {
    try {
      setA(await getCampaignAnalysis(id))
      setErr(null)
    } catch (e) {
      setErr(errText(e))
    }
  }, [id])
  useEffect(() => {
    void load()
  }, [load])
  useEffect(() => {
    void loadItems(offset)
  }, [loadItems, offset])

  const running = a?.status === "queued" || a?.status === "running"
  usePoll(running, async () => {
    const next = await getCampaignAnalysis(id)
    setA(next)
    if (next.status === "done" || next.status === "failed") {
      void loadItems(0)
      setOffset(0)
      onChanged()
      setUsageKey((k) => k + 1)
      return true
    }
    return false
  })

  async function refresh() {
    setErr(null)
    try {
      setA(await refreshCampaignAnalysis(id))
      setUsageKey((k) => k + 1)
    } catch (e) {
      if (e instanceof AnalyticsApiError && e.forbidden) markDenied()
      setErr(errText(e))
    }
  }
  async function remove() {
    if (!window.confirm("Delete this analysis?")) return
    try {
      await deleteCampaignAnalysis(id)
      onChanged()
      onBack()
    } catch (e) {
      setErr(errText(e))
    }
  }

  if (!a) return err ? <ErrorNote message={err} /> : <p className="text-sm text-muted-foreground">Loading…</p>
  const agg = a.aggregate
  const split = agg?.overall.split
  const trend = (agg?.trend ?? []).map((t) => ({ ...t }))

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <Button variant="ghost" size="sm" className="-ml-2 mb-1" onClick={onBack}>
            <ArrowLeft className="h-3.5 w-3.5" />
            All analyses
          </Button>
          <h2 className="break-words text-lg font-semibold text-foreground">{a.name}</h2>
          <p className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <span>Subject: {a.subject}</span>
            <Pill tone={runTone(a.status)}>{a.status}</Pill>
            <span>{a.item_count} items</span>
            <span>Last run: {a.last_run_at ? fmtDateTime(a.last_run_at) : "never"}</span>
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button onClick={refresh} disabled={running || denied} title={denied ? NO_RUN_TIP : undefined}>
            {running ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCcw className="h-4 w-4" />}
            {running ? "Running…" : "Refresh"}
          </Button>
          <Button variant="ghost" aria-label="Delete analysis (admin)" title="Delete (admin only)" onClick={remove}>
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      </div>
      <UsageIndicator refreshKey={usageKey} />
      <ErrorNote message={err} />
      {a.status === "failed" && <ErrorNote message={a.error ?? "The analysis failed."} />}
      {running && (
        <p className="flex items-center gap-2 text-sm text-muted-foreground" role="status">
          <Loader2 className="h-4 w-4 animate-spin" />
          Searching public pages and reading them. This can take a few minutes.
        </p>
      )}

      <div className="rounded-md border border-amber-500/40 bg-amber-500/10 p-4">
        <h3 className="mb-1 text-sm font-semibold text-amber-300">Coverage limits</h3>
        {a.limitations && a.limitations.length > 0 ? (
          <ul className="list-disc space-y-1 pl-5 text-xs text-foreground/90">
            {a.limitations.map((l, i) => (
              <li key={i}>{l}</li>
            ))}
          </ul>
        ) : (
          <p className="text-xs text-foreground/90">
            Only publicly readable web pages are analysed. Private or login-walled platforms are not covered.
          </p>
        )}
        {agg?.coverage && (
          <p className="mt-2 text-xs text-muted-foreground">
            Searches {agg.coverage.queries ?? 0} · pages read {agg.coverage.pages_read ?? 0} · failed {agg.coverage.pages_failed ?? 0} · blocked{" "}
            {agg.coverage.pages_skipped_blocked ?? 0}
          </p>
        )}
      </div>

      {!agg ? (
        <p className="text-sm text-muted-foreground">{running ? "Results will appear when the run finishes." : "No results yet. Press Refresh to run the analysis."}</p>
      ) : agg.total_items === 0 ? (
        <p className="text-sm text-muted-foreground">The run finished but found no usable public items for this subject.</p>
      ) : (
        <>
          <div className="grid gap-4 lg:grid-cols-2">
            <div className="surface-card p-4">
              <h4 className="mb-2 text-sm font-semibold text-foreground">
                Sentiment split <span className="font-normal text-muted-foreground">({agg.total_items} items, overall {agg.overall.label})</span>
              </h4>
              {split && (
                <>
                  <div className="flex h-4 w-full overflow-hidden rounded" role="img" aria-label="Sentiment split">
                    {(["positive", "neutral", "negative"] as Sentiment[]).map((k) => (
                      <div key={k} style={{ width: `${split[k].pct}%`, background: SENT_COLOR[k] }} title={`${k} ${split[k].pct}%`} />
                    ))}
                  </div>
                  <ul className="mt-2 flex flex-wrap gap-4 text-xs">
                    {(["positive", "neutral", "negative"] as Sentiment[]).map((k) => (
                      <li key={k} className="flex items-center gap-1.5">
                        <span className="h-2.5 w-2.5 rounded-sm" style={{ background: SENT_COLOR[k] }} />
                        {k}: {split[k].count} ({split[k].pct}%)
                      </li>
                    ))}
                  </ul>
                </>
              )}
              {agg.ratings && agg.ratings.count > 0 && agg.ratings.avg !== null && (
                <p className="mt-2 text-xs text-muted-foreground">
                  Average star rating {agg.ratings.avg.toFixed(1)} across {agg.ratings.count} rated items.
                </p>
              )}
            </div>

            <div className="surface-card p-4">
              <h4 className="mb-2 text-sm font-semibold text-foreground">Volume by source</h4>
              {agg.volume_by_source.length === 0 ? (
                <p className="text-sm text-muted-foreground">No sources.</p>
              ) : (
                <div style={{ height: Math.max(120, agg.volume_by_source.slice(0, 8).length * 28) }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={agg.volume_by_source.slice(0, 8)} layout="vertical" margin={{ left: 10, right: 16 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="rgba(128,128,128,0.25)" />
                      <XAxis type="number" allowDecimals={false} fontSize={11} stroke="#888" />
                      <YAxis type="category" dataKey="domain" width={130} fontSize={11} stroke="#888" />
                      <Tooltip contentStyle={{ backgroundColor: "var(--card, #1a1a2e)", border: "1px solid rgba(128,128,128,0.4)", borderRadius: 8 }} />
                      <Bar dataKey="count" fill="#38bdf8" isAnimationActive={false} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}
            </div>
          </div>

          <div className="surface-card p-4">
            <h4 className="mb-2 text-sm font-semibold text-foreground">Sentiment over time</h4>
            {trend.length < 2 ? (
              <p className="text-sm text-muted-foreground">
                Not enough dated items for a trend{trend.length === 1 ? ` (only ${trend[0].period})` : ""}.
                {agg.undated_items > 0 ? ` ${agg.undated_items} items have no publish date.` : ""}
              </p>
            ) : (
              <>
                <div className="h-60">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={trend} margin={{ top: 8, right: 16, left: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="rgba(128,128,128,0.25)" />
                      <XAxis dataKey="period" fontSize={11} stroke="#888" />
                      <YAxis domain={[-1, 1]} fontSize={11} stroke="#888" width={36} />
                      <Tooltip
                        formatter={(v: number) => [v.toFixed(2), "Average sentiment (-1 to 1)"]}
                        contentStyle={{ backgroundColor: "var(--card, #1a1a2e)", border: "1px solid rgba(128,128,128,0.4)", borderRadius: 8 }}
                      />
                      <Line type="monotone" dataKey="avg_score" stroke="#a78bfa" strokeWidth={2} dot={{ r: 3 }} isAnimationActive={false} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
                <p className="mt-1 text-xs text-muted-foreground">
                  Monthly average sentiment from dated items only{agg.undated_items > 0 ? ` (${agg.undated_items} undated items excluded)` : ""}.
                </p>
              </>
            )}
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <ThemeList title="Top praised themes" themes={agg.top_praised_themes} tone="good" />
            <ThemeList title="Top complained themes" themes={agg.top_complained_themes} tone="bad" />
          </div>
        </>
      )}

      <div className="surface-card p-4">
        <h4 className="mb-2 text-sm font-semibold text-foreground">Items {items ? `(${items.total})` : ""}</h4>
        {items && items.rows.length === 0 ? (
          <p className="text-sm text-muted-foreground">No items collected.</p>
        ) : (
          <div className="overflow-x-auto rounded-md border border-border">
            <table className="w-full text-left text-xs">
              <thead className="bg-secondary/40 text-muted-foreground">
                <tr>
                  <th className="px-3 py-2">Excerpt</th>
                  <th className="px-3 py-2">Rating</th>
                  <th className="px-3 py-2">Date</th>
                  <th className="px-3 py-2">Sentiment</th>
                  <th className="px-3 py-2">Source</th>
                </tr>
              </thead>
              <tbody>
                {items?.rows.map((it) => (
                  <tr key={it.id} className="border-t border-border align-top">
                    <td className="max-w-md px-3 py-2">{it.excerpt}</td>
                    <td className="px-3 py-2">{it.rating ?? "—"}</td>
                    <td className="whitespace-nowrap px-3 py-2">{it.date ? fmtDate(it.date) : "—"}</td>
                    <td className="px-3 py-2">
                      <Pill tone={SENT_TONE[it.sentiment]}>{it.sentiment}</Pill>
                    </td>
                    <td className="px-3 py-2">
                      <ExternalLink href={safeHttpUrl(it.url)}>{it.domain}</ExternalLink>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {items && items.total > PAGE && (
          <div className="mt-2 flex items-center justify-between text-xs text-muted-foreground">
            <span>
              {offset + 1}-{Math.min(offset + PAGE, items.total)} of {items.total}
            </span>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>
                Previous
              </Button>
              <Button variant="outline" size="sm" disabled={offset + PAGE >= items.total} onClick={() => setOffset(offset + PAGE)}>
                Next
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

function CreateForm({ onCreated, onCancel }: { onCreated: (a: CampaignAnalysis) => void; onCancel: () => void }) {
  const { markDenied } = usePermission()
  const [name, setName] = useState("")
  const [mode, setMode] = useState<"own" | "free">("free")
  const [own, setOwn] = useState("")
  const [subject, setSubject] = useState("")
  const [keywords, setKeywords] = useState("")
  const [competitorId, setCompetitorId] = useState("")
  const [urls, setUrls] = useState("")
  const [campaigns, setCampaigns] = useState<Campaign[]>([])
  const [competitors, setCompetitors] = useState<{ id: string; name: string }[]>([])
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    listCampaigns({ limit: 100 })
      .then((c) => setCampaigns(Array.isArray(c) ? c : []))
      .catch(() => setCampaigns([]))
    getCompetitorOverview()
      .then((o) => setCompetitors(o.competitors.map((c) => ({ id: c.id, name: c.name }))))
      .catch(() => setCompetitors([]))
  }, [])

  async function save() {
    setErr(null)
    if (!name.trim()) return setErr("Enter a name for this analysis.")
    if (mode === "own" && !own) return setErr("Pick one of your campaigns, or switch to free text.")
    if (mode === "free" && subject.trim().length < 2) return setErr("Enter the brand or campaign to analyse.")
    const urlList = urls.split(/\s+/).map((u) => u.trim()).filter(Boolean)
    if (urlList.length > 10) return setErr("Use at most 10 source URLs.")
    for (const u of urlList) {
      try {
        const p = new URL(u)
        if (p.protocol !== "https:") throw new Error()
      } catch {
        return setErr(`Source URL must be a valid https:// address: ${u.slice(0, 80)}`)
      }
    }
    const kw = keywords.split(",").map((k) => k.trim()).filter(Boolean)
    setBusy(true)
    try {
      const created = await createCampaignAnalysis({
        name: name.trim(),
        ...(mode === "own" ? { own_campaign_id: own } : { subject: subject.trim() }),
        keywords: kw,
        sources: urlList.length ? urlList : "auto",
        ...(competitorId ? { competitor_id: competitorId } : {}),
      })
      onCreated(created)
    } catch (e) {
      if (e instanceof AnalyticsApiError && e.forbidden) markDenied()
      setErr(errText(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="surface-card space-y-3 p-4">
      <h3 className="text-sm font-semibold text-foreground">New campaign analysis</h3>
      <label className="block text-xs font-medium text-muted-foreground">
        Name
        <input className={cn(inputCls, "mt-1")} value={name} onChange={(e) => setName(e.target.value)} />
      </label>
      <div className="flex gap-4 text-xs text-muted-foreground">
        <label className="flex items-center gap-1.5">
          <input type="radio" checked={mode === "free"} onChange={() => setMode("free")} /> Brand / competitor campaign
        </label>
        <label className="flex items-center gap-1.5">
          <input type="radio" checked={mode === "own"} onChange={() => setMode("own")} /> One of my campaigns
        </label>
      </div>
      {mode === "own" ? (
        <select className={inputCls} value={own} onChange={(e) => setOwn(e.target.value)} aria-label="Own campaign">
          <option value="">Select a campaign…</option>
          {campaigns.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
      ) : (
        <input className={inputCls} value={subject} onChange={(e) => setSubject(e.target.value)} placeholder="e.g. Rival Fibre winter promotion" aria-label="Subject" />
      )}
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="text-xs font-medium text-muted-foreground">
          Keywords (comma separated, optional)
          <input className={cn(inputCls, "mt-1")} value={keywords} onChange={(e) => setKeywords(e.target.value)} />
        </label>
        <label className="text-xs font-medium text-muted-foreground">
          Competitor link (optional)
          <select className={cn(inputCls, "mt-1")} value={competitorId} onChange={(e) => setCompetitorId(e.target.value)}>
            <option value="">None</option>
            {competitors.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </label>
      </div>
      <label className="block text-xs font-medium text-muted-foreground">
        Source URLs (optional, one per line, max 10). Leave empty to search review sites, forums and news automatically.
        <textarea className={cn(inputCls, "mt-1 h-20 py-2")} value={urls} onChange={(e) => setUrls(e.target.value)} />
      </label>
      <ErrorNote message={err} />
      <div className="flex gap-2">
        <Button onClick={save} disabled={busy}>
          {busy && <Loader2 className="h-4 w-4 animate-spin" />}Start analysis
        </Button>
        <Button variant="outline" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </div>
  )
}

export function CampaignAnalysisView() {
  const { denied } = usePermission()
  const [list, setList] = useState<CampaignAnalysis[] | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)

  const load = useCallback(async () => {
    try {
      setList((await listCampaignAnalyses(50, 0)).items)
      setErr(null)
    } catch (e) {
      setErr(errText(e))
    }
  }, [])
  useEffect(() => {
    void load()
  }, [load])

  if (selected) return <Detail id={selected} onBack={() => setSelected(null)} onChanged={load} />

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-foreground">Campaign Analysis</h2>
          <p className="text-sm text-muted-foreground">What the public web says about a campaign or brand: sentiment, themes and sources.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <UsageIndicator />
          <Button onClick={() => setCreating(true)} disabled={denied} title={denied ? NO_RUN_TIP : undefined}>
            <Plus className="h-4 w-4" />
            New analysis
          </Button>
        </div>
      </div>
      <ErrorNote message={err} />
      {creating && (
        <CreateForm
          onCancel={() => setCreating(false)}
          onCreated={(a) => {
            setCreating(false)
            void load()
            setSelected(a.id)
          }}
        />
      )}
      {list === null && !err ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : list && list.length === 0 ? (
        <div className="rounded-lg border border-dashed border-border bg-secondary/20 p-6 text-center text-sm text-muted-foreground">
          No analyses yet. Create one to see sentiment and themes.
        </div>
      ) : (
        <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {list?.map((a) => (
            <li key={a.id}>
              <button type="button" onClick={() => setSelected(a.id)} className="surface-card w-full space-y-1 p-4 text-left hover:border-primary/50">
                <div className="flex items-start justify-between gap-2">
                  <p className="break-words font-semibold text-foreground">{a.name}</p>
                  <Pill tone={runTone(a.status)}>{a.status}</Pill>
                </div>
                <p className="text-xs text-muted-foreground">Subject: {a.subject}</p>
                <p className="text-xs text-muted-foreground">
                  {a.item_count} items · last run {a.last_run_at ? fmtDate(a.last_run_at) : "never"}
                </p>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
