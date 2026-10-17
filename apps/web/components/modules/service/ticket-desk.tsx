"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { BarChart3, Inbox, Loader2, Plus, RefreshCw, Repeat, Search, Settings2 } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { NotConnected } from "@/components/ui/not-connected"
import {
  SupportApiError, supportApi, type Assignee, type Ticket, type TicketMeta, type TicketSearch, type TicketSummary,
} from "@/lib/support-api"
import {
  PRIORITY_TONE, SLA_TONE, SOURCE_LABELS, STATUS_LABELS, ageLabel, formatHours, labelOf, slaView, viewFilters, type DeskView,
} from "@/lib/support-derive"
import type { Loadable } from "@/lib/service-state"
import { TicketCreateDialog } from "./ticket-create-dialog"
import { TicketDetail } from "./ticket-detail"
import { TicketPerformance } from "./ticket-performance"
import { TicketRulesPanel } from "./ticket-rules-panel"

const FIELD = "h-9 rounded-md border border-input bg-background px-2 text-sm"
const PAGE = 40
const POLL_MS = 30_000

const VIEWS: { id: DeskView; label: string; count: (s: TicketSummary) => number | null }[] = [
  { id: "open", label: "Open", count: (s) => s.open },
  { id: "mine", label: "Mine", count: (s) => s.mine },
  { id: "unassigned", label: "Unassigned", count: (s) => s.unassigned },
  { id: "breached", label: "Overdue", count: (s) => s.breached },
  { id: "closed", label: "Closed", count: (s) => s.closed },
  { id: "all", label: "All", count: (s) => s.total },
]

const asLoadable = (e: unknown): Loadable<never> => {
  const status = e instanceof SupportApiError ? e.status : null
  if (status === 401 || status === 403) return { state: "denied", status }
  if (status === null || status === 502 || status === 503 || status === 504) return { state: "unreachable", status }
  return { state: "error", status, message: e instanceof Error ? e.message : undefined }
}

function readTicketParam(): string | null {
  try {
    return new URLSearchParams(window.location.search).get("ticket")
  } catch {
    return null
  }
}

function writeTicketParam(id: string | null) {
  try {
    const url = new URL(window.location.href)
    if (id) url.searchParams.set("ticket", id)
    else url.searchParams.delete("ticket")
    window.history.replaceState(null, "", url.toString())
  } catch {
    /* non-browser */
  }
}

