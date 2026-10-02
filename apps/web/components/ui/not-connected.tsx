"use client"

import type { ReactNode } from "react"
import { CloudOff, AlertTriangle, RefreshCcw } from "lucide-react"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import { describeLoadable, tileLabel, type Loadable } from "@/lib/service-state"

/**
 * Honest replacement for fabricated figures. Use <StatValue> inside KPI tiles
 * and <NotConnected> in place of charts/tables/lists that have no real data.
 */

/** Renders `children(data)` when ready; otherwise a compact state label. */
export function StatValue<T>({
  loadable,
  children,
  className,
}: {
  loadable: Loadable<T>
  children: (data: T) => ReactNode
  className?: string
}) {
  if (loadable.state === "ready") return <>{children(loadable.data)}</>
  if (loadable.state === "loading") {
    return <span className={cn("inline-block h-7 w-24 animate-pulse rounded bg-muted align-middle", className)} aria-label="Loading" />
  }
  return <span className={cn("text-sm font-medium text-muted-foreground", className)}>{tileLabel(loadable)}</span>
}

export function NotConnected({
  loadable,
  service = "Service",
  onRetry,
  className,
  emptyTitle,
  deniedDetail,
}: {
  loadable: Loadable<unknown>
  service?: string
  onRetry?: () => void
  className?: string
  /** Shown only for `state: "ready"` misuse; normally callers render their own empty state. */
  emptyTitle?: string
  /** Replaces the generic "no access" copy for a 403, e.g. "Not permitted: requires finance admin". */
  deniedDetail?: string
}) {
  if (loadable.state === "loading") {
    return <div className={cn("h-24 animate-pulse rounded-lg bg-muted/50", className)} aria-label="Loading" />
  }
  const base = describeLoadable(loadable, service)
  const copy = base && loadable.state === "denied" && loadable.status === 403 && deniedDetail ? { title: "Not permitted", detail: deniedDetail } : base
  const Icon = loadable.state === "error" ? AlertTriangle : CloudOff
  return (
    <div
      role="status"
      className={cn(
        "flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-border bg-secondary/20 p-6 text-center",
        className,
      )}
    >
      <Icon className="h-5 w-5 text-muted-foreground" />
      <p className="text-sm font-semibold text-foreground">{copy?.title ?? emptyTitle ?? "No data yet"}</p>
      {copy && <p className="max-w-sm text-xs text-muted-foreground">{copy.detail}</p>}
      {onRetry && loadable.state !== "ready" && (
        <Button variant="outline" size="sm" onClick={onRetry}>
          <RefreshCcw className="h-3.5 w-3.5" />
          Retry
        </Button>
      )}
    </div>
  )
}

/** Connected but no rows: honest empty state (zeros are real, samples are not). */
export function NoDataYet({ message = "No data yet", className }: { message?: string; className?: string }) {
  return (
    <div className={cn("rounded-lg border border-dashed border-border bg-secondary/20 p-6 text-center text-sm text-muted-foreground", className)}>
      {message}
    </div>
  )
}
