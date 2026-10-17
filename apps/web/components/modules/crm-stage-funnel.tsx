"use client"

import { leadStageDistribution } from "@/lib/crm-derive"

const FUNNEL_ORDER = ["NEW", "CONTACTED", "QUALIFIED", "PROPOSAL", "NEGOTIATION", "CONVERTED"]
const COLORS = ["#3b82f6", "#6366f1", "#8b5cf6", "#d946ef", "#f59e0b", "#10b981"]

const label = (s: string) => s.charAt(0) + s.slice(1).toLowerCase()

/**
 * Funnel of CRM lead stages in pipeline order. Each bar is the number of leads that have
 * reached that stage or beyond (current stage + all later stages), so widths shrink
 * monotonically and the % between stages is a reach-rate. Lost/disqualified leads are shown
 * apart: their last stage is not recorded, so they cannot be placed in the funnel.
 */
export function CrmStageFunnel({ counts }: { counts: Record<string, number> }) {
  const dist = leadStageDistribution(counts)
  const byStage = Object.fromEntries(dist.map((d) => [d.stage, d.count]))
  const total = dist.reduce((a, d) => a + d.count, 0)
  if (total === 0) {
    return <p className="text-sm text-muted-foreground">No leads yet. Add or import leads and the funnel will fill in.</p>
  }
  const reached: number[] = []
  let running = 0
  for (let i = FUNNEL_ORDER.length - 1; i >= 0; i--) {
    running += byStage[FUNNEL_ORDER[i]] ?? 0
    reached[i] = running
  }
  const max = reached[0] || 1
  const others = dist.filter((d) => !FUNNEL_ORDER.includes(d.stage) && d.count > 0)

  return (
    <div className="space-y-1">
      {FUNNEL_ORDER.map((stage, i) => {
        const count = reached[i]
        const width = Math.max((count / max) * 100, count > 0 ? 6 : 0)
        const conv = i > 0 && reached[i - 1] > 0 ? Math.round((count / reached[i - 1]) * 100) : null
        return (
          <div key={stage}>
            {conv !== null && (
              <div className="py-0.5 text-center text-[11px] text-muted-foreground">↓ {conv}% advance from {label(FUNNEL_ORDER[i - 1])}</div>
            )}
            <div className="flex items-center gap-3">
              <div className="w-28 shrink-0 text-sm font-medium">{label(stage)}</div>
              <div className="flex flex-1 justify-center">
                <div
                  className="flex h-9 items-center justify-center rounded-md text-sm font-semibold text-white transition-all"
                  style={{ width: `${width}%`, backgroundColor: COLORS[i], minWidth: count > 0 ? 40 : 0 }}
                  title={`${count} leads reached ${label(stage)} or beyond`}
                >
                  {count > 0 ? count : ""}
                </div>
                {count === 0 && <span className="text-xs text-muted-foreground">0</span>}
              </div>
              <div className="w-14 shrink-0 text-right text-xs text-muted-foreground">{Math.round((count / max) * 100)}%</div>
            </div>
          </div>
        )
      })}
      <div className="flex flex-wrap gap-2 pt-3 text-xs text-muted-foreground">
        <span>Out of funnel:</span>
        {others.length === 0 ? <span>none</span> : others.map((o) => (
          <span key={o.stage} className="rounded border px-2 py-0.5">{label(o.stage)} {o.count}</span>
        ))}
        <span className="ml-auto">{total} leads total</span>
      </div>
    </div>
  )
}
