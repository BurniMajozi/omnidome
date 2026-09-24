"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import {
  CalendarClock, ChevronDown, ChevronRight, ExternalLink, FileText, Globe, Image as ImageIcon, Loader2,
  Pause, Play, Plus, RefreshCw, Trash2, X,
} from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { opportunityApi, type Tender, type TenderSource, type TenderStatus } from "@/lib/fno-api"
import { salesApi } from "@/lib/sales-api"

const INTERVALS: { hours: 12 | 24 | 168; label: string }[] = [
  { hours: 12, label: "Twice a day" },
  { hours: 24, label: "Daily" },
  { hours: 168, label: "Weekly" },
]

const TENDER_STATUSES: { id: TenderStatus; label: string }[] = [
  { id: "new", label: "New" },
  { id: "reviewing", label: "Reviewing" },
  { id: "bidding", label: "Bidding" },
  { id: "skipped", label: "Skipped" },
]

// Shared by the "add source" form and the sources table so they line up.
const SOURCE_GRID = "grid grid-cols-[minmax(0,44fr)_minmax(0,20fr)_minmax(0,14fr)_minmax(0,22fr)] gap-3"

function timeAgo(iso: string | null, now: number) {
  if (!iso) return "never"
  const mins = Math.round((now - new Date(iso).getTime()) / 60000)
  if (mins < 1) return "just now"
  if (mins < 60) return `${mins} min ago`
  const hours = Math.round(mins / 60)
  return hours < 48 ? `${hours} h ago` : `${Math.round(hours / 24)} days ago`
}

function formatDateTime(iso: string | null) {
  if (!iso) return null
  return new Date(iso).toLocaleString("en-ZA", {
    day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", timeZone: "Africa/Johannesburg",
  })
}

function Countdown({ closingAt, now }: { closingAt: string | null; now: number }) {
  if (!closingAt) return null
  const ms = new Date(closingAt).getTime() - now
  if (ms <= 0) return <Badge variant="outline" className="border-muted-foreground/40 text-[10px] text-muted-foreground">Closed</Badge>
  const days = Math.floor(ms / 86400000)
  const hours = Math.floor((ms % 86400000) / 3600000)
  const urgent = days < 3
  return (
    <Badge variant="outline" className={`text-[10px] ${urgent ? "border-red-500/50 text-red-400" : "border-emerald-500/40 text-emerald-400"}`}>
      {days > 0 ? `${days}d ${hours}h left` : `${hours}h left`}
    </Badge>
  )
}

function sourceName(s: TenderSource) {
  if (s.label) return s.label
  try {
    return new URL(s.url).hostname.replace(/^www\./, "")
  } catch {
    return s.url
  }
}

