"use client"

import { Badge } from "@/components/ui/badge"
import { pct, type Metrics } from "@/lib/supplier-api"

export const GRADE_CLS: Record<string, string> = {
  Excellent: "border-emerald-500/40 text-emerald-400",
  Good: "border-blue-500/40 text-blue-400",
  Fair: "border-amber-500/40 text-amber-400",
  Poor: "border-red-500/40 text-red-400",
  "Not enough data": "border-border text-muted-foreground",
}

export function ScoreBadge({ m }: { m: Pick<Metrics, "score" | "grade"> }) {
  return (
    <Badge variant="outline" className={`text-[10px] font-medium ${GRADE_CLS[m.grade] ?? GRADE_CLS["Not enough data"]}`} title="Composite of on-time delivery, fill rate, quality, returns and ratings">
      {m.score === null ? "No score yet" : `${m.score.toFixed(0)} · ${m.grade}`}
    </Badge>
  )
}

function Tile({ label, value, hint, tone }: { label: string; value: string; hint?: string; tone?: "good" | "warn" | "bad" }) {
  const cls = tone === "good" ? "text-emerald-400" : tone === "warn" ? "text-amber-400" : tone === "bad" ? "text-red-400" : "text-foreground"
  return (
    <div className="rounded-lg border border-border bg-card/60 p-3">
      <div className="text-[11px] text-muted-foreground">{label}</div>
      <div className={`mt-0.5 text-lg font-semibold ${cls}`}>{value}</div>
      {hint && <div className="mt-0.5 text-[11px] text-muted-foreground">{hint}</div>}
    </div>
  )
}

const tone = (v: number | null, good: number, warn: number): "good" | "warn" | "bad" | undefined =>
  v === null ? undefined : v >= good ? "good" : v >= warn ? "warn" : "bad"

/** The six things a buyer asks about a supplier, plus lead time. Empty values say "no data", never zero. */
export function MetricTiles({ m }: { m: Metrics }) {
  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
      <Tile label="Performance score" value={m.score === null ? "—" : m.score.toFixed(0)} hint={m.score === null ? `Needs 3 deliveries (has ${m.deliveries})` : m.grade} tone={m.score === null ? undefined : tone(m.score, 90, 75)} />
      <Tile label="On-time delivery" value={pct(m.on_time_rate)} hint={m.on_time_known ? `${m.on_time_known} order(s) with a due date` : "No due dates recorded"} tone={tone(m.on_time_rate, 0.9, 0.75)} />
      <Tile label="Average days late" value={m.avg_days_late === null ? "—" : m.avg_days_late.toFixed(1)} hint="Early counts as 0" tone={m.avg_days_late === null ? undefined : m.avg_days_late <= 1 ? "good" : m.avg_days_late <= 3 ? "warn" : "bad"} />
      <Tile label="Order fill rate" value={pct(m.fill_rate)} hint={m.units_ordered ? `${m.units_accepted} of ${m.units_ordered} units accepted` : undefined} tone={tone(m.fill_rate, 0.95, 0.85)} />
      <Tile label="Quality (accepted)" value={m.rejection_rate === null ? "—" : pct(1 - m.rejection_rate)} hint={m.units_received ? `${m.units_rejected} of ${m.units_received} units rejected at receiving` : undefined} tone={m.rejection_rate === null ? undefined : tone(1 - m.rejection_rate, 0.98, 0.93)} />
      <Tile label="Returned to supplier" value={String(m.units_returned)} hint={m.return_rate === null ? undefined : `${pct(m.return_rate)} of accepted units`} tone={m.return_rate === null ? undefined : m.return_rate <= 0.01 ? "good" : m.return_rate <= 0.04 ? "warn" : "bad"} />
      <Tile label="Receiver rating" value={m.avg_rating === null ? "—" : `${m.avg_rating.toFixed(1)} / 5`} hint={m.ratings ? `${m.ratings} rated deliver${m.ratings === 1 ? "y" : "ies"}` : "No ratings yet"} tone={m.avg_rating === null ? undefined : m.avg_rating >= 4.2 ? "good" : m.avg_rating >= 3.3 ? "warn" : "bad"} />
      <Tile label="Actual lead time" value={m.avg_lead_days === null ? "—" : `${m.avg_lead_days.toFixed(0)} days`} hint="Order date to first receipt" />
    </div>
  )
}

export function RejectionReasons({ m }: { m: Metrics }) {
  if (!m.top_rejection_reasons.length) return null
  return (
    <p className="text-[11px] text-muted-foreground">
      Most common rejection reasons: {m.top_rejection_reasons.map((r) => `${r.reason} (${r.units})`).join(", ")}
    </p>
  )
}
