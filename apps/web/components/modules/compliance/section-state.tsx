"use client"

import type { ReactNode } from "react"
import { AlertTriangle, CloudOff, Lock, RefreshCcw } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import type { Loadable } from "@/lib/service-state"
import { describeSection } from "@/lib/compliance-state"

/**
 * Honest per-section states for the Compliance Center. Every tab renders its
 * content only when its data actually loaded; otherwise the user is told WHY
 * it is empty: service not running, error (with Retry), or not permitted.
 * A section that loaded but has no rows renders its own real empty state.
 */

export function SectionStateNotice({
  state,
  onRetry,
  className,
}: {
  state: Loadable<unknown>
  onRetry?: () => void
  className?: string
}) {
  if (state.state === "loading") {
    return <div className={cn("h-32 animate-pulse rounded-lg bg-muted/50", className)} aria-label="Loading" />
  }
  const copy = describeSection(state)
  if (!copy) return null
  const Icon = state.state === "error" ? AlertTriangle : state.state === "denied" ? Lock : CloudOff
  return (
    <div
      role="status"
      data-section-state={state.state}
      className={cn(
        "flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-border bg-secondary/20 p-8 text-center",
        className,
      )}
    >
      <Icon className="h-5 w-5 text-muted-foreground" />
      <p className="text-sm font-semibold text-foreground">{copy.title}</p>
      <p className="max-w-md text-xs text-muted-foreground">{copy.detail}</p>
      {onRetry && state.state !== "denied" && (
        <Button variant="outline" size="sm" onClick={onRetry}>
          <RefreshCcw className="h-3.5 w-3.5" />
          Retry
        </Button>
      )}
    </div>
  )
}

/** Renders children only when the section is ready; a notice otherwise. */
export function SectionGate({
  state,
  onRetry,
  children,
}: {
  state: Loadable<unknown> | undefined
  onRetry?: () => void
  children: ReactNode
}) {
  const s: Loadable<unknown> = state ?? { state: "loading" }
  if (s.state === "ready") return <>{children}</>
  return <SectionStateNotice state={s} onRetry={onRetry} />
}

/** Slim inline banner for a secondary data source that failed while the rest of the tab loaded. */
export function PartialNotice({
  state,
  label,
  onRetry,
}: {
  state: Loadable<unknown> | undefined
  label: string
  onRetry?: () => void
}) {
  if (!state || state.state === "ready" || state.state === "loading") return null
  const copy = describeSection(state)
  if (!copy) return null
  return (
    <div
      role="status"
      className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-amber-500/30 bg-amber-500/5 px-3 py-2 text-xs text-amber-300"
    >
      <span>
        {label}: {copy.title}. {copy.detail}
      </span>
      {onRetry && state.state !== "denied" && (
        <Button variant="outline" size="sm" className="h-7" onClick={onRetry}>
          <RefreshCcw className="h-3 w-3" />
          Retry
        </Button>
      )}
    </div>
  )
}

/** Shown beside PAYE / UIF / SDL figures while the backend says rates are not verified. */
export function RatesNotVerifiedChip({ className }: { className?: string }) {
  return (
    <Badge
      variant="outline"
      className={cn("border-amber-500/40 text-amber-400 text-[10px] font-medium", className)}
      title="The PAYE, UIF and SDL rates used have not been verified against current SARS tables. Check figures on eFiling before paying."
    >
      Rates not verified with SARS
    </Badge>
  )
}
