"use client"

import { useCallback, useEffect, useState } from "react"
import { Loader2, RefreshCw } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { supportApi, type Assignee, type KpiBlock, type LateTicket, type TicketKpis } from "@/lib/support-api"
import { CATEGORY_LABELS, PRIORITY_TONE, STATUS_LABELS, formatHours, formatPct, labelOf } from "@/lib/support-derive"

const FIELD = "h-8 rounded-md border border-input bg-background px-2 text-xs"
const WINDOWS = [7, 30, 90]

function Tile({ label, value, sub, tone }: { label: string; value: string; sub?: string; tone?: "warn" | "bad" }) {
  return (
    <div className="surface-card p-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className={`mt-1 text-xl font-semibold ${tone === "bad" ? "text-red-400" : tone === "warn" ? "text-amber-400" : ""}`}>{value}</p>
      {sub && <p className="mt-0.5 text-[11px] text-muted-foreground">{sub}</p>}
    </div>
  )
}

function BreakdownTable({ title, rows, labelFor }: { title: string; rows: (KpiBlock & { key: string })[]; labelFor: (key: string) => string }) {
  if (rows.length === 0) return null
  return (
    <section>
      <h4 className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">{title}</h4>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[520px] text-sm">
          <thead>
            <tr className="border-b border-border text-left text-xs text-muted-foreground">
              <th className="py-1.5 pr-3 font-medium" />
              <th className="py-1.5 pr-3 font-medium">Opened</th>
              <th className="py-1.5 pr-3 font-medium">Resolved</th>
              <th className="py-1.5 pr-3 font-medium">To respond</th>
              <th className="py-1.5 pr-3 font-medium">To resolve</th>
              <th className="py-1.5 font-medium">First-touch</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.key} className="border-b border-border/60 last:border-0">
                <td className="py-1.5 pr-3 font-medium">{labelFor(r.key)}</td>
                <td className="py-1.5 pr-3">{r.opened}</td>
                <td className="py-1.5 pr-3">{r.resolved}</td>
                <td className="py-1.5 pr-3">{formatHours(r.mean_hours_to_respond)}</td>
                <td className="py-1.5 pr-3">{formatHours(r.mean_hours_to_resolve)}</td>
                <td className="py-1.5">{formatPct(r.first_touch_resolution_pct)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

/** How the desk is performing: response and resolution times, first-touch resolution, time in each stage, who is late. */
export function TicketPerformance({ assignees, onOpenTicket }: { assignees: Assignee[]; onOpenTicket: (id: string) => void }) {
  const [days, setDays] = useState(30)
  const [kpis, setKpis] = useState<TicketKpis | null>(null)
  const [late, setLate] = useState<LateTicket[]>([])
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [k, l] = await Promise.all([supportApi.kpis(days), supportApi.late(15)])
      setKpis(k)
      setLate(l.items)
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load the figures")
    } finally {
      setLoading(false)
    }
  }, [days])

  useEffect(() => {
    void load()
  }, [load])

  const name = (id: string | null) => (id ? assignees.find((a) => a.id === id)?.name ?? "A teammate" : "Unassigned")

  if (!kpis) {
    return (
      <div className="surface-card flex min-h-48 items-center justify-center p-6 text-sm text-muted-foreground">
        {error ? <p role="alert">{error}</p> : <Loader2 className="h-5 w-5 animate-spin" aria-label="Loading performance" />}
      </div>
    )
  }

  const o = kpis.overall
  const slowest = Math.max(1, ...kpis.time_in_stage.map((s) => s.avg_hours ?? 0))

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-muted-foreground">Tickets opened in the last {kpis.window_days} days. Times run from the moment a ticket opened.</p>
        <div className="flex items-center gap-2">
          <select className={FIELD} aria-label="Time window" value={days} onChange={(e) => setDays(Number(e.target.value))}>
            {WINDOWS.map((w) => <option key={w} value={w}>Last {w} days</option>)}
          </select>
          <Button variant="outline" size="sm" onClick={() => void load()} aria-label="Refresh performance"><RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} /></Button>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <Tile label="Time to respond" value={formatHours(o.mean_hours_to_respond)} sub={`median ${formatHours(o.median_hours_to_respond)}`} />
        <Tile label="Time to assign" value={formatHours(o.mean_hours_to_assign)} />
        <Tile label="Time to resolve" value={formatHours(o.mean_hours_to_resolve)} sub={`median ${formatHours(o.median_hours_to_resolve)}`} />
        <Tile label="First-touch resolution" value={formatPct(o.first_touch_resolution_pct)} sub="resolved by one person, no hand-offs" />
        <Tile label="Deadlines met" value={formatPct(o.sla_met_pct)} />
        <Tile label="Opened / resolved" value={`${o.opened} / ${o.resolved}`} sub={`${o.still_open} still open`} />
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        <Tile label="Open now" value={String(kpis.now.open_now)} />
        <Tile label="Unassigned" value={String(kpis.now.unassigned_now)} tone={kpis.now.unassigned_now > 0 ? "warn" : undefined} />
        <Tile label="Escalated" value={String(kpis.now.escalated_now)} />
        <Tile label="Past deadline" value={String(kpis.now.overdue_now)} tone={kpis.now.overdue_now > 0 ? "bad" : undefined} />
        <Tile label="Gone quiet" value={String(kpis.now.stale_now)} tone={kpis.now.stale_now > 0 ? "warn" : undefined} />
      </div>

      {late.length > 0 && (
        <section className="surface-card p-4">
          <h4 className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">Late or gone quiet, worst first</h4>
          <ul className="divide-y divide-border" aria-label="Late tickets">
            {late.map((t) => (
              <li key={t.id}>
                <button type="button" className="flex w-full flex-wrap items-center gap-x-3 gap-y-1 py-2 text-left hover:bg-muted/40" onClick={() => onOpenTicket(t.id)}>
                  <span className="font-mono text-xs text-muted-foreground">{t.ref ?? t.id.slice(0, 8)}</span>
                  <span className="min-w-0 flex-1 truncate text-sm font-medium">{t.subject}</span>
                  <Badge variant="outline" className={`text-[10px] ${PRIORITY_TONE[t.priority]}`}>{labelOf({}, t.priority)}</Badge>
                  <span className="text-xs text-muted-foreground">{labelOf(STATUS_LABELS, t.status)} · {name(t.assigned_to)}</span>
                  <span className={`text-xs font-medium ${t.overdue ? "text-red-400" : "text-amber-400"}`}>
                    {t.overdue ? `${formatHours(t.hours_overdue)} past deadline` : `quiet for ${formatHours(t.hours_idle)}`}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

      {kpis.time_in_stage.length > 0 && (
        <section>
          <h4 className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">Average time spent in each stage</h4>
          <ul className="space-y-2" aria-label="Time in stage">
            {kpis.time_in_stage.map((s) => (
              <li key={s.status} className="grid grid-cols-[7rem_minmax(0,1fr)_5rem] items-center gap-3 text-sm">
                <span>{labelOf(STATUS_LABELS, s.status)}</span>
                <span className="h-2 rounded-full bg-muted" aria-hidden>
                  <span className="block h-2 rounded-full bg-primary" style={{ width: `${Math.max(2, ((s.avg_hours ?? 0) / slowest) * 100)}%` }} />
                </span>
                <span className="text-right text-xs text-muted-foreground">{formatHours(s.avg_hours)} · {s.tickets}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <BreakdownTable title="By person (tickets assigned to them)" rows={kpis.by_assignee.map((a) => ({ ...a, key: a.id }))}
        labelFor={(id) => kpis.by_assignee.find((a) => a.id === id)?.name || assignees.find((a) => a.id === id)?.name || "A teammate"} />
      <BreakdownTable title="By queue" rows={kpis.by_queue} labelFor={(k) => labelOf({}, k)} />
      <BreakdownTable title="By category" rows={kpis.by_category} labelFor={(k) => labelOf(CATEGORY_LABELS, k)} />
    </div>
  )
}
