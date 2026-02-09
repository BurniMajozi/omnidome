import { cn } from "@/lib/utils"
import { type LucideIcon, TrendingUp, TrendingDown } from "lucide-react"
import { useIsClient } from "@/lib/use-is-client"

interface StatCardProps {
  title: string
  value: string
  change: string
  changeType: "positive" | "negative" | "neutral"
  icon: LucideIcon
  description?: string
  isCurrency?: boolean
}

export function StatCard({
  title,
  value,
  change,
  changeType,
  icon: Icon,
  description,
  isCurrency = false,
}: StatCardProps) {
  const isClient = useIsClient()

  const displayValue = !isClient
    ? (isCurrency ? "R --" : value)
    : isCurrency
      ? `R ${Number.parseFloat(value.replace(/[^0-9.]/g, "")).toLocaleString("en-ZA", { maximumFractionDigits: 0 })}`
      : value

  return (
    <div className="rounded-xl border border-border bg-card p-4 sm:p-5">
      <div className="flex items-start justify-between">
        <div className="space-y-1">
          <p className="text-xs font-medium text-muted-foreground sm:text-sm">{title}</p>
          <p className="text-xl font-bold text-foreground sm:text-2xl">{displayValue}</p>
        </div>
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/10 sm:h-10 sm:w-10">
          <Icon className="h-4.5 w-4.5 text-primary sm:h-5 sm:w-5" />
        </div>
      </div>
      <div className="mt-3 flex items-center gap-2">
        <div
          className={cn(
            "flex items-center gap-1 text-[11px] font-medium sm:text-xs",
            changeType === "positive" && "text-primary",
            changeType === "negative" && "text-destructive",
            changeType === "neutral" && "text-muted-foreground",
          )}
        >
          {changeType === "positive" && <TrendingUp className="h-3 w-3" />}
          {changeType === "negative" && <TrendingDown className="h-3 w-3" />}
          {change}
        </div>
        {description && <span className="text-xs text-muted-foreground">{description}</span>}
      </div>
    </div>
  )
}
