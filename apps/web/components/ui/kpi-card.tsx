"use client"

import { useState, type ReactNode } from "react"
import { TrendingUp, TrendingDown, Minus } from "lucide-react"
import { cn } from "@/lib/utils"

type TrendDir = "up" | "down" | "neutral"
type TrendSentiment = "positive" | "negative" | "neutral"

export interface KPICardProps {
  title: string
  value: string | number
  /** e.g. "+12%" or "-3 pts" */
  trend?: string
  /** Whether a positive trend is good (default true). Set false for metrics like churn rate */
  positiveIsGood?: boolean
  trendDir?: TrendDir
  icon?: ReactNode
  /** Accent color for the icon bubble. Defaults to primary. */
  iconColor?: string
  /** If provided, renders a flip-back detail view */
  detail?: {
    title?: string
    rows: { label: string; value: string }[]
    note?: string
  }
  className?: string
  loading?: boolean
}

function trendSentiment(dir: TrendDir, positiveIsGood: boolean): TrendSentiment {
  if (dir === "neutral") return "neutral"
  if (dir === "up") return positiveIsGood ? "positive" : "negative"
  return positiveIsGood ? "negative" : "positive"
}

function TrendBadge({ dir, sentiment, label }: { dir: TrendDir; sentiment: TrendSentiment; label: string }) {
  const color =
    sentiment === "positive"
      ? "text-emerald-400 border-emerald-500/30 bg-emerald-500/10"
      : sentiment === "negative"
        ? "text-red-400 border-red-500/30 bg-red-500/10"
        : "text-muted-foreground border-border bg-muted/40"
  return (
    <span className={cn("inline-flex items-center gap-0.5 rounded-full border px-1.5 py-0.5 text-xs font-medium", color)}>
      {dir === "up" ? (
        <TrendingUp className="h-3 w-3" />
      ) : dir === "down" ? (
        <TrendingDown className="h-3 w-3" />
      ) : (
        <Minus className="h-3 w-3" />
      )}
      {label}
    </span>
  )
}

/**
 * Uniform KPI card with optional flip-to-detail.
 * Replaces the various ad-hoc KPI implementations across modules.
 */
export function KPICard({
  title,
  value,
  trend,
  positiveIsGood = true,
  trendDir,
  icon,
  iconColor,
  detail,
  className,
  loading = false,
}: KPICardProps) {
  const [flipped, setFlipped] = useState(false)

  const dir: TrendDir = trendDir ?? (trend?.startsWith("-") ? "down" : trend ? "up" : "neutral")
  const sentiment = trendSentiment(dir, positiveIsGood)

  const handleClick = () => {
    if (detail) setFlipped((f) => !f)
  }

  return (
    <div
      className={cn(
        "kpi-card",
        detail && "cursor-pointer select-none",
        className,
      )}
      onClick={handleClick}
      role={detail ? "button" : undefined}
      tabIndex={detail ? 0 : undefined}
      onKeyDown={detail ? (e) => e.key === "Enter" && setFlipped((f) => !f) : undefined}
    >
      {!flipped ? (
        /* ── Front ─────────────────────────────────────────────────────────── */
        <>
          <div className="flex items-start justify-between">
            {icon ? (
              <div
                className="kpi-icon-wrap"
                style={iconColor ? { backgroundColor: `${iconColor}22`, color: iconColor } : undefined}
              >
                {icon}
              </div>
            ) : (
              <div />
            )}
            {trend && (
              <TrendBadge dir={dir} sentiment={sentiment} label={trend} />
            )}
          </div>

          <div className="mt-auto">
            <p className="label-sm mb-1">{title}</p>
            <p className="metric-value">
              {loading ? <span className="animate-pulse text-muted-foreground">—</span> : value}
            </p>
          </div>

          {detail && (
            <p className="text-xs text-muted-foreground/60">Click for details</p>
          )}
        </>
      ) : (
        /* ── Back (detail) ──────────────────────────────────────────────── */
        <>
          <p className="card-title">{detail?.title ?? title}</p>
          <div className="mt-1 flex-1 space-y-1.5 overflow-auto scrollbar-thin">
            {detail?.rows.map((row, i) => (
              <div key={i} className="flex items-center justify-between text-sm">
                <span className="text-muted-foreground">{row.label}</span>
                <span className="font-medium text-foreground tabular-nums">{row.value}</span>
              </div>
            ))}
          </div>
          {detail?.note && (
            <p className="mt-2 text-xs text-emerald-400">{detail.note}</p>
          )}
        </>
      )}
    </div>
  )
}

/**
 * Container for a row of KPI cards with consistent grid layout.
 */
export function KPIGrid({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn("kpi-grid", className)}>{children}</div>
}
