import type { ReactNode } from "react"
import { cn } from "@/lib/utils"

interface SectionHeaderProps {
  title: string
  description?: string
  actions?: ReactNode
  className?: string
}

/**
 * Lightweight section divider with title and optional inline actions.
 * Use inside a Card or between content blocks — not at page level (use PageHeader instead).
 */
export function SectionHeader({ title, description, actions, className }: SectionHeaderProps) {
  return (
    <div className={cn("flex items-start justify-between gap-4 mb-4", className)}>
      <div>
        <h3 className="section-title">{title}</h3>
        {description && (
          <p className="mt-0.5 text-xs text-muted-foreground">{description}</p>
        )}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </div>
  )
}

/**
 * Thin horizontal rule with an optional centre label — for separating major visual zones.
 */
export function SectionDivider({ label, className }: { label?: string; className?: string }) {
  if (!label) {
    return <hr className={cn("border-border my-6", className)} />
  }
  return (
    <div className={cn("relative my-6 flex items-center", className)}>
      <div className="flex-1 border-t border-border" />
      <span className="mx-3 label-sm">{label}</span>
      <div className="flex-1 border-t border-border" />
    </div>
  )
}