export function OpportunityTenders() {
  const [sources, setSources] = useState<TenderSource[] | null>(null)
  const [tenders, setTenders] = useState<Tender[] | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)

  const [url, setUrl] = useState("")
  const [label, setLabel] = useState("")
  const [interval, setIntervalHours] = useState<12 | 24 | 168>(24)
  const [formError, setFormError] = useState<string | null>(null)
  const [adding, setAdding] = useState(false)
  const [sourceBusy, setSourceBusy] = useState<Record<string, boolean>>({})

  const [statusFilter, setStatusFilter] = useState<TenderStatus | "">("")
  const [sourceFilter, setSourceFilter] = useState("")
  const [showClosed, setShowClosed] = useState(false)
  const [expanded, setExpanded] = useState<string | null>(null)
  const [rowBusy, setRowBusy] = useState<Record<string, boolean>>({})
  const [rowError, setRowError] = useState<Record<string, string>>({})
  const [evidence, setEvidence] = useState<{ url: string; title: string } | null>(null)
  // Countdowns and "last checked" times tick once a minute.
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 60000)
    return () => clearInterval(timer)
  }, [])

  const loadSources = useCallback(() => opportunityApi.listSources().then(setSources), [])
  const loadTenders = useCallback(
    () => opportunityApi.listTenders({
      status: statusFilter || undefined, source_id: sourceFilter || undefined, include_closed: showClosed,
    }).then(setTenders),
    [statusFilter, sourceFilter, showClosed],
  )

  useEffect(() => {
    loadSources().catch((err) => setLoadError(err instanceof Error ? err.message : "Couldn't load sources"))
  }, [loadSources])
  useEffect(() => {
    loadTenders().catch((err) => setLoadError(err instanceof Error ? err.message : "Couldn't load tenders"))
  }, [loadTenders])

  // While any source is queued or scanning, poll; when a scan finishes, reload tenders.
  const scanning = (sources ?? []).some((s) => s.last_status === "queued" || s.last_status === "scanning")
  useEffect(() => {
    if (!scanning) return
    const timer = setInterval(async () => {
      try {
        const next = await opportunityApi.listSources()
        setSources(next)
        if (!next.some((s) => s.last_status === "queued" || s.last_status === "scanning")) await loadTenders()
      } catch {
        // keep polling
      }
    }, 5000)
    return () => clearInterval(timer)
  }, [scanning, loadTenders])

  const addSource = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!url.trim()) {
      setFormError("Paste the address of the page that lists the tenders")
      return
    }
    setAdding(true)
    setFormError(null)
    try {
      const created = await opportunityApi.createSource(url.trim(), label.trim() || null, interval)
      setSources((prev) => [created, ...(prev ?? [])])
      setUrl("")
      setLabel("")
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Couldn't add that page")
    } finally {
      setAdding(false)
    }
  }

  const sourceAction = async (s: TenderSource, fn: () => Promise<unknown>) => {
    setSourceBusy((p) => ({ ...p, [s.id]: true }))
    try {
      await fn()
      await loadSources()
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : "That didn't work")
    } finally {
      setSourceBusy((p) => ({ ...p, [s.id]: false }))
    }
  }

  const removeSource = (s: TenderSource) => {
    if (!window.confirm(`Stop watching "${sourceName(s)}"? Its tenders are removed too.`)) return
    sourceAction(s, async () => {
      await opportunityApi.deleteSource(s.id)
      await loadTenders()
    })
  }

  const showEvidence = async (snapshotId: string, title: string) => {
    try {
      setEvidence({ url: await opportunityApi.screenshotUrl(snapshotId), title })
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : "Screenshot not available")
    }
  }

  const closeEvidence = () => {
    if (evidence) URL.revokeObjectURL(evidence.url)
    setEvidence(null)
  }

  const updateTender = (t: Tender) =>
    setTenders((prev) => (prev ?? []).map((x) => (x.id === t.id ? { ...x, ...t, source_label: t.source_label ?? x.source_label } : x)))

  const tenderAction = async (t: Tender, fn: () => Promise<void>) => {
    setRowBusy((p) => ({ ...p, [t.id]: true }))
    setRowError((p) => { const n = { ...p }; delete n[t.id]; return n })
    try {
      await fn()
    } catch (err) {
      setRowError((p) => ({ ...p, [t.id]: err instanceof Error ? err.message : "That didn't work" }))
    } finally {
      setRowBusy((p) => ({ ...p, [t.id]: false }))
    }
  }

  const setStatus = (t: Tender, status: TenderStatus) =>
    tenderAction(t, async () => updateTender(await opportunityApi.patchTender(t.id, { status })))

  const addToPipeline = (t: Tender) =>
    tenderAction(t, async () => {
      const lead = await salesApi.createLead({
        first_name: t.issuer || t.source_label || "Tender",
        last_name: t.reference ? `(${t.reference})` : "",
        source: "TENDER",
        interest_level: 4,
        notes: [
          `Tender: ${t.title}.`,
          t.reference ? `Reference: ${t.reference}.` : null,
          t.closing_text ? `Closes: ${t.closing_text}.` : null,
          t.briefing_text ? `Briefing: ${t.briefing_text}.` : null,
          t.required_documents.length ? `Required documents: ${t.required_documents.join("; ")}.` : null,
          t.detail_url ? `Details: ${t.detail_url}` : null,
        ].filter(Boolean).join(" "),
      })
      updateTender(await opportunityApi.patchTender(t.id, {
        sales_lead_id: lead.id, status: t.status === "new" ? "reviewing" : t.status,
      }))
    })

  const sourceById = useMemo(() => new Map((sources ?? []).map((s) => [s.id, s])), [sources])

  if (loadError && !sources) {
    return <div className="surface-card p-5 text-sm text-red-400">Couldn&apos;t load tenders: {loadError}</div>
  }

  return (
    <div className="space-y-6">
      {/* Sources */}
      <div className="surface-card p-5 space-y-4">
        <div>
          <h4 className="text-sm font-bold text-foreground flex items-center gap-2">
            <Globe className="h-4 w-4 text-amber-400" />
            Pages we watch for tenders and RFQs
          </h4>
          <p className="text-xs text-muted-foreground">
            Paste the address of any page that lists tenders (a government portal, municipality or company supplier page).
            We read it on a schedule, keep a screenshot as evidence, and list every tender we find.
          </p>
        </div>

        <form onSubmit={addSource} className={`${SOURCE_GRID} items-end rounded-xl border border-border bg-muted/10 p-3`}>
          <label className="space-y-1">
            <span className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Page address</span>
            <input value={url} onChange={(e) => { setUrl(e.target.value); setFormError(null) }} inputMode="url"
              placeholder="https://www.sita.co.za/content/invitations"
              className="w-full rounded-lg border border-border bg-background px-2.5 py-2 text-xs focus:outline-none focus:ring-1 focus:ring-primary" />
          </label>
          <label className="space-y-1">
            <span className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Name (optional)</span>
            <input value={label} onChange={(e) => setLabel(e.target.value)} maxLength={200} placeholder="SITA invitations"
              className="w-full rounded-lg border border-border bg-background px-2.5 py-2 text-xs focus:outline-none focus:ring-1 focus:ring-primary" />
          </label>
          <label className="space-y-1">
            <span className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Check</span>
            <select value={interval} onChange={(e) => setIntervalHours(Number(e.target.value) as 12 | 24 | 168)}
              className="w-full rounded-lg border border-border bg-background px-2 py-2 text-xs focus:outline-none focus:ring-1 focus:ring-primary">
              {INTERVALS.map((i) => <option key={i.hours} value={i.hours}>{i.label}</option>)}
            </select>
          </label>
          <Button type="submit" size="sm" className="h-9 gap-1.5 text-xs" disabled={adding}>
            {adding ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />}
            Watch this page
          </Button>
        </form>
        {formError && <p className="text-[11px] text-red-400">{formError}</p>}

        {!sources ? (
          <div className="flex items-center gap-2 text-xs text-muted-foreground"><Loader2 className="h-3.5 w-3.5 animate-spin" /> Loading…</div>
        ) : sources.length === 0 ? (
          <p className="rounded-lg border border-dashed border-border p-4 text-xs text-muted-foreground">
            No pages yet. Add one above and the first scan starts straight away.
          </p>
        ) : (
          <div className="rounded-lg border border-border">
            <div className={`${SOURCE_GRID} border-b border-border px-3 py-2 text-[11px] font-medium text-muted-foreground`}>
              <span>Page</span><span>Last checked</span><span className="text-right">Tenders</span><span className="text-right">Actions</span>
            </div>
            <ul className="divide-y divide-border/60">
              {sources.map((s) => {
                const busy = sourceBusy[s.id]
                const working = s.last_status === "queued" || s.last_status === "scanning"
                return (
                  <li key={s.id} className={`px-3 py-2 text-xs ${s.active ? "" : "opacity-60"}`}>
                    <div className={`${SOURCE_GRID} items-center`}>
                      <div className="min-w-0">
                        <div className="truncate font-medium text-foreground">{sourceName(s)}</div>
                        <a href={s.url} target="_blank" rel="noopener noreferrer" className="block truncate text-[10px] text-muted-foreground hover:text-primary">{s.url}</a>
                      </div>
                      <div>
                        {working ? (
                          <span className="inline-flex items-center gap-1 text-blue-400"><Loader2 className="h-3 w-3 animate-spin" /> Reading the page…</span>
                        ) : s.last_status === "failed" ? (
                          <span className="text-red-400" title={s.last_error ?? undefined}>Failed {timeAgo(s.last_scanned_at, now)}</span>
                        ) : (
                          <span className="text-muted-foreground">{timeAgo(s.last_scanned_at, now)}{s.active ? "" : " · paused"}</span>
                        )}
                      </div>
                      <div className="text-right font-semibold text-foreground">{s.tender_count}</div>
                      <div className="flex items-center justify-end gap-1">
                        {s.latest_snapshot_id && (
                          <Button variant="ghost" size="icon" className="h-7 w-7" title="See the page as we last saw it"
                            aria-label={`Screenshot of ${sourceName(s)}`} onClick={() => showEvidence(s.latest_snapshot_id!, sourceName(s))}>
                            <ImageIcon className="h-3.5 w-3.5" />
                          </Button>
                        )}
                        <Button variant="ghost" size="icon" className="h-7 w-7" title="Check now" aria-label={`Check ${sourceName(s)} now`}
                          disabled={busy || working} onClick={() => sourceAction(s, () => opportunityApi.scanSource(s.id))}>
                          <RefreshCw className="h-3.5 w-3.5" />
                        </Button>
                        <Button variant="ghost" size="icon" className="h-7 w-7" title={s.active ? "Pause" : "Resume"}
                          aria-label={s.active ? `Pause ${sourceName(s)}` : `Resume ${sourceName(s)}`} disabled={busy}
                          onClick={() => sourceAction(s, () => opportunityApi.patchSource(s.id, { active: !s.active }))}>
                          {s.active ? <Pause className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5" />}
                        </Button>
                        <Button variant="ghost" size="icon" className="h-7 w-7 text-muted-foreground hover:text-red-400" title="Stop watching"
                          aria-label={`Stop watching ${sourceName(s)}`} disabled={busy} onClick={() => removeSource(s)}>
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      </div>
                    </div>
                    {s.last_status === "failed" && s.last_error && <p className="mt-1 text-[10px] text-red-400">{s.last_error}</p>}
                  </li>
                )
              })}
            </ul>
          </div>
        )}
      </div>

      {/* Tenders */}
      <div className="surface-card p-5 space-y-4">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h4 className="text-sm font-bold text-foreground flex items-center gap-2">
              <FileText className="h-4 w-4 text-amber-400" />
              Tenders and RFQs
            </h4>
            <p className="text-xs text-muted-foreground">Soonest closing first. Open a row for documents and briefing details.</p>
          </div>
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <select value={sourceFilter} onChange={(e) => setSourceFilter(e.target.value)} aria-label="Filter by page"
              className="rounded-lg border border-border bg-background px-2 py-1.5 text-xs">
              <option value="">All pages</option>
              {(sources ?? []).map((s) => <option key={s.id} value={s.id}>{sourceName(s)}</option>)}
            </select>
            <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value as TenderStatus | "")} aria-label="Filter by status"
              className="rounded-lg border border-border bg-background px-2 py-1.5 text-xs">
              <option value="">Any status</option>
              {TENDER_STATUSES.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
            </select>
            <label className="flex items-center gap-1.5 text-muted-foreground">
              <input type="checkbox" checked={showClosed} onChange={(e) => setShowClosed(e.target.checked)} className="h-3 w-3 accent-primary" />
              Show closed
            </label>
          </div>
        </div>

        {!tenders ? (
          <div className="flex items-center gap-2 text-xs text-muted-foreground"><Loader2 className="h-3.5 w-3.5 animate-spin" /> Loading tenders…</div>
        ) : tenders.length === 0 ? (
          <p className="rounded-lg border border-dashed border-border p-4 text-xs text-muted-foreground">
            {scanning ? "Reading your pages — tenders appear here when the scan finishes." : "No open tenders yet. Add a page above, or show closed ones."}
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-border text-left text-muted-foreground">
                  <th className="py-2 pr-3 font-medium w-[40%]">Tender</th>
                  <th className="py-2 pr-3 font-medium">Closes</th>
                  <th className="py-2 pr-3 font-medium">Briefing</th>
                  <th className="py-2 pr-3 text-right font-medium">Docs</th>
                  <th className="py-2 pr-3 font-medium">Status</th>
                  <th className="py-2 text-right font-medium">Actions</th>
                </tr>
              </thead>
              <tbody>
                {tenders.map((t) => {
                  const open = expanded === t.id
                  const docs = t.required_documents.length + t.document_links.length
                  const src = sourceById.get(t.source_id)
                  return [
                    <tr key={t.id} className="border-b border-border/50 align-top hover:bg-muted/20">
                      <td className="py-2 pr-3">
                        <button type="button" className="flex items-start gap-1.5 text-left" onClick={() => setExpanded(open ? null : t.id)} aria-expanded={open}>
                          {open ? <ChevronDown className="mt-0.5 h-3 w-3 shrink-0" /> : <ChevronRight className="mt-0.5 h-3 w-3 shrink-0" />}
                          <span>
                            <span className="font-medium text-foreground line-clamp-2">{t.title}</span>
                            <span className="block text-[10px] text-muted-foreground">
                              {[t.reference, t.issuer || (src ? sourceName(src) : t.source_label)].filter(Boolean).join(" · ")}
                            </span>
                          </span>
                        </button>
                      </td>
                      <td className="py-2 pr-3 whitespace-nowrap">
                        <div className="text-foreground">{formatDateTime(t.closing_at) ?? t.closing_text ?? "—"}</div>
                        <Countdown closingAt={t.closing_at} now={now} />
                      </td>
                      <td className="py-2 pr-3 max-w-[180px]">
                        {t.briefing_text ? (
                          <span className="inline-flex items-start gap-1 text-muted-foreground">
                            <CalendarClock className="mt-0.5 h-3 w-3 shrink-0" /><span className="line-clamp-2">{t.briefing_text}</span>
                          </span>
                        ) : <span className="text-muted-foreground">—</span>}
                      </td>
                      <td className="py-2 pr-3 text-right">{docs || "—"}</td>
                      <td className="py-2 pr-3">
                        <select value={t.status} onChange={(e) => setStatus(t, e.target.value as TenderStatus)} disabled={rowBusy[t.id]}
                          aria-label={`Status of ${t.title}`} className="rounded-md border border-border bg-background px-1.5 py-1 text-[11px]">
                          {TENDER_STATUSES.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
                        </select>
                      </td>
                      <td className="py-2 text-right whitespace-nowrap">
                        {t.snapshot_id && (
                          <Button variant="ghost" size="icon" className="h-7 w-7" title="Evidence: the page when we found this tender"
                            aria-label={`Evidence for ${t.title}`} onClick={() => showEvidence(t.snapshot_id!, t.title)}>
                            <ImageIcon className="h-3.5 w-3.5" />
                          </Button>
                        )}
                        {t.sales_lead_id ? (
                          <Badge variant="outline" className="border-emerald-500/40 text-[10px] text-emerald-400">In pipeline</Badge>
                        ) : (
                          <Button variant="outline" size="sm" className="h-7 gap-1 px-2 text-[11px]" disabled={rowBusy[t.id]} onClick={() => addToPipeline(t)}>
                            {rowBusy[t.id] ? <Loader2 className="h-3 w-3 animate-spin" /> : <Plus className="h-3 w-3" />} Add to pipeline
                          </Button>
                        )}
                        {rowError[t.id] && <p className="mt-1 text-[10px] text-red-400">{rowError[t.id]}</p>}
                      </td>
                    </tr>,
                    open && (
                      <tr key={`${t.id}-open`} className="border-b border-border/50 bg-muted/10">
                        <td colSpan={6} className="px-6 py-3 text-[11px]">
                          <div className="grid gap-4 md:grid-cols-3">
                            <div className="space-y-1">
                              <div className="font-semibold text-foreground">About</div>
                              <p className="text-muted-foreground">{t.description || "No description on the page."}</p>
                              {t.contact && <p className="text-muted-foreground">Contact: {t.contact}</p>}
                              {(t.detail_url || src) && (
                                <a href={t.detail_url || src!.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-primary hover:underline">
                                  Open the tender page <ExternalLink className="h-3 w-3" />
                                </a>
                              )}
                            </div>
                            <div className="space-y-1">
                              <div className="font-semibold text-foreground">Required documents</div>
                              {t.required_documents.length ? (
                                <ul className="list-disc space-y-0.5 pl-4 text-muted-foreground">
                                  {t.required_documents.map((d) => <li key={d}>{d}</li>)}
                                </ul>
                              ) : <p className="text-muted-foreground">Not listed on the page — check the tender documents.</p>}
                            </div>
                            <div className="space-y-1">
                              <div className="font-semibold text-foreground">Documents and briefing</div>
                              {t.document_links.length ? (
                                <ul className="space-y-0.5">
                                  {t.document_links.map((l) => (
                                    <li key={l.url}>
                                      <a href={l.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-primary hover:underline">
                                        <FileText className="h-3 w-3" /> {l.label || l.url.split("/").pop()}
                                      </a>
                                    </li>
                                  ))}
                                </ul>
                              ) : <p className="text-muted-foreground">No downloads found on the page.</p>}
                              {t.briefing_text && <p className="text-muted-foreground">Briefing: {t.briefing_text}{t.briefing_location ? ` (${t.briefing_location})` : ""}</p>}
                            </div>
                          </div>
                        </td>
                      </tr>
                    ),
                  ]
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {evidence && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" role="dialog" aria-label="Page screenshot" onClick={closeEvidence}>
          <div className="max-h-[90vh] w-full max-w-4xl overflow-hidden rounded-xl border border-border bg-card" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between border-b border-border px-4 py-2 text-xs">
              <span className="truncate font-medium text-foreground">Evidence: {evidence.title}</span>
              <button type="button" onClick={closeEvidence} aria-label="Close screenshot" className="rounded p-1 text-muted-foreground hover:bg-muted">
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="max-h-[80vh] overflow-y-auto"><img src={evidence.url} alt={`Screenshot of the page for ${evidence.title}`} className="w-full" /></div>
          </div>
        </div>
      )}
    </div>
  )
}
