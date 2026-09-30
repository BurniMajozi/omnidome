"use client"

import { Badge } from "@/components/ui/badge"
import { NotConnected, NoDataYet } from "@/components/ui/not-connected"
import { loadEscalations } from "@/lib/ops-api"
import { ESCALATIONS_KEY, useSharedOps } from "@/lib/overview-api"
import { partialNote, relativeTime, type EscalationRow } from "@/lib/ops-derive"

const statusColors: Record<string, string> = {
  open: "bg-destructive/20 text-destructive",
  in_progress: "bg-chart-2/20 text-chart-2",
  resolved: "bg-primary/20 text-primary",
  closed: "bg-primary/20 text-primary",
}

const statusLabel = (s: string) => s.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase())
const shortId = (e: EscalationRow) => e.ticket_id || `ESC-${String(e.id).slice(0, 8)}`

/** Latest escalations from the communication service (real rows only). */
export function TicketsTable() {
  // Same request as the Overview KPI strip: shared, so the page fetches escalations once.
  const { value, reload } = useSharedOps(ESCALATIONS_KEY, loadEscalations)
  const note = value.state === "ready" ? partialNote(value.data) : null
  const rows: EscalationRow[] =
    value.state === "ready"
      ? [...(value.data.rows as EscalationRow[])]
          .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
          .slice(0, 5)
      : []

  return (
    <div className="rounded-xl border border-border bg-card">
      <div className="border-b border-border p-5">
        <h3 className="text-lg font-semibold text-foreground">Recent Escalations</h3>
        {note && <p className="mt-1 text-xs text-amber-400">{note} The newest rows shown may not be the latest.</p>}
      </div>
      {value.state !== "ready" ? (
        <div className="p-4">
          <NotConnected loadable={value} service="The communication service" onRetry={reload} />
        </div>
      ) : rows.length === 0 ? (
        <div className="p-4">
          <NoDataYet message="No escalations yet" />
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[560px]">
            <thead>
              <tr className="border-b border-border text-left">
                <th className="px-5 py-3 text-xs font-medium uppercase text-muted-foreground">Reference</th>
                <th className="px-5 py-3 text-xs font-medium uppercase text-muted-foreground">Reason</th>
                <th className="px-5 py-3 text-xs font-medium uppercase text-muted-foreground">Status</th>
                <th className="px-5 py-3 text-xs font-medium uppercase text-muted-foreground">Raised</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((e) => (
                <tr key={e.id} className="border-b border-border last:border-0 hover:bg-secondary/30">
                  <td className="px-5 py-4 text-sm font-medium text-primary">{shortId(e)}</td>
                  <td className="px-5 py-4 text-sm text-foreground">{e.reason || "—"}</td>
                  <td className="px-5 py-4">
                    <Badge variant="secondary" className={statusColors[e.status] ?? "bg-secondary text-foreground"}>
                      {statusLabel(e.status)}
                    </Badge>
                  </td>
                  <td className="px-5 py-4 text-sm text-muted-foreground">{relativeTime(e.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
