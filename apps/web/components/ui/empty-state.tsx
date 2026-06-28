import type { ReactNode } from "react"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"

interface EmptyStateProps {
  icon?: ReactNode
  title: string
  description?: string
  action?: {
    label: string
    onClick: () => void
    variant?: "cta" | "default" | "outline"
  }
  className?: string
}

/**
 * Consistent empty state displayed inside lists, tables and cards
 * when there is no data to show.
 */
export function EmptyState({ icon, title, description, action, className }: EmptyStateProps) {
  return (
    <div className={cn("empty-state", className)}>
      {icon && (
        <div className="empty-state-icon">{icon}</div>
      )}
      <div>
        <p className="text-sm font-semibold text-foreground">{title}</p>
        {description && (
          <p className="mt-1 text-xs text-muted-foreground max-w-xs mx-auto">{description}</p>
        )}
      </div>
      {action && (
        <Button variant={action.variant ?? "outline"} size="sm" onClick={action.onClick}>
          {action.label}
        </Button>
      )}
    </div>
  )
}