/** The ticket desk: every ticket, wherever it came from, with filters, SLA, assignment and a full timeline. */
export function TicketDesk() {
  const [panel, setPanel] = useState<"tickets" | "performance" | "rules">("tickets")
  const [view, setView] = useState<DeskView>("open")
  const [q, setQ] = useState("")
  const [debouncedQ, setDebouncedQ] = useState("")
  const [source, setSource] = useState("")
  const [priority, setPriority] = useState("")
  const [queue, setQueue] = useState("")
  const [sort, setSort] = useState<"newest" | "priority" | "sla" | "updated">("newest")
  const [offset, setOffset] = useState(0)
  const [result, setResult] = useState<TicketSearch | null>(null)
  const [failure, setFailure] = useState<Loadable<never> | null>(null)
  const [loading, setLoading] = useState(true)
  const [summary, setSummary] = useState<TicketSummary | null>(null)
  const [meta, setMeta] = useState<TicketMeta | null>(null)
  const [assignees, setAssignees] = useState<Assignee[]>([])
  const [selected, setSelected] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const seq = useRef(0)

  useEffect(() => {
    setSelected(readTicketParam())
    supportApi.meta().then(setMeta).catch(() => undefined)
    supportApi.assignees().then(setAssignees).catch(() => undefined)
  }, [])

  useEffect(() => {
    const t = setTimeout(() => setDebouncedQ(q.trim()), 300)
    return () => clearTimeout(t)
  }, [q])

  useEffect(() => setOffset(0), [view, debouncedQ, source, priority, queue, sort])

  const load = useCallback(
    async (quiet = false) => {
      const mine = ++seq.current
      if (!quiet) setLoading(true)
      try {
        const [list, sum] = await Promise.all([
          supportApi.search({
            ...viewFilters(view), q: debouncedQ || undefined, source: source || undefined, priority: priority || undefined,
            queue: queue || undefined, sort, limit: PAGE, offset,
          }),
          supportApi.summary(),
        ])
        if (mine !== seq.current) return
        setResult(list)
        setSummary(sum)
        setFailure(null)
      } catch (e) {
        if (mine === seq.current) setFailure(asLoadable(e))
      } finally {
        if (mine === seq.current) setLoading(false)
      }
    },
    [view, debouncedQ, source, priority, queue, sort, offset],
  )

  useEffect(() => {
    if (panel !== "tickets") return
    void load()
    const id = setInterval(() => {
      if (document.visibilityState === "visible") void load(true)
    }, POLL_MS)
    return () => clearInterval(id)
  }, [load, panel])

  const select = (id: string | null) => {
    setSelected(id)
    writeTicketParam(id)
  }

  const onChanged = (t: Ticket) => {
    setResult((cur) => (cur ? { ...cur, items: cur.items.map((x) => (x.id === t.id ? { ...x, ...t, timeline: undefined } : x)) } : cur))
    void supportApi.summary().then(setSummary).catch(() => undefined)
  }

  const tiles = useMemo(
    () =>
      summary
        ? [
            { label: "Open", value: String(summary.open) },
            { label: "Unassigned", value: String(summary.unassigned), warn: summary.unassigned > 0 },
            { label: "Mine", value: String(summary.mine) },
            { label: "Overdue", value: String(summary.breached), bad: summary.breached > 0 },
            { label: "Avg response", value: summary.avg_response_hours == null ? "No data yet" : formatHours(summary.avg_response_hours) },
            { label: "Avg resolution", value: summary.avg_resolution_hours === null ? "No data yet" : formatHours(summary.avg_resolution_hours) },
            { label: "Gone quiet", value: String(summary.stale ?? 0), warn: (summary.stale ?? 0) > 0 },
          ]
        : [],
    [summary],
  )

  const items = result?.items ?? []

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex gap-1" role="tablist" aria-label="Ticket desk sections">
          <Button role="tab" aria-selected={panel === "tickets"} size="sm" variant={panel === "tickets" ? "default" : "outline"} onClick={() => setPanel("tickets")}>
            <Inbox className="mr-1.5 h-3.5 w-3.5" /> Tickets
          </Button>
          <Button role="tab" aria-selected={panel === "performance"} size="sm" variant={panel === "performance" ? "default" : "outline"} onClick={() => setPanel("performance")}>
            <BarChart3 className="mr-1.5 h-3.5 w-3.5" /> Performance
          </Button>
          <Button role="tab" aria-selected={panel === "rules"} size="sm" variant={panel === "rules" ? "default" : "outline"} onClick={() => setPanel("rules")}>
            <Settings2 className="mr-1.5 h-3.5 w-3.5" /> Automatic rules
          </Button>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => void load()} aria-label="Refresh tickets">
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
          </Button>
          <Button size="sm" onClick={() => setCreating(true)}>
            <Plus className="mr-1.5 h-3.5 w-3.5" /> New ticket
          </Button>
        </div>
      </div>

      {panel === "rules" ? (
        <TicketRulesPanel meta={meta} assignees={assignees} />
      ) : panel === "performance" ? (
        <TicketPerformance
          assignees={assignees}
          onOpenTicket={(id) => {
            setPanel("tickets")
            setView("all")
            select(id)
          }}
        />
      ) : (
        <>
          {tiles.length > 0 && (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-7">
              {tiles.map((t) => (
                <div key={t.label} className="surface-card p-3">
                  <p className="text-xs text-muted-foreground">{t.label}</p>
                  <p className={`mt-1 text-xl font-semibold ${t.bad ? "text-red-400" : t.warn ? "text-amber-400" : ""}`}>{t.value}</p>
                </div>
              ))}
            </div>
          )}

          <div className="flex flex-wrap items-center gap-2">
            <div role="tablist" aria-label="Ticket views" className="flex flex-wrap gap-1">
              {VIEWS.map((v) => {
                const n = summary ? v.count(summary) : null
                return (
                  <Button key={v.id} role="tab" aria-selected={view === v.id} size="sm" variant={view === v.id ? "secondary" : "ghost"} className="h-8" onClick={() => setView(v.id)}>
                    {v.label}
                    {n !== null && <span className="ml-1.5 rounded-full bg-muted px-1.5 text-[10px] text-muted-foreground">{n}</span>}
                  </Button>
                )
              })}
            </div>
            <div className="relative ml-auto min-w-52 flex-1 sm:max-w-xs">
              <Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
              <Input className="pl-8" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search subject, text or T-123" aria-label="Search tickets" />
            </div>
            <select className={FIELD} aria-label="Filter by source" value={source} onChange={(e) => setSource(e.target.value)}>
              <option value="">All sources</option>
              {(meta?.sources ?? Object.keys(SOURCE_LABELS)).map((s) => <option key={s} value={s}>{labelOf(SOURCE_LABELS, s)}</option>)}
            </select>
            <select className={FIELD} aria-label="Filter by priority" value={priority} onChange={(e) => setPriority(e.target.value)}>
              <option value="">Any priority</option>
              {(meta?.priorities ?? []).map((p) => <option key={p} value={p}>{labelOf({}, p)}</option>)}
            </select>
            <select className={FIELD} aria-label="Filter by queue" value={queue} onChange={(e) => setQueue(e.target.value)}>
              <option value="">Any queue</option>
              {(meta?.queues ?? []).map((p) => <option key={p} value={p}>{labelOf({}, p)}</option>)}
            </select>
            <select className={FIELD} aria-label="Sort tickets" value={sort} onChange={(e) => setSort(e.target.value as typeof sort)}>
              <option value="newest">Newest first</option>
              <option value="priority">Highest priority</option>
              <option value="sla">SLA due soonest</option>
              <option value="updated">Recently updated</option>
            </select>
          </div>

          {failure && !result ? (
            <NotConnected loadable={failure} service="Support" onRetry={() => void load()} />
          ) : (
            <div className="grid gap-4 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
              <div className={`surface-card overflow-hidden ${selected ? "hidden lg:block" : ""}`}>
                {loading && !result ? (
                  <div className="flex min-h-48 items-center justify-center text-muted-foreground"><Loader2 className="h-5 w-5 animate-spin" aria-label="Loading tickets" /></div>
                ) : items.length === 0 ? (
                  <div className="flex min-h-48 flex-col items-center justify-center gap-2 p-6 text-center">
                    <Inbox className="h-8 w-8 text-muted-foreground" />
                    <p className="text-sm font-medium">No tickets here</p>
                    <p className="max-w-xs text-xs text-muted-foreground">
                      {summary && summary.total === 0
                        ? "Nothing has been raised yet. Create one, or let emails, calls, payments and HomeDome alerts open them for you."
                        : "No ticket matches these filters."}
                    </p>
                    {summary?.total === 0 && <Button size="sm" onClick={() => setCreating(true)}>New ticket</Button>}
                  </div>
                ) : (
                  <ul className="divide-y divide-border" aria-label="Tickets">
                    {items.map((t) => {
                      const sla = slaView(t.sla_state, t.sla_due_at)
                      const active = selected === t.id
                      return (
                        <li key={t.id}>
                          <button
                            type="button"
                            onClick={() => select(t.id)}
                            aria-current={active}
                            className={`flex w-full flex-col gap-1.5 px-4 py-3 text-left transition-colors hover:bg-muted/50 ${active ? "bg-muted/60" : ""}`}
                          >
                            <div className="flex items-center gap-2 text-xs text-muted-foreground">
                              <span className="font-mono">{t.ticket_ref ?? t.id.slice(0, 8)}</span>
                              <span>·</span>
                              <span>{labelOf(SOURCE_LABELS, t.source)}</span>
                              <span className="ml-auto">{ageLabel(t.created_at)}</span>
                            </div>
                            <p className="line-clamp-2 break-words text-sm font-medium">{t.subject}</p>
                            <div className="flex flex-wrap items-center gap-2">
                              <Badge variant="outline" className={`text-[10px] ${PRIORITY_TONE[t.priority]}`}>{labelOf({}, t.priority)}</Badge>
                              <Badge variant="outline" className="text-[10px]">{labelOf(STATUS_LABELS, t.status)}</Badge>
                              <span className={`text-[11px] font-medium ${SLA_TONE[sla.tone]}`}>{sla.label}</span>
                              {t.stale && !t.overdue && (
                                <span className="text-[11px] text-amber-400" title="No activity for longer than this priority allows">Gone quiet</span>
                              )}
                              {t.occurrence_count > 1 && (
                                <span className="inline-flex items-center gap-1 text-[11px] text-amber-400" title="Repeats folded into this ticket">
                                  <Repeat className="h-3 w-3" />{t.occurrence_count}
                                </span>
                              )}
                              <span className="ml-auto text-[11px] text-muted-foreground">
                                {t.assigned_to ? assignees.find((a) => a.id === t.assigned_to)?.name ?? "Assigned" : "Unassigned"}
                              </span>
                            </div>
                          </button>
                        </li>
                      )
                    })}
                  </ul>
                )}
                {result && result.total > PAGE && (
                  <div className="flex items-center justify-between border-t border-border px-4 py-2 text-xs text-muted-foreground">
                    <span>{offset + 1}–{Math.min(offset + PAGE, result.total)} of {result.total}</span>
                    <div className="flex gap-1">
                      <Button size="sm" variant="ghost" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>Previous</Button>
                      <Button size="sm" variant="ghost" disabled={offset + PAGE >= result.total} onClick={() => setOffset(offset + PAGE)}>Next</Button>
                    </div>
                  </div>
                )}
              </div>

              <div className={selected ? "" : "hidden lg:block"}>
                {selected ? (
                  <TicketDetail ticketId={selected} meta={meta} assignees={assignees} onChanged={onChanged} onClose={() => select(null)} />
                ) : (
                  <div className="surface-card flex min-h-48 items-center justify-center p-6 text-sm text-muted-foreground">Select a ticket to see its timeline</div>
                )}
              </div>
            </div>
          )}
        </>
      )}

      <TicketCreateDialog
        open={creating}
        onOpenChange={setCreating}
        meta={meta}
        assignees={assignees}
        onCreated={(t) => {
          setView("open")
          select(t.id)
          void load()
        }}
      />
    </div>
  )
}
