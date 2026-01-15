import { useState, useEffect } from "react"
import { cn } from "@/lib/utils"
import { type LucideIcon, TrendingUp, TrendingDown } from "lucide-react"

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
  const [mounted, setMounted] = useState(false)

  useEffect(() => {
    setMounted(true)
  }, [])

  const displayValue = !mounted
    ? (isCurrency ? "R --" : value)
    : isCurrency
      ? `R ${Number.parseFloat(value.replace(/[^0-9.]/g, "")).toLocaleString("en-ZA", { maximumFractionDigits: 0 })}`
      : value

  return (
    <div className="rounded-xl border border-border bg-card p-5">
      <div className="flex items-start justify-between">
        <div className="space-y-1">
          <p className="text-sm font-medium text-muted-foreground">{title}</p>
          <p className="text-2xl font-bold text-foreground">{displayValue}</p>
        </div>
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10">
          <Icon className="h-5 w-5 text-primary" />
        </div>
      </div>
      <div className="mt-3 flex items-center gap-2">
        <div
          className={cn(
            "flex items-center gap-1 text-xs font-medium",
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
