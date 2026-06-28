"use client"

import type { ReactNode } from "react"
import { cn } from "@/lib/utils"

interface PageHeaderProps {
  title: string
  subtitle?: string
  icon?: ReactNode
  /** Right-aligned actions (buttons, dropdowns, etc.) */
  actions?: ReactNode
  /** Optional status badge shown next to title */
  badge?: ReactNode
  className?: string
  /** Extra content below the title row (e.g. breadcrumbs, tab switcher) */
  below?: ReactNode
}

/**
 * Uniform module / page header with Z-flow:
 *   Icon + Title + Badge  →  Subtitle  →  Actions (right-aligned)
 *
 * Usage:
 *   <PageHeader
 *     title="Call Center"
 *     subtitle="Manage agents, queues and live sessions"
 *     icon={<Headset className="h-5 w-5 text-primary" />}
 *     actions={<Button variant="cta" size="sm"><Plus />New Agent</Button>}
 *   />
 */
export function PageHeader({ title, subtitle, icon, actions, badge, className, below }: PageHeaderProps) {
  return (
    <div className={cn("module-header", className)}>
      {/* Left: title + subtitle */}
      <div className="flex items-start gap-3 min-w-0">
        {icon && (
          <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/15">
            {icon}
          </div>
        )}
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="page-title truncate">{title}</h1>
            {badge}
          </div>
          {subtitle && (
            <p className="mt-0.5 text-sm text-muted-foreground">{subtitle}</p>
          )}
        </div>
      </div>

      {/* Right: actions */}
      {actions && (
        <div className="module-header-actions shrink-0">
          {actions}
        </div>
      )}

      {/* Below row (spans full width) */}
      {below && <div className="w-full">{below}</div>}
    </div>
  )
}
